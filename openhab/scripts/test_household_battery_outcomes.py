"""Chronological battery endpoint errors retain original atomic barriers."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import importlib
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_energy_persistence import pipeline_fixture
from local_measurement_test_support import bms_evidence as evidence


def api():return importlib.import_module('household.battery_outcomes')


def context(tmp_path,monkeypatch):
    _,plan,runtime,thermal=pipeline_fixture(tmp_path,monkeypatch)
    issue=instant(plan['inputs']['snapshot']['as_of']);target=issue+timedelta(hours=1);requested=target+timedelta(minutes=5)
    rows=[(target-timedelta(seconds=2),evidence(target-timedelta(seconds=20),soc=95)),
          (target-timedelta(seconds=30),evidence(target-timedelta(seconds=40),soc=96))]
    return plan,runtime,thermal,target,requested,rows


def packet(target,requested,rows):
    return api().build_endpoint_source(rows=rows,target_at=target,requested_at=requested,received_at=requested+timedelta(seconds=1),item_id=613)


def seal(plan,runtime,thermal,target,requested,rows):
    return api().seal_battery_outcomes(plan_receipt=plan,endpoint_sources={'1':packet(target,requested,rows)},
        assessed_at=requested+timedelta(seconds=2),plan_runtime_manifest=runtime,outcome_runtime_manifest=runtime,
        thermal_runtime=thermal.to_dict()['executing_runtime'])


def test_mature_original_endpoint_compares_constant_power_and_hold_soc(tmp_path,monkeypatch):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch);score=seal(plan,runtime,thermal,target,requested,rows)
    first=score['output']['by_horizon']['1']
    assert first['status']=='scored' and first['actual_soc_pct']==95
    assert first['predictions_soc_pct']=={'constant_power':97.55859375,'hold_soc':100.}
    assert first['errors_soc_pct']=={'constant_power':2.55859375,'hold_soc':5.}
    assert score['inputs']['plan_receipt_sha256']==plan['receipt_sha256']
    assert score['inputs']['plan_document_sha256']==sha256(canonical(plan)).hexdigest()
    assert 'plan_receipt' not in score['inputs']
    assert score['output']['by_horizon']['6']['status']=='not_mature'
    assert score['output']['causal_benefit_qualified'] is False and score['output']['automatic_actuation'] is False
    assert api().replay_battery_outcomes(score,plan_receipt=plan,plan_runtime_manifest=runtime,
        outcome_runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])==score


@pytest.mark.parametrize('damage',['null','malformed','expired','phase'])
def test_latest_barrier_never_falls_back_to_older_good_soc(tmp_path,monkeypatch,damage):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch)
    if damage=='null':rows[0]=(rows[0][0],None)
    elif damage=='malformed':rows[0]=(rows[0][0],'{}')
    elif damage=='expired':rows[0]=(target-timedelta(seconds=2),evidence(target-timedelta(seconds=120),soc=95))
    else:
        raw=loads(rows[0][1]);raw['streamEpoch']='00000000-0000-0000-0000-000000000002';rows[0]=(rows[0][0],canonical(raw).decode())
    score=seal(plan,runtime,thermal,target,requested,rows);first=score['output']['by_horizon']['1']
    assert first['status']=='source_unavailable' and first['actual_soc_pct'] is None
    assert first['predictions_soc_pct'] is None and first['errors_soc_pct'] is None
    assert score['inputs']['endpoint_sources']['1']['rows'][0][1]==rows[0][1]


@pytest.mark.parametrize('damage',['tie','future_row','reversed','oversize','too_many','wrong_item'])
def test_endpoint_source_refuses_ambiguous_or_out_of_window_originals(tmp_path,monkeypatch,damage):
    _,_,_,target,requested,rows=context(tmp_path,monkeypatch)
    if damage=='tie':rows[1]=(rows[0][0],rows[1][1])
    elif damage=='future_row':rows[0]=(target+timedelta(seconds=1),rows[0][1])
    elif damage=='reversed':rows.reverse()
    elif damage=='oversize':rows[0]=(rows[0][0],'x'*4097)
    elif damage=='too_many':rows+=rows
    else:
        with pytest.raises(ValueError):api().build_endpoint_source(rows=rows,target_at=target,requested_at=requested,received_at=requested,item_id=-1)
        return
    with pytest.raises(ValueError):packet(target,requested,rows)


def test_immature_endpoint_has_no_measurement_or_premature_source(tmp_path,monkeypatch):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch)
    kwargs=dict(plan_receipt=plan,assessed_at=target+timedelta(minutes=4),plan_runtime_manifest=runtime,outcome_runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    score=api().seal_battery_outcomes(endpoint_sources={},**kwargs)
    assert score['output']['by_horizon']['1']['status']=='not_mature'
    with pytest.raises(ValueError):api().seal_battery_outcomes(endpoint_sources={'1':packet(target,requested,rows)},**kwargs)


@pytest.mark.parametrize('damage',['output','source','plan'])
def test_rehashed_score_changes_refuse_against_original_plan(tmp_path,monkeypatch,damage):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch);score=seal(plan,runtime,thermal,target,requested,rows)
    if damage=='output':score['output']['by_horizon']['1']['actual_soc_pct']=0
    elif damage=='source':score['inputs']['endpoint_sources']['1']['source_sha256']='f'*64
    else:plan=deepcopy(plan);plan['receipt_sha256']='f'*64
    score['receipt_sha256']=identity({k:v for k,v in score.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api().replay_battery_outcomes(score,plan_receipt=plan,plan_runtime_manifest=runtime,
        outcome_runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])


def test_report_deduplicates_forecasts_and_labels_day_units(tmp_path,monkeypatch):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch);score=seal(plan,runtime,thermal,target,requested,rows)
    report=api().build_performance([score,score],cohort=score['output']['cohort'],generated_at=requested+timedelta(seconds=3),next_mature_at=target+timedelta(hours=5,minutes=5))
    first=report['by_horizon']['1']
    assert first['count']==1 and first['unique_origin_days']==1
    assert first['mae_soc_pct']=={'constant_power':2.55859375,'hold_soc':5.}
    assert report['by_horizon']['6']['count']==0 and report['by_horizon']['6']['mae_soc_pct'] is None
    assert report['sampling_basis']=='one_origin_per_utc_hour'
    assert report['validation_scope']=='sealed_producer_endpoint_pairs'
    assert report['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['authority','nonfinite','wrong_reason','immature_terminal','extra_output','extra_row'])
def test_report_refuses_rehashed_invalid_producer_pairs(tmp_path,monkeypatch,damage):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch);score=seal(plan,runtime,thermal,target,requested,rows)
    changed=deepcopy(score);out=changed['output'];row=out['by_horizon']['1']
    if damage=='authority':out['automatic_actuation']=True
    elif damage=='nonfinite':out['origin']['battery_power_w']=float('inf')
    elif damage=='wrong_reason':row['status']='source_unavailable';row['reason']='invented';row['actual_soc_pct']=None;row['predictions_soc_pct']=None;row['errors_soc_pct']=None;row['absolute_errors_soc_pct']=None
    elif damage=='immature_terminal':out['by_horizon']['6']=deepcopy(row);out['by_horizon']['6'].update(horizon_hours=6,target_at=(target+timedelta(hours=5)).isoformat())
    elif damage=='extra_output':out['private_path']='private'
    else:row['extra']=1
    if damage=='nonfinite':
        with pytest.raises(ValueError):changed['receipt_sha256']=identity({k:v for k,v in changed.items() if k!='receipt_sha256'})
        return
    changed['receipt_sha256']=identity({k:v for k,v in changed.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api().build_performance([changed],cohort=score['output']['cohort'],generated_at=requested+timedelta(seconds=3),next_mature_at=None)
