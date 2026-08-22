import json
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import thermal_model.dataset as dataset_module
from thermal_model.dataset import (
    MASS_OBSERVER_TAU_MINUTES,
    ThermalDataset,
    build_samples,
    dataset_manifest,
    latent_mass_from_series,
)
from thermal_model.actions import reconstruct_events, reconstruct_state
from thermal_model.solar import is_astronomical_night, solar_elevation_sin
from thermal_model.schema import (
    ActionEvent,
    ModeEvent,
    OPTIONAL_OBSERVATION_ITEMS,
    THERMAL_ITEMS,
)


UTC = timezone.utc
START = datetime(2026, 8, 13, tzinfo=UTC)
END = START + timedelta(hours=2)
HOUR = timedelta(hours=1)
NIGHT_START = datetime(2026, 8, 13, 6, 0, tzinfo=UTC)
DAY_START = datetime(2026, 8, 13, 18, 0, tzinfo=UTC)
EXPECTED_RADIATION_PROVENANCE_LABELS = (
    "observed",
    "interpolated",
    "held",
    "astronomical_night_zero",
)
EVERY_CHANGE_START = datetime(2026, 1, 1, tzinfo=ZoneInfo("America/Denver"))
EVERY_CHANGE_END = EVERY_CHANGE_START + timedelta(days=45)


def five_minute_range(start, end):
    cursor = start
    while cursor < end:
        yield cursor
        cursor += timedelta(minutes=5)


def synthetic_radiation(at):
    return 0.0 if is_astronomical_night(at) else 800.0 * solar_elevation_sin(at)


def every_change_radiation(start, end):
    rows = []
    previous = None
    for at in five_minute_range(start, end):
        value = synthetic_radiation(at)
        if value != previous:
            rows.append((at, value))
            previous = value
    return rows


def action(
    event_id,
    action_name,
    state,
    at,
    source="manual_dm",
    confidence=1.0,
    *,
    note="",
    interval_id=None,
):
    return ActionEvent(
        event_id=event_id,
        idempotency_key=f"receipt-{event_id}",
        received_at=at,
        effective_at=at,
        action=action_name,
        state=state,
        source=source,
        confidence=confidence,
        interval_id=interval_id,
        note=note,
    )


def mode_event(
    mode,
    at,
    *,
    event_id=None,
    source="manual_dm",
    confidence=1.0,
    supersedes=None,
):
    event_id = event_id or f"mode-{mode}-{at.timestamp()}"
    return ModeEvent(
        event_id=event_id,
        idempotency_key=f"receipt-{event_id}",
        received_at=at,
        effective_at=at,
        mode=mode,
        source=source,
        confidence=confidence,
        supersedes=supersedes,
    )


def fixture_series(*, gap_minutes=0, glazing=True):
    rows = {role: [] for role in THERMAL_ITEMS}
    for step in range(24):
        at = START + timedelta(minutes=5 * step, seconds=30 if step % 2 else 0)
        if gap_minutes and 30 <= step * 5 < 30 + gap_minutes:
            continue
        values = {
            "air": 74 + 0.1 * step,
            "mass": 72 + 0.02 * step,
            "glazing": 76 + 0.1 * step,
            "outdoor": 68 + 0.05 * step,
            "radiation": max(0, 700 * math.sin(math.pi * step / 24)),
        }
        for role, value in values.items():
            if role != "glazing" or glazing:
                rows[role].append((at, value))
    return rows


def constant_series(start, end):
    rows = {role: [] for role in THERMAL_ITEMS}
    cursor = start
    while cursor < end:
        for role, value in {
            "air": 72.0,
            "mass": 70.0,
            "glazing": 73.0,
            "outdoor": 60.0,
            "radiation": 0.0,
        }.items():
            rows[role].append((cursor, value))
        cursor += timedelta(minutes=5)
    return rows


