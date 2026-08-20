import math
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

import thermal_model.dynamics as dynamics
from thermal_model.dynamics import (
    AIR_BOUNDS,
    GLAZING_BOUNDS,
    MASS_BOUNDS,
    fit_diagnostics,
    fit_dynamics,
    fit_dynamics_for_evaluation,
    predict_step,
    simulate,
    validate_physics,
)
from thermal_model.schema import DynamicsModel, ThermalSample


UTC = timezone.utc
STEP = timedelta(minutes=5)


def _sample(at, air, mass, glazing, outdoor, radiation, vent, indoor, outdoor_shade):
    return ThermalSample(
        at=at,
        air_f=air,
        mass_f=mass,
        glazing_f=glazing,
        outdoor_f=outdoor,
        radiation_wm2=radiation,
        vent_open=vent,
        vent_confidence=1.0,
        indoor_shade_closed=indoor,
        indoor_shade_confidence=1.0,
        outdoor_shade_present=outdoor_shade,
        outdoor_shade_confidence=1.0,
        action_confidence=1.0,
        passive_fit_allowed=True,
        mode="warm",
    )


TRUE_AIR_COEFFICIENTS = {
    "outside_exchange": 0.018,
    "mass_exchange": 0.040,
    "solar_unshaded": 0.00015,
    "solar_indoor_closed": 0.00006,
    "solar_outdoor": 0.00003,
    "vent_exchange": 0.070,
    "bias": 0.002,
}
TRUE_MASS_COEFFICIENTS = {
    "air_exchange": 0.008,
    "outside_exchange": 0.003,
    "solar_unshaded": 0.000035,
    "solar_indoor_closed": 0.000014,
    "solar_outdoor": 0.000007,
}
TRUE_GLAZING_COEFFICIENTS = {
    "intercept": 4.0,
    "air": 0.72,
    "outdoor": 0.20,
    "solar_unshaded": 0.0030,
    "solar_indoor_closed": 0.0013,
    "solar_outdoor": 0.0008,
}


def _synthetic_forcing(index):
    minute = index % 288
    day = index // 288
    angle = 2.0 * math.pi * minute / 288.0
    return {
        "outdoor": 61.0 + 18.0 * math.sin(angle - math.pi / 2.0),
        "radiation": max(0.0, 760.0 * math.sin(angle - math.pi / 2.0)),
        "vent": float(minute >= 225 or minute < 72),
        "indoor": float(105 <= minute < 210 and day % 3 != 0),
        "outdoor_shade": float(day % 4 in (1, 2)),
    }


def _synthetic_solar(forcing):
    indoor = forcing["indoor"]
    outdoor_shade = forcing["outdoor_shade"]
    radiation = forcing["radiation"]
    return (
        radiation * (1.0 - indoor) * (1.0 - outdoor_shade),
        radiation * indoor,
        radiation * (1.0 - indoor) * outdoor_shade,
    )


def synthetic_2r2c_days(days, seed):
    rng = random.Random(seed)
    at = datetime(2026, 5, 1, tzinfo=UTC)
    air = 70.0
    mass = 67.0
    rows = []
    for index in range(days * 288):
        forcing = _synthetic_forcing(index)
        solar = _synthetic_solar(forcing)
        glazing = (
            TRUE_GLAZING_COEFFICIENTS["intercept"]
            + TRUE_GLAZING_COEFFICIENTS["air"] * air
            + TRUE_GLAZING_COEFFICIENTS["outdoor"] * forcing["outdoor"]
            + TRUE_GLAZING_COEFFICIENTS["solar_unshaded"] * solar[0]
            + TRUE_GLAZING_COEFFICIENTS["solar_indoor_closed"] * solar[1]
            + TRUE_GLAZING_COEFFICIENTS["solar_outdoor"] * solar[2]
            + rng.uniform(-0.02, 0.02)
        )
        rows.append(
            _sample(
                at,
                air,
                mass,
                glazing,
                forcing["outdoor"],
                forcing["radiation"],
                forcing["vent"],
                forcing["indoor"],
                forcing["outdoor_shade"],
            )
        )

        end_forcing = _synthetic_forcing(index + 1)
        end_solar = _synthetic_solar(end_forcing)
        pre_air = air
        pre_mass = mass
        air = (
            pre_air
            + TRUE_AIR_COEFFICIENTS["outside_exchange"]
            * (end_forcing["outdoor"] - pre_air)
            + TRUE_AIR_COEFFICIENTS["mass_exchange"] * (pre_mass - pre_air)
            + TRUE_AIR_COEFFICIENTS["solar_unshaded"] * end_solar[0]
            + TRUE_AIR_COEFFICIENTS["solar_indoor_closed"] * end_solar[1]
            + TRUE_AIR_COEFFICIENTS["solar_outdoor"] * end_solar[2]
            + TRUE_AIR_COEFFICIENTS["vent_exchange"]
            * end_forcing["vent"]
            * (end_forcing["outdoor"] - pre_air)
            + TRUE_AIR_COEFFICIENTS["bias"]
            + rng.uniform(-0.003, 0.003)
        )
        mass = (
            pre_mass
            + TRUE_MASS_COEFFICIENTS["air_exchange"] * (pre_air - pre_mass)
            + TRUE_MASS_COEFFICIENTS["outside_exchange"]
            * (end_forcing["outdoor"] - pre_mass)
            + TRUE_MASS_COEFFICIENTS["solar_unshaded"] * end_solar[0]
            + TRUE_MASS_COEFFICIENTS["solar_indoor_closed"] * end_solar[1]
            + TRUE_MASS_COEFFICIENTS["solar_outdoor"] * end_solar[2]
            + rng.uniform(-0.001, 0.001)
        )
        at += STEP
    split = (days - 2) * 288
    return rows[:split], rows[split:]


