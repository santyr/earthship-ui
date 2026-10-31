"""Preparation-only tests for the real seven-ID controller; no daemon effects."""
from copy import deepcopy
import errno
from pathlib import Path
import socket
from urllib.parse import unquote
import pytest
from services.lorawan.tests.qualification_guard import Refused
from services.lorawan.tests import qualification_stack_controller as controller
from services.lorawan.tests.test_qualification_runtime import manifest, Daemon


def test_capture_binds_seven_stopped_ids_and_original_metadata(manifest):
    daemon=Daemon(manifest)
    def request(method,path):
        if path.startswith('/images/'):
            return {'Id':manifest['images'][unquote(path[len('/images/'):-len('/json')])]}
        if path.startswith('/containers/earthship-sensors-test-'):
            service=path.split('/')[2].removeprefix('earthship-sensors-test-').removesuffix('-1')
            return manifest['containers'][service]
        return daemon(method,path)
    result=controller.capture_stopped(manifest['root'],manifest['nonce'],manifest['rendered'],request=request)
    assert result==manifest
    assert all(method=='GET' for method,path in daemon.calls)


def test_started_or_foreign_precreated_member_prevents_guardian_handoff(manifest):
    daemon=Daemon(manifest)
    def request(method,path):
        if path.startswith('/images/'):
            return {'Id':manifest['images'][unquote(path[len('/images/'):-len('/json')])]}
        if path.startswith('/containers/earthship-sensors-test-'):
            service=path.split('/')[2].removeprefix('earthship-sensors-test-').removesuffix('-1')
            value=deepcopy(manifest['containers'][service])
            if service=='mqtt':value['State']['Running']=True
            return value
        return daemon(method,path)
    with pytest.raises(Refused):controller.capture_stopped(manifest['root'],manifest['nonce'],manifest['rendered'],request=request)


def test_fixed_budget_profiles_keep_original_total_and_uncertainty():
    assert controller.profile('lifecycle-proof')=={'controller_mib':1024,'controller_tasks':96,'external_mib':128,'services':('mqtt',)}
    full=controller.profile('qualification')
    assert full['controller_mib']==512 and full['external_mib']==2112
    assert full['services']==('mqtt','postgres','redis','openhab','chirpstack','ingest')
    with pytest.raises(Refused):controller.profile('unbounded')


@pytest.fixture
def port_bindings(monkeypatch):
    """Only the kernel bind boundary is replaced; no host ports are touched."""
    probes=[];unavailable={}
    class Probe:
        def __init__(self,family,kind):
            assert (family,kind)==(socket.AF_INET,socket.SOCK_STREAM)
            self.address=None;self.timeout=None;self.closed=False;probes.append(self)
        def __enter__(self):return self
        def __exit__(self,*_):self.closed=True
        def settimeout(self,value):self.timeout=value
        def bind(self,address):
            self.address=address
            if address in unavailable:raise OSError(unavailable[address],'fixture port unavailable')
    monkeypatch.setattr(controller.socket,'socket',Probe)
    return probes,unavailable


@pytest.fixture
def precreate_fixture(manifest,port_bindings):
    root=Path(manifest['root']);private=root/'.superpowers/lorawan-private';private.mkdir(parents=True,mode=0o700)
    for spec in manifest['rendered']['services'].values():
        for mount in spec.get('volumes',[]):
            if mount['type']=='bind':
                path=Path(mount['source']);path.parent.mkdir(parents=True,exist_ok=True);path.touch()
    daemon=Daemon(manifest);calls=[]
    def request(method,path):
        calls.append((method,path));assert method=='GET'
        if path=='/containers/json?all=1':return []
        if path=='/networks':return [daemon(method,'/networks/'+name) for name in manifest['networks']]
        if path.startswith('/images/'):
            return {'Id':manifest['images'][unquote(path[len('/images/'):-len('/json')])]}
        return daemon(method,path)
    return manifest,request,calls


@pytest.mark.parametrize('representation',[int,str])
def test_precreate_accepts_rendered_memory_formats(precreate_fixture,representation):
    manifest,request,calls=precreate_fixture
    for spec in manifest['rendered']['services'].values():
        for key in ('mem_limit','memswap_limit'):spec[key]=representation(spec[key])
    assert controller.precreate_inventory(manifest['root'],manifest['nonce'],manifest['rendered'],request)==[]
    assert calls and all(method=='GET' for method,_ in calls)


@pytest.mark.parametrize('field',['mem_limit','memswap_limit'])
@pytest.mark.parametrize('value',['067108864',67108864.0,True,'67108865','9223372036854775808'])
def test_precreate_rejects_ambiguous_rendered_memory(precreate_fixture,field,value):
    manifest,request,calls=precreate_fixture
    manifest['rendered']['services']['mqtt'][field]=value
    with pytest.raises(Refused):controller.precreate_inventory(manifest['root'],manifest['nonce'],manifest['rendered'],request)
    assert all(method=='GET' for method,_ in calls)