def every_change_history(start=EVERY_CHANGE_START, end=EVERY_CHANGE_END):
    rows = {role: [] for role in THERMAL_ITEMS}
    for at in five_minute_range(start, end):
        solar = max(0.0, solar_elevation_sin(at))
        phase = 2.0 * math.pi * (at.hour * 60 + at.minute) / 1440.0
        values = {
            "air": 68.0 + 3.0 * math.sin(phase - math.pi / 3.0),
            "mass": 66.0 + 1.5 * math.sin(phase - math.pi / 2.0),
            "glazing": 67.0 + 5.0 * solar,
            "outdoor": 46.0 + 24.0 * solar,
        }
        for role, value in values.items():
            rows[role].append((at, value))
    rows["radiation"] = every_change_radiation(start, end)
    actions = [
        action("every-change-vent", "vent", "closed", start),
        action("every-change-indoor", "indoor_shade", "open", start),
        action("every-change-outdoor", "outdoor_shade", "absent", start),
    ]
    modes = [
        mode_event("winter", start, event_id="every-change-winter"),
        mode_event(
            "warm", start + timedelta(days=30), event_id="every-change-warm"
        ),
    ]
    return rows, actions, modes


def fully_labeled_events(at=START):
    return [
        action("vent-open", "vent", "open", at),
        action("shade-open", "indoor_shade", "open", at),
        action("outside-installed", "outdoor_shade", "installed", at),
        action("kiva-off", "kiva", "off", at),
    ]


def test_dataset_retains_only_actual_confirmed_action_event_rows():
    events = [
        action(
            "exact", "vent", "closed", START + timedelta(minutes=5),
            "manual_dm", 1.0,
        ),
        action(
            "confirmed", "vent", "open", START + timedelta(minutes=7),
            "manual_dm", 1.0,
        ),
        action(
            "photo", "indoor_shade", "closed", START + timedelta(minutes=15),
            "photosensor", 0.8,
        ),
        action(
            "after-final", "vent", "closed", END + timedelta(minutes=1),
            "manual_dm", 1.0,
        ),
    ]

    samples = build_samples(fixture_series(), events, [], START, END)

    assert samples.confirmed_action_rows == (
        START + timedelta(minutes=5),
        START + timedelta(minutes=10),
    )


def test_five_minute_alignment_does_not_bridge_large_gaps():
    samples = build_samples(
        series_by_role=fixture_series(gap_minutes=65),
        events=fully_labeled_events(),
        modes=[],
        start=START,
        end=END,
    )
    assert all(sample.at.minute % 5 == 0 and sample.at.second == 0 for sample in samples)
    gap_start = START + timedelta(minutes=30)
    gap_end = START + timedelta(minutes=90)
    assert not any(gap_start <= sample.at <= gap_end for sample in samples)


def test_five_minute_alignment_interpolates_only_finite_short_gaps():
    rows = fixture_series()
    expected_at = START + timedelta(minutes=5)
    for role in ("air", "mass", "outdoor", "radiation"):
        rows[role].pop(1)

    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    interpolated = next(sample for sample in samples if sample.at == expected_at)
    manifest = dataset_manifest(samples, fully_labeled_events(), [])

    assert interpolated.air_f == pytest.approx(74.1)
    assert interpolated.north_wall_f == pytest.approx(72.02)
    assert manifest["interpolation_counts"] == {
        "air": 1,
        "glazing": 0,
        "living_office": 0,
        "mass": 1,
        "outdoor": 1,
        "radiation": 1,
    }


def test_short_gap_alignment_never_replaces_explicit_nonfinite_value():
    rows = fixture_series()
    target_at, _ = rows["mass"][1]
    rows["mass"][1] = (target_at, math.nan)

    samples = build_samples(rows, fully_labeled_events(), [], START, END)

    assert not any(sample.at == START + timedelta(minutes=5) for sample in samples)