def _synthetic_unordered_glazing_pressure():
    training, _ = synthetic_2r2c_days(days=21, seed=41)
    pressured = []
    coefficients = {
        "intercept": 4.0,
        "air": 0.72,
        "outdoor": 0.20,
        "solar_unshaded": 0.0010,
        "solar_indoor_closed": 0.0040,
        "solar_outdoor": 0.0020,
    }
    for sample in training:
        forcing = {
            "radiation": sample.radiation_wm2,
            "indoor": sample.indoor_shade_closed,
            "outdoor_shade": sample.outdoor_shade_present,
        }
        solar = _synthetic_solar(forcing)
        glazing = (
            coefficients["intercept"]
            + coefficients["air"] * sample.air_f
            + coefficients["outdoor"] * sample.outdoor_f
            + coefficients["solar_unshaded"] * solar[0]
            + coefficients["solar_indoor_closed"] * solar[1]
            + coefficients["solar_outdoor"] * solar[2]
        )
        pressured.append(replace(sample, glazing_f=glazing))
    return pressured


def _forcing_rows(samples):
    return samples[1:]


def _mae(actual, expected):
    return sum(
        abs(left - right) for left, right in zip(actual, expected)
    ) / len(expected)


def test_fit_recovers_stable_synthetic_2r2c():
    training, holdout = synthetic_2r2c_days(days=21, seed=7)
    model = fit_dynamics(training)
    predicted = simulate(
        model,
        {"air_f": holdout[0].air_f, "mass_f": holdout[0].mass_f},
        _forcing_rows(holdout),
    )

    assert (
        _mae([row["air_f"] for row in predicted], [s.air_f for s in holdout[1:]])
        < 0.45
    )
    assert (
        _mae([row["mass_f"] for row in predicted], [s.mass_f for s in holdout[1:]])
        < 0.25
    )
    air_tolerances = {
        "outside_exchange": 0.00010,
        "mass_exchange": 0.00006,
        "solar_unshaded": 0.000002,
        "solar_indoor_closed": 0.000002,
        "solar_outdoor": 0.000002,
        "vent_exchange": 0.00010,
        "bias": 0.0001,
    }
    for name, expected in TRUE_AIR_COEFFICIENTS.items():
        assert model.air_coefficients[name] == pytest.approx(
            expected, abs=air_tolerances[name]
        )
    mass_tolerances = {
        "air_exchange": 0.00002,
        "outside_exchange": 0.00002,
        "solar_unshaded": 0.000001,
        "solar_indoor_closed": 0.000001,
        "solar_outdoor": 0.000001,
    }
    for name, expected in TRUE_MASS_COEFFICIENTS.items():
        assert model.mass_coefficients[name] == pytest.approx(
            expected, abs=mass_tolerances[name]
        )
    glazing_tolerances = {
        "intercept": 0.01,
        "air": 0.001,
        "outdoor": 0.001,
        "solar_unshaded": 0.00001,
        "solar_indoor_closed": 0.00001,
        "solar_outdoor": 0.00001,
    }
    for name, expected in TRUE_GLAZING_COEFFICIENTS.items():
        assert model.glazing_observation_coefficients[name] == pytest.approx(
            expected, abs=glazing_tolerances[name]
        )


def test_fit_enforces_ordered_solar_gains_during_optimization():
    samples = _synthetic_unordered_glazing_pressure()
    design, target = dynamics._glazing_rows(dynamics._selected_pairs(samples))
    direct = dynamics.lsq_linear(
        design,
        target,
        bounds=(-math.inf, math.inf),
        method="trf",
        lsmr_tol="auto",
    )
    direct_coefficients = dict(zip(dynamics.GLAZING_NAMES, direct.x))
    assert direct.success
    assert (
        direct_coefficients["solar_indoor_closed"]
        > direct_coefficients["solar_unshaded"]
    )

    model = fit_dynamics(samples)

    for coefficients in (
        model.air_coefficients,
        model.mass_coefficients,
        model.glazing_observation_coefficients,
    ):
        assert coefficients["solar_unshaded"] >= coefficients["solar_indoor_closed"]
        assert coefficients["solar_unshaded"] >= coefficients["solar_outdoor"]
        assert coefficients["solar_indoor_closed"] >= 0.0
        assert coefficients["solar_outdoor"] >= 0.0


