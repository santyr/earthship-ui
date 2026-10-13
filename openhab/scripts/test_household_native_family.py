"""Private coherent family drafts; no unit installation or model selection."""
import importlib,json
from pathlib import Path
import pytest
from test_native_household_deploy import native_fixture
from test_household_cycle_deploy import api as deployment,encode,write


def api():return importlib.import_module('household_native_family')


def fixture(tmp_path,monkeypatch):
    args,files,candidate,settings=native_fixture(tmp_path)
    import astro_geometry_worker as worker
    geometry=Path(candidate['originals']['geometry']['path'])
    native_runtime={'binding_version':'5.2.3','libraries':{role:'a'*64 for role in worker.ROLES},'collector_sha256':'b'*64}
    write(geometry,encode({'native_runtime':native_runtime}))
    from hashlib import sha256
    candidate['originals']['geometry']['sha256']=sha256(geometry.read_bytes()).hexdigest()
    from native_thermal_artifact import digest
    candidate['artifact_sha256']=digest(candidate,'artifact_sha256');settings['artifact_sha256']=candidate['artifact_sha256']
    write(Path(settings['candidate_path']),encode(candidate));write(args['forecast_config'],encode(settings))
    deployment().stage_deployment(**args);record=deployment().verify_stage(args['stage'])
    paths={role:str(tmp_path/(role+'.jar')) for role in worker.ROLES}
    libraries=tmp_path/'libraries.json';write(libraries,encode({'schema':'earthship-native-geometry-libraries/v1','library_paths':paths}))
    monkeypatch.setattr(worker,'runtime_identity',lambda actual,**kw:native_runtime if actual=={key:Path(value) for key,value in paths.items()} else pytest.fail('wrong native libraries'))
    return api(),args,settings,record,libraries,tmp_path/'family'


def test_private_draft_uses_one_stage_config_and_nonoverlapping_bounded_clocks(tmp_path,monkeypatch):
    m,args,settings,record,libraries,out=fixture(tmp_path,monkeypatch)
    result=m.prepare(args['stage'],libraries,out,guard=lambda:None)
    assert result['status']=='native_family_staged' and result['live_units_changed'] is False
    assert (out/'forecast.conf').read_bytes()==(args['stage']/'service.conf').read_bytes()
    import shlex
    def unit(name):
        text=(out/name).read_text();rows={}
        for line in text.splitlines():
            if '=' in line:
                key,value=line.split('=',1);rows.setdefault(key,[]).append(value)
        return rows
    prep=unit('thermal-native-geometry-prepare.service');timer=unit('thermal-native-geometry-prepare.timer');score=unit('score.conf')
    for key,value in {'TimeoutStartSec':'90','CPUQuota':'20%','MemoryMax':'256M','MemorySwapMax':'0','TasksMax':'24','Nice':'15','IOSchedulingClass':'idle','IOWeight':'10'}.items():assert prep[key]==[value]
    prep_command=shlex.split(prep['ExecStart'][0]);score_command=shlex.split(score['ExecStart'][-1])
    for command in (prep_command,score_command):
        assert command[0]=='/usr/bin/python3'
        assert command[command.index('--config')+1]==str(args['forecast_config'])
        assert command[command.index('--stage')+1]==str(args['stage'])
    assert prep_command[prep_command.index('--libraries')+1]==str(libraries)
    assert timer['OnCalendar']==['*-*-* *:03/5:05 UTC']
    assert unit('score-timer.conf')['OnCalendar']==['','*-*-* *:01/5:00 UTC','*-*-* *:02/5:00 UTC']
    # Latest score starts at120s and ends by180s; prep starts185s,
    # ends by275s; the unchanged forecast warm slot is285s.
    assert 120+60<185 and 185+90<285
    assert all(path.stat().st_mode&0o777==0o600 for path in out.iterdir() if path.is_file())
    saved=json.loads((out/'family.json').read_bytes())
    assert saved['artifact_sha256']==settings['artifact_sha256'] and saved['runtime_sha256']==settings['runtime_sha256']
    assert saved['automatic_actuation'] is False


def test_draft_refuses_library_identity_change(tmp_path,monkeypatch):
    m,args,settings,record,libraries,out=fixture(tmp_path,monkeypatch)
    import astro_geometry_worker as worker
    monkeypatch.setattr(worker,'runtime_identity',lambda *a,**k:{'binding_version':'unqualified'})
    with pytest.raises(ValueError):m.prepare(args['stage'],libraries,out,guard=lambda:None)
    assert not out.exists()


def test_draft_refuses_legacy_stage_and_existing_output(tmp_path,monkeypatch):
    m,args,settings,record,libraries,out=fixture(tmp_path,monkeypatch)
    record['schema']='earthship-household-cycle-deployment/v1'
    monkeypatch.setattr(deployment(),'verify_stage',lambda stage:record)
    with pytest.raises(ValueError):m.prepare(args['stage'],libraries,out,guard=lambda:None)
    assert not out.exists()


def test_draft_refuses_source_drift_before_creating_output(tmp_path,monkeypatch):
    m,args,settings,record,libraries,out=fixture(tmp_path,monkeypatch)
    calls=[]
    def guard():
        calls.append(1)
        if len(calls)==2:libraries.write_text('{}')
    with pytest.raises(ValueError):m.prepare(args['stage'],libraries,out,guard=guard)
    assert not out.exists()


def test_independent_family_verification_reads_original_stage_and_library_pins(tmp_path,monkeypatch):
    m,args,settings,record,libraries,out=fixture(tmp_path,monkeypatch)
    m.prepare(args['stage'],libraries,out,guard=lambda:None)
    checked=m.verify(out,guard=lambda:None)
    assert checked['artifact_sha256']==settings['artifact_sha256']
    assert checked['runtime_sha256']==settings['runtime_sha256']
    assert checked['live_units_changed'] is False and checked['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['memory','timer','model','extra_file','library_config'])
def test_family_verifier_refuses_resealed_unsafe_or_unbound_drafts(tmp_path,monkeypatch,damage):
    m,args,settings,record,libraries,out=fixture(tmp_path,monkeypatch)
    m.prepare(args['stage'],libraries,out,guard=lambda:None)
    from hashlib import sha256
    meta=json.loads((out/'family.json').read_bytes())
    if damage in ('memory','timer'):
        name='thermal-native-geometry-prepare.service' if damage=='memory' else 'score-timer.conf'
        path=out/name;text=path.read_text()
        text=text.replace('MemoryMax=256M','MemoryMax=2G') if damage=='memory' else text.replace('*:02/5:00','*:03/5:10')
        path.write_text(text);meta['file_sha256'][name]=sha256(path.read_bytes()).hexdigest()
    elif damage=='model':meta['artifact_sha256']='f'*64
    elif damage=='extra_file':write(out/'unexpected.conf',b'unbound')
    else:libraries.write_text('{}')
    write(out/'family.json',encode(meta))
    with pytest.raises((ValueError,OSError)):m.verify(out,guard=lambda:None)
