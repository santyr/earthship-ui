"""Native prep command must preserve original lock, source and pressure boundaries."""
import importlib,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest


def api():return importlib.import_module('household_native_geometry_prepare')


def fixture(tmp_path,monkeypatch):
    module=api()
    import native_thermal_live as native
    from astro_geometry_worker import ROLES
    import native_inference_pressure as pressure
    now=[datetime(2026,10,13,14,2,15,tzinfo=timezone.utc)];ticks=[100.];calls=[]
    settings={'schema':native.LIVE_SCHEMA,'shared_lock':str(tmp_path/'lock'),'artifact_sha256':'a'*64,'runtime_sha256':'b'*64}
    lock=Path(settings['shared_lock']);lock.write_text('');lock.chmod(0o600)
    config=tmp_path/'config.json';config.write_text(json.dumps(settings));config.chmod(0o600)
    paths={role:str(tmp_path/(role+'.jar')) for role in ROLES}
    libraries=tmp_path/'libraries.json';libraries.write_text(json.dumps({'schema':'earthship-native-geometry-libraries/v1','library_paths':paths}));libraries.chmod(0o600)
    monkeypatch.setattr(native,'load_settings',lambda path:settings)
    monkeypatch.setattr(native,'_resource_preflight',lambda:calls.append('caps'))
    class Headroom:
        def __init__(self,**kw):assert not kw
        def preflight(self):calls.append('quiet_preflight')
        def check(self):calls.append('pressure')
    monkeypatch.setattr(pressure,'NativeInferenceHeadroom',Headroom)
    def prepare(actual,*,issue,library_paths,guard):
        guard();assert actual==settings and issue==now[0].replace(minute=5);assert library_paths=={k:Path(v) for k,v in paths.items()}
        assert Path(settings['shared_lock']).is_file()
        return {'status':'prepared','geometry_series_sha256':'c'*64,'automatic_actuation':False}
    monkeypatch.setattr(native,'prepare_geometry',prepare)
    return module,config,libraries,settings,now,ticks,calls


def test_command_prepares_native_geometry_under_original_lock_and_pressure_guard(tmp_path,monkeypatch):
    m,c,l,s,now,ticks,calls=fixture(tmp_path,monkeypatch)
    result=m.run(c,l,clock=lambda:now[0],monotonic=lambda:ticks[0])
    assert result['status']=='prepared' and 'quiet_preflight' in calls and 'pressure' in calls
    from thermal_model.capture_guard import SharedScoreLock
    with SharedScoreLock(s['shared_lock']) as lock:lock.verify()


@pytest.mark.parametrize('left',[119,90,20])
def test_command_reserves_issuance_window_before_taking_lock(tmp_path,monkeypatch,left):
    m,c,l,s,now,ticks,calls=fixture(tmp_path,monkeypatch)
    now[0]=now[0].replace(minute=5)-timedelta(seconds=left)
    import native_thermal_live as native
    monkeypatch.setattr(native,'prepare_geometry',lambda *a,**k:pytest.fail('reserved window entered'))
    import thermal_model.capture_guard as locks
    monkeypatch.setattr(locks,'SharedScoreLock',lambda *a:pytest.fail('reserved window took shared lock'))
    with pytest.raises(BlockingIOError):m.run(c,l,clock=lambda:now[0],monotonic=lambda:ticks[0])
    assert 'quiet_preflight' not in calls


@pytest.mark.parametrize('changed',['config','libraries','deadline','cutoff'])
def test_command_refuses_input_drift_or_elapsed_deadline(tmp_path,monkeypatch,changed):
    m,c,l,s,now,ticks,calls=fixture(tmp_path,monkeypatch)
    import native_thermal_live as native
    def prepare(*a,guard,**kw):
        guard()
        if changed in ('config','libraries'):(c if changed=='config' else l).write_text('{}')
        elif changed=='deadline':ticks[0]+=76
        else:now[0]=now[0].replace(minute=5)-timedelta(seconds=34)
        guard();pytest.fail('changed original or deadline accepted')
    monkeypatch.setattr(native,'prepare_geometry',prepare)
    with pytest.raises(ValueError):m.run(c,l,clock=lambda:now[0],monotonic=lambda:ticks[0])