def test_fit_rejects_shaded_gain_above_unshaded_gain():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.02,
            "mass_exchange": 0.03,
            "solar_unshaded": 0.01,
            "solar_indoor_closed": 0.02,
            "solar_outdoor": 0.005,
            "vent_exchange": 0.05,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.01,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.002,
            "solar_indoor_closed": 0.001,
            "solar_outdoor": 0.0005,
        },
        glazing_observation_coefficients={},
    )

    with pytest.raises(ValueError, match="shade gain"):
        validate_physics(model)


def test_fit_diagnostics_match_exact_selected_pairs_and_auxiliary_rows():
    samples, _ = synthetic_2r2c_days(days=5, seed=11)
    samples = samples[:12]
    samples[2] = replace(samples[2], passive_fit_allowed=False)
    samples[5] = replace(
        samples[5], vent_open=None, vent_confidence=0.0, action_confidence=0.0
    )
    samples[8] = replace(samples[8], glazing_f=None)
    samples[10] = replace(samples[10], at=samples[10].at + STEP)

    diagnostics = fit_diagnostics(samples)

    assert diagnostics == {
        "total_consecutive_pairs": 9,
        "fitted_pairs": 6,
        "excluded_passive_pairs": 2,
        "excluded_unknown_action_pairs": 1,
        "auxiliary_glazing_fitted_rows": 0,
        "auxiliary_glazing_skipped_rows": 6,
        "envelope_identification_pairs": 0,
        "auxiliary_living_office_observation_rows": 0,
        "auxiliary_living_office_hallway_mae_f": None,
        "action_label_coverage_fraction": pytest.approx(6 / 9),
    }


def test_fit_diagnostics_include_bounded_living_office_comparison():
    samples, _ = synthetic_2r2c_days(days=5, seed=67)
    samples[0] = replace(
        samples[0], living_office_f=samples[0].air_f + 1.0
    )
    samples[1] = replace(
        samples[1], living_office_f=samples[1].air_f - 2.0
    )

    diagnostics = fit_diagnostics(samples)

    assert diagnostics["auxiliary_living_office_observation_rows"] == 2
    assert diagnostics["auxiliary_living_office_hallway_mae_f"] == pytest.approx(1.5)
    assert 0 < diagnostics["envelope_identification_pairs"] <= diagnostics["fitted_pairs"]


def test_boosted_ventilation_forcing_scales_effective_outdoor_exchange():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.0,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
            "vent_exchange": 0.1,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.0,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
        glazing_observation_coefficients={},
    )
    forcing = {
        "air_f": 80.0,
        "mass_f": 70.0,
        "outdoor_f": 60.0,
        "radiation_wm2": 0.0,
        "vent_open": 1.0,
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
    }

    baseline_air, _, _ = predict_step(model, forcing)
    boosted_air, _, _ = predict_step(model, forcing | {"vent_open": 2.0})

    assert baseline_air == pytest.approx(78.0)
    assert boosted_air == pytest.approx(76.0)


def test_invalid_glazing_row_skips_only_auxiliary_fit():
    training, _ = synthetic_2r2c_days(days=5, seed=13)
    training[4] = replace(training[4], glazing_f=math.nan)

    model = fit_dynamics(training)
    diagnostics = fit_diagnostics(training)

    assert model.glazing_observation_coefficients
    assert diagnostics["auxiliary_glazing_fitted_rows"] == len(training) - 2
    assert diagnostics["auxiliary_glazing_skipped_rows"] == 1


def test_absent_glazing_skips_auxiliary_model_without_becoming_a_state():
    training, _ = synthetic_2r2c_days(days=5, seed=17)
    training = [replace(sample, glazing_f=None) for sample in training]

    model = fit_dynamics(training)
    predicted = simulate(
        model,
        {"air_f": training[0].air_f, "mass_f": training[0].mass_f},
        training[:2],
    )

    assert model.glazing_observation_coefficients == {}
    assert all(row["glazing_f"] is None for row in predicted)


def test_sparse_glazing_coverage_skips_auxiliary_fit_without_rejecting_core():
    training, _ = synthetic_2r2c_days(days=5, seed=19)
    training = [
        replace(sample, glazing_f=sample.glazing_f if index < 5 else None)
        for index, sample in enumerate(training)
    ]

    model = fit_dynamics(training)
    diagnostics = fit_diagnostics(training)

    assert model.glazing_observation_coefficients == {}
    assert diagnostics["auxiliary_glazing_fitted_rows"] == 0
    assert diagnostics["auxiliary_glazing_skipped_rows"] == len(training) - 1


def test_negative_ventilation_forcing_is_rejected():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.02,
            "mass_exchange": 0.03,
            "solar_unshaded": 0.001,
            "solar_indoor_closed": 0.0005,
            "solar_outdoor": 0.0002,
            "vent_exchange": 0.1,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.01,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0002,
            "solar_indoor_closed": 0.0001,
            "solar_outdoor": 0.00005,
        },
        glazing_observation_coefficients={},
    )
    forcing = {
        "air_f": 80.0,
        "mass_f": 70.0,
        "outdoor_f": 60.0,
        "radiation_wm2": 0.0,
        "vent_open": -0.1,
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
    }

    with pytest.raises(ValueError, match="vent.*nonnegative"):
        predict_step(model, forcing)


