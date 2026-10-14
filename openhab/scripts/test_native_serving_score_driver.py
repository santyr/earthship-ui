"""Routing-only outer scorer proof; genuine receipt replay is tested separately."""
from datetime import datetime,timezone
from pathlib import Path
import inspect,json
import pytest


def fixture(tmp_path,monkeypatch,minute):
    import household_forecast_score as coordinator,native_thermal_live as native
    assert 'deployment_sha256' in inspect.signature(coordinator.run).parameters,'external score pin propagation missing'
    import thermal_installed_intel as installed,native_inference_pressure as pressure
    import thermal_model.capture_guard as locks,native_model_serving_receipt as admission
    tmp_path.chmod(0o700);stage=tmp_path/'stage';stage.mkdir(mode=0o700)
    source=stage/'sources/openhab/scripts/household_forecast_score.py';source.parent.mkdir(parents=True);source.write_bytes(Path(coordinator.__file__).read_bytes())
    monkeypatch.setattr(coordinator,'__file__',str(source))
    settings={'schema':native.SERVING_SCHEMA,'shared_lock':str(tmp_path/'lock')}
    config=stage/'forecast.json';config.write_text(json.dumps(settings));config.chmod(0o600)
    monkeypatch.setattr(native,'load_settings',lambda path:settings)
    monkeypatch.setattr(installed,'_resource_preflight',lambda:None)
    calls=[];model=object();selection=object()
    class Lock:
        def __init__(self,path):assert path==settings['shared_lock']
        def __enter__(self):calls.append('locked');return self
        def __exit__(self,*a):calls.append('unlocked')
        def verify(self):calls.append('lock_check')
    class Headroom:
        def preflight(self):calls.append('quiet')
        def check(self):calls.append('pressure')
    monkeypatch.setattr(locks,'SharedScoreLock',Lock);monkeypatch.setattr(pressure,'NativeInferenceHeadroom',Headroom)
    import household_cycle_deploy as deploy
    def verify(actual,*,expected_deployment_sha256=None):
        assert actual==stage and expected_deployment_sha256=='a'*64;calls.append('stage_verified');return {'schema':'earthship-household-cycle-deployment/v3'}
    monkeypatch.setattr(deploy,'verify_stage',verify)
    dispatch={'current':'current','legacy':{'stage':str(tmp_path/'legacy'),'config':str(tmp_path/'legacy.json')},'historical':[]}
    def selected(actual,*,deployment_sha256,guard):
        assert actual==stage and deployment_sha256=='a'*64;guard();calls.append('dispatch');return dispatch
    monkeypatch.setattr(coordinator,'read_score_dispatch',selected)
    def owned(actual,*,expected_deployment_sha256,assessed_at,guard):
        assert calls.index('locked')<calls.index('quiet');assert expected_deployment_sha256=='a'*64;guard();calls.append('selected');return selection
    monkeypatch.setattr(admission,'load_serving_selection',owned)
    def read(actual,*,assessed_at,guard):assert actual is selection;guard();calls.append('read_model');return model
    monkeypatch.setattr(admission,'read_serving_model',read)
    now=datetime(2026,10,13,14,minute,20,tzinfo=timezone.utc)
    return coordinator,config,stage,calls,model,now,dispatch


def test_current_score_slot_reads_one_context_under_existing_lock(tmp_path,monkeypatch):
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,2)
    def score(settings,*,guard,clock,queue,serving_model,historical_selections):
        assert serving_model is model and historical_selections==() and queue is True;guard();calls.append('scored');return {'status':'waiting','scored':0,'automatic_actuation':False}
    monkeypatch.setattr(coordinator,'score_with_report',score)
    result=coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100)
    assert result['status']=='waiting' and calls.count('read_model')==1 and calls[-1]=='unlocked'


def test_legacy_slot_executes_only_explicit_retained_worker(tmp_path,monkeypatch):
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,1)
    monkeypatch.setattr(coordinator,'score_with_report',lambda *a,**k:pytest.fail('legacy slot ran active native worker'))
    def execute(selection):
        assert selection==dispatch['legacy'];calls.append('legacy_exec');return {'status':'waiting','scored':0,'automatic_actuation':False}
    monkeypatch.setattr(coordinator,'execute_legacy_score',execute,raising=False)
    result=coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100)
    assert result['status']=='waiting' and 'read_model' not in calls and calls[-1]=='legacy_exec'


def test_missing_external_pin_refuses_both_score_workers(tmp_path,monkeypatch):
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,2)
    monkeypatch.setattr(coordinator,'score_with_report',lambda *a,**k:pytest.fail('missing pin served score'))
    with pytest.raises(ValueError):coordinator.run(config,stage=stage,clock=lambda:now,monotonic=lambda:100)
    assert 'read_model' not in calls and 'locked' not in calls
