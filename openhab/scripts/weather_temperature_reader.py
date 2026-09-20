"""Strict, pure as-of selection from whole temperature evidence snapshots.

No fetch, learned-state update or fallback to legacy temperature history. The
adapter must supply the complete queried window plus its original carry row.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from uuid import UUID

from weather_temperature_evidence import MODELS, TemperaturePolicy

FIELDS = {'version', 'streamEpoch', 'recordedAt', 'model', 'sensorId', 'field',
          'status', 'reason', 'receivedAt', 'validUntil', 'temperatureF'}


def _utc(value):
    if isinstance(value, str): value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return value.astimezone(timezone.utc)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate key')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('nonfinite JSON')


def _snapshot(raw, stored_at, stream, policy):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 8192:
        raise ValueError('bounded raw snapshot required')
    envelope = json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant)
    if not isinstance(envelope, dict) or set(envelope) != {'version', 'streamEpoch', 'records'}:
        raise ValueError('closed envelope required')
    if type(envelope['version']) is not int or envelope['version'] != 1:
        raise ValueError('unsupported envelope')
    epoch = envelope['streamEpoch']
    if not isinstance(epoch, str) or str(UUID(epoch)) != epoch:
        raise ValueError('invalid epoch')
    records = envelope['records']
    if not isinstance(records, dict) or not 1 <= len(records) <= 3 or any(
        not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) for name in records):
        raise ValueError('invalid stream registry')
    record = records.get(stream)
    if record is None: return epoch, None
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError('closed temperature record required')
    if type(record['version']) is not int or record['version'] != 1 or record['streamEpoch'] != epoch:
        raise ValueError('record version/epoch mismatch')
    if record['model'] != policy.model or type(record['sensorId']) is not int or record['sensorId'] != policy.sensor_id or record['field'] != MODELS[policy.model][1]:
        raise ValueError('record identity mismatch')
    recorded = _utc(record['recordedAt'])
    if recorded > stored_at: raise ValueError('future source record')
    if record['status'] != 'valid': return epoch, None
    received, expires = _utc(record['receivedAt']), _utc(record['validUntil'])
    value = record['temperatureF']
    if record['reason'] != 'accepted' or received != recorded or type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('invalid accepted receipt')
    if not policy.minimum_f <= value <= policy.maximum_f or not 0 < (expires - received).total_seconds() <= policy.validity_seconds:
        raise ValueError('receipt outside selected policy')
    return epoch, {'temperatureF': value, 'receivedAt': received, 'validUntil': expires,
                   'storedAt': stored_at, 'streamEpoch': epoch,
                   'snapshotSha256': hashlib.sha256(raw.encode('utf-8')).hexdigest()}


def select_temperature_at(rows, *, target, assessed_at, history_start, stream, policy):
    """Return qualified metadata or None; never use a post-target snapshot.

    rows are ordered (original persistence datetime, raw JSON string) pairs.
    history_start attests the adapter's complete query begins at least one policy
    validity interval before target. Preserve carry timestamps; do not relabel
    them to the query boundary. Latest invalid/malformed/unknown snapshots are
    barriers, not candidates to skip while looking for an older valid value.
    """
    try:
        return select_temperature_grid(rows, targets=[target], assessed_at=assessed_at,
            history_start=history_start, stream=stream, policy=policy)[0][1]
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None


def select_temperature_grid(rows, *, targets, assessed_at, history_start, stream, policy):
    """Select at most 289 increasing targets over one elapsed day in one pass.

    Returns (target, qualified metadata or None) pairs, not fabricated sensor
    observations. Invalid history ordering or query contracts refuse the entire
    batch. Invalid snapshots remain barriers until a genuinely newer receipt.
    The complete history and original carry must be supplied from at least one
    validity interval before the first target. No numeric-history fallback.
    """
    if not isinstance(policy, TemperaturePolicy) or not isinstance(stream, str):
        raise ValueError('explicit stream and policy required')
    if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= 289:
        raise ValueError('bounded target grid required')
    targets = [_utc(target) for target in targets]
    assessed_at, start = _utc(assessed_at), _utc(history_start)
    if (targets[-1] > assessed_at or targets[-1] - targets[0] > timedelta(days=1)
            or start > targets[0] - timedelta(seconds=policy.validity_seconds)
            or any(left >= right for left, right in zip(targets, targets[1:]))):
        raise ValueError('invalid target window')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('bounded history required')
    normalized = []
    previous_at = None; previous_raw = None
    for stored, raw in rows:
        stored = _utc(stored)
        if previous_at is not None and (stored < previous_at or (stored == previous_at and raw != previous_raw)):
            raise ValueError('unordered or conflicting history')
        previous_at, previous_raw = stored, raw
        normalized.append((stored, raw))
    selected = None; barrier_at = None; epoch = None; index = 0; results = []
    for target in targets:
        while index < len(normalized) and normalized[index][0] <= target:
            stored, raw = normalized[index]
            index += 1
            try:
                next_epoch, candidate = _snapshot(raw, stored, stream, policy)
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                candidate = None; next_epoch = None
            if candidate is not None and selected is not None and next_epoch == epoch:
                earlier = candidate['receivedAt'] < selected['receivedAt']
                conflicting = candidate['receivedAt'] == selected['receivedAt'] and any(
                    candidate[key] != selected[key] for key in ('temperatureF', 'validUntil'))
                if earlier or conflicting:
                    candidate = None
            if epoch is not None and next_epoch != epoch:
                # A new epoch needs its own received observation after the most
                # recent old-epoch snapshot, not a copied/restored value.
                if selected is not None: barrier_at = selected['storedAt']
            epoch = next_epoch
            if candidate is None:
                barrier_at = stored
            elif barrier_at is not None and candidate['receivedAt'] <= barrier_at:
                candidate = None
                barrier_at = stored
            selected = candidate
        qualified = selected if selected is not None and selected['receivedAt'] <= target < selected['validUntil'] else None
        results.append((target, None if qualified is None else dict(qualified)))
    return results