def test_fit_rejects_rank_deficient_identification_data():
    start = datetime(2026, 5, 1, tzinfo=UTC)
    samples = [
        _sample(start + index * STEP, 70.0, 70.0, None, 70.0, 0.0, 0.0, 0.0, 0.0)
        for index in range(20)
    ]

    with pytest.raises(ValueError, match="rank deficient"):
        fit_dynamics(samples)


def test_evaluation_fit_allows_only_exactly_inactive_action_forcing():
    training, _ = synthetic_2r2c_days(days=5, seed=71)
    training = [
        replace(sample, outdoor_shade_present=0.0)
        for sample in training
    ]

    with pytest.raises(ValueError, match="rank deficient"):
        fit_dynamics(training)

    fitted = fit_dynamics_for_evaluation(training)

    assert fitted.inactive_forcing_features == ("solar_outdoor",)
    assert fitted.dynamics.air_coefficients["solar_outdoor"] == 0.0
    assert fitted.dynamics.mass_coefficients["solar_outdoor"] == 0.0
    validate_physics(fitted.dynamics)


def test_evaluation_fit_refuses_structural_rank_deficiency(monkeypatch):
    start = datetime(2026, 5, 1, tzinfo=UTC)
    samples = [
        _sample(start + index * STEP, 70.0, 70.0, None, 60.0, 0.0, 0.0, 0.0, 0.0)
        for index in range(40)
    ]
    monkeypatch.setattr(
        dynamics, "_fit_envelope_exchange", lambda pairs: (0.01, len(pairs))
    )

    with pytest.raises(ValueError, match="rank deficient"):
        fit_dynamics_for_evaluation(samples)


def test_fit_uses_evidence_derived_envelope_exchange_as_initializer(
    monkeypatch,
):
    training, _ = synthetic_2r2c_days(days=5, seed=53)
    identified = 0.012345
    seen = {}
    original_refine = dynamics._refine_multihorizon

    def envelope(pairs):
        seen["pairs"] = len(pairs)
        return identified, 37

    def refine(initial, endpoints, inactive_features):
        seen["initial"] = initial.air_coefficients["outside_exchange"]
        return original_refine(initial, endpoints, inactive_features)

    monkeypatch.setattr(dynamics, "_fit_envelope_exchange", envelope)
    monkeypatch.setattr(dynamics, "_refine_multihorizon", refine)

    model = fit_dynamics(training)

    assert seen["pairs"] == len(training) - 1
    assert seen["initial"] == identified
    assert 0.0 <= model.air_coefficients["outside_exchange"] <= 0.5


def test_fit_refuses_without_closed_low_radiation_envelope_evidence():
    training, _ = synthetic_2r2c_days(days=5, seed=59)
    training = [
        replace(sample, vent_open=1.0, radiation_wm2=max(100.0, sample.radiation_wm2))
        for sample in training
    ]

    with pytest.raises(ValueError, match="closed low-radiation envelope"):
        fit_dynamics(training)


def test_fit_refuses_nonpositive_identified_envelope_exchange(monkeypatch):
    training, _ = synthetic_2r2c_days(days=5, seed=61)
    monkeypatch.setattr(
        dynamics, "_fit_envelope_exchange", lambda pairs: (0.0, 100)
    )

    with pytest.raises(ValueError, match="positive envelope exchange"):
        fit_dynamics(training)


def test_ordered_fit_rejects_unsuccessful_optimizer(monkeypatch):
    training, _ = synthetic_2r2c_days(days=5, seed=43)

    def unsuccessful(*args, **kwargs):
        return SimpleNamespace(success=False, x=np.asarray(args[1], dtype=float))

    monkeypatch.setattr(dynamics, "minimize", unsuccessful)

    with pytest.raises(ValueError, match="constrained least-squares fit failed"):
        fit_dynamics(training)


@pytest.mark.parametrize("failure", ["nonfinite", "unordered"])
def test_ordered_fit_rejects_invalid_optimizer_result(monkeypatch, failure):
    training, _ = synthetic_2r2c_days(days=5, seed=47)

    def invalid(*args, **kwargs):
        candidate = np.asarray(args[1], dtype=float).copy()
        if failure == "nonfinite":
            candidate[0] = math.nan
        else:
            candidate[2] = 0.0
            candidate[3] = 1.0
        return SimpleNamespace(success=True, x=candidate)

    monkeypatch.setattr(dynamics, "minimize", invalid)
    message = "fit failed" if failure == "nonfinite" else "violated solar order"

    with pytest.raises(ValueError, match=message):
        fit_dynamics(training)


