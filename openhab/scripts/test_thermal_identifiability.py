import math
from dataclasses import replace

import numpy as np
import pytest

import thermal_model.dynamics as dynamics
from test_thermal_dynamics import synthetic_2r2c_days


def test_normalized_condition_number_is_invariant_to_column_units():
    matrix = np.asarray([
        [1.0, 2.0, 5.0],
        [2.0, 1.0, 7.0],
        [3.0, 4.0, 2.0],
        [4.0, 3.0, 9.0],
        [5.0, 7.0, 1.0],
    ])
    scaled = matrix * np.asarray([1e-6, 1e4, 0.25])
    left = dynamics._normalized_design_condition_number(matrix)
    right = dynamics._normalized_design_condition_number(scaled)
    assert math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-12)


def test_full_rank_but_nearly_collinear_fit_is_refused():
    epsilon = 1e-8
    matrix = np.asarray([
        [1.0, 1.0],
        [2.0, 2.0 + epsilon],
        [3.0, 3.0 - epsilon],
        [4.0, 4.0 + 2 * epsilon],
        [5.0, 5.0 - 2 * epsilon],
    ])
    assert np.linalg.matrix_rank(matrix) == 2
    assert (
        dynamics._normalized_design_condition_number(matrix)
        > dynamics.NORMALIZED_CONDITION_NUMBER_LIMIT
    )
    with pytest.raises(ValueError, match="ill-conditioned"):
        dynamics._fit(
            matrix,
            np.arange(1.0, 6.0),
            ([-10.0, -10.0], [10.0, 10.0]),
            ("a", "b"),
        )


def test_stable_synthetic_fit_passes_independent_day_block_refits():
    training, _ = synthetic_2r2c_days(days=30, seed=20261007)
    baseline, _ = dynamics._fit_five_minute_dynamics(
        training, allow_inactive_action_forcing=False
    )
    result = dynamics._validate_block_refit_stability(training, baseline)
    assert result["assessed"] is True
    assert result["independent_days"] >= dynamics.BLOCK_REFIT_MIN_INDEPENDENT_DAYS
    assert result["refit_count"] == dynamics.BLOCK_REFIT_GROUPS
    assert result["max_bound_span_fraction"] <= dynamics.BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION


def test_block_refit_stability_refuses_large_coefficient_movement():
    training, _ = synthetic_2r2c_days(days=30, seed=20261008)
    baseline, _ = dynamics._fit_five_minute_dynamics(
        training, allow_inactive_action_forcing=False
    )
    calls = 0

    def unstable(_rows):
        nonlocal calls
        calls += 1
        air = dict(baseline.air_coefficients)
        if calls == 1:
            air["outside_exchange"] += 0.2
        return replace(baseline, air_coefficients=air)

    with pytest.raises(ValueError, match="coefficient instability"):
        dynamics._validate_block_refit_stability(
            training, baseline, fitter=unstable
        )


def test_block_refit_stability_does_not_invent_a_pass_for_short_history():
    training, _ = synthetic_2r2c_days(days=10, seed=20261009)
    baseline, _ = dynamics._fit_five_minute_dynamics(
        training, allow_inactive_action_forcing=False
    )
    result = dynamics._validate_block_refit_stability(training, baseline)
    assert result["assessed"] is False
    assert result["refit_count"] == 0
    assert result["max_bound_span_fraction"] is None


@pytest.mark.parametrize("days,assessed", [(10, False), (30, True)])
def test_strict_fit_returns_block_stability_evidence(days, assessed):
    training, _ = synthetic_2r2c_days(days=days, seed=20261009)
    fitted = dynamics.fit_dynamics_with_evidence(training)
    evidence = fitted.evidence.block_refit_stability
    assert evidence is not None
    assert evidence.assessed is assessed
    assert evidence.independent_days == days - 1
    assert evidence.required_days == 24
    if assessed:
        assert evidence.refit_count == 4
        assert 0 <= evidence.max_bound_span_fraction <= 0.25
    else:
        assert evidence.refit_count == 0
        assert evidence.max_bound_span_fraction is None
        assert evidence.worst_coefficient is None


def test_evaluation_fit_does_not_claim_block_stability():
    training, _ = synthetic_2r2c_days(days=10, seed=20261009)
    fitted = dynamics.fit_dynamics_for_evaluation(training)
    assert fitted.evidence.block_refit_stability is None
