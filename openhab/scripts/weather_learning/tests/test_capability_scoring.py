"""Original emitted marginal verification, never a reconstructed forecast."""
from copy import deepcopy
from datetime import timedelta
import importlib,json,sqlite3
import pytest
from learning_fixtures import T,SITE,EPOCH,native_snapshot,receipt
from weather_learning.archive import Archive
from weather_learning.shadow import ShadowStore
from weather_learning.capability_publish import build_capability_report,retain_capability_report
from weather_learning.features import local_temperature_outcome

def api():return importlib.import_module('weather_learning.capability_scoring')

def setup(tmp_path,*,hours=12,offset_minutes=30):
    archive=Archive(tmp_path/'archive');archive.store_snapshot(native_snapshot(mean_c=0,hours=hours))
    state=ShadowStore(tmp_path/'shadow')
    report=build_capability_report(archive,decision=T+timedelta(minutes=offset_minutes),site=SITE,horizons=(min(hours-1,10),))
    retain_capability_report(state.root,report)
    return archive,state,report

def run(state,now,**kwargs):
    return api().monitor_capabilities(state,now=now,sensor_epoch=EPOCH,observation_policy_sha256='a'*64,
        read_temperature=lambda targets,assessed:{t:receipt(t,3) for t in targets},**kwargs)

def test_literal_pinball_interval_and_point_scores_use_original_emitted_values(tmp_path):
    _,_,report=setup(tmp_path);row=report['groups']['temperature']['hours'][0]
    at=T+timedelta(hours=1)
    outcome=local_temperature_outcome(receipt(at,3),target_at=at,assessed_at=at+timedelta(minutes=2),sensor_epoch=EPOCH)
    score=api().temperature_range_score(report,row,outcome,observation_policy_sha256='a'*64)
    assert score['mean_absolute_error_c']==pytest.approx(3)
    assert score['p10_pinball_c']==pytest.approx(.5)
    assert score['p90_pinball_c']==pytest.approx(.9)
    assert score['interval_score_80_c']==pytest.approx(14)
    assert score['width_c']==4 and score['covered_80'] is False
    assert score['wis_c'] is None and score['issued']['p50_c'] is None
    assert score['issued']['mean_c']==0 and score['source']['snapshot_sha256']==row['source_sha256']
    assert score['local_coverage_qualified'] is False

def test_only_actual_median_enables_weighted_interval_score_and_ties_cover(tmp_path):
    _,_,report=setup(tmp_path);report=deepcopy(report);row=report['groups']['temperature']['hours'][0]
    row['p50_c']=1
    from weather_learning.contracts import identity
    report['report_sha256']=identity({k:v for k,v in report.items() if k!='report_sha256'})
    at=T+timedelta(hours=1);outcome=local_temperature_outcome(receipt(at,2),target_at=at,assessed_at=at+timedelta(minutes=2),sensor_epoch=EPOCH)
    score=api().temperature_range_score(report,row,outcome,observation_policy_sha256='a'*64)
    assert score['wis_c']==pytest.approx(.6)
    assert score['covered_80'] is True

def test_retention_registers_predeclared_targets_and_scores_survive_restart(tmp_path):
    _,state,report=setup(tmp_path)
    assert (state.root/'capability-scores.sqlite3').exists()
    raw=(state.root/'capability-issues'/(report['report_sha256']+'.json')).read_bytes()
    first=run(state,T+timedelta(hours=13),apply=True,limit=8)
    assert first['observations_attempted']==3  # declared offsets 1,3,6 occur in the ten-hour product
    assert first['local_coverage_qualified'] is False
    second=api().monitor_capabilities(ShadowStore(state.root),now=T+timedelta(hours=13),sensor_epoch=EPOCH,
        observation_policy_sha256='a'*64,read_temperature=lambda *args:pytest.fail('completed outcomes must not be reread'),apply=True)
    assert second['observations_attempted']==0
    assert second['cohorts']==first['cohorts']
    assert (state.root/'capability-issues'/(report['report_sha256']+'.json')).read_bytes()==raw
    assert first['cohorts'][0]['raw_range']['coverage_80']==0

def test_late_discovery_scores_timely_original_observation_once_and_preview_is_pure(tmp_path):
    _,state,_=setup(tmp_path)
    before=(state.root/'capability-scores.sqlite3').read_bytes()
    preview=run(state,T+timedelta(days=10),apply=False,limit=1)
    assert preview['observations_attempted']==1
    assert (state.root/'capability-scores.sqlite3').read_bytes()==before
    actual=run(state,T+timedelta(days=10),apply=True,limit=1)
    assert actual['scored']==1 and actual['pending']>0

