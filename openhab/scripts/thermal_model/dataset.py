"""Pure, read-only construction of reproducible five-minute thermal samples."""

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from statistics import median

from .actions import reconstruct_events, reconstruct_state
from .schema import (
    ActionEvent,
    ModeEvent,
    OPTIONAL_OBSERVATION_ITEMS,
    SOURCE_WEIGHTS,
    THERMAL_ITEMS,
    ThermalSample,
)


STEP = timedelta(minutes=5)
MAX_INTERPOLATION_GAP = timedelta(minutes=20)
MAX_HOLD_FORWARD_GAP = timedelta(minutes=60)
MASS_OBSERVER_TAU_MINUTES = 120
REQUIRED_ROLES = ("air", "mass", "outdoor", "radiation")
TEMPERATURE_ROLES = ("air", "mass", "glazing", "outdoor")
CONFIRMED_SOURCES = frozenset(("nostr_confirmed", "manual_dm"))
CORE_REJECTED_COUNT_KEYS = frozenset(
    {"missing_required", "source_gap", "range", "jump"}
)
AUXILIARY_EXCLUSION_COUNT_KEYS = frozenset(
    {
        "glazing_range",
        "glazing_jump",
        "glazing_source_gap",
        "glazing_non_finite",
        "glazing_missing",
        "living_office_range",
        "living_office_jump",
        "living_office_source_gap",
        "living_office_non_finite",
        "living_office_missing",
    }
)
SITE_LATITUDE = 38.3739919
SITE_LONGITUDE = -105.7744609


class ThermalDataset(list):
    """A list carrying the quality-gate evidence needed by its manifest."""

    def __init__(
        self, values, *, start, end, rejected_counts, auxiliary_exclusion_counts,
        confirmed_action_rows=(), interpolation_counts=None,
        hold_forward_counts=None,
    ):
        super().__init__(values)
        self.start = start
        self.end = end
        self.rejected_counts = dict(rejected_counts)
        self.auxiliary_exclusion_counts = dict(auxiliary_exclusion_counts)
        self.confirmed_action_rows = tuple(confirmed_action_rows)
        self.interpolation_counts = dict(interpolation_counts or {})
        self.hold_forward_counts = dict(hold_forward_counts or {})