def test_precreate_checks_every_declared_loopback_tcp_port(precreate_fixture,port_bindings):
    manifest,request,_=precreate_fixture;probes,_=port_bindings
    assert controller.precreate_inventory(manifest['root'],manifest['nonce'],manifest['rendered'],request)==[]
    assert [probe.address for probe in probes]==[('127.0.0.1',18884),('127.0.0.1',18084),('127.0.0.1',28085)]
    assert all(probe.closed and probe.timeout==1 for probe in probes)


@pytest.mark.parametrize('port',[18884,18084,28085])
@pytest.mark.parametrize('error',[errno.EADDRINUSE,errno.EACCES])
def test_precreate_unavailable_tcp_port_refuses_before_create_intents(precreate_fixture,port_bindings,port,error):
    manifest,request,calls=precreate_fixture;probes,unavailable=port_bindings
    unavailable[('127.0.0.1',port)]=error
    receipt=Path(manifest['root'])/'create-intents.json';mutations=[]
    with pytest.raises(Refused,match='loopback TCP test port unavailable'):
        controller.precreate_inventory(manifest['root'],manifest['nonce'],manifest['rendered'],request)
        controller.precreate(manifest['root'],manifest['nonce'],receipt,run=mutations.append)
    assert not receipt.exists() and mutations==[]
    assert probes[-1].address==('127.0.0.1',port) and all(probe.closed for probe in probes)
    assert all(method=='GET' for method,_ in calls)


@pytest.mark.parametrize('mode,tasks',[('qualification',64),('lifecycle-proof',96)])
def test_controller_accepts_only_its_mode_task_allocation(tmp_path,mode,tasks):
    scope=tmp_path/'pool/scope';scope.mkdir(parents=True);pool=scope.parent
    for name,value in [('memory.max',str((512 if mode=='qualification' else 1024)*1024**2)),
                       ('memory.swap.max','0'),('pids.max',str(tasks))]:
        (scope/name).write_text(value+'\n')
    for name,value in [('memory.max','6442450944'),('memory.swap.max','0'),
                       ('pids.max','256'),('cpu.max','800000 100000')]:
        (pool/name).write_text(value+'\n')
    controller.verify_controller_caps(scope,pool,mode)


@pytest.mark.parametrize('mode,tasks',[('qualification',96),('lifecycle-proof',64),
                                      ('qualification',80),('lifecycle-proof',80)])
def test_controller_refuses_wrong_mode_or_changed_task_allocation(tmp_path,mode,tasks):
    scope=tmp_path/'pool/scope';scope.mkdir(parents=True);pool=scope.parent
    for name,value in [('memory.max',str((512 if mode=='qualification' else 1024)*1024**2)),
                       ('memory.swap.max','0'),('pids.max',str(tasks))]:
        (scope/name).write_text(value+'\n')
    for name,value in [('memory.max','6442450944'),('memory.swap.max','0'),
                       ('pids.max','256'),('cpu.max','800000 100000')]:
        (pool/name).write_text(value+'\n')
    with pytest.raises(Refused):controller.verify_controller_caps(scope,pool,mode)


@pytest.mark.parametrize('change',['ten','twelve','skipped','errors','failures','nonzero','live','empty','missing','malformed','incomplete'])
def test_python_gate_forbids_phase_effects_without_eleven_completed_passes(tmp_path,change):
    from types import SimpleNamespace
    count=10 if change=='ten' else 12 if change=='twelve' else 11
    xml=tmp_path/'python.xml'
    xml.write_text('<testsuites><testsuite tests="'+str(count)+'" failures="'+('1' if change=='failures' else '0')+
        '" errors="'+('1' if change=='errors' else '0')+'" skipped="'+('1' if change=='skipped' else '0')+'">'+
        ''.join('<testcase classname="integration" name="case'+str(i)+'" />' for i in range(count))+'</testsuite></testsuites>')
    if change=='empty':xml.write_text('<testsuites />')
    if change=='missing':xml.unlink()
    if change=='malformed':xml.write_text('<testsuites>')
    if change=='incomplete':xml.write_text('<testsuite tests="11" failures="0" errors="0" skipped="0" />')
    status=None if change=='live' else 1 if change=='nonzero' else 0
    child=SimpleNamespace(poll=lambda:status,returncode=status);effects=[]
    with pytest.raises((Refused,OSError,__import__('xml.etree.ElementTree',fromlist=['ParseError']).ParseError)):
        controller.enter_browser_phase(child,xml,request=lambda operation:effects.append(operation),restore=lambda:effects.append('restore'))
    assert effects==[]


