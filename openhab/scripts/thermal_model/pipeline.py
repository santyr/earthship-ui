"""Offline orchestration for training, backtesting, and thermal shadow output.

The module treats OpenHAB persistence and the action journal as read-only
authorities.  Its only writes are delegated to the local artifact registry or
to :func:`write_shadow_output`.
"""

from bisect import bisect_right
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from .artifacts import (
    AIR_BOUNDS,
    GLAZING_BOUNDS,
    GLAZING_NAMES,
    MASS_BOUNDS,
    MAX_VENT_FORCING,
    MODEL_SCHEMA,
    MULTIHORIZON_CONTRACT,
    OUTPUT_RANGE_F,
    STABILITY_TOLERANCE,
    THERMAL_UNITS,
    ArtifactPromotionRefused,
    ArtifactUnavailable,
    ArtifactValidationError,
    validate_artifact,
)
from .behavior import (
    AIRFLOW_LEVELS,
    MINIMUM_IMPROVEMENT,
    _forcing_rows as _behavior_forcing_rows,
    baseline_schedule,
    fit_behavior,
    search_candidate_schedule,
)
from .dataset import (
    MASS_OBSERVER_TAU_MINUTES,
    MAX_HOLD_FORWARD_GAP,
    MAX_INTERPOLATION_GAP,
    build_samples,
    dataset_manifest,
    radiation_reconstruction_contract,
)
from .dynamics import (
    AIR_NAMES,
    ENVELOPE_MAX_RADIATION_WM2,
    MASS_NAMES,
    MultihorizonDynamicsFit,
    fit_diagnostics,
    fit_dynamics,
    fit_dynamics_with_evidence,
    fit_dynamics_for_evaluation,
    simulate,
)
from .evaluation import walk_forward_evaluate
from .schema import (
    OPTIONAL_OBSERVATION_ITEMS,
    THERMAL_ITEMS,
    ThermalArtifact,
    validate_shadow_output,
)


STEP = timedelta(minutes=5)
MAX_CURRENT_AGE = timedelta(minutes=20)
MIN_FORECAST_HOURS = 24
MAX_FORECAST_HOURS = 72
MAX_TRAJECTORY_POINTS = 73
MAX_OBSERVED_POINTS = 25
MAX_SHADOW_BYTES = 16 * 1024
MAX_REASON_BYTES = 256
MAX_REASONS = 8
DAILY_TRAINING_CADENCE = timedelta(hours=26)
TEMPERATURE_RANGE_F = (-40.0, 140.0)
RADIATION_RANGE_WM2 = (0.0, 1600.0)
SITE_TIMEZONE = ZoneInfo("America/Denver")
ACTION_MARKERS = frozenset(
    {
        "vent_open",
        "vent_close",
        "indoor_shade_open",
        "indoor_shade_close",
        "outdoor_shade_installed",
        "outdoor_shade_removed",
    }
)
_CURRENT_LABELS = {
    "air": "hallway temperature",
    "mass": "mass temperature",
    "outdoor": "outdoor temperature",
    "radiation": "solar radiation",
}


def _bounded_reasons(reasons, fallback):
    """Return stable, single-line reasons bounded by UTF-8 bytes."""
    if isinstance(reasons, (str, bytes)):
        reasons = (reasons,)
    bounded = []
    for reason in reasons or ():
        text = str(reason)
        text = " ".join(
            "".join(character if character.isprintable() else " " for character in text).split()
        )
        encoded = text.encode("utf-8")[:MAX_REASON_BYTES]
        text = encoded.decode("utf-8", errors="ignore").strip()
        if text and text not in bounded:
            bounded.append(text)
        if len(bounded) >= MAX_REASONS:
            break
    if not bounded:
        safe_fallback = " ".join(
            "".join(
                character if character.isprintable() else " "
                for character in str(fallback)
            ).split()
        )
        encoded = safe_fallback.encode("utf-8")[:MAX_REASON_BYTES]
        safe_fallback = encoded.decode("utf-8", errors="ignore").strip()
        bounded.append(safe_fallback or "shadow input unavailable")
    return bounded


class TrainingRefused(RuntimeError):
    """A complete backtest was persisted but the candidate was not promoted."""

    def __init__(self, reasons):
        self.reasons = tuple(str(reason) for reason in reasons if str(reason))
        super().__init__(", ".join(self.reasons) or "candidate promotion refused")


@dataclass(frozen=True)
class TrainingResult:
    artifact: ThermalArtifact
    report: dict
    promoted: bool


