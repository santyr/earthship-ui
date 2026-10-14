"""Missing outcomes cannot erase independently verified completed measurements."""
import importlib,json
from pathlib import Path
import pytest
from test_provisional_thermal_monitor import setup,module


def api():return importlib.import_module('household_forecast_score')


@pytest.mark.parametrize('status,expected',[
    ('scored',0),('waiting',0),('monitoring_refreshed',0),('withheld',1),('unknown',1)])
def test_cli_preserves_original_integrity_refusal(status,expected,tmp_path,monkeypatch,capsys):
    result={'status':status,'reason':'completed_original_unavailable'}
    monkeypatch.setattr(api(),'run',lambda *a,**kw:result)
    assert api().main(['--config',str(tmp_path/'score.json')])==expected
    assert json.loads(capsys.readouterr().out)==result


def test_missing_new_outcome_rebuilds_report_from_verified_completed_pairs(tmp_path,monkeypatch):
    settings,_,reader=setup(tmp_path,monkeypatch)
    module().score_jobs(settings,guard=lambda:None,reader=reader)
    # Force the existing expected refusal after its report deletion. Completed
    # originals still exist and must be independently checked before reporting.
    def missing(settings,**kw):
        (Path(settings['evidence_directory'])/'latest-provisional-performance.json').unlink()
        raise ValueError('original mature outcome unavailable')
    monkeypatch.setattr(module(),'score_jobs',missing)
    result=api().score_with_report(settings,guard=lambda:None,clock=module()._clock)
    assert result['status']=='monitoring_refreshed'
    assert result['scored']==0 and result['current_revision_scored']==1
    assert result['pending_reason']=='mature_outcome_unavailable'
    report=json.loads((Path(settings['evidence_directory'])/'latest-provisional-performance.json').read_bytes())
    assert report['by_horizon']['1']['model']['count']==1
    assert report['graduated'] is False and result['automatic_actuation'] is False


def test_missing_completed_source_still_refuses_report_refresh(tmp_path,monkeypatch):
    settings,_,reader=setup(tmp_path,monkeypatch)
    module().score_jobs(settings,guard=lambda:None,reader=reader)
    pair=next(Path(settings['evidence_directory']).glob('scores-*/*.provisional-pair-v1.json'));pair.unlink()
    def missing(*args,**kwargs):raise ValueError('original mature outcome unavailable')
    monkeypatch.setattr(module(),'score_jobs',missing)
    with pytest.raises((OSError,ValueError)):api().score_with_report(settings,guard=lambda:None,clock=module()._clock)


@pytest.mark.parametrize('reason',['actual original publication receipt missing','training host pressure or memory reserve unavailable','original scoring model/runtime identity differs'])
def test_unexpected_failures_do_not_publish_fallback_report(reason,tmp_path,monkeypatch):
    settings,_,_=setup(tmp_path,monkeypatch)
    def broken(*args,**kwargs):raise ValueError(reason)
    monkeypatch.setattr(module(),'score_jobs',broken)
    monkeypatch.setattr(module(),'refresh_report',lambda *a,**k:pytest.fail('unexpected failure refreshed a report'))
    with pytest.raises(ValueError,match=reason):api().score_with_report(settings,guard=lambda:None,clock=module()._clock)


def runtime_setup(tmp_path,monkeypatch):
    from thermal_model import provisional_live,training_pressure_guard
    import thermal_installed_intel
    from datetime import datetime,timezone,timedelta
    settings={'shared_lock':str(tmp_path/'score.lock')}
    lock=tmp_path/'score.lock';lock.write_text('');lock.chmod(0o600)
    config=tmp_path/'score.json';config.write_text(json.dumps(settings));config.chmod(0o600)
    monkeypatch.setattr(provisional_live,'load_settings',lambda path:settings)
    monkeypatch.setattr(thermal_installed_intel,'_resource_preflight',lambda:None)
    class Pressure:
        def __init__(self,**kw):pass
        def check(self):pass
    monkeypatch.setattr(training_pressure_guard,'TrainingHeadroom',Pressure)
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(provisional_live,'_next_issue',lambda at:now+timedelta(minutes=5))
    return config,now


def test_score_coordinator_refuses_near_forecast_preparation(tmp_path,monkeypatch):
    from datetime import timedelta
    from thermal_model import provisional_live
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
