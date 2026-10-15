"""Compact verified samples preserve replayable originals and score arithmetic."""
import importlib
import pytest
from household.codec import identity
from test_household_pv_outcomes import context,originals


def test_compact_verification_preserves_errors_without_duplicating_raw_history(tmp_path,monkeypatch,originals):
    api=importlib.import_module('household_pv_samples');outcomes,args=context(tmp_path,monkeypatch,originals);score=outcomes.seal_pv_outcomes(**args)
    sample=api.summarize_verified_score(score,verified_at=args['assessed_at'])
    assert sample['score_document_sha256']==identity(score) and sample['output']==score['output']
    assert 'hour_sources' not in sample['inputs'] and sample['hour_source_pins']['1']==score['inputs']['hour_sources']['1']['source_sha256']
    report=outcomes.build_performance([sample],cohort=score['output']['cohort'],generated_at=args['assessed_at'],next_mature_at=None)
    assert report['by_horizon']['1']['models']['constant_load_pv']['count']==1


@pytest.mark.parametrize('damage',['error','coverage','target','authority','pin'])
def test_resealed_compact_sample_rejects_changed_errors_coverage_or_gates(tmp_path,monkeypatch,originals,damage):
    api=importlib.import_module('household_pv_samples');outcomes,args=context(tmp_path,monkeypatch,originals);score=outcomes.seal_pv_outcomes(**args);sample=api.summarize_verified_score(score,verified_at=args['assessed_at']);row=sample['output']['by_horizon']['1']
    if damage=='error':row['errors_kwh']['constant_load_pv']+=1
    elif damage=='coverage':row['covered_seconds']-=1
    elif damage=='target':row['target_at']=row['window_start']
    elif damage=='authority':sample['output']['automatic_actuation']=True
    else:sample['hour_source_pins'].clear()
    sample['sample_sha256']=identity({k:v for k,v in sample.items() if k!='sample_sha256'})
    with pytest.raises(ValueError):api.validate_sample(sample)
