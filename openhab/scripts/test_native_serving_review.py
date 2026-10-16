"""Integration regressions from the final serving-receipt review."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from test_native_serving_score_driver import fixture


def test_admissible_configured_slots_cover_current_and_retained(tmp_path,monkeypatch):
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,2)
    historical={'stage':str(tmp_path/'older'),'deployment_sha256':'b'*64}
    dispatch['historical']=[historical];seen=[]
    monkeypatch.setattr(coordinator,'execute_retained_native_score',lambda selection,**kw:seen.append('history') or {'status':'waiting'})
    monkeypatch.setattr(coordinator,'score_with_report',lambda *a,**k:seen.append('current') or {'status':'waiting'})
    # A different-runtime archive is never admitted into the current process.
    import household_cycle_deploy as deploy
    original=deploy.verify_stage
    def verify(actual,*,expected_deployment_sha256=None):
        if actual==Path(historical['stage']):return {'runtime_sha256':'f'*64,'model_verification':{'helper':{'sha256':'e'*64}}}
        return original(actual,expected_deployment_sha256=expected_deployment_sha256)
    monkeypatch.setattr(deploy,'verify_stage',verify)
    # :10 before :15 must retain the original 90-second refusal.
    before=now.replace(minute=0,second=10)
    with pytest.raises(BlockingIOError):coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:before,monotonic=lambda:100)
    after=now.replace(minute=0,second=16)
    coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:after,monotonic=lambda:100)
    assert seen==[]  # Publication's reserved minute does not score.
    for minute in (1,11,16):
        at=now.replace(minute=minute,second=20)
        coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:at,monotonic=lambda:100)
    assert seen==['current','current','history']


def test_older_helper_is_opaque_to_current_worker(tmp_path,monkeypatch):
    coordinator,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,1)
    import household_cycle_deploy as deploy
    historical=tmp_path/'older';historical.mkdir(mode=0o700)
    helper=historical/'native_model_serving_receipt.py';helper.write_bytes(b'# genuine different archived helper bytes\n')
    from hashlib import sha256
    dispatch['historical']=[{'stage':str(historical),'deployment_sha256':'b'*64}]
    original=deploy.verify_stage
    def verify(actual,*,expected_deployment_sha256=None):
        if actual==historical:return {'runtime_sha256':'f'*64,'model_verification':{'helper':{'sha256':sha256(helper.read_bytes()).hexdigest()}}}
        return original(actual,expected_deployment_sha256=expected_deployment_sha256)
    monkeypatch.setattr(deploy,'verify_stage',verify)
    monkeypatch.setattr(coordinator,'score_with_report',lambda *a,**k: {'status':'waiting'} if k['historical_selections']==() else pytest.fail('incompatible history loaded'))
    at=now.replace(second=20)
    assert coordinator.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:at,monotonic=lambda:100)['status']=='waiting'
    assert 'read_model' in calls


@pytest.mark.parametrize('phase',['replay','readback'])
def test_cache_guard_refuses_drift_during_materialization(tmp_path,monkeypatch,phase):
    from test_household_observation import materializer_fixture,NOW
    import household_observation as observation
    source,target,_=materializer_fixture(tmp_path)
    observation.materialize(source,target,clock=lambda:NOW);before=target.read_bytes();previous_inode=target.stat().st_ino;changed=[]
    if phase=='replay':
        real=observation.observe_pipeline
        def replay(*a,**kw):
            value=real(*a,**kw);changed.append(True);return value
        monkeypatch.setattr(observation,'observe_pipeline',replay)
    else:
        real=observation._private_file
        def read(path,*a,**kw):
            value=real(path,*a,**kw)
            if str(path)==target.name and kw.get('directory_fd') is not None:changed.append(True)
            return value
        monkeypatch.setattr(observation,'_private_file',read)
    def guard():
        if changed:raise ValueError('serving dependency or lock changed')
    with pytest.raises(ValueError,match='serving dependency'):
        observation.materialize(source,target,clock=lambda:NOW+timedelta(seconds=1),publication_guard=guard)
    assert target.read_bytes()==before and target.stat().st_ino==previous_inode


def test_completion_keeps_archive_guard_through_cache_readback(tmp_path,monkeypatch):
    import household_cycle as cycle,household_observation as observation
    import household.weather_context as weather,household_pipeline as pipeline
    calls=[]
    def unchanged():calls.append('archive_and_model_checked')
    monkeypatch.setattr(cycle,'load_cycle_delivery',lambda *a,**k:dict(capture={},receipts={},native=False,verify_unchanged=unchanged))
    monkeypatch.setattr(weather,'prepare_cycle_contexts',lambda *a,**k:(None,None))
    monkeypatch.setattr(cycle,'derive_cycle',lambda **k:{})
    monkeypatch.setattr(pipeline,'verify_source_closure',lambda *a:None)
    monkeypatch.setattr(cycle,'_retain_original',lambda *a:tmp_path/'receipt')
    def materialize(*a,**kw):
        assert kw.get('publication_guard') is unchanged,'final cache lost original archive/model/resource guard'
        kw['publication_guard']();return {'status':'observation_written'}
    monkeypatch.setattr(observation,'materialize',materialize)
    result=cycle.complete_cycle(publication={'status':'published','delivery_verified':True},collection={'status':'collected','issue':datetime.now(timezone.utc),'originals':{}},parameter_record=None,runtime_manifest=None,code_revision='a'*40,evidence_directory=tmp_path,observation_cache=tmp_path/'cache',guard=lambda:None)
    assert result['status']=='observation_written' and len(calls)==3