def _aware(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return value


def _parse_time(value, name):
    if isinstance(value, datetime):
        return _aware(value, name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    return _aware(parsed, name)


def _iso(value):
    return _aware(value, "timestamp").isoformat(timespec="seconds")


def _iso_utc(value):
    return (
        _aware(value, "timestamp")
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _finite(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _bounded(value, name, lower, upper):
    number = _finite(value, name)
    if not lower <= number <= upper:
        raise ValueError(f"{name} is outside [{lower}, {upper}]")
    return number


def _read_authorities(*, start, end, series_reader, journal, site_settings_loader):
    start = _aware(start, "start")
    end = _aware(end, "end")
    if end <= start:
        raise ValueError("end must be after start")
    if site_settings_loader is not None:
        site_settings_loader()
    series_by_role = {
        role: tuple(series_reader(item, start, end))
        for role, item in {**THERMAL_ITEMS, **OPTIONAL_OBSERVATION_ITEMS}.items()
    }
    events = tuple(journal.effective_events(start, end))
    modes = tuple(journal.effective_modes(start, end))
    return series_by_role, events, modes


def _fit_bundle(samples, dynamics_fitter, behavior_fitter):
    fitted = dynamics_fitter(samples)
    if hasattr(fitted, "dynamics") and hasattr(
        fitted, "inactive_forcing_features"
    ):
        dynamics = fitted.dynamics
        inactive = tuple(fitted.inactive_forcing_features)
    else:
        dynamics = fitted
        inactive = ()
    return SimpleNamespace(
        dynamics=dynamics,
        behavior=behavior_fitter(samples),
        inactive_forcing_features=inactive,
    )


def _constraints_manifest():
    return {
        "step_minutes": 5,
        "air_coefficient_names": list(AIR_NAMES),
        "mass_coefficient_names": list(MASS_NAMES),
        "glazing_observation_coefficient_names": list(GLAZING_NAMES),
        "air_bounds": [list(bound) for bound in AIR_BOUNDS],
        "mass_bounds": [list(bound) for bound in MASS_BOUNDS],
        "glazing_observation_bounds": [
            [value if math.isfinite(value) else None for value in bound]
            for bound in GLAZING_BOUNDS
        ],
        "output_range_f": list(OUTPUT_RANGE_F),
        "max_vent_forcing": MAX_VENT_FORCING,
        "stability_tolerance": STABILITY_TOLERANCE,
        "max_interpolation_gap_minutes": int(
            MAX_INTERPOLATION_GAP.total_seconds() / 60
        ),
        "max_every_change_hold_minutes": int(
            MAX_HOLD_FORWARD_GAP.total_seconds() / 60
        ),
        "radiation_reconstruction": radiation_reconstruction_contract(),
        "mass_observer": {
            "kind": "causal_ema",
            "source_role": "mass",
            "time_constant_minutes": MASS_OBSERVER_TAU_MINUTES,
        },
        "envelope_identification": {
            "max_radiation_wm2": ENVELOPE_MAX_RADIATION_WM2,
            "vent_forcing": 0.0,
        },
        "multihorizon_identification": deepcopy(MULTIHORIZON_CONTRACT),
    }


def _complete_manifest(samples, events, modes, evidence):
    manifest = dataset_manifest(samples, events, modes)
    diagnostics = fit_diagnostics(samples)
    diagnostics.update(
        {
            "multihorizon_origin_counts": dict(evidence.origin_counts),
            "multihorizon_initial_objective": evidence.initial_objective,
            "multihorizon_final_objective": evidence.final_objective,
        }
    )
    manifest.update(
        {
            "units": dict(THERMAL_UNITS),
            "fit_diagnostics": diagnostics,
            "constraints": _constraints_manifest(),
        }
    )
    return manifest


def _refusal_reasons(exc):
    message = str(exc).strip()
    marker = "candidate promotion refused:"
    if marker in message:
        message = message.split(marker, 1)[1].strip()
    reasons = tuple(part.strip() for part in message.split(",") if part.strip())
    return reasons or ("candidate promotion refused",)


def run_backtest(
    *,
    start,
    end,
    registry,
    journal,
    series_reader,
    forecast_reader=None,
    clock=lambda: datetime.now(timezone.utc),
    revision_reader=lambda: "",
    site_settings_loader=None,
    sample_builder=build_samples,
    dynamics_fitter=fit_dynamics,
    evaluation_dynamics_fitter=fit_dynamics_for_evaluation,
    behavior_fitter=fit_behavior,
    evaluator=walk_forward_evaluate,
    artifact_validator=validate_artifact,
):
    """Build one reproducible sample set and persist its chronological report."""
    del forecast_reader, clock, revision_reader, artifact_validator
    series_by_role, events, modes = _read_authorities(
        start=start,
        end=end,
        series_reader=series_reader,
        journal=journal,
        site_settings_loader=site_settings_loader,
    )
    samples = sample_builder(series_by_role, events, modes, start, end)
    report = evaluator(
        samples,
        lambda train: _fit_bundle(
            train, evaluation_dynamics_fitter, behavior_fitter
        ),
    )
    registry.save_backtest_report(report)
    return report


def run_training(
    *,
    start,
    end,
    registry,
    journal,
    series_reader,
    forecast_reader=None,
    clock=lambda: datetime.now(timezone.utc),
    revision_reader=lambda: "",
    site_settings_loader=None,
    sample_builder=build_samples,
    dynamics_fitter=fit_dynamics_with_evidence,
    evaluation_dynamics_fitter=fit_dynamics_for_evaluation,
    behavior_fitter=fit_behavior,
    evaluator=walk_forward_evaluate,
    artifact_validator=validate_artifact,
):
    """Fit, backtest, persist, validate, and promote an offline candidate."""
    del forecast_reader
    series_by_role, events, modes = _read_authorities(
        start=start,
        end=end,
        series_reader=series_reader,
        journal=journal,
        site_settings_loader=site_settings_loader,
    )
    samples = sample_builder(series_by_role, events, modes, start, end)
    fitted_dynamics = dynamics_fitter(samples)
    if not isinstance(fitted_dynamics, MultihorizonDynamicsFit):
        raise ValueError(
            "training dynamics fitter must return multihorizon evidence"
        )
    dynamics = fitted_dynamics.dynamics
    behavior = behavior_fitter(samples)
    report = evaluator(
        samples,
        lambda train: _fit_bundle(
            train, evaluation_dynamics_fitter, behavior_fitter
        ),
    )

    # The refusal evidence is durable before any candidate validation or promotion.
    registry.save_backtest_report(report)
    manifest = _complete_manifest(
        samples, events, modes, fitted_dynamics.evidence
    )
    created_at = _aware(clock(), "clock")
    artifact = ThermalArtifact(
        schema=MODEL_SCHEMA,
        created_at=_iso_utc(created_at),
        trained_from=manifest["start"],
        trained_through=manifest["end"],
        code_revision=str(revision_reader()),
        dynamics=dynamics,
        behavior=behavior,
        metrics=report["metrics"],
        data_manifest=manifest,
    )
    try:
        artifact_validator(artifact)
        registry.save_candidate(artifact)
        promoted = registry.promote_candidate()
    except (ArtifactPromotionRefused, ArtifactValidationError, ValueError) as exc:
        raise TrainingRefused(_refusal_reasons(exc)) from exc
    return TrainingResult(artifact=promoted, report=report, promoted=True)


def _row_value(row, names, label):
    for name in names:
        if name in row:
            return row[name]
    raise ValueError(f"forecast {label} is missing")


def _normalize_hourly_rows(rows):
    rows = tuple(rows)
    raw_timelines = [
        raw.get("_modeTimeline")
        for raw in rows
        if isinstance(raw, dict) and raw.get("_modeTimeline") is not None
    ]
    timeline = ()
    if raw_timelines:
        timeline = tuple(
            (
                _parse_time(effective_at, "mode transition timestamp"),
                str(mode),
            )
            for effective_at, mode in raw_timelines[0]
        )
        if any(mode not in {"spring", "warm", "fall_charge", "winter"} for _, mode in timeline):
            raise ValueError("mode transition is invalid")
        if any(
            tuple(
                (
                    _parse_time(effective_at, "mode transition timestamp"),
                    str(mode),
                )
                for effective_at, mode in candidate
            )
            != timeline
            for candidate in raw_timelines[1:]
        ):
            raise ValueError("forecast mode timelines disagree")
    normalized = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("forecast row must be an object")
        at = _parse_time(raw.get("at"), "forecast timestamp")
        temperature = _finite(
            _row_value(raw, ("tempF", "outdoor_f", "temperature_2m"), "temperature"),
            "forecast temperature",
        )
        radiation = _finite(
            _row_value(
                raw,
                ("radiationWm2", "radiation_wm2", "shortwave_radiation"),
                "solar radiation",
            ),
            "forecast solar radiation",
        )
        temperature = _bounded(temperature, "forecast temperature", *TEMPERATURE_RANGE_F)
        radiation = _bounded(radiation, "forecast solar radiation", *RADIATION_RANGE_WM2)
        wind = _finite(
            _row_value(raw, ("windMph", "wind_mph", "wind_speed_10m"), "wind"),
            "forecast wind",
        )
        weather = _row_value(
            raw,
            ("weatherCode", "weather_code", "cloudState", "cloud_state"),
            "cloud/weather state",
        )
        if weather is None or isinstance(weather, (dict, list, tuple)):
            raise ValueError("forecast cloud/weather state is invalid")
        mode = str(raw.get("mode", raw.get("season", "")))
        if mode not in {"spring", "warm", "fall_charge", "winter"}:
            raise ValueError("forecast mode is missing or invalid")
        normalized.append(
            {
                "at": at,
                "outdoor_f": temperature,
                "radiation_wm2": radiation,
                "weather_code": weather,
                "wind_mph": wind,
                "mode": mode,
                "_modeTimeline": timeline,
            }
        )
    normalized.sort(key=lambda row: row["at"].astimezone(timezone.utc))
    if len(normalized) < 2:
        raise ValueError("forecast requires at least two timestamped hourly rows")
    for left, right in zip(normalized, normalized[1:]):
        difference = right["at"].astimezone(timezone.utc) - left["at"].astimezone(timezone.utc)
        if difference != timedelta(hours=1):
            raise ValueError("forecast rows must be unique consecutive hourly timestamps")
    return tuple(normalized)


def interpolate_hourly_forecast(rows, *, start, end):
    """Interpolate numeric forcing at five minutes and hold source categories."""
    start = _aware(start, "forecast start")
    end = _aware(end, "forecast end")
    if end < start:
        raise ValueError("forecast end must not precede start")
    hourly = _normalize_hourly_rows(rows)
    utc_times = tuple(row["at"].astimezone(timezone.utc) for row in hourly)
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    if start_utc < utc_times[0] or end_utc > utc_times[-1]:
        raise ValueError("forecast interpolation must not extrapolate")
    if start.second or start.microsecond or start.minute % 5:
        raise ValueError("forecast start must align to a five-minute boundary")
    if end.second or end.microsecond or end.minute % 5:
        raise ValueError("forecast end must align to a five-minute boundary")

    result = []
    cursor_utc = start_utc
    while cursor_utc <= end_utc:
        cursor = cursor_utc.astimezone(start.tzinfo)
        right_index = bisect_right(utc_times, cursor_utc)
        if right_index == 0:
            raise ValueError("forecast interpolation must not extrapolate")
        if right_index == len(hourly):
            if cursor_utc != utc_times[-1]:
                raise ValueError("forecast interpolation must not extrapolate")
            left = right = hourly[-1]
            fraction = 0.0
        else:
            left = hourly[right_index - 1]
            right = hourly[right_index]
            elapsed = cursor_utc - left["at"].astimezone(timezone.utc)
            span = right["at"].astimezone(timezone.utc) - left["at"].astimezone(timezone.utc)
            fraction = elapsed / span
        result.append(
            {
                "at": cursor,
                "outdoor_f": float(
                    left["outdoor_f"]
                    + fraction * (right["outdoor_f"] - left["outdoor_f"])
                ),
                "radiation_wm2": float(
                    left["radiation_wm2"]
                    + fraction * (right["radiation_wm2"] - left["radiation_wm2"])
                ),
                "weather_code": left["weather_code"] if fraction < 1.0 else right["weather_code"],
                "wind_mph": left["wind_mph"] if fraction < 1.0 else right["wind_mph"],
                "mode": (
                    max(
                        (
                            (effective_at, mode)
                            for effective_at, mode in left["_modeTimeline"]
                            if effective_at.astimezone(timezone.utc) <= cursor_utc
                        ),
                        key=lambda item: item[0].astimezone(timezone.utc),
                    )[1]
                    if left["_modeTimeline"]
                    else left["mode"] if fraction < 1.0 else right["mode"]
                ),
                "_modeTimeline": left["_modeTimeline"],
            }
        )
        cursor_utc += STEP
    return result


def _reading(entry, role, now):
    label = _CURRENT_LABELS.get(role, role)
    if not isinstance(entry, dict):
        raise ValueError(f"missing {label}")
    at = _parse_time(entry.get("at"), f"{label} timestamp")
    value = entry.get("value")
    if role == "glazing" and value is None:
        return None, at, max(0.0, (now - at).total_seconds() / 60.0)
    bounds = RADIATION_RANGE_WM2 if role == "radiation" else TEMPERATURE_RANGE_F
    number = _bounded(value, label, *bounds)
    age = now.astimezone(timezone.utc) - at.astimezone(timezone.utc)
    if age < timedelta(0):
        raise ValueError(f"future {label}")
    if role in _CURRENT_LABELS and age > MAX_CURRENT_AGE:
        raise ValueError(f"stale {label}")
    return number, at, age.total_seconds() / 60.0


def _current_values(current, now):
    values = {}
    ages = {}
    for role in ("air", "mass", "outdoor", "radiation", "glazing"):
        if role == "glazing" and role not in current:
            values[role] = None
            ages[role] = None
            continue
        value, _, age = _reading(current.get(role), role, now)
        values[role] = value
        ages[role] = round(age, 3)
    return values, ages


def _artifact_context(artifact, now):
    created = _parse_time(artifact.created_at, "artifact created_at")
    trained = _parse_time(artifact.trained_through, "artifact trained_through")
    now_utc = now.astimezone(timezone.utc)
    if created.astimezone(timezone.utc) > now_utc:
        raise ValueError("artifact created_at is in the future")
    if trained.astimezone(timezone.utc) > now_utc:
        raise ValueError("artifact trained_through is in the future")
    model_age = (now_utc - created.astimezone(timezone.utc)).total_seconds() / 3600.0
    data_age = (now_utc - trained.astimezone(timezone.utc)).total_seconds() / 3600.0
    metadata = {
        "createdAt": _iso(created),
        "trainedThrough": _iso(trained),
        "codeRevision": str(artifact.code_revision),
    }
    return metadata, round(model_age, 3), round(data_age, 3)


def _observed_rows(current, now):
    observed = []
    for row in current.get("observed", ()):
        try:
            at = _parse_time(row.get("at"), "observed timestamp")
            if at.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                continue
            air = _finite(row.get("hallwayF", row.get("air_f")), "observed hallway")
            mass = _finite(row.get("massF", row.get("mass_f")), "observed mass")
        except (AttributeError, TypeError, ValueError):
            continue
        observed.append({"at": _iso(at), "hallwayF": round(air, 3), "massF": round(mass, 3)})
    observed.sort(key=lambda row: _parse_time(row["at"], "observed timestamp"))
    return observed[-MAX_OBSERVED_POINTS:]


def _local_minute(day, minute, timezone_value):
    return (
        datetime.combine(day, datetime.min.time(), tzinfo=timezone_value)
        + timedelta(minutes=int(minute))
    )


def _expand_nightly_venting(schedule, rows, timezone_value):
    if (
        schedule.get("mode") == "winter"
        or schedule.get("ventOpenMinute") is None
        or schedule.get("ventCloseMinute") is None
    ):
        return dict(schedule)
    first = rows[0]["at"].astimezone(timezone_value)
    last = rows[-1]["at"].astimezone(timezone_value)
    first_utc = first.astimezone(timezone.utc)
    last_utc = last.astimezone(timezone.utc)
    day = first.date() - timedelta(days=1)
    segments = []
    while day <= last.date():
        opened = _local_minute(day, schedule["ventOpenMinute"], timezone_value)
        close_day = day + timedelta(
            days=int(schedule["ventCloseMinute"] <= schedule["ventOpenMinute"])
        )
        closed = _local_minute(close_day, schedule["ventCloseMinute"], timezone_value)
        if (
            closed.astimezone(timezone.utc) > first_utc
            and opened.astimezone(timezone.utc) < last_utc
        ):
            segments.append(
                {
                    "startAt": max(opened, first),
                    "endAt": min(closed, last),
                    "level": "baseline",
                }
            )
        day += timedelta(days=1)
    segments.extend(
        dict(segment)
        for segment in schedule.get("airflowSegments", ())
        if segment.get("level") == "boosted"
    )
    clipped = []
    for segment in segments:
        start = segment["startAt"]
        end = segment["endAt"]
        if end.astimezone(timezone.utc) <= first_utc or start.astimezone(timezone.utc) >= last_utc:
            continue
        clipped.append(
            {
                **segment,
                "startAt": first if start.astimezone(timezone.utc) < first_utc else start,
                "endAt": last if end.astimezone(timezone.utc) > last_utc else end,
            }
        )
    clipped.sort(
        key=lambda segment: (
            segment["startAt"].astimezone(timezone.utc),
            0 if segment["level"] == "baseline" else 1,
        )
    )
    expanded = dict(schedule)
    expanded["airflowSegments"] = tuple(clipped)
    return expanded


def _validate_internal_schedule(schedule, *, horizon_start, horizon_end):
    """Validate the richer modeled schedule before simulation and projection."""
    if not isinstance(schedule, dict):
        raise ValueError("modeled schedule must be an object")
    start_limit = _aware(horizon_start, "schedule horizon start").astimezone(timezone.utc)
    end_limit = _aware(horizon_end, "schedule horizon end").astimezone(timezone.utc)
    if start_limit >= end_limit:
        raise ValueError("schedule horizon must be ordered")

    opened = schedule.get("ventOpenAt")
    closed = schedule.get("ventCloseAt")
    if (opened is None) != (closed is None):
        raise ValueError("modeled vent window must be complete")
    if opened is not None:
        opened_utc = _aware(opened, "modeled vent open").astimezone(timezone.utc)
        closed_utc = _aware(closed, "modeled vent close").astimezone(timezone.utc)
        if not start_limit <= opened_utc < closed_utc <= end_limit:
            raise ValueError("modeled vent window must be ordered within the horizon")

    raw_transitions = schedule.get("shadeTransitions", ())
    if not isinstance(raw_transitions, (tuple, list)):
        raise ValueError("modeled shade transitions must be a sequence")
    shade_transitions = []
    for index, transition in enumerate(raw_transitions):
        if not isinstance(transition, dict) or set(transition) != {
            "at", "state", "source", "status"
        }:
            raise ValueError(f"modeled shade transition {index} has invalid fields")
        at = _aware(transition["at"], "modeled shade transition").astimezone(timezone.utc)
        if not start_limit <= at <= end_limit:
            raise ValueError("modeled shade transition must be within the horizon")
        if transition["state"] not in {"open", "closed"}:
            raise ValueError("modeled shade transition state is invalid")
        for field in ("source", "status"):
            value = transition[field]
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 64:
                raise ValueError(f"modeled shade transition {field} is invalid")
        shade_transitions.append((at, transition["state"]))
    for prior, current_transition in zip(shade_transitions, shade_transitions[1:]):
        if current_transition[0] <= prior[0]:
            raise ValueError("modeled shade transitions must be strictly ordered")
        if current_transition[1] == prior[1]:
            raise ValueError("modeled shade transitions must change state")

    shade_open = schedule.get("shadeOpenAt")
    shade_close = schedule.get("shadeCloseAt")
    if shade_transitions:
        first_open = next((at for at, state in shade_transitions if state == "open"), None)
        first_close = next((at for at, state in shade_transitions if state == "closed"), None)
        for legacy, expected, label in (
            (shade_open, first_open, "open"),
            (shade_close, first_close, "close"),
        ):
            if (legacy is None) != (expected is None) or (
                legacy is not None
                and _aware(legacy, f"modeled shade {label}").astimezone(timezone.utc) != expected
            ):
                raise ValueError("modeled shade legacy times must match typed transitions")
    else:
        if (shade_open is None) != (shade_close is None):
            raise ValueError("modeled shade window must be complete")
        if shade_open is not None:
            shade_open_utc = _aware(shade_open, "modeled shade open").astimezone(timezone.utc)
            shade_close_utc = _aware(shade_close, "modeled shade close").astimezone(timezone.utc)
            if not start_limit <= shade_open_utc < shade_close_utc <= end_limit:
                raise ValueError("modeled shade window must be ordered within the horizon")

    raw_segments = schedule.get("airflowSegments", ())
    if not isinstance(raw_segments, (tuple, list)):
        raise ValueError("modeled airflow segments must be a sequence")
    segments = []
    for index, segment in enumerate(raw_segments):
        if not isinstance(segment, dict) or set(segment) != {"startAt", "endAt", "level"}:
            raise ValueError(f"modeled airflow segment {index} has invalid fields")
        level = segment["level"]
        if level not in AIRFLOW_LEVELS:
            raise ValueError(f"modeled airflow segment {index} has invalid level")
        started = _aware(segment["startAt"], "airflow start").astimezone(timezone.utc)
        ended = _aware(segment["endAt"], "airflow end").astimezone(timezone.utc)
        if not start_limit <= started < ended <= end_limit:
            raise ValueError("modeled airflow segment must be ordered within the horizon")
        segments.append((started, ended, level))

    baseline_windows = [item for item in segments if item[2] == "baseline"]
    for started, ended, level in segments:
        if level == "boosted" and not any(
            owner_start <= started and ended <= owner_end
            for owner_start, owner_end, _ in baseline_windows
        ):
            raise ValueError("boosted airflow segment must be nested within a vent window")

    for level in AIRFLOW_LEVELS:
        prior_start = None
        prior_end = None
        for started, ended, segment_level in segments:
            if segment_level != level:
                continue
            if prior_start is not None and started < prior_start:
                raise ValueError(f"{level} airflow segments must be sorted")
            if prior_end is not None and started < prior_end:
                raise ValueError(f"{level} airflow segments must not overlap")
            prior_start, prior_end = started, ended
    return schedule


def _vent_schedule_is_valid(rows, schedule):
    if schedule.get("mode") == "winter":
        return True
    origin = rows[0]["at"]
    horizon_end = rows[-1]["at"]
    for segment in schedule.get("airflowSegments", ()):
        if segment.get("level") != "baseline" or segment["startAt"] < origin:
            continue
        window = [
            row
            for row in rows
            if segment["startAt"] <= row["at"] < min(segment["endAt"], horizon_end)
        ]
        if len(window) < 12:
            return False
        if any(
            row["outdoor_f"] > row.get("air_baseline_f", row["air_f"]) - 1.0
            for row in window[:12]
        ):
            return False
        if any(
            row["outdoor_f"] >= row.get("air_baseline_f", row["air_f"])
            for row in window
        ):
            return False
    return True


def _schedule_forcings(rows, schedule):
    """Use the behavior engine's per-timestep forcing semantics verbatim."""
    return _behavior_forcing_rows(rows, schedule)


def _simulate_schedule(dynamics, rows, schedule, initial):
    return simulate(dynamics, initial, _schedule_forcings(rows, schedule))


def _summary_metric(artifact, name):
    try:
        value = artifact.metrics["overall"]["model"]["air"]["24"][name]
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError(f"artifact 24-hour {name} is unavailable") from exc
    return _finite(value, f"artifact 24-hour {name}")


def _interval_margin(artifact):
    rmse = _summary_metric(artifact, "rmse")
    try:
        coverage = artifact.metrics["prediction_interval_coverage"]["air"]["24"]["fraction"]
        fraction = _finite(coverage, "artifact interval coverage")
    except (KeyError, TypeError, ValueError):
        fraction = 0.0
    widening = 1.0 + max(0.0, 0.90 - min(1.0, max(0.0, fraction)))
    return max(0.5, 1.645 * rmse * widening)


def _contains_positive_count(value):
    if isinstance(value, dict):
        return any(
            (key == "count" and isinstance(nested, int) and nested > 0)
            or _contains_positive_count(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_positive_count(item) for item in value)
    return False


def _action_label(artifact):
    counts = artifact.data_manifest.get("event_counts_by_source", {})
    evaluation = artifact.metrics.get("by_provenance", {})
    confirmed = artifact.metrics.get("action_evidence", {}).get("confirmed", {})
    if (
        isinstance(confirmed, dict)
        and isinstance(confirmed.get("training_rows"), int)
        and not isinstance(confirmed.get("training_rows"), bool)
        and confirmed["training_rows"] > 0
        and isinstance(confirmed.get("evaluation_targets"), int)
        and not isinstance(confirmed.get("evaluation_targets"), bool)
        and confirmed["evaluation_targets"] > 0
        and isinstance(confirmed.get("disjoint_fold_count"), int)
        and not isinstance(confirmed.get("disjoint_fold_count"), bool)
        and confirmed["disjoint_fold_count"] > 0
    ):
        return "confirmed", "operator_confirmed"
    for label, sources in (
        ("photosensor", ("photosensor",)),
        ("reconstructed", ("historical_reconstruction",)),
        ("model_inferred", ("model_inferred",)),
    ):
        if any(counts.get(source, 0) > 0 for source in sources) or _contains_positive_count(evaluation.get(label, {})):
            return label, sources[0]
    return "unknown", "unknown"


def _schedule_times(schedule):
    if schedule is None:
        return None
    return {
        "ventOpenAt": _iso(schedule["ventOpenAt"]) if schedule.get("ventOpenAt") else None,
        "ventCloseAt": _iso(schedule["ventCloseAt"]) if schedule.get("ventCloseAt") else None,
    }


def _action_events(schedule):
    if schedule is None:
        return ()
    events = [
        (segment["startAt"], "vent_open")
        for segment in schedule.get("airflowSegments", ())
        if segment.get("level") == "baseline"
    ]
    events.extend(
        (segment["endAt"], "vent_close")
        for segment in schedule.get("airflowSegments", ())
        if segment.get("level") == "baseline"
    )
    shade_transitions = schedule.get("shadeTransitions", ())
    if shade_transitions:
        events.extend(
            (transition["at"], f'indoor_shade_{"open" if transition["state"] == "open" else "close"}')
            for transition in shade_transitions
        )
    else:
        events.extend(
            (schedule[field], marker)
            for field, marker in (
                ("shadeOpenAt", "indoor_shade_open"),
                ("shadeCloseAt", "indoor_shade_close"),
            )
            if schedule.get(field) is not None
        )
    events = tuple(dict.fromkeys(events))
    if any(marker not in ACTION_MARKERS for _, marker in events):
        raise ValueError("action marker is outside the closed vocabulary")
    return tuple(sorted(events, key=lambda item: item[0]))


def _trajectory(rows, predictions, margin, schedule, timezone_value):
    states = (
        {"air_f": rows[0]["air_f"], "mass_f": rows[0]["mass_f"]},
        *predictions,
    )
    events = _action_events(schedule)
    points = []
    previous_boundary = None
    for row, state in zip(rows, states):
        local = row["at"].astimezone(timezone_value)
        if local.minute != 0 or local.second != 0 or local.microsecond != 0:
            continue
        actions = [
            marker
            for at, marker in events
            if (previous_boundary is None and at == row["at"])
            or (previous_boundary is not None and previous_boundary < at <= row["at"])
        ]
        air = float(state["air_f"])
        points.append(
            {
                "at": _iso(row["at"]),
                "hallwayF": round(air, 3),
                "massF": round(float(state["mass_f"]), 3),
                "lowF": round(air - margin, 3),
                "highF": round(air + margin, 3),
                "actions": actions,
            }
        )
        previous_boundary = row["at"]
    return points[:MAX_TRAJECTORY_POINTS]


def _morning_mass(rows, predictions, timezone_value):
    for row, state in zip(rows[1:], predictions):
        local = row["at"].astimezone(timezone_value)
        if local.hour == 7 and local.minute == 0:
            return float(state["mass_f"])
    return float(predictions[-1]["mass_f"])


def _unavailable(
    now, reasons, *, artifact=None, current=None,
    fallback_reason="shadow input unavailable",
):
    model = {}
    model_age = None
    data_age = None
    if artifact is not None:
        try:
            model, model_age, data_age = _artifact_context(artifact, now)
        except (AttributeError, TypeError, ValueError):
            model = {}
    current_payload = {"hallwayF": None, "massF": None, "glazingF": None}
    ages = {role: None for role in THERMAL_ITEMS}
    if isinstance(current, dict):
        for role, field in (("air", "hallwayF"), ("mass", "massF"), ("glazing", "glazingF"), ("outdoor", None), ("radiation", None)):
            entry = current.get(role)
            if isinstance(entry, dict):
                value = entry.get("value")
                try:
                    if field is not None:
                        current_payload[field] = (
                            None if value is None else _finite(value, field)
                        )
                    at = _parse_time(entry.get("at"), f"{field} timestamp")
                    ages[role] = round(max(0.0, (now - at).total_seconds() / 60.0), 3)
                except (TypeError, ValueError):
                    pass
    payload = {
        "version": 1,
        "status": "shadow",
        "generatedAt": _iso(now),
        "model": model,
        "current": current_payload,
        "forecast": {
            "availableHours": 0,
            "hallwayHighF": None,
            "hallwayHighAt": None,
            "hallwayLowF": None,
            "hallwayLowAt": None,
            "morningMassF": None,
            "intervalLowF": None,
            "intervalHighF": None,
            "trajectory": [],
            "observed": _observed_rows(current or {}, now),
        },
        "schedule": {},
        "confidence": {"grade": "unavailable", "actionLabels": "unknown"},
        "provenance": {
            "sensorItems": dict(THERMAL_ITEMS),
            "actions": "unknown",
            "currentAgeMinutes": ages,
            "modelAgeHours": model_age,
            "trainingDataAgeHours": data_age,
        },
        "reasons": _bounded_reasons(reasons, fallback_reason),
    }
    validate_shadow_output(payload)
    return payload


def _build_available_shadow(
    *, artifact, current, forecast, now, site_timezone, registry_reason=None
):
    model, model_age, data_age = _artifact_context(artifact, now)
    values, current_ages = _current_values(current, now)
    local_now = now.astimezone(site_timezone)
    origin = local_now.replace(second=0, microsecond=0) - timedelta(minutes=local_now.minute % 5)
    hourly = _normalize_hourly_rows(forecast)
    final = min(hourly[-1]["at"].astimezone(timezone.utc), origin.astimezone(timezone.utc) + timedelta(hours=MAX_FORECAST_HOURS))
    available_hours = int((final - origin.astimezone(timezone.utc)).total_seconds() // 3600)
    if available_hours < MIN_FORECAST_HOURS:
        raise ValueError(
            f"forecast horizon is {available_hours} hours; at least {MIN_FORECAST_HOURS} required"
        )
    end = (origin.astimezone(timezone.utc) + timedelta(hours=available_hours)).astimezone(origin.tzinfo)
    rows = interpolate_hourly_forecast(hourly, start=origin, end=end)
    rows[0].update({"air_f": values["air"], "mass_f": values["mass"]})
    initial = {"air_f": values["air"], "mass_f": values["mass"]}

    # Weather provides outdoor forcing only. Seed the learned timing features
    # with a causal physics trajectory under the existing seasonal protocol.
    # The learned schedule is then simulated again below for candidate scoring.
    protocol_behavior = replace(artifact.behavior, transitions={})
    protocol = _expand_nightly_venting(
        baseline_schedule(protocol_behavior, rows), rows, site_timezone
    )
    _validate_internal_schedule(
        protocol, horizon_start=rows[0]["at"], horizon_end=rows[-1]["at"]
    )
    protocol_predictions = _simulate_schedule(artifact.dynamics, rows, protocol, initial)
    for row, predicted in zip(rows[1:], protocol_predictions):
        row.update({"air_f": predicted["air_f"], "mass_f": predicted["mass_f"]})

    baseline = _expand_nightly_venting(
        baseline_schedule(artifact.behavior, rows), rows, site_timezone
    )
    _validate_internal_schedule(
        baseline, horizon_start=rows[0]["at"], horizon_end=rows[-1]["at"]
    )
    baseline_predictions = _simulate_schedule(artifact.dynamics, rows, baseline, initial)
    decorated = [dict(rows[0])]
    for row, predicted in zip(rows[1:], baseline_predictions):
        decorated.append(
            {
                **row,
                "air_f": predicted["air_f"],
                "mass_f": predicted["mass_f"],
                "air_baseline_f": predicted["air_f"],
                "mass_baseline_f": predicted["mass_f"],
            }
        )
    search = search_candidate_schedule(
        behavior=artifact.behavior,
        dynamics=artifact.dynamics,
        forecast=decorated,
    )
    selection_reason = search.modeled_difference.get("selectionReason")
    improvement = _finite(
        search.modeled_difference.get("scoreImprovement", 0.0),
        "candidate score improvement",
    )
    candidate = (
        _expand_nightly_venting(search.candidate, rows, site_timezone)
        if search.candidate is not None
        else None
    )
    if (
        selection_reason != "bounded_candidate_improved"
        or improvement < MINIMUM_IMPROVEMENT
        or candidate == baseline
    ):
        candidate = None
    elif candidate is not None:
        try:
            _validate_internal_schedule(
                candidate, horizon_start=rows[0]["at"], horizon_end=rows[-1]["at"]
            )
        except ValueError:
            candidate = None
            selection_reason = "no_valid_candidate"
    if candidate is not None and not _vent_schedule_is_valid(decorated, candidate):
        candidate = None
        selection_reason = "no_valid_candidate"
    selected = candidate or baseline
    predictions = (
        _simulate_schedule(artifact.dynamics, rows, selected, initial)
        if selected != baseline
        else baseline_predictions
    )
    margin = _interval_margin(artifact)
    trajectory = _trajectory(rows, predictions, margin, selected, site_timezone)
    all_states = (
        {"air_f": values["air"], "mass_f": values["mass"]},
        *predictions,
    )
    high_index = max(range(len(all_states)), key=lambda index: all_states[index]["air_f"])
    low_index = min(range(len(all_states)), key=lambda index: all_states[index]["air_f"])
    baseline_peak = max(float(row["air_f"]) for row in baseline_predictions)
    selected_peak = max(float(row["air_f"]) for row in predictions)
    baseline_morning = _morning_mass(rows, baseline_predictions, site_timezone)
    selected_morning = _morning_mass(rows, predictions, site_timezone)
    action_label, action_source = _action_label(artifact)
    reasons = []
    if registry_reason is not None:
        reasons.append(registry_reason)
    if timedelta(hours=model_age) > DAILY_TRAINING_CADENCE:
        reasons.append("accepted model daily training cadence missed")
    if candidate is None:
        reasons.append(
            {
                "minimum_improvement_not_met": "minimum modeled improvement not met; no candidate emitted",
                "protocol_constraint": "protocol constraint retained baseline; no candidate emitted",
                "explicit_mode_transition": "explicit journal mode transition retained evidence-backed baseline; no candidate emitted",
            }.get(selection_reason, "no physically valid bounded candidate")
        )
    elif selection_reason == "bounded_candidate_improved":
        reasons.append("bounded candidate improved in model simulation")
    else:
        reasons.append("minimum modeled improvement not met; baseline retained")

    payload = {
        "version": 1,
        "status": "shadow",
        "generatedAt": _iso(now),
        "model": model,
        "current": {
            "hallwayF": round(values["air"], 3),
            "massF": round(values["mass"], 3),
            "glazingF": None if values["glazing"] is None else round(values["glazing"], 3),
        },
        "forecast": {
            "availableHours": available_hours,
            "hallwayHighF": round(float(all_states[high_index]["air_f"]), 3),
            "hallwayHighAt": _iso(rows[high_index]["at"]),
            "hallwayLowF": round(float(all_states[low_index]["air_f"]), 3),
            "hallwayLowAt": _iso(rows[low_index]["at"]),
            "morningMassF": round(selected_morning, 3),
            "intervalLowF": round(
                min(float(state["air_f"]) for state in all_states) - margin, 3
            ),
            "intervalHighF": round(
                max(float(state["air_f"]) for state in all_states) + margin, 3
            ),
            "trajectory": trajectory,
            "observed": _observed_rows(current, now),
        },
        "schedule": {
            "baseline": _schedule_times(baseline),
            "candidate": _schedule_times(candidate),
            "effect": {
                "morningMassDeltaF": round(selected_morning - baseline_morning, 3),
                "hallwayPeakDeltaF": round(selected_peak - baseline_peak, 3),
            },
        },
        "confidence": {"grade": "low", "actionLabels": action_label},
        "provenance": {
            "sensorItems": dict(THERMAL_ITEMS),
            "actions": action_source,
            "currentAgeMinutes": current_ages,
            "modelAgeHours": model_age,
            "trainingDataAgeHours": data_age,
        },
        "reasons": reasons,
    }
    validate_shadow_output(payload)
    encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) >= MAX_SHADOW_BYTES:
        raise ValueError("shadow output exceeds the 16 KiB bound")
    return payload


def build_unavailable_shadow(
    *, now, reasons, artifact=None, current=None,
    fallback_reason="shadow input unavailable",
):
    """Build one exact fail-soft shadow payload without reading any authority."""
    return _unavailable(
        _aware(now, "now"), reasons, artifact=artifact, current=current,
        fallback_reason=fallback_reason,
    )


def run_shadow(*, registry, current, forecast, now, site_timezone=SITE_TIMEZONE):
    """Return a bounded shadow result; invalid dependencies fail soft."""
    now = _aware(now, "now")
    artifact = None
    failed_input = "accepted artifact input"
    try:
        artifact = registry.load_accepted()
        registry_reason = (
            "accepted model recovered from verified prior accepted generation"
            if getattr(registry, "last_load_source", None) == "previous_restored"
            else None
        )
        failed_input = "shadow input"
        return _build_available_shadow(
            artifact=artifact,
            current=current,
            forecast=forecast,
            now=now,
            site_timezone=site_timezone,
            registry_reason=registry_reason,
        )
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        ArtifactValidationError,
        ArtifactUnavailable,
        OSError,
    ) as exc:
        return _unavailable(
            now, (str(exc),), artifact=artifact, current=current,
            fallback_reason=f"{failed_input} unavailable",
        )


def build_shadow_output(**kwargs):
    """Compatibility entrypoint for the versioned Task 7 shadow builder."""
    return run_shadow(**kwargs)


def write_shadow_output(path, payload):
    """Atomically write one validated, compact local shadow JSON document."""
    validate_shadow_output(payload)
    encoded = (
        json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    if len(encoded) >= MAX_SHADOW_BYTES:
        raise ValueError("shadow output exceeds the 16 KiB bound")
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{destination.name}.tmp-", dir=destination.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        temporary = None
        directory = os.open(
            destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return destination