def test_rank_deficient_glazing_design_skips_only_auxiliary_fit():
    training, _ = synthetic_2r2c_days(days=5, seed=23)
    training = [
        replace(sample, glazing_f=sample.glazing_f if index < 10 else None)
        for index, sample in enumerate(training)
    ]

    model = fit_dynamics(training)
    diagnostics = fit_diagnostics(training)

    assert model.glazing_observation_coefficients == {}
    assert diagnostics["auxiliary_glazing_fitted_rows"] == 0
    assert diagnostics["auxiliary_glazing_skipped_rows"] == len(training) - 1


def test_validation_rejects_unstable_72_hour_unforced_response():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.001,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.001,
            "solar_indoor_closed": 0.0005,
            "solar_outdoor": 0.0002,
            "vent_exchange": 0.8,
            "bias": 0.2,
        },
        mass_coefficients={
            "air_exchange": 0.01,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0002,
            "solar_indoor_closed": 0.0001,
            "solar_outdoor": 0.00005,
        },
        glazing_observation_coefficients={},
    )

    with pytest.raises(ValueError, match="out of range"):
        validate_physics(model)


def test_validation_rejects_negative_solar_gains_even_when_ordered():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.02,
            "mass_exchange": 0.03,
            "solar_unshaded": -0.001,
            "solar_indoor_closed": -0.002,
            "solar_outdoor": -0.003,
            "vent_exchange": 0.1,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.01,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0002,
            "solar_indoor_closed": 0.0001,
            "solar_outdoor": 0.00005,
        },
        glazing_observation_coefficients={},
    )

    with pytest.raises(ValueError, match="solar gain.*nonnegative"):
        validate_physics(model)


def test_exact_coefficient_bounds_are_the_approved_five_minute_bounds():
    assert AIR_BOUNDS == (
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.20],
        [0.50, 0.50, 0.020, 0.010, 0.015, 0.80, 0.20],
    )
    assert MASS_BOUNDS == (
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [0.20, 0.20, 0.008, 0.004, 0.006],
    )
    assert GLAZING_BOUNDS == (
        [-math.inf, -math.inf, -math.inf, 0.0, 0.0, 0.0],
        [math.inf, math.inf, math.inf, math.inf, math.inf, math.inf],
    )


@pytest.mark.parametrize(
    ("indoor", "outdoor_shade", "expected_air", "expected_mass"),
    [
        (0.0, 0.0, 70.3, 65.03),
        (1.0, 0.0, 70.2, 65.02),
        (0.0, 1.0, 70.1, 65.01),
    ],
)
def test_prediction_uses_distinct_solar_gain_for_each_shade_regime(
    indoor, outdoor_shade, expected_air, expected_mass
):
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.0,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.003,
            "solar_indoor_closed": 0.002,
            "solar_outdoor": 0.001,
            "vent_exchange": 0.0,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.0,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0003,
            "solar_indoor_closed": 0.0002,
            "solar_outdoor": 0.0001,
        },
        glazing_observation_coefficients={},
    )
    forcing = {
        "air_f": 70.0,
        "mass_f": 65.0,
        "outdoor_f": 70.0,
        "radiation_wm2": 100.0,
        "vent_open": 0.0,
        "indoor_shade_closed": indoor,
        "outdoor_shade_present": outdoor_shade,
    }

    air, mass, glazing = predict_step(model, forcing)

    assert air == pytest.approx(expected_air)
    assert mass == pytest.approx(expected_mass)
    assert glazing is None


def test_sqrt_confidence_weighting_suppresses_low_confidence_measurement_noise():
    training, _ = synthetic_2r2c_days(days=21, seed=31)
    clean = fit_dynamics(training)
    fully_weighted = list(training)
    confidence_weighted = list(training)
    for index in range(100, len(training) - 1, 31):
        noise = 0.8 if index % 2 else -0.8
        fully_weighted[index] = replace(
            fully_weighted[index], air_f=fully_weighted[index].air_f + noise
        )
        confidence_weighted[index] = replace(
            confidence_weighted[index],
            air_f=confidence_weighted[index].air_f + noise,
            action_confidence=0.01,
        )
        confidence_weighted[index + 1] = replace(
            confidence_weighted[index + 1], action_confidence=0.01
        )

    unweighted_model = fit_dynamics(fully_weighted)
    weighted_model = fit_dynamics(confidence_weighted)
    names = clean.air_coefficients
    unweighted_error = sum(
        abs(unweighted_model.air_coefficients[name] - clean.air_coefficients[name])
        for name in names
    )
    weighted_error = sum(
        abs(weighted_model.air_coefficients[name] - clean.air_coefficients[name])
        for name in names
    )

    assert weighted_error < unweighted_error * 0.10


def test_simulation_is_repeatable_and_never_clamps_out_of_range_output():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.0,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
            "vent_exchange": 0.0,
            "bias": 0.2,
        },
        mass_coefficients={
            "air_exchange": 0.0,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
        glazing_observation_coefficients={},
    )
    forcing = {
        "outdoor_f": 70.0,
        "radiation_wm2": 0.0,
        "vent_open": 0.0,
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
    }
    initial = {"air_f": 70.0, "mass_f": 65.0}

    assert simulate(model, initial, [forcing] * 2) == simulate(
        model, initial, [forcing] * 2
    )
    with pytest.raises(ValueError, match="out of range"):
        simulate(model, {"air_f": 139.9, "mass_f": 65.0}, [forcing])