def test_every_change_alignment_holds_state_after_twenty_up_to_sixty_minutes():
    rows = fixture_series()
    for role in ("air", "mass", "outdoor", "radiation"):
        rows[role] = [rows[role][0], *rows[role][6:]]

    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    manifest = dataset_manifest(samples, fully_labeled_events(), [])

    held = next(sample for sample in samples if sample.at == START + timedelta(minutes=25))
    assert held.air_f == pytest.approx(74.0)
    assert held.north_wall_f == pytest.approx(72.0)
    assert manifest["hold_forward_counts"]["air"] == 5
    assert manifest["hold_forward_counts"]["mass"] == 5


def test_every_change_alignment_refuses_gaps_over_sixty_minutes():
    rows = fixture_series()
    for role in ("air", "mass", "outdoor", "radiation"):
        rows[role] = [rows[role][0], *rows[role][13:]]

    samples = build_samples(rows, fully_labeled_events(), [], START, END)

    assert not any(
        START < sample.at < START + timedelta(minutes=65)
        for sample in samples
    )


def test_astronomical_night_reconstruction_preserves_ordinary_precedence():
    end = NIGHT_START + timedelta(hours=2)
    rows = constant_series(NIGHT_START, end)
    rows["radiation"] = [
        (NIGHT_START, 11.0),
        (NIGHT_START + timedelta(minutes=10), 13.0),
        (NIGHT_START + timedelta(minutes=40), 17.0),
    ]

    dataset = build_samples(
        rows, fully_labeled_events(NIGHT_START), [], NIGHT_START, end
    )
    by_at = {sample.at: sample for sample in dataset}

    assert by_at[NIGHT_START].radiation_wm2 == 11.0
    assert dataset.radiation_provenance_by_at[NIGHT_START] == "observed"
    assert by_at[NIGHT_START + timedelta(minutes=5)].radiation_wm2 == 12.0
    assert (
        dataset.radiation_provenance_by_at[
            NIGHT_START + timedelta(minutes=5)
        ]
        == "interpolated"
    )
    assert by_at[NIGHT_START + timedelta(minutes=35)].radiation_wm2 == 13.0
    assert (
        dataset.radiation_provenance_by_at[
            NIGHT_START + timedelta(minutes=35)
        ]
        == "held"
    )
    reconstructed_at = NIGHT_START + timedelta(minutes=105)
    assert by_at[reconstructed_at].radiation_wm2 == 0.0
    assert (
        dataset.radiation_provenance_by_at[reconstructed_at]
        == "astronomical_night_zero"
    )


def test_night_reconstruction_never_fills_day_nonfinite_or_temperature_gaps():
    night_end = NIGHT_START + timedelta(hours=2)
    rows = constant_series(NIGHT_START, night_end)
    rows["radiation"] = [
        (NIGHT_START + timedelta(minutes=15), math.nan),
    ]
    rows["air"][6] = (NIGHT_START + timedelta(minutes=30), math.nan)

    night = build_samples(
        rows, fully_labeled_events(NIGHT_START), [], NIGHT_START, night_end
    )
    accepted = {sample.at for sample in night}

    assert NIGHT_START in accepted
    assert NIGHT_START + timedelta(minutes=15) not in accepted
    assert NIGHT_START + timedelta(minutes=30) not in accepted

    day_end = DAY_START + timedelta(hours=2)
    day_rows = constant_series(DAY_START, day_end)
    day_rows["radiation"] = []
    daylight_gap_dataset = build_samples(
        day_rows, fully_labeled_events(DAY_START), [], DAY_START, day_end
    )
    assert DAY_START not in {sample.at for sample in daylight_gap_dataset}
    assert daylight_gap_dataset == []


def test_every_change_radiation_history_recovers_continuous_nights():
    rows, actions, modes = every_change_history()
    dataset = build_samples(
        rows, actions, modes, EVERY_CHANGE_START, EVERY_CHANGE_END
    )
    radiation_rows = rows["radiation"]

    assert len(radiation_rows) < len(rows["air"])
    assert all(
        value == 0.0
        for at, value in radiation_rows
        if is_astronomical_night(at)
    )
    assert all(
        not is_astronomical_night(next_at)
        for (_, value), (next_at, _) in zip(radiation_rows, radiation_rows[1:])
        if value == 0.0
    )
    assert len(dataset) == 45 * 24 * 12
    assert set(sample.mode for sample in dataset) == {"winter", "warm"}
    assert sum(
        provenance == "astronomical_night_zero"
        for provenance in dataset.radiation_provenance_by_at.values()
    ) > 45 * 12


