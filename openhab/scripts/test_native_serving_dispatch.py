"""Explicit score slots and selections must never become refusal fallback."""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import json
import pytest
from test_installed_shade_score_inputs import settings


def test_native_only_slots_leave_legacy_backlog_unscheduled():
    import household_forecast_score as coordinator
    selector=getattr(coordinator,'score_role',None)
    assert callable(selector),'explicit score slot selector is missing'
    roles=[selector(datetime(2026,10,13,18,minute,10,tzinfo=timezone.utc)) for minute in range(10)]
    assert 'legacy' not in roles
    assert tuple(i for i in range(10) if roles[i]=='historical')==(6,)
    assert tuple(i for i in range(10) if roles[i]=='current')==(1,)
    assert tuple(i for i in range(10) if roles[i]=='battery')==(8,)
    assert roles.count('reserved')==7


def test_receipt_score_refusal_cannot_route_to_legacy_monitor(monkeypatch,settings,tmp_path):
    import inspect,household_forecast_score as coordinator,native_thermal_live as native
    assert 'serving_model' in inspect.signature(coordinator.score_with_report).parameters,'receipt scoring propagation is missing'
    from thermal_model import provisional_monitor as legacy
    context=object();settings={**settings[1],'schema':'earthship-weathernext-thermal-live-config/v2','evidence_directory':str(tmp_path/'evidence')}
    (tmp_path/'evidence').mkdir(mode=0o700)
    def refusal(value,*,guard,reader,serving_model,historical_selections):
        from household_native_score_queries import EndpointWindowScoreReader
        assert isinstance(reader,EndpointWindowScoreReader)
        assert value==settings and serving_model is context and historical_selections==()
        raise ValueError('receipt refused')
    monkeypatch.setattr(native,'score_jobs',refusal)
    monkeypatch.setattr(legacy,'current_runtime',lambda:pytest.fail('receipt refusal selected legacy runtime'))
    with pytest.raises(ValueError,match='receipt refused'):
        coordinator.score_with_report(settings,guard=lambda:None,serving_model=context,historical_selections=())


def dispatch_fixture(tmp_path,monkeypatch):
    import household_forecast_score as coordinator,household_cycle_deploy as deploy
    reader=getattr(coordinator,'read_score_dispatch',None)
    assert callable(reader),'owned dispatch reader is missing'
    tmp_path.chmod(0o700);stage=tmp_path/'current';stage.mkdir(mode=0o700)
    legacy=tmp_path/'legacy';legacy.mkdir(mode=0o700)
    config=legacy/'forecast.json';config.write_text(json.dumps({'schema':'earthship-provisional-thermal-live-config/v1'}));config.chmod(0o600)
    cycle=legacy/'cycle.json';cycle.write_text(json.dumps({'forecast_config':str(config)}));cycle.chmod(0o600)
    manifest=legacy/'deployment.json';manifest.write_bytes(b'{}');manifest.chmod(0o600);legacy_pin=sha256(manifest.read_bytes()).hexdigest()
    body={'schema':'earthship-native-score-dispatch/v1','current':'current','legacy':{'stage':str(legacy),'deployment_sha256':legacy_pin,'config':str(config),'config_sha256':sha256(config.read_bytes()).hexdigest()},'historical':[]}
    path=stage/'score-dispatch.json';path.write_text(json.dumps(body));path.chmod(0o600)
    record={'schema':'earthship-household-cycle-deployment/v3','score_dispatch':{'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}}
    calls=[]
    def verify(actual,*,expected_deployment_sha256=None):
        calls.append((actual,expected_deployment_sha256))
        if actual==stage:
            assert expected_deployment_sha256=='a'*64;return record
        if actual==legacy:
            assert expected_deployment_sha256==legacy_pin;return {'schema':'earthship-household-cycle-deployment/v1'}
        pytest.fail('unselected stage')
    monkeypatch.setattr(deploy,'verify_stage',verify)
    return reader,stage,path,body,record,calls


def test_owned_dispatch_pins_legacy_stage_and_original_config(tmp_path,monkeypatch):
    reader,stage,path,body,record,calls=dispatch_fixture(tmp_path,monkeypatch)
    assert reader(stage,deployment_sha256='a'*64,guard=lambda:None)==body
    assert (Path(body['legacy']['stage']),body['legacy']['deployment_sha256']) in calls
    Path(body['legacy']['config']).write_bytes(b'{}')
    with pytest.raises(ValueError):reader(stage,deployment_sha256='a'*64,guard=lambda:None)


@pytest.mark.parametrize('damage',['digest','self_pin','no_legacy','wrong_slot'])
def test_dispatch_cannot_select_unpinned_or_implicit_model(tmp_path,monkeypatch,damage):
    reader,stage,path,body,record,calls=dispatch_fixture(tmp_path,monkeypatch)
    if damage=='self_pin':body['deployment_sha256']='a'*64
    if damage=='no_legacy':body['legacy']=None
    if damage=='wrong_slot':body['current']='legacy'
    if damage=='digest':body['legacy']['config_sha256']='f'*64
    path.write_text(json.dumps(body));record['score_dispatch']['sha256']=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):reader(stage,deployment_sha256='a'*64,guard=lambda:None)
