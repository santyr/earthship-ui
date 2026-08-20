import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import thermal_model.behavior as behavior
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
    mode="warm",
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
        mode=mode,
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


def confirmed_winter_samples(open_minute=600, close_minute=840, days=14):
    start = datetime(2026, 1, 1, tzinfo=DENVER)
    rows = []
    for index in range(days * 288):
        at = start + index * STEP
        minute = at.hour * 60 + at.minute
        indoor_closed = float(not (open_minute <= minute < close_minute))
        radiation = 500.0 if 450 <= minute < 1020 else 0.0
        rows.append(
            _sample(
                at,
                vent=0.0,
                indoor=indoor_closed,
                outdoor_shade=0.0,
                air=64.0,
                mass=61.0,
                outdoor=30.0,
                radiation=radiation,
                mode="winter",
            )
        )
    return rows


def warm_samples_with_boosted_doors():
    rows = confirmed_warm_samples()
    return [
        replace(
            row,
            vent_open=2.0
            if 390 <= row.at.hour * 60 + row.at.minute < 420
            else row.vent_open,
        )
        for row in rows
    ]


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


def winter_forecast(*, sunny, hours=36):
    start = datetime(2026, 1, 10, tzinfo=DENVER)
    rows = []
    for index in range(hours * 12):
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
        version=2,
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
            "outside_exchange": 0.0,
            "solar_unshaded": 0.00003,
            "solar_indoor_closed": 0.00001,
            "solar_outdoor": 0.000005,
        },
        glazing_observation_coefficients={},
    )


def warm_behavior():
    return fit_behavior(confirmed_warm_samples())


def winter_behavior():
    return fit_behavior(confirmed_winter_samples())


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



def test_transition_rows_include_only_source_state_risk_set():
    start = datetime(2026, 7, 1, tzinfo=DENVER)
    states = (0.0, 0.0, 1.0, 1.0, 2.0, 0.0, None)
    rows = [
        _sample(
            start + index * STEP,
            vent=state,
            indoor=1.0,
            outdoor_shade=1.0,
        )
        for index, state in enumerate(states)
    ]

    _, open_labels, _ = behavior._transition_rows(rows, "vent_open")
    _, close_labels, _ = behavior._transition_rows(rows, "vent_close")

    assert open_labels.tolist() == [0.0, 1.0]
    assert close_labels.tolist() == [0.0, 0.0, 1.0]


@pytest.mark.parametrize(
    ("transition", "field", "states", "expected"),
    (
        ("indoor_shade_open", "indoor", (1.0, 1.0, 0.0, 0.0), [0.0, 1.0]),
        ("indoor_shade_close", "indoor", (0.0, 0.0, 1.0, 1.0), [0.0, 1.0]),
        (
            "outdoor_shade_installed",
            "outdoor_shade",
            (0.0, 0.0, 1.0, 1.0),
            [0.0, 1.0],
        ),
        (
            "outdoor_shade_removed",
            "outdoor_shade",
            (1.0, 1.0, 0.0, 0.0),
            [0.0, 1.0],
        ),
    ),
)
def test_shade_transition_rows_use_matching_source_state(
    transition, field, states, expected
):
    start = datetime(2026, 7, 1, tzinfo=DENVER)
    rows = []
    for index, state in enumerate(states):
        values = {"vent": 0.0, "indoor": 1.0, "outdoor_shade": 1.0}
        values[field] = state
        rows.append(
            _sample(
                start + index * STEP,
                vent=values["vent"],
                indoor=values["indoor"],
                outdoor_shade=values["outdoor_shade"],
            )
        )
    _, labels, _ = behavior._transition_rows(rows, transition)
    assert labels.tolist() == expected



def test_model_inferred_confidence_does_not_supply_positive_labels():
    rows = confirmed_warm_samples(days=12)
    inferred = [replace(row, action_confidence=0.15) for row in rows]
    model = fit_behavior(inferred)
    assert all(coefficients == () for coefficients in model.transitions.values())


