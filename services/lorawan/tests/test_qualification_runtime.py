"""Closed Docker/manifest boundary with an in-memory daemon, never real Docker."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import pytest
from services.lorawan.tests import qualification_runtime as runtime
from services.lorawan.tests.qualification_guard import Refused


@pytest.fixture
def manifest(tmp_path):
    root=tmp_path/'checkout';(root/'deploy/lorawan').mkdir(parents=True)
    compose=root/'deploy/lorawan/compose.test.yaml';compose.write_text('approved fixture source\n')
    rendered=json.loads((Path(__file__).with_name('fixtures')/'compose.test.rendered.json').read_text().replace('@WORKTREE@',str(root)))
    containers={};images={};nonce='a'*32
    # Independent caps, identities and rendered baseline.
    caps={'mqtt':(64,250000000,8),'postgres':(256,1000000000,20),'ingest':(192,500000000,8),
          'openhab':(1152,2000000000,144),'redis':(64,250000000,8),'chirpstack':(192,1000000000,8),'simulator':(128,500000000,8)}
    for i,(service,(memory,cpu,pids)) in enumerate(caps.items(),1):
        spec=rendered['services'][service];identity=f'{i:064x}';images[spec['image']]='sha256:'+('2a8053a90d76dcdd13696f6c21ab58ad2555f59dec266cda7ba77ec80a3dd19a' if service in ('ingest','simulator') else identity)
        mounts=[]
        for volume in spec.get('volumes',[]):
            mount={'Type':volume['type'],'Destination':volume['target'],'RW':not volume.get('read_only',False)}
            if volume['type']=='bind':mount['Source']=volume['source']
            else:mount['Name']=rendered['volumes'][volume['source']]['name']
            mounts.append(mount)
        ports={str(p['target'])+'/tcp':[{'HostIp':p['host_ip'],'HostPort':str(p['published'])}] for p in spec.get('ports',[])}
        containers[service]={'Id':identity,'Name':'/earthship-sensors-test-'+service+'-1','Image':images[spec['image']],
            'Config':{'Image':spec['image'],'Labels':{'com.docker.compose.project':'earthship-sensors-test','com.docker.compose.service':service,
                'com.docker.compose.project.working_dir':str(compose.parent),'com.docker.compose.project.config_files':str(compose),
                'org.earthship.sensor.qualification':nonce}},'HostConfig':{'Memory':memory*1024**2,'MemorySwap':memory*1024**2,'NanoCpus':cpu,
                'PidsLimit':pids,'RestartPolicy':{'Name':'no','MaximumRetryCount':0},'PortBindings':ports,'Privileged':False,'AutoRemove':False,'OomKillDisable':False},
            'Mounts':mounts,'NetworkSettings':{'Ports':ports,'Networks':{rendered['networks'][n]['name']:{'NetworkID':('b' if n=='sensors' else 'c')*64} for n in spec['networks']}},
            'State':{'Running':False,'Pid':0}}
    return {'schema':'earthship-sensor-qualification/v1','nonce':nonce,'root':str(root),'compose_sha256':sha256(compose.read_bytes()).hexdigest(),
        'rendered':rendered,'containers':containers,'images':images,
        'networks':{'earthship-sensors-test_sensors':'b'*64,'earthship-sensors-test_management':'c'*64},
        'volumes':{name:dict(Name=name,Driver='local',Options=None,Labels={'com.docker.compose.project':'earthship-sensors-test','com.docker.compose.volume':name.removeprefix('earthship-sensors-test_')}) for name in ['earthship-sensors-test_database','earthship-sensors-test_openhab_data','earthship-sensors-test_redis_data']}}


class Daemon:
    def __init__(self,manifest):
        self.manifest=manifest;self.containers={c['Id']:deepcopy(c) for c in manifest['containers'].values()};self.calls=[]
    def __call__(self,method,path):
        self.calls.append((method,path));parts=path.split('/')
        if path=='/containers/json?all=1':return list(self.containers.values())
        if parts[1]=='containers':
            identity=parts[2].split('?',1)[0]
            if path.endswith('/json'):return self.containers.get(identity)
            if method=='DELETE':self.containers.pop(identity,None);return None
            if method=='POST':return None
        if parts[1]=='networks':
            name=parts[2];return {'Id':self.manifest['networks'][name],'Name':name,'Driver':'bridge','Internal':name.endswith('_sensors'),
                                'Labels':{'com.docker.compose.project':'earthship-sensors-test'}}
        if parts[1]=='volumes':return self.manifest['volumes'][parts[2]]
        raise AssertionError((method,path))


def backend(manifest,mode='qualification'):
    daemon=Daemon(manifest)
    return runtime.DockerBackend(manifest,request=daemon,cgroup_empty=lambda identity:True,mode=mode),daemon


def test_seven_stopped_id_manifest_validates_without_mutation(manifest):
    value,daemon=backend(manifest)
    value.validate({name:c['Id'] for name,c in manifest['containers'].items()})
    assert all(method=='GET' for method,_ in daemon.calls)


@pytest.mark.parametrize('mutation',[
    lambda c:c['Config']['Labels'].__setitem__('com.docker.compose.project','earthship-sensors'),
    lambda c:c['Config']['Labels'].__setitem__('org.earthship.sensor.qualification','f'*32),
    lambda c:c['HostConfig'].__setitem__('MemorySwap',-1),
    lambda c:c['HostConfig'].__setitem__('PidsLimit',129),
    lambda c:c['HostConfig'].__setitem__('NanoCpus',0),
    lambda c:c['HostConfig'].__setitem__('Privileged',True),
    lambda c:c['Mounts'][0].__setitem__('Source','/production/private'),
    lambda c:c.__setitem__('Image','sha256:'+'f'*64),
    lambda c:c['NetworkSettings']['Networks'].__setitem__('production',{'NetworkID':'e'*64}),
])
def test_unsafe_initial_manifest_cannot_authorize_cleanup_or_start(manifest,mutation):
    mutation(manifest['containers']['mqtt'])
    with pytest.raises(Refused):backend(manifest)


def test_changed_container_after_pin_cannot_be_mutated(manifest):
    value,daemon=backend(manifest);identity=manifest['containers']['mqtt']['Id']
    daemon.containers[identity]['Config']['Labels']['org.earthship.sensor.qualification']='f'*32
    with pytest.raises(Refused):value.action('start',identity)
    assert all(method=='GET' for method,_ in daemon.calls)


def test_only_fixed_ids_and_lifecycle_verbs_reach_daemon(manifest):
    value,daemon=backend(manifest)
    for action,identity in [('start','f'*64),('exec',manifest['containers']['mqtt']['Id'])]:
        with pytest.raises(Refused):value.action(action,identity)
    assert daemon.calls==[]


def test_partial_cleanup_recovery_does_not_recreate_removed_id(manifest):
    value,daemon=backend(manifest);ids={name:c['Id'] for name,c in manifest['containers'].items()}
    daemon.containers.pop(ids['mqtt']);value.validate(ids,cleanup=True)
    value.action('remove',ids['mqtt'])
    assert all(method!='POST' for method,_ in daemon.calls)
    assert value.absent(ids) is False
    for identity in ids.values():value.action('remove',identity)
    assert value.absent(ids) is True


def test_stopped_foreign_volume_consumer_and_cgroup_residue_keep_exclusion(manifest):
    value,daemon=backend(manifest);ids={name:c['Id'] for name,c in manifest['containers'].items()}
    foreign=deepcopy(manifest['containers']['postgres']);foreign['Id']='f'*64;daemon.containers[foreign['Id']]=foreign
    with pytest.raises(Refused):value.validate(ids,cleanup=True)
    assert all(method=='GET' for method,_ in daemon.calls)
    daemon.containers.clear();value.cgroup_empty=lambda _:False
    assert value.absent(ids) is False


def test_compose_drift_blocks_even_owned_lifecycle(manifest):
    value,daemon=backend(manifest)
    (Path(manifest['root'])/'deploy/lorawan/compose.test.yaml').write_text('changed')
    with pytest.raises(Refused):value.action('start',manifest['containers']['mqtt']['Id'])
    assert all(method=='GET' for method,_ in daemon.calls)



def test_state_machine_recovers_a_partially_removed_real_adapter_inventory(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    value,daemon=backend(manifest);events=[];ids=value.ids
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=value,quiesce=lambda:events.append('quiesce'),release=lambda:events.append('release'))
    state.register(ids);daemon.containers.pop(ids['mqtt'])
    state.cleanup()
    assert events==['quiesce','release'] and not daemon.containers


@pytest.fixture
def unix_directory():
    import tempfile
    # AF_UNIX paths are bounded to108bytes; own short ext4 directory, not tmpfs.
    with tempfile.TemporaryDirectory(prefix='.es-sock-',dir='/home/sat') as name:
        yield Path(name)


@pytest.mark.parametrize('status,body,expected',[(200,b'{"ok":true}',{'ok':True}),(204,b'',None),(404,b'{"message":"missing"}',None),(503,b'{"private":"never report"}',Refused),(200,b'{"bad":NaN}',Refused)])
def test_docker_socket_uses_owned_unix_transport_and_sanitizes_protocol(unix_directory,status,body,expected):
    import os,socket,threading
    path=unix_directory/'docker.sock';server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(path));path.chmod(0o600);server.listen(1)
    requests=[]
    def reply():
        connection,_=server.accept()
        with connection:
            requests.append(connection.recv(8192))
            connection.sendall(f'HTTP/1.1 {status} reply\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)
    worker=threading.Thread(target=reply,daemon=True);worker.start()
    try:
        transport=runtime.DockerSocket(path,owner=os.getuid())
        if expected is Refused:
            with pytest.raises(Refused,match='Docker protocol refused'):transport('GET','/containers/'+'a'*64+'/json')
        else:assert transport('GET','/containers/'+'a'*64+'/json')==expected
        worker.join(2);assert not worker.is_alive()
        assert requests[0].startswith(b'GET /containers/'+b'a'*64+b'/json HTTP/1.1\r\n')
    finally:server.close()


def test_notify_barrier_passes_same_fd_and_waits_for_receiver_close(unix_directory):
    import array,fcntl,os,socket,threading
    path=unix_directory/'notify';server=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);server.bind(str(path))
    received=[]
    lock=unix_directory/'lock';fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX)
    def receiver():
        for _ in range(2):
            raw,anc,flags,_=server.recvmsg(8192,socket.CMSG_SPACE(4));fds=array.array('i');fds.frombytes(anc[0][2]);received.append(raw)
            if raw==b'BARRIER=1':os.close(fds[0])
            else:
                assert 'FLOCK' in Path(f'/proc/self/fdinfo/{fds[0]}').read_text()
                os.close(fds[0])
    thread=threading.Thread(target=receiver,daemon=True);thread.start()
    try:
        notifier=runtime.SystemdNotify(str(path));notifier('FDSTORE=1\nFDNAME=admission\nFDPOLL=0',fd);notifier.barrier()
        thread.join(2);assert not thread.is_alive();assert received==[b'FDSTORE=1\nFDNAME=admission\nFDPOLL=0',b'BARRIER=1']
    finally:os.close(fd);server.close()


@pytest.fixture
def controller_files(tmp_path):
    proc=tmp_path/'proc';cg=tmp_path/'cgroup';relative='/user.slice/user-1000.slice/user@1000.service/earthship.slice/earthship-work.slice/earthship-job-'+('a'*32)+'.scope'
    scope=cg/relative.lstrip('/');scope.mkdir(parents=True);(scope/'cgroup.events').write_text('populated 1\nfrozen 0\n');(scope/'cgroup.procs').write_text('123\n')
    process=proc/'123';process.mkdir(parents=True);(process/'stat').write_text('123 (controller) '+' '.join(['S']+['0']*18+['999']))
    (process/'status').write_text('Uid:\t1000\t1000\t1000\t1000\n');(process/'cgroup').write_text('0::'+relative+'\n')
    record={'pid':123,'starttime':999,'uid':1000,'cgroup':relative,'dev':scope.stat().st_dev,'ino':scope.stat().st_ino,
            'unit':scope.name,'invocation':'b'*32,'guardian_unit':'earthship-sensor-guard-'+('c'*32)+'.service'}
    return record,proc,cg,scope


def test_controller_identity_and_empty_scope_allow_cleanup(controller_files):
    record,proc,cg,scope=controller_files
    value=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    assert value.alive()
    (proc/'123/stat').unlink();(scope/'cgroup.procs').write_text('');(scope/'cgroup.events').write_text('populated 0\nfrozen 0\n')
    assert not value.alive();value.quiesce()
    assert not (scope/'cgroup.kill').exists()


@pytest.mark.parametrize('change',['inode','moved','foreign_member','root_foreign'])
def test_ambiguous_scope_ownership_refuses_before_kill(controller_files,change):
    record,proc,cg,scope=controller_files;value=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    if change=='inode':record['ino']+=1;value=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    if change=='moved':(proc/'123/cgroup').write_text('0::/foreign.scope\n')
    if change=='foreign_member':(proc/'123/status').write_text('Uid:\t1001\t1001\t1001\t1001\n')
    if change=='root_foreign':
        (proc/'123/status').write_text('Uid:\t0\t0\t0\t0\n');(proc/'123/cmdline').write_bytes(b'/usr/bin/foreign\0')
    with pytest.raises(Refused):value.quiesce()
    assert not (scope/'cgroup.kill').exists()


def test_exact_scope_kill_must_be_followed_by_population_zero(controller_files,monkeypatch):
    record,proc,cg,scope=controller_files;value=runtime.Controller(record,proc_root=proc,cgroup_root=cg);calls=[]
    def kill(directory):
        assert directory==scope;calls.append(directory)
        (scope/'cgroup.events').write_text('populated 0\nfrozen 0\n');(scope/'cgroup.procs').write_text('')
    monkeypatch.setattr(value,'kill',kill);value.quiesce()
    assert calls==[scope]


def test_owned_root_launcher_client_remains_inside_scope_cleanup(controller_files,monkeypatch):
    record,proc,cg,scope=controller_files;process=proc/'456';process.mkdir()
    (process/'status').write_text('Uid:\t0\t0\t0\t0\n');(process/'cgroup').write_text('0::'+record['cgroup']+'\n')
    (process/'cmdline').write_bytes(('/usr/bin/systemd-run\0--system\0--pipe\0--unit='+record['guardian_unit']+'\0').encode())
    (scope/'cgroup.procs').write_text('123\n456\n');value=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    def kill(directory):(scope/'cgroup.events').write_text('populated 0\nfrozen 0\n')
    monkeypatch.setattr(value,'kill',kill);value.quiesce()


def test_control_protocol_is_closed_and_requires_original_live_scope_peer(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    value,daemon=backend(manifest)
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=value,quiesce=lambda:None,release=lambda:None);state.register(value.ids)
    class Controller:
        record={'pid':123,'uid':1000}
        def alive(self):return True
        def process(self,pid):
            if pid not in (123,124):raise Refused('foreign scope')
            return 1000
    actor=Controller();checks=[]
    handler=runtime.RequestHandler(state,controller=actor,manifest_digest='a'*64,lease_check=lambda:checks.append(True))
    assert handler.request({'operation':'hello','manifest_sha256':'a'*64},(123,1000,1000))=={'ready':True}
    bad=[({'operation':'exec','manifest_sha256':'a'*64},(123,1000,1000)),
         ({'operation':'hello','manifest_sha256':'b'*64},(123,1000,1000)),
         ({'operation':'hello','manifest_sha256':'a'*64},(123,0,0)),
         ({'operation':'hello','manifest_sha256':'a'*64},(124,1000,1000)),
         ({'operation':'lifecycle','manifest_sha256':'a'*64,'action':'start','service':'mqtt'},(999,1000,1000))]
    daemon.calls.clear()
    for payload,peer in bad:
        with pytest.raises(Refused):handler.request(payload,peer)
    assert not daemon.calls
    answer=handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':'start','service':'mqtt'},(124,1000,1000))
    assert answer=={'returncode':0,'stdout':'','stderr':''}
    assert ('POST','/containers/'+value.ids['mqtt']+'/start') in daemon.calls
    actor.alive=lambda:False;daemon.calls.clear()
    with pytest.raises(Refused):handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':'start','service':'mqtt'},(124,1000,1000))
    assert not daemon.calls


def test_lease_verification_failure_prevents_lifecycle(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    value,daemon=backend(manifest);state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=value,quiesce=lambda:None,release=lambda:None);state.register(value.ids)
    class Controller:
        record={'pid':123,'uid':1000}
        def alive(self):return True
        def process(self,pid):return 1000
    def changed():raise Refused('source or lock changed')
    handler=runtime.RequestHandler(state,controller=Controller(),manifest_digest='a'*64,lease_check=changed);daemon.calls.clear()
    with pytest.raises(Refused):handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':'start','service':'mqtt'},(123,1000,1000))
    assert not daemon.calls


def lease_fixture(manifest,tmp_path):
    import os
    source=tmp_path/'source';source.mkdir();files={}
    for name in ('qualification_guard.py','qualification_runtime.py','stack_ownership.py'):
        path=source/name;path.write_text('# frozen helper\n');path.chmod(0o400);files[name]=sha256(path.read_bytes()).hexdigest()
    envelope={'schema':'earthship-sensor-admission/v1','mode':'qualification','late_request_proof':False,'stack':manifest,'controller':{},'lock':{},'source_root':str(source),
              'sources':files,'boot_id':'fixture-boot','deadline':200.}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(envelope));path.chmod(0o600)
    return path,sha256(path.read_bytes()).hexdigest(),envelope


def test_lease_binds_manifest_source_root_boot_and_original_deadline(manifest,tmp_path):
    path,digest,envelope=lease_fixture(manifest,tmp_path)
    lease=runtime.Lease(path,digest,root=Path(manifest['root']),nonce=manifest['nonce'],boot_id='fixture-boot',clock=lambda:100.)
    assert lease.verify()==envelope
    (Path(envelope['source_root'])/'qualification_guard.py').chmod(0o600)
    (Path(envelope['source_root'])/'qualification_guard.py').write_text('different bytes')
    with pytest.raises(Refused):lease.verify()


@pytest.mark.parametrize('change',['manifest','deadline','boot','root','nonce','writable_source','symlink_source'])
def test_lease_changes_refuse_before_docker_or_service_effects(manifest,tmp_path,change):
    path,digest,envelope=lease_fixture(manifest,tmp_path)
    kwargs={'root':Path(manifest['root']),'nonce':manifest['nonce'],'boot_id':'fixture-boot','clock':lambda:100.}
    if change=='manifest':path.write_text(path.read_text()+' ')
    if change=='deadline':kwargs['clock']=lambda:200.
    if change=='boot':kwargs['boot_id']='other-boot'
    if change=='root':kwargs['root']=tmp_path
    if change=='nonce':kwargs['nonce']='b'*32
    source=Path(envelope['source_root'])/'qualification_guard.py'
    if change=='writable_source':source.chmod(0o622)
    if change=='symlink_source':target=source.with_suffix('.old');source.rename(target);source.symlink_to(target)
    with pytest.raises(Refused):runtime.Lease(path,digest,**kwargs).verify()


@pytest.mark.parametrize('change',[None,'wrong_group','memory','swap','cpu','pids'])
def test_guardian_service_context_enforces_own_system_manager_caps(tmp_path,change,monkeypatch):
    import subprocess
    def output(argv,**kwargs):
        assert argv==['/usr/bin/systemctl','show','--value','-p','TasksMax',unit]
        return '16\n'
    monkeypatch.setattr(subprocess,'check_output',output)
    proc=tmp_path/'proc';(proc/'self').mkdir(parents=True);cg=tmp_path/'cg';unit='earthship-sensor-guard-'+('a'*32)+'.service'
    path=cg/'system.slice'/unit;path.mkdir(parents=True)
    (proc/'self/cgroup').write_text('0::/system.slice/'+unit+'\n')
    for name,value in [('memory.max',str(64*1024**2)),('memory.swap.max','0'),('pids.max','16'),('cpu.max','50000 100000')]:
        (path/name).write_text(value)
    if change=='wrong_group':(proc/'self/cgroup').write_text('0::/user.slice/'+unit+'\n')
    replacements={'memory':('memory.max','max'),'swap':('memory.swap.max','1'),'cpu':('cpu.max','max 100000'),'pids':('pids.max','128')}
    if change in replacements:
        name,value=replacements[change];(path/name).write_text(value)
    if change:
        with pytest.raises(Refused):runtime.check_service_context(unit,proc_root=proc,cgroup_root=cg)
    else:assert runtime.check_service_context(unit,proc_root=proc,cgroup_root=cg)==path


def test_lifecycle_proof_mode_cannot_start_any_non_mqtt_fixture(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    value,daemon=backend(manifest,mode='lifecycle-proof')
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=value,quiesce=lambda:None,release=lambda:None)
    state.register(value.ids)
    class Actor:
        record={'uid':1000,'pid':123}
        def alive(self):return True
        def process(self,pid):return 1000
    handler=runtime.RequestHandler(state,controller=Actor(),manifest_digest='a'*64,lease_check=lambda:None,mode='lifecycle-proof')
    for service in ['postgres','ingest','openhab','redis','chirpstack','simulator']:
        for action in ['start','restart']:
            with pytest.raises(Refused):handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':action,'service':service},(123,1000,1000))
    assert not any(method!='GET' for method,path in daemon.calls)
    result=handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':'start','service':'mqtt'},(123,1000,1000))
    assert result['returncode']==0
    assert ('POST','/containers/'+value.ids['mqtt']+'/start') in daemon.calls
    with pytest.raises(Refused):runtime.RequestHandler(state,controller=Actor(),manifest_digest='a'*64,lease_check=lambda:None,mode='anything')


def test_seven_container_manifest_can_hold_bounded_docker_environment_metadata(manifest,tmp_path):
    path,digest,envelope=lease_fixture(manifest,tmp_path)
    envelope['stack']['containers']['mqtt']['Config']['Env']=['FIXTURE_METADATA='+('x'*70000)]
    path.write_text(json.dumps(envelope));digest=sha256(path.read_bytes()).hexdigest()
    assert runtime.Lease(path,digest,root=Path(manifest['root']),nonce=manifest['nonce'],boot_id='fixture-boot',clock=lambda:100.).verify()==envelope


@pytest.mark.parametrize('changed',[None,'memory.swap.max','pids.max','cpu.max','pid'])
def test_actual_container_cgroup_caps_are_required_before_lifecycle_ack(tmp_path,changed):
    identity='a'*64;relative='/system.slice/docker-'+identity+'.scope'
    cg=tmp_path/'cgroup';path=cg/relative.lstrip('/');path.mkdir(parents=True)
    proc=tmp_path/'proc';(proc/'123').mkdir(parents=True);(proc/'123/cgroup').write_text('0::'+relative+'\n')
    for name,value in [('memory.max','67108864'),('memory.swap.max','0'),('pids.max','8'),('cpu.max','25000 100000'),
        ('memory.current','1234'),('memory.peak','2345'),('pids.current','2'),('memory.events','max 0\noom 0\noom_kill 0\n'),('pids.events','max 0\n')]:
        (path/name).write_text(value)
    if changed=='pid':(proc/'123/cgroup').write_text('0::/production\n')
    elif changed:(path/changed).write_text('max' if changed!='cpu.max' else 'max 100000')
    container={'Id':identity,'State':{'Running':True,'Pid':123}}
    if changed:
        with pytest.raises(Refused):runtime.container_caps('mqtt',identity,container,cgroup_root=cg,proc_root=proc)
    else:
        result=runtime.container_caps('mqtt',identity,container,cgroup_root=cg,proc_root=proc)
        assert result['cgroup']==relative and result['memory.peak']=='2345' and result['pids.max']=='8'


@pytest.mark.parametrize('memory,swap,accepted',[
    ('1207959552','0',True),('1610612736','0',False),('1207959552','1',False),
])
def test_openhab_memory_profile_requires_exact_kernel_limit_without_swap(tmp_path,memory,swap,accepted):
    identity='a'*64;relative='/system.slice/docker-'+identity+'.scope'
    cg=tmp_path/'cgroup';path=cg/relative.lstrip('/');path.mkdir(parents=True)
    proc=tmp_path/'proc';(proc/'123').mkdir(parents=True);(proc/'123/cgroup').write_text('0::'+relative+'\n')
    for name,value in [('memory.max',memory),('memory.swap.max',swap),('pids.max','144'),('cpu.max','200000 100000'),
        ('memory.current','1234'),('memory.peak','2345'),('pids.current','2'),('memory.events','max 0\noom 0\noom_kill 0\n'),('pids.events','max 0\n')]:
        (path/name).write_text(value)
    container={'Id':identity,'State':{'Running':True,'Pid':123}}
    if accepted:
        result=runtime.container_caps('openhab',identity,container,cgroup_root=cg,proc_root=proc)
        assert result['memory.max']=='1207959552' and result['memory.swap.max']=='0'
        assert result['cgroup']==relative and result['pids.max']=='144'
    else:
        with pytest.raises(Refused):runtime.container_caps('openhab',identity,container,cgroup_root=cg,proc_root=proc)


def test_late_request_witness_runs_after_http_send_before_response(unix_directory):
    import os,socket,threading
    path=unix_directory/'late.sock';server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    server.bind(str(path));path.chmod(0o600);server.listen(1)
    received=threading.Event();release=threading.Event();events=[]
    def reply():
        connection,_=server.accept()
        with connection:
            raw=connection.recv(8192);events.append(raw.split(b'\r\n',1)[0]);received.set()
            if release.wait(2):connection.sendall(b'HTTP/1.1 204 done\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
    thread=threading.Thread(target=reply,daemon=True);thread.start()
    def witness(method,path):
        assert received.wait(2)
        events.append((method,path));release.set()
    try:
        transport=runtime.DockerSocket(path,owner=os.getuid(),after_request=witness)
        assert transport('POST','/containers/'+'a'*64+'/start') is None
        thread.join(2);assert not thread.is_alive()
        assert events==[b'POST /containers/'+b'a'*64+b'/start HTTP/1.1',('POST','/containers/'+'a'*64+'/start')]
    finally:release.set();server.close()


def test_replaced_volume_free_mqtt_identity_blocks_cleanup_release(manifest):
    value,daemon=backend(manifest)
    old=value.ids['mqtt'];replacement=deepcopy(daemon.containers.pop(old));replacement['Id']='f'*64
    daemon.containers[replacement['Id']]=replacement
    with pytest.raises(Refused):value.validate(value.ids,cleanup=True)
    assert all(method=='GET' for method,path in daemon.calls)


@pytest.mark.parametrize('request_fails',[False,True])
def test_completed_cleanup_exits_successfully_even_after_lost_reply(manifest,tmp_path,request_fails):
    from services.lorawan.tests.qualification_guard import GuardianState
    docker,daemon=backend(manifest);events=[]
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=docker,
        quiesce=lambda:events.append('quiesced'),release=lambda:events.append('released'))
    state.register(docker.ids)
    def operation():
        events.append('request')
        if request_fails:raise BrokenPipeError('private request data must not be persisted')
    failure=tmp_path/'request-failure.json'
    assert runtime.run_owned_session(operation,state,failure)==0
    assert events==['request','quiesced','released']
    assert not daemon.containers
    if request_fails:assert json.loads(failure.read_text())=={'request_failed':True}
    else:assert not failure.exists()


def test_failed_cleanup_preserves_restart_and_never_releases(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    docker,daemon=backend(manifest);events=[]
    def quiesce():raise Refused('controller has not quiesced')
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=docker,
        quiesce=quiesce,release=lambda:events.append('released'))
    state.register(docker.ids)
    def operation():raise BrokenPipeError()
    with pytest.raises(Refused,match='controller has not quiesced'):
        runtime.run_owned_session(operation,state,tmp_path/'request-failure.json')
    assert events==[] and len(daemon.containers)==7


def test_failure_receipt_error_cannot_prevent_cleanup_or_trigger_restart(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    docker,daemon=backend(manifest);events=[]
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=docker,
        quiesce=lambda:None,release=lambda:events.append('released'))
    state.register(docker.ids)
    def operation():raise BrokenPipeError()
    assert runtime.run_owned_session(operation,state,tmp_path/'missing'/'failure.json')==0
    assert events==['released'] and not daemon.containers


@pytest.mark.parametrize('representation',[int,str])
def test_backend_accepts_rendered_memory_formats(manifest,representation):
    for spec in manifest['rendered']['services'].values():
        for key in ('mem_limit','memswap_limit'):spec[key]=representation(spec[key])
    value,daemon=backend(manifest);value.validate(value.ids)
    assert all(method=='GET' for method,_ in daemon.calls)


@pytest.mark.parametrize('field',['mem_limit','memswap_limit'])
@pytest.mark.parametrize('value',['067108864',67108864.0,True,'67108865','9223372036854775808'])
def test_backend_rejects_ambiguous_rendered_memory(manifest,field,value):
    manifest['rendered']['services']['mqtt'][field]=value
    with pytest.raises(Refused):backend(manifest)


@pytest.mark.parametrize('field',['Memory','MemorySwap'])
def test_backend_does_not_normalize_actual_docker_caps(manifest,field):
    manifest['containers']['mqtt']['HostConfig'][field]='67108864'
    with pytest.raises(Refused):backend(manifest)


@pytest.mark.parametrize('before,after',[(False,None),(None,False)])
def test_default_oom_flag_alias_allows_post_start_validation_and_exact_cleanup(manifest,tmp_path,before,after):
    from services.lorawan.tests.qualification_guard import GuardianState
    manifest['containers']['mqtt']['HostConfig']['OomKillDisable']=before
    value,daemon=backend(manifest);events=[];identity=value.ids['mqtt']
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=value,
        quiesce=lambda:events.append('quiesced'),release=lambda:events.append('released'))
    state.register(value.ids);state.action('start','mqtt')
    daemon.containers[identity]['HostConfig']['OomKillDisable']=after
    daemon.containers[identity]['State'].update(Running=True,Pid=123)
    value.validate(value.ids)
    assert manifest['containers']['mqtt']['HostConfig']['OomKillDisable'] is before
    assert value.manifest['containers']['mqtt']['HostConfig']['OomKillDisable'] is before
    state.cleanup()
    assert events==['quiesced','released'] and not daemon.containers
    assert {path.split('/')[2].split('?')[0] for method,path in daemon.calls if method=='DELETE'}==set(value.ids.values())
    assert all(path.endswith('?force=1&v=0') for method,path in daemon.calls if method=='DELETE')


@pytest.mark.parametrize('flag',[True,0,1,'false','null',[],{}])
def test_invalid_initial_oom_flag_cannot_authorize_a_fixture(manifest,flag):
    manifest['containers']['mqtt']['HostConfig']['OomKillDisable']=flag
    with pytest.raises(Refused):backend(manifest)


@pytest.mark.parametrize('mutation',[
    lambda c:c['HostConfig'].__setitem__('OomKillDisable',True),
    lambda c:c['HostConfig'].__setitem__('OomKillDisable',0),
    lambda c:c['HostConfig'].__setitem__('OomKillDisable','false'),
    lambda c:c['HostConfig'].__setitem__('ReadonlyRootfs',True),
    lambda c:c['Config'].__setitem__('Env',['UNOWNED=1']),
    lambda c:c['Mounts'][0].__setitem__('RW',not c['Mounts'][0]['RW']),
    lambda c:c['HostConfig'].pop('OomKillDisable'),
])
def test_oom_alias_does_not_mask_other_identity_changes_during_cleanup(manifest,tmp_path,mutation):
    from services.lorawan.tests.qualification_guard import GuardianState
    value,daemon=backend(manifest);released=[]
    state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,docker=value,
        quiesce=lambda:None,release=lambda:released.append(True));state.register(value.ids)
    current=daemon.containers[value.ids['mqtt']];current['HostConfig']['OomKillDisable']=None;mutation(current)
    daemon.calls.clear()
    with pytest.raises(Refused):state.cleanup()
    assert not released and len(daemon.containers)==7 and all(method=='GET' for method,_ in daemon.calls)


@pytest.fixture
def recovered_session(manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    value,daemon=backend(manifest);events=[];stored=[True];receipt=tmp_path/'receipt.json'
    first=GuardianState(receipt,manifest_digest='a'*64,docker=value,quiesce=lambda:None,release=lambda:None)
    first.register(value.ids)
    def quiesce():events.append('quiesced')
    def release():events.append('released');stored[0]=False
    state=GuardianState(receipt,manifest_digest='a'*64,docker=value,quiesce=quiesce,release=release)
    class Notify:
        def __call__(self,message):events.append(message)
        def barrier(self):events.append('barrier')
    return state,daemon,events,stored,Notify()


def test_recovery_ready_is_acknowledged_before_cleanup_and_terminal_exit(recovered_session):
    state,daemon,events,stored,notifier=recovered_session
    daemon.calls.clear()
    assert runtime.recover_owned_session(state,notifier)==0
    assert events==['READY=1','barrier','quiesced','released'] and stored==[False]
    assert state.state['phase']=='terminal' and not daemon.containers
    assert all(method in ('GET','DELETE') for method,_ in daemon.calls)


def test_recovery_cleanup_failure_remains_nonzero_with_reservation_retained(recovered_session):
    state,daemon,events,stored,notifier=recovered_session
    def refuse():events.append('quiescence_refused');raise Refused('controller remains alive')
    state.quiesce=refuse
    with pytest.raises(Refused,match='controller remains alive'):runtime.recover_owned_session(state,notifier)
    assert events==['READY=1','barrier','quiescence_refused'] and stored==[True]
    assert len(daemon.containers)==7 and state.state['phase']=='cleanup'


@pytest.mark.parametrize('failure',['notify','barrier'])
def test_recovery_notify_failure_cannot_clean_or_release(recovered_session,failure):
    state,daemon,events,stored,_=recovered_session
    class Notify:
        def __call__(self,message):
            events.append(message)
            if failure=='notify':raise Refused('notify refused')
        def barrier(self):raise Refused('barrier refused')
    with pytest.raises(Refused):runtime.recover_owned_session(state,Notify())
    assert events==['READY=1'] and stored==[True] and len(daemon.containers)==7
    assert state.state['phase']=='armed'


def test_recovery_entrypoint_refuses_nonrecovered_state(recovered_session):
    state,daemon,events,stored,notifier=recovered_session;state.recovered=False
    with pytest.raises(Refused):runtime.recover_owned_session(state,notifier)
    assert events==[] and stored==[True] and len(daemon.containers)==7


@pytest.fixture
def sudo_monitor(controller_files):
    record,proc,cg,scope=controller_files;process=proc/'456';process.mkdir()
    (process/'status').write_text('Uid:\t1000\t0\t0\t0\n')
    (process/'cgroup').write_text('0::'+record['cgroup']+'\n')
    (process/'cmdline').write_bytes(('/usr/bin/sudo\0-n\0/usr/bin/systemd-run\0--system\0--pipe\0--unit='+record['guardian_unit']+'\0').encode())
    (scope/'cgroup.procs').write_text('123\n456\n')
    return record,proc,cg,scope,process


def test_exact_sudo_rs_monitor_is_root_classified_and_quiesced_with_original_scope(sudo_monitor,monkeypatch):
    record,proc,cg,scope,_=sudo_monitor;value=runtime.Controller(record,proc_root=proc,cgroup_root=cg);calls=[]
    assert value.alive() and value.process(456)==0
    def kill(directory):
        calls.append(directory);(scope/'cgroup.events').write_text('populated 0\nfrozen 0\n')
    monkeypatch.setattr(value,'kill',kill);value.quiesce()
    assert calls==[scope]


@pytest.mark.parametrize('uids',[(1001,0,0,0),(1000,1000,0,0),(1000,0,1000,0),(1000,0,0,1000),(0,1000,0,0)])
def test_other_mixed_credential_forms_refuse_before_scope_kill(sudo_monitor,uids):
    record,proc,cg,scope,process=sudo_monitor
    (process/'status').write_text('Uid:\t'+'\t'.join(map(str,uids))+'\n')
    with pytest.raises(Refused):runtime.Controller(record,proc_root=proc,cgroup_root=cg).quiesce()
    assert not (scope/'cgroup.kill').exists()


@pytest.mark.parametrize('change',['argv','command','unit','moved'])
def test_sudo_monitor_requires_exact_launch_identity_and_scope(sudo_monitor,change):
    record,proc,cg,scope,process=sudo_monitor
    if change=='argv':(process/'cmdline').write_bytes(('/usr/bin/systemd-run\0--unit='+record['guardian_unit']+'\0').encode())
    if change=='command':(process/'cmdline').write_bytes(('/usr/bin/sudo\0-n\0/usr/bin/foreign\0--system\0--pipe\0--unit='+record['guardian_unit']+'\0').encode())
    if change=='unit':(process/'cmdline').write_bytes(b'/usr/bin/sudo\0--unit=foreign.service\0')
    if change=='moved':(process/'cgroup').write_text('0::/foreign.scope\n')
    with pytest.raises(Refused):runtime.Controller(record,proc_root=proc,cgroup_root=cg).quiesce()
    assert not (scope/'cgroup.kill').exists()


def test_sudo_monitor_cannot_authenticate_as_main_or_rpc_peer(sudo_monitor,manifest,tmp_path):
    from services.lorawan.tests.qualification_guard import GuardianState
    record,proc,cg,scope,process=sudo_monitor;actor=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    value,daemon=backend(manifest);state=GuardianState(tmp_path/'receipt.json',manifest_digest='a'*64,
        docker=value,quiesce=lambda:None,release=lambda:None);state.register(value.ids)
    handler=runtime.RequestHandler(state,controller=actor,manifest_digest='a'*64,lease_check=lambda:None)
    daemon.calls.clear()
    with pytest.raises(Refused):handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':'start','service':'mqtt'},(456,1000,1000))
    assert daemon.calls==[]
    (proc/'123/status').write_text('Uid:\t1000\t0\t0\t0\n')
    (proc/'123/cmdline').write_bytes((process/'cmdline').read_bytes())
    with pytest.raises(Refused):actor.alive()


def test_reused_main_pid_cannot_authenticate_after_sudo_monitor_support(sudo_monitor):
    record,proc,cg,scope,_=sudo_monitor
    (proc/'123/stat').write_text('123 (replacement) '+' '.join(['S']+['0']*18+['1000']))
    assert runtime.Controller(record,proc_root=proc,cgroup_root=cg).alive() is False


@pytest.fixture
def guardian_mode_context(tmp_path,monkeypatch):
    import subprocess
    proc=tmp_path/'mode-proc';(proc/'self').mkdir(parents=True)
    cg=tmp_path/'mode-cg';unit='earthship-sensor-guard-'+('a'*32)+'.service'
    scope=cg/'system.slice'/unit;scope.mkdir(parents=True)
    (proc/'self/cgroup').write_text('0::/system.slice/'+unit+'\n')
    for name,value in [('memory.max','67108864'),('memory.swap.max','0'),('cpu.max','50000 100000')]:
        (scope/name).write_text(value)
    manager={'tasks':'8'};calls=[]
    def output(argv,**kwargs):
        calls.append(argv)
        if argv==['/usr/bin/systemctl','show','--value','-p','TasksMax',unit]:return manager['tasks']+'\n'
        assert argv==['/usr/bin/systemctl','show','--value','-p','CollectMode',unit]
        return 'inactive\n'
    monkeypatch.setattr(subprocess,'check_output',output)
    return proc,cg,unit,scope,manager,calls


@pytest.mark.parametrize('mode,tasks',[('qualification',8),('lifecycle-proof',16)])
def test_guardian_mode_context_requires_both_kernel_and_manager_caps(guardian_mode_context,mode,tasks):
    proc,cg,unit,scope,manager,calls=guardian_mode_context
    (scope/'pids.max').write_text(str(tasks));manager['tasks']=str(tasks)
    assert runtime.check_service_context(unit,mode=mode,proc_root=proc,cgroup_root=cg)==scope
    assert calls==[['/usr/bin/systemctl','show','--value','-p','TasksMax',unit]]


@pytest.mark.parametrize('mode,correct,wrong',[('qualification',8,16),('lifecycle-proof',16,8)])
@pytest.mark.parametrize('boundary',['kernel','manager'])
def test_guardian_wrong_mode_cap_refuses_before_fdstore(guardian_mode_context,monkeypatch,tmp_path,mode,correct,wrong,boundary):
    from services.lorawan.tests import qualification_guard as protocol
    proc,cg,unit,scope,manager,calls=guardian_mode_context
    (scope/'pids.max').write_text(str(wrong if boundary=='kernel' else correct))
    manager['tasks']=str(wrong if boundary=='manager' else correct)
    original=runtime.check_service_context
    monkeypatch.setattr(runtime,'check_service_context',lambda value,*,mode:original(value,mode=mode,proc_root=proc,cgroup_root=cg))
    effects=[]
    def inherited(_):effects.append('inherited');raise AssertionError('must refuse before descriptor custody')
    monkeypatch.setattr(protocol,'inherited_descriptor',inherited)
    with pytest.raises(Refused):runtime.service_main(['--mode',mode,'--manifest',str(tmp_path/'unused'),
        '--sha256','a'*64,'--root',str(tmp_path),'--nonce','a'*32])
    assert effects==[]


@pytest.mark.parametrize('mode',['other',8,16,None])
def test_guardian_context_refuses_unknown_or_numeric_mode(guardian_mode_context,mode):
    proc,cg,unit,scope,manager,calls=guardian_mode_context
    (scope/'pids.max').write_text('8')
    with pytest.raises(Refused):runtime.check_service_context(unit,mode=mode,proc_root=proc,cgroup_root=cg)
    assert calls==[]


@pytest.mark.parametrize('mode',['qualification','lifecycle-proof'])
def test_hashed_lease_binds_manifest_to_fixed_guardian_mode(manifest,tmp_path,mode):
    path,digest,envelope=lease_fixture(manifest,tmp_path)
    envelope['mode']=mode;path.write_text(json.dumps(envelope));digest=sha256(path.read_bytes()).hexdigest()
    lease=runtime.Lease(path,digest,root=Path(manifest['root']),nonce=manifest['nonce'],boot_id='fixture-boot',clock=lambda:100.)
    assert lease.verify_mode(mode)==envelope
    opposite='lifecycle-proof' if mode=='qualification' else 'qualification'
    with pytest.raises(Refused):lease.verify_mode(opposite,allow_expired=True)
    envelope['mode']=opposite;path.write_text(json.dumps(envelope))
    with pytest.raises(Refused):lease.verify_mode(opposite,allow_expired=True)  # Rewritten bytes cannot inherit the original hash.


@pytest.mark.parametrize('mode',['qualification','lifecycle-proof'])
@pytest.mark.parametrize('inherited',[None,117])
def test_service_manifest_mode_mismatch_retains_custody_before_effects_and_recovery(
        manifest,tmp_path,guardian_mode_context,monkeypatch,mode,inherited):
    import os,subprocess
    from types import SimpleNamespace
    from services.lorawan.tests import qualification_guard as protocol
    path,digest,envelope=lease_fixture(manifest,tmp_path)
    envelope['mode']='lifecycle-proof' if mode=='qualification' else 'qualification'
    path.write_text(json.dumps(envelope));digest=sha256(path.read_bytes()).hexdigest()
    proc,cg,unit,scope,manager,calls=guardian_mode_context
    tasks=8 if mode=='qualification' else 16
    (scope/'pids.max').write_text(str(tasks));manager['tasks']=str(tasks)
    real_context=runtime.check_service_context;events=[]
    def context(value,*,mode):
        events.append('context');return real_context(value,mode=mode,proc_root=proc,cgroup_root=cg)
    monkeypatch.setattr(runtime,'check_service_context',context)
    realpath=Path;directory=tmp_path/unit.removesuffix('.service');directory.mkdir(mode=0o700)
    boot=tmp_path/'boot';boot.write_text('fixture-boot')
    def mapped(value,*parts):
        value=realpath(value,*parts)
        if str(value)=='/run':return tmp_path
        if str(value)=='/proc/sys/kernel/random/boot_id':return boot
        return value
    monkeypatch.setattr(runtime,'Path',mapped)
    fd=0 if inherited is None else inherited;fstat=os.fstat
    monkeypatch.setattr(os,'fstat',lambda value:SimpleNamespace(st_dev=1,st_ino=2) if value==fd else fstat(value))
    monkeypatch.setattr(protocol,'inherited_descriptor',lambda _:inherited)
    monkeypatch.setattr(protocol,'verify_lock',lambda *a,**kw:events.append('lock'))
    class Notify:
        def __call__(self,*_):events.append('notify')
        def barrier(self):events.append('barrier')
    monkeypatch.setattr(runtime,'SystemdNotify',lambda _:Notify())
    class Store:
        def __init__(self,**_):pass
        def pin(self,value):events.append('pin')
        def release(self):events.append('release');raise AssertionError('forged mode cannot release custody')
    monkeypatch.setattr(protocol,'FdStore',Store)
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='1'))
    def forbidden(*a,**kw):events.append('effect');raise AssertionError('mode mismatch reached operational effects')
    monkeypatch.setattr(runtime,'DockerBackend',forbidden)
    monkeypatch.setattr(runtime,'Controller',forbidden)
    with pytest.raises(Refused,match='mode'):runtime.service_main(['--mode',mode,'--manifest',str(path),
        '--sha256',digest,'--root',manifest['root'],'--nonce',manifest['nonce']])
    assert events[0]=='context' and 'release' not in events and 'effect' not in events and 'notify' not in events
    assert ('pin' in events)==(inherited is None)
    if inherited is not None:assert 'barrier' in events  # Original recovered OFD remains held.


@pytest.mark.parametrize('mode',['qualification','lifecycle-proof'])
@pytest.mark.parametrize('failure',[None,'context','manifest'])
def test_recovery_rechecks_bound_mode_and_context_before_fdstore_release(
        manifest,tmp_path,guardian_mode_context,monkeypatch,mode,failure):
    import os,subprocess
    from types import SimpleNamespace
    from services.lorawan.tests import qualification_guard as protocol,stack_ownership
    path,digest,envelope=lease_fixture(manifest,tmp_path)
    envelope['mode']=mode;path.write_text(json.dumps(envelope));digest=sha256(path.read_bytes()).hexdigest()
    proc,cg,unit,scope,manager,calls=guardian_mode_context
    tasks=8 if mode=='qualification' else 16
    (scope/'pids.max').write_text(str(tasks));manager['tasks']=str(tasks)
    context=runtime.check_service_context;events=[]
    def checked(value,*,mode):
        events.append('context');return context(value,mode=mode,proc_root=proc,cgroup_root=cg)
    monkeypatch.setattr(runtime,'check_service_context',checked)
    realpath=Path;directory=tmp_path/unit.removesuffix('.service');directory.mkdir(mode=0o700)
    (directory/'receipt.json').write_text('{}')
    boot=tmp_path/'boot';boot.write_text('fixture-boot');source=realpath(envelope['source_root'])
    module_paths={runtime.__file__:'qualification_runtime.py',protocol.__file__:'qualification_guard.py',
                  stack_ownership.__file__:'stack_ownership.py'}
    def mapped(value,*parts):
        value=realpath(value,*parts)
        if str(value)=='/run':return tmp_path
        if str(value)=='/proc/sys/kernel/random/boot_id':return boot
        if str(value) in module_paths:return source/module_paths[str(value)]
        return value
    monkeypatch.setattr(runtime,'Path',mapped)
    fstat=os.fstat;monkeypatch.setattr(os,'fstat',lambda value:SimpleNamespace(st_dev=1,st_ino=2) if value==117 else fstat(value))
    envelope['lock'].update(path='/run/user/1000/earthship-job-admission.lock',dev=1,ino=2);path.write_text(json.dumps(envelope));digest=sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(protocol,'inherited_descriptor',lambda _:117)
    monkeypatch.setattr(protocol,'verify_lock',lambda *a,**kw:events.append('lock'))
    class Notify:
        def __call__(self,value):events.append(value)
        def barrier(self):events.append('barrier')
    monkeypatch.setattr(runtime,'SystemdNotify',lambda _:Notify())
    class Store:
        def __init__(self,**_):pass
        def pin(self,_):raise AssertionError('recovery cannot repin')
        def release(self):events.append('release')
    monkeypatch.setattr(protocol,'FdStore',Store)
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='1'))
    class Docker:
        def configuration(self):pass
    monkeypatch.setattr(runtime,'DockerBackend',lambda *a,**kw:Docker())
    monkeypatch.setattr(runtime,'Controller',lambda record:SimpleNamespace(record={'guardian_unit':unit},quiesce=lambda:None))
    class State:
        recovered=True
        def cleanup(self):
            events.append('cleanup')
            if failure=='context':manager['tasks']='16' if mode=='qualification' else '8'
            if failure=='manifest':
                envelope['mode']='lifecycle-proof' if mode=='qualification' else 'qualification'
                path.write_text(json.dumps(envelope))
            self.release()
    def state(*a,release,**kw):value=State();value.release=release;return value
    monkeypatch.setattr(protocol,'GuardianState',state)
    argv=['--mode',mode,'--manifest',str(path),'--sha256',digest,'--root',manifest['root'],'--nonce',manifest['nonce']]
    if failure:
        with pytest.raises(Refused):runtime.service_main(argv)
        assert 'release' not in events
    else:
        assert runtime.service_main(argv)==0 and events[-1]=='release'
    assert events.index('READY=1')<events.index('cleanup')
    assert events.count('context')==(1 if failure=='manifest' else 2)


@pytest.fixture
def phase_session(manifest,controller_files,tmp_path,monkeypatch):
    """Real journal, handler, controller and Docker adapter; external effects only are simulated."""
    from types import SimpleNamespace
    import subprocess
    from services.lorawan.tests import qualification_guard as guard
    from services.lorawan.tests import qualification_stack_controller as stack
    record,proc,cg,scope=controller_files;events=[];manager={'tasks':'32'}
    for name,value in [('memory.max','1073741824'),('memory.swap.max','0'),('pids.max','32'),
                       ('cpu.max','200000 100000'),('pids.current','2')]:
        (scope/name).write_text(value)
    for name,value in [('memory.max','6442450944'),('memory.swap.max','0'),('pids.max','256'),('cpu.max','800000 100000')]:
        (scope.parent/name).write_text(value)
    root=proc/'456';root.mkdir();(root/'status').write_text('Uid:\t0\t0\t0\t0\n')
    (root/'cgroup').write_text('0::'+record['cgroup']+'\n')
    (root/'cmdline').write_bytes(('/usr/bin/systemd-run\0--system\0--pipe\0--unit='+record['guardian_unit']+'\0').encode())
    (scope/'cgroup.procs').write_text('123\n456\n')
    def show(argv,**kwargs):
        assert argv==['/usr/bin/systemctl','--user','show','-p','InvocationID','-p','ControlGroup','-p','TasksMax',record['unit']]
        return 'InvocationID='+manager.get('invocation',record['invocation'])+'\nControlGroup='+manager.get('cgroup',record['cgroup'])+'\nTasksMax='+manager['tasks']+'\n'
    def set_property(argv,**kwargs):
        assert argv[:5]==['/usr/bin/systemctl','--user','set-property','--runtime',record['unit']]
        assert argv[5] in ('TasksMax=32','TasksMax=60') and len(argv)==6
        tasks=argv[5].split('=')[1];events.append('manager-'+tasks)
        manager['tasks']=tasks;(scope/'pids.max').write_text(tasks)
    monkeypatch.setattr(subprocess,'check_output',show);monkeypatch.setattr(subprocess,'run',set_property)
    actor=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    def kill(directory):
        assert directory==scope and (scope/'cgroup.procs').read_text()=='123\n456\n'
        events.append('quiesce');(scope/'cgroup.events').write_text('populated 0\n')
        (scope/'cgroup.procs').write_text('');(scope/'pids.current').write_text('0');(proc/'123/stat').unlink()
    monkeypatch.setattr(actor,'kill',kill)
    receipt=tmp_path/'phase-receipt.json';daemon=Daemon(manifest);fault={'point':None};stored=[1]
    def request(method,path,*,deadline=None):
        if method=='POST':
            service=next(s for s,c in manifest['containers'].items() if '/'+c['Id']+'/' in path)
            assert path=='/containers/'+manifest['containers'][service]['Id']+'/stop?t=10'
            durable=guard.read_private(receipt)
            assert durable['workload_phase']=='retiring-'+service
            assert durable['pending']=={'action':'stop','service':service}
            if fault['point']=='before-stop-'+service:raise TimeoutError('before stop submission')
            events.append('stop-'+service);daemon.containers[manifest['containers'][service]['Id']]['State']={'Running':False,'Pid':0}
            if fault['point']=='after-stop-'+service:raise TimeoutError('stop reply lost')
        if method=='DELETE':events.append('remove-'+path.split('/')[2].split('?')[0])
        return daemon(method,path)
    def empty(identity):
        if identity not in daemon.containers:events.append('absent-'+identity);return True
        return not daemon.containers[identity]['State']['Running'] and fault['point']!='nonempty'
    docker=runtime.DockerBackend(manifest,request=request,cgroup_empty=empty)
    def notify(message,fd=None):
        assert message=='FDSTOREREMOVE=1\nFDNAME=admission';events.append('fdremove');stored[0]=0
    def count():events.append('count0');return stored[0]
    store=guard.FdStore(notify=notify,barrier=lambda:events.append('barrier'),count=count)
    def state():return guard.GuardianState(receipt,manifest_digest='a'*64,docker=docker,quiesce=actor.quiesce,release=store.release)
    value=state();value.register(docker.ids)
    for service,identity in docker.ids.items():
        if service!='simulator':daemon.containers[identity]['State']={'Running':True,'Pid':1000+len(service)}
    handler=runtime.RequestHandler(value,controller=actor,manifest_digest='a'*64,
        lease_check=lambda **kwargs:actor.verify_context('qualification',value.state['workload_phase'],**kwargs))
    def call(operation):return handler.request({'operation':operation,'manifest_sha256':'a'*64},(123,1000,1000))
    xml=tmp_path/'python.xml';xml.write_text('<testsuites><testsuite tests="11" failures="0" errors="0" skipped="0">'+
        ''.join('<testcase name="case'+str(i)+'" classname="integration" />' for i in range(11))+'</testsuite></testsuites>')
    child=SimpleNamespace(poll=lambda:0,returncode=0)
    def restore():stack.restore_browser_controller(actor)
    return SimpleNamespace(state=value,recover=state,actor=actor,docker=docker,daemon=daemon,events=events,
        stored=stored,fault=fault,call=call,handler=handler,scope=scope,proc=proc,manager=manager,record=record,
        receipt=receipt,xml=xml,child=child,restore=restore)


def assert_phase_cleanup(session):
    from services.lorawan.tests import qualification_guard as guard
    state=session.recover()
    with pytest.raises(Refused):state.action('start','mqtt')
    class Notify:
        def __call__(self,message):assert message=='READY=1'
        def barrier(self):pass
    assert runtime.recover_owned_session(state,Notify())==0
    suffix=session.events[session.events.index('quiesce'):]
    ids=list(session.docker.ids.values())
    assert len(suffix)==18 and suffix[0]=='quiesce'
    assert set(suffix[1:8])=={'remove-'+i for i in ids}
    assert set(suffix[8:15])=={'absent-'+i for i in ids}
    assert suffix[15:]==['fdremove','barrier','count0']
    assert not session.daemon.containers and session.stored==[0]
    assert guard.read_private(session.receipt)['phase']=='terminal'
    assert all(path.endswith('?force=1&v=0') for method,path in session.daemon.calls if method=='DELETE')


def test_closed_phase_retires_three_exact_ids_before_restoring_browser_capacity(phase_session):
    from services.lorawan.tests import qualification_stack_controller as stack
    s=phase_session
    assert s.state.state.get('workload_phase')=='python'
    stack.enter_browser_phase(s.child,s.xml,request=s.call,restore=s.restore)
    assert s.state.state['workload_phase']=='browser' and s.state.state['pending'] is None
    assert s.events==['stop-chirpstack','stop-redis','stop-simulator','manager-60']
    assert len(s.daemon.containers)==7 and s.scope.joinpath('pids.max').read_text()=='60'
    assert_phase_cleanup(s)


@pytest.mark.parametrize('phase,operation',[
    ('python','retire-redis-for-browser'),('python','enter-browser'),
    ('chirpstack-retired','retire-chirpstack-for-browser'),('chirpstack-retired','enter-browser'),
    ('browser-ready','retire-chirpstack-for-browser'),('browser-ready','retire-redis-for-browser'),
    ('browser','enter-browser'),('browser','retire-chirpstack-for-browser'),
])
def test_phase_replay_skip_and_backward_requests_cannot_mutate(phase_session,phase,operation):
    s=phase_session
    if phase!='python':s.call('retire-chirpstack-for-browser')
    if phase in ('redis-retired','browser-ready','browser'):s.call('retire-redis-for-browser')
    if phase in ('browser-ready','browser'):s.call('retire-simulator-for-browser')
    if phase=='browser':s.restore();s.call('enter-browser')
    before=list(s.events)
    with pytest.raises(Refused):s.call(operation)
    assert s.events==before
    assert_phase_cleanup(s)


@pytest.mark.parametrize('phase',['chirpstack-retired','browser-ready','browser'])
@pytest.mark.parametrize('service',['chirpstack','redis','simulator'])
@pytest.mark.parametrize('action',['start','restart'])
def test_retirement_permanently_revokes_both_members(phase_session,phase,service,action):
    s=phase_session;s.call('retire-chirpstack-for-browser')
    if phase in ('redis-retired','browser-ready','browser'):s.call('retire-redis-for-browser')
    if phase in ('browser-ready','browser'):s.call('retire-simulator-for-browser')
    if phase=='browser':s.restore();s.call('enter-browser')
    before=list(s.events)
    with pytest.raises(Refused):s.handler.request({'operation':'lifecycle','manifest_sha256':'a'*64,'action':action,'service':service},(123,1000,1000))
    assert s.events==before


@pytest.mark.parametrize('point',['before-stop-chirpstack','after-stop-chirpstack','before-stop-redis','after-stop-redis','before-stop-simulator','after-stop-simulator'])
def test_uncertain_stop_reply_recovers_seven_ids_without_retry(phase_session,point):
    from services.lorawan.tests import qualification_stack_controller as stack
    s=phase_session;s.fault['point']=point
    with pytest.raises(TimeoutError):stack.enter_browser_phase(s.child,s.xml,request=s.call,restore=s.restore)
    assert 'manager-60' not in s.events
    s.fault['point']=None
    assert_phase_cleanup(s)
    assert sum(e=='stop-chirpstack' for e in s.events)<=1 and sum(e=='stop-redis' for e in s.events)<=1


@pytest.mark.parametrize('phase',['retiring-chirpstack','chirpstack-retired','retiring-redis','redis-retired','retiring-simulator','browser-ready','browser'])
@pytest.mark.parametrize('side',['before','after'])
def test_each_phase_durable_write_crash_is_cleanup_only(phase_session,monkeypatch,phase,side):
    from services.lorawan.tests import qualification_guard as guard
    from services.lorawan.tests import qualification_stack_controller as stack
    s=phase_session;persist=guard.persist
    def interrupted(path,value,**kwargs):
        if value.get('workload_phase')==phase and value['phase']=='armed':
            if side=='after':persist(path,value,**kwargs)
            raise OSError('durable phase boundary')
        persist(path,value,**kwargs)
    monkeypatch.setattr(guard,'persist',interrupted)
    with pytest.raises(OSError):stack.enter_browser_phase(s.child,s.xml,request=s.call,restore=s.restore)
    monkeypatch.setattr(guard,'persist',persist)
    assert_phase_cleanup(s)


@pytest.mark.parametrize('point',['before-ready-ack','after-ready-ack','before-restore','during-restore','after-restore','before-browser-ack','after-browser-ack'])
def test_handoff_ack_and_manager_crash_never_resume_work(phase_session,point):
    from services.lorawan.tests import qualification_stack_controller as stack
    s=phase_session
    def request(operation):
        answer=s.call(operation)
        if (point=='before-ready-ack' and operation=='retire-simulator-for-browser' or
            point=='before-browser-ack' and operation=='enter-browser'):raise TimeoutError('ack lost')
        if point=='after-browser-ack' and operation=='enter-browser':raise OSError('controller exits after ack')
        return answer
    def restore():
        if point in ('after-ready-ack','before-restore'):raise OSError('controller exits before restoration')
        if point=='during-restore':s.manager['tasks']='60';raise OSError('manager applied before kernel readback')
        s.restore()
        if point=='after-restore':raise OSError('controller exits after restoration')
    with pytest.raises((OSError,TimeoutError)):stack.enter_browser_phase(s.child,s.xml,request=request,restore=restore)
    assert_phase_cleanup(s)


@pytest.mark.parametrize('service',['chirpstack','simulator'])
@pytest.mark.parametrize('change',['running','pid','nonempty','missing','replacement'])
def test_retirement_requires_positive_original_stopped_empty_identity(phase_session,service,change):
    s=phase_session
    if service=='simulator':s.call('retire-chirpstack-for-browser');s.call('retire-redis-for-browser')
    identity=s.docker.ids[service];original=s.docker.request
    def request(method,path,**kwargs):
        result=original(method,path,**kwargs)
        if method=='POST':
            if change=='running':s.daemon.containers[identity]['State']['Running']=True
            if change=='pid':s.daemon.containers[identity]['State']['Pid']=1234
            if change=='nonempty':s.fault['point']='nonempty'
            if change=='missing':s.daemon.containers.pop(identity)
            if change=='replacement':s.daemon.containers[identity]['Id']='f'*64
        return result
    s.docker.request=request
    with pytest.raises(Refused):s.call('retire-'+service+'-for-browser')
    assert s.state.state['workload_phase']=='retiring-'+service and 'manager-60' not in s.events and s.stored==[1]


@pytest.mark.parametrize('operation',['retire-chirpstack-for-browser','retire-redis-for-browser','retire-simulator-for-browser','enter-browser'])
def test_phase_requests_require_original_main_pid_and_qualification_mode(phase_session,operation):
    s=phase_session;process=s.proc/'124';process.mkdir()
    (process/'status').write_text('Uid:\t1000\t1000\t1000\t1000\n');(process/'cgroup').write_text('0::'+s.record['cgroup']+'\n')
    payload={'operation':operation,'manifest_sha256':'a'*64}
    with pytest.raises(Refused):s.handler.request(payload,(124,1000,1000))
    s.handler.mode='lifecycle-proof'
    with pytest.raises(Refused):s.handler.request(payload,(123,1000,1000))
    assert not s.events and s.state.state['workload_phase']=='python'


@pytest.mark.parametrize('change',['kernel64','manager64','memory','swap','cpu','pool','invocation','manager-cgroup','live-child'])
def test_first_retirement_refuses_wrong_context_or_unexited_workload(phase_session,change):
    s=phase_session
    if change=='kernel64':(s.scope/'pids.max').write_text('60')
    elif change=='manager64':s.manager['tasks']='60'
    elif change=='memory':(s.scope/'memory.max').write_text('536870912')
    elif change=='swap':(s.scope/'memory.swap.max').write_text('1')
    elif change=='cpu':(s.scope/'cpu.max').write_text('300000 100000')
    elif change=='pool':(s.scope.parent/'pids.max').write_text('264')
    elif change=='invocation':s.manager['invocation']='c'*32
    elif change=='manager-cgroup':s.manager['cgroup']='/other'
    else:
        process=s.proc/'124';process.mkdir();(process/'cgroup').write_text('0::'+s.record['cgroup']+'\n')
        (process/'status').write_text('Uid:\t1000\t1000\t1000\t1000\n');(s.scope/'cgroup.procs').write_text('123\n456\n124\n')
    with pytest.raises(Refused):s.call('retire-chirpstack-for-browser')
    assert not s.events and s.state.state['workload_phase']=='python'


@pytest.mark.parametrize('service',['mqtt','postgres','ingest','openhab'])
def test_browser_entry_requires_all_four_remaining_dependencies(phase_session,service):
    s=phase_session;s.call('retire-chirpstack-for-browser');s.call('retire-redis-for-browser');s.call('retire-simulator-for-browser');s.restore()
    s.daemon.containers[s.docker.ids[service]]['State']={'Running':False,'Pid':0}
    with pytest.raises(Refused):s.call('enter-browser')
    assert s.state.state['workload_phase']=='browser-ready'


@pytest.mark.parametrize('change',['unknown-phase','unknown-key','manifest','missing-phase','wrong-mode'])
def test_corrupt_or_mode_mismatched_phase_receipt_keeps_original_fd(phase_session,change):
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;s.call('retire-chirpstack-for-browser');value=guard.read_private(s.receipt)
    if change=='unknown-phase':value['workload_phase']='resume'
    if change=='unknown-key':value['tasks']=64
    if change=='manifest':value['manifest_sha256']='b'*64
    if change=='missing-phase':value.pop('workload_phase')
    if change=='wrong-mode':s.docker.mode='lifecycle-proof'
    guard.persist(s.receipt,value)
    with pytest.raises(Refused):s.recover()
    assert s.stored==[1] and len(s.daemon.containers)==7 and 'fdremove' not in s.events


@pytest.mark.parametrize('change',[None,'populated','pids','missing-pids','bad-events'])
def test_retired_cgroup_requires_both_population_and_task_zero(tmp_path,change):
    identity='a'*64;path=tmp_path/'system.slice'/('docker-'+identity+'.scope');path.mkdir(parents=True)
    (path/'cgroup.events').write_text('populated 0\nfrozen 0\n');(path/'pids.current').write_text('0\n')
    if change=='populated':(path/'cgroup.events').write_text('populated 1\n')
    if change=='pids':(path/'pids.current').write_text('1\n')
    if change=='missing-pids':(path/'pids.current').unlink()
    if change=='bad-events':(path/'cgroup.events').write_text('populated 0\npopulated 1\n')
    if change in ('missing-pids','bad-events'):
        with pytest.raises((Refused,OSError)):runtime.docker_cgroup_empty(identity,cgroup_root=tmp_path)
    else:assert runtime.docker_cgroup_empty(identity,cgroup_root=tmp_path)==(change is None)


@pytest.mark.parametrize('service',['chirpstack','redis','simulator'])
def test_late_stop_reply_cannot_complete_phase_or_release_reservation(phase_session,monkeypatch,service):
    import time
    s=phase_session;clock=[100.];monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    if service in ('redis','simulator'):s.call('retire-chirpstack-for-browser')
    if service=='simulator':s.call('retire-redis-for-browser')
    original=s.docker.request
    def delayed(method,path,**kwargs):
        value=original(method,path,**kwargs)
        if method=='POST':clock[0]+=31
        return value
    s.docker.request=delayed
    with pytest.raises(Refused):s.call('retire-'+service+'-for-browser')
    assert s.state.state['workload_phase']=='retiring-'+service and 'manager-60' not in s.events
    assert_phase_cleanup(s)


@pytest.mark.parametrize('change',['command-failed','kernel-not-restored','manager-not-restored'])
def test_failed_cap_restoration_never_acknowledges_browser(phase_session,monkeypatch,change):
    import subprocess
    from services.lorawan.tests import qualification_stack_controller as stack
    s=phase_session
    def failed(argv,**kwargs):
        assert argv[-1]=='TasksMax=60'
        if change=='command-failed':raise subprocess.CalledProcessError(1,argv)
        if change!='manager-not-restored':s.manager['tasks']='60'
        if change!='kernel-not-restored':(s.scope/'pids.max').write_text('60')
    monkeypatch.setattr(subprocess,'run',failed)
    with pytest.raises((Refused,subprocess.CalledProcessError)):stack.enter_browser_phase(s.child,s.xml,request=s.call,restore=s.restore)
    assert s.state.state['workload_phase']=='browser-ready'
    assert_phase_cleanup(s)


@pytest.mark.parametrize('change',['source','identity','delete','inspection','cgroup'])
def test_post_retirement_cleanup_failure_keeps_fdstore(phase_session,change):
    s=phase_session;s.call('retire-chirpstack-for-browser');s.call('retire-redis-for-browser')
    if change=='source':(s.docker.root/'deploy/lorawan/compose.test.yaml').write_text('changed')
    if change=='identity':s.daemon.containers[s.docker.ids['redis']]['Id']='f'*64
    request=s.docker.request
    def failed(method,path,**kwargs):
        if change=='delete' and method=='DELETE':raise TimeoutError('delete reply unavailable')
        if change=='inspection' and method=='GET':raise OSError('inspection unavailable')
        return request(method,path,**kwargs)
    s.docker.request=failed
    if change=='cgroup':s.docker.cgroup_empty=lambda identity:False
    state=s.recover()
    with pytest.raises((Refused,OSError,TimeoutError)):state.cleanup()
    assert 'quiesce' in s.events and 'fdremove' not in s.events and s.stored==[1]


@pytest.mark.parametrize('phase',['cleanup','terminal'])
@pytest.mark.parametrize('side',['before','after'])
def test_post_retirement_cleanup_journal_crash_recovers_without_phase_replay(phase_session,monkeypatch,phase,side):
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;s.call('retire-chirpstack-for-browser');s.call('retire-redis-for-browser');persist=guard.persist
    def failed(path,value,**kwargs):
        if value['phase']==phase:
            if side=='after':persist(path,value,**kwargs)
            raise OSError('cleanup journal interrupted')
        persist(path,value,**kwargs)
    monkeypatch.setattr(guard,'persist',failed)
    with pytest.raises(OSError):s.state.cleanup()
    assert 'fdremove' not in s.events and s.stored==[1]
    monkeypatch.setattr(guard,'persist',persist)
    state=s.recover();state.cleanup()
    assert not s.daemon.containers and s.stored==[0] and s.events[-3:]==['fdremove','barrier','count0']
    assert s.events.count('stop-chirpstack')==s.events.count('stop-redis')==1


def test_system_guardian_reads_exact_user_manager_without_inherited_bus_environment(phase_session,monkeypatch):
    import subprocess
    s=phase_session;original=subprocess.check_output
    monkeypatch.delenv('XDG_RUNTIME_DIR',raising=False);monkeypatch.delenv('DBUS_SESSION_BUS_ADDRESS',raising=False)
    def show(argv,**kwargs):
        assert kwargs.get('env',{}).get('XDG_RUNTIME_DIR')=='/run/user/1000'
        assert kwargs.get('env',{}).get('DBUS_SESSION_BUS_ADDRESS')=='unix:path=/run/user/1000/bus'
        return original(argv,**kwargs)
    monkeypatch.setattr(subprocess,'check_output',show)
    s.actor.verify_context('qualification','python')


@pytest.mark.parametrize('action',['start','stop','restart'])
def test_browser_pending_lifecycle_recovery_remains_cleanup_only(phase_session,action):
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;s.call('retire-chirpstack-for-browser');s.call('retire-redis-for-browser');s.call('retire-simulator-for-browser');s.restore();s.call('enter-browser')
    original=s.docker.request
    def lost(method,path,**kwargs):
        if method=='POST':
            assert path=='/containers/'+s.docker.ids['mqtt']+'/'+action+('' if action=='start' else '?t=10')
            assert guard.read_private(s.receipt)['pending']=={'action':action,'service':'mqtt'}
            raise TimeoutError('browser lifecycle reply lost')
        return original(method,path,**kwargs)
    s.docker.request=lost
    with pytest.raises(TimeoutError):s.state.action(action,'mqtt')
    s.docker.request=original
    assert_phase_cleanup(s)


@pytest.mark.parametrize('phase',['chirpstack-retired','browser-ready','browser'])
def test_continuing_phase_check_rejects_retired_reactivation(phase_session,phase):
    s=phase_session;s.call('retire-chirpstack-for-browser')
    if phase in ('redis-retired','browser-ready','browser'):s.call('retire-redis-for-browser')
    if phase in ('browser-ready','browser'):s.call('retire-simulator-for-browser')
    if phase=='browser':s.restore();s.call('enter-browser')
    s.daemon.containers[s.docker.ids['chirpstack']]['State']={'Running':True,'Pid':1234}
    with pytest.raises(Refused):s.state.check_retired()
    assert s.stored==[1]


def phase_deadline(end):
    from services.lorawan.tests import qualification_guard as guard
    assert hasattr(guard,'PhaseDeadline'),'phase work requires an absolute deadline'
    return guard.PhaseDeadline(end)


def test_nested_two_eighteen_second_reads_cannot_submit_a_late_stop(phase_session,monkeypatch):
    """The reviewer's real backend path used to POST at fake elapsed36s."""
    import time
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;clock=[0.];delayed=[];original=s.docker.request
    monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    def request(method,path,**kwargs):
        if method=='GET' and len(delayed)<2 and guard.read_private(s.receipt)['pending'] is not None:
            clock[0]+=18.;delayed.append(path)
        return original(method,path,**kwargs)
    s.docker.request=request
    with pytest.raises(Refused):s.call('retire-chirpstack-for-browser')
    assert clock==[36.] and len(delayed)==2
    assert not [call for call in s.daemon.calls if call[0]=='POST']
    assert s.state.state['pending']=={'action':'stop','service':'chirpstack'}
    assert s.state.state['workload_phase']=='retiring-chirpstack'
    assert s.stored==[1] and len(s.daemon.containers)==7 and s.manager['tasks']=='32'
    s.docker.request=original;assert_phase_cleanup(s)


