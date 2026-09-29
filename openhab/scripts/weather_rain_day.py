"""Conservative daily rain totals from original, source-bound counter receipts.

This is a pure reader. It does not fetch JDBC rows or alter forecast learning.
A caller must provide the last pre-day carry and original persisted snapshots
through a post-day counter receipt in one bounded, stable query.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from itertools import islice
import json
import math
from uuid import UUID
from zoneinfo import ZoneInfo

from weather_rain_evidence import RainPolicy


MAX_ROWS = 4000
MAX_BYTES = 4096
BOUNDARY_UNCERTAINTY_IN = 0.02


class RainDayRefused(ValueError):
    """The supplied evidence cannot prove a complete daily total."""


@dataclass(frozen=True)
class RainSample:
    persisted_at: datetime
    received_at: datetime
    valid_until: datetime
    epoch: str
    counter_in: float
    packet_count: int
    invalid_packets: int
    counter_drops: int
    counter_jumps: int


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise RainDayRefused('aware timestamp required')
    return value.astimezone(timezone.utc)


def _instant(value):
    if not isinstance(value, str):
        raise RainDayRefused('ISO timestamp required')
    try:
        return _utc(datetime.fromisoformat(value))
    except ValueError as exc:
        raise RainDayRefused('invalid ISO timestamp') from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RainDayRefused('duplicate JSON key')
        result[key] = value
    return result


def parse_rain_snapshot(raw, persisted_at, policy):
    """Validate one exact v1 snapshot without silently discarding bad rows."""
    persisted = _utc(persisted_at)
    if not isinstance(policy, RainPolicy):
        raise RainDayRefused('explicit rain policy required')
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
        raise RainDayRefused('missing or oversized rain snapshot')
    try:
        envelope = json.loads(raw, object_pairs_hook=_unique,
                              parse_constant=lambda _v: (_ for _ in ()).throw(
                                  RainDayRefused('nonfinite JSON value')))
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise RainDayRefused('invalid rain snapshot JSON') from exc
    keys = {'version', 'streamEpoch', 'record', 'packetCount',
            'invalidPackets', 'counterDrops', 'counterJumps'}
    if (not isinstance(envelope, dict) or set(envelope) != keys
            or type(envelope['version']) is not int or envelope['version'] != 1):
        raise RainDayRefused('invalid rain snapshot envelope')
    epoch = envelope['streamEpoch']
    try:
        if type(epoch) is not str or str(UUID(epoch)) != epoch:
            raise ValueError('noncanonical epoch')
    except ValueError as exc:
        raise RainDayRefused('invalid rain stream epoch') from exc
    counts = []
    for name in ('packetCount', 'invalidPackets', 'counterDrops', 'counterJumps'):
        value = envelope[name]
        if type(value) is not int or not 0 <= value <= 2**53 - 1:
            raise RainDayRefused('invalid rain fault count')
        counts.append(value)
    if counts[0] == 0 or any(value > counts[0] for value in counts[1:]):
        raise RainDayRefused('inconsistent rain packet counts')
    record = envelope['record']
    record_keys = {'version', 'streamEpoch', 'recordedAt', 'model', 'sensorId',
                   'field', 'status', 'reason', 'receivedAt', 'validUntil',
                   'totalRainIn'}
    if not isinstance(record, dict) or set(record) != record_keys:
        raise RainDayRefused('missing or malformed rain record')
    if (type(record['version']) is not int or record['version'] != 1
            or record['streamEpoch'] != epoch
            or record['model'] != 'Fineoffset-WH65B'
            or type(record['sensorId']) is not int
            or record['sensorId'] != policy.sensor_id
            or record['field'] != 'totalrainin'
            or record['status'] != 'valid' or record['reason'] != 'accepted'):
        raise RainDayRefused('invalid or unavailable rain observation')
    recorded = _instant(record['recordedAt'])
    received = _instant(record['receivedAt'])
    until = _instant(record['validUntil'])
    counter = record['totalRainIn']
    if (recorded != received or not received <= persisted < until
            or until != received + timedelta(seconds=policy.validity_seconds)
            or type(counter) not in (int, float) or not math.isfinite(counter)
            or not 0 <= counter <= policy.maximum_counter_in):
        raise RainDayRefused('rain observation time or value invalid')
    return RainSample(persisted, received, until, epoch, float(counter), *counts)


def qualify_rain_day(local_date, *, as_of, observations, policy,
                     site_timezone='America/Denver'):
    """Return a bounded source-qualified counter difference or refuse it.

    The returned midpoint differs from the source-reported daily cumulative
    counter difference by at most half of ``uncertainty_in`` if that counter
    was monotone. It cannot prove gauge calibration or physical rainfall.
    Any observed gap, invalid packet, drop, jump, restart or broad midnight
    bracket refuses the day. No numeric Item fallback is permitted.
    """
    if not isinstance(local_date, date) or isinstance(local_date, datetime):
        raise RainDayRefused('local date required')
    if not isinstance(policy, RainPolicy):
        raise RainDayRefused('explicit rain policy required')
    zone = ZoneInfo(site_timezone)
    start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    assessed_at = _utc(as_of)
    if assessed_at < end:
        raise RainDayRefused('rain day incomplete')
    rows = tuple(islice(observations, MAX_ROWS + 1))
    if not rows or len(rows) > MAX_ROWS:
        raise RainDayRefused('rain evidence absent or row bound exceeded')
    samples = []
    previous = None
    fetch_start = start - timedelta(seconds=policy.validity_seconds)
    fetch_end = end + timedelta(seconds=policy.validity_seconds)
    for persisted_at, raw in rows:
        sample = parse_rain_snapshot(raw, persisted_at, policy)
        if (not fetch_start <= sample.persisted_at <= fetch_end
                or sample.persisted_at > assessed_at):
            raise RainDayRefused('rain row outside bounded window')
        if previous is not None:
            if (sample.persisted_at <= previous.persisted_at
                    or sample.received_at <= previous.received_at):
                raise RainDayRefused('rain row or source time replay')
            if sample.epoch != previous.epoch:
                raise RainDayRefused('rain receiver restarted during day')
            if (sample.packet_count <= previous.packet_count
                    or sample.invalid_packets != previous.invalid_packets
                    or sample.counter_drops != previous.counter_drops
                    or sample.counter_jumps != previous.counter_jumps):
                raise RainDayRefused('rain source fault or packet replay')
            if sample.counter_in < previous.counter_in:
                raise RainDayRefused('rain counter regressed')
        samples.append(sample)
        previous = sample
    before_start = [s for s in samples if s.received_at <= start]
    after_start = [s for s in samples if s.received_at >= start]
    before_end = [s for s in samples if s.received_at <= end]
    after_end = [s for s in samples if s.received_at >= end]
    if not all((before_start, after_start, before_end, after_end)):
        raise RainDayRefused('rain counter boundary bracket missing')
    start_pre, start_post = before_start[-1], after_start[0]
    end_pre, end_post = before_end[-1], after_end[0]
    if (start_pre.valid_until <= start or end_pre.valid_until < end
            or start_post.received_at - start > timedelta(seconds=policy.validity_seconds)
            or end_post.received_at - end > timedelta(seconds=policy.validity_seconds)):
        raise RainDayRefused('rain midnight bracket stale')
    coverage_end = start_pre.valid_until
    for sample in samples:
        if sample.received_at <= start or sample.received_at >= end:
            continue
        if sample.received_at >= coverage_end:
            raise RainDayRefused('rain source coverage gap')
        coverage_end = max(coverage_end, sample.valid_until)
    if coverage_end < end:
        raise RainDayRefused('rain source does not cover day end')
    lower = end_pre.counter_in - start_post.counter_in
    upper = end_post.counter_in - start_pre.counter_in
    if lower < 0 or upper < lower:
        raise RainDayRefused('rain counter boundary order invalid')
    uncertainty = upper - lower
    if uncertainty > BOUNDARY_UNCERTAINTY_IN + 1e-9:
        raise RainDayRefused('rain boundary uncertainty too large')
    return {
        'basis': 'source_bound_counter_bracket_v1',
        'local_date': local_date.isoformat(),
        'rain_in': round((lower + upper) / 2, 4),
        'uncertainty_in': round(uncertainty, 4),
        'receipt_count': len(samples),
        'stream_epoch': samples[0].epoch,
    }
