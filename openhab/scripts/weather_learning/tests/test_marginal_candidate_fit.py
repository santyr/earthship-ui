"""The explicit fitter never turns preparation into serving-model selection."""
from dataclasses import asdict,replace
import gzip,importlib.util
import pytest
from test_probabilistic import POLICY,pairs
from weather_learning.contracts import canonical,identity


def api():
    assert importlib.util.find_spec('marginal_candidate_fit'), 'Task7 explicit actual candidate fitter missing'
    import marginal_candidate_fit
    return marginal_candidate_fit


def population(tmp_path,*,historical=False):
    rows=pairs(days=2)
    if historical:rows=[replace(p,forecast=replace(p.forecast,availability_basis='historical_assumed_availability')) for p in rows]
    value=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=POLICY['policy_sha256'],rows=[asdict(p) for p in rows]);value['population_sha256']=identity(value)
    path=tmp_path/(value['population_sha256']+'.population.json.gz');path.write_bytes(gzip.compress(canonical(value)));path.chmod(0o600);return path


def test_preview_reads_actual_availability_without_creating_a_state_namespace(tmp_path):
    state=tmp_path/'preview-state'
    result=api().run(population=population(tmp_path),cohort_sha256='b'*64,state_root=state,policy=POLICY)
    assert result['retained'] is False and result['selection_installed'] is False
    assert result['fitted_models']==0 and result['training_support']['targets']==0
    assert not state.exists()


def test_explicit_apply_retains_original_cold_bundle_without_a_current_selector(tmp_path):
    state=tmp_path/'apply-state'
    result=api().run(population=population(tmp_path),cohort_sha256='b'*64,state_root=state,policy=POLICY,apply=True)
    assert result['status']=='cold_unselected_bundle_retained'
    assert len(list((state/'marginal-models').glob('*.json')))==1
    assert not (state/'current-model.json').exists() and not (state/'marginal-current.json').exists()
    assert result['automatic_actuation'] is False


def test_historical_assumptions_refuse_before_a_prospective_model_is_retained(tmp_path):
    state=tmp_path/'invalid-state'
    with pytest.raises(ValueError,match='recorded'):
        api().run(population=population(tmp_path,historical=True),cohort_sha256='b'*64,state_root=state,policy=POLICY,apply=True)
    assert not state.exists()


def test_fitter_carries_frozen_population_partition_into_retained_candidate(tmp_path):
    from learning_fixtures import T
    from datetime import timedelta
    from weather_learning.probabilistic_artifacts import read_candidates
    from weather_learning.shadow import ShadowStore
    partition=dict(method='contiguous_whole_native_leads_greedy_capacity/v1',parent_cohort_sha256='b'*64,lower_exclusive_hours=0.,upper_inclusive_hours=2.)
    fine=identity(partition);rows=[replace(p,forecast=replace(p.forecast,cohort_sha256=fine)) for p in pairs()]
    body=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=POLICY['policy_sha256'],rows=[asdict(p) for p in rows],partitions={fine:partition})
    body['population_sha256']=identity(body);path=tmp_path/(body['population_sha256']+'.population.json.gz');path.write_bytes(gzip.compress(canonical(body)));path.chmod(0o600)
    result=api().run(population=path,cohort_sha256=fine,state_root=tmp_path/'state',policy=POLICY,apply=True,clock=lambda:T+timedelta(days=15))
    bundle=read_candidates(ShadowStore(tmp_path/'state'),result['artifact']['artifact_sha256'],policy=POLICY)
    assert bundle.to_dict()['partition']==partition
