"""Shared evidence accounting for Earthship forecast learning.

These helpers deliberately count independent calendar days or non-overlapping
forecast windows. Dense sensor rows are observations, not independent training
experiments. The functions are pure and never read or mutate OpenHAB state.
"""

from datetime import date, datetime, timedelta, timezone
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
    ordered.sort(key=lambda origin: origin.astimezone(timezone.utc))
    instants = [origin.astimezone(timezone.utc) for origin in ordered]
    if len(set(instants)) != len(instants):
        raise ValueError("forecast origins must be unique")

    selected = []
    available_at = None
    for origin, instant in zip(ordered, instants):
        if available_at is None or instant >= available_at:
            selected.append(origin)
            available_at = instant + horizon
    return {
        "version": 1,
        "evidence_unit": "nonoverlapping_forecast_window",
        "reported_origin_count": len(ordered),
        "independent_origin_count": len(selected),
        "horizon_seconds": (int(horizon.total_seconds())
                            if horizon.total_seconds().is_integer()
                            else horizon.total_seconds()),
        "first_origin": selected[0].isoformat() if selected else None,
        "last_origin": selected[-1].isoformat() if selected else None,
    }


def summarize_soc_night_sources(sample_days, records, issue_origin):
    """Expose same-read measurement metadata; never claim model/release authority.

    Metadata digests identify the assessor inputs; this diagnostic does not
    replace original observations or perform prospective forecast scoring.
    """
    import math
    import re
    from advisory_windows import trough_window
    result = dict(model_kind='rolling_completed_night_heuristic', trained_model=False,
                  issue_origin=None, sample_dates=[], bank_epochs=[], source_coverage={},
                  source_evidence_digests={}, source_qualified_night_count=0,
                  provenance_basis='same_read_assessment_metadata', release_authority=False)
    try:
        origin = datetime.fromisoformat(issue_origin)
        if origin.utcoffset() is None or not isinstance(records, dict) or len(records)>4:
            return result
        dates = sorted(set(date.fromisoformat(day) for day in sample_days))
        if len(dates)>4:return result
    except (TypeError, ValueError):
        return result
    result['issue_origin'] = origin.isoformat()
    banks=set()
    for ending_day in dates:
        day=ending_day.isoformat();record=records.get(day)
        if not isinstance(record, dict) or set(record)!={'bank_epoch','assessment'}:continue
        bank=record['bank_epoch'];assessment=record['assessment']
        if not isinstance(bank,str) or not 1<=len(bank)<=128 or not isinstance(assessment,dict):continue
        if (assessment.get('assessment_version')!='atomic-soc-trough-v1' or
                assessment.get('status')!='measured' or assessment.get('source')!='BMS_SOC_Evidence_JSON' or
                assessment.get('prediction_day')!=(ending_day-timedelta(days=1)).isoformat()):continue
        coverage=assessment.get('coverage');minimum=assessment.get('min_soc_pct');digest=assessment.get('evidence_digest')
        if (type(coverage) not in (int,float) or not math.isfinite(coverage) or not .9<=coverage<=1 or
                type(minimum) not in (int,float) or not math.isfinite(minimum) or not 0<=minimum<=100 or
                not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None):continue
        try:
            assessed=datetime.fromisoformat(assessment['assessed_at'])
            window=trough_window(ending_day-timedelta(days=1),assessment['site_timezone'])
            if (assessed.utcoffset() is None or not window.end<=assessed<=origin or
                    assessment['window_start']!=window.start.isoformat() or assessment['window_end']!=window.end.isoformat()):continue
        except (KeyError,TypeError,ValueError):continue
        banks.add(bank);result['sample_dates'].append(day)
        result['source_coverage'][day]=coverage;result['source_evidence_digests'][day]=digest
    result['bank_epochs']=sorted(banks)
    result['source_qualified_night_count']=len(result['sample_dates'])
    return result