def test_stability_rejects_slow_neutral_bias_drift_inside_72_hour_range():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.0,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
            "vent_exchange": 0.0,
            "bias": 0.01,
        },
        mass_coefficients={
            "air_exchange": 0.0,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
        glazing_observation_coefficients={},
    )

    with pytest.raises(ValueError, match="transition stability.*closed"):
        validate_physics(model)


def test_stability_rejects_oscillatory_boosted_transition():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.5,
            "mass_exchange": 0.5,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
            "vent_exchange": 0.8,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.2,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
        glazing_observation_coefficients={},
    )

    with pytest.raises(ValueError, match="transition stability.*boosted"):
        validate_physics(model)


def test_ventilation_forcing_is_bounded_at_operator_approved_boost():
    assert dynamics.MAX_VENT_FORCING == 2.0
    assert dynamics.STABILITY_TOLERANCE == 1e-9
    forcing = {
        "air_f": 70.0,
        "mass_f": 65.0,
        "outdoor_f": 60.0,
        "radiation_wm2": 0.0,
        "vent_open": 2.01,
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
    }
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.02,
            "mass_exchange": 0.03,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
            "vent_exchange": 0.1,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.01,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
        glazing_observation_coefficients={},
    )

    with pytest.raises(ValueError, match="vent forcing.*2.0"):
        predict_step(model, forcing)


def test_glazing_prediction_is_aligned_with_end_of_step_air_state():
    model = DynamicsModel(
        version=2,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.5,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
            "vent_exchange": 0.0,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.0,
            "outside_exchange": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
        glazing_observation_coefficients={
            "intercept": 0.0,
            "air": 1.0,
            "outdoor": 0.0,
            "solar_unshaded": 0.0,
            "solar_indoor_closed": 0.0,
            "solar_outdoor": 0.0,
        },
    )
    forcing = {
        "air_f": 70.0,
        "mass_f": 65.0,
        "outdoor_f": 90.0,
        "radiation_wm2": 0.0,
        "vent_open": 0.0,
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
    }

    air, _, glazing = predict_step(model, forcing)

    assert air == pytest.approx(80.0)
    assert glazing == pytest.approx(80.0)


def test_glazing_fit_and_diagnostics_use_end_of_step_observation_rows():
    training, _ = synthetic_2r2c_days(days=5, seed=37)
    training[-1] = replace(training[-1], glazing_f=None)

    fit_dynamics(training)
    diagnostics = fit_diagnostics(training)

    assert diagnostics["auxiliary_glazing_fitted_rows"] == len(training) - 2
    assert diagnostics["auxiliary_glazing_skipped_rows"] == 1


def test_synthetic_fixture_recovers_known_mass_coefficients():
    training, _ = synthetic_2r2c_days(days=21, seed=7)
    model = fit_dynamics(training)

    assert model.mass_coefficients["air_exchange"] == pytest.approx(
        0.008, abs=0.00002
    )
    assert model.mass_coefficients["outside_exchange"] == pytest.approx(
        0.003, abs=0.00002
    )
    assert model.mass_coefficients["solar_unshaded"] == pytest.approx(
        0.000035, abs=0.000001
    )
    assert model.mass_coefficients["solar_indoor_closed"] == pytest.approx(
        0.000014, abs=0.000001
    )
    assert model.mass_coefficients["solar_outdoor"] == pytest.approx(
        0.000007, abs=0.000001
    )


def test_multihorizon_selector_is_daily_bounded_and_spans_training_range():
    training, _ = synthetic_2r2c_days(days=90, seed=101)
    endpoints = dynamics._select_multihorizon_endpoints(training)

    assert tuple(endpoints) == (1, 12, 72, 144, 288)
    for steps, rows in endpoints.items():
        assert len(rows) <= 64
        assert len({
            row.origin.at.astimezone(dynamics.SITE_TIMEZONE).date()
            for row in rows
        }) == len(rows)
        assert all(len(row.forcings) == steps for row in rows)
        assert rows[0].origin.at < rows[-1].origin.at
    eligible_24h = dynamics._eligible_daily_endpoints(training, 288, ())
    assert endpoints[288][0] == eligible_24h[0]
    assert endpoints[288][-1] == eligible_24h[-1]


def test_daily_selector_prefers_longest_future_then_earliest_utc():
    start = datetime(2026, 5, 1, 6, 0, tzinfo=UTC)

    def segment(offset_minutes, rows):
        return [
            _sample(
                start + timedelta(minutes=offset_minutes + 5 * index),
                70.0,
                68.0,
                None,
                60.0,
                0.0,
                0.0,
                0.0,
                0.0,
            )
            for index in range(rows)
        ]

    first = segment(0, 7)
    longer_later = segment(60, 8)
    selected = dynamics._eligible_daily_endpoints(
        first + longer_later, 6, ()
    )
    assert len(selected) == 1
    assert selected[0].origin.at == longer_later[0].at

    equal_later = longer_later[:-1]
    selected = dynamics._eligible_daily_endpoints(
        first + equal_later, 6, ()
    )
    assert len(selected) == 1
    assert selected[0].origin.at == first[0].at