def test_python_phase_driver_requires_each_exact_ack_before_next_effect(tmp_path):
    from types import SimpleNamespace
    xml=tmp_path/'python.xml';xml.write_text('<testsuite tests="11" failures="0" errors="0" skipped="0">'+
        ''.join('<testcase name="case'+str(i)+'" />' for i in range(11))+'</testsuite>')
    child=SimpleNamespace(poll=lambda:0,returncode=0)
    expected=[('retire-chirpstack-for-browser',{'workload_phase':'chirpstack-retired'}),
              ('retire-redis-for-browser',{'workload_phase':'browser-ready'}),
              ('enter-browser',{'workload_phase':'browser'})]
    for refused in range(3):
        events=[]
        def request(operation):
            index=sum(isinstance(e,tuple) for e in events);assert operation==expected[index][0]
            events.append(('request',operation))
            return {'workload_phase':'python'} if index==refused else expected[index][1]
        with pytest.raises(Refused):controller.enter_browser_phase(child,xml,request=request,restore=lambda:events.append('restore'))
        assert sum(isinstance(e,tuple) for e in events)==refused+1
        assert ('restore' in events)==(refused==2)


def test_closed_phase_arithmetic_rejects_unretired_browser_combination():
    # These independent reservations include all7 IDs and the observer reserve.
    from services.lorawan.tests.stack_ownership import CAPS
    assert sum(v[0] for v in CAPS.values())+512+64==2624
    assert sum(v[1] for v in CAPS.values())+2+.5==8
    assert sum(v[2] for v in CAPS.values())==192
    assert 48+8+192==248 and 64+8+176==248
    assert 64+8+192==264 and 248+8==256
    assert 6144-2624-256==3264 and 3072+2624==5696


@pytest.mark.parametrize('change',[None,'wrong-admission','set-failed','kernel-not-narrowed','manager-not-narrowed'])
def test_exact_admission_narrowing_completes_before_external_effects(tmp_path,monkeypatch,change):
    from services.lorawan.tests.test_qualification_runtime import controller_files
    # Exercise the real context validator using a complete independent scope.
    from services.lorawan.tests import qualification_runtime as runtime
    import subprocess
    record,proc,cg,scope=controller_files.__wrapped__(tmp_path);tasks=['64'];effects=[]
    for name,value in [('memory.max','536870912'),('memory.swap.max','0'),('pids.max','64'),('cpu.max','200000 100000')]:
        (scope/name).write_text(value)
    for name,value in [('memory.max','6442450944'),('memory.swap.max','0'),('pids.max','256'),('cpu.max','800000 100000')]:
        (scope.parent/name).write_text(value)
    def show(argv,**kwargs):
        assert argv==['/usr/bin/systemctl','--user','show','-p','InvocationID','-p','ControlGroup','-p','TasksMax',record['unit']]
        return 'InvocationID='+record['invocation']+'\nControlGroup='+record['cgroup']+'\nTasksMax='+tasks[0]+'\n'
    def narrow(argv,**kwargs):
        assert argv==['/usr/bin/systemctl','--user','set-property','--runtime',record['unit'],'TasksMax=48']
        effects.append('narrow')
        if change=='set-failed':raise subprocess.CalledProcessError(1,argv)
        if change!='kernel-not-narrowed':(scope/'pids.max').write_text('48')
        if change!='manager-not-narrowed':tasks[0]='48'
    monkeypatch.setattr(subprocess,'check_output',show);monkeypatch.setattr(subprocess,'run',narrow)
    if change=='wrong-admission':(scope/'pids.max').write_text('48')
    actor=runtime.Controller(record,proc_root=proc,cgroup_root=cg)
    def prepare():controller.prepare_python_controller(actor);effects.append('external-start')
    if change:
        with pytest.raises((Refused,subprocess.CalledProcessError)):prepare()
        assert 'external-start' not in effects
    else:prepare();assert effects==['narrow','external-start']


@pytest.mark.parametrize('change',[None,'memory','pids','pool-memory','pool-pids','reset','malformed'])
def test_phase_resource_gate_requires_unchanged_controller_and_pool_events(tmp_path,change):
    scope=tmp_path/'pool/scope';scope.mkdir(parents=True);pool=scope.parent
    memory='low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n';pids='max 0\n'
    baseline={'memory_events':memory,'pids_events':pids,'pool_events':memory,'pool_pids_events':'max 2\n'}
    for path,value in [(scope/'memory.events',memory),(scope/'pids.events',pids),(pool/'memory.events',memory),(pool/'pids.events','max 2\n')]:path.write_text(value)
    if change=='memory':(scope/'memory.events').write_text(memory.replace('high 0','high 1'))
    if change=='pids':(scope/'pids.events').write_text('max 1\n')
    if change=='pool-memory':(pool/'memory.events').write_text(memory.replace('max 0','max 1'))
    if change=='pool-pids':(pool/'pids.events').write_text('max 3\n')
    if change=='reset':(pool/'pids.events').write_text('max 0\n')
    if change=='malformed':(scope/'memory.events').write_text('max 0\nmax 0\n')
    if change:
        with pytest.raises(Refused):controller.verify_resource_events(scope,pool,baseline)
    else:controller.verify_resource_events(scope,pool,baseline)
