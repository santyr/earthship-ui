"""As-issued policy reports keep unavailable cases and original model identities."""
from copy import deepcopy
from datetime import timedelta
import importlib.util,json
import pytest
from test_marginal_queue import setup,run
from test_probabilistic import POLICY
from weather_learning.contracts import identity


def api():
    assert importlib.util.find_spec('weather_learning.marginal_reporting'), 'Task7 prospective marginal comparison report missing'
    from weather_learning import marginal_reporting
    return marginal_reporting


def records(tmp_path):
    state,q,_,_,at,_=setup(tmp_path);run(state,at+timedelta(hours=6,minutes=2),limit=3)
    with q.connect() as db:values=[json.loads(r[0]) for r in db.execute('SELECT body FROM scores ORDER BY target,key')]
    assert len(values)==3;return values


def rehash(value):
    value['score_sha256']=identity({k:v for k,v in value.items() if k!='score_sha256'});return value


def test_policy_comparison_includes_unavailable_targets_and_declared_absent_regimes(tmp_path):
    values=records(tmp_path);last=values[-1];last['local']={k:None for k in last['local']};last['adaptive']=None;last['fallback_reason']='observed_measurement_cohort_changed';last['measurement_cohort_compatible']=False;rehash(last)
    report=api().summarize_scores(values,policy=POLICY);group=report['model_sets'][0];comparison=group['comparisons']['temperature_normal_vs_raw']
    assert comparison['matched']['support']['targets']==2
    assert comparison['fallback_inclusive']['support']['targets']==3
    assert comparison['withheld']['observed_measurement_cohort_changed']==1
    assert comparison['by_subgroup']['season']['autumn']['support']['targets']==0
    assert comparison['fallback_inclusive']['baseline']['wis'] is None
    assert group['support']['local_dates']==1 and report['local_coverage_qualified'] is False
    assert comparison['probability_claim'] is False


def test_new_model_set_and_observation_policy_never_borrow_original_skill(tmp_path):
    values=records(tmp_path);changed=deepcopy(values)
    for value in changed:value['configured_bundle_sha256s']=['e'*64];value['model_set_sha256']=identity(['e'*64]);value['observation']['observation_policy_sha256']='f'*64;rehash(value)
    result=api().summarize_scores(values+changed,policy=POLICY)
    assert len(result['model_sets'])==2
    assert {g['model_set_sha256'] for g in result['model_sets']}=={values[0]['model_set_sha256'],identity(['e'*64])}
    assert all(g['support']['targets']==3 for g in result['model_sets'])
    assert all(g['comparisons']['temperature_normal_vs_raw']['matched']['support']['pairs']==3 for g in result['model_sets'])


def test_report_consumes_original_metrics_without_mutating_or_refitting(tmp_path,monkeypatch):
    values=records(tmp_path);before=deepcopy(values)
    from weather_learning import probabilistic
    monkeypatch.setattr(probabilistic,'fit_marginal',lambda *a,**k:pytest.fail('no report refit'))
    monkeypatch.setattr(probabilistic,'fit_adaptive',lambda *a,**k:pytest.fail('no report refit'))
    report=api().summarize_scores(values,policy=POLICY)
    assert values==before and report['records']==3
    assert report['model_sets'][0]['comparisons']['temperature_normal_vs_raw']['matched']['baseline']['mae']==pytest.approx(2.)
    assert report['summary_sha256']==identity({k:v for k,v in report.items() if k!='summary_sha256'})


def test_unissued_or_changed_metric_record_cannot_enter_prospective_report(tmp_path):
    values=records(tmp_path);unissued=deepcopy(values[0]);unissued['issued']=False;rehash(unissued)
    with pytest.raises(ValueError,match='issued|original'):api().summarize_scores([unissued],policy=POLICY)
    values[0]['raw']['absolute_error']=900
    with pytest.raises(ValueError,match='original'):api().summarize_scores(values,policy=POLICY)


def test_missing_native_bounds_keeps_empirical_point_comparison_without_new_gate(tmp_path):
    from dataclasses import asdict
    from weather_learning.probabilistic import ForecastInput
    from weather_learning.probabilistic_evaluation import _raw_score
    values=records(tmp_path)
    for value in values:
        f=dict(value['forecast']);f.pop('input_sha256');f.update(p10=None,p50=None,p90=None);frame=ForecastInput(**f)
        value['forecast']=asdict(frame);value['raw']=_raw_score(frame,value['observation']['value']);value['local']['temperature_normal']=None;rehash(value)
    result=api().summarize_scores(values,policy=POLICY)['model_sets'][0]['comparisons']
    assert result['empirical_vs_raw']['matched']['support']['targets']==0
    point=result['empirical_median_point_vs_raw_mean']
    assert point['matched']['support']['targets']==3
    assert point['matched']['candidate']['mae']<point['matched']['baseline']['mae']
    assert point['diagnostic_only'] is True and point['candidate_meets_score_gate'] is False and point['probability_review_support_only'] is False