def test_every_change_history_keeps_daylight_and_mass_gaps_rejected():
    def gap_start():
        return next(
            at
            for at in five_minute_range(EVERY_CHANGE_START, EVERY_CHANGE_END)
            if all(
                not is_astronomical_night(candidate)
                for candidate in five_minute_range(
                    at, at + timedelta(minutes=75)
                )
            )
        )

    missing_start = gap_start()
    expected_gap = missing_start + timedelta(minutes=65)

    for role in ("radiation", "mass"):
        rows, actions, modes = every_change_history()
        rows[role] = [
            point
            for point in rows[role]
            if not missing_start <= point[0] < missing_start + timedelta(minutes=70)
        ]
        dataset = build_samples(
            rows, actions, modes, EVERY_CHANGE_START, EVERY_CHANGE_END
        )

        assert expected_gap not in {sample.at for sample in dataset}
        assert dataset.rejected_counts["source_gap"] > 0


def test_manifest_partitions_radiation_provenance_and_binds_it_to_digest():
    end = NIGHT_START + timedelta(hours=2)
    rows = constant_series(NIGHT_START, end)
    rows["radiation"] = [
        (NIGHT_START, 1.0),
        (NIGHT_START + timedelta(minutes=10), 3.0),
        (NIGHT_START + timedelta(minutes=40), 5.0),
    ]
    events = fully_labeled_events(NIGHT_START)
    dataset = build_samples(rows, events, [], NIGHT_START, end)

    manifest = dataset_manifest(dataset, events, [])

    assert tuple(manifest.get("radiation_provenance_counts", ())) == (
        EXPECTED_RADIATION_PROVENANCE_LABELS
    )
    assert sum(manifest["radiation_provenance_counts"].values()) == len(dataset)
    assert manifest["radiation_provenance_counts"]["observed"] == 3
    assert manifest["radiation_provenance_counts"]["interpolated"] == 1
    assert manifest["radiation_provenance_counts"]["held"] == 17
    assert (
        manifest["radiation_provenance_counts"]["astronomical_night_zero"]
        == len(dataset) - 21
    )
    assert hasattr(dataset_module, "radiation_reconstruction_contract")
    assert dataset_module.radiation_reconstruction_contract() == {
        "rule": "missing_at_solar_elevation_lte_zero_becomes_zero",
        "night_value_wm2": 0.0,
        "solar": {
            "rule": "earthship-solar-elevation/v1",
            "latitude": 38.3739919,
            "longitude": -105.7744609,
            "night_when_elevation_sin_lte": 0.0,
        },
        "provenance_labels": list(EXPECTED_RADIATION_PROVENANCE_LABELS),
    }

    changed_provenance = dict(dataset.radiation_provenance_by_at)
    changed_provenance[dataset[0].at] = "held"
    mutation = ThermalDataset(
        dataset,
        start=dataset.start,
        end=dataset.end,
        rejected_counts=dataset.rejected_counts,
        auxiliary_exclusion_counts=dataset.auxiliary_exclusion_counts,
        confirmed_action_rows=dataset.confirmed_action_rows,
        interpolation_counts=dataset.interpolation_counts,
        hold_forward_counts=dataset.hold_forward_counts,
        radiation_provenance_by_at=changed_provenance,
    )
    mutated_manifest = dataset_manifest(mutation, events, [])
    assert (
        mutated_manifest["canonical_rows_sha256"]
        != manifest["canonical_rows_sha256"]
    )