def test_unqualified_receipt_is_withheld_and_does_not_turn_into_zero(tmp_path):
    _,state,_=setup(tmp_path)
    result=api().monitor_capabilities(state,now=T+timedelta(hours=13),sensor_epoch=EPOCH,observation_policy_sha256='a'*64,
        read_temperature=lambda targets,assessed:{t:receipt(t,0,epoch='00000000-0000-4000-8000-000000000099') for t in targets},apply=True)
    assert result['scored']==0 and result['cohorts']==[]
    assert result['withheld']['quality_withheld']>0

def test_missing_original_is_retried_without_rediscovering_a_current_forecast(tmp_path):
    _,state,report=setup(tmp_path)
    original=state.root/'capability-issues'/(report['report_sha256']+'.json');raw=original.read_bytes();original.unlink()
    result=run(state,T+timedelta(hours=13),apply=True)
    assert result['withheld']['missing_original']>0 and result['scored']==0
    original.write_bytes(raw);original.chmod(0o600)
    result=run(state,T+timedelta(hours=15),apply=True)
    assert result['scored']>0

def test_repeated_issuances_do_not_inflate_independent_target_or_day_counts(tmp_path):
    archive,state,report=setup(tmp_path)
    newer=build_capability_report(archive,decision=T+timedelta(minutes=40),site=SITE,horizons=(10,))
    retain_capability_report(state.root,newer)
    result=run(state,T+timedelta(hours=13),apply=True)
    cohort=result['cohorts'][0]
    assert cohort['issued_forecast_rows']==6
    assert cohort['independent_targets']==3 and cohort['independent_local_dates']==1
    assert cohort['raw_range']['interval_score_80_c']==pytest.approx(14)

def test_global_stop_guard_propagates_and_new_namespace_has_no_legacy_report_write(tmp_path):
    _,state,_=setup(tmp_path)
    with pytest.raises(TimeoutError):run(state,T+timedelta(hours=13),guard=lambda:(_ for _ in ()).throw(TimeoutError('deadline')))
    assert not (state.root/'weather-performance.json').exists()
    assert not (state.root/'capability-performance.json').exists()

def test_equal_target_dates_weight_scores_instead_of_pooling_repeated_rows(tmp_path):
    archive,state,_=setup(tmp_path)
    archive.store_snapshot(native_snapshot(day=1,mean_c=0,hours=2))
    day_two=build_capability_report(archive,decision=T+timedelta(days=1,minutes=30),site=SITE,horizons=(1,))
    retain_capability_report(state.root,day_two)
    result=api().monitor_capabilities(state,now=T+timedelta(days=2),sensor_epoch=EPOCH,observation_policy_sha256='a'*64,
        read_temperature=lambda targets,assessed:{t:receipt(t,3 if t<T+timedelta(days=1) else 9) for t in targets},apply=True)
    cohort=result['cohorts'][0]
    assert cohort['independent_local_dates']==2 and cohort['issued_forecast_rows']==4
    assert cohort['raw_range']['mean_absolute_error_c']==pytest.approx(6)

def test_failed_cache_publication_does_not_count_prepared_forecasts_as_issued(tmp_path,monkeypatch):
    archive=Archive(tmp_path/'archive');archive.store_snapshot(native_snapshot(hours=12))
    state=ShadowStore(tmp_path/'shadow')
    report=build_capability_report(archive,decision=T+timedelta(minutes=30),site=SITE,horizons=(10,))
    write=ShadowStore._write
    def fail_cache(self,path,value,**kw):
        if path.name=='weather-capabilities.json':raise OSError('cache publication failed')
        return write(self,path,value,**kw)
    monkeypatch.setattr(ShadowStore,'_write',fail_cache)
    with pytest.raises(OSError):retain_capability_report(state.root,report)
    result=run(state,T+timedelta(hours=13),apply=True)
    assert result['observations_attempted']==0 and result['total_retained_scores']==0

def test_published_cache_is_recovered_if_process_stops_before_index_confirmation(tmp_path,monkeypatch):
    archive=Archive(tmp_path/'archive');archive.store_snapshot(native_snapshot(hours=12))
    state=ShadowStore(tmp_path/'shadow')
    report=build_capability_report(archive,decision=T+timedelta(minutes=30),site=SITE,horizons=(10,))
    with monkeypatch.context() as patch:
        patch.setattr(api().CapabilityScores,'confirm',lambda *args:(_ for _ in ()).throw(OSError('interrupted confirmation')))
        with pytest.raises(OSError):retain_capability_report(state.root,report)
    assert (state.root/'weather-capabilities.json').exists()
    result=run(ShadowStore(state.root),T+timedelta(hours=13),apply=True)
    assert result['scored']==3
