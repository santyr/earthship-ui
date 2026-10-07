"""Shared evidence accounting for Earthship forecast learning.

These helpers deliberately count independent calendar days or non-overlapping
forecast windows. Dense sensor rows are observations, not independent training
experiments. The functions are pure and never read or mutate OpenHAB state.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def _local_day(value, timezone_name):
    zone = ZoneInfo(timezone_name)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("evidence timestamp must be timezone-aware")
        return value.astimezone(zone).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            if len(value) == 10:
                return date.fromisoformat(value)
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("evidence date must be ISO-8601") from exc
        if parsed.utcoffset() is None:
            raise ValueError("evidence timestamp must include an offset")
        return parsed.astimezone(zone).date()
    raise ValueError("evidence origin must be a date, aware datetime, or ISO string")


def summarize_day_evidence(
    values,
    *,
    timezone_name="America/Denver",
    active_parameter_count=0,
    minimum_unique_days=None,
):
    """Return compact, reproducible support measured in unique local days."""
    if isinstance(active_parameter_count, bool) or not isinstance(active_parameter_count, int):
        raise ValueError("active_parameter_count must be an integer")
    if active_parameter_count < 0:
        raise ValueError("active_parameter_count must be nonnegative")
    if minimum_unique_days is not None:
        if isinstance(minimum_unique_days, bool) or not isinstance(minimum_unique_days, int):
            raise ValueError("minimum_unique_days must be an integer or None")
        if minimum_unique_days < 0:
            raise ValueError("minimum_unique_days must be nonnegative")

    origins = tuple(values)
    days = tuple(_local_day(value, timezone_name) for value in origins)
    unique = tuple(sorted(set(days)))
    unique_count = len(unique)
    return {
        "version": 1,
        "evidence_unit": "local_day",
        "reported_unit_count": len(days),
        "unique_unit_count": unique_count,
        "duplicate_unit_count": len(days) - unique_count,
        "first_unit": unique[0].isoformat() if unique else None,
        "last_unit": unique[-1].isoformat() if unique else None,
        "active_parameter_count": active_parameter_count,
        "units_per_active_parameter": (
            unique_count / active_parameter_count if active_parameter_count else None
        ),
        "minimum_unique_units": minimum_unique_days,
        "minimum_unique_units_met": (
            unique_count >= minimum_unique_days
            if minimum_unique_days is not None
            else None
        ),
    }


def summarize_nonoverlapping_origins(origins, horizon):
    """Greedily count independent forecast origins separated by one horizon."""
    if not isinstance(horizon, timedelta) or horizon <= timedelta(0):
        raise ValueError("horizon must be a positive timedelta")
    ordered = []
    for value in origins:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("forecast origins must be timezone-aware datetimes")
        ordered.append(value)
    ordered.sort()
    if len(set(ordered)) != len(ordered):
        raise ValueError("forecast origins must be unique")

    selected = []
    available_at = None
    for origin in ordered:
        if available_at is None or origin >= available_at:
            selected.append(origin)
            available_at = origin + horizon
    return {
        "version": 1,
        "evidence_unit": "nonoverlapping_forecast_window",
        "reported_origin_count": len(ordered),
        "independent_origin_count": len(selected),
        "horizon_seconds": int(horizon.total_seconds()),
        "first_origin": selected[0].isoformat() if selected else None,
        "last_origin": selected[-1].isoformat() if selected else None,
    }
