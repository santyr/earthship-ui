"""Guarded legacy entrypoint: no original imports or live operations by default."""
from hashlib import sha256
import importlib,json,os,subprocess,sys
from pathlib import Path
import pytest


def module():
    assert importlib.util.find_spec('thermal_legacy_observe') is not None, 'missing guarded legacy entrypoint'
    return importlib.import_module('thermal_legacy_observe')


@pytest.fixture
def config(tmp_path):
    base=tmp_path/'private';base.mkdir(mode=0o700)
    root=base/'sources';root.mkdir(mode=0o700);package=root/'thermal_model';package.mkdir(mode=0o700)
    archive=base/'archive';archive.mkdir(mode=0o700)
    files={'thermal_intel.py':'raise RuntimeError("original must not execute by default")\n',
        'thermal_temperature_runtime.py':'# original native reader\n',
        'thermal_legacy_origin.py':'# independently pinned observer\n',
        'thermal_legacy_observe.py':'# independently pinned entrypoint\n',
        'thermal_model/__init__.py':'',
        'thermal_model/artifacts.py':'MODEL_SCHEMA="earthship-thermal-model/v4"\n',
        'thermal_model/forcing_capture.py':'# original writer\n'}
    for name,body in files.items():
        p=root/name;p.write_text(body);p.chmod(0o600)
    lock=base/'shared.lock';lock.write_text('');lock.chmod(0o600)
    value=dict(schema='earthship-thermal-legacy-observe-config/v1',legacy_root=str(root),
        archive=str(archive),shared_lock=str(lock),source_sha256={name:sha256(body.encode()).hexdigest() for name,body in files.items()})
    path=base/'config.json';path.write_text(json.dumps(value));path.chmod(0o600)
    return path,value