def _isolated_vent_transition_pairs(count, left_vent_confidence):
    start = datetime(2026, 7, 1, 20, 0, tzinfo=DENVER)
    rows = []
    for day in range(count):
        at = start + timedelta(days=day)
        left = _sample(
            at,
            vent=0.0,
            indoor=1.0,
            outdoor_shade=1.0,
        )
        left = replace(
            left,
            vent_confidence=left_vent_confidence,
            action_confidence=0.15,
        )
        right = replace(
            left,
            at=at + STEP,
            vent_open=1.0,
            vent_confidence=1.0,
            action_confidence=1.0,
        )
        rows.extend((left, right))
    return rows


def test_inferred_left_state_cannot_enter_transition_risk_set():
    rows = _isolated_vent_transition_pairs(1, left_vent_confidence=0.15)

    _, labels, _ = behavior._transition_rows(rows, "vent_open")

    assert labels.tolist() == []


def test_ten_inferred_left_pairs_create_no_positive_or_source_vocabulary():
    rows = _isolated_vent_transition_pairs(10, left_vent_confidence=0.15)

    _, labels, _ = behavior._transition_rows(rows, "vent_open")
    model = fit_behavior(rows)
    vocabulary = {item.mode: item for item in model.seasonal_vocabulary}["warm"]

    assert labels.tolist() == []
    assert model.transitions["vent_open"] == ()
    assert "vent_open" not in vocabulary.transitions
    assert "closed" not in dict(vocabulary.action_states)["vent"]


def test_reconstructed_left_and_confirmed_right_are_eligible_by_action_confidence():
    rows = _isolated_vent_transition_pairs(1, left_vent_confidence=0.35)

    _, labels, weights = behavior._transition_rows(rows, "vent_open")
    model = fit_behavior(rows)
    vocabulary = {item.mode: item for item in model.seasonal_vocabulary}["warm"]

    assert labels.tolist() == [1.0]
    assert weights.tolist() == [1.0]
    assert "vent_open" in vocabulary.transitions
    assert dict(vocabulary.action_states)["vent"] == ("closed", "open")


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


def test_empty_model_counterfactual_does_not_describe_fallback_as_learned():
    empty = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )

    result = search_candidate_schedule(
        behavior=empty,
        dynamics=stable_model(),
        forecast=warm_forecast(),
    )

    description = result.modeled_difference["description"].lower()
    assert "learned" not in description
    assert "baseline schedule" in description


def test_outdoor_shades_are_fixed_seasonal_configuration_not_search_variable():
    forecast = warm_forecast()
    baseline = baseline_schedule(warm_behavior(), forecast)
    result = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=forecast
    )
    assert baseline["outdoorShade"] == "present"
    assert baseline["outdoorShadeSource"] == "forecast_state"
    assert baseline["outdoorShadeStatus"] == "observed"
    assert result.candidate["outdoorShade"] == baseline["outdoorShade"]


def test_unknown_outdoor_shade_forecast_is_explicit_protocol_fallback():
    empty = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )
    forecast = [
        replace(row, outdoor_shade_present=None)
        for row in warm_forecast()
    ]

    schedule = baseline_schedule(empty, forecast)

    assert schedule["outdoorShade"] == "present"
    assert schedule["outdoorShadeSource"] == "protocol_fallback"
    assert schedule["outdoorShadeStatus"] == INSUFFICIENT_DATA


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
    assert result.baseline["vent"] == "closed"
    assert result.baseline["indoorShadeDay"] == "closed"
    assert result.candidate is None


def test_sunny_winter_day_may_charge_mass_but_closes_by_sunset():
    forecast = winter_forecast(sunny=True)
    schedule = baseline_schedule(warm_behavior(), forecast)
    assert schedule["indoorShadeDay"] == "open"
    assert schedule["indoorShadeNight"] == "closed"
    assert schedule["shadeCloseAt"] <= max(
        row.at for row in forecast if row.radiation_wm2 > 0.0
    ) + STEP
    assert schedule["vent"] == "closed"



