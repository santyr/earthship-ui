"""Pure source-bound charge-day/trough diagnostics; never correct a forecast."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import islice
import json
from zoneinfo import ZoneInfo

from advisory_windows import trough_window
from earthship_energy.bms_evidence import build_soc_intervals, soc_at
from earthship_energy.trough_assessment import assess_trough_measurement, MAX_OBSERVATIONS


def _utc(at):
    if not isinstance(at, datetime) or at.utcoffset() is None:
        raise ValueError('aware diagnostic timestamp required')
    return at.astimezone(timezone.utc)


def measure(*, day, sunset, sunset_persisted_at, as_of, observations,
            epoch_start, epoch_end=None, timezone_name='America/Denver'):
    """Require the original sunset and completed atomic coverage at the origin.

    The target minimum remains the existing 20:00–11:00 canonical trough.
    Refuse if extending/shifting its start to sunset would change that minimum.
    Missing start, ambiguous ordering or a future receipt is not repaired.
    """
    sunset, persisted, as_of, epoch_start = map(_utc,
        (sunset, sunset_persisted_at, as_of, epoch_start))
    epoch_end = _utc(epoch_end) if epoch_end is not None else None
    target = trough_window(day, timezone_name)
    if (sunset.astimezone(ZoneInfo(timezone_name)).date() != day
            or not persisted <= sunset < target.end <= as_of
            or epoch_start > min(sunset, target.start)
            or (epoch_end is not None and epoch_end < target.end)):
        return None
    rows = tuple(islice(observations, MAX_OBSERVATIONS + 1))
    if (len(rows) > MAX_OBSERVATIONS or any(
            not isinstance(at, datetime) or at.utcoffset() is None or at > as_of
            or not isinstance(raw, str) or len(raw) > 4096 for at, raw in rows)):
        return None
    canonical = assess_trough_measurement(
        prediction_day=day, site_timezone=timezone_name, assessed_at=as_of,
        observations=rows, epoch_start=epoch_start, epoch_end=epoch_end)
    if canonical['status'] != 'measured':
        return None
    try:
        intervals = build_soc_intervals(rows, sunset, target.end,
            epoch_start=epoch_start, epoch_end=epoch_end)
        start_soc = soc_at(intervals, sunset)
        covered = sum((part.end-part.start).total_seconds() for part in intervals)
        coverage = covered/(target.end-sunset).total_seconds()
        minimum = min((part.soc for part in intervals), default=None)
    except ValueError:
        return None
    if start_soc is None or coverage < 0.9 or minimum != canonical['min_soc_pct']:
        return None
    binding = {'version': 'sunset-soc-profile-v1', 'sunset': sunset.isoformat(),
        'sunset_persisted_at': persisted.isoformat(),
        'canonical_evidence_digest': canonical['evidence_digest'],
        'epoch_start': epoch_start.isoformat(),
        'epoch_end': epoch_end.isoformat() if epoch_end else None}
    return {'prediction_day': day.isoformat(), 'sunset_at': sunset.isoformat(),
        'sunset_persisted_at': persisted.isoformat(), 'as_of': as_of.isoformat(),
        'sunset_soc_pct': start_soc, 'trough_soc_pct': minimum,
        'drop_pct': start_soc-minimum, 'coverage': coverage,
        'canonical_coverage': canonical['coverage'],
        'evidence_digest': sha256(json.dumps(binding, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()}


def charge_profile(*, day, origin, sunset, sunset_persisted_at, as_of,
                   observations, epoch_start, epoch_end=None,
                   timezone_name='America/Denver'):
    """Qualified first *reported* 100% and post-full decline through sunset.

    A no-full report is right-censored at sunset, not a fabricated charge time
    or proof that a physical full-charge event could not occur between polls.
    Already full at the origin is left-censored, not a new charging outcome.
    """
    origin, sunset, persisted, as_of, epoch_start = map(_utc,
        (origin, sunset, sunset_persisted_at, as_of, epoch_start))
    epoch_end = _utc(epoch_end) if epoch_end is not None else None
    zone = ZoneInfo(timezone_name)
    if (origin.astimezone(zone).date() != day or sunset.astimezone(zone).date() != day
            or not persisted <= origin < sunset <= as_of or epoch_start > origin
            or (epoch_end is not None and epoch_end <= sunset)):
        return None
    rows = tuple(islice(observations, MAX_OBSERVATIONS+1))
    if len(rows) > MAX_OBSERVATIONS or any(_utc(at) > as_of
            or not isinstance(raw, str) or len(raw) > 4096 for at, raw in rows):
        return None
    try:
        intervals = build_soc_intervals(rows, origin, sunset+timedelta(microseconds=1),
            epoch_start=epoch_start, epoch_end=epoch_end)
        start_soc, sunset_soc = soc_at(intervals, origin), soc_at(intervals, sunset)
        covered = sum(max(0, (min(part.end, sunset)-part.start).total_seconds())
                      for part in intervals)
        coverage = covered/(sunset-origin).total_seconds()
    except ValueError:
        return None
    if start_soc is None or sunset_soc is None or coverage < .995:
        return None
    full = next((part for part in intervals if part.start <= sunset and part.soc == 100), None)
    status = ('already_full_at_origin' if start_soc == 100 else
              'reported_full' if full else 'no_full_report')
    binding = {'version':'charge-day-profile-v1', 'origin':origin.isoformat(),
        'sunset':sunset.isoformat(), 'sunset_persisted_at':persisted.isoformat(),
        'epoch_start':epoch_start.isoformat(), 'epoch_end':epoch_end.isoformat() if epoch_end else None,
        'rows':[(at.isoformat(), raw) for at, raw in rows]}
    return {'status':status, 'assessed_at':as_of.isoformat(),
        'soc_at_origin_pct':start_soc, 'sunset_soc_pct':sunset_soc,
        'first_reported_full_at':full.start.isoformat() if status == 'reported_full' else None,
        'elapsed_to_full_seconds':(full.start-origin).total_seconds() if status == 'reported_full' else None,
        'censor_at':(sunset.isoformat() if status == 'no_full_report' else
                     origin.isoformat() if status == 'already_full_at_origin' else None),
        'post_full_decline_pct':100-sunset_soc if full else None, 'coverage':coverage,
        'evidence_digest':sha256(json.dumps(binding, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()}
