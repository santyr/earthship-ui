"""Default-off candidate for a fully bracketed, rejected rain-counter spike.

This module has no production caller. It never turns a rejected counter into
rainfall: it admits only a prompt return to the identical accepted counter.
The original strict day reader remains the publication authority.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from weather_rain_day import (MAX_BYTES, MAX_ROWS, RainDayRefused,
                              parse_rain_snapshot, qualify_rain_day)
from weather_rain_evidence import RainPolicy


MAX_RECOVERED_JUMPS = 16


@dataclass(frozen=True)
class RejectedJump:
    persisted_at: datetime
    recorded_at: datetime
    epoch: str
    packet_count: int
    invalid_packets: int
    counter_drops: int
    counter_jumps: int


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RainDayRefused('duplicate rain JSON key')
        result[key] = value
    return result


def _object(raw):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
        raise RainDayRefused('missing or oversized rain snapshot')
    try:
        return json.loads(raw, object_pairs_hook=_unique,
                          parse_constant=lambda _v: (_ for _ in ()).throw(
                              RainDayRefused('nonfinite rain JSON value')))
    except (ValueError, TypeError, RecursionError) as exc:
        raise RainDayRefused('invalid rain snapshot JSON') from exc


def _time(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise RainDayRefused('aware rain timestamp required')
    return value.astimezone(timezone.utc)


def _instant(value):
    try:
        return _time(datetime.fromisoformat(value)) if isinstance(value, str) else None
    except ValueError as exc:
        raise RainDayRefused('invalid rain timestamp') from exc


def _rejected_jump(envelope, persisted_at, policy):
    """Parse the exact invalid receipt emitted by the guarded collector."""
    if not isinstance(envelope, dict) or set(envelope) != {
            'version', 'streamEpoch', 'record', 'packetCount',
            'invalidPackets', 'counterDrops', 'counterJumps'}:
        raise RainDayRefused('invalid rejected-jump envelope')
    epoch = envelope['streamEpoch']
    try:
        if type(epoch) is not str or str(UUID(epoch)) != epoch:
            raise ValueError('noncanonical epoch')
    except ValueError as exc:
        raise RainDayRefused('invalid rain stream epoch') from exc
    counts = [envelope[k] for k in ('packetCount', 'invalidPackets',
                                    'counterDrops', 'counterJumps')]
    if (type(envelope['version']) is not int or envelope['version'] != 1
            or any(type(v) is not int or not 0 <= v <= 2**53 - 1 for v in counts)
            or counts[0] == 0 or any(v > counts[0] for v in counts[1:])):
        raise RainDayRefused('invalid rejected-jump counters')
    record = envelope['record']
    if not isinstance(record, dict) or set(record) != {
            'version', 'streamEpoch', 'recordedAt', 'model', 'sensorId',
            'field', 'status', 'reason', 'receivedAt', 'validUntil',
            'totalRainIn'}:
        raise RainDayRefused('invalid rejected-jump record')
    at = _instant(record['recordedAt'])
    persisted = _time(persisted_at)
    if (type(record['version']) is not int or record['version'] != 1
            or record['streamEpoch'] != epoch
            or record['model'] != 'Fineoffset-WH65B'
            or type(record['sensorId']) is not int
            or record['sensorId'] != policy.sensor_id
            or record['field'] != 'totalrainin'
            or record['status'] != 'invalid'
            or record['reason'] != 'counter_jump'
            or any(record[k] is not None for k in (
                'receivedAt', 'validUntil', 'totalRainIn'))
            or at is None or not at <= persisted < at + timedelta(
                seconds=policy.validity_seconds)):
        raise RainDayRefused('unqualified rejected-jump record')
    return RejectedJump(persisted, at, epoch, *counts)


def _near_boundary(first, last, start, end, seconds):
    margin = timedelta(seconds=seconds)
    return any(first <= boundary + margin and last >= boundary - margin
               for boundary in (start, end))


def qualify_rain_day_recovery(local_date, *, as_of, observations, policy,
                              site_timezone='America/Denver'):
    """Candidate only: accept isolated, fully recovered counter-jump barriers.

    Hidden rejected jumps between polls and explicit invalid snapshots both
    require paired jump/invalid counts, an unchanged accepted counter, an
    unexpired preceding valid receipt and distance from either midnight.
    Every other fault and any unknown packet interval fails closed.
    """
    if not isinstance(local_date, date) or isinstance(local_date, datetime):
        raise RainDayRefused('local rain date required')
    if not isinstance(policy, RainPolicy):
        raise RainDayRefused('explicit rain policy required')
    zone = ZoneInfo(site_timezone)
    start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    assessed_at = _time(as_of)
    fetch_start = start - timedelta(seconds=policy.validity_seconds)
    fetch_end = end + timedelta(seconds=policy.validity_seconds)
    rows = []
    for row in observations:
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise RainDayRefused('rain row bound exceeded')
    if not rows:
        raise RainDayRefused('rain evidence absent')
    accepted = []
    prior = None
    prior_valid = None
    pending = None
    recovered = 0
    baseline = None
    for persisted_at, raw in rows:
        envelope = _object(raw)
        record = envelope.get('record') if isinstance(envelope, dict) else None
        if isinstance(record, dict) and record.get('status') == 'invalid':
            sample = _rejected_jump(envelope, persisted_at, policy)
        else:
            sample = parse_rain_snapshot(raw, persisted_at, policy)
        if not fetch_start <= sample.persisted_at <= fetch_end or sample.persisted_at > assessed_at:
            raise RainDayRefused('rain row outside bounded window')
        if prior is not None:
            if (sample.persisted_at <= prior.persisted_at
                    or sample.epoch != prior.epoch
                    or sample.packet_count <= prior.packet_count
                    or sample.counter_drops != prior.counter_drops):
                raise RainDayRefused('rain replay, restart or counter drop')
            jump_delta = sample.counter_jumps - prior.counter_jumps
            invalid_delta = sample.invalid_packets - prior.invalid_packets
            if jump_delta not in (0, 1) or invalid_delta != jump_delta:
                raise RainDayRefused('unpaired rain source fault')
        else:
            if isinstance(sample, RejectedJump):
                raise RainDayRefused('rejected jump without preceding valid carry')
            baseline = (sample.invalid_packets, sample.counter_jumps)
            jump_delta = 0
        if isinstance(sample, RejectedJump):
            if (pending is not None or prior_valid is None or jump_delta != 1
                    or not prior_valid.received_at < sample.recorded_at
                    < prior_valid.valid_until
                    or _near_boundary(prior_valid.received_at, sample.recorded_at,
                                      start, end, policy.validity_seconds)):
                raise RainDayRefused('rejected jump lacks safe bracket')
            pending = sample
        else:
            if pending is not None:
                if (jump_delta != 0 or sample.counter_in != prior_valid.counter_in
                        or not pending.recorded_at < sample.received_at
                        < prior_valid.valid_until
                        or _near_boundary(pending.recorded_at, sample.received_at,
                                          start, end, policy.validity_seconds)):
                    raise RainDayRefused('rejected jump did not recover')
                recovered += 1
                pending = None
            elif prior_valid is not None and jump_delta:
                if (sample.counter_in != prior_valid.counter_in
                        or sample.received_at >= prior_valid.valid_until
                        or _near_boundary(prior_valid.received_at, sample.received_at,
                                          start, end, policy.validity_seconds)):
                    raise RainDayRefused('hidden jump lacks safe bracket')
                recovered += 1
            normalized = dict(envelope)
            normalized['invalidPackets'], normalized['counterJumps'] = baseline
            accepted.append((persisted_at, json.dumps(normalized)))
            prior_valid = sample
        if recovered > MAX_RECOVERED_JUMPS:
            raise RainDayRefused('too many rejected rain jumps')
        prior = sample
    if pending is not None:
        raise RainDayRefused('rejected jump lacks recovery')
    result = qualify_rain_day(local_date, as_of=as_of, observations=accepted,
                              policy=policy, site_timezone=site_timezone)
    return {**result, 'basis': 'source_bound_counter_recovered_jump_candidate_v2',
            'quarantined_jumps': recovered,
            'original_receipt_count': len(rows)}
