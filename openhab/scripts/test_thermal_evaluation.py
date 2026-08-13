from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
from types import SimpleNamespace

import pytest
from zoneinfo import ZoneInfo

from thermal_model.dynamics import predict_step
from thermal_model.behavior import FEATURE_NAMES, TRANSITIONS
from thermal_model.evaluation import threshold_advisory, walk_forward_evaluate
from thermal_model.schema import BehaviorModel, DynamicsModel, ThermalSample


STEP = timedelta(minutes=5)
UTC = timezone.utc
SITE_TIMEZONE = ZoneInfo("America/Denver")


def fixed_model():
    return DynamicsModel(
        version=1,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.018,
            "mass_exchange": 0.040,
            "solar_unshaded": 0.00015,
            "solar_indoor_closed": 0.00006,
            "solar_outdoor": 0.00003,
            "vent_exchange": 0.070,
            "bias": 0.002,
        },
        mass_coefficients={
            "air_exchange": 0.008,
            "solar_unshaded": 0.000035,
            "solar_indoor_closed": 0.000014,
            "solar_outdoor": 0.000007,
        },
        glazing_observation_coefficients={},
    )


def samples_45_days():
    model = fixed_model()
    start = datetime(2026, 5, 1, tzinfo=SITE_TIMEZONE)
    air = 72.0
    mass = 70.0
    rows = []
    for index in range(45 * 24 * 12):
        at = start + index * STEP
        minute = at.hour * 60 + at.minute
        phase = 2.0 * math.pi * minute / 1440.0
        outdoor = 68.0 + 13.0 * math.sin(phase - math.pi / 2.0)
        radiation = max(0.0, 700.0 * math.sin(phase - math.pi / 2.0))
        forcing = {
            "air_f": air,
            "mass_f": mass,
            "outdoor_f": outdoor,
            "radiation_wm2": radiation,
            "vent_open": 0.0,
            "indoor_shade_closed": 0.0,
            "outdoor_shade_present": 0.0,
        }
        air, mass, _ = predict_step(model, forcing)
        rows.append(
            ThermalSample(
                at=at,
                air_f=air,
                mass_f=mass,
                glazing_f=None,
                outdoor_f=outdoor,
                radiation_wm2=radiation,
                vent_open=0.0,
                vent_confidence=1.0,
                indoor_shade_closed=0.0,
                indoor_shade_confidence=1.0,
                outdoor_shade_present=0.0,
                outdoor_shade_confidence=1.0,
                action_confidence=1.0,
                passive_fit_allowed=True,
                mode="warm",
            )
        )
    return rows


def test_walk_forward_never_trains_on_or_after_prediction_day():
    seen = []
    report = walk_forward_evaluate(
        samples_45_days(),
        fit=lambda train: seen.append(train[-1].at) or fixed_model(),
    )

    assert len(report["folds"]) == 31
    assert all(
        datetime.fromisoformat(fold["train_end"].replace("Z", "+00:00"))
        < datetime.fromisoformat(fold["prediction_start"].replace("Z", "+00:00"))
        for fold in report["folds"]
    )
    assert seen == [
        datetime.fromisoformat(fold["train_end"].replace("Z", "+00:00"))
        for fold in report["folds"]
    ]
    assert report["folds"][0]["horizons_hours"] == [1, 6, 12, 24, 48, 72]
    assert 72 not in report["folds"][-1]["horizons_hours"]




def test_report_contains_required_metrics_baselines_splits_and_shadow_gates():
    report = walk_forward_evaluate(samples_45_days(), fit=lambda train: fixed_model())
    metrics = report["metrics"]

    assert metrics["overall"]["model"]["air"]["24"]["mae"] < 1e-10
    assert (
        metrics["overall"]["model"]["air"]["24"]["mae"]
        < metrics["overall"]["persistence"]["air"]["24"]["mae"]
    )
    assert metrics["overall"]["recent_cycle"]["air"]["72"]["count"] > 0
    assert metrics["by_regime"]["warm"]["air"]["24"]["count"] > 0
    assert metrics["by_regime"]["winter"] == {}
    assert metrics["by_regime"]["shoulder"] == {}
    assert metrics["by_provenance"]["confirmed"]["air"]["24"]["count"] > 0
    assert metrics["daily"]["hallway_high_f"]["count"] > 0
    assert metrics["daily"]["hallway_low_f"]["count"] > 0
    assert metrics["daily"]["peak_time_minutes"]["count"] > 0
    assert metrics["daily"]["morning_mass_f"]["count"] > 0
    assert metrics["prediction_interval_coverage"]["air"]["24"]["count"] > 0

    promotion = metrics["promotion"]
    assert promotion["eligible"] is True
    assert promotion["shadow_only"] is True
    assert set(promotion["gates"]) == {
        "physics_valid",
        "finite_metrics",
        "at_least_two_folds",
        "air_24h_beats_persistence",
    }
    assert all(promotion["gates"].values())


