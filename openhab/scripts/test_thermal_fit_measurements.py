"""Tiny matrix and controlled optimizer boundaries; no numerical model fitting."""
from dataclasses import FrozenInstanceError
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

import numpy as np
import pytest

from thermal_model import dynamics
from test_thermal_pipeline import stable_dynamics


def controlled_fit(monkeypatch,*,days=24,bad_final=False,matrix_rows=None):
    model=stable_dynamics();original=dynamics._coefficient_vector(model)
    samples=tuple(SimpleNamespace(at=datetime(2026,6,1,12,tzinfo=timezone.utc)+timedelta(days=day)) for day in range(days))
    def initializer(rows,*,allow_inactive_action_forcing):
        assert allow_inactive_action_forcing is False
        for columns in (3,6,5):
            matrix=np.eye(columns)
            if matrix_rows is not None:
                rows_count=max(columns,int(matrix_rows*len(rows)/days))
                matrix=np.tile(matrix,((rows_count+columns-1)//columns,1))[:rows_count]
            dynamics._require_well_conditioned(matrix,'fit design')
        return model,()
    endpoints={steps:(object(),object()) for steps in dynamics.IDENTIFICATION_HORIZON_STEPS}
    monkeypatch.setattr(dynamics,'_fit_five_minute_dynamics',initializer)
    monkeypatch.setattr(dynamics,'_selected_pairs',lambda rows:[(row,row) for row in rows])
    monkeypatch.setattr(dynamics,'_select_multihorizon_endpoints',lambda *_:endpoints)
    monkeypatch.setattr(dynamics,'_prepare_multihorizon_forcings',lambda *_:{})
    monkeypatch.setattr(dynamics,'_prepare_multihorizon_batches',lambda *_:())
    def objective(vector,endpoints,*,sensitivity_rows=None,**kwargs):
        if sensitivity_rows is not None:
            matrix=np.eye(12)
            if bad_final and not np.array_equal(vector,original):
                matrix[:,1]=matrix[:,0];matrix[1,1]=1e-9
            sensitivity_rows.extend(np.concatenate([matrix,np.zeros((8,12))]))
        return .2 if np.array_equal(vector,original) else .1,np.zeros(12)
    monkeypatch.setattr(dynamics,'_multihorizon_objective_and_gradient',objective)
    monkeypatch.setattr(dynamics,'minimize',lambda fun,initial,**kwargs:SimpleNamespace(success=True,x=np.asarray(initial)*1.01))
    return samples


def test_qualification_retains_measured_initial_and_final_conditioning_and_final_refits(monkeypatch):
    samples=controlled_fit(monkeypatch)
    result=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    evidence=result.evidence
    assert evidence.graduation_block_refit_stability.assessed is True
    assert evidence.graduation_block_refit_stability.independent_days==24
    assert evidence.graduation_block_refit_stability.refit_count==4
    assert evidence.graduation_block_refit_stability.max_bound_span_fraction==0
    final=[entry for entry in evidence.conditioning if entry.label=='multihorizon final sensitivity matrix']
    assert len(final)==5
    assert final[0].stage=='refinement'
    assert all(entry.stage=='graduation_block_refit' for entry in final[1:])
    assert all(entry.column_count==12 and entry.condition_number==1 for entry in final)
    with pytest.raises(FrozenInstanceError):final[0].condition_number=0


def test_short_qualification_records_insufficient_final_refit_support(monkeypatch):
    samples=controlled_fit(monkeypatch,days=3)
    result=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    report=result.evidence.graduation_block_refit_stability
    assert report.assessed is False and report.refit_count==0
    assert report.independent_days==3 and report.required_days==24
    assert report.max_bound_span_fraction is None


def test_default_fitting_result_preserves_the_legacy_numerical_path(monkeypatch):
    samples=controlled_fit(monkeypatch,bad_final=True)
    result=dynamics.fit_dynamics_with_evidence(samples)
    assert result.evidence.conditioning is None
    assert result.evidence.graduation_block_refit_stability is None
    assert result.evidence.block_refit_stability.assessed is True


def test_qualification_refuses_full_rank_but_ill_conditioned_final_optimizer_state(monkeypatch):
    samples=controlled_fit(monkeypatch,bad_final=True)
    with pytest.raises(ValueError,match='ill-conditioned'):
        dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    assert dynamics._condition_capture.get() is None


def test_measurement_context_is_reset_between_qualification_and_default_fits(monkeypatch):
    samples=controlled_fit(monkeypatch,days=3)
    first=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    dynamics._require_well_conditioned(np.eye(2),'detached check')
    second=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    assert first==second
    assert dynamics._condition_capture.get() is None
    assert dynamics.fit_dynamics_with_evidence(samples).evidence.conditioning is None


@pytest.mark.parametrize('argument',[True,1,'yes'])
def test_evaluation_only_or_ambiguous_fit_cannot_collect_release_measurements(monkeypatch,argument):
    samples=controlled_fit(monkeypatch,days=3)
    options=dict(collect_graduation_evidence=argument)
    if argument is True:options['allow_inactive_action_forcing']=True
    with pytest.raises(ValueError):dynamics.fit_dynamics_with_evidence(samples,**options)


def test_qualification_retains_each_deterministic_omission_and_actual_refit_coefficients(monkeypatch):
    samples=controlled_fit(monkeypatch)
    result=dynamics.fit_dynamics_with_evidence(samples,collect_graduation_evidence=True)
    blocks=result.evidence.graduation_block_refits
    assert len(blocks)==4
    assert [block.group for block in blocks]==list(range(4))
    assert blocks[0].omitted_days==tuple((samples[index].at.date().isoformat()) for index in range(0,24,4))
    assert len({day for block in blocks for day in block.omitted_days})==24
    for block in blocks:
        assert block.coefficients==tuple(dynamics._coefficient_vector(result.dynamics))
