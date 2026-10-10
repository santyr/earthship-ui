"""Provisional live math uses real causal input validators; source binding seam is mathematical."""
from copy import deepcopy
from datetime import timedelta
import pytest
from test_installed_shade_origin import native,weather,actions,ISSUE
from test_provisional_thermal_artifact import example


def module():
    from thermal_model import provisional_forecast
    return provisional_forecast


def context(tmp_path,monkeypatch):
    candidate,_,_=example(tmp_path)
    candidate['created_at']=(ISSUE-timedelta(hours=1)).isoformat()
    candidate['fit']['training_start']=(ISSUE-timedelta(days=1)).isoformat()
    candidate['fit']['training_end']=(ISSUE-timedelta(hours=2)).isoformat()
    from test_installed_shade_inputs import EPOCHS
    candidate['fit']['sensor_epochs']=deepcopy(EPOCHS)
    from thermal_model.provisional_artifact import candidate_digest
    candidate['artifact_sha256']=candidate_digest(candidate)
    current,proof=native(ISSUE)
    data=dict(current=current,origin_temperatures=proof,forecast=weather(ISSUE),action_snapshot=actions(ISSUE),native_source_paths={'mathematical':'source'})
    # This seam does not assert genuine query acquisition. Existing compressed
    # binding tests exercise real retained sources; live deployment must use them.
    monkeypatch.setattr(module(),'build_binding',lambda *a,**k:{'mathematical':'binding'})
    return candidate,data


def test_provisional_forecast_has_no_graduation_or_calibration_claim(tmp_path,monkeypatch):
    candidate,inputs=context(tmp_path,monkeypatch)
    capture=module().build_capture(candidate,inputs,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2))
    payload=module().publication(capture)
    assert payload['version']==8 and payload['status']=='provisional'
    assert payload['confidence']=={'grade':'low','actionLabels':'withheld'}
    assert payload['automaticActuation'] is False
    assert payload['graduation']=={'forecastQualified':False,'stabilityAssessed':False,'calibrationAssessed':False}
    assert payload['forecast']['prediction_intervals'] is None
    assert len(payload['forecast']['trajectory'])==24


@pytest.mark.parametrize('damage',['wrong_epoch','stale','removed_shades','future_weather','missing_sources'])
def test_looser_data_support_never_accepts_invalid_issue_inputs(tmp_path,monkeypatch,damage):
    candidate,data=context(tmp_path,monkeypatch)
    if damage=='wrong_epoch':
        candidate['fit']['sensor_epochs']['air']='00000000-0000-0000-0000-000000000001'
        from thermal_model.provisional_artifact import candidate_digest
        candidate['artifact_sha256']=candidate_digest(candidate)
    if damage=='stale':
        for role in data['origin_temperatures']['roles'].values():role['grid'][-1][1]['validUntil']=ISSUE.isoformat()
    if damage=='removed_shades':data['action_snapshot']['actions']['outdoor_shade']['state']='removed'
    if damage=='future_weather':data['forecast']['captured_at']=(ISSUE+timedelta(seconds=1)).isoformat()
    if damage=='missing_sources':data.pop('native_source_paths')
    with pytest.raises(ValueError):module().build_capture(candidate,data,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2))


def test_monitoring_report_is_visible_without_promoting_confidence(tmp_path,monkeypatch):
    candidate,inputs=context(tmp_path,monkeypatch)
    report={'schema':'earthship-provisional-thermal-performance/v1','artifact_sha256':candidate['artifact_sha256'],'graduated':False,'assessed_at':ISSUE.isoformat(),
        'by_horizon':{str(h):{key:{'count':1,'mae_f':.5,'bias_f':.1} for key in ('model','persistence','recent_cycle')} for h in (1,6,12,24)}}
    capture=module().build_capture(candidate,inputs,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2),monitoring_report=report)
    payload=module().publication(capture)
    assert payload['confidence']['grade']=='low'
    assert any('MAE' in reason for reason in payload['reasons'])
    report['artifact_sha256']='f'*64
    with pytest.raises(ValueError):module().build_capture(candidate,inputs,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2),monitoring_report=report)


def test_monitoring_report_expires_after_fifteen_minutes():
    from thermal_model.provisional_score import summarize
    report=summarize([],artifact_sha256='a'*64)
    report['assessed_at']=(ISSUE-timedelta(minutes=15,seconds=1)).isoformat()
    with pytest.raises(ValueError):module()._validate_report(report,'a'*64,ISSUE)


def test_phased_issue_preserves_preissue_input_clock_and_exact_hourly_trajectory(tmp_path,monkeypatch):
    from test_installed_shade_origin import weather
    monkeypatch.setattr(module(),'replay_binding',lambda *a,**k:None)
    candidate,inputs=context(tmp_path,monkeypatch);issue=ISSUE+timedelta(seconds=15)
    inputs['forecast']=weather(issue);inputs['action_snapshot']['origin']=issue
    capture=module().build_capture(candidate,inputs,issue=issue,available=ISSUE,published=issue+timedelta(seconds=2))
    assert capture['issued_at']==issue.isoformat()
    assert capture['output']['trajectory'][0]['at']==(issue+timedelta(hours=1)).isoformat()
    assert module().validate_capture(capture)==capture
    with pytest.raises(ValueError):module().build_capture(candidate,inputs,issue=issue,available=issue+timedelta(seconds=1),published=issue+timedelta(seconds=2))


def test_phased_origin_replays_original_compressed_query_packets(tmp_path,monkeypatch):
    from test_installed_shade_raw_score_sources import origin_inputs,compressed_inputs
    from thermal_model.installed_shade_raw_score_sources import build_compressed_native_origin_binding,replay_compressed_native_origin_binding
    args=compressed_inputs(origin_inputs(tmp_path,monkeypatch))
    observed=module()._utc(args['origin_temperatures']['assessed_at'])
    args['issue_at']=observed.replace(minute=observed.minute//5*5,second=0,microsecond=0)+timedelta(minutes=5,seconds=15)
    binding=build_compressed_native_origin_binding(**args)
    assert replay_compressed_native_origin_binding(binding,args['origin_temperatures'],issue_at=args['issue_at'])==binding
    with pytest.raises(ValueError):replay_compressed_native_origin_binding(binding,args['origin_temperatures'],issue_at=args['issue_at']+timedelta(seconds=1))
