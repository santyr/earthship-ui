from copy import deepcopy
from datetime import timedelta
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_profiled_outcomes import case,originals
from test_household_calibrated_energy import calibration


def context(tmp_path,monkeypatch,originals):
    from household_calibrated_energy import seal
    from household_calibrated_outcomes import seal_outcomes
    _,old=case(tmp_path,monkeypatch,originals)
    energy,plan,profile=old['energy_receipt'],old['plan_receipt'],old['profiled_receipt']
    forecast=seal(energy=energy,plan=plan,profiled=profile,calibration_path=calibration(tmp_path,energy),now=instant(energy['inputs']['assessed_at']))
    return seal_outcomes,dict(forecast=forecast,energy=energy,plan=plan,profiled=profile,
        hour_sources=old['hour_sources'],endpoint_sources=old['endpoint_sources'],assessed_at=old['assessed_at'])


def test_calibrated_and_raw_storage_share_one_actual_target_and_preserve_forecasts(tmp_path,monkeypatch,originals):
    from household_calibrated_outcomes import replay_outcomes
    api,args=context(tmp_path,monkeypatch,originals);before=canonical(args['forecast']);score=api(**args)
    row=score['output']['by_horizon']['1'];soc=row['soc'];load=row['load']
    assert soc['status']=='scored' and soc['actual_soc_pct']==95
    assert set(soc['predictions_soc_pct'])=={'calibrated_pv','raw_pv','hold_soc'}
    expected=args['forecast']['output']['profiled_storage']['trajectory'][0]['nominal_soc_pct']
    assert soc['predictions_soc_pct']['calibrated_pv']==expected
    assert soc['errors_soc_pct']['calibrated_pv']==pytest.approx(expected-95)
    assert load['status']=='scored' and load['coverage']==1 and load['actual_known_ac_kwh']==pytest.approx(1)
    assert score['output']['by_horizon']['6']['soc']['status']=='not_mature'
    assert score['output']['automatic_actuation'] is False and score['output']['physical_calibration_qualified'] is False
    assert score['output']['pv_energy_accuracy']=='unavailable_unmatched_meter_scope'
    assert canonical(args['forecast'])==before
    assert replay_outcomes(score,**{k:v for k,v in args.items() if k in ('forecast','energy','plan','profiled')})==score


def test_missing_or_unqualified_sources_do_not_become_zero_error(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);args['hour_sources']={}
    source=args['endpoint_sources']['1'];source['rows'][0][1]=None
    source['source_sha256']=identity({k:v for k,v in source.items() if k!='source_sha256'})
    row=api(**args)['output']['by_horizon']['1']
    assert row['load']['status']=='pending_source' and row['load']['errors_kwh'] is None
    assert row['soc']['status']=='source_unavailable' and row['soc']['errors_soc_pct'] is None


def test_partial_ac_hour_is_not_a_full_hour_accuracy_sample(tmp_path,monkeypatch,originals):
    from household_ac_load_window import build_hour_source
    from test_household_ac_load_sources import raw
    api,args=context(tmp_path,monkeypatch,originals);source=args['hour_sources']['1'];start=instant(source['window_start']);end=instant(source['window_end'])
    args['hour_sources']['1']=build_hour_source(rows=[(start,raw(start))],start=start,end=end,
        requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=613)
    load=api(**args)['output']['by_horizon']['1']['load']
    assert load['status']=='insufficient_coverage' and load['coverage']==30/3600
    assert load['actual_known_ac_kwh']==pytest.approx(30/3600) and load['errors_kwh'] is None