@pytest.mark.parametrize('boundary',['alive','peer','lease','controller','python','retired'])
def test_phase_prechecks_consume_original_deadline(phase_session,monkeypatch,boundary):
    import time
    s=phase_session;clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    if boundary=='retired':s.call('retire-chirpstack-for-browser')
    obj,name={'alive':(s.actor,'alive'),'peer':(s.actor,'process'),'lease':(s.handler,'lease_check'),
        'controller':(s.actor,'verify_context'),'python':(s.actor,'python_exited'),'retired':(s.state,'check_retired')}[boundary]
    original=getattr(obj,name);used=[]
    def slow(*args,**kwargs):
        result=original(*args,**kwargs)
        if not used:clock[0]+=30.;used.append(True)
        return result
    monkeypatch.setattr(obj,name,slow)
    if boundary=='retired':
        lease=s.handler.lease_check
        def checked(**kwargs):lease(**kwargs);s.state.check_retired(**kwargs)
        s.handler.lease_check=checked
    before=list(s.events)
    with pytest.raises(Refused):s.call('retire-redis-for-browser' if boundary=='retired' else 'retire-chirpstack-for-browser')
    assert s.events==before and s.stored==[1] and s.manager['tasks']=='32'


@pytest.mark.parametrize('operation',['retire-chirpstack-for-browser','retire-redis-for-browser','retire-simulator-for-browser','enter-browser'])
@pytest.mark.parametrize('boundary',['validation','fsync','replacement'])
def test_expiry_blocks_each_phase_promotion_and_effect(phase_session,monkeypatch,operation,boundary):
    import os,time
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session
    if operation!='retire-chirpstack-for-browser':s.call('retire-chirpstack-for-browser')
    if operation=='enter-browser':s.call('retire-redis-for-browser');s.call('retire-simulator-for-browser');s.restore()
    clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);before=guard.read_private(s.receipt);events=list(s.events)
    if boundary=='validation':
        original=s.docker.validate
        def slow(*args,**kwargs):result=original(*args,**kwargs);clock[0]=30.;return result
        monkeypatch.setattr(s.docker,'validate',slow)
    else:
        original=getattr(os,'fsync' if boundary=='fsync' else 'replace')
        def slow(*args,**kwargs):result=original(*args,**kwargs);clock[0]=30.;return result
        monkeypatch.setattr(os,'fsync' if boundary=='fsync' else 'replace',slow)
    with pytest.raises(Refused):s.call(operation)
    assert s.events==events and s.stored==[1]
    if boundary!='replacement':assert guard.read_private(s.receipt)==before


