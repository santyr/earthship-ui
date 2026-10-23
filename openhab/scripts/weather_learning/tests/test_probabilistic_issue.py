"""Shadow marginal issues bind original native inputs and known origin context."""
from dataclasses import replace
from datetime import timedelta
import importlib.util
import pytest
from learning_fixtures import T,EPOCH,SITE,native_snapshot,receipt
from test_probabilistic import POLICY,pairs


def api():
    assert importlib.util.find_spec('weather_learning.probabilistic_issue'), 'Task7 original prospective issue compiler missing'
    from weather_learning import probabilistic_issue
    return probabilistic_issue


def context():
    decision=T+timedelta(days=15,hours=9)
    return api().temperature_context(receipt(decision),sampled_at=decision,acquired_at=decision,sensor_epoch=EPOCH)


def issue(*,with_model=True,**kwargs):
    from weather_learning.probabilistic_retained import prepare_marginal_source
    from weather_learning.probabilistic_artifacts import fit_candidates
    s=native_snapshot(day=15,hours=360);decision=T+timedelta(days=15,hours=9);ctx=context();f=prepare_marginal_source(s,assessed_at=decision).forecast('temperature',target=decision+timedelta(hours=1),quality=ctx.quality_at(decision),origin=decision)
    rows=[replace(p,forecast=replace(p.forecast,cohort_sha256=f.cohort_sha256,grid_sha256=f.grid_sha256)) for p in pairs()]
    bundle=fit_candidates(rows,cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,population_sha256='a'*64).bundle
    args=dict(snapshots=[s],decision=decision,site=SITE,contexts={'temperature':ctx},bundles=[bundle] if with_model else [],policy=POLICY)
    args.update(kwargs);return api().prepare_marginal_issue(**args)


def test_original_shadow_issue_keeps_raw_range_and_locally_generated_marginals_separate():
    prepared=issue();body=prepared.to_dict();rows=[r for r in body['rows'] if r['forecast']['kind']=='temperature'];first=rows[0]
    assert len(rows)==30
    assert first['raw']['mean']==pytest.approx(10.) and first['raw']['p10']==pytest.approx(8.)
    assert first['raw']['p50'] is None
    assert first['candidates']['marginals']['temperature_normal']['mean']==pytest.approx(12,abs=.5)
    assert first['candidates']['marginals']['empirical']['mean'] is None
    assert first['candidates']['marginals']['empirical']['point_estimate_kind']=='model_median'
    assert body['issued'] is False and body['core_forecast_modified'] is False
    assert body['local_coverage_qualified'] is False and body['automatic_actuation'] is False
    assert len(body['bundle_originals'])==1 and len(body['source_originals'])==1


def test_cold_bundle_or_missing_origin_context_never_withdraws_raw_future_hours():
    cold=issue(with_model=False).to_dict();unknown=issue(contexts={}).to_dict()
    assert len(cold['rows'])==len(unknown['rows'])==30
    assert cold['rows'][0]['candidates']['reason']=='candidate_bundle_unavailable'
    assert unknown['rows'][0]['candidates']['reason']=='origin_measurement_context_unavailable'
    assert all(r['raw']['p10']==pytest.approx(8.) for r in unknown['rows'])


def test_origin_context_cannot_be_acquired_after_decision_or_outlive_native_receipt():
    decision=T+timedelta(days=15,hours=9);ctx=context()
    with pytest.raises(ValueError,match='origin|available'):
        ctx.quality_at(decision-timedelta(seconds=1))
    with pytest.raises(ValueError,match='origin|expired|lifetime'):
        ctx.quality_at(decision+timedelta(minutes=3))
    with pytest.raises(ValueError,match='acquisition|persisted'):
        api().temperature_context(receipt(decision),sampled_at=decision,acquired_at=decision-timedelta(seconds=6),sensor_epoch=EPOCH)


def test_issue_replay_uses_copied_fitted_values_and_rejects_rehashed_prediction_changes():
    prepared=issue();rebuilt=api().validate_marginal_issue(prepared.to_dict(),policy=POLICY,replay=True)
    assert rebuilt==prepared.to_dict()
    changed=prepared.to_dict();changed['rows'][0]['candidates']['marginals']['temperature_normal']['mean']+=1
    from weather_learning.contracts import identity
    changed['issue_sha256']=identity({k:v for k,v in changed.items() if k!='issue_sha256'})
    with pytest.raises(ValueError,match='original|prediction|replay'):
        api().validate_marginal_issue(changed,policy=POLICY,replay=True)


def test_historical_or_not_yet_available_sources_cannot_become_prospective_issues():
    source=native_snapshot(day=15,hours=360);source['historical']=True
    body=issue(snapshots=[source]).to_dict()
    assert body['rows']==[] and body['status']=='raw_unavailable'
    early=issue(decision=T+timedelta(days=15)).to_dict()
    assert early['rows']==[]


def test_fixed_scoring_offsets_are_independent_of_display_row_count():
    body=issue().to_dict();targets=api().scoring_rows(body)
    assert len(body['rows'])==30
    assert len(targets)==11
    assert sorted(r['offset'] for r in targets)==[1,3,6,12,24,48,72,120,168,240,336]
    assert all(r['forecast']['target_end']>body['decision_at'] for r in targets)


def test_incompatible_optional_bundle_keeps_raw_issue_independently_available():
    from weather_learning.probabilistic_artifacts import CandidateBundle
    from weather_learning.probabilistic import _freeze
    original=issue().to_dict();body=next(iter(original['bundle_originals'].values()));body.pop('bundle_sha256')
    body['numerical_manifest']['openhab/scripts/weather_learning/probabilistic_retained.py']='f'*64
    broken=_freeze(CandidateBundle,body,'bundle_sha256')
    prepared=issue(bundles=[broken]).to_dict()
    assert len(prepared['rows'])==30
    assert all(row['raw']['mean']==pytest.approx(10.) for row in prepared['rows'])
    assert prepared['status']=='raw_fallback'
    assert prepared['withheld']['candidate_temperature']=='candidate_numeric_runtime_changed'


def test_contiguous_lead_candidate_issues_use_fine_forecast_identity_and_replay():
    from weather_learning.probabilistic_artifacts import fit_candidates
    from weather_learning.contracts import identity
    original=issue().to_dict();first=original['rows'][0]['forecast']
    partition=dict(method='contiguous_whole_native_leads_greedy_capacity/v1',parent_cohort_sha256=first['cohort_sha256'],lower_exclusive_hours=0.,upper_inclusive_hours=2.)
    fine=identity(partition)
    rows=[replace(p,forecast=replace(p.forecast,cohort_sha256=fine,grid_sha256=first['grid_sha256'])) for p in pairs()]
    bundle=fit_candidates(rows,cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,population_sha256='a'*64,partition=partition).bundle
    body=issue(bundles=[bundle]).to_dict()
    assert [r['candidates']['status'] for r in body['rows'][:3]]==['read_only_shadow_candidates','read_only_shadow_candidates','raw_fallback']
    assert body['rows'][0]['forecast']['cohort_sha256']==fine
    prediction=body['rows'][0]['candidates']['marginals']['temperature_normal']
    assert prediction['input_sha256']==body['rows'][0]['forecast']['input_sha256']
    assert api().validate_marginal_issue(body,policy=POLICY,replay=True)==body
