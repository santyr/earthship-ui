"""Strict, read-only daily coverage from source-bound TP-Link switch receipts.

No Item state, Thing command, database privilege, or quality publication is
created by importing this module. Callers supply original ordered JDBC rows.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from itertools import islice
import json
from uuid import UUID
from zoneinfo import ZoneInfo


ITEM = 'TPLink_Switch_Evidence_JSON'
BASIS = 'tplink_hs103_switch_report_v1'
FIELDS = ('load.dishwasher_state', 'load.shurflo_pump_state')
UNAVAILABLE = {'source_unavailable', 'input_unavailable', 'invalid_input', 'input_stale'}
TTL = timedelta(seconds=90)
MAX_ROWS = 5000
MAX_BYTES = 4096


class SwitchEvidenceRefused(ValueError):
    """The supplied receipts cannot qualify a switch-state day."""


@dataclass(frozen=True)
class Field:
    status: str
    observed_at: datetime | None
    valid_until: datetime | None
    value: str | None


@dataclass(frozen=True)
class Receipt:
    epoch: str
    sequence: int
    recorded_at: datetime
    fields: dict[str, Field]


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise SwitchEvidenceRefused('timestamp must be aware')
    return value.astimezone(timezone.utc)


def _millis(value):
    if type(value) is not int or not 0 < value <= 2**53 - 1:
        raise SwitchEvidenceRefused('invalid millisecond timestamp')
    try:
        return (datetime.fromtimestamp(value // 1000, timezone.utc)
                + timedelta(milliseconds=value % 1000))
    except (OverflowError, OSError, ValueError) as exc:
        raise SwitchEvidenceRefused('invalid millisecond timestamp') from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SwitchEvidenceRefused('duplicate JSON key')
        result[key] = value
    return result


def parse_switch_receipt(raw, persisted_at):
    """Validate one exact v1 receipt; malformed rows are barriers, not skips."""
    persisted = _utc(persisted_at)
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
        raise SwitchEvidenceRefused('missing or oversized evidence row')
    try:
        body = json.loads(raw, object_pairs_hook=_unique)
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise SwitchEvidenceRefused('invalid evidence JSON') from exc
    if (not isinstance(body, dict) or set(body) != {
            'version', 'basis', 'streamEpoch', 'sequence', 'recordedAt', 'fields'}
            or type(body['version']) is not int or body['version'] != 1
            or body['basis'] != BASIS or not isinstance(body['fields'], dict)
            or set(body['fields']) != set(FIELDS)):
        raise SwitchEvidenceRefused('invalid evidence envelope')
    epoch = body['streamEpoch']
    try:
        if type(epoch) is not str or str(UUID(epoch)) != epoch:
            raise ValueError('noncanonical epoch')
    except ValueError as exc:
        raise SwitchEvidenceRefused('invalid stream epoch') from exc
    sequence = body['sequence']
    if type(sequence) is not int or not 0 < sequence <= 2**53 - 1:
        raise SwitchEvidenceRefused('invalid sequence')
    recorded = _millis(body['recordedAt'])
    if recorded > persisted:
        raise SwitchEvidenceRefused('receipt persisted before recording')
    fields = {}
    for name in FIELDS:
        field = body['fields'][name]
        if not isinstance(field, dict) or set(field) != {
                'status', 'reason', 'observedAt', 'validUntil', 'value'}:
            raise SwitchEvidenceRefused('invalid switch field')
        if field['status'] == 'unavailable':
            if field['reason'] not in UNAVAILABLE or any(
                    field[key] is not None for key in ('observedAt', 'validUntil', 'value')):
                raise SwitchEvidenceRefused('invalid unavailable switch field')
            fields[name] = Field('unavailable', None, None, None)
            continue
        if field['status'] != 'valid' or field['reason'] != 'ok':
            raise SwitchEvidenceRefused('invalid switch status')
        observed, until = _millis(field['observedAt']), _millis(field['validUntil'])
        if (not observed <= recorded < until or until != observed + TTL
                or type(field['value']) is not str or field['value'] not in {'ON', 'OFF'}):
            raise SwitchEvidenceRefused('invalid or expired switch observation')
        fields[name] = Field('valid', observed, until, field['value'])
    return Receipt(epoch, sequence, recorded, fields)


def _coverage(receipts, field, start, end):
    """Intersect each valid source span with the next persisted status barrier."""
    intervals = []
    unavailable_barriers = 0
    for index, receipt in enumerate(receipts):
        current = receipt.fields[field]
        next_at = receipts[index + 1].recorded_at if index + 1 < len(receipts) else end
        if current.status != 'valid':
            if start <= receipt.recorded_at < end:
                unavailable_barriers += 1
            continue
        left = max(start, current.observed_at)
        right = min(end, current.valid_until, next_at)
        if right > left:
            intervals.append((left, right, current.value))
    cursor = start
    covered = timedelta(0)
    on_time = timedelta(0)
    gaps = 0
    for left, right, value in intervals:
        left = max(left, cursor)
        if right <= left:
            continue
        if left > cursor:
            gaps += 1
        span = right - left
        covered += span
        if value == 'ON':
            on_time += span
        cursor = right
    if cursor < end:
        gaps += 1
    seconds = (end - start).total_seconds()
    coverage = covered.total_seconds() / seconds
    quality = ('ok' if gaps == 0 and unavailable_barriers == 0
               and covered == end - start else
               'partial' if coverage >= 0.5 else 'insufficient_data')
    return {
        'coverage': coverage,
        'covered_seconds': covered.total_seconds(),
        'observed_on_seconds': on_time.total_seconds(),
        'window_seconds': seconds,
        'gap_count': gaps,
        'unavailable_barriers': unavailable_barriers,
        'quality': quality,
    }


def qualify_switch_day(local_date, *, as_of, cutover, observations,
                       site_timezone='America/Denver'):
    """Assess an elapsed local day after activation, with a <=90s carry-in.

    ``observations`` are ordered (persisted_at, raw JSON) JDBC rows from
    [local midnight - TTL, next local midnight). Missing/ambiguous rows refuse
    the whole read rather than authorizing coverage from held Switch state.
    """
    if not isinstance(local_date, date) or isinstance(local_date, datetime):
        raise ValueError('local_date must be a date')
    zone = ZoneInfo(site_timezone)
    start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    if not _utc(cutover) <= start < end <= _utc(as_of):
        raise SwitchEvidenceRefused('switch day precedes cutover or is incomplete')
    rows = tuple(islice(observations, MAX_ROWS + 1))
    if len(rows) > MAX_ROWS or not rows:
        raise SwitchEvidenceRefused('missing or over-budget switch evidence')
    receipts = []
    previous_persisted = None
    for persisted_at, raw in rows:
        persisted = _utc(persisted_at)
        if (not start - TTL <= persisted < end
                or previous_persisted is not None and persisted <= previous_persisted):
            raise SwitchEvidenceRefused('evidence row order or boundary invalid')
        receipt = parse_switch_receipt(raw, persisted)
        if not start - TTL <= receipt.recorded_at < end:
            raise SwitchEvidenceRefused('receipt belongs to another day')
        if receipts:
            previous = receipts[-1]
            if receipt.recorded_at <= previous.recorded_at:
                raise SwitchEvidenceRefused('evidence clock regressed or conflicted')
            if receipt.epoch == previous.epoch:
                if receipt.sequence != previous.sequence + 1:
                    raise SwitchEvidenceRefused('evidence sequence gap or replay')
            elif receipt.sequence != 1 or any(
                    entry.status != 'unavailable' for entry in receipt.fields.values()):
                raise SwitchEvidenceRefused('unbarriered switch stream restart')
        receipts.append(receipt)
        previous_persisted = persisted
    if not any(start <= receipt.recorded_at < end for receipt in receipts):
        raise SwitchEvidenceRefused('no in-day switch receipt')
    return {
        'source_item': ITEM,
        'source_cutover': _utc(cutover).isoformat(),
        'local_date': local_date.isoformat(),
        'window_start': start.isoformat(),
        'window_end': end.isoformat(),
        'evidence_rows': len(receipts),
        'fields': {field: _coverage(receipts, field, start, end) for field in FIELDS},
    }
