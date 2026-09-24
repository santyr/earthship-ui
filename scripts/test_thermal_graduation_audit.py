import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('audit-thermal-graduation.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def metrics(model_mae, persistence_mae, recent_mae, counts=(30,30,30)):
    methods = {name: {'air': {'24': {'mae': value, 'count': count, 'bias': 0}}}
        for name, value, count in zip(('model','persistence','recent_cycle'), (model_mae,persistence_mae,recent_mae), counts)}
    return {'overall': methods, 'by_regime': {'warm': methods},
        'prediction_interval_coverage': {'air': {'24': {'fraction': .8,'nominal': .9,'count': 29}}},
        'promotion': {'eligible': True,'shadow_only': True,'graduation_thresholds': None},
        'action_evidence': {'confirmed': {'disjoint_fold_count': 0}}, 'behavior': {}}


@pytest.mark.parametrize('values,expected', [((2.18,1.69,1.83),False), ((1,2,1),False), ((1,2,1.5),True)])
def test_shadow_acceptance_is_not_baseline_superiority(values,expected):
    report=m.summarize(metrics(*values))
    assert report['air_forecast_comparisons'][0]['strictly_beats_both_baselines'] is expected
    assert report['advisory_graduation_claimed'] is False
    assert report['air_forecast_comparisons'][0]['interval_coverage']==.8
    assert 'artifact_is_shadow_only' in report['advisory_graduation_blockers']
    assert 'advisory_graduation_thresholds_unapproved' in report['advisory_graduation_blockers']
    assert 'confirmed_action_outcomes_absent' in report['advisory_graduation_blockers']
    assert 'qualified_operational_shadow_scores_not_in_artifact' in report['advisory_graduation_blockers']
    assert ('historical_24h_air_not_better_than_both_baselines'
            in report['advisory_graduation_blockers']) is not expected


def test_unpaired_counts_do_not_pass_comparison():
    report=m.summarize(metrics(1,2,3,(30,29,30)))
    assert report['air_forecast_comparisons'][0]['strictly_beats_both_baselines'] is False
    assert report['air_forecast_comparisons'][0]['paired_comparable'] is False
    assert 'historical_24h_air_baseline_counts_unpaired' in report['advisory_graduation_blockers']
    assert 'historical_24h_air_not_better_than_both_baselines' not in report['advisory_graduation_blockers']


def test_unscored_historical_24h_is_explicitly_blocked():
    data=metrics(1,2,3,(0,0,0))
    report=m.summarize(data)
    assert 'historical_24h_air_unscored' in report['advisory_graduation_blockers']
    assert 'historical_24h_air_not_better_than_both_baselines' not in report['advisory_graduation_blockers']


def test_historical_success_alone_never_claims_operational_graduation():
    data=metrics(1,2,3)
    data['promotion']['shadow_only']=False
    data['promotion']['graduation_thresholds']={'reviewed': True}
    data['action_evidence']['confirmed']['disjoint_fold_count']=10
    report=m.summarize(data)
    assert report['advisory_graduation_blockers']==[
        'qualified_operational_shadow_scores_not_in_artifact']
    assert report['advisory_graduation_claimed'] is False


def test_invalid_artifact_is_refused_without_registry_mutation(tmp_path):
    for name in ('accepted.json','backtest-report.json'):
        (tmp_path/name).write_text('{}')
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError):m.audit(tmp_path)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


@pytest.mark.parametrize('alpha', [0, .15, .5])
def test_raw_rescore_inverts_blend_for_both_states(alpha):
    records = []
    for raw, persistence in [(2, -4), (-4, 2)]:
        records.append({'horizon': 24,
            'model': {state: (1-alpha)*raw + alpha*persistence for state in ('air','mass')},
            'persistence': {state: persistence for state in ('air','mass')}})
    result = m.rescore_raw_errors(records, alpha)
    assert result['assumed_historical_shrinkage_alpha'] == alpha
    for row in result['raw_errors']:
        assert row['count'] == 2
        assert row['mae_f'] == pytest.approx(3)
        assert row['bias_f'] == pytest.approx(-1)
        assert row['rmse_f'] == pytest.approx(10**.5)


@pytest.mark.parametrize('alpha', [-.1, 1, 2, float('nan'), float('inf')])
def test_raw_rescore_refuses_noninvertible_or_invalid_assumption(alpha):
    with pytest.raises(ValueError):
        m.rescore_raw_errors([], alpha)


def test_raw_schema_cannot_be_treated_as_historically_blended(tmp_path):
    (tmp_path/'accepted.json').write_text('{}')
    (tmp_path/'backtest-report.json').write_text('{"schema":"earthship-thermal-backtest/v3"}')
    with pytest.raises(ValueError, match='raw backtest schema cannot be unblended'):
        m.audit(tmp_path, .15)


def test_artifact_selection_is_explicit_and_bounded(tmp_path):
    with pytest.raises(ValueError, match='explicit accepted or candidate'):
        m.audit(tmp_path, artifact_name='../candidate.json')
    (tmp_path/'candidate.json').write_text('{}')
    (tmp_path/'backtest-report.json').write_text('{}')
    with pytest.raises(FileNotFoundError):
        m.audit(tmp_path)
    with pytest.raises(ValueError):
        m.audit(tmp_path, artifact_name='candidate.json')
    assert not (tmp_path/'accepted.json').exists()
