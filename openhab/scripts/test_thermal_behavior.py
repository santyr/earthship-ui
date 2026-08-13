import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from thermal_model.behavior import (
    AIRFLOW_LEVELS,
    FEATURE_NAMES,
    INSUFFICIENT_DATA,
    baseline_schedule,
    feature_vector,
    fit_behavior,
    search_candidate_schedule,
    transition_probability,
)
from thermal_model.schema import BehaviorModel, DynamicsModel, ThermalSample


UTC = timezone.utc
DENVER = ZoneInfo("America/Denver")
STEP = timedelta(minutes=5)


@dataclass(frozen=True)
class ForecastRow:
    at: datetime
    outdoor_f: float
    radiation_wm2: float
    air_baseline_f: float
    mass_baseline_f: float
    mode: str
    indoor_shade_closed: float = 1.0
    outdoor_shade_present: float = 1.0


def _sample(
    at,
    *,
    vent,
    indoor,
    outdoor_shade,
    confidence=1.0,
    air=72.0,
    mass=68.0,
    outdoor=60.0,
    radiation=0.0,
):
    return ThermalSample(
        at=at,
        air_f=air,
        mass_f=mass,
        glazing_f=None,
        outdoor_f=outdoor,
        radiation_wm2=radiation,
        vent_open=vent,
        vent_confidence=confidence,
        indoor_shade_closed=indoor,
        indoor_shade_confidence=confidence,
        outdoor_shade_present=outdoor_shade,
        outdoor_shade_confidence=confidence,
        action_confidence=confidence,
        passive_fit_allowed=True,
    )


def confirmed_warm_samples(open_minute=1230, close_minute=420, days=14):
    start = datetime(2026, 6, 1, tzinfo=DENVER)
    rows = []
    for index in range(days * 288):
        at = start + index * STEP
        minute = at.hour * 60 + at.minute
        vent = float(minute >= open_minute or minute < close_minute)
        indoor = float(600 <= minute < 1140)
        rows.append(
            _sample(
                at,
                vent=vent,
                indoor=indoor,
                outdoor_shade=1.0,
                air=75.0,
                mass=70.0,
                outdoor=60.0,
                radiation=0.0,
            )
        )
    return rows


def warm_forecast(hours=36, *, hot=False):
    start = datetime(2026, 7, 1, tzinfo=DENVER)
    rows = []
    for index in range(hours * 12):
        at = start + index * STEP
        minute = at.hour * 60 + at.minute
        daylight = 360 <= minute < 1200
        outdoor = (58.0 if minute >= 1200 or minute < 480 else 86.0) if hot else 60.0
        radiation = (700.0 if daylight else 0.0) if hot else 0.0
        rows.append(
            ForecastRow(
                at=at,
                outdoor_f=outdoor,
                radiation_wm2=radiation,
                air_baseline_f=(78.0 if daylight else 74.0) if hot else 75.0,
                mass_baseline_f=70.0,
                mode="warm",
                indoor_shade_closed=float(daylight),
                outdoor_shade_present=1.0,
            )
        )
    return rows


def winter_forecast(*, sunny):
    start = datetime(2026, 1, 10, tzinfo=DENVER)
    rows = []
    for index in range(24 * 12):
        at = start + index * STEP
        minute = at.hour * 60 + at.minute
        daylight = 450 <= minute < 1020
        radiation = 500.0 if sunny and daylight else (40.0 if daylight else 0.0)
        rows.append(
            ForecastRow(
                at=at,
                outdoor_f=34.0 if daylight else 20.0,
                radiation_wm2=radiation,
                air_baseline_f=64.0,
                mass_baseline_f=61.0,
                mode="winter",
                indoor_shade_closed=1.0,
                outdoor_shade_present=0.0,
            )
        )
    return rows


def stable_model():
    return DynamicsModel(
        version=1,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.02,
            "mass_exchange": 0.04,
            "solar_unshaded": 0.00012,
            "solar_indoor_closed": 0.00004,
            "solar_outdoor": 0.00002,
            "vent_exchange": 0.06,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": 0.008,
            "solar_unshaded": 0.00003,
            "solar_indoor_closed": 0.00001,
            "solar_outdoor": 0.000005,
        },
        glazing_observation_coefficients={},
    )