@pytest.mark.parametrize('boundary',['precheck','pending','reply','retirement','ack'])
@pytest.mark.parametrize('cleanup_failure',[False,True])
def test_expired_phase_unwinds_timer_before_positive_owned_cleanup(phase_session,monkeypatch,boundary,cleanup_failure,tmp_path):
    import signal,time
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);original=s.docker.request;observed_expiry=[]
    def request(method,path,**kwargs):
        if method=='DELETE':
            assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.) and guard._phase_deadline is None
            assert kwargs.get('deadline') is None
            if cleanup_failure:raise Refused('positive cleanup unavailable')
        if boundary=='pending' and method=='GET' and guard.read_private(s.receipt)['pending'] is not None:clock[0]=30.
        if boundary=='retirement' and method=='GET' and 'stop-chirpstack' in s.events:clock[0]=30.
        result=original(method,path,**kwargs)
        if boundary=='reply' and method=='POST':clock[0]=30.
        return result
    s.docker.request=request
    if boundary=='precheck':
        check=s.handler.lease_check
        def expired(**kwargs):check(**kwargs);clock[0]=30.
        s.handler.lease_check=expired
    if boundary=='ack':
        transition=s.state.transition
        def expired(*args,**kwargs):result=transition(*args,**kwargs);clock[0]=30.;return result
        monkeypatch.setattr(s.state,'transition',expired)
    def operation():
        with pytest.raises(Refused):s.call('retire-chirpstack-for-browser')
        assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.) and guard._phase_deadline is None
        observed_expiry.append(True)
    if cleanup_failure:
        with pytest.raises(Refused,match='positive cleanup'):runtime.run_owned_session(operation,s.state,tmp_path/'failure.json')
        assert s.stored==[1] and 'fdremove' not in s.events
    else:
        assert runtime.run_owned_session(operation,s.state,tmp_path/'failure.json')==0
        ids=list(s.docker.ids.values());suffix=s.events[s.events.index('quiesce'):]
        assert suffix==['quiesce']+['remove-'+i for i in ids]+['absent-'+i for i in ids]+['fdremove','barrier','count0']
        assert s.stored==[0] and not s.daemon.containers and guard.read_private(s.receipt)['phase']=='terminal'
    assert s.events.count('stop-chirpstack')==(1 if boundary in ('reply','retirement','ack') else 0)
    assert 'stop-redis' not in s.events and 'manager-60' not in s.events
    assert observed_expiry==[True]


