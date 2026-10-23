"""Chronological, matched marginal comparisons with literal retained predictions."""
from dataclasses import replace
from datetime import timedelta
import importlib.util
import pytest
from learning_fixtures import T
from test_probabilistic import POLICY,pairs


def api():
    assert importlib.util.find_spec('weather_learning.probabilistic_evaluation'), 'Task7 chronological marginal evaluator missing'
    from weather_learning import probabilistic_evaluation
    return probabilistic_evaluation


def assess(rows=None):
    return api().assess_marginals(pairs(days=45) if rows is None else rows,policy=POLICY,completed_at=T+timedelta(days=90))


def test_outer_predictions_are_original_immutable_values_and_scores_have_real_support():
    report=assess();cohort=report['cohorts'][0]
    assert cohort['outer_support']==dict(pairs=60,targets=60,local_dates=15)
    assert set(cohort['comparisons'])=={'temperature_normal_vs_raw','temperature_normal_vs_empirical','empirical_vs_raw','adaptive_vs_incumbent'}
    score=cohort['comparisons']['temperature_normal_vs_raw']
    assert score['matched']['support']['targets']>=48
    assert score['matched']['candidate']['mae']<.4
    assert score['matched']['baseline']['mae']>2
    assert score['matched']['candidate']['crps'] is not None
    assert score['matched']['baseline']['crps'] is None
    assert score['matched']['baseline']['wis'] is None
    assert score['matched']['candidate']['wis'] is not None
    assert score['probability_claim'] is False and score['automatic_actuation'] is False
    assert len(report['predictions'])==60
    for row in report['predictions']:
        assert row['raw']['p50'] is None
        assert row['issued'] is False
        for value in row['marginals'].values():
            if value is None:continue
            model=report['models'][value['model_sha256']]
            assert model['ready_at']<=row['forecast']['origin']
            assert model['training_end']<model['cutoff']
            assert value['median_source']=='local_model_generated'


def test_outer_outcomes_cannot_choose_ridge_or_decay_or_change_first_predictions():
    original=pairs(days=45);a=assess(original)
    changed=[replace(p,value=30.) if p.forecast.origin>=(T+timedelta(days=30)).isoformat() else p for p in original]
    b=assess(changed)
    assert a['cohorts'][0]['selection']==b['cohorts'][0]['selection']
    assert a['predictions'][0]['marginals']==b['predictions'][0]['marginals']
    assert a['predictions'][0]['adaptive']==b['predictions'][0]['adaptive']
    assert a['cohorts'][0]['comparisons']['temperature_normal_vs_raw']['matched']['candidate']['mae']!=b['cohorts'][0]['comparisons']['temperature_normal_vs_raw']['matched']['candidate']['mae']


def test_late_recorded_training_labels_produce_explicit_full_raw_fallback():
    rows=[replace(p,outcome_ready_at=(T+timedelta(days=90)).isoformat(),actual_outcome_available_at=(T+timedelta(days=90)).isoformat()) for p in pairs(days=45)]
    report=assess(rows);score=report['cohorts'][0]['comparisons']['temperature_normal_vs_raw']
    assert report['models']=={}
    assert score['matched']['support']['targets']==0
    assert score['fallback_inclusive']['support']['targets']==60
    assert score['fallback_inclusive']['baseline']['mae']==score['fallback_inclusive']['candidate']['mae']
    assert score['withheld']['candidate_unavailable']==60
    assert score['disposition']=='insufficient_evidence'


def test_absent_regimes_and_seasons_are_named_without_all_season_claims():
    score=assess()['cohorts'][0]['comparisons']['temperature_normal_vs_raw']
    assert score['by_subgroup']['native_regime']['zero']['support']['targets']==0
    assert score['by_subgroup']['outcome_regime']['zero']['support']['targets']==0
    assert set(score['by_subgroup']['season'])=={'winter','spring','summer','autumn'}
    assert sum(x['support']['targets']==0 for x in score['by_subgroup']['season'].values())>=2
    assert score['paired_date_blocks']['probability_claim'] is False
    assert score['local_coverage_qualified'] is False


def test_different_source_grid_cohorts_never_pool_fitted_training_membership():
    rows=pairs(days=45)
    rows += [replace(p,forecast=replace(p.forecast,grid_sha256='e'*64,cohort_sha256='f'*64)) for p in pairs(days=20)]
    report=assess(rows)
    assert len(report['cohorts'])==2
    assert {v['cohort_sha256'] for v in report['models'].values()}=={'b'*64,'f'*64}


@pytest.mark.parametrize('kind',['wind','solar_proxy'])
def test_nonnegative_uncertainty_uses_matched_empirical_not_invented_hourly_native_quantiles(kind):
    report=assess(pairs(kind,days=45));score=report['cohorts'][0]['comparisons']['nonnegative_vs_empirical']
    assert score['matched']['support']['targets']>0
    assert score['matched']['baseline']['interval_score_80'] is not None
    assert score['matched']['candidate']['interval_score_80'] is not None
    assert score['matched']['baseline']['crps'] is None
    assert score['matched']['candidate']['crps'] is None
    assert all(p['raw']['p10'] is None and p['raw']['p90'] is None for p in report['predictions'])
    assert all(p['marginals']['nonnegative'] is None or min(p['marginals']['nonnegative']['quantiles'])>=0 for p in report['predictions'])


def test_retained_report_can_be_scored_again_without_fitting_or_consulting_current_models():
    report=assess();row=report['predictions'][0];value=row['marginals']['temperature_normal']
    score=api().score_retained_prediction(value,12.)
    assert score['prediction_sha256']==value['prediction_sha256']
    assert score['absolute_error']<.4
    corrupted=dict(value,mean=99.)
    with pytest.raises(ValueError,match='original'):
        api().score_retained_prediction(corrupted,12.)
