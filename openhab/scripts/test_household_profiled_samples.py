"""Verified compact samples report all as-issued daily models without refitting."""
from copy import deepcopy
from datetime import timedelta
from household.codec import identity
from test_household_profiled_outcomes import case,originals
import importlib
import pytest


def sample(tmp_path,monkeypatch,originals):
    scores,args=case(tmp_path,monkeypatch,originals);score=scores.seal_profiled_outcomes(**args)
    api=importlib.import_module('household_profiled_samples');value=api.summarize_verified_score(score,verified_at=args['assessed_at'])
    return api,value,score,args


def test_verified_summary_preserves_scalar_outcomes_and_original_receipt_pins(tmp_path,monkeypatch,originals):
    api,value,score,args=sample(tmp_path,monkeypatch,originals)
    assert value['score_document_sha256']==identity(score) and value['score_receipt_sha256']==score['receipt_sha256']
    assert value['output']==score['output'] and 'hour_sources' not in str(value) and 'reference_score' not in value
    assert api.validate_sample(value)==value
    report=api.build_performance([value,value],cohort=value['output']['cohort'],generated_at=args['assessed_at'],next_mature_at=None)
    assert report['by_horizon']['1']['load']['count']==1 and report['by_horizon']['1']['soc']['count']==1
    assert report['by_horizon']['1']['load']['unique_origin_days']==1
    assert report['by_horizon']['1']['load']['mae_kwh']['current_load']==pytest.approx(0,abs=1e-12)
    assert report['by_horizon']['6']['load']['count']==0 and report['by_horizon']['6']['load']['mae_kwh'] is None
    assert report['model_version_count']==1 and report['evaluation_scope']=='rolling_as_issued_model_versions'
    assert report['physical_calibration_qualified'] is False and report['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['error','actual','target','coverage','prediction','hash','future'])
def test_resealed_summary_cannot_change_arithmetic_or_quality_clocks(tmp_path,monkeypatch,originals,damage):
    api,value,score,args=sample(tmp_path,monkeypatch,originals)
    if damage=='error':value['output']['load_by_horizon']['1']['errors_kwh']['current_load']=9
    elif damage=='actual':value['output']['soc_by_horizon']['1']['actual_soc_pct']=0
    elif damage=='target':value['output']['load_by_horizon']['1']['target_at']=value['output']['load_by_horizon']['6']['target_at']
    elif damage=='coverage':value['output']['load_by_horizon']['1']['coverage']=.5
    elif damage=='prediction':value['output']['soc_by_horizon']['1']['predictions_soc_pct']['hold_soc']=0
    elif damage=='hash':value['score_document_sha256']='invalid'
    else:value['verified_at']=(args['assessed_at']-timedelta(seconds=1)).isoformat()
    value['sample_sha256']=identity({k:v for k,v in value.items() if k!='sample_sha256'})
    with pytest.raises(ValueError):api.validate_sample(value)


def test_daily_model_versions_share_algorithm_cohort_and_keep_independent_day_counts(tmp_path,monkeypatch,originals):
    api,first,score,args=sample(tmp_path,monkeypatch,originals);second=deepcopy(first)
    from household.control_contracts import instant
    def later(value):return (instant(value)+timedelta(days=1)).isoformat()
    second['score_assessed_at']=later(second['score_assessed_at']);second['verified_at']=later(second['verified_at'])
    second['output']['origin']['issued_at']=later(second['output']['origin']['issued_at']);second['reference_origin']['issued_at']=later(second['reference_origin']['issued_at'])
    second['output']['origin']['model_artifact_sha256']='b'*64;second['output']['origin']['model_sha256']='c'*64
    second['score_document_sha256']='d'*64;second['score_receipt_sha256']='e'*64;second['profiled_receipt_sha256']='f'*64
    for rows in (second['output']['load_by_horizon'],second['output']['soc_by_horizon']):
        for row in rows.values():
            row['target_at']=later(row['target_at'])
            if 'window_start' in row:row['window_start']=later(row['window_start'])
    second['sample_sha256']=identity({k:v for k,v in second.items() if k!='sample_sha256'})
    api.validate_sample(second)
    report=api.build_performance([first,second],cohort=first['output']['cohort'],generated_at=instant(second['verified_at']),next_mature_at=None)
    assert report['model_version_count']==2
    assert report['by_horizon']['1']['load']['count']==2 and report['by_horizon']['1']['load']['unique_origin_days']==2
    assert report['by_horizon']['1']['soc']['count']==2 and report['by_horizon']['1']['soc']['model_version_count']==2
    assert report['by_horizon']['1']['load']['mae_kwh']==first['output']['load_by_horizon']['1']['absolute_errors_kwh']
