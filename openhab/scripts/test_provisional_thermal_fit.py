"""Provisional learning never claims stable coefficients or release qualification."""
from dataclasses import replace
import time
import pytest
from test_installed_shade_fit import endpoints,COEFFICIENTS


def module():
    from thermal_model import provisional_fit
    return provisional_fit


def test_short_rank_deficient_data_can_fit_with_explicit_prior(monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    points=endpoints(2)
    seed=list(COEFFICIENTS);seed[1]*=1.12
    result=module().fit_points(points,initial=tuple(seed),deadline=time.monotonic()+25)
    assert result['mode']=='provisional' and result['confidence']=='low'
    assert result['fit_executed'] is True and result['stability_assessed'] is False
    assert result['graduated'] is False and result['automatic_actuation'] is False
    assert result['prediction_intervals'] is None
    assert result['final_objective']<=result['initial_objective']
    assert result['conditioning_rank']<10
    assert result['normalized_condition_number'] is None
    assert result['regularization_strength']>0
    assert len(result['coefficients'])==10


def test_provisional_fit_still_requires_explicit_optin(monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','0')
    with pytest.raises(ValueError):module().fit_points(endpoints(2),initial=COEFFICIENTS,deadline=time.monotonic()+10)


def test_provisional_fit_refuses_expired_deadline(monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    with pytest.raises(ValueError,match='deadline'):module().fit_points(endpoints(2),initial=COEFFICIENTS,deadline=time.monotonic()-1)


def test_provisional_fit_refuses_unphysical_seed(monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    with pytest.raises(ValueError):module().fit_points(endpoints(2),initial=(float('nan'),)*10,deadline=time.monotonic()+10)


def test_failed_optimizer_never_claims_learned_model(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    monkeypatch.setattr(module(),'minimize',lambda *a,**k:SimpleNamespace(success=False))
    with pytest.raises(ValueError,match='optimizer'):module().fit_points(endpoints(2),initial=COEFFICIENTS,deadline=time.monotonic()+10)