@pytest.mark.parametrize('damage',['forecast','source','error','runtime'])
def test_resealed_changes_cannot_rewrite_calibrated_outcomes(tmp_path,monkeypatch,originals,damage):
    from household_calibrated_outcomes import replay_outcomes
    api,args=context(tmp_path,monkeypatch,originals);score=api(**args)
    if damage=='forecast':score['inputs']['forecast_document_sha256']='f'*64
    elif damage=='source':score['inputs']['endpoint_sources']['1']['rows'][0][1]='changed'
    elif damage=='error':score['output']['by_horizon']['1']['soc']['errors_soc_pct']['calibrated_pv']=0
    else:score['runtime_manifest'][next(iter(score['runtime_manifest']))]='f'*64
    score['receipt_sha256']=identity({k:v for k,v in score.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_outcomes(score,**{k:v for k,v in args.items() if k in ('forecast','energy','plan','profiled')})


def test_curated_accuracy_uses_verified_same_cohort_samples_and_keeps_unavailable_counts(tmp_path,monkeypatch,originals):
    from household_calibrated_outcomes import summarize_score,performance,validate_sample
    api,args=context(tmp_path,monkeypatch,originals);score=api(**args)
    sample=summarize_score(score,verified_at=args['assessed_at'],score_file_sha256='a'*64)
    assert validate_sample(sample)==sample
    report=performance([sample],origin=score['inputs']['origin'],generated_at=args['assessed_at'])
    one=report['by_horizon']['1'];six=report['by_horizon']['6']
    assert one['soc']['count']==one['soc']['attempted_count']==1
    assert one['soc']['mae_soc_pct']['calibrated_pv']==score['output']['by_horizon']['1']['soc']['absolute_errors_soc_pct']['calibrated_pv']
    assert six['soc']['count']==six['soc']['attempted_count']==0 and six['soc']['mae_soc_pct']['calibrated_pv'] is None
    assert report['automatic_actuation'] is False and report['calibration_model_sha256']==score['output']['calibration_model_sha256']
    damaged=deepcopy(sample);damaged['output']['by_horizon']['1']['soc']['errors_soc_pct']['raw_pv']+=1
    damaged['sample_sha256']=identity({k:v for k,v in damaged.items() if k!='sample_sha256'})
    with pytest.raises(ValueError):validate_sample(damaged)


def test_original_context_is_resolved_by_document_hash_not_current_forecast(tmp_path,monkeypatch,originals):
    from household_calibrated_score import resolve_originals
    api,args=context(tmp_path,monkeypatch,originals)
    stage=tmp_path/'stage';directory=stage/'evidence';directory.mkdir(parents=True,mode=0o700);stage.chmod(0o700)
    paths=[]
    for value,suffix in [(args['energy'],'.household-energy-forecast-v1.json'),(args['plan'],'.household-model-plan-v6.json'),(args['profiled'],'.household-profiled-energy-v1.json')]:
        path=directory/(identity(value)+suffix);path.write_bytes(canonical(value));path.chmod(0o600);paths.append(path)
    energy,plan,profile,reference=resolve_originals(args['forecast'],stages=[stage])
    assert energy==args['energy'] and plan==args['plan'] and profile==args['profiled']
    assert reference['energy_path']==str(paths[0]) and reference['profiled_path']==str(paths[2])
    paths[0].write_bytes(b'{}')
    with pytest.raises(ValueError):resolve_originals(args['forecast'],stages=[stage])


def test_all_four_mature_horizons_use_their_own_qualified_windows(tmp_path,monkeypatch,originals):
    from household_ac_load_window import build_hour_source
    from household.battery_outcomes import build_endpoint_source
    from test_household_ac_load_sources import raw
    from local_measurement_test_support import bms_evidence
    api,args=context(tmp_path,monkeypatch,originals);issue=instant(args['forecast']['output']['issued_at']);assessed=issue+timedelta(hours=24,minutes=6)
    args.update(assessed_at=assessed,hour_sources={},endpoint_sources={})
    for h in (1,6,12,24):
        end=issue+timedelta(hours=h);start=end-timedelta(hours=1)
        args['hour_sources'][str(h)]=build_hour_source(rows=[(start+timedelta(seconds=30*i),raw(start+timedelta(seconds=30*i),i+1)) for i in range(120)],
            start=start,end=end,requested_at=assessed-timedelta(seconds=2),received_at=assessed-timedelta(seconds=1),item_id=613)
        args['endpoint_sources'][str(h)]=build_endpoint_source(rows=[(end-timedelta(seconds=2),bms_evidence(end-timedelta(seconds=20),soc=90))],
            target_at=end,requested_at=assessed-timedelta(seconds=2),received_at=assessed-timedelta(seconds=1),item_id=614)
    out=api(**args)['output']['by_horizon']
    for h in (1,6,12,24):
        row=out[str(h)]
        assert instant(row['target_at'])==issue+timedelta(hours=h)
        assert row['soc']['status']=='scored' and row['soc']['actual_soc_pct']==90
        assert row['load']['status']=='scored' and row['load']['actual_known_ac_kwh']==pytest.approx(1)


def test_accuracy_exposes_the_policy_and_does_not_reuse_another_policy_samples(tmp_path,monkeypatch,originals):
 from household_calibrated_outcomes import summarize_score,performance
 from weather_learning.pv_calibration_policy import POLICY_SHA256
 api,args=context(tmp_path,monkeypatch,originals);score=api(**args);origin=score['inputs']['origin']
 assert origin['cohort']['calibration_policy_sha256']==POLICY_SHA256
 sample=summarize_score(score,verified_at=args['assessed_at'],score_file_sha256='a'*64)
 report=performance([sample],origin=origin,generated_at=args['assessed_at'])
 assert report['schema']=='earthship-household-calibrated-energy-performance/v2'
 assert report['calibration_policy_sha256']==POLICY_SHA256
 other=deepcopy(origin);other['cohort']['calibration_policy_sha256']='f'*64;other['cohort_id']=identity(other['cohort'])
 assert performance([sample],origin=other,generated_at=args['assessed_at'])['by_horizon']['1']['soc']['count']==0
