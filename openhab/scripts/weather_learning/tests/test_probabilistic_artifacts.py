"""Only actually completed, past-available candidate bundles may serve shadows."""
from dataclasses import replace
from datetime import timedelta
import importlib.util
import pytest
from learning_fixtures import T
from test_probabilistic import POLICY,pairs,frame


def api():
    assert importlib.util.find_spec('weather_learning.probabilistic_artifacts'), 'Task7 source-bound candidate artifacts missing'
    from weather_learning import probabilistic_artifacts
    return probabilistic_artifacts


def fitted(rows=None,**kw):
    return api().fit_candidates(pairs() if rows is None else rows,cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,population_sha256='a'*64,**kw)


def test_actual_candidate_fit_retains_literal_training_and_does_not_select_or_qualify():
    prepared=fitted();bundle=prepared.bundle.to_dict();training=prepared.training_dict()
    assert set(bundle['models'])=={'empirical','temperature_normal','adaptive'}
    assert bundle['models']['temperature_normal']['retrospective_only'] is False
    assert len(training['pairs'])==60
    assert bundle['training_inputs_sha256']==training['training_inputs_sha256']
    assert bundle['role']=='unselected_shadow_candidates'
    assert bundle['local_coverage_qualified'] is False and bundle['automatic_actuation'] is False
    assert bundle['selection']['temperature_normal']==1.
    assert bundle['selection']['adaptive']==72
    training['pairs'][0]['value']=99
    assert prepared.training_dict()['pairs'][0]['value']!=99


def test_candidate_bundle_requires_real_readiness_and_never_backdates_historical_fits():
    prepared=fitted();bundle=prepared.bundle
    ready=api().predict_candidates(bundle,frame(15),policy=POLICY)
    assert ready['marginals']['temperature_normal']['mean']==pytest.approx(12,abs=.5)
    early=replace(frame(15),origin=(T+timedelta(days=15,seconds=30)).isoformat(),source_ready_at=(T+timedelta(days=15,seconds=1)).isoformat(),actual_source_available_at=(T+timedelta(days=15,seconds=1)).isoformat())
    value=api().predict_candidates(bundle,early,policy=POLICY)
    assert value['status']=='raw_fallback' and value['reason']=='candidate_not_ready'
    assert all(v is None for v in value['marginals'].values())


def test_future_training_labels_stay_ineligible_and_cold_fallback_keeps_raw_forecast():
    late=(T+timedelta(days=30)).isoformat();rows=[replace(p,outcome_ready_at=late,actual_outcome_available_at=late) for p in pairs()]
    prepared=fitted(rows);body=prepared.bundle.to_dict()
    assert not prepared.training_dict()['pairs']
    assert all(v is None for v in body['models'].values())
    value=api().predict_candidates(prepared.bundle,frame(15),policy=POLICY)
    assert value['status']=='raw_fallback' and value['raw']['mean']==10.
    assert value['raw']['p50'] is None


def test_historical_assumed_frame_cannot_become_a_prospective_candidate_training_record():
    rows=[replace(p,forecast=replace(p.forecast,availability_basis='historical_assumed_availability')) for p in pairs()]
    with pytest.raises(ValueError,match='recorded|prospective'):
        fitted(rows)


def test_retained_bundle_requires_original_expected_digest_and_current_preprocessing_source():
    prepared=fitted();body=prepared.bundle.to_dict();pin=body['bundle_sha256']
    loaded=api().load_candidate_bundle(body,expected_sha256=pin,policy=POLICY)
    assert api().predict_candidates(loaded,frame(15),policy=POLICY)['marginals']==api().predict_candidates(prepared.bundle,frame(15),policy=POLICY)['marginals']
    changed=dict(body,numerical_manifest=dict(body['numerical_manifest']));changed['numerical_manifest']['openhab/scripts/weather_learning/probabilistic_retained.py']='f'*64
    from weather_learning.contracts import identity
    changed['bundle_sha256']=identity({k:v for k,v in changed.items() if k!='bundle_sha256'})
    with pytest.raises(ValueError,match='original'):
        api().load_candidate_bundle(changed,expected_sha256=pin,policy=POLICY)
    with pytest.raises(ValueError,match='numerical|preprocessing'):
        api().load_candidate_bundle(changed,expected_sha256=changed['bundle_sha256'],policy=POLICY)


