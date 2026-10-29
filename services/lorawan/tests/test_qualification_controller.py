"""Hermetic controller preparation tests; no units, locks or Docker accessed."""
from pathlib import Path
import json
import pytest
from services.lorawan.tests.qualification_guard import Refused
from services.lorawan.tests import qualification_controller as controller


def test_guardian_unit_has_preexec_stdin_transport_and_original_caps(tmp_path):
    argv=controller.guardian_command(python=Path('/owned/python3.12'),source=tmp_path/'source',
        manifest=tmp_path/'manifest.json',digest='a'*64,root=tmp_path,nonce='b'*32)
    assert argv[:4]==['/usr/bin/sudo','-n','/usr/bin/systemd-run','--system']
    assert '--pipe' in argv and '--collect' not in argv and '--service-type=notify' in argv
    assert '--unit=earthship-sensor-guard-'+ 'b'*32 +'.service' in argv
    properties=[argv[i+1] for i,value in enumerate(argv[:-1]) if value=='--property']
    for value in ['User=sat','Group=sat','SupplementaryGroups=docker','MemoryMax=67108864','MemorySwapMax=0',
                  'TasksMax=16','CPUQuota=50%','FileDescriptorStoreMax=1','FileDescriptorStorePreserve=yes',
                  'Restart=on-failure','TimeoutStopSec=infinity','BindsTo=user-runtime-dir@1000.service',
                  'After=user-runtime-dir@1000.service','RuntimeDirectoryMode=0700','RuntimeDirectoryPreserve=yes']:
        assert value in properties
    assert all('user@1000.service' not in value for value in properties)
    assert '--setenv=PYTHONDONTWRITEBYTECODE=1' in argv
    assert argv[-8:]==['--manifest',str(tmp_path/'manifest.json'),'--sha256','a'*64,'--root',str(tmp_path),'--nonce','b'*32]


def test_creation_intents_are_durable_before_only_create_command(tmp_path):
    seen=[];receipt=tmp_path/'create.json'
    def run(command):
        value=json.loads(receipt.read_text());assert value['phase']=='creating'
        assert value['nonce']=='a'*32 and value['ids']=={}
        assert set(value['intents'])=={'mqtt','postgres','ingest','openhab','redis','chirpstack','simulator'}
        seen.append(command)
    controller.precreate(tmp_path,'a'*32,receipt,run=run)
    assert len(seen)==1
    assert seen[0]==['/snap/bin/docker','compose','-f',str(tmp_path/'deploy/lorawan/compose.test.yaml'),
                     '--profile','*','create','--no-build','--pull','never']
    assert not any(word in seen[0] for word in ['start','up','run','restart','build'])


def test_ambiguous_create_retains_intents_and_never_starts_or_retries(tmp_path):
    calls=[];receipt=tmp_path/'create.json'
    def fail(command):calls.append(command);raise TimeoutError('lost daemon reply')
    with pytest.raises(TimeoutError):controller.precreate(tmp_path,'a'*32,receipt,run=fail)
    assert len(calls)==1 and json.loads(receipt.read_text())['phase']=='creating'
    with pytest.raises(Refused):controller.precreate(tmp_path,'a'*32,receipt,run=fail)
    assert len(calls)==1


@pytest.mark.parametrize('current,other,pids,swap',[(2369*1024**2,False,0,0),(2000*1024**2,True,0,0),(2000*1024**2,False,1,0),(2000*1024**2,False,0,1)])
def test_headroom_refuses_without_original_reserve_and_quiescence(current,other,pids,swap):
    with pytest.raises(Refused):controller.check_budget(residual=current,other_children=other,direct_pids=pids,swap=swap)


def test_headroom_keeps_256_mib_uncertainty_reserve():
    assert controller.check_budget(residual=2368*1024**2,other_children=False,direct_pids=0,swap=0)==256*1024**2


def test_lifetime_probe_uses_two_original_descriptors_before_external_exec(tmp_path):
    calls=[]
    def spawn(argv,**kwargs):calls.append((argv,kwargs));return object()
    controller.launch_lifetime(python=Path('/owned/python3.12'),source=tmp_path/'source',directory=tmp_path,
        nonce='a'*32,real_fd=17,probe_fd=18,log=19,spawn=spawn)
    assert len(calls)==1
    argv,options=calls[0]
    assert options=={'stdin':17,'stdout':18,'stderr':19,'close_fds':True}
    assert 'services.lorawan.tests.qualification_lifetime_probe' in argv
    assert '--pipe' in argv and '-P' in argv
    assert 'FileDescriptorStoreMax=2' in argv and 'FileDescriptorStoreMax=1' not in argv
    assert argv[-4:]==['--directory',str(tmp_path),'--nonce','a'*32]


def test_source_freeze_copies_only_closed_guardian_modules(tmp_path):
    source=tmp_path/'input';source.mkdir()
    for name in ['qualification_guard.py','qualification_runtime.py','stack_ownership.py','qualification_lifetime_probe.py','qualification_controller.py']:
        (source/name).write_text('# '+name+'\n')
    package=tmp_path/'frozen'
    result=controller.freeze_sources(source,package)
    assert set(result)=={'qualification_guard.py','qualification_runtime.py','stack_ownership.py','qualification_lifetime_probe.py','qualification_controller.py'}
    for name,digest in result.items():
        path=package/'services/lorawan/tests'/name
        assert path.read_bytes()==(source/name).read_bytes() and path.stat().st_mode & 0o777==0o400
        assert len(digest)==64
    assert (package/'services/__init__.py').read_bytes()==b''
    with pytest.raises(FileExistsError):controller.freeze_sources(source,package)


def test_preinitialization_probe_has_only_fixed_ten_second_prestart(tmp_path):
    calls=[]
    controller.launch_lifetime(python=Path('/owned/python3.12'),source=tmp_path/'source',directory=tmp_path,
        nonce='a'*32,real_fd=17,probe_fd=18,log=19,preinit_proof=True,
        spawn=lambda argv,**kwargs:calls.append((argv,kwargs)))
    argv,options=calls[0]
    assert argv.count('ExecStartPre=/usr/bin/sleep 10')==1
    index=argv.index('ExecStartPre=/usr/bin/sleep 10')
    assert argv[index-1]=='--property'
    assert options['stdin']==17 and options['stdout']==18


@pytest.mark.parametrize('mode,tasks',[('qualification',8),('lifecycle-proof',16)])
def test_guardian_command_binds_fixed_mode_and_task_cap(tmp_path,mode,tasks):
    argv=controller.guardian_command(python=Path('/owned/python3.12'),source=tmp_path/'source',
        manifest=tmp_path/'manifest.json',digest='a'*64,root=tmp_path,nonce='b'*32,mode=mode)
    properties=[argv[i+1] for i,value in enumerate(argv[:-1]) if value=='--property']
    assert [v for v in properties if v.startswith('TasksMax=')]==['TasksMax='+str(tasks)]
    assert argv[argv.index('--mode')+1]==mode
    assert 'Restart=on-failure' in properties and 'FileDescriptorStorePreserve=yes' in properties


@pytest.mark.parametrize('mode',['other',8,16,None])
def test_guardian_command_refuses_unknown_or_numeric_modes(tmp_path,mode):
    with pytest.raises(Refused):controller.guardian_command(python=Path('/owned/python3.12'),
        source=tmp_path/'source',manifest=tmp_path/'manifest.json',digest='a'*64,
        root=tmp_path,nonce='b'*32,mode=mode)