def test_latent_mass_observer_is_causal_and_preserves_north_wall_observation():
    rows = fixture_series()
    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    alpha = 1.0 - math.exp(-5.0 / MASS_OBSERVER_TAU_MINUTES)

    assert MASS_OBSERVER_TAU_MINUTES == 120
    assert samples[0].north_wall_f == pytest.approx(72.0)
    assert samples[0].mass_f == pytest.approx(72.0)
    assert samples[1].north_wall_f == pytest.approx(72.02)
    assert samples[1].mass_f == pytest.approx(72.0 + alpha * 0.02)

    changed_future = fixture_series()
    changed_future["mass"][-1] = (changed_future["mass"][-1][0], 75.0)
    changed = build_samples(
        changed_future, fully_labeled_events(), [], START, END
    )
    assert [sample.mass_f for sample in changed[:-1]] == pytest.approx(
        [sample.mass_f for sample in samples[:-1]]
    )


def test_live_latent_mass_uses_the_same_causal_observer():
    alpha = 1.0 - math.exp(-5.0 / MASS_OBSERVER_TAU_MINUTES)
    points = (
        (START, 68.0),
        (START + timedelta(minutes=5), 72.0),
    )

    at, value = latent_mass_from_series(points)

    assert at == START + timedelta(minutes=5)
    assert value == pytest.approx(68.0 + alpha * 4.0)


def test_living_office_temperature_is_optional_secondary_observation():
    rows = fixture_series()
    rows["living_office"] = [
        (START, 73.5),
        (START + timedelta(minutes=5), 73.7),
    ]

    samples = build_samples(rows, fully_labeled_events(), [], START, END)

    assert samples[0].air_f == pytest.approx(74.0)
    assert samples[0].living_office_f == pytest.approx(73.5)
    assert samples[2].living_office_f == pytest.approx(73.7)
    assert samples[14].living_office_f is None


def test_bucket_uses_median_finite_value_and_glazing_is_optional():
    rows = fixture_series(glazing=False)
    rows["air"].extend(
        [
            (START + timedelta(minutes=1), 80.0),
            (START + timedelta(minutes=2), math.nan),
            (START + timedelta(minutes=3), math.inf),
        ]
    )
    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    assert samples[0].air_f == pytest.approx(77.0)
    assert samples[0].glazing_f is None


@pytest.mark.parametrize(
    ("case", "target_step", "reason"),
    [
        ("missing", 0, "missing"),
        ("non_finite", 3, "non_finite"),
        ("range", 4, "range"),
        ("jump", 5, "jump"),
        ("source_gap", 7, "source_gap"),
    ],
)
def test_glazing_quality_failure_retains_core_sample_and_reports_exclusion(
    case, target_step, reason
):
    rows = fixture_series()
    if case == "missing":
        rows["glazing"].pop(target_step)
    elif case == "non_finite":
        at, _ = rows["glazing"][target_step]
        rows["glazing"][target_step] = (at, math.nan)
    elif case == "range":
        at, _ = rows["glazing"][target_step]
        rows["glazing"][target_step] = (at, 150.0)
    elif case == "jump":
        at, _ = rows["glazing"][target_step]
        rows["glazing"][target_step] = (at, 100.0)
    else:
        rows["glazing"] = [
            point
            for step, point in enumerate(rows["glazing"])
            if not 6 <= step <= 18
        ]

    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    target_at = START + timedelta(minutes=5 * target_step)
    target = next(sample for sample in samples if sample.at == target_at)
    manifest = dataset_manifest(samples, fully_labeled_events(), [])

    assert target.glazing_f is None
    assert len(samples) == 24
    assert manifest["auxiliary_exclusion_counts"][f"glazing_{reason}"] >= 1