@pytest.mark.parametrize('damage',['schema','extra','roles','relative','symlink'])
def test_library_configuration_is_closed_owned_and_resolved(tmp_path,monkeypatch,damage):
    m,c,l,s,now,ticks,calls=fixture(tmp_path,monkeypatch)
    value=json.loads(l.read_text())
    if damage=='schema':value['schema']='other'
    elif damage=='extra':value['publish_url']='unapproved'
    elif damage=='roles':value['library_paths'].pop(next(iter(value['library_paths'])))
    elif damage=='relative':value['library_paths'][next(iter(value['library_paths']))]='relative.jar'
    else:
        old=l;l=tmp_path/'link.json';l.symlink_to(old)
    if damage!='symlink':l.write_text(json.dumps(value))
    with pytest.raises((ValueError,OSError)):m.run(c,l,clock=lambda:now[0],monotonic=lambda:ticks[0])


def test_pressure_refusal_cannot_enter_preparation(tmp_path,monkeypatch):
    m,c,l,s,now,ticks,calls=fixture(tmp_path,monkeypatch)
    import native_thermal_live as native
    import native_inference_pressure as pressure
    class Headroom:
        def __init__(self,**kw):pass
        def preflight(self):raise ValueError('host pressure unavailable')
    monkeypatch.setattr(pressure,'NativeInferenceHeadroom',Headroom)
    monkeypatch.setattr(native,'prepare_geometry',lambda *a,**k:pytest.fail('pressure refusal bypassed'))
    with pytest.raises(ValueError,match='host pressure unavailable'):m.run(c,l,clock=lambda:now[0],monotonic=lambda:ticks[0])


def test_cli_failure_does_not_print_private_configuration(tmp_path,monkeypatch,capsys):
    m=api()
    def broken(*a,**kw):raise ValueError('private diagnostic fixture text')
    monkeypatch.setattr(m,'run',broken)
    assert m.main(['--config',str(tmp_path/'c'),'--libraries',str(tmp_path/'l')])==1
    value=json.loads(capsys.readouterr().out)
    assert value=={'status':'geometry_withheld','fit_executed':False,'automatic_actuation':False}


def test_stage_option_refuses_execution_from_an_unsealed_source_path(tmp_path,monkeypatch):
    m,c,l,s,now,ticks,calls=fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    import native_thermal_live as native
    stage=tmp_path/'stage';stage.mkdir(mode=0o700)
    monkeypatch.setattr(deploy,'verify_stage',lambda actual:{'source_manifest':{}})
    monkeypatch.setattr(native,'prepare_geometry',lambda *a,**k:pytest.fail('unsealed stage entry accepted'))
    with pytest.raises(ValueError,match='staged'):
        m.run(c,l,stage=stage,clock=lambda:now[0],monotonic=lambda:ticks[0])


def source_guard_fixture(tmp_path):
    import household_native_geometry_prepare as api
    paths=[tmp_path/name for name in ('config.json','libraries.json','prepare.py')]
    for path in paths:path.write_bytes(b'original bytes');path.chmod(0o600)
    return api,paths


def test_source_guard_reuses_parsed_paths_without_caching_bytes(tmp_path,monkeypatch):
    from pathlib import Path
    api,paths=source_guard_fixture(tmp_path);guard=api._SourceGuard(*paths)
    calls=[];resolve=Path.resolve
    def tracked(path,*args,**kwargs):calls.append(str(path));return resolve(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',tracked);guard.check();assert calls==[]
    paths[0].write_bytes(b'changed bytes!')
    with pytest.raises(ValueError):guard.check()


@pytest.mark.parametrize('index',[0,1,2])
def test_source_guard_refuses_same_size_bytes_even_with_restored_mtime(tmp_path,index):
    import os
    api,paths=source_guard_fixture(tmp_path);guard=api._SourceGuard(*paths);path=paths[index];before=path.stat()
    path.write_bytes(b'changed bytes!');os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
    with pytest.raises(ValueError):guard.check()


def test_source_guard_refuses_parent_symlink_after_initial_normal_path(tmp_path):
    api,paths=source_guard_fixture(tmp_path);guard=api._SourceGuard(*paths)
    saved=tmp_path.with_name(tmp_path.name+'-saved');tmp_path.rename(saved);tmp_path.symlink_to(saved,target_is_directory=True)
    with pytest.raises(ValueError):guard.check()


@pytest.mark.parametrize('damage',['mode','hardlink','replacement'])
def test_source_guard_refuses_changed_private_file_identity_or_permissions(tmp_path,damage):
    import os
    api,paths=source_guard_fixture(tmp_path);guard=api._SourceGuard(*paths);path=paths[0]
    if damage=='mode':path.chmod(0o640)
    elif damage=='hardlink':os.link(path,tmp_path/'linked.json')
    else:
        path.rename(tmp_path/'saved.json');path.write_bytes(b'original bytes');path.chmod(0o600)
    with pytest.raises(ValueError):guard.check()