def _nonwinter_forecast(mode, *, with_solar=True):
    rows = warm_forecast(hours=36, hot=True)
    return [
        replace(
            row,
            mode=mode,
            radiation_wm2=row.radiation_wm2 if with_solar else 0.0,
            indoor_shade_closed=None,
            outdoor_shade_present=0.0 if mode == "fall_charge" else 1.0,
        )
        for row in rows
    ]


@pytest.mark.parametrize("mode", ["warm", "spring"])
def test_warm_and_spring_shades_close_in_sunny_day_and_open_at_night(mode):
    forecast = _nonwinter_forecast(mode)
    model = warm_behavior() if mode == "warm" else BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )

    schedule = baseline_schedule(model, forecast)
    forcings = behavior._forcing_rows(forecast, schedule)
    by_at = {row.at: forcing for row, forcing in zip(forecast[1:], forcings)}
    daytime = next(row for row in forecast[1:] if row.at.hour == 12)
    nighttime = next(row for row in forecast[1:] if row.at.hour == 23)

    assert by_at[daytime.at]["indoor_shade_closed"] == 1.0
    assert by_at[nighttime.at]["indoor_shade_closed"] == 0.0
    assert schedule["indoorShadeDay"] == "closed"
    assert schedule["indoorShadeNight"] == "open"
    assert {item["state"] for item in schedule["shadeTransitions"]} == {
        "closed",
        "open",
    }
    assert schedule["shadeTimingSource"] == (
        "learned" if mode == "warm" else "forecast_radiation_fallback"
    )


def test_fall_charge_keeps_indoor_shades_open_for_mass_charging_and_at_night():
    forecast = _nonwinter_forecast("fall_charge")
    empty = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )

    schedule = baseline_schedule(empty, forecast)
    forcings = behavior._forcing_rows(forecast, schedule)

    assert schedule["indoorShadeDay"] == "open"
    assert schedule["indoorShadeNight"] == "open"
    assert schedule["shadeTransitions"] == ()
    assert schedule["shadeTimingSource"] == "mass_charging_protocol"
    assert all(row["indoor_shade_closed"] == 0.0 for row in forcings)


def test_nonwinter_candidate_and_baseline_share_time_varying_shade_forcing():
    forecast = _nonwinter_forecast("warm")
    result = search_candidate_schedule(
        behavior=warm_behavior(),
        dynamics=stable_model(),
        forecast=forecast,
    )
    assert result.candidate is not None

    for schedule in (result.baseline, result.candidate):
        forcings = behavior._forcing_rows(forecast, schedule)
        by_hour = {
            row.at.hour: forcing["indoor_shade_closed"]
            for row, forcing in zip(forecast[1:24 * 12 + 1], forcings)
        }
        assert by_hour[12] == 1.0
        assert by_hour[23] == 0.0


def test_explicit_horizon_mode_transition_retains_baseline_without_candidate():
    forecast = warm_forecast(hours=36, hot=True)
    transition_at = forecast[18 * 12].at
    forecast = [
        replace(row, mode="fall_charge") if row.at >= transition_at else row
        for row in forecast
    ]

    result = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=forecast
    )
    forcings = behavior._forcing_rows(forecast, result.baseline)
    before = next(
        forcing["indoor_shade_closed"]
        for row, forcing in zip(forecast[1:], forcings)
        if row.at == transition_at - STEP
    )
    after = next(
        forcing["indoor_shade_closed"]
        for row, forcing in zip(forecast[1:], forcings)
        if row.at == transition_at
    )

    assert before == 1.0
    assert after == 0.0
    assert result.candidate is None
    assert result.modeled_difference["selectionReason"] == "explicit_mode_transition"
    assert result.rejected_candidate_counts == {"explicit_mode_transition": 1}