def test_range_jump_and_missing_required_inputs_are_rejected_and_counted():
    rows = fixture_series()
    rows["mass"] = [(at, value) for at, value in rows["mass"] if at >= START + timedelta(minutes=5)]
    rows["radiation"][2] = (rows["radiation"][2][0], 1700.0)
    rows["air"][3] = (rows["air"][3][0], 100.0)

    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    manifest = dataset_manifest(samples, fully_labeled_events(), [])

    assert not any(sample.at in {START, START + timedelta(minutes=10), START + timedelta(minutes=15)} for sample in samples)
    assert manifest["rejected_counts"]["missing_required"] >= 1
    assert manifest["rejected_counts"]["range"] >= 1
    assert manifest["rejected_counts"]["jump"] >= 1


def test_reconstruct_state_matches_seasonal_policy():
    assert reconstruct_state(
        "winter", is_daylight=True, sunny=True, cold_cloudy=False
    ) == {"vent_open": 0.0, "indoor_shade_closed": 0.0}
    assert reconstruct_state(
        "winter", is_daylight=True, sunny=False, cold_cloudy=True
    ) == {"vent_open": 0.0, "indoor_shade_closed": 1.0}
    assert reconstruct_state(
        "winter", is_daylight=False, sunny=False, cold_cloudy=False
    ) == {"vent_open": 0.0, "indoor_shade_closed": 1.0}
    assert reconstruct_state(
        "fall_charge", is_daylight=False, sunny=False, cold_cloudy=False
    ) == {"vent_open": 1.0, "indoor_shade_closed": None}
    assert reconstruct_state(
        "warm", is_daylight=False, sunny=False, cold_cloudy=False
    ) == {"vent_open": 1.0, "indoor_shade_closed": 0.0}


def test_reconstruction_has_no_calendar_guess_before_first_effective_mode():
    first_mode = START + timedelta(minutes=30)
    intervals = reconstruct_events(START, END, [mode_event("warm", first_mode)])

    assert len(intervals) == 1
    assert intervals[0].start == first_mode
    assert intervals[0].end == END
    assert intervals[0].regime == "warm"
    assert (intervals[0].source, intervals[0].confidence) == (
        "historical_reconstruction",
        0.35,
    )
    assert (intervals[0].mode_source, intervals[0].mode_confidence) == (
        "manual_dm",
        1.0,
    )

    samples = build_samples(fixture_series(), [], [mode_event("warm", first_mode)], START, END)
    before = next(sample for sample in samples if sample.at == START)
    after = next(sample for sample in samples if sample.at == first_mode)
    assert before.vent_open is None
    assert before.indoor_shade_closed is None
    assert before.action_confidence == 0.0
    assert after.vent_open is not None
    assert after.indoor_shade_closed is not None
    assert after.action_confidence == 0.35


def test_mode_correction_gap_stays_unknown_until_corrected_effective_time():
    original = mode_event("warm", START, event_id="mode-original")
    correction = mode_event(
        "winter",
        START + timedelta(minutes=30),
        event_id="mode-correction",
        supersedes=original.event_id,
    )
    intervals = reconstruct_events(START, END, [original, correction])
    assert [(item.start, item.end, item.regime) for item in intervals] == [
        (START + timedelta(minutes=30), END, "winter")
    ]


def test_confirmed_actions_override_same_time_reconstruction():
    events = [
        action(
            "reconstructed-vent",
            "vent",
            "open",
            START,
            "historical_reconstruction",
            0.35,
        ),
        action("confirmed-vent", "vent", "closed", START, "manual_dm", 1.0),
        action("confirmed-shade", "indoor_shade", "open", START, "manual_dm", 1.0),
        action("confirmed-outside", "outdoor_shade", "installed", START, "manual_dm", 1.0),
    ]
    samples = build_samples(fixture_series(), events, [], START, END)
    assert samples[0].vent_open == 0.0
    assert samples[0].action_confidence == 1.0


def test_confirmed_vent_keeps_own_confidence_beside_reconstructed_shade():
    sample = build_samples(
        fixture_series(),
        [action("confirmed-vent", "vent", "closed", START)],
        [mode_event("warm", START)],
        START,
        END,
    )[0]
    assert sample.vent_open == 0.0
    assert sample.vent_confidence == 1.0
    assert sample.indoor_shade_confidence == 0.35
    assert sample.outdoor_shade_confidence == 0.0
    assert sample.action_confidence == 0.35