def test_default_checks_private_sources_without_loading_original(config,capsys):
    path,_=config;m=module()
    assert m.main(['--config',str(path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='configuration_verified'
    assert result['live_execution_requested'] is False and result['release_authority'] is False


@pytest.mark.parametrize('damage',['changed_source','extra_module','wrong_hash','escape','public_config','symlink','extra_config','same_archive'])
def test_refuses_unverified_or_insecure_private_configuration(config,damage):
    path,v=config;m=module();root=Path(v['legacy_root'])
    if damage=='changed_source':(root/'thermal_intel.py').write_text('raise RuntimeError("changed")\n')
    elif damage=='extra_module':
        p=root/'unverified.py';p.write_text('');p.chmod(0o600)
    elif damage=='wrong_hash':v['source_sha256']['thermal_intel.py']='0'*64
    elif damage=='escape':v['source_sha256']['../outside.py']='a'*64
    elif damage=='public_config':path.chmod(0o644)
    elif damage=='symlink':
        target=root/'thermal_intel.py';target.unlink();target.symlink_to(root/'thermal_temperature_runtime.py')
    elif damage=='extra_config':v['active']=True
    else:v['archive']=v['legacy_root']
    path.write_text(json.dumps(v))
    with pytest.raises(ValueError):m.load_settings(path)


def test_resource_refusal_never_loads_original(config,monkeypatch,capsys):
    path,_=config;m=module()
    def refused():raise ValueError('private resource detail')
    monkeypatch.setattr(m,'_resource_preflight',refused)
    assert m.main(['--config',str(path),'--observe'])==1
    out=capsys.readouterr();assert 'private resource detail' not in out.out+out.err
    assert json.loads(out.out)['status']=='unverified_failure'


def test_busy_existing_shared_lock_skips_original(config,monkeypatch,capsys):
    import fcntl
    path,v=config;m=module();monkeypatch.setattr(m,'_resource_preflight',lambda:None)
    with open(v['shared_lock'],'r+') as held:
        fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert m.main(['--config',str(path),'--observe'])==75
    assert json.loads(capsys.readouterr().out)['status']=='busy'


def test_default_fresh_process_imports_no_original_or_numerical_dependencies(config):
    path,_=config;m=module()
    script='''import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in ('numpy','scipy','psycopg2','thermal_intel','thermal_model','thermal_legacy_origin'):
   raise AssertionError('unguarded original import')
sys.meta_path.insert(0,Block())
import thermal_legacy_observe as command
raise SystemExit(command.main(['--config',sys.argv[1]]))
'''
    p=subprocess.run([sys.executable,'-c',script,str(path)],capture_output=True,text=True,timeout=10)
    assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)['live_execution_requested'] is False


def test_explicit_observe_calls_only_original_shadow_with_fit_disabled(config,monkeypatch):
    path,v=config;root=Path(v['legacy_root']);stamp=path.parent/'invocation.json'
    original=f'''import json,os
from pathlib import Path
RUNTIME_REVISION_PATHS=('thermal_intel.py',)
def capture_shadow_inputs(*args,**kwargs):pass
def main(argv):
 Path({str(stamp)!r}).write_text(json.dumps(dict(argv=argv,fit=os.environ.get('EARTHSHIP_QUALIFICATION_FIT'),remote_fit=os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT'))))
 return 0
'''
    worker='def configured_shadow_temperatures(*args,**kwargs):pass\n'
    observer='''class LegacyOriginObserver:
 def __init__(self,*args,**kwargs):pass
 def wrap_native(self,reader):return reader
 def wrap_capture(self,writer):return writer
def bind_legacy_runtime(root,paths):raise RuntimeError('unused by this inert original')
'''
    bodies={'thermal_intel.py':original,'thermal_temperature_runtime.py':worker,
        'thermal_legacy_origin.py':observer,'thermal_legacy_observe.py':Path(module().__file__).read_text()}
    for name,body in bodies.items():
        (root/name).write_text(body);v['source_sha256'][name]=sha256(body.encode()).hexdigest()
    path.write_text(json.dumps(v))
    script='''import sys
import thermal_legacy_observe as command
command._resource_preflight=lambda:None
raise SystemExit(command.main(['--config',sys.argv[1],'--observe']))
'''
    env=dict(os.environ,PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1')
    p=subprocess.run([sys.executable,'-c',script,str(path)],env=env,capture_output=True,text=True,timeout=10)
    assert p.returncode==0,p.stderr+p.stdout
    assert json.loads(stamp.read_text())=={'argv':['shadow','--publish'],'fit':'0','remote_fit':'0'}


def test_source_changed_during_preflight_is_refused_before_import(config):
    path,v=config;root=Path(v['legacy_root']);marker=path.parent/'must-not-execute'
    body=Path(module().__file__).read_bytes();(root/'thermal_legacy_observe.py').write_bytes(body)
    v['source_sha256']['thermal_legacy_observe.py']=sha256(body).hexdigest();path.write_text(json.dumps(v))
    script='''import sys
from pathlib import Path
import thermal_legacy_observe as command
def changed():
 Path(sys.argv[2]).write_text('from pathlib import Path\\nPath('+repr(sys.argv[3])+').write_text("unverified code executed")\\n')
command._resource_preflight=changed
raise SystemExit(command.main(['--config',sys.argv[1],'--observe']))
'''
    p=subprocess.run([sys.executable,'-c',script,str(path),str(root/'thermal_intel.py'),str(marker)],
        env=dict(os.environ,PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=10)
    assert p.returncode==1
    assert not marker.exists(), 'unverified original code ran before source reconciliation'


@pytest.fixture
def resources(tmp_path,monkeypatch):
    # This test controls resource metadata, not the CI runner's scheduling.
    monkeypatch.setattr(os,'getpriority',lambda *args:15)
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','PYTHONDONTWRITEBYTECODE'):
        monkeypatch.setenv(name,'1')
    root=tmp_path/'cgroup';leaf=root/'scope';leaf.mkdir(parents=True)
    proc=tmp_path/'proc';(proc/'self').mkdir(parents=True);(proc/'pressure').mkdir()
    (proc/'self/cgroup').write_text('0::/scope\n')
    (proc/'meminfo').write_text('MemAvailable: 2000000 kB\n')
    (proc/'pressure/memory').write_text('some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n')
    for name,value in {'cpu.max':'20000 100000','memory.max':'268435456','memory.swap.max':'0','pids.max':'24','io.weight':'default 10'}.items():
        (leaf/name).write_text(value)
    return root,proc,leaf


def test_resource_caps_accept_strict_metadata(resources):
    root,proc,_=resources;module()._resource_preflight(cgroup_root=root,proc_root=proc)


@pytest.mark.parametrize('damage',['cpu','memory','swap','tasks','io','headroom','pressure','priority','threads','bytecode'])
def test_resource_caps_refuse_relaxed_or_pressured_host(resources,damage,monkeypatch):
    root,proc,leaf=resources
    values={'cpu':('cpu.max','21000 100000'),'memory':('memory.max','268435457'),
        'swap':('memory.swap.max','1'),'tasks':('pids.max','25'),'io':('io.weight','default 11')}
    if damage in values:
        name,value=values[damage];(leaf/name).write_text(value)
    elif damage=='headroom':(proc/'meminfo').write_text('MemAvailable: 1024 kB\n')
    elif damage=='priority':monkeypatch.setattr(os,'getpriority',lambda *args:0)
    elif damage=='threads':monkeypatch.setenv('OMP_NUM_THREADS','2')
    elif damage=='bytecode':monkeypatch.delenv('PYTHONDONTWRITEBYTECODE')
    else:(proc/'pressure/memory').write_text('some avg10=1.00\nfull avg10=0.00\n')
    with pytest.raises(ValueError):module()._resource_preflight(cgroup_root=root,proc_root=proc)