def warm_behavior():
    return fit_behavior(confirmed_warm_samples())


def test_feature_order_is_fixed_and_probability_uses_that_order():
    assert FEATURE_NAMES == (
        "intercept",
        "sin_time",
        "cos_time",
        "sin_year",
        "cos_year",
        "outdoor_minus_air",
        "mass_minus_air",
        "radiation_norm",
        "solar_elevation_sin",
        "is_daylight",
    )
    coefficients = (0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    model = BehaviorModel(1, FEATURE_NAMES, {"vent_open": coefficients})
    features = {name: 0.0 for name in reversed(FEATURE_NAMES)}
    features["sin_time"] = 2.0
    features["intercept"] = 1.0
    assert transition_probability(model, "vent_open", features) == pytest.approx(
        1.0 / (1.0 + math.exp(-2.0))
    )


def test_time_features_use_denver_local_time_for_utc_samples():
    noon_mdt = _sample(
        datetime(2026, 7, 1, 18, 0, tzinfo=UTC),
        vent=0.0,
        indoor=0.0,
        outdoor_shade=1.0,
    )
    values = feature_vector(noon_mdt)
    assert values[1] == pytest.approx(0.0, abs=1e-12)
    assert values[2] == pytest.approx(-1.0)


def test_fit_learns_all_six_hazards_or_explicitly_abstains():
    model = fit_behavior(confirmed_warm_samples())
    assert set(model.transitions) == {
        "vent_open",
        "vent_close",
        "indoor_shade_open",
        "indoor_shade_close",
        "outdoor_shade_installed",
        "outdoor_shade_removed",
    }
    for transition in (
        "vent_open",
        "vent_close",
        "indoor_shade_open",
        "indoor_shade_close",
    ):
        assert len(model.transitions[transition]) == len(FEATURE_NAMES)
    assert model.transitions["outdoor_shade_installed"] == ()
    assert model.transitions["outdoor_shade_removed"] == ()
    assert (
        transition_probability(model, "outdoor_shade_installed", (1.0,) * 10)
        == INSUFFICIENT_DATA
    )


def test_model_inferred_confidence_does_not_supply_positive_labels():
    rows = confirmed_warm_samples(days=12)
    inferred = [replace(row, action_confidence=0.15) for row in rows]
    model = fit_behavior(inferred)
    assert all(coefficients == () for coefficients in model.transitions.values())


def test_features_for_a_transition_do_not_use_the_future_sample_values():
    start = datetime(2026, 6, 1, tzinfo=DENVER)
    original = []
    changed_future = []
    for day in range(12):
        at = start + timedelta(days=day, hours=20)
        left = _sample(
            at,
            vent=0.0,
            indoor=1.0,
            outdoor_shade=1.0,
            outdoor=60.0 + day,
            radiation=20.0,
        )
        previous = replace(left, at=at - STEP)
        right = replace(left, at=at + STEP, vent_open=1.0)
        original.extend((previous, left, right))
        changed_future.extend(
            (
                previous,
                left,
                replace(
                    right,
                    air_f=110.0,
                    mass_f=40.0,
                    outdoor_f=-20.0,
                    radiation_wm2=1500.0,
                ),
            )
        )
    first = fit_behavior(original)
    second = fit_behavior(changed_future)
    assert first.transitions["vent_open"]
    assert first.transitions["vent_open"] == pytest.approx(
        second.transitions["vent_open"]
    )


def test_weighted_fit_gives_confirmed_rows_more_influence_than_reconstructed_rows():
    rows = confirmed_warm_samples(open_minute=1200, days=12)
    weak_late = []
    for row in confirmed_warm_samples(open_minute=1320, days=12):
        weak_late.append(replace(row, at=row.at + timedelta(days=20), action_confidence=0.35))
    model = fit_behavior(rows + weak_late)
    schedule = baseline_schedule(model, warm_forecast())
    assert abs(schedule["ventOpenMinute"] - 1200) < abs(
        schedule["ventOpenMinute"] - 1320
    )


def test_learned_warm_schedule_tracks_confirmed_transition_times():
    model = fit_behavior(confirmed_warm_samples(open_minute=1230, close_minute=420))
    schedule = baseline_schedule(model, warm_forecast())
    assert abs(schedule["ventOpenMinute"] - 1230) <= 20
    assert abs(schedule["ventCloseMinute"] - 420) <= 20
    assert schedule["vent"] == "open"
    assert schedule["ventFlow"] == "baseline"


def test_warm_baseline_venting_is_mandatory_and_airflow_levels_are_explicit():
    schedule = baseline_schedule(warm_behavior(), warm_forecast())
    assert schedule["vent"] == "open"
    assert schedule["airflowSegments"][0]["level"] == "baseline"
    assert AIRFLOW_LEVELS == {"closed": 0.0, "baseline": 1.0, "boosted": 2.0}


def test_candidate_never_vents_while_outdoor_is_warmer_and_requires_one_cool_hour():
    forecast = warm_forecast(hot=True)
    result = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=forecast
    )
    open_rows = [
        row
        for row in forecast
        if result.vent_open_at <= row.at < result.vent_close_at
    ]
    assert len(open_rows) >= 12
    assert all(row.outdoor_f < row.air_baseline_f for row in open_rows)
    assert all(
        row.outdoor_f <= row.air_baseline_f - 1.0 for row in open_rows[:12]
    )


