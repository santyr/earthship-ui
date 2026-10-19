"""A native selection must not pass through a legacy candidate/scorer reader."""
from pathlib import Path
import pytest


def test_native_profile_routes_monitoring_to_native_score_queue(tmp_path,monkeypatch):
    import household_forecast_score as coordinator
    import native_thermal_live as native
    from thermal_model import provisional_monitor as legacy
    settings={'schema':native.LIVE_SCHEMA,'candidate_path':str(tmp_path/'native-model'),
        'artifact_sha256':'a'*64,'runtime_sha256':'b'*64}
    expected={'status':'waiting','scored':0,'automatic_actuation':False};calls=[]
    def score(value,*,guard):
        assert value==settings;guard();calls.append('native');return expected
    monkeypatch.setattr(native,'score_jobs',score,raising=False)
    monkeypatch.setattr(legacy,'current_runtime',lambda:pytest.fail('native selection used legacy runtime'))
    result=coordinator.score_with_report(settings,guard=lambda:None,queue=True)
    assert result==expected and calls==['native']


def test_native_monitor_refusal_does_not_refresh_a_legacy_report(tmp_path,monkeypatch):
    import household_forecast_score as coordinator
    import native_thermal_live as native
    from thermal_model import provisional_monitor as legacy
    settings={'schema':native.LIVE_SCHEMA,'candidate_path':str(tmp_path/'native-model')}
    def refused(*a,**kw):raise ValueError('original native source incomplete')
    monkeypatch.setattr(native,'score_jobs',refused,raising=False)
    monkeypatch.setattr(legacy,'current_runtime',lambda:pytest.fail('native selection used legacy runtime'))
    monkeypatch.setattr(legacy,'refresh_report',lambda *a,**kw:pytest.fail('native refusal reused a legacy report'))
    with pytest.raises(ValueError,match='original native source incomplete'):
        coordinator.score_with_report(settings,guard=lambda:None,queue=True)


def test_native_private_runner_uses_native_loader_and_original_lock_deadline(tmp_path,monkeypatch):
    import json
    from datetime import datetime,timezone
    import household_forecast_score as coordinator
    import native_thermal_live as native
    import thermal_model.provisional_live as legacy
    import thermal_model.capture_guard as locks
    import native_inference_pressure as pressure
    import thermal_model.serial_publication_caps as installed
    settings={'schema':native.LIVE_SCHEMA,'shared_lock':str(tmp_path/'lock'),'artifact_sha256':'a'*64,'runtime_sha256':'b'*64}
    path=tmp_path/'native-config.json';path.write_text(json.dumps(settings));path.chmod(0o600);calls=[]
    monkeypatch.setattr(native,'load_settings',lambda actual:settings if actual==path else pytest.fail('wrong native config'))
    monkeypatch.setattr(legacy,'load_settings',lambda *a:pytest.fail('native private runner used legacy loader'))
    monkeypatch.setattr(coordinator,'production_resource_preflight',lambda:None)
    class Lock:
        def __init__(self,actual):assert actual==settings['shared_lock']
        def __enter__(self):calls.append('locked');return self
        def verify(self):calls.append('verified')
        def __exit__(self,*args):calls.append('unlocked')
    class Headroom:
        def __init__(self,**kw):assert not kw
        def preflight(self):calls.append('preflight')
        def check(self):calls.append('headroom')
    monkeypatch.setattr(locks,'SharedScoreLock',Lock);monkeypatch.setattr(pressure,'NativeInferenceHeadroom',Headroom)
    monkeypatch.setattr(coordinator,'production_pressure_monitor',Headroom)
    def score(value,*,guard,clock,queue):
        assert value==settings and queue is True;guard();return {'status':'waiting','scored':0,'automatic_actuation':False}
    monkeypatch.setattr(coordinator,'score_with_report',score)
    now=datetime(2026,10,13,14,1,20,tzinfo=timezone.utc)
    result=coordinator.run(path,clock=lambda:now,monotonic=lambda:100.)
    assert result['status']=='waiting' and 'headroom' in calls and calls[0]=='locked' and calls[-1]=='unlocked'
