"""Retain originals across frequent operational deployments without wider inference."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import pytest


@pytest.mark.parametrize('count',[32,63])
def test_dispatch_roundtrip_retains_every_explicit_stage(tmp_path,monkeypatch,count):
    from test_native_serving_dispatch_package import fixture
    import household_cycle_deploy as deploy,household_forecast_score as score
    writer,legacy,pin,config,output=fixture(tmp_path,monkeypatch)
    current=tmp_path/'current';current.mkdir(mode=0o700)
    references=[]
    for i in range(count):
        stage=tmp_path/str(i);stage.mkdir(mode=0o700)
        path=stage/'deployment.json';path.write_bytes(b'{}');path.chmod(0o600)
        references.append(dict(stage=str(stage),deployment_sha256=sha256(path.read_bytes()).hexdigest()))
    current_record={'schema':'earthship-household-cycle-deployment/v3'}
    def verify(stage,*,expected_deployment_sha256=None):
        if stage==current:return current_record
        assert expected_deployment_sha256==pin
        return {'schema':'earthship-household-cycle-deployment/v1' if stage==legacy else 'earthship-household-cycle-deployment/v3'}
    monkeypatch.setattr(deploy,'verify_stage',verify)
    result=writer(legacy_stage=legacy,legacy_deployment_sha256=pin,historical_selections=tuple(references),output=output,guard=lambda:None)
    current_record['score_dispatch']={'path':str(output),'sha256':result['sha256']}
    assert score.read_score_dispatch(current,deployment_sha256='a'*64,guard=lambda:None)['historical']==references
    assert output.stat().st_size<=131072
    # Every retained worker remains independently scheduled, including entries
    # outside the current process's original 31-model inference envelope.
    selected={score.native_score_selection({'historical':references},at=datetime(2026,10,15,0,6,tzinfo=timezone.utc)+timedelta(minutes=10*i))['stage'] for i in range(count)}
    assert selected=={r['stage'] for r in references}


def test_current_native_pass_preserves_original_31_selection_envelope(tmp_path,monkeypatch):
    from test_native_serving_score_driver import fixture
    import household_cycle_deploy as deploy,native_model_serving_receipt as admission
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,1)
    refs=[dict(stage=str(tmp_path/str(i)),deployment_sha256='a'*64) for i in range(63)]
    dispatch['historical']=refs
    old=deploy.verify_stage
    monkeypatch.setattr(deploy,'verify_stage',lambda actual,**kw:old(stage,**kw))
    monkeypatch.setattr(admission,'load_serving_selection',lambda actual,**kw:str(actual))
    monkeypatch.setattr(admission,'read_serving_model',lambda *a,**kw:model)
    def score(settings,*,guard,clock,queue,serving_model,historical_selections):
        assert historical_selections==tuple(r['stage'] for r in refs[-31:])
        return dict(status='waiting',scored=0,automatic_actuation=False)
    monkeypatch.setattr(coordinator,'score_with_report',score)
    assert coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100)['status']=='waiting'


def test_dispatch_retains_a_finite_inventory_bound(tmp_path,monkeypatch):
    from test_native_serving_dispatch_package import fixture
    writer,legacy,pin,config,output=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded explicit historical'):
        writer(legacy_stage=legacy,legacy_deployment_sha256=pin,
            historical_selections=({},)*64,output=output,guard=lambda:None)
    assert not output.exists()