def test_action_confidence_is_minimum_of_joined_winning_states():
    events = [
        action("vent", "vent", "open", START, "manual_dm", 1.0),
        action("shade", "indoor_shade", "closed", START, "photosensor", 0.8),
        action(
            "outside",
            "outdoor_shade",
            "installed",
            START,
            "historical_reconstruction",
            0.35,
        ),
    ]
    sample = build_samples(fixture_series(), events, [], START, END)[0]
    assert sample.action_confidence == 0.35


def test_unknown_action_state_remains_none_with_zero_confidence():
    sample = build_samples(fixture_series(), [], [], START, END)[0]
    assert sample.vent_open is None
    assert sample.indoor_shade_closed is None
    assert sample.outdoor_shade_present is None
    assert sample.action_confidence == 0.0


def test_explicit_unknown_transition_does_not_fall_back_to_reconstruction():
    events = [
        action("shade-known", "indoor_shade", "closed", START),
        action("shade-unknown", "indoor_shade", "unknown", START + timedelta(minutes=5)),
    ]
    samples = build_samples(
        fixture_series(), events, [mode_event("warm", START)], START, END
    )
    unknown = next(sample for sample in samples if sample.at == START + timedelta(minutes=5))
    assert unknown.indoor_shade_closed is None
    assert unknown.indoor_shade_confidence == 0.0
    assert unknown.vent_open is not None
    assert unknown.vent_confidence == 0.35
    assert unknown.action_confidence == 0.35


def test_winter_samples_never_vent_and_follow_sunny_cold_cloudy_night_shades():
    times = (
        datetime(2026, 1, 15, 19, tzinfo=UTC),
        datetime(2026, 1, 15, 20, tzinfo=UTC),
        datetime(2026, 1, 16, 6, tzinfo=UTC),
    )
    radiation = (500.0, 50.0, 0.0)
    outdoor = (45.0, 30.0, 45.0)
    rows = {
        "air": [(at, 70.0) for at in times],
        "mass": [(at, 68.0) for at in times],
        "glazing": [],
        "outdoor": list(zip(times, outdoor)),
        "radiation": list(zip(times, radiation)),
    }
    samples = build_samples(
        rows,
        [],
        [mode_event("winter", times[0])],
        times[0],
        times[-1] + timedelta(minutes=5),
    )
    by_at = {sample.at: sample for sample in samples}
    assert [by_at[at].vent_open for at in times] == [0.0, 0.0, 0.0]
    assert [by_at[at].indoor_shade_closed for at in times] == [0.0, 1.0, 1.0]


def test_kiva_and_unknown_exceptional_heat_exclude_passive_fit():
    events = fully_labeled_events() + [
        action("kiva-on", "kiva", "on", START + HOUR),
        action("kiva-stop", "kiva", "off", START + HOUR + timedelta(minutes=10)),
        action(
            "unknown-heat",
            "kiva",
            "exceptional_heat_unknown",
            START + timedelta(minutes=20),
            note="exceptional_heat_unknown",
        ),
        action("unknown-heat-end", "kiva", "off", START + timedelta(minutes=30)),
    ]
    samples = build_samples(fixture_series(), events, [], START, END)
    by_at = {sample.at: sample for sample in samples}
    assert by_at[START + timedelta(minutes=20)].passive_fit_allowed is False
    assert by_at[START + HOUR].passive_fit_allowed is False
    assert by_at[START + HOUR + timedelta(minutes=55)].passive_fit_allowed is False


def test_unconfirmed_kiva_stop_does_not_create_cooldown():
    events = fully_labeled_events() + [
        action("kiva-on", "kiva", "on", START + timedelta(minutes=5)),
        action(
            "kiva-inferred-stop",
            "kiva",
            "off",
            START + timedelta(minutes=10),
            "model_inferred",
            0.15,
        ),
    ]
    by_at = {
        sample.at: sample
        for sample in build_samples(fixture_series(), events, [], START, END)
    }
    assert by_at[START + timedelta(minutes=10)].passive_fit_allowed is True