def test_actual_expiry_and_different_observed_phase_have_named_fallbacks():
    bundle=fitted().bundle
    assert api().predict_candidates(bundle,frame(31),policy=POLICY)['reason']=='candidate_expired'
    other=replace(frame(15),cohort_sha256='d'*64)
    assert api().predict_candidates(bundle,other,policy=POLICY)['reason']=='candidate_cohort_changed'


@pytest.mark.parametrize('kind',['wind','solar_proxy'])
def test_nonnegative_candidate_artifacts_preserve_kind_and_zero_atom(kind):
    bundle=fitted(pairs(kind)).bundle;value=api().predict_candidates(bundle,frame(15,kind=kind),policy=POLICY)
    assert value['marginals']['nonnegative']['distribution']=='zero_atom_plus_positive_log1p_normal'
    assert min(value['marginals']['nonnegative']['quantiles'])>=0
    assert value['raw']['p10'] is None


def test_candidate_retention_copies_original_training_source_and_never_installs_a_selector(tmp_path):
    from weather_learning.shadow import ShadowStore
    from weather_learning.contracts import identity
    state=ShadowStore(tmp_path/'shadow');prepared=fitted()
    reference=api().retain_candidates(state,prepared,policy=POLICY)
    assert not (state.root/'current-model.json').exists()
    assert not (state.root/'marginal-current.json').exists()
    bundle=api().read_candidates(state,reference['artifact_sha256'],policy=POLICY)
    assert bundle.to_dict()==prepared.bundle.to_dict()
    original=state.root/'marginal-models'/(reference['artifact_sha256']+'.json')
    raw=original.read_bytes();assert api().retain_candidates(state,prepared,policy=POLICY)==reference
    assert original.read_bytes()==raw
    body=__import__('json').loads(raw);body['bundle']['models']['temperature_normal']['parameters'][0]+=1
    body['artifact_sha256']=identity({k:v for k,v in body.items() if k!='artifact_sha256'});original.write_bytes(__import__('json').dumps(body).encode())
    with pytest.raises(ValueError,match='original'):
        api().read_candidates(state,reference['artifact_sha256'],policy=POLICY)


def test_training_artifact_hash_and_actual_availability_are_checked_before_retention(tmp_path):
    from weather_learning.shadow import ShadowStore
    from weather_learning.contracts import canonical,identity
    state=ShadowStore(tmp_path/'shadow');original=fitted();changed=original.training_dict();changed['pairs'][0]['actual_outcome_available_at']=(T+timedelta(days=90)).isoformat()
    changed['training_inputs_sha256']=identity({k:v for k,v in changed.items() if k!='training_inputs_sha256'})
    altered=api().FittedCandidates(original.bundle,canonical(changed))
    with pytest.raises(ValueError,match='training|original'):
        api().retain_candidates(state,altered,policy=POLICY)
    assert not list((state.root/'marginal-models').glob('*.json')) if (state.root/'marginal-models').exists() else True


def test_literal_source_bytes_remain_available_after_model_artifact_is_reopened(tmp_path):
    from weather_learning.shadow import ShadowStore
    import base64,gzip,json
    from hashlib import sha256
    state=ShadowStore(tmp_path/'shadow');prepared=fitted();ref=api().retain_candidates(state,prepared,policy=POLICY)
    original=json.loads((state.root/'marginal-models'/(ref['artifact_sha256']+'.json')).read_bytes())
    source=json.loads(gzip.decompress(base64.b64decode(original['source_originals_gzip_base64'])))
    assert all(sha256(raw.encode()).hexdigest()==prepared.bundle.to_dict()['numerical_manifest'][name] for name,raw in source.items())
    training=json.loads(gzip.decompress(base64.b64decode(original['training_original_gzip_base64'])))
    assert training==prepared.training_dict()


def test_candidate_runtime_binds_actual_interpreter_and_numerical_binary_bytes():
    body=fitted().bundle.to_dict()
    env=body['numerical_environment']
    assert len(env['binary_sha256s'])>=5
    assert any('lbfgsb' in name for name in env['binary_sha256s'])
    from weather_learning.contracts import identity
    changed=dict(body,numerical_environment=dict(env,binary_sha256s=dict(env['binary_sha256s'])))
    name=next(iter(changed['numerical_environment']['binary_sha256s']));changed['numerical_environment']['binary_sha256s'][name]='f'*64
    changed['bundle_sha256']=identity({k:v for k,v in changed.items() if k!='bundle_sha256'})
    with pytest.raises(ValueError,match='numerical|environment'):
        api().load_candidate_bundle(changed,expected_sha256=changed['bundle_sha256'],policy=POLICY)
