"""Deployment package integrity; these tests do not qualify a fitted model."""
import importlib,json,subprocess
from pathlib import Path
from hashlib import sha256
import pytest


def api():return importlib.import_module('household_cycle_deploy')
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def write(path,raw,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(mode)


def fixture(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    files={'openhab/scripts/provisional_thermal.py':b'original publisher\n','openhab/scripts/thermal_model/provisional_live.py':b'original runtime\n',
        'openhab/scripts/household_cycle.py':b'observer\n','openhab/scripts/household_cycle_deploy.py':b'installer\n',
        'openhab/managed-resources.json':b'{}','openhab/file-config/ownership.json':b'{}'}
    for name,raw in files.items():write(repo/name,raw,0o644)
    for args in (['init','-q'],['add','.'],['-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture']):
        subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
    revision=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    original=tmp_path/'original';original.mkdir(mode=0o700)
    candidate=original/'candidate.json';write(candidate,encode({'runtime':{'source_manifest':{name.removeprefix('openhab/scripts/'):sha256(raw).hexdigest() for name,raw in files.items() if 'provisional_' in name}}}))
    config=original/'forecast.json';write(config,encode({'candidate_path':str(candidate)}))
    params=original/'params.json';write(params,b'{"original":"retained"}')
    cache_parent=tmp_path/'cache';cache_parent.mkdir(mode=0o700)
    unit=tmp_path/'thermal-provisional-forecast.service'
    body=f'[Service]\nExecStart=/usr/bin/python3 /original/provisional_thermal.py --config {config} --publish\n'
    body+='TimeoutStartSec=90\nCPUQuota=20%\nMemoryMax=256M\nMemorySwapMax=0\nTasksMax=24\nNice=15\nIOSchedulingClass=idle\nIOWeight=10\n'
    write(unit,body.encode(),0o644)
    return dict(repo_root=repo,stage=tmp_path/'stage',forecast_config=config,parameters=params,parameters_sha256=sha256(params.read_bytes()).hexdigest(),
        observation_cache=cache_parent/'observation.json',service_file=unit,code_revision=revision),files


def test_stage_preserves_core_and_registry_layout_with_private_configuration(tmp_path):
    args,files=fixture(tmp_path)
    result=api().stage_deployment(**args)
    assert result['status']=='deployment_staged'
    assert api().verify_stage(args['stage'])['code_revision']==args['code_revision']
    for name,raw in files.items():assert (args['stage']/'sources'/name).read_bytes()==raw
    assert (args['stage']/'cycle.json').stat().st_mode & 0o777==0o600
    assert (args['stage']/'evidence').stat().st_mode & 0o777==0o700
    dropin=(args['stage']/'service.conf').read_text()
    assert 'ExecStart=\nExecStart=/usr/bin/python3 ' in dropin
    assert '/sources/openhab/scripts/household_cycle.py' in dropin
    assert '--code-revision '+args['code_revision'] in dropin


def test_new_candidate_config_preserves_original_service_and_binds_both_configs(tmp_path):
    args,_=fixture(tmp_path);baseline=args['forecast_config'];old=json.loads(baseline.read_bytes())
    candidate=baseline.parent/'next-candidate.json';write(candidate,Path(old['candidate_path']).read_bytes())
    config=baseline.parent/'next-forecast.json';write(config,encode({**old,'candidate_path':str(candidate)}))
    unit=args['service_file'].read_bytes();args.update(forecast_config=config,service_forecast_config=baseline)
    api().stage_deployment(**args);record=api().verify_stage(args['stage'])
    assert str(config) in record['original_bindings'] and str(baseline) in record['original_bindings']
    assert args['service_file'].read_bytes()==unit
    assert json.loads((args['stage']/'cycle.json').read_bytes())['forecast_config']==str(config)


def test_candidate_selection_cannot_change_existing_source_settings(tmp_path):
    args,_=fixture(tmp_path);baseline=args['forecast_config'];old=json.loads(baseline.read_bytes())
    config=baseline.parent/'next-forecast.json';write(config,encode({**old,'openhab_base':'different'}))
    args.update(forecast_config=config,service_forecast_config=baseline)
    with pytest.raises(ValueError):api().stage_deployment(**args)
    assert not args['stage'].exists()

@pytest.mark.parametrize('damage',['dirty','core','parameters','weak_limits','symlink'])
def test_bad_sources_refuse_before_creating_package(damage,tmp_path):
    args,_=fixture(tmp_path);repo=args['repo_root']
    if damage in ('dirty','core'):
        write(repo/'openhab/scripts/provisional_thermal.py',b'changed\n',0o644)
        if damage=='core':
            subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qam','changed'],check=True,capture_output=True)
            args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if damage=='parameters':args['parameters'].write_bytes(b'{}')
    if damage=='weak_limits':args['service_file'].write_text(args['service_file'].read_text().replace('MemoryMax=256M','MemoryMax=2G'))
    if damage=='symlink':
        source=repo/'openhab/scripts/household_cycle.py';source.unlink();source.symlink_to(args['parameters'])
        subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qam','symlink'],check=True,capture_output=True)
        args['code_revision']=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    with pytest.raises(ValueError):api().stage_deployment(**args)
    assert not args['stage'].exists()

@pytest.mark.parametrize('damage',['source','extra_source','unit','config','parameters'])
def test_changed_package_or_live_original_refuses_verification(damage,tmp_path):
    args,_=fixture(tmp_path);api().stage_deployment(**args)
    if damage=='source':(args['stage']/'sources/openhab/scripts/provisional_thermal.py').write_bytes(b'changed')
    if damage=='extra_source':write(args['stage']/'sources/openhab/scripts/household/injected.py',b'pass',0o644)
    if damage=='unit':args['service_file'].write_bytes(b'changed')
    if damage=='config':args['forecast_config'].write_bytes(b'{}')
    if damage=='parameters':args['parameters'].write_bytes(b'{}')
    with pytest.raises(ValueError):api().verify_stage(args['stage'])


def apply_fixture(tmp_path,monkeypatch):
    args,_=fixture(tmp_path);api().stage_deployment(**args);calls=[]
    monkeypatch.setattr(api(),'_qualify',lambda stage:calls.append('qualified'),raising=False)
    def state(service):
        dropin=service.parent/(service.name+'.d')/'zzzz-household-cycle.conf'
        command=str(args['stage']/'sources/openhab/scripts/household_cycle.py') if dropin.exists() else '/original/provisional_thermal.py --config '+str(args['forecast_config'])+' --publish'
        return dict(ActiveState='inactive',MainPID='0',ExecStart=command,CPUQuotaPerSecUSec='200ms',MemoryMax='268435456',MemorySwapMax='0',TasksMax='24',Nice='15',IOSchedulingClass='3',IOWeight='10')
    monkeypatch.setattr(api(),'_service_state',state,raising=False)
    monkeypatch.setattr(api(),'_systemctl',lambda *args:calls.append(args),raising=False)
    return args,calls


def test_handoff_changes_only_override_and_reload_not_running_service(tmp_path,monkeypatch):
    args,calls=apply_fixture(tmp_path,monkeypatch)
    original=args['service_file'].read_bytes()
    result=api().apply_stage(args['stage'])
    assert result['status']=='deployment_installed'
    assert calls==['qualified',('daemon-reload',)]
    assert args['service_file'].read_bytes()==original
    target=args['service_file'].parent/(args['service_file'].name+'.d')/'zzzz-household-cycle.conf'
    assert target.read_bytes()==(args['stage']/'service.conf').read_bytes()


def test_runtime_qualification_failure_never_changes_service(tmp_path,monkeypatch):
    args,calls=apply_fixture(tmp_path,monkeypatch)
    def refused(stage):raise ValueError('runtime differs')
    monkeypatch.setattr(api(),'_qualify',refused)
    with pytest.raises(ValueError):api().apply_stage(args['stage'])
    assert calls==[]
    assert not (args['service_file'].parent/(args['service_file'].name+'.d')).exists()


def test_source_change_during_qualification_refuses_handoff(tmp_path,monkeypatch):
    args,calls=apply_fixture(tmp_path,monkeypatch)
    def drift(stage):(stage/'sources/openhab/scripts/household_cycle.py').write_bytes(b'changed')
    monkeypatch.setattr(api(),'_qualify',drift)
    with pytest.raises(ValueError):api().apply_stage(args['stage'])
    assert calls==[]
    assert not (args['service_file'].parent/(args['service_file'].name+'.d')).exists()


def test_active_original_worker_prevents_handoff(tmp_path,monkeypatch):
    args,calls=apply_fixture(tmp_path,monkeypatch)
    state=api()._service_state
    monkeypatch.setattr(api(),'_service_state',lambda service:{**state(service),'ActiveState':'activating','MainPID':'42'})
    with pytest.raises(ValueError):api().apply_stage(args['stage'])
    assert calls==[]

@pytest.mark.parametrize('valid',[True,False])
def test_runtime_probe_is_capped_and_bound_to_exact_package(valid,tmp_path,monkeypatch):
    args,_=fixture(tmp_path);api().stage_deployment(**args);calls=[]
    identity=sha256((args['stage']/'deployment.json').read_bytes()).hexdigest()
    def execute(command,**kw):
        calls.append(command)
        assert command[:3]==['systemd-run','--user','--scope']
        for limit in ['CPUQuota=20%','MemoryMax=256M','MemorySwapMax=0','TasksMax=24','IOWeight=10']:assert limit in command
        assert '/usr/bin/python3' in command
        assert '--verify-runtime' in command
        assert kw['timeout']<=60
        return encode({'status':'runtime_verified','deployment_sha256':identity if valid else 'a'*64,'automatic_actuation':False})
    monkeypatch.setattr(subprocess,'check_output',execute)
    if valid:api()._qualify(args['stage'])
    else:
        with pytest.raises(ValueError):api()._qualify(args['stage'])
    assert len(calls)==1


def test_source_edit_after_cleanliness_check_cannot_masquerade_as_commit(tmp_path,monkeypatch):
    args,files=fixture(tmp_path);original=api()._git
    changed=args['repo_root']/'openhab/scripts/household_cycle.py'
    def git(repo,*command):
        result=original(repo,*command)
        if command[:2]==('status','--porcelain'):changed.write_bytes(b'unreviewed observer\n')
        return result
    monkeypatch.setattr(api(),'_git',git)
    try:api().stage_deployment(**args)
    except ValueError:assert not args['stage'].exists()
    else:
        assert (args['stage']/'sources/openhab/scripts/household_cycle.py').read_bytes()==files['openhab/scripts/household_cycle.py']
        assert api().verify_stage(args['stage'])['code_revision']==args['code_revision']


def test_index_edit_after_clean_check_cannot_omit_committed_entrypoint(tmp_path,monkeypatch):
    args,files=fixture(tmp_path);original=api()._git
    def git(repo,*command):
        result=original(repo,*command)
        if command[:2]==('status','--porcelain'):
            subprocess.run(['git','-C',str(repo),'rm','--cached','-q','openhab/scripts/household_cycle.py'],check=True,capture_output=True)
        return result
    monkeypatch.setattr(api(),'_git',git)
    try:api().stage_deployment(**args)
    except ValueError:assert not args['stage'].exists()
    else:
        target=args['stage']/'sources/openhab/scripts/household_cycle.py'
        assert target.is_file(), 'mutable index omitted the committed service entrypoint'
        assert target.read_bytes()==files['openhab/scripts/household_cycle.py']