def test_phase_transition_requires_internal_deadline_before_any_io(phase_session):
    s=phase_session;s.daemon.calls.clear()
    with pytest.raises(Refused):s.state.transition('retire-chirpstack-for-browser')
    assert not s.events and not s.daemon.calls


@pytest.mark.parametrize('field',['deadline','timeout','seconds'])
def test_wire_cannot_supply_phase_timing_authority(phase_session,field):
    s=phase_session
    with pytest.raises(Refused):s.handler.request({'operation':'retire-chirpstack-for-browser','manifest_sha256':'a'*64,field:60},(123,1000,1000))
    assert not s.events


def test_nested_io_and_controller_calls_use_one_decreasing_allowance(phase_session,monkeypatch):
    import subprocess,time
    s=phase_session;clock=[100.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);end=phase_deadline(104.)
    show=subprocess.check_output;timeouts=[]
    def observed(argv,**kwargs):timeouts.append(kwargs['timeout']);result=show(argv,**kwargs);clock[0]+=1.;return result
    monkeypatch.setattr(subprocess,'check_output',observed)
    s.actor.verify_context('qualification','python',deadline=end)
    s.actor.verify_context('qualification','python',deadline=end)
    assert timeouts==[4.,3.]
    original=s.docker.request;seen=[]
    def request(method,path,*,deadline):
        assert deadline is end;seen.append(deadline.timeout(35));clock[0]+=1.
        return original(method,path)
    s.docker.request=request
    with pytest.raises(Refused):s.docker.validate(s.docker.ids,deadline=end)
    assert seen==[2.,1.] and not s.events
    with pytest.raises(Refused):s.actor.verify_context('qualification','python',deadline=end)
    assert timeouts==[4.,3.]