def test_lower_precedence_colliding_kiva_on_cannot_fabricate_cooldown():
    collision = START + HOUR
    events = fully_labeled_events() + [
        action(
            "inferred-kiva-on",
            "kiva",
            "on",
            collision,
            "model_inferred",
            0.15,
        ),
        action("confirmed-kiva-off", "kiva", "off", collision),
    ]
    by_at = {
        sample.at: sample
        for sample in build_samples(fixture_series(), events, [], START, END)
    }
    assert by_at[collision].passive_fit_allowed is True
    assert by_at[collision + timedelta(minutes=30)].passive_fit_allowed is True


def test_timestamps_are_normalized_to_aware_utc_without_future_rows():
    offset = timezone(timedelta(hours=-6))
    local_start = START.astimezone(offset)
    rows = {
        role: [(at.astimezone(offset), value) for at, value in values]
        for role, values in fixture_series().items()
    }
    samples = build_samples(
        rows,
        fully_labeled_events(local_start),
        [],
        local_start,
        END.astimezone(offset),
    )
    assert samples[0].at == START
    assert samples[0].at.tzinfo == UTC
    assert all(START <= sample.at < END for sample in samples)



def test_samples_preserve_reconstructed_mode_for_behavior_vocabulary():
    samples = build_samples(
        fixture_series(),
        fully_labeled_events(),
        [mode_event("warm", START)],
        START,
        END,
    )
    assert samples
    assert {sample.mode for sample in samples} == {"warm"}



def test_naive_boundaries_or_points_are_rejected():
    with pytest.raises(ValueError, match="start.*timezone"):
        build_samples(fixture_series(), [], [], START.replace(tzinfo=None), END)
    rows = fixture_series()
    rows["air"][0] = (START.replace(tzinfo=None), rows["air"][0][1])
    with pytest.raises(ValueError, match="series.*timezone"):
        build_samples(rows, [], [], START, END)


def test_manifest_is_canonical_reproducible_and_identifies_authoritative_items():
    events = fully_labeled_events()
    modes = [mode_event("warm", START)]
    samples = build_samples(fixture_series(), events, modes, START, END)
    manifest = dataset_manifest(samples, events, modes)
    repeated = dataset_manifest(list(reversed(samples)), list(reversed(events)), modes)

    assert manifest["start"] == "2026-08-13T00:00:00Z"
    assert manifest["end"] == "2026-08-13T02:00:00Z"
    assert manifest["sample_count"] == len(samples)
    assert manifest["items"] == {**THERMAL_ITEMS, **OPTIONAL_OBSERVATION_ITEMS}
    assert manifest["event_counts_by_source"] == {"manual_dm": 5}
    assert len(manifest["canonical_rows_sha256"]) == 64
    assert manifest["canonical_rows_sha256"] == repeated["canonical_rows_sha256"]
    json.dumps(manifest, allow_nan=False)


def test_manifest_reports_exact_closed_sample_counts_by_mode():
    events = fully_labeled_events()
    samples = build_samples(fixture_series(), events, [], START, END)
    modes = (None, "fall_charge", "winter", "spring", "warm")
    samples = [
        replace(sample, mode=modes[index % len(modes)])
        for index, sample in enumerate(samples)
    ]

    manifest = dataset_manifest(samples, events, [])

    expected = {name: 0 for name in modes if name is not None}
    expected["unknown"] = 0
    for sample in samples:
        expected[sample.mode or "unknown"] += 1
    assert manifest["sample_counts_by_mode"] == {
        "unknown": expected["unknown"],
        "fall_charge": expected["fall_charge"],
        "winter": expected["winter"],
        "spring": expected["spring"],
        "warm": expected["warm"],
    }
    assert sum(manifest["sample_counts_by_mode"].values()) == len(samples)