def _utc(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return value.astimezone(timezone.utc)


def _floor_five(value):
    value = value.astimezone(timezone.utc)
    return value.replace(minute=(value.minute // 5) * 5, second=0, microsecond=0)


def _ceil_five(value):
    value = _utc(value, "action effective_at")
    aligned = _floor_five(value)
    return aligned if aligned == value else aligned + STEP


def _iso_utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _bucket_series(series_by_role, start, end):
    buckets = {}
    non_finite_only = {}
    roles = tuple(THERMAL_ITEMS) + tuple(OPTIONAL_OBSERVATION_ITEMS)
    interpolation_counts = {role: 0 for role in roles}
    hold_forward_counts = {role: 0 for role in roles}
    observed_buckets = {}
    for role in roles:
        grouped = defaultdict(list)
        non_finite = set()
        for point in series_by_role.get(role, ()):
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise TypeError(f"series {role} points must be (timestamp, value) pairs")
            at, raw_value = point
            at = _utc(at, f"series {role} timestamp")
            if not start <= at < end:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            bucket = _floor_five(at)
            if math.isfinite(value):
                grouped[bucket].append(value)
            else:
                non_finite.add(bucket)
        buckets[role] = {
            at: float(median(values)) for at, values in grouped.items() if values
        }
        observed_buckets[role] = dict(buckets[role])
        non_finite_only[role] = non_finite - set(buckets[role])
        original = sorted(buckets[role].items())
        for (left_at, left_value), (right_at, right_value) in zip(
            original, original[1:]
        ):
            gap = right_at - left_at
            if gap <= STEP or gap > MAX_HOLD_FORWARD_GAP:
                continue
            if any(left_at < at < right_at for at in non_finite_only[role]):
                continue
            valid = (
                0.0 <= left_value <= 1600.0
                and 0.0 <= right_value <= 1600.0
                if role == "radiation"
                else -40.0 <= left_value <= 140.0
                and -40.0 <= right_value <= 140.0
            )
            if not valid:
                continue
            steps = int(gap / STEP)
            for index in range(1, steps):
                at = left_at + STEP * index
                if at in non_finite_only[role]:
                    continue
                if gap <= MAX_INTERPOLATION_GAP:
                    fraction = index / steps
                    buckets[role][at] = float(
                        left_value + fraction * (right_value - left_value)
                    )
                    interpolation_counts[role] += 1
                else:
                    buckets[role][at] = float(left_value)
                    hold_forward_counts[role] += 1
        if original:
            last_at, last_value = original[-1]
            cursor = last_at + STEP
            limit = min(end, last_at + MAX_HOLD_FORWARD_GAP + STEP)
            while cursor < limit:
                if cursor in non_finite_only[role]:
                    break
                buckets[role][cursor] = float(last_value)
                hold_forward_counts[role] += 1
                cursor += STEP
    return (
        buckets,
        non_finite_only,
        interpolation_counts,
        hold_forward_counts,
        observed_buckets,
    )


def _range_failures(
    buckets, temperature_roles=TEMPERATURE_ROLES, *, include_radiation=True
):
    failed = set()
    for role in temperature_roles:
        for at, value in buckets[role].items():
            if not -40.0 <= value <= 140.0:
                failed.add(at)
    if include_radiation:
        for at, value in buckets["radiation"].items():
            if not 0.0 <= value <= 1600.0:
                failed.add(at)
    return failed


def _jump_failures(buckets, roles=TEMPERATURE_ROLES):
    failed = set()
    for role in roles:
        previous = None
        for at, value in sorted(buckets[role].items()):
            if previous is not None:
                previous_at, previous_value = previous
                elapsed_steps = (at - previous_at) / STEP
                if elapsed_steps > 0 and abs(value - previous_value) > 10.0 * elapsed_steps:
                    failed.add(at)
            previous = (at, value)
    return failed


def _large_gap_buckets(
    buckets, start, end, roles=REQUIRED_ROLES,
    max_gap=MAX_HOLD_FORWARD_GAP,
):
    failed = set()
    for role in roles:
        points = sorted(buckets[role])
        for left, right in zip(points, points[1:]):
            if right - left <= max_gap:
                continue
            cursor = max(start, left + STEP)
            while cursor < min(end, right):
                failed.add(cursor)
                cursor += STEP
    return failed


def _glazing_value(
    at,
    buckets,
    non_finite,
    range_failures,
    jump_failures,
    gap_failures,
    exclusion_counts,
):
    reason = None
    if at in range_failures:
        reason = "range"
    elif at in jump_failures:
        reason = "jump"
    elif at in gap_failures:
        reason = "source_gap"
    elif at in non_finite:
        reason = "non_finite"
    elif at not in buckets:
        reason = "missing"
    if reason is not None:
        exclusion_counts[f"glazing_{reason}"] += 1
        return None
    return buckets[at]


def _optional_temperature_value(
    role, at, buckets, non_finite, range_failures, jump_failures,
    gap_failures, exclusion_counts,
):
    reason = None
    if at in range_failures:
        reason = "range"
    elif at in jump_failures:
        reason = "jump"
    elif at in gap_failures:
        reason = "source_gap"
    elif at in non_finite:
        reason = "non_finite"
    elif at not in buckets:
        reason = "missing"
    if reason is not None:
        exclusion_counts[f"{role}_{reason}"] += 1
        return None
    return buckets[at]


def _observe_latent_mass(samples):
    alpha = 1.0 - math.exp(-STEP.total_seconds() / 60.0 / MASS_OBSERVER_TAU_MINUTES)
    observed = []
    latent = None
    previous_at = None
    for sample in samples:
        north_wall = sample.mass_f
        if previous_at is None or sample.at - previous_at != STEP:
            latent = north_wall
        else:
            latent += alpha * (north_wall - latent)
        observed.append(
            replace(sample, mass_f=float(latent), north_wall_f=north_wall)
        )
        previous_at = sample.at
    return observed


def latent_mass_from_series(points):
    """Return the latest causal latent mass from raw north-wall history."""
    points = tuple(points)
    aware = [
        at
        for at, _ in points
        if isinstance(at, datetime)
        and at.tzinfo is not None
        and at.utcoffset() is not None
    ]
    if not aware:
        return None
    start = _floor_five(min(aware).astimezone(timezone.utc))
    end = _floor_five(max(aware).astimezone(timezone.utc)) + STEP
    buckets, _, _, _, _ = _bucket_series({"mass": points}, start, end)
    alpha = 1.0 - math.exp(
        -STEP.total_seconds() / 60.0 / MASS_OBSERVER_TAU_MINUTES
    )
    latent = None
    previous_at = None
    latest_at = None
    for at, north_wall in sorted(buckets["mass"].items()):
        if previous_at is None or at - previous_at != STEP:
            latent = north_wall
        else:
            latent += alpha * (north_wall - latent)
        previous_at = latest_at = at
    return None if latest_at is None else (latest_at, float(latent))


def _source_rank(source):
    return SOURCE_WEIGHTS.get(source, -1.0)


def _effective_action(events, action_name, at):
    candidates = [
        event
        for event in events
        if event.action == action_name and event.effective_at.astimezone(timezone.utc) <= at
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda event: (
            event.effective_at.astimezone(timezone.utc),
            _source_rank(event.source),
            event.received_at.astimezone(timezone.utc),
            event.event_id,
        ),
    )


def _binary_state(event, true_states, false_states):
    if event is None:
        return None
    if event.state in true_states:
        return 1.0
    if event.state in false_states:
        return 0.0
    return None


def _solar_elevation_positive(at):
    """NOAA fractional-year approximation; sufficient for a daylight sign gate."""
    at = at.astimezone(timezone.utc)
    day = at.timetuple().tm_yday
    hour = at.hour + at.minute / 60.0 + at.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (day - 1 + (hour - 12.0) / 24.0)
    equation_minutes = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    solar_minutes = hour * 60.0 + equation_minutes + 4.0 * SITE_LONGITUDE
    hour_angle = math.radians(solar_minutes / 4.0 - 180.0)
    latitude = math.radians(SITE_LATITUDE)
    cosine_zenith = (
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    return cosine_zenith > 0.0


def _regime_at(intervals, at):
    for interval in intervals:
        if interval.start <= at < interval.end:
            return interval.regime
    return None


def _confirmed_kiva_cooldowns(events):
    by_effective_at = defaultdict(list)
    for event in events:
        if event.action == "kiva":
            by_effective_at[event.effective_at.astimezone(timezone.utc)].append(event)
    kiva = [
        max(
            colliding,
            key=lambda event: (
                _source_rank(event.source),
                event.received_at.astimezone(timezone.utc),
                event.event_id,
            ),
        )
        for _, colliding in sorted(by_effective_at.items())
    ]
    cooldowns = []
    last_state = None
    for event in kiva:
        if event.state == "on":
            last_state = "on"
        elif event.state == "off":
            if event.source in CONFIRMED_SOURCES and last_state == "on":
                stop = event.effective_at.astimezone(timezone.utc)
                cooldowns.append((stop, stop + timedelta(hours=2)))
            last_state = "off"
        elif event.state == "exceptional_heat_unknown":
            last_state = "unknown"
    return cooldowns


def _project_actions(at, radiation, outdoor, events, regimes, cooldowns):
    values = {
        "vent_open": None,
        "indoor_shade_closed": None,
        "outdoor_shade_present": None,
    }
    confidences = {}
    regime = _regime_at(regimes, at)
    if regime is not None:
        daylight = _solar_elevation_positive(at)
        reconstructed = reconstruct_state(
            regime,
            is_daylight=daylight,
            sunny=daylight and radiation > 150.0,
            cold_cloudy=daylight and radiation < 100.0 and outdoor < 40.0,
        )
        for field, value in reconstructed.items():
            values[field] = value
            if value is not None:
                confidences[field] = SOURCE_WEIGHTS["historical_reconstruction"]

    projections = (
        ("vent", "vent_open", {"open"}, {"closed"}),
        ("indoor_shade", "indoor_shade_closed", {"closed"}, {"open"}),
        (
            "outdoor_shade",
            "outdoor_shade_present",
            {"installed", "present"},
            {"removed", "absent"},
        ),
    )
    for action_name, field, true_states, false_states in projections:
        event = _effective_action(events, action_name, at)
        projected = _binary_state(event, true_states, false_states)
        if projected is not None:
            values[field] = projected
            confidences[field] = event.confidence
        elif event is not None:
            values[field] = None
            confidences[field] = 0.0

    joined = [
        confidences[field]
        for field, value in values.items()
        if value is not None
    ]
    action_confidence = min(joined) if joined else 0.0

    kiva = _effective_action(events, "kiva", at)
    exceptional = kiva is not None and (
        kiva.state in {"on", "exceptional_heat_unknown"}
        or "exceptional_heat_unknown" in kiva.note
    )
    in_cooldown = any(cooldown_start <= at < cooldown_end for cooldown_start, cooldown_end in cooldowns)
    return values, confidences, action_confidence, not (exceptional or in_cooldown)


def build_samples(series_by_role, events, modes, start, end):
    """Build deterministic five-minute samples without writing either authority."""
    start_utc = _utc(start, "start")
    end_utc = _utc(end, "end")
    if end_utc <= start_utc:
        raise ValueError("end must be after start")
    events = tuple(events)
    modes = tuple(modes)
    if not all(isinstance(event, ActionEvent) for event in events):
        raise TypeError("events must contain only ActionEvent records")
    if not all(isinstance(mode, ModeEvent) for mode in modes):
        raise TypeError("modes must contain only ModeEvent records")
    for event in events:
        _utc(event.received_at, "event received_at")
        _utc(event.effective_at, "event effective_at")

    (
        buckets,
        non_finite,
        interpolation_counts,
        hold_forward_counts,
        observed_buckets,
    ) = _bucket_series(series_by_role, start_utc, end_utc)
    range_failures = _range_failures(
        buckets, ("air", "mass", "outdoor"), include_radiation=True
    )
    jump_failures = _jump_failures(
        observed_buckets, ("air", "mass", "outdoor")
    )
    gap_failures = _large_gap_buckets(
        observed_buckets, start_utc, end_utc
    )
    glazing_range_failures = _range_failures(
        buckets, ("glazing",), include_radiation=False
    )
    glazing_jump_failures = _jump_failures(observed_buckets, ("glazing",))
    glazing_gap_failures = _large_gap_buckets(
        observed_buckets, start_utc, end_utc, ("glazing",)
    )
    living_range_failures = _range_failures(
        buckets, ("living_office",), include_radiation=False
    )
    living_jump_failures = _jump_failures(
        observed_buckets, ("living_office",)
    )
    living_gap_failures = _large_gap_buckets(
        observed_buckets, start_utc, end_utc, ("living_office",)
    )
    regimes = reconstruct_events(start_utc, end_utc, modes)
    cooldowns = _confirmed_kiva_cooldowns(events)
    rejected = Counter()
    auxiliary_exclusions = Counter()
    samples = []

    cursor = _floor_five(start_utc)
    if cursor < start_utc:
        cursor += STEP
    while cursor < end_utc:
        missing = [role for role in REQUIRED_ROLES if cursor not in buckets[role]]
        if missing:
            rejected["missing_required"] += 1
            if cursor in gap_failures:
                rejected["source_gap"] += 1
            cursor += STEP
            continue
        if cursor in range_failures:
            rejected["range"] += 1
            cursor += STEP
            continue
        if cursor in jump_failures:
            rejected["jump"] += 1
            cursor += STEP
            continue

        values, confidences, confidence, passive = _project_actions(
            cursor,
            buckets["radiation"][cursor],
            buckets["outdoor"][cursor],
            events,
            regimes,
            cooldowns,
        )
        samples.append(
            ThermalSample(
                at=cursor,
                air_f=buckets["air"][cursor],
                mass_f=buckets["mass"][cursor],
                glazing_f=_glazing_value(
                    cursor,
                    buckets["glazing"],
                    non_finite["glazing"],
                    glazing_range_failures,
                    glazing_jump_failures,
                    glazing_gap_failures,
                    auxiliary_exclusions,
                ),
                outdoor_f=buckets["outdoor"][cursor],
                radiation_wm2=buckets["radiation"][cursor],
                vent_open=values["vent_open"],
                vent_confidence=confidences.get("vent_open", 0.0),
                indoor_shade_closed=values["indoor_shade_closed"],
                indoor_shade_confidence=confidences.get(
                    "indoor_shade_closed", 0.0
                ),
                outdoor_shade_present=values["outdoor_shade_present"],
                outdoor_shade_confidence=confidences.get(
                    "outdoor_shade_present", 0.0
                ),
                action_confidence=confidence,
                passive_fit_allowed=passive,
                mode=_regime_at(regimes, cursor),
                living_office_f=_optional_temperature_value(
                    "living_office",
                    cursor,
                    buckets["living_office"],
                    non_finite["living_office"],
                    living_range_failures,
                    living_jump_failures,
                    living_gap_failures,
                    auxiliary_exclusions,
                ),
            )
        )
        cursor += STEP
    sample_times = {sample.at for sample in samples}
    confirmed_action_rows = tuple(
        sorted(
            {
                _ceil_five(event.effective_at)
                for event in events
                if event.source in CONFIRMED_SOURCES
                and _ceil_five(event.effective_at) in sample_times
            }
        )
    )
    samples = _observe_latent_mass(samples)
    return ThermalDataset(
        samples,
        start=start_utc,
        end=end_utc,
        rejected_counts=rejected,
        auxiliary_exclusion_counts=auxiliary_exclusions,
        confirmed_action_rows=confirmed_action_rows,
        interpolation_counts=interpolation_counts,
        hold_forward_counts=hold_forward_counts,
    )


def _canonical_sample(sample):
    row = asdict(sample)
    row["at"] = _iso_utc(sample.at)
    return row


MODE_COUNT_KEYS = ("unknown", "fall_charge", "winter", "spring", "warm")


def dataset_manifest(samples, events, modes):
    """Describe and digest a sample set using canonical, finite JSON rows."""
    ordered = sorted(samples, key=lambda sample: sample.at.astimezone(timezone.utc))
    canonical_rows = [_canonical_sample(sample) for sample in ordered]
    canonical_json = json.dumps(
        canonical_rows, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")

    if isinstance(samples, ThermalDataset):
        start = samples.start
        end = samples.end
        rejected_counts = samples.rejected_counts
        auxiliary_exclusion_counts = samples.auxiliary_exclusion_counts
        interpolation_counts = samples.interpolation_counts
        hold_forward_counts = samples.hold_forward_counts
    elif ordered:
        start = ordered[0].at.astimezone(timezone.utc)
        end = ordered[-1].at.astimezone(timezone.utc) + STEP
        rejected_counts = {}
        auxiliary_exclusion_counts = {}
        interpolation_counts = {}
        hold_forward_counts = {}
    else:
        start = end = None
        rejected_counts = {}
        auxiliary_exclusion_counts = {}
        interpolation_counts = {}
        hold_forward_counts = {}

    counts = Counter(record.source for record in tuple(events) + tuple(modes))
    mode_counts = {name: 0 for name in MODE_COUNT_KEYS}
    for sample in ordered:
        mode = sample.mode or "unknown"
        if mode not in mode_counts:
            raise ValueError("sample mode is outside the closed seasonal vocabulary")
        mode_counts[mode] += 1
    return {
        "start": _iso_utc(start) if start is not None else None,
        "end": _iso_utc(end) if end is not None else None,
        "sample_count": len(ordered),
        "sample_counts_by_mode": mode_counts,
        "rejected_counts": dict(sorted(rejected_counts.items())),
        "auxiliary_exclusion_counts": dict(
            sorted(auxiliary_exclusion_counts.items())
        ),
        "interpolation_counts": {
            role: int(interpolation_counts.get(role, 0))
            for role in tuple(THERMAL_ITEMS) + tuple(OPTIONAL_OBSERVATION_ITEMS)
        },
        "hold_forward_counts": {
            role: int(hold_forward_counts.get(role, 0))
            for role in tuple(THERMAL_ITEMS) + tuple(OPTIONAL_OBSERVATION_ITEMS)
        },
        "event_counts_by_source": dict(sorted(counts.items())),
        "items": {
            **dict(THERMAL_ITEMS),
            **dict(OPTIONAL_OBSERVATION_ITEMS),
        },
        "canonical_rows_sha256": sha256(canonical_json).hexdigest(),
    }