def test_uniform_origin_indices_are_exact_and_include_boundaries():
    assert dynamics._uniform_origin_indices(5, 64) == (0, 1, 2, 3, 4)
    indices = dynamics._uniform_origin_indices(100, 64)
    assert len(indices) == 64
    assert indices[0] == 0
    assert indices[-1] == 99
    assert indices == tuple((index * 99) // 63 for index in range(64))


@pytest.mark.parametrize(
    "mutation", ("gap", "unknown_action", "unknown_mode", "kiva")
)
def test_multihorizon_selector_rejects_invalid_interior_rows(mutation):
    training, _ = synthetic_2r2c_days(days=4, seed=103)
    damaged = list(training)
    index = 150
    invalid_at = damaged[index].at
    if mutation == "gap":
        damaged.pop(index)
    elif mutation == "unknown_action":
        damaged[index] = replace(damaged[index], vent_open=None)
    elif mutation == "unknown_mode":
        damaged[index] = replace(damaged[index], mode=None)
    else:
        damaged[index] = replace(damaged[index], passive_fit_allowed=False)

    endpoints = dynamics._select_multihorizon_endpoints(damaged)
    assert all(
        not (endpoint.origin.at < invalid_at <= endpoint.target.at)
        for rows in endpoints.values()
        for endpoint in rows
    )


def test_rollout_confidence_is_minimum_over_complete_prefix():
    training, _ = synthetic_2r2c_days(days=4, seed=107)
    training[10] = replace(training[10], action_confidence=0.35)
    endpoint = next(
        row for row in dynamics._eligible_daily_endpoints(training, 12, ())
        if row.origin.at < training[10].at <= row.target.at
    )
    assert endpoint.confidence == 0.35


def test_inactive_forcing_activation_excludes_only_affected_horizon():
    training, _ = synthetic_2r2c_days(days=4, seed=109)
    activation = training[20].at
    training = [
        replace(row, outdoor_shade_present=float(row.at >= activation))
        for row in training
    ]
    endpoints = dynamics._select_multihorizon_endpoints(
        training, ("solar_outdoor",)
    )
    assert all(
        all(
            dynamics.evaluation_forcing_features(row)["solar_outdoor"] == 0.0
            for row in endpoint.forcings
        )
        for rows in endpoints.values()
        for endpoint in rows
    )



def synthetic_latent_observer_days(days, seed):
    physical_training, physical_holdout = synthetic_2r2c_days(
        days=days, seed=seed
    )
    physical = physical_training + physical_holdout
    alpha = 1.0 - math.exp(-5.0 / 120.0)
    latent = physical[0].mass_f
    observed = []
    for row in physical:
        north_wall = row.mass_f
        latent += alpha * (north_wall - latent)
        observed.append(
            replace(row, mass_f=latent, north_wall_f=north_wall, mode="warm")
        )
    split = (days - 2) * 288
    return observed[:split], observed[split:]


def test_multihorizon_gradient_matches_centered_difference():
    training, _ = synthetic_2r2c_days(days=8, seed=113)
    initial, _ = dynamics._fit_five_minute_dynamics(
        training, allow_inactive_action_forcing=False
    )
    vector = dynamics._coefficient_vector(initial)
    endpoints = dynamics._select_multihorizon_endpoints(training)
    _, analytic = dynamics._multihorizon_objective_and_gradient(
        vector, endpoints
    )
    numeric = []
    epsilon = 1e-7
    for index in range(len(vector)):
        plus = vector.copy()
        minus = vector.copy()
        plus[index] += epsilon
        minus[index] -= epsilon
        plus_loss, _ = dynamics._multihorizon_objective_and_gradient(
            plus, endpoints
        )
        minus_loss, _ = dynamics._multihorizon_objective_and_gradient(
            minus, endpoints
        )
        numeric.append((plus_loss - minus_loss) / (2.0 * epsilon))
    assert np.asarray(analytic) == pytest.approx(
        np.asarray(numeric), rel=2e-5, abs=2e-6
    )


def test_multihorizon_refinement_reduces_latent_observer_open_loop_drift():
    training, holdout = synthetic_latent_observer_days(days=28, seed=127)
    initial, _ = dynamics._fit_five_minute_dynamics(
        training, allow_inactive_action_forcing=False
    )
    refined = dynamics.fit_dynamics_with_evidence(training)
    origin = 72
    target = origin + 288
    initial_prediction = simulate(
        initial, holdout[origin], holdout[origin + 1:target + 1]
    )[-1]
    refined_prediction = simulate(
        refined.dynamics, holdout[origin], holdout[origin + 1:target + 1]
    )[-1]
    initial_error = abs(initial_prediction["air_f"] - holdout[target].air_f)
    refined_error = abs(
        refined_prediction["air_f"] - holdout[target].air_f
    )
    assert refined_error < initial_error
    assert (
        refined.evidence.final_objective
        <= refined.evidence.initial_objective
    )
    validate_physics(refined.dynamics)


def test_multihorizon_fit_is_byte_deterministic():
    training, _ = synthetic_latent_observer_days(days=28, seed=131)
    first = dynamics.fit_dynamics_with_evidence(training)
    second = dynamics.fit_dynamics_with_evidence(training)
    assert first == second


@pytest.mark.parametrize("probe", ("unsuccessful", "nonfinite"))
def test_multihorizon_optimizer_failures_refuse(monkeypatch, probe):
    training, _ = synthetic_latent_observer_days(days=28, seed=137)
    original_minimize = dynamics.minimize

    def injected(fun, initial, **kwargs):
        if kwargs.get("options", {}).get("maxiter") != 500:
            return original_minimize(fun, initial, **kwargs)
        if probe == "unsuccessful":
            return SimpleNamespace(
                success=False,
                x=np.asarray(initial),
                message="injected failure",
            )
        return SimpleNamespace(
            success=True,
            x=np.full_like(np.asarray(initial), np.nan),
            message="injected nonfinite result",
        )

    monkeypatch.setattr(dynamics, "minimize", injected)
    with pytest.raises(ValueError, match="multihorizon"):
        dynamics.fit_dynamics_with_evidence(training)


@pytest.mark.parametrize(
    ("probe", "message"),
    (
        ("objective", "objective increased"),
        ("bounds", "exchange coefficients must be nonnegative"),
        ("solar_order", "shade gain exceeds"),
        ("output_range", "out of range"),
    ),
)
def test_multihorizon_optimizer_invalid_success_results_refuse(
    monkeypatch, probe, message
):
    training, _ = synthetic_latent_observer_days(days=28, seed=141)
    original_minimize = dynamics.minimize

    def injected(fun, initial, **kwargs):
        if kwargs.get("options", {}).get("maxiter") != 500:
            return original_minimize(fun, initial, **kwargs)
        candidate = np.asarray(initial, dtype=float).copy()
        if probe == "objective":
            baseline = float(fun(candidate))
            for index in range(len(candidate)):
                trial = candidate.copy()
                trial[index] = min(1.0, trial[index] + 1e-4)
                if float(fun(trial)) > baseline:
                    candidate = trial
                    break
            else:
                raise AssertionError("no increasing local objective probe")
        elif probe == "bounds":
            candidate[0] = -0.1
        elif probe == "solar_order":
            candidate[2] = 0.0
            candidate[3] = 1.0
        else:
            candidate[0] = 1e-6
            candidate[1] = 0.0
            candidate[6] = 1.0
        return SimpleNamespace(
            success=True,
            x=candidate,
            message=f"injected {probe}",
        )

    monkeypatch.setattr(dynamics, "minimize", injected)
    with pytest.raises(ValueError, match=message):
        dynamics.fit_dynamics_with_evidence(training)


def test_multihorizon_fit_requires_two_origins_at_every_horizon(monkeypatch):
    training, _ = synthetic_2r2c_days(days=8, seed=139)
    original = dynamics._select_multihorizon_endpoints

    def insufficient(samples, inactive_features=()):
        endpoints = original(samples, inactive_features)
        endpoints[288] = endpoints[288][:1]
        return endpoints

    monkeypatch.setattr(dynamics, "_select_multihorizon_endpoints", insufficient)
    with pytest.raises(ValueError, match="insufficient multihorizon.*1440"):
        dynamics.fit_dynamics_with_evidence(training)


def test_multihorizon_refinement_rejects_rank_deficient_endpoint_evidence():
    training, _ = synthetic_2r2c_days(days=8, seed=143)
    initial, inactive = dynamics._fit_five_minute_dynamics(
        training, allow_inactive_action_forcing=False
    )
    selected = dynamics._select_multihorizon_endpoints(training)
    rank_deficient = {}
    for steps, rows in selected.items():
        first, second = rows[:2]
        offset = second.origin.at - first.origin.at
        repeated_day = dynamics.RolloutEndpoint(
            origin=replace(first.origin, at=second.origin.at),
            forcings=tuple(
                replace(row, at=row.at + offset)
                for row in first.forcings
            ),
            target=replace(first.target, at=first.target.at + offset),
            confidence=first.confidence,
        )
        rank_deficient[steps] = (first, repeated_day)

    with pytest.raises(ValueError, match="multihorizon.*rank deficient"):
        dynamics._refine_multihorizon(
            initial, rank_deficient, inactive
        )


def test_multihorizon_fit_rejects_final_unstable_model(monkeypatch):
    training, _ = synthetic_latent_observer_days(days=28, seed=149)
    original = dynamics.validate_physics
    calls = 0

    def reject_final(model):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("transition eigenvalue reaches the unit circle")
        return original(model)

    monkeypatch.setattr(dynamics, "validate_physics", reject_final)
    with pytest.raises(ValueError, match="unit circle"):
        dynamics.fit_dynamics_with_evidence(training)