def test_nonwinter_shade_transition_is_not_invented_without_solar_or_learned_evidence():
    forecast = _nonwinter_forecast("spring", with_solar=False)
    empty = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )

    schedule = baseline_schedule(empty, forecast)

    assert schedule["shadeTransitions"] == ()
    assert schedule["shadeTimingSource"] == "forecast_radiation_fallback"
    assert schedule["shadeTimingStatus"] == INSUFFICIENT_DATA


def test_fit_persists_observed_seasonal_action_vocabulary_and_boosted_windows():
    model = fit_behavior(warm_samples_with_boosted_doors())
    vocabulary = {item.mode: item for item in model.seasonal_vocabulary}["warm"]
    states = dict(vocabulary.action_states)

    assert states["vent"] == ("closed", "open")
    assert states["indoor_shade"] == ("closed", "open")
    assert states["outdoor_shade"] == ("present",)
    assert {"vent_open", "vent_close"} <= set(vocabulary.transitions)
    assert vocabulary.airflow_levels == ("closed", "baseline", "boosted")
    assert vocabulary.boosted_windows == ((390, 420),)


def test_protocol_defaults_are_explicitly_insufficient_not_learned():
    empty = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )
    warm = baseline_schedule(empty, warm_forecast())
    winter = baseline_schedule(empty, winter_forecast(sunny=True))

    assert warm["ventOpenMinute"] == 1230
    assert warm["ventCloseMinute"] == 420
    assert warm["timingSource"] == "protocol_fallback"
    assert warm["timingStatus"] == INSUFFICIENT_DATA
    assert warm["ventTimingSource"] == "protocol_fallback"
    assert winter["shadeTimingSource"] == "protocol_fallback"
    assert winter["shadeTimingStatus"] == INSUFFICIENT_DATA


def test_learned_timing_and_vocabulary_are_not_confused_with_protocol_fallback():
    warm = baseline_schedule(warm_behavior(), warm_forecast())
    winter = baseline_schedule(winter_behavior(), winter_forecast(sunny=True))

    assert warm["timingSource"] == "learned"
    assert warm["timingStatus"] == "fitted"
    assert winter["shadeTimingSource"] == "learned"
    assert winter["shadeTimingStatus"] == "fitted"
    assert abs(winter["shadeOpenMinute"] - 600) <= 35
    assert abs(winter["shadeCloseMinute"] - 840) <= 35


def test_missing_mode_state_is_only_used_as_marked_protocol_fallback():
    closed_only = [
        replace(row, indoor_shade_closed=1.0)
        for row in confirmed_winter_samples()
    ]
    model = fit_behavior(closed_only)
    vocabulary = {item.mode: item for item in model.seasonal_vocabulary}["winter"]
    schedule = baseline_schedule(model, winter_forecast(sunny=True))

    assert dict(vocabulary.action_states)["indoor_shade"] == ("closed",)
    assert schedule["indoorShadeDay"] == "open"
    assert schedule["shadeTimingSource"] == "protocol_fallback"
    assert schedule["shadeTimingStatus"] == INSUFFICIENT_DATA



def test_nonwinter_shade_state_is_not_invented_without_mode_vocabulary():
    empty = BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions={transition: () for transition in behavior.TRANSITIONS},
        seasonal_vocabulary=(),
    )
    forecast = [
        replace(row, indoor_shade_closed=0.0)
        for row in warm_forecast()
    ]
    schedule = baseline_schedule(empty, forecast)

    assert schedule["indoorShadeDay"] == "open"
    assert schedule["indoorShadeSource"] == "forecast_state"



