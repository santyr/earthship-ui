import math
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from thermal_model.dynamics import (
    AIR_BOUNDS,
    MASS_BOUNDS,
    fit_diagnostics,
    fit_dynamics,
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
    )


def synthetic_2r2c_days(days, seed):
    rng = random.Random(seed)
    at = datetime(2026, 5, 1, tzinfo=UTC)
    air = 70.0
    mass = 67.0
    rows = []
    for index in range(days * 288):
        minute = index % 288
        day = index // 288
        angle = 2.0 * math.pi * minute / 288.0
        radiation = max(0.0, 760.0 * math.sin(angle - math.pi / 2.0))
        outdoor = 61.0 + 18.0 * math.sin(angle - math.pi / 2.0)
        vent = float(minute >= 225 or minute < 72)
        indoor = float(105 <= minute < 210 and day % 3 != 0)
        outdoor_shade = float(day % 4 in (1, 2))
        unshaded = (1.0 - indoor) * (1.0 - outdoor_shade)
        outdoor_shaded = (1.0 - indoor) * outdoor_shade
        glazing = (
            4.0
            + 0.72 * air
            + 0.20 * outdoor
            + 0.0030 * radiation * unshaded
            + 0.0013 * radiation * indoor
            + 0.0008 * radiation * outdoor_shaded
            + rng.uniform(-0.02, 0.02)
        )
        rows.append(
            _sample(
                at,
                air,
                mass,
                glazing,
                outdoor,
                radiation,
                vent,
                indoor,
                outdoor_shade,
            )
        )
        air += (
            0.018 * (outdoor - air)
            + 0.040 * (mass - air)
            + 0.00015 * radiation * unshaded
            + 0.00006 * radiation * indoor
            + 0.00003 * radiation * outdoor_shaded
            + 0.070 * vent * (outdoor - air)
            + 0.002
            + rng.uniform(-0.003, 0.003)
        )
        mass += (
            0.008 * (air - mass)
            + 0.000035 * radiation * unshaded
            + 0.000014 * radiation * indoor
            + 0.000007 * radiation * outdoor_shaded
            + rng.uniform(-0.001, 0.001)
        )
        at += STEP
    split = (days - 2) * 288
    return rows[:split], rows[split:]


def _forcing_rows(samples):
    return samples[:-1]


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
    assert model.air_coefficients["outside_exchange"] >= 0
    assert model.air_coefficients["mass_exchange"] >= 0
    assert model.mass_coefficients["air_exchange"] >= 0
    assert set(model.glazing_observation_coefficients) == {
        "intercept",
        "air",
        "outdoor",
        "solar_unshaded",
        "solar_indoor_closed",
        "solar_outdoor",
    }


def test_fit_rejects_shaded_gain_above_unshaded_gain():
    model = DynamicsModel(
        version=1,
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
        "action_label_coverage_fraction": pytest.approx(6 / 9),
    }


def test_boosted_ventilation_forcing_scales_effective_outdoor_exchange():
    model = DynamicsModel(
        version=1,
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
    boosted_air, _, _ = predict_step(model, forcing | {"vent_open": 1.5})

    assert baseline_air == pytest.approx(78.0)
    assert boosted_air == pytest.approx(77.0)


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
        version=1,
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
        version=1,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.0,
            "mass_exchange": 0.0,
            "solar_unshaded": 0.001,
            "solar_indoor_closed": 0.0005,
            "solar_outdoor": 0.0002,
            "vent_exchange": 0.8,
            "bias": 0.2,
        },
        mass_coefficients={
            "air_exchange": 0.0,
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
        version=1,
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
        [0.0, 0.0, 0.0, 0.0],
        [0.20, 0.008, 0.004, 0.006],
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
        version=1,
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
        confidence_weighted[index - 1] = replace(
            confidence_weighted[index - 1], action_confidence=0.01
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

    assert weighted_error < unweighted_error * 0.05


def test_simulation_is_repeatable_and_never_clamps_out_of_range_output():
    model = DynamicsModel(
        version=1,
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
