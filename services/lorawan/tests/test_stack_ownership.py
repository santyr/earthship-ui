"""Exercise actual integration entrypoints against foreign Docker inventory."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from services.lorawan.tests import browser_auth, integration_probe, test_integration


@pytest.fixture
def foreign_stack(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SENSOR_INTEGRATION', '1')
    monkeypatch.setenv('SENSOR_QUALIFICATION_NONCE', 'a' * 32)
    private = tmp_path / '.superpowers/lorawan-private'
    private.mkdir(parents=True)
    for name in ['ingest', 'simulator']:
        path = private / (name + '.json')
        path.write_text(json.dumps(dict(environment='simulation', mqtt_host='mqtt', mqtt_port=1883,
            mqtt_username='fixture', mqtt_password='fixture', database_dsn='sqlite:fixture')))
        path.chmod(0o600)
    # A foreign inventory must stop each real caller before any network or
    # state-changing Docker command. Do not mock the preflight under test.
    calls = []
    def docker(args, **kwargs):
        calls.append(args)
        if 'config' in args:
            return Mock(stdout='{}', returncode=0)
        if 'ps' in args:
            return Mock(stdout='a' * 64 + '\n', returncode=0)
        if 'inspect' in args:
            return Mock(stdout=json.dumps([{'Id': 'a' * 64, 'Config': {'Labels': {
                'com.docker.compose.project': 'earthship-sensors-test',
                'com.docker.compose.project.working_dir': '/foreign/checkout/deploy/lorawan',
            }}}]), returncode=0)
        pytest.fail('Docker mutation attempted before ownership refusal: ' + repr(args))
    monkeypatch.setattr('subprocess.run', docker)
    monkeypatch.setattr('subprocess.check_output', lambda args, **kw: docker(args, **kw).stdout)
    network = Mock(side_effect=AssertionError('network effect before ownership refusal'))
    monkeypatch.setattr('urllib.request.urlopen', network)
    monkeypatch.setattr('services.lorawan.runtime.mqtt_client', network)
    monkeypatch.setattr(browser_auth, 'request', network)
    return calls, network, private


def test_python_suite_refuses_foreign_stack_before_first_http_or_publish(foreign_stack):
    calls, network, _ = foreign_stack
    with pytest.raises(RuntimeError, match='(?i)(ownership|isolat|fixture)'):
        test_integration.ready_software_path.__wrapped__()
    network.assert_not_called()


def test_browser_auth_refuses_foreign_stack_before_account_creation(foreign_stack):
    _, network, private = foreign_stack
    with pytest.raises(RuntimeError, match='(?i)(ownership|isolat|fixture)'):
        browser_auth.prepare_browser_auth()
    network.assert_not_called()
    assert not (private / 'browser-auth.json').exists()


def test_standalone_publisher_refuses_foreign_stack_before_mqtt(foreign_stack):
    _, network, _ = foreign_stack
    with pytest.raises(RuntimeError, match='(?i)(ownership|isolat|fixture)'):
        integration_probe.publisher()
    network.assert_not_called()


@pytest.fixture
def owned_stack(monkeypatch, tmp_path):
    """Snapshot is a read-only Docker Compose render, not a preflight mock."""
    from services.lorawan.tests import stack_ownership as ownership
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SENSOR_INTEGRATION', '1')
    monkeypatch.setenv('SENSOR_QUALIFICATION_NONCE', 'a' * 32)
    monkeypatch.setattr(ownership, 'ROOT', tmp_path)
    monkeypatch.setattr(ownership, '_bound_ids', None)
    monkeypatch.setattr(ownership, '_bound_config', None)
    source = Path(__file__).with_name('fixtures') / 'compose.test.rendered.json'
    rendered = json.loads(source.read_text().replace('@WORKTREE@', str(tmp_path)))
    compose = tmp_path / 'deploy/lorawan/compose.test.yaml'
    compose.parent.mkdir(parents=True)
    compose.write_text('# fixture source bound during inspection\n')
    containers = []
    for index, service in enumerate(['mqtt', 'postgres', 'ingest', 'openhab', 'redis', 'chirpstack'], 1):
        spec = rendered['services'][service]
        mounts = []
        for volume in spec['volumes']:
            mount = {'Type': volume['type'], 'Destination': volume['target']}
            if volume['type'] == 'bind':
                mount['Source'] = volume['source']
            elif volume['type'] == 'volume':
                mount['Name'] = rendered['volumes'][volume['source']]['name']
            mounts.append(mount)
        ports = {str(port['target']) + '/tcp': [{'HostIp': port['host_ip'], 'HostPort': port['published']}]
                 for port in spec.get('ports', [])}
        containers.append({'Id': f'{index:064x}', 'Config': {'Image': spec['image'], 'Labels': {
            'com.docker.compose.project': 'earthship-sensors-test',
            'org.earthship.sensor.qualification': 'a' * 32,
            'com.docker.compose.service': service,
            'com.docker.compose.project.working_dir': str(compose.parent),
            'com.docker.compose.project.config_files': str(compose),
        }}, 'Mounts': mounts, 'NetworkSettings': {'Ports': ports}, 'State': {'Running': True}})
    # Independent resource fixture, including no-swap Docker semantics.
    caps={'mqtt':(64,250000000,8),'postgres':(256,1000000000,20),'ingest':(192,500000000,8),
          'openhab':(1152,2000000000,144),'redis':(64,250000000,8),'chirpstack':(192,1000000000,8)}
    for container in containers:
        service=container['Config']['Labels']['com.docker.compose.service'];m,c,t=caps[service]
        container['HostConfig']={'Memory':m*1024**2,'MemorySwap':m*1024**2,'NanoCpus':c,
            'PidsLimit':t,'RestartPolicy':{'Name':'no','MaximumRetryCount':0},
            'PortBindings':dict(container['NetworkSettings']['Ports'])}
        container['NetworkSettings']['Networks']={name:{} for name in rendered['services'][service]['networks']}
        container['NetworkSettings']['Networks']={rendered['networks'][name]['name']:value for name,value in container['NetworkSettings']['Networks'].items()}
        container['Image']='sha256:'+('2a8053a90d76dcdd13696f6c21ab58ad2555f59dec266cda7ba77ec80a3dd19a' if service=='ingest' else container['Id'])
    inspections, effects = [], []
    def docker(command, **kwargs):
        if 'config' in command:
            inspections.append(command)
            return Mock(stdout=json.dumps(rendered), returncode=0)
        if 'ps' in command:
            inspections.append(command)
            return Mock(stdout='\n'.join(container['Id'] for container in containers), returncode=0)
        if command[1:3]==['image','inspect']:
            name=command[-1]
            image=next(c['Image'] for c in containers if c['Config']['Image']==name)
            return Mock(stdout=json.dumps([{'Id':image}]),returncode=0)
        if command[1:3]==['volume','inspect']:
            return Mock(stdout=json.dumps([{'Name':name,'Driver':'local','Options':None,
                'Labels':{'com.docker.compose.project':'earthship-sensors-test','com.docker.compose.volume':name.removeprefix('earthship-sensors-test_')}} for name in command[3:]]),returncode=0)
        if 'inspect' in command:
            inspections.append(command)
            return Mock(stdout=json.dumps(containers), returncode=0)
        effects.append(command)
        return Mock(stdout='', returncode=0)
    monkeypatch.setattr('subprocess.run', docker)
    private = tmp_path / '.superpowers/lorawan-private'
    private.mkdir(parents=True)
    for name in ['ingest', 'simulator', 'observer']:
        path = private / (name + '.json')
        path.write_text(json.dumps(dict(environment='simulation', mqtt_host='mqtt', mqtt_port=1883,
            mqtt_username='fixture', mqtt_password='fixture', database_dsn='sqlite:fixture')))
        path.chmod(0o600)
    network = Mock(side_effect=AssertionError('foreign-stack network effect'))
    monkeypatch.setattr('urllib.request.urlopen', network)
    monkeypatch.setattr('services.lorawan.runtime.mqtt_client', network)
    monkeypatch.setattr(browser_auth, 'request', network)
    return ownership, containers, rendered, inspections, effects, network


def test_all_current_worktree_services_pass_read_only_preflight(owned_stack):
    ownership, containers, _, inspections, effects, network = owned_stack
    assert set(ownership.assert_owned_stack()) == {'mqtt', 'postgres', 'ingest', 'openhab', 'redis', 'chirpstack'}
    assert inspections
    assert effects == []
    network.assert_not_called()


def test_chirpstack_login_uses_owned_test_endpoint(owned_stack,monkeypatch):
    from io import BytesIO
    ownership,_,_,_,effects,_=owned_stack
    inspect=ownership.subprocess.run
    def docker(command,**kwargs):
        if command[1:3]==['exec','-i']:
            assert command[3]==f'{2:064x}' and command[4:6]==['psql','-U']
            return Mock(stdout='20\n',returncode=0)
        return inspect(command,**kwargs)
    monkeypatch.setattr(ownership.subprocess,'run',docker)
    requests=[]
    def urlopen(request,**kwargs):
        assert request.full_url=='http://127.0.0.1:28085/api.InternalService/Login'
        assert kwargs=={'timeout':5}
        requests.append(request.full_url)
        return BytesIO(b'grpc-status:0'+b'x'*100)
    monkeypatch.setattr('urllib.request.urlopen',urlopen)
    test_integration.test_chirpstack_database_migrations_and_login()
    assert requests==['http://127.0.0.1:28085/api.InternalService/Login'] and effects==[]


def test_chirpstack_production_endpoint_refused_before_http(owned_stack):
    ownership,_,_,_,effects,network=owned_stack
    ownership.assert_owned_stack()
    with pytest.raises(ownership.IsolationError):
        ownership.owned_urlopen('http://127.0.0.1:18085/api.InternalService/Login',timeout=5)
    assert effects==[]
    network.assert_not_called()


def test_chirpstack_production_port_refused_in_owned_stack(owned_stack):
    ownership,containers,rendered,_,effects,network=owned_stack
    rendered['services']['chirpstack']['ports'][0]['published']='18085'
    chirpstack=next(c for c in containers if c['Config']['Labels']['com.docker.compose.service']=='chirpstack')
    chirpstack['HostConfig']['PortBindings']['8080/tcp'][0]['HostPort']='18085'
    chirpstack['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort']='18085'
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]
    network.assert_not_called()


@pytest.mark.parametrize('service', ['mqtt', 'postgres', 'ingest', 'openhab', 'redis', 'chirpstack'])
@pytest.mark.parametrize('entrypoint', ['python-suite', 'browser-auth', 'publisher'])
def test_each_entrypoint_refuses_any_foreign_service_before_effects(owned_stack, service, entrypoint):
    ownership, containers, _, _, effects, network = owned_stack
    container = next(container for container in containers if container['Config']['Labels']['com.docker.compose.service'] == service)
    container['Config']['Labels']['com.docker.compose.project.working_dir'] = '/foreign/checkout/deploy/lorawan'
    call = {'python-suite': test_integration.ready_software_path.__wrapped__,
            'browser-auth': browser_auth.prepare_browser_auth,
            'publisher': integration_probe.publisher}[entrypoint]
    with pytest.raises(ownership.IsolationError):
        call()
    network.assert_not_called()
    assert effects == []
    assert not (ownership.ROOT / '.superpowers/lorawan-private/browser-auth.json').exists()


@pytest.mark.parametrize('service', ['mqtt', 'openhab', 'chirpstack'])
def test_foreign_or_public_published_endpoint_refused(owned_stack, service):
    ownership, containers, _, _, effects, network = owned_stack
    container = next(container for container in containers if container['Config']['Labels']['com.docker.compose.service'] == service)
    next(iter(container['NetworkSettings']['Ports'].values()))[0]['HostIp'] = '0.0.0.0'
    with pytest.raises(ownership.IsolationError):
        test_integration.ready_software_path.__wrapped__()
    assert effects == []
    network.assert_not_called()


def test_missing_service_refused_before_network(owned_stack):
    ownership, containers, _, _, effects, network = owned_stack
    containers.pop()
    with pytest.raises(ownership.IsolationError):
        browser_auth.prepare_browser_auth()
    assert effects == []
    network.assert_not_called()


def test_lifecycle_and_database_cleanup_refuse_replaced_project(owned_stack):
    ownership, containers, _, _, effects, _ = owned_stack
    ownership.assert_owned_stack()
    containers[1]['Config']['Labels']['com.docker.compose.project.working_dir'] = '/foreign/checkout'
    for arguments in [['restart', 'mqtt'], ['start', 'postgres'],
                      ['exec', '-T', 'postgres', 'dropdb', '-U', 'postgres', 'sensors_restore_test'],
                      ['--profile', 'simulation', 'run', '--rm', 'simulator']]:
        with pytest.raises(ownership.IsolationError):
            ownership.run_compose(arguments, check=True)
    assert effects == []


def test_lifecycle_pins_original_container_and_permits_owned_stopped_service(owned_stack, monkeypatch):
    ownership, containers, _, _, effects, _ = owned_stack
    ownership.assert_owned_stack()
    containers[1]['State']['Running'] = False
    forwarded=[]
    monkeypatch.setattr(ownership, '_guardian_lifecycle', lambda action, service, **kwargs: forwarded.append((action, service, kwargs)), raising=False)
    ownership.run_compose(['start', 'postgres'], check=True)
    assert forwarded == [('start', 'postgres', {'check': True})]
    assert effects == []  # No controller-owned late Docker start can escape cleanup.


def test_simulator_uses_only_precreated_guardian_owned_identity(owned_stack, monkeypatch):
    ownership, _, _, _, effects, _ = owned_stack
    forwarded=[]
    monkeypatch.setattr(ownership, '_guardian_lifecycle', lambda action, service, **kwargs: forwarded.append((action, service, kwargs)), raising=False)
    ownership.run_compose(['--profile', 'simulation', 'run', '--rm', 'simulator'], capture_output=True, text=True, timeout=30)
    assert forwarded == [('start', 'simulator', {'capture_output': True, 'text': True, 'timeout': 30})]
    assert effects == []  # Compose run would create a new, unreserved identity.


def test_recreated_even_locally_owned_container_requires_new_qualification(owned_stack):
    ownership, containers, _, _, effects, _ = owned_stack
    ownership.assert_owned_stack()
    containers[0]['Id'] = 'f' * 64
    with pytest.raises(ownership.IsolationError):
        ownership.run_compose(['restart', 'mqtt'], check=True)
    assert effects == []


def test_http_auth_revalidates_before_each_account_write(owned_stack):
    ownership, containers, _, _, effects, network = owned_stack
    ownership.assert_owned_stack()
    containers[0]['Config']['Labels']['com.docker.compose.project.working_dir'] = '/foreign/checkout'
    # Exercise actual request implementation even though other tests replace it
    # to prove the higher-level caller never enters auth handling.
    from importlib import reload
    reload(browser_auth)
    with pytest.raises(ownership.IsolationError):
        browser_auth.request('/auth', {'username': 'fixture', 'password': 'fixture'})
    assert effects == []
    network.assert_not_called()


def test_existing_mqtt_publisher_revalidates_before_next_uplink(owned_stack, monkeypatch):
    ownership, containers, _, _, effects, _ = owned_stack
    client = Mock()
    publish_effect = client.publish
    factory = Mock(return_value=client)
    monkeypatch.setattr('services.lorawan.runtime.mqtt_client', factory)
    publisher = ownership.guarded_mqtt_client({'environment': 'simulation', 'mqtt_host': '127.0.0.1', 'mqtt_port': 18884}, 'fixture')
    containers[0]['Config']['Labels']['com.docker.compose.project.working_dir'] = '/foreign/checkout'
    with pytest.raises(ownership.IsolationError):
        publisher.publish('fixture/topic', b'fixture')
    publish_effect.assert_not_called()
    assert effects == []


def test_simulator_refuses_foreign_config_before_container_creation(owned_stack):
    ownership, _, rendered, _, effects, network = owned_stack
    rendered['services']['simulator']['volumes'][0]['source'] = '/foreign/simulator.json'
    with pytest.raises(ownership.IsolationError):
        ownership.run_compose(['--profile', 'simulation', 'run', '--rm', 'simulator'], check=True)
    assert effects == []
    network.assert_not_called()


def test_mqtt_connect_refuses_replacement_after_client_construction(owned_stack, monkeypatch):
    ownership, containers, _, _, effects, _ = owned_stack
    client = Mock()
    connect_effect = client.connect
    monkeypatch.setattr('services.lorawan.runtime.mqtt_client', Mock(return_value=client))
    publisher = ownership.guarded_mqtt_client({'environment': 'simulation', 'mqtt_host': '127.0.0.1', 'mqtt_port': 18884}, 'fixture')
    containers[0]['Id'] = 'f' * 64
    with pytest.raises(ownership.IsolationError):
        publisher.connect('127.0.0.1', 18884, 30)
    connect_effect.assert_not_called()
    assert effects == []


@pytest.mark.parametrize('field,value',[('Memory',0),('MemorySwap',-1),('NanoCpus',0),('PidsLimit',129),('RestartPolicy',{'Name':'always','MaximumRetryCount':0})])
def test_inspected_resource_drift_refused_before_lifecycle(owned_stack,field,value):
    ownership,containers,_,_,effects,_=owned_stack
    containers[0]['HostConfig'][field]=value
    with pytest.raises(ownership.IsolationError):ownership.run_compose(['start','mqtt'],check=True)
    assert effects==[]

@pytest.mark.parametrize('field,value',[('mem_limit',0),('memswap_limit',-1),('cpus',8),('pids_limit',129),('restart','always')])
def test_rendered_resource_drift_refused_before_lifecycle(owned_stack,field,value):
    ownership,_,rendered,_,effects,_=owned_stack
    rendered['services']['simulator'][field]=value
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]


def test_inspected_extra_network_refused(owned_stack):
    ownership,containers,_,_,effects,_=owned_stack
    containers[0]['NetworkSettings']['Networks']['earthship-sensors_default']={}
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]


def test_container_image_id_must_match_pinned_cached_image(owned_stack,monkeypatch):
    ownership,_,_,_,effects,_=owned_stack
    original=ownership._inspect
    monkeypatch.setattr(ownership,'_inspect',lambda args: json.dumps([{'Id':'sha256:'+'f'*64}]) if args[:2]==['image','inspect'] else original(args))
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]


def test_stopped_foreign_volume_consumer_blocks_fixture_use(owned_stack,monkeypatch):
    ownership,containers,_,_,effects,_=owned_stack
    foreign={'Id':'f'*64,'State':{'Running':False},'Mounts':[{'Type':'volume','Name':'earthship-sensors-test_database'}]}
    original=ownership._inspect
    def inspect(args):
        if args==['ps','--all','--quiet','--no-trunc']:return '\n'.join([c['Id'] for c in containers]+[foreign['Id']])
        if args[0]=='inspect' and foreign['Id'] in args:return json.dumps(containers+[foreign])
        return original(args)
    monkeypatch.setattr(ownership,'_inspect',inspect)
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]


def test_fixture_nonce_must_bind_all_container_lifecycles(owned_stack, monkeypatch):
    ownership, containers, _, _, effects, _ = owned_stack
    monkeypatch.setenv('SENSOR_QUALIFICATION_NONCE', 'a' * 32)
    for container in containers:
        container['Config']['Labels']['org.earthship.sensor.qualification'] = 'f' * 32
    with pytest.raises(ownership.IsolationError):
        ownership.assert_owned_stack()
    assert effects == []


def test_stopped_mqtt_retains_fixed_binding_before_guarded_recovery(owned_stack, monkeypatch):
    ownership, containers, _, _, effects, _ = owned_stack
    mqtt=containers[0]
    mqtt['HostConfig']['PortBindings']={'1883/tcp':[{'HostIp':'127.0.0.1','HostPort':'18884'}]}
    mqtt['State']['Running']=False
    mqtt['NetworkSettings']['Ports']={}
    requests=[]
    monkeypatch.setattr(ownership,'_guardian_lifecycle',lambda *args,**kwargs:requests.append(args),raising=False)
    ownership.run_compose(['start','mqtt'])
    assert requests==[('start','mqtt')] and effects==[]


@pytest.mark.parametrize('value,expected',[(1,1),('1',1),(67108864,67108864),('67108864',67108864),
    (9223372036854775807,9223372036854775807),('9223372036854775807',9223372036854775807)])
def test_rendered_memory_accepts_only_bounded_integer_or_canonical_decimal(value,expected):
    from services.lorawan.tests.stack_ownership import rendered_memory_bytes
    assert rendered_memory_bytes(value)==expected


@pytest.mark.parametrize('value',[None,True,False,0,-1,1.0,67108864.0,'','0','00','01','067108864',
    '+67108864','-67108864',' 67108864','67108864 ','67108864\n','64m','6.7108864e7','67108864.0',
    '６７１０８８６４',9223372036854775808,'9223372036854775808','9'*1000,[],{}])
def test_rendered_memory_rejects_ambiguous_or_unbounded_values(value):
    from services.lorawan.tests.stack_ownership import rendered_memory_bytes
    assert rendered_memory_bytes(value) is None


@pytest.mark.parametrize('representation',[int,str])
def test_owned_boundary_accepts_rendered_memory_formats(owned_stack,representation):
    ownership,_,rendered,_,effects,network=owned_stack
    for spec in rendered['services'].values():
        for key in ('mem_limit','memswap_limit'):spec[key]=representation(spec[key])
    assert len(ownership.assert_owned_stack())==6
    assert effects==[];network.assert_not_called()


@pytest.mark.parametrize('field',['mem_limit','memswap_limit'])
@pytest.mark.parametrize('value',['067108864',67108864.0,True,'67108865','9223372036854775808'])
def test_owned_boundary_rejects_ambiguous_rendered_memory(owned_stack,field,value):
    ownership,_,rendered,_,effects,_=owned_stack
    rendered['services']['mqtt'][field]=value
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]


@pytest.mark.parametrize('field',['Memory','MemorySwap'])
def test_owned_boundary_does_not_normalize_actual_docker_caps(owned_stack,field):
    ownership,containers,_,_,effects,_=owned_stack
    containers[0]['HostConfig'][field]='67108864'
    with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]


@pytest.mark.parametrize('rendered_memory,rendered_swap,inspected_memory,inspected_swap,accepted',[
    (1152,1152,1152,1152,True),
    (1536,1536,1536,1536,False),
    (1536,1536,1152,1152,False),
    (1152,1152,1536,1536,False),
    (1152,1536,1152,1152,False),
    (1152,1152,1152,1536,False),
])
def test_openhab_memory_profile_requires_matching_1152_mib_without_swap(
        owned_stack,rendered_memory,rendered_swap,inspected_memory,inspected_swap,accepted):
    ownership,containers,rendered,_,effects,network=owned_stack
    spec=rendered['services']['openhab']
    spec['mem_limit']=str(rendered_memory*1024**2)
    spec['memswap_limit']=str(rendered_swap*1024**2)
    container=next(c for c in containers if c['Config']['Labels']['com.docker.compose.service']=='openhab')
    container['HostConfig']['Memory']=inspected_memory*1024**2
    container['HostConfig']['MemorySwap']=inspected_swap*1024**2
    if accepted:
        assert ownership.assert_owned_stack()['openhab']==container['Id']
    else:
        with pytest.raises(ownership.IsolationError):ownership.assert_owned_stack()
    assert effects==[]
    network.assert_not_called()