def test_sunny_winter_search_uses_learned_shade_hazards_and_improves_mass():
    forecast = winter_forecast(sunny=True)
    result = search_candidate_schedule(
        behavior=winter_behavior(),
        dynamics=stable_model(),
        forecast=forecast,
    )

    assert result.candidate is not None
    assert result.candidate["vent"] == "closed"
    assert result.candidate["indoorShadeNight"] == "closed"
    assert (
        result.candidate["shadeOpenMinute"]
        < result.baseline["shadeOpenMinute"]
        or result.candidate["shadeCloseMinute"]
        > result.baseline["shadeCloseMinute"]
    )
    assert result.modeled_difference["scoreImprovement"] >= 0.25


def test_cold_cloudy_winter_rejects_open_shade_candidates():
    result = search_candidate_schedule(
        behavior=winter_behavior(),
        dynamics=stable_model(),
        forecast=winter_forecast(sunny=False),
    )

    assert result.baseline["indoorShadeDay"] == "closed"
    assert result.baseline["indoorShadeNight"] == "closed"
    assert result.candidate is None
    assert result.modeled_difference["selectionReason"] == "protocol_constraint"
    assert result.modeled_difference["scoreImprovement"] == 0.0
    assert result.rejected_candidate_counts["cold_cloudy_protocol"] > 0


def test_minimum_improvement_retains_baseline_without_candidate():
    dynamics = stable_model()
    dynamics.air_coefficients["vent_exchange"] = 0.0

    result = search_candidate_schedule(
        behavior=warm_behavior(),
        dynamics=dynamics,
        forecast=warm_forecast(),
    )

    assert result.modeled_difference["selectionReason"] == "minimum_improvement_not_met"
    assert result.modeled_difference["scoreImprovement"] == 0.0
    assert result.candidate is None


def test_always_hot_forecast_reports_no_valid_candidate_not_unsafe_baseline():
    forecast = [
        replace(row, outdoor_f=90.0, air_baseline_f=75.0)
        for row in warm_forecast()
    ]
    result = search_candidate_schedule(
        behavior=warm_behavior(),
        dynamics=stable_model(),
        forecast=forecast,
    )

    assert result.baseline["vent"] == "open"
    assert result.candidate is None
    assert result.vent_open_at is None
    assert result.modeled_difference["scoreImprovement"] == 0.0
    assert result.modeled_difference["selectionReason"] == "no_valid_candidate"
    assert sum(result.rejected_candidate_counts.values()) > 0


def test_observed_boosted_segments_are_simulated_at_two_and_change_temperature():
    forecast = warm_forecast()
    model = fit_behavior(warm_samples_with_boosted_doors())
    schedule = baseline_schedule(model, forecast)
    boosted_segments = [
        segment
        for segment in schedule["airflowSegments"]
        if segment["level"] == "boosted"
    ]
    assert boosted_segments

    forcings = behavior._forcing_rows(forecast, schedule)
    assert max(row["vent_open"] for row in forcings) == 2.0
    assert all(0.0 <= row["vent_open"] <= 2.0 for row in forcings)

    baseline_only = dict(schedule)
    baseline_only["airflowSegments"] = tuple(
        segment
        for segment in schedule["airflowSegments"]
        if segment["level"] != "boosted"
    )
    boosted_trace = behavior._simulation(stable_model(), forecast, schedule)
    baseline_trace = behavior._simulation(stable_model(), forecast, baseline_only)
    assert [row["air_f"] for row in boosted_trace] != [
        row["air_f"] for row in baseline_trace
    ]


def test_boosted_segments_are_not_invented_without_observed_evidence():
    schedule = baseline_schedule(warm_behavior(), warm_forecast())
    assert {
        segment["level"] for segment in schedule["airflowSegments"]
    } == {"baseline"}



def test_feature_vector_is_finite_and_scaled_for_optimizer():
    row = confirmed_warm_samples(days=1)[100]
    values = feature_vector(row)
    assert len(values) == len(FEATURE_NAMES)
    assert values[0] == 1.0
    assert all(math.isfinite(value) for value in values)
    assert abs(values[7]) <= 1.6
