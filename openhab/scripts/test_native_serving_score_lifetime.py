"""Current compatible history must not renew worker lifetime or lose new I/O fixes."""
from pathlib import Path
import pytest
from test_native_serving_score_driver import fixture


def compatible_fixture(tmp_path,monkeypatch,helper='a'*64):
    import household_cycle_deploy as deploy,native_model_serving_receipt as admission
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,2)
    history={'stage':str(tmp_path/'historical'),'deployment_sha256':'b'*64};dispatch['historical']=[history]
    monkeypatch.setattr(coordinator,'native_score_selection',lambda *_:history)
    original=deploy.verify_stage
    def verify(actual,*,expected_deployment_sha256=None):
        if actual==Path(history['stage']):
            assert expected_deployment_sha256==history['deployment_sha256']
            return {'schema':'earthship-household-cycle-deployment/v3','runtime_sha256':'a'*64,'model_verification':{'helper':{'sha256':helper}}}
        return original(actual,expected_deployment_sha256=expected_deployment_sha256)
    monkeypatch.setattr(deploy,'verify_stage',verify)
    owned=admission.load_serving_selection;archived=object()
    def selected(actual,*,expected_deployment_sha256,assessed_at,guard):
        if actual==Path(history['stage']):assert expected_deployment_sha256=='b'*64;guard();return archived
        return owned(actual,expected_deployment_sha256=expected_deployment_sha256,assessed_at=assessed_at,guard=guard)
    monkeypatch.setattr(admission,'load_serving_selection',selected)
    return coordinator,config,stage,calls,model,now,history,archived


def test_same_runtime_and_helper_use_current_worker_with_owned_history(tmp_path,monkeypatch):
    c,config,stage,calls,model,now,history,archived=compatible_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(c,'execute_retained_native_score',lambda *_:pytest.fail('compatible history restarted the old worker'))
    def score(settings,*,guard,clock,queue,serving_model,historical_selections):
        assert serving_model is model and historical_selections==(archived,);guard();return {'status':'waiting'}
    monkeypatch.setattr(c,'score_with_report',score)
    assert c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100)['status']=='waiting'


def test_changed_helper_keeps_exact_retained_worker(tmp_path,monkeypatch):
    c,config,stage,calls,model,now,history,archived=compatible_fixture(tmp_path,monkeypatch,helper='c'*64)
    seen=[];monkeypatch.setattr(c,'execute_retained_native_score',lambda selected:seen.append(selected) or {'status':'waiting'})
    monkeypatch.setattr(c,'score_with_report',lambda *_a,**_k:pytest.fail('incompatible helper loaded into current worker'))
    assert c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100)['status']=='waiting'
    assert seen==[history] and 'locked' not in calls


def test_stage_verification_counts_toward_existing_fifty_second_lifetime(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,2)
    ticks=[100.];verify=deploy.verify_stage
    def expensive(*args,**kwargs):
        result=verify(*args,**kwargs);ticks[0]+=51.;return result
    monkeypatch.setattr(deploy,'verify_stage',expensive)
    monkeypatch.setattr(c,'score_with_report',lambda *_a,**_k:{'status':'waiting'})
    with pytest.raises(ValueError,match='score'):
        c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:ticks[0])
    assert 'read_model' not in calls and 'locked' not in calls
