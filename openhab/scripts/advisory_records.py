"""Canonical immutable advisory evidence records; no storage or side effects."""
import json
import math
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from advisory_windows import local_day_window, trough_window

INPUT_FIELDS = frozenset({
    "weather_today_high_raw_f", "weather_today_low_raw_f",
    "tomorrow_high_raw_f", "tomorrow_low_raw_f",
    "tomorrow_high_corrected_f", "tomorrow_low_corrected_f",
    "high_bias_f", "low_bias_f", "next_three_highs_raw_f",
    "three_day_high_mean_corrected_f", "pv_today_kwh", "trough_tomorrow_pct",
})
THRESHOLD_FIELDS = frozenset({
    "close_up_high_f", "close_up_streak_f", "vent_high_f", "trough_dm_pct",
})
ADVISORIES = frozenset({"none", "vent_tonight", "close_up_tomorrow"})
PUBLICATION_TARGETS = frozenset({"Thermal_Advisory", "Predicted_SoC_Trough_Tomorrow"})
PUBLICATION_STATES = frozenset({"accepted", "failed", "unknown"})
NOTIFICATION_STATES = frozenset({
    "not_eligible", "suppressed", "attempted_reported_success",
    "attempted_failed", "attempted_unknown", "unknown",
})
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/+\-]{0,95}\Z")


def _id(value):
    if not isinstance(value, (str, UUID)):
        raise ValueError("UUID identity required")
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise ValueError("UUID identity required") from exc


def _stamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("offset-qualified timestamp required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _token(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ValueError("bounded version/epoch token required")
    return value


def _number(value):
    if type(value) not in (int, float):
        raise ValueError("finite numeric input required")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("finite numeric input required") from exc
    if not math.isfinite(number):
        raise ValueError("finite numeric input required")
    return number


def _fields(values, expected):
    if not isinstance(values, dict) or set(values) != expected:
        raise ValueError("record fields do not match the schema")


def _window(window):
    return {"start": _stamp(window.start), "end": _stamp(window.end)}


def _encode(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_decision_record(*, decision_id, issued_at, site_timezone,
                          source_revision, policy_version, bank_epoch,
                          prediction_day, advisory, inputs, thresholds,
                          notification_eligible, notification_suppressed):
    """Freeze caller-used values; never recalculate policy or generate a clock/ID."""
    _fields(inputs, INPUT_FIELDS)
    _fields(thresholds, THRESHOLD_FIELDS)
    sequence = inputs["next_three_highs_raw_f"]
    if not isinstance(sequence, (list, tuple)) or len(sequence) != 3:
        raise ValueError("three raw high forecasts required")
    frozen_inputs = {
        key: ([_number(value) for value in sequence]
              if key == "next_three_highs_raw_f" else _number(value))
        for key, value in inputs.items()
    }
    frozen_thresholds = {key: _number(value) for key, value in thresholds.items()}
    if advisory not in ADVISORIES:
        raise ValueError("unknown advisory category")
    if type(notification_eligible) is not bool or type(notification_suppressed) is not bool:
        raise ValueError("notification intent requires explicit booleans")
    if notification_suppressed and not notification_eligible:
        raise ValueError("only eligible notifications can be suppressed")
    if not isinstance(site_timezone, str):
        raise ValueError("IANA site timezone required")
    ZoneInfo(site_timezone)
    today = local_day_window(prediction_day, site_timezone)
    tomorrow = local_day_window(prediction_day + timedelta(days=1), site_timezone)
    night = trough_window(prediction_day, site_timezone)
    return _encode({
        "schema_version": 1, "record_type": "advisory_decision",
        "decision_id": _id(decision_id), "issued_at": _stamp(issued_at),
        "site_timezone": site_timezone, "source_revision": _token(source_revision),
        "policy_version": _token(policy_version), "bank_epoch": _token(bank_epoch),
        "prediction_day": prediction_day.isoformat(), "advisory": advisory,
        "inputs": frozen_inputs, "thresholds": frozen_thresholds,
        "notification": {"eligible": notification_eligible, "suppressed": notification_suppressed},
        "targets": {
            "pv_today": _window(today), "trough": _window(night),
            "weather_today": _window(today), "weather_tomorrow": _window(tomorrow),
            "thermal_tomorrow": _window(tomorrow), "action_transition": _window(night),
        },
    })


def build_result_record(*, result_id, decision_id, observed_at, kind, target, status):
    """Freeze a reported result; success is neither delivery nor human action."""
    if kind == "publication":
        valid = target in PUBLICATION_TARGETS and status in PUBLICATION_STATES
    elif kind == "notification":
        valid = target == "deep_cycle_dm" and status in NOTIFICATION_STATES
    else:
        valid = False
    if not valid:
        raise ValueError("unknown result kind, target or status")
    return _encode({
        "schema_version": 1, "record_type": "advisory_result",
        "result_id": _id(result_id), "decision_id": _id(decision_id),
        "observed_at": _stamp(observed_at), "kind": kind,
        "target": target, "status": status,
    })