@pytest.mark.parametrize('stage',['header','body'])
def test_wall_timer_interrupts_real_buffered_docker_drip(unix_directory,stage):
    import os,signal,socket,threading,time
    from services.lorawan.tests import qualification_guard as guard
    deadline=phase_deadline(time.monotonic()+.15);path=unix_directory/'drip.sock'
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(path));path.chmod(0o600);server.listen(1)
    received=[];done=threading.Event()
    def drip():
        connection,_=server.accept()
        with connection:
            received.append(connection.recv(8192))
            try:
                if stage=='body':connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n')
                for _ in range(50):
                    connection.sendall(b'x')
                    if done.wait(.01):break
            except (BrokenPipeError,ConnectionResetError):pass
    worker=threading.Thread(target=drip,daemon=True);worker.start();start=time.monotonic();prior=signal.getsignal(signal.SIGALRM)
    try:
        with pytest.raises(guard.PhaseExpired):
            with guard.phase_scope(deadline):runtime.DockerSocket(path,owner=os.getuid())('GET','/containers/'+'a'*64+'/json',deadline=deadline)
        assert time.monotonic()-start<.45
        assert received and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
        assert guard._phase_deadline is None and signal.getsignal(signal.SIGALRM)==prior
    finally:done.set();worker.join(1);server.close()
    assert not worker.is_alive()