def test_search_stays_on_quarter_hours_within_two_hours_of_learned_baseline():
    baseline = baseline_schedule(warm_behavior(), warm_forecast())
    result = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=warm_forecast()
    )
    candidate = result.candidate
    for key, baseline_key in (
        ("ventOpenMinute", "ventOpenMinute"),
        ("ventCloseMinute", "ventCloseMinute"),
    ):
        assert candidate[key] % 15 == 0
        delta = abs(candidate[key] - baseline[baseline_key])
        delta = min(delta, 1440 - delta)
        assert delta <= 120


def test_search_reports_modeled_comparison_and_rejection_reasons_deterministically():
    first = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=warm_forecast()
    )
    second = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=warm_forecast()
    )
    assert first == second
    assert first.baseline
    assert first.candidate
    assert first.modeled_difference["kind"] == "modeled_counterfactual"
    assert "causal" not in first.modeled_difference["description"].lower()
    assert isinstance(first.rejected_candidate_counts, dict)


def test_outdoor_shades_are_fixed_seasonal_configuration_not_search_variable():
    forecast = warm_forecast()
    baseline = baseline_schedule(warm_behavior(), forecast)
    result = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=forecast
    )
    assert baseline["outdoorShade"] == "present"
    assert result.candidate["outdoorShade"] == baseline["outdoorShade"]


def test_winter_cold_cloudy_schedule_keeps_shades_and_vents_closed():
    schedule = baseline_schedule(warm_behavior(), winter_forecast(sunny=False))
    assert schedule["indoorShadeDay"] == "closed"
    assert schedule["indoorShadeNight"] == "closed"
    assert schedule["vent"] == "closed"
    result = search_candidate_schedule(
        behavior=warm_behavior(),
        dynamics=stable_model(),
        forecast=winter_forecast(sunny=False),
    )
    assert result.candidate["vent"] == "closed"
    assert result.candidate["indoorShadeDay"] == "closed"


def test_sunny_winter_day_may_charge_mass_but_closes_by_sunset():
    forecast = winter_forecast(sunny=True)
    schedule = baseline_schedule(warm_behavior(), forecast)
    assert schedule["indoorShadeDay"] == "open"
    assert schedule["indoorShadeNight"] == "closed"
    assert schedule["shadeCloseAt"] <= max(
        row.at for row in forecast if row.radiation_wm2 > 0.0
    ) + STEP
    assert schedule["vent"] == "closed"


def test_feature_vector_is_finite_and_scaled_for_optimizer():
    row = confirmed_warm_samples(days=1)[100]
    values = feature_vector(row)
    assert len(values) == len(FEATURE_NAMES)
    assert values[0] == 1.0
    assert all(math.isfinite(value) for value in values)
    assert abs(values[7]) <= 1.6
