import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from thermal_model.dataset import build_samples, dataset_manifest
from thermal_model.actions import reconstruct_events, reconstruct_state
from thermal_model.schema import ActionEvent, ModeEvent, THERMAL_ITEMS


UTC = timezone.utc
START = datetime(2026, 8, 13, tzinfo=UTC)
END = START + timedelta(hours=2)
HOUR = timedelta(hours=1)


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


def fully_labeled_events(at=START):
    return [
        action("vent-open", "vent", "open", at),
        action("shade-open", "indoor_shade", "open", at),
        action("outside-installed", "outdoor_shade", "installed", at),
        action("kiva-off", "kiva", "off", at),
    ]


def test_five_minute_alignment_does_not_bridge_large_gaps():
    samples = build_samples(
        series_by_role=fixture_series(gap_minutes=35),
        events=fully_labeled_events(),
        modes=[],
        start=START,
        end=END,
    )
    assert all(sample.at.minute % 5 == 0 and sample.at.second == 0 for sample in samples)
    gap_start = START + timedelta(minutes=30)
    gap_end = START + timedelta(minutes=60)
    assert not any(gap_start <= sample.at <= gap_end for sample in samples)


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
        ("missing", 2, "missing"),
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
            if not 6 <= step <= 11
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
    assert manifest["items"] == THERMAL_ITEMS
    assert manifest["event_counts_by_source"] == {"manual_dm": 5}
    assert len(manifest["canonical_rows_sha256"]) == 64
    assert manifest["canonical_rows_sha256"] == repeated["canonical_rows_sha256"]
    json.dumps(manifest, allow_nan=False)