def test_guardian_and_fdstore_manager_reads_share_original_five_second_ceiling(guardian_mode_context,monkeypatch):
    import subprocess,time
    from types import SimpleNamespace
    proc,cg,unit,scope,manager,_=guardian_mode_context;(scope/'pids.max').write_text('8')
    clock=[10.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);end=phase_deadline(16.);timeouts=[]
    def show(argv,**kwargs):timeouts.append(kwargs['timeout']);clock[0]+=4.;return '8\n'
    def count(argv,**kwargs):timeouts.append(kwargs['timeout']);clock[0]+=2.;return SimpleNamespace(stdout='1')
    monkeypatch.setattr(subprocess,'check_output',show);monkeypatch.setattr(subprocess,'run',count)
    runtime.check_service_context(unit,mode='qualification',proc_root=proc,cgroup_root=cg,deadline=end)
    with pytest.raises(Refused):runtime.fdstore_count(unit,deadline=end)
    assert timeouts==[5.,2.]
    with pytest.raises(Refused):runtime.fdstore_count(unit,deadline=end)
    assert timeouts==[5.,2.]


def test_wall_timer_interrupts_and_reaps_stalled_manager(guardian_mode_context,monkeypatch):
    import signal,subprocess,sys,time
    from services.lorawan.tests import qualification_guard as guard
    proc,cg,unit,scope,manager,_=guardian_mode_context;(scope/'pids.max').write_text('8')
    deadline=phase_deadline(time.monotonic()+.15);children=[];popen=subprocess.Popen
    def child(*args,**kwargs):value=popen(*args,**kwargs);children.append(value);return value
    monkeypatch.setattr(subprocess,'Popen',child)
    def blocked(argv,**kwargs):
        return subprocess.run([sys.executable,'-B','-c','import time; time.sleep(2)'],capture_output=True,text=True,check=True,timeout=kwargs['timeout']).stdout
    monkeypatch.setattr(subprocess,'check_output',blocked);start=time.monotonic()
    with pytest.raises((Refused,subprocess.TimeoutExpired)):
        with guard.phase_scope(deadline):runtime.check_service_context(unit,mode='qualification',proc_root=proc,cgroup_root=cg,deadline=deadline)
    assert time.monotonic()-start<.7 and children and all(p.poll() is not None for p in children)
    assert guard._phase_deadline is None and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)


