"""Missing outcomes cannot erase independently verified completed measurements."""
import importlib,json
from pathlib import Path
import pytest
from test_native_monitor import setup as native_setup,originals


def api():return importlib.import_module('household_forecast_score')


def test_production_retained_runner_loads_reviewed_sibling_and_closed_reader():
    from hashlib import sha256
    import household_native_score_queries as queries
    coordinator=api()
    helper=Path(coordinator.__file__).resolve().with_name('household_retained_native_score.py')
    # Independently reviewed source authority from the signed Task3 result.
    assert sha256(helper.read_bytes()).hexdigest()=='80d7fb5c60467bfe132016fb490bd522007193c18593090144c83305720841a3'
    module=coordinator.production_retained_runner()
    assert Path(module.__file__).resolve()==helper
    assert Path(module.run.__code__.co_filename).resolve()==helper
    assert module._reader_factory() is queries.RecentCycleWindowReader


def test_production_retained_runner_refuses_changed_sibling_before_execution(tmp_path,monkeypatch):
    coordinator=api()
    helper=Path(coordinator.__file__).resolve().with_name('household_retained_native_score.py')
    changed=tmp_path/helper.name
    changed.write_bytes(helper.read_bytes()+b"\nraise AssertionError('unreviewed retained helper executed')\n")
    changed.chmod(0o644)
    monkeypatch.setattr(coordinator,'__file__',str(tmp_path/'household_forecast_score.py'))
    with pytest.raises(ValueError,match='retained coordinator source differs'):
        coordinator.production_retained_runner()


@pytest.mark.parametrize('status,expected',[
    ('scored',0),('waiting',0),('monitoring_refreshed',0),('withheld',1),('unknown',1)])
def test_cli_preserves_original_integrity_refusal(status,expected,tmp_path,monkeypatch,capsys):
    result={'status':status,'reason':'completed_original_unavailable'}
    monkeypatch.setattr(api(),'run',lambda *a,**kw:result)
    assert api().main(['--config',str(tmp_path/'score.json')])==expected
    assert json.loads(capsys.readouterr().out)==result


def prepared_native(tmp_path,monkeypatch,originals):
    live,settings,reader,clock,*_=native_setup(tmp_path,monkeypatch,originals)
    original=live.score_jobs
    def score(value,*,guard):return original(value,guard=guard,reader=reader)
    original(settings,guard=lambda:None,reader=reader)
    monkeypatch.setattr(live,'score_jobs',score)
    return settings,clock


def test_missing_new_outcome_rebuilds_report_from_verified_completed_pairs(tmp_path,monkeypatch,originals):
    settings,clock=prepared_native(tmp_path,monkeypatch,originals)
    path=Path(settings['evidence_directory'])/'latest-native-provisional-performance.json'
    path.unlink()
    result=api().score_with_report(settings,guard=lambda:None,clock=lambda:clock[0])
    assert result['status']=='waiting'
    assert result['scored']==0 and result['current_revision_scored']==1
    report=json.loads(path.read_bytes())
    assert report['by_horizon']['1']['model']['count']==1
    assert report['graduated'] is False and result['automatic_actuation'] is False


def test_missing_completed_source_still_refuses_report_refresh(tmp_path,monkeypatch,originals):
    settings,clock=prepared_native(tmp_path,monkeypatch,originals)
    pair=next(Path(settings['evidence_directory']).glob('scores-*/*.native-thermal-score-sources-v1.json'));pair.unlink()
    with pytest.raises((OSError,ValueError)):api().score_with_report(settings,guard=lambda:None,clock=lambda:clock[0])


@pytest.mark.parametrize('reason',['actual original publication receipt missing','training host pressure or memory reserve unavailable','original scoring model/runtime identity differs'])
def test_unexpected_failures_do_not_publish_fallback_report(reason,tmp_path,monkeypatch):
    import native_thermal_live as native
    settings={'schema':native.LIVE_SCHEMA}
    def broken(*args,**kwargs):raise ValueError(reason)
    monkeypatch.setattr(native,'score_jobs',broken)
    with pytest.raises(ValueError,match=reason):api().score_with_report(settings,guard=lambda:None)


def runtime_setup(tmp_path,monkeypatch,*,mock_native_pressure=True):
    from thermal_model import native_operational_io as provisional_live
    import native_thermal_live as native,native_inference_pressure
    from datetime import datetime,timezone,timedelta
    settings={'schema':native.LIVE_SCHEMA,'shared_lock':str(tmp_path/'score.lock')}
    lock=tmp_path/'score.lock';lock.write_text('');lock.chmod(0o600)
    config=tmp_path/'score.json';config.write_text(json.dumps(settings));config.chmod(0o600)
    monkeypatch.setattr(native,'load_settings',lambda path:settings)
    monkeypatch.setattr(api(),'production_resource_preflight',lambda:None)
    class Pressure:
        def __init__(self,**kw):pass
        def preflight(self):pass
        def check(self):pass
    if mock_native_pressure:monkeypatch.setattr(native_inference_pressure,'NativeInferenceHeadroom',Pressure)
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(provisional_live,'_next_issue',lambda at:now+timedelta(minutes=5))
    return config,now


def test_score_coordinator_refuses_near_forecast_preparation(tmp_path,monkeypatch):
    from datetime import timedelta
    from thermal_model import native_operational_io as provisional_live
    config,now=runtime_setup(tmp_path,monkeypatch)
    monkeypatch.setattr(provisional_live,'_next_issue',lambda at:now+timedelta(seconds=89))
    monkeypatch.setattr(api(),'score_with_report',lambda *a,**k:pytest.fail('score entered forecast preparation window'))
    with pytest.raises(BlockingIOError):api().run(config,clock=lambda:now)


def test_score_coordinator_total_deadline_does_not_renew(tmp_path,monkeypatch):
    config,now=runtime_setup(tmp_path,monkeypatch);ticks=[0.]
    def overrun(settings,*,guard,**kw):
        guard();ticks[0]=api().SCORE_LIFETIME_SECONDS+1;guard();pytest.fail('score overrun accepted')
    monkeypatch.setattr(api(),'score_with_report',overrun)
    with pytest.raises(ValueError,match='score lifetime elapsed'):
        api().run(config,clock=lambda:now,monotonic=lambda:ticks[0])


def test_score_coordinator_detects_changed_original_configuration(tmp_path,monkeypatch):
    config,now=runtime_setup(tmp_path,monkeypatch)
    def changed(settings,*,guard,**kw):
        guard();config.write_text('{}');guard();pytest.fail('changed config accepted')
    monkeypatch.setattr(api(),'score_with_report',changed)
    with pytest.raises(ValueError,match='score source or configuration changed'):
        api().run(config,clock=lambda:now)