def test_missing_future_samples_omit_only_uncovered_horizons_and_report_is_deterministic():
    rows = samples_45_days()
    first_origin = rows[14 * 24 * 12]
    missing_at = first_origin.at + timedelta(hours=48)
    incomplete = [row for row in rows if row.at != missing_at]

    first = walk_forward_evaluate(incomplete, fit=lambda train: fixed_model())
    second = walk_forward_evaluate(incomplete, fit=lambda train: fixed_model())

    assert first == second
    assert json.dumps(first, allow_nan=False, sort_keys=True)
    assert first["folds"][0]["horizons_hours"] == [1, 6, 12, 24]
    assert first["metrics"]["overall"]["model"]["air"]["48"]["count"] > 0


@pytest.mark.parametrize(
    ("tomorrow_high", "three_day_average", "expected"),
    [
        (89.99, 91.99, "none"),
        (90.0, 91.99, "vent_tonight"),
        (94.99, 92.0, "close_up_tomorrow"),
        (95.0, None, "close_up_tomorrow"),
    ],
)
def test_threshold_baseline_preserves_existing_boundaries(
    tomorrow_high, three_day_average, expected
):
    assert threshold_advisory(tomorrow_high, three_day_average) == expected


def test_behavior_metrics_are_reported_when_transition_labels_exist():
    rows = [
        replace(
            row,
            vent_open=float(
                row.at.hour * 60 + row.at.minute >= 20 * 60 + 30
                or row.at.hour * 60 + row.at.minute < 7 * 60
            ),
        )
        for row in samples_45_days()
    ]
    behavior = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={
            transition: (
                tuple(0.0 for _ in FEATURE_NAMES)
                if transition in {"vent_open", "vent_close"}
                else ()
            )
            for transition in TRANSITIONS
        },
    )
    report = walk_forward_evaluate(
        rows,
        fit=lambda train: SimpleNamespace(
            dynamics=fixed_model(), behavior=behavior
        ),
    )

    behavior_metrics = report["metrics"]["behavior"]
    assert behavior_metrics["available"] is True
    assert behavior_metrics["label_count"] > 0
    assert behavior_metrics["precision"] is not None
    assert behavior_metrics["recall"] is not None
    assert behavior_metrics["median_timing_error_minutes"] is not None


def test_unphysical_fold_models_fail_the_shadow_promotion_gate():
    dynamics = fixed_model()
    coefficients = dict(dynamics.air_coefficients)
    coefficients["outside_exchange"] = -0.01
    unphysical = replace(dynamics, air_coefficients=coefficients)

    report = walk_forward_evaluate(
        samples_45_days(), fit=lambda train: unphysical
    )

    assert report["metrics"]["promotion"]["eligible"] is False
    assert report["metrics"]["promotion"]["gates"]["physics_valid"] is False



def test_overlapping_long_horizons_calibrate_only_after_targets_are_observed():
    report = walk_forward_evaluate(
        samples_45_days(), fit=lambda train: fixed_model()
    )
    metrics = report["metrics"]
    records = report["prediction_records"]

    assert records
    assert all(
        datetime.fromisoformat(record["origin_at"].replace("Z", "+00:00"))
        < datetime.fromisoformat(record["target_at"].replace("Z", "+00:00"))
        for record in records
    )
    for hours, unavailable_origins in ((48, 2), (72, 3)):
        scored = metrics["overall"]["model"]["air"][str(hours)]["count"]
        calibrated = metrics["prediction_interval_coverage"]["air"][
            str(hours)
        ]["count"]
        assert calibrated == scored - unavailable_origins
