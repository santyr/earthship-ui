"""Fit-local auxiliary reuse; no chronological input/result cache."""
from dataclasses import asdict, replace

import numpy as np
import pytest

import thermal_model.dynamics as dynamics
from test_thermal_dynamics import synthetic_2r2c_days


def test_one_glazing_build_per_fit_and_no_reuse_between_fits(monkeypatch):
    rows, _ = synthetic_2r2c_days(5, 20261003)
    original = dynamics._glazing_rows
    calls = []
    def counted(pairs):
        calls.append(tuple(pairs))
        return original(pairs)
    monkeypatch.setattr(dynamics, '_glazing_rows', counted)
    a = dynamics._fit_five_minute_dynamics(rows, allow_inactive_action_forcing=False)
    assert len(calls) == 1
    b = dynamics._fit_five_minute_dynamics(rows, allow_inactive_action_forcing=False)
    assert len(calls) == 2 and a == b
    altered = tuple(replace(row, glazing_f=row.glazing_f + 0.1) for row in rows)
    c = dynamics._fit_five_minute_dynamics(altered, allow_inactive_action_forcing=False)
    assert len(calls) == 3
    assert c[0].glazing_observation_coefficients != a[0].glazing_observation_coefficients


@pytest.mark.parametrize('allow_inactive', [False, True])
def test_complete_fit_exactly_matches_duplicate_row_construction(monkeypatch, allow_inactive):
    rows, _ = synthetic_2r2c_days(8, 20260930)
    reused = dynamics.fit_dynamics_with_evidence(rows, allow_inactive_action_forcing=allow_inactive)
    original = dynamics._selection_with_glazing
    def duplicate(samples):
        selected, diagnostics, _, _ = original(samples)
        design, target = dynamics._glazing_rows(selected)
        return selected, diagnostics, design, target
    monkeypatch.setattr(dynamics, '_selection_with_glazing', duplicate)
    legacy = dynamics.fit_dynamics_with_evidence(rows, allow_inactive_action_forcing=allow_inactive)
    assert asdict(reused) == asdict(legacy)


def test_selector_contract_diagnostics_and_rows_preserved():
    rows, _ = synthetic_2r2c_days(5, 71)
    selected, diagnostics, design, target = dynamics._selection_with_glazing(rows)
    assert dynamics._selection(rows) == (selected, diagnostics)
    assert dynamics._selected_pairs(rows) == selected
    assert dynamics.fit_diagnostics(rows) == diagnostics
    expected_design, expected_target = dynamics._glazing_rows(selected)
    assert np.array_equal(np.asarray(design), np.asarray(expected_design))
    assert target == expected_target


@pytest.mark.parametrize('damage', ['unknown_action', 'invalid_glazing', 'invalid_auxiliary'])
def test_validation_and_refusals_not_removed(monkeypatch, damage):
    rows, _ = synthetic_2r2c_days(5, 71)
    if damage == 'unknown_action': rows = tuple(replace(row, vent_open=None) for row in rows)
    elif damage == 'invalid_glazing': rows = tuple(replace(row, glazing_f='bad') for row in rows)
    else: rows = tuple(replace(row, living_office_f='bad') for row in rows)
    original = dynamics._selection_with_glazing
    def duplicate(samples):
        selected, diagnostics, _, _ = original(samples)
        design, target = dynamics._glazing_rows(selected)
        return selected, diagnostics, design, target
    def failure():
        with pytest.raises((TypeError, ValueError)) as exc:
            dynamics._fit_five_minute_dynamics(rows, allow_inactive_action_forcing=False)
        return type(exc.value), str(exc.value)
    actual = failure()
    monkeypatch.setattr(dynamics, '_selection_with_glazing', duplicate)
    assert failure() == actual
