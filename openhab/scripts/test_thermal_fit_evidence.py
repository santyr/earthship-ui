"""Numerical proof fixtures measure tiny matrices; never production evidence."""
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256

import pytest

from thermal_model import dynamics
from thermal_model.forcing_capture import _canonical
from test_thermal_artifacts import valid_artifact
from test_thermal_fit_measurements import controlled_fit


def inputs(monkeypatch,*,days=61):
    samples=controlled_fit(monkeypatch,days=days,matrix_rows=64)
    fitted=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    artifact=valid_artifact(code_revision='f'*64);manifest=deepcopy(artifact.data_manifest)
    diagnostics=manifest['fit_diagnostics'];diagnostics.update(fitted_pairs=64,
        excluded_passive_pairs=0,excluded_unknown_action_pairs=diagnostics['total_consecutive_pairs']-64,
        auxiliary_glazing_fitted_rows=0,auxiliary_glazing_skipped_rows=64,envelope_identification_pairs=64,
        action_label_coverage_fraction=64/diagnostics['total_consecutive_pairs'],
        multihorizon_origin_counts=dict(fitted.evidence.origin_counts),
        multihorizon_initial_objective=fitted.evidence.initial_objective,
        multihorizon_final_objective=fitted.evidence.final_objective)
    artifact=replace(artifact,dynamics=fitted.dynamics,data_manifest=manifest)
    return artifact,fitted


def module():
    from thermal_model import fit_evidence
    return fit_evidence


def test_fit_proof_binds_actual_final_model_matrices_and_block_coefficients(monkeypatch):
    evidence=module();artifact,fitted=inputs(monkeypatch)
    proof=evidence.build_fit_evidence(artifact,fitted)
    assert proof['schema']=='earthship-thermal-fit-evidence/v1'
    assert proof['artifact_sha256']==sha256(_canonical(asdict(artifact))).hexdigest()
    assert proof['training_inputs_sha256']==artifact.data_manifest['canonical_rows_sha256']
    assert proof['active_parameter_count']==12
    assert proof['coefficient_block_refit_stability']['independent_days']==61
    assert len(proof['block_refits'])==4
    assert proof['fit_gates_passed'] is True
    assert proof['release_authorized'] is False
    assert evidence.validate_fit_evidence(proof,artifact)==proof
    assert 'conditioning' not in artifact.data_manifest['fit_diagnostics']


def test_insufficient_independent_days_are_explicitly_not_a_fit_qualification_pass(monkeypatch):
    evidence=module();artifact,fitted=inputs(monkeypatch,days=3)
    proof=evidence.build_fit_evidence(artifact,fitted)
    assert proof['coefficient_block_refit_stability']['assessed'] is False
    assert proof['block_refits']==[]
    assert proof['gates']['independent_day_support'] is False
    assert proof['gates']['final_coefficient_stability'] is False
    assert proof['fit_gates_passed'] is False


@pytest.mark.parametrize('damage',['no_collection','inactive','artifact','optimizer'])
def test_incomplete_or_unbound_fitter_result_refuses_proof(monkeypatch,damage):
    evidence=module();artifact,fitted=inputs(monkeypatch)
    if damage=='no_collection':fitted=replace(fitted,evidence=replace(fitted.evidence,conditioning=None))
    elif damage=='inactive':fitted=replace(fitted,inactive_forcing_features=('vent_exchange',))
    elif damage=='artifact':
        changed=replace(artifact.dynamics,air_coefficients={**artifact.dynamics.air_coefficients,'bias':.01})
        artifact=replace(artifact,dynamics=changed)
    elif damage=='optimizer':fitted=replace(fitted,evidence=replace(fitted.evidence,final_objective=.05))
    with pytest.raises(ValueError):evidence.build_fit_evidence(artifact,fitted)


@pytest.mark.parametrize('damage',['claimed_pass','limits','matrix_shape','artifact','rows','block_days','coefficients','extra','count_type','gate_type','limit_type'])
def test_rehashed_summary_cannot_replace_actual_measured_binding(monkeypatch,damage):
    evidence=module();artifact,fitted=inputs(monkeypatch);proof=evidence.build_fit_evidence(artifact,fitted)
    if damage=='claimed_pass':proof['release_authorized']=True
    elif damage=='limits':proof['limits']['normalized_condition_number_limit']*=2
    elif damage=='matrix_shape':proof['conditioning'][0]['column_count']=True
    elif damage=='artifact':proof['artifact_sha256']='b'*64
    elif damage=='rows':proof['conditioning'][0]['row_count']=1
    elif damage=='block_days':proof['block_refits'][0]['omitted_days'][0]='2025-01-01'
    elif damage=='coefficients':proof['block_refits'][0]['coefficients'][0]=.4
    elif damage=='extra':proof['active']=True
    elif damage=='count_type':proof['active_parameter_count']=12.0
    elif damage=='gate_type':proof['gates']['numerical_conditioning']=1
    elif damage=='limit_type':proof['limits']['block_refit_groups']=4.0
    body={key:value for key,value in proof.items() if key!='fit_evidence_sha256'}
    proof['fit_evidence_sha256']=sha256(_canonical(body)).hexdigest()
    with pytest.raises(ValueError):evidence.validate_fit_evidence(proof,artifact)


def test_fit_proof_storage_is_private_immutable_and_requires_the_bound_artifact(tmp_path,monkeypatch):
    evidence=module();artifact,fitted=inputs(monkeypatch);proof=evidence.build_fit_evidence(artifact,fitted)
    tmp_path.chmod(0o700);path=evidence.write_fit_evidence(tmp_path,proof,artifact)
    assert evidence.read_fit_evidence(path,artifact)==proof
    assert path.stat().st_mode & 0o777==0o600
    assert evidence.write_fit_evidence(tmp_path,proof,artifact)==path
    artifact=replace(artifact,code_revision='e'*64)
    with pytest.raises(ValueError):evidence.read_fit_evidence(path,artifact)


def test_numerical_proof_does_not_require_or_claim_shadow_forecast_promotion(monkeypatch):
    from thermal_model.artifacts import validate_artifact
    evidence=module();artifact,fitted=inputs(monkeypatch);manifest=deepcopy(artifact.data_manifest)
    manifest['sample_counts_by_mode']={key:0 for key in manifest['sample_counts_by_mode']}
    manifest['sample_counts_by_mode']['warm']=manifest['sample_count']
    artifact=replace(artifact,data_manifest=manifest)
    with pytest.raises(ValueError):validate_artifact(artifact,require_eligible=True)
    proof=evidence.build_fit_evidence(artifact,fitted)
    assert proof['fit_gates_passed'] is True
    assert proof['release_authorized'] is False


def test_real_qualification_fit_is_exercised_only_on_the_hosted_runner():
    import os
    if os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='1':
        pytest.skip('full qualification model fitting is restricted to hosted CI')
    from test_thermal_dynamics import synthetic_2r2c_days
    from thermal_model.pipeline import _complete_manifest
    evidence=module();samples,_=synthetic_2r2c_days(28,20261007)
    fitted=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    manifest=_complete_manifest(samples,(),(),fitted.evidence)
    artifact=valid_artifact(code_revision='f'*64)
    artifact=replace(artifact,dynamics=fitted.dynamics,data_manifest=manifest,
        trained_from=manifest['start'],trained_through=manifest['end'])
    proof=evidence.build_fit_evidence(artifact,fitted)
    assert proof['fit_gates_passed'] is True
    assert proof['release_authorized'] is False
    assert len(proof['block_refits'])==4
    assert proof['coefficient_block_refit_stability']['independent_days']>=24