@pytest.mark.parametrize('late',['check','accept','receive','reply'])
def test_transport_keeps_preaccept_check_deadline_through_final_ack(phase_session,monkeypatch,late):
    import struct,time
    s=phase_session;clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);sent=[];closed=[]
    assert hasattr(runtime,'serve_request'),'the continuing check and accepted request need one scope'
    class Connection:
        def settimeout(self,value):assert 0<value<=35
        def getsockopt(self,*args):return struct.pack('3i',123,1000,1000)
        def recvmsg(self,*args):
            if late=='receive':clock[0]+=20.
            return json.dumps({'operation':'retire-chirpstack-for-browser','manifest_sha256':'a'*64}).encode(),[],0,None
        def sendall(self,value):sent.append(value)
        def close(self):closed.append(True)
    class Server:
        def accept(self):
            if late=='accept':clock[0]+=20.
            return Connection(),None
    def check(**kwargs):clock[0]+=30. if late=='check' else 15.
    if late=='reply':
        original=s.handler.request
        def request(*args,**kwargs):value=original(*args,**kwargs);clock[0]=30.;return value
        monkeypatch.setattr(s.handler,'request',request)
    with pytest.raises(Refused):runtime.serve_request(Server(),s.handler,lease_check=check,lease_end=1800.,mode='qualification')
    assert not sent and closed==([] if late=='check' else [True]) and s.manager['tasks']=='32'
    if late!='reply':assert not s.events


