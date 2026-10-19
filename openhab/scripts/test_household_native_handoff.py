"""Coherent private handoff records bind actual previous service ownership."""
import importlib,json
from pathlib import Path
import pytest
from test_household_native_family import fixture as family_fixture
from test_household_cycle_deploy import write,encode


def fixture(tmp_path,monkeypatch):
    family,args,settings,record,libraries,out=family_fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    legacy={**args,'stage':tmp_path/'previous','forecast_config':args['service_forecast_config']}
    legacy.pop('service_forecast_config');deploy.stage_deployment(**legacy)
    previous=legacy['stage'];base=args['service_file'].parent;config=legacy['forecast_config']
    forecast_override=base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf'
    forecast_override.parent.mkdir(mode=0o700);write(forecast_override,(previous/'service.conf').read_bytes())
    score_raw=(f'[Service]\nEnvironment="PYTHONPATH={previous}/sources/openhab/scripts:/home/sat/Solar_PV/analytics/src"\nExecStart=\nExecStart=/usr/bin/python3 {previous}/sources/openhab/scripts/household_forecast_score.py --config {config} --stage {previous}\n').encode()
    score_override=base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf'
    score_override.parent.mkdir(mode=0o700);write(score_override,score_raw)
    caps='\n'.join(k+'='+('60' if k=='TimeoutStartSec' else v) for k,v in deploy.LIMITS.items())
    write(base/'thermal-provisional-score.service',('[Service]\n'+caps+'\n').encode(),0o644)
    write(base/'thermal-provisional-forecast.timer',b'[Timer]\nOnCalendar=*-*-* *:04/5:45 UTC\n',0o644)
    write(base/'thermal-provisional-score.timer',b'[Timer]\nOnCalendar=*-*-* *:00/5:10 UTC\nOnCalendar=*-*-* *:01/5:10 UTC\nOnCalendar=*-*-* *:02/5:10 UTC\nOnCalendar=*-*-* *:03/5:10 UTC\n',0o644)
    family.prepare(args['stage'],libraries,out,guard=lambda:None)
    module=importlib.import_module('household_native_handoff')
    def definition(path):
        dropins=[str(p) for p in (base/(path.name+'.d')).glob('*.conf')]
        return {'FragmentPath':str(path),'DropInPaths':' '.join(dropins)}
    monkeypatch.setattr(module,'_unit_definition',definition)
    def state(path):
        raw=(previous/'service.conf').read_bytes() if path.name=='thermal-provisional-forecast.service' else score_raw
        command=[r[10:] for r in raw.decode().splitlines() if r.startswith('ExecStart=') and r!='ExecStart='][0]
        return dict(deploy.EFFECTIVE_LIMITS,ExecStart=command,ActiveState='inactive',MainPID='0')
    monkeypatch.setattr(deploy,'_service_state',state)
    return module,args,previous,out,tmp_path/'handoff',base


def test_handoff_binds_one_native_family_and_both_previous_owned_stages(tmp_path,monkeypatch):
    m,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    # A fresh Google fit owns different source bytes from its retired baseline.
    assert deploy.verify_stage(args['stage'])['protected_runtime_sources']!=deploy.verify_stage(previous)['protected_runtime_sources']
    selected=json.loads(args['forecast_config'].read_bytes())
    assert selected['schema']=='earthship-weathernext-thermal-live-config/v1'
    result=m.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    assert result['status']=='native_handoff_staged' and result['live_units_changed'] is False
    checked=m.verify(out,guard=lambda:None)
    assert checked['previous_forecast_stage']==str(previous) and checked['previous_score_stage']==str(previous)
    assert len(checked['changes'])==5 and checked['automatic_actuation'] is False
    assert {row['target'] for row in checked['changes'].values()}=={
        str(base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf'),
        str(base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf'),
        str(base/'thermal-provisional-score.timer.d'/'zzzz-household-native-timer.conf'),
        str(base/'thermal-native-geometry-prepare.service'),str(base/'thermal-native-geometry-prepare.timer')}
    assert not (base/'thermal-native-geometry-prepare.service').exists()


@pytest.mark.parametrize('damage',['override','effective','extra_dropin','timer','collision','family','cache'])
def test_handoff_refuses_unreconciled_originals_before_creating_output(tmp_path,monkeypatch,damage):
    m,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    if damage=='override':(base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf').write_text('changed')
    elif damage=='effective':monkeypatch.setattr(deploy,'_service_state',lambda path:{**deploy.EFFECTIVE_LIMITS,'ExecStart':'unowned command'})
    elif damage=='extra_dropin':write(base/'thermal-provisional-score.service.d'/'zzzzz-other.conf',b'[Service]\n')
    elif damage=='timer':(base/'thermal-provisional-forecast.timer').write_text('[Timer]\nOnCalendar=hourly\n')
    elif damage=='collision':write(base/'thermal-native-geometry-prepare.service',b'existing')
    elif damage=='family':(family/'score.conf').write_text('resealed unsafe command')
    else:
        path=previous/'cycle.json';value=json.loads(path.read_bytes());value['observation_cache']=str(base/'other-cache');path.write_bytes(encode(value))
    with pytest.raises((ValueError,OSError)):m.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    assert not out.exists()


def test_resealed_handoff_targets_cannot_redirect_writes(tmp_path,monkeypatch):
    m,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    m.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    path=out/'handoff.json';value=json.loads(path.read_bytes());value['changes']['forecast']['target']=str(base/'unrelated.service')
    from hashlib import sha256
    value['handoff_sha256']=sha256(encode({k:v for k,v in value.items() if k!='handoff_sha256'})).hexdigest();path.write_bytes(encode(value))
    with pytest.raises(ValueError):m.verify(out,guard=lambda:None)
