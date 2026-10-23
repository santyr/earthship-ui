"""Matched solar experiments need past-only fits and independent-target support."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import importlib,json
import pytest
from weather_learning.contracts import identity

T=datetime(2026,1,1,12,tzinfo=timezone.utc)
PROTOCOL=json.loads((Path(__file__).resolve().parents[4]/'docs/operations/weathernext3-capabilities/evaluation-protocol.json').read_text())
def api():return importlib.import_module('weather_learning.solar_evaluation')
def seal(r):r['pair_sha256']=identity({k:v for k,v in r.items() if k!='pair_sha256'});return r

def rows():
    out=[]
    for day in range(9):
        for i in range(16):
            start=T+timedelta(days=day,minutes=5*i);origin=start.replace(hour=0,minute=0)
            r=dict(start=start.isoformat(),end=(start+timedelta(minutes=5)).isoformat(),origin=origin.isoformat(),
                native_w=80.,total_only_w=100.,outcome_w=100.,fixed_gain=1.,fixed_gain_source_sha256=None,
                forecast_sha256=identity(('forecast',day)),energy_source_sha256=identity(('energy',day,i)),
                outcome_available_at=(start+timedelta(minutes=10)).isoformat(),cohort_sha256='c'*64,
                availability_basis='retrospective_assumed_full_cycle_9h',native_supported=True,fallback_reason=None,azimuth_degrees=180.)
            out.append(seal(r))
    return out

def assess(data=None,**kwargs):
    return api().assess_pv_components(rows() if data is None else data,timezone_name='UTC',protocol=PROTOCOL,**kwargs)


def test_fixed_electrical_comparison_precedes_matched_separate_refits():
    r=assess()
    assert r['outer_dates']==['2026-01-07','2026-01-08','2026-01-09']
    assert r['fallback_inclusive']['fixed_total']['mae']==0
    assert r['fallback_inclusive']['fixed_native']['mae']==20
    assert r['fallback_inclusive']['refit_total']['mae']==pytest.approx(0)
    assert r['fallback_inclusive']['refit_native']['mae']==pytest.approx(0)
    assert r['models'][0]['total_only']['gain']==pytest.approx(1)
    assert r['models'][0]['native']['gain']==pytest.approx(1.25)
    assert r['models'][0]['total_only']['model_sha256']!=r['models'][0]['native']['model_sha256']
    assert r['disposition']=='retain_incumbent' and r['automatic_promotion'] is False
    assert r['prospective_score'] is False and r['physical_calibration_qualified'] is False


def test_extra_forecasts_for_one_target_do_not_inflate_dates_or_target_support():
    source=rows();a=assess(source)
    duplicated=[]
    for r in source:
        second=deepcopy(r);second['forecast_sha256']=identity(('second',r['forecast_sha256']));second['origin']=(datetime.fromisoformat(r['origin'])-timedelta(hours=1)).isoformat();duplicated.extend([r,seal(second)])
    b=assess(duplicated)
    assert b['support']['outer_targets']==48 and b['support']['outer_forecast_pairs']==96
    assert b['fallback_inclusive']['fixed_native']['mae']==a['fallback_inclusive']['fixed_native']['mae']
    assert b['support']['outer_local_dates']==3


def test_outer_outcomes_cannot_enter_the_first_outer_fit():
    source=rows();a=assess(source)
    for r in source:
        if r['start'][:10]>='2026-01-07':r['outcome_w']=150;seal(r)
    b=assess(source)
    assert b['models'][0]==a['models'][0]
    assert all(p['target_end']<p['decision_origin'] for p in b['training_audit'])


def test_operational_training_excludes_late_discovered_outcomes():
    source=rows()
    for r in source:
        r['outcome_available_at']=(T+timedelta(days=20)).isoformat();r['availability_basis']='recorded_operational_original';seal(r)
    result=assess(source,evidence_class='operational_originals')
    assert result['models']==[] and result['disposition']=='insufficient_evidence'
    assert all(p['refit_native_w'] is None for p in result['predictions'])


def test_missing_native_support_stays_in_fallback_inclusive_comparison():
    source=rows()
    for r in source:r['native_supported']=False;r['fallback_reason']='native_direct_unavailable';r['native_w']=100.;seal(r)
    result=assess(source)
    assert result['support']['outer_targets']==48 and result['matched_native']['support']['targets']==0
    assert result['fallback_reasons']=={'native_direct_unavailable':144}
    assert result['disposition']=='insufficient_evidence'


@pytest.mark.parametrize('change',[{'outcome_w':110},{'energy_source_sha256':'a'*64}])
def test_conflicting_receipts_for_the_same_target_are_rejected(change):
    source=rows();duplicate=deepcopy(source[0]);duplicate.update(change);duplicate['forecast_sha256']='f'*64;source.append(seal(duplicate))
    with pytest.raises(ValueError):assess(source)


def test_epoch_or_policy_cohorts_cannot_be_pooled():
    source=rows();source[-1]['cohort_sha256']='d'*64;seal(source[-1])
    with pytest.raises(ValueError):assess(source)