def test_shorter_immutable_lease_and_transport_deadline_cannot_be_renewed(phase_session,monkeypatch):
    import time
    s=phase_session;clock=[100.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);end=phase_deadline(105.)
    original=s.handler.lease_check
    def slow(**kwargs):original(**kwargs);clock[0]=105.
    s.handler.lease_check=slow
    with pytest.raises(Refused):s.handler.request({'operation':'retire-chirpstack-for-browser','manifest_sha256':'a'*64},(123,1000,1000),deadline=end)
    assert not s.events


@pytest.mark.parametrize('expiry',['connect','write','header','body',None])
def test_docker_transport_rechecks_connect_and_clamps_every_io(unix_directory,monkeypatch,expiry):
    import http.client,os,socket,time
    path=unix_directory/'controlled.sock'
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(path));path.chmod(0o600)
    transport=runtime.DockerSocket(path,owner=os.getuid());clock=[0.];timeouts=[];effects=[];closed=[]
    monkeypatch.setattr(time,'monotonic',lambda:clock[0]);end=phase_deadline(4.)
    def advance(stage):clock[0]=4. if expiry==stage else clock[0]+.5
    class Socket:
        def settimeout(self,value):timeouts.append(value)
        def connect(self,path):advance('connect')
    class Response:
        status=200
        def read(self,limit):advance('body');return b'{}'
        def close(self):closed.append('response')
    class HTTP:
        def __init__(self,*args,**kwargs):assert kwargs['timeout']==4.
        def request(self,method,path,**kwargs):effects.append(clock[0]);advance('write')
        def getresponse(self):advance('header');return Response()
        def close(self):closed.append('connection')
    monkeypatch.setattr(socket,'socket',lambda *a,**kw:Socket());monkeypatch.setattr(http.client,'HTTPConnection',HTTP)
    try:
        if expiry is None:assert transport('POST','/containers/'+'a'*64+'/stop?t=10',deadline=end)=={}
        else:
            with pytest.raises(Refused):transport('POST','/containers/'+'a'*64+'/stop?t=10',deadline=end)
        assert effects==([] if expiry=='connect' else [.5])
        assert timeouts=={'connect':[4.],'write':[4.,3.5],'header':[4.,3.5,3.],
            'body':[4.,3.5,3.,2.5],None:[4.,3.5,3.,2.5]}[expiry]
        assert closed[-1]=='connection'
        clock[0]=5.;before=list(timeouts)
        with pytest.raises(Refused):transport('POST','/containers/'+'a'*64+'/stop?t=10',deadline=end)
        assert timeouts==before
    finally:server.close()


@pytest.mark.parametrize('mode',['qualification','lifecycle-proof'])
def test_ordinary_wire_request_has_original_timeout_outside_phase_scope(phase_session,monkeypatch,mode):
    import struct,time
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;s.handler.mode=mode;s.state.mode=mode;s.docker.mode=mode;timeouts=[];sent=[];closed=[]
    payload={'operation':'hello','manifest_sha256':'a'*64}
    class Connection:
        def settimeout(self,value):timeouts.append(value)
        def getsockopt(self,*args):return struct.pack('3i',123,1000,1000)
        def recvmsg(self,*args):return json.dumps(payload).encode(),[],0,None
        def sendall(self,value):
            assert guard._phase_deadline is None;sent.append(json.loads(value))
        def close(self):closed.append(True)
    class Server:
        def accept(self):return Connection(),None
    def check(**kwargs):
        assert (kwargs.get('deadline') is None)==(mode=='lifecycle-proof')
    # Context is tested elsewhere; hello itself must retain its exact wire reply.
    s.handler.lease_check=lambda:None
    runtime.serve_request(Server(),s.handler,lease_check=check,lease_end=time.monotonic()+1800,mode=mode)
    assert sent==[{'ready':True}] and timeouts[-1]==35 and closed==[True] and not s.events


def test_preaccept_check_time_is_not_discarded_by_handler_entry(phase_session,monkeypatch):
    import struct,time
    s=phase_session;clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);seen=[];sent=[]
    class Connection:
        def settimeout(self,value):pass
        def getsockopt(self,*args):return struct.pack('3i',123,1000,1000)
        def recvmsg(self,*args):return b'{"operation":"retire-chirpstack-for-browser","manifest_sha256":"'+b'a'*64+b'"}',[],0,None
        def sendall(self,value):sent.append(value)
        def close(self):pass
    class Server:
        def accept(self):return Connection(),None
    def precheck(*,deadline):seen.append(deadline);clock[0]+=15.
    original=s.handler.lease_check
    def handlercheck(*,deadline):
        assert deadline is seen[0];original(deadline=deadline);clock[0]+=15.
    s.handler.lease_check=handlercheck
    with pytest.raises(Refused):runtime.serve_request(Server(),s.handler,lease_check=precheck,lease_end=1800.,mode='qualification')
    assert not sent and not s.events and clock==[30.]


def test_shorter_lease_end_bounds_direct_handler_before_prechecks(phase_session,monkeypatch):
    import time
    s=phase_session;clock=[100.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);s.handler.lease_end=105.
    original=s.handler.lease_check
    def slow(**kwargs):original(**kwargs);clock[0]=105.
    s.handler.lease_check=slow
    with pytest.raises(Refused):s.call('retire-chirpstack-for-browser')
    assert not s.events


def test_real_alarm_expiry_releases_only_after_independent_positive_cleanup(phase_session,tmp_path):
    import signal,time
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;original=s.docker.request;expired=[]
    def blocked(method,path,**kwargs):
        if kwargs.get('deadline') is not None:time.sleep(.3)
        if method=='DELETE':assert guard._phase_deadline is None and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
        return original(method,path,**kwargs)
    s.docker.request=blocked
    def operation():
        with pytest.raises(guard.PhaseExpired):
            s.handler.request({'operation':'retire-chirpstack-for-browser','manifest_sha256':'a'*64},(123,1000,1000),deadline=phase_deadline(time.monotonic()+.1))
        expired.append(True)
    assert runtime.run_owned_session(operation,s.state,tmp_path/'real-expiry.json')==0
    ids=list(s.docker.ids.values())
    assert expired==[True] and s.events==['quiesce']+['remove-'+i for i in ids]+['absent-'+i for i in ids]+['fdremove','barrier','count0']
    assert not s.daemon.containers and s.stored==[0] and guard.read_private(s.receipt)['phase']=='terminal'


@pytest.mark.parametrize('change',['source','identity','mode','receipt'])
def test_expiry_never_grants_release_for_unknown_cleanup_state(phase_session,monkeypatch,change):
    import time
    from services.lorawan.tests import qualification_guard as guard
    s=phase_session;clock=[0.];monkeypatch.setattr(time,'monotonic',lambda:clock[0]);original=s.docker.request
    def delayed(method,path,**kwargs):
        result=original(method,path,**kwargs)
        if method=='POST':clock[0]=30.
        return result
    s.docker.request=delayed
    with pytest.raises(Refused):s.call('retire-chirpstack-for-browser')
    s.docker.request=original
    if change=='source':(s.docker.root/'deploy/lorawan/compose.test.yaml').write_text('changed')
    if change=='identity':s.daemon.containers[s.docker.ids['redis']]['Id']='f'*64
    if change=='mode':s.docker.mode='lifecycle-proof'
    if change=='receipt':
        value=guard.read_private(s.receipt);value['workload_phase']='unknown';guard.persist(s.receipt,value)
    with pytest.raises(Refused):s.recover().cleanup()
    assert s.stored==[1] and 'fdremove' not in s.events
