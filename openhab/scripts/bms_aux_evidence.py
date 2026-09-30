"""Strict, non-actuating daily evidence from Discover BMS native channels.

Receipts are not inferred from change-only capacity or scaled temperature Item
history. Importing this module performs no I/O or quality publication.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from itertools import islice
import json
from uuid import UUID
from zoneinfo import ZoneInfo


ITEM = 'BMS_Aux_Evidence_JSON'
BASIS = 'discover_bms_190_native_aux_v1'
FIELDS = ('battery.remaining_ah', 'battery.temperature_raw')
UNAVAILABLE = {'source_unavailable', 'input_unavailable', 'invalid_input', 'input_stale'}
TTL = timedelta(seconds=120)
MAX_ROWS = 5000
MAX_BYTES = 4096
BOUNDS = {'battery.remaining_ah': (0, 450),
          'battery.temperature_raw': (23300, 33855)}


class BmsAuxEvidenceRefused(ValueError):
    """No BMS auxiliary quality may be inferred from these rows."""


@dataclass(frozen=True)
class Field:
    status: str
    observed_at: datetime | None
    valid_until: datetime | None
    value: int | None


@dataclass(frozen=True)
class Receipt:
    persisted_at: datetime
    epoch: str
    sequence: int
    recorded_at: datetime
    fields: dict[str, Field]


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise BmsAuxEvidenceRefused('aware timestamp required')
    return value.astimezone(timezone.utc)


def _millis(value):
    if type(value) is not int or not 0 < value <= 2**53 - 1:
        raise BmsAuxEvidenceRefused('invalid millisecond timestamp')
    try:
        return (datetime.fromtimestamp(value // 1000, timezone.utc)
                + timedelta(milliseconds=value % 1000))
    except (OverflowError, OSError, ValueError) as exc:
        raise BmsAuxEvidenceRefused('invalid millisecond timestamp') from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BmsAuxEvidenceRefused('duplicate JSON key')
        result[key] = value
    return result


def parse_bms_aux_receipt(raw, persisted_at):
    """Validate one exact v1 receipt; malformed rows are barriers, not skips."""
    persisted = _utc(persisted_at)
    if not isinstance(raw, str):
        raise BmsAuxEvidenceRefused('missing or oversized evidence row')
    try:
        encoded_size = len(raw.encode('utf-8'))
    except UnicodeEncodeError as exc:
        raise BmsAuxEvidenceRefused('invalid evidence text') from exc
    if encoded_size > MAX_BYTES:
        raise BmsAuxEvidenceRefused('missing or oversized evidence row')
    try:
        body = json.loads(raw, object_pairs_hook=_unique)
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise BmsAuxEvidenceRefused('invalid evidence JSON') from exc
    if (not isinstance(body, dict) or set(body) != {
            'version', 'basis', 'streamEpoch', 'sequence', 'recordedAt', 'fields'}
            or type(body['version']) is not int or body['version'] != 1
            or body['basis'] != BASIS or not isinstance(body['fields'], dict)
            or set(body['fields']) != set(FIELDS)):
        raise BmsAuxEvidenceRefused('invalid evidence envelope')
    epoch = body['streamEpoch']
    try:
        if type(epoch) is not str or str(UUID(epoch)) != epoch:
            raise ValueError('noncanonical epoch')
    except ValueError as exc:
        raise BmsAuxEvidenceRefused('invalid stream epoch') from exc
    sequence = body['sequence']
    if type(sequence) is not int or not 0 < sequence <= 2**53 - 1:
        raise BmsAuxEvidenceRefused('invalid sequence')
    recorded = _millis(body['recordedAt'])
    if recorded > persisted:
        raise BmsAuxEvidenceRefused('receipt persisted before recording')
    fields = {}
    for name in FIELDS:
        field = body['fields'][name]
        if not isinstance(field, dict) or set(field) != {
                'status', 'reason', 'observedAt', 'validUntil', 'value'}:
            raise BmsAuxEvidenceRefused('invalid auxiliary field')
        if field['status'] == 'unavailable':
            if type(field['reason']) is not str or field['reason'] not in UNAVAILABLE or any(
                    field[key] is not None for key in ('observedAt', 'validUntil', 'value')):
                raise BmsAuxEvidenceRefused('invalid unavailable field')
            fields[name] = Field('unavailable', None, None, None)
            continue
        if field['status'] != 'valid' or field['reason'] != 'ok':
            raise BmsAuxEvidenceRefused('invalid field status')
        observed, until = _millis(field['observedAt']), _millis(field['validUntil'])
        value = field['value']
        lower, upper = BOUNDS[name]
        if (not observed <= recorded < until or until != observed + TTL
                or type(value) is not int or not lower <= value <= upper):
            raise BmsAuxEvidenceRefused('invalid or expired auxiliary observation')
        fields[name] = Field('valid', observed, until, value)
    return Receipt(persisted, epoch, sequence, recorded, fields)


def validate_receipt_successor(previous, receipt):
    """Bind ordering to sequence and durable time, not clock precision alone.

    Two independent native updates may share a recording millisecond. Their
    source times/expiry remain unchanged; only an ordered, changed snapshot
    with fresh native evidence (or an unavailable barrier) can follow a tie.
    """
    if receipt.persisted_at <= previous.persisted_at:
        raise BmsAuxEvidenceRefused('evidence persistence order or replay')
    if receipt.recorded_at < previous.recorded_at:
        raise BmsAuxEvidenceRefused('evidence clock regressed or conflicted')
    if receipt.epoch == previous.epoch:
        if receipt.sequence != previous.sequence + 1:
            raise BmsAuxEvidenceRefused('evidence sequence gap or replay')
    elif receipt.sequence != 1 or any(
            entry.status != 'unavailable' for entry in receipt.fields.values()):
        raise BmsAuxEvidenceRefused('unbarriered auxiliary stream restart')
    if receipt.epoch == previous.epoch:
        for name in FIELDS:
            before, after = previous.fields[name], receipt.fields[name]
            if after.status != 'valid':
                continue
            if before.status == 'valid':
                if (after.observed_at < before.observed_at
                        or after.observed_at == before.observed_at and after != before):
                    raise BmsAuxEvidenceRefused('regressed or conflicting source observation')
            elif (after.observed_at < previous.recorded_at
                  or after.observed_at == previous.recorded_at
                  and receipt.recorded_at != previous.recorded_at):
                # A fault/restart barrier destroys the old measurement. ONLINE
                # and a later envelope alone cannot restore a pre-barrier value.
                # At a recording tie, the other channel can have published an
                # older unavailable state just before this new native event.
                raise BmsAuxEvidenceRefused('recovery requires post-barrier source observation')
    if receipt.recorded_at == previous.recorded_at:
        if receipt.epoch != previous.epoch or receipt.fields == previous.fields:
            raise BmsAuxEvidenceRefused('evidence clock regressed or conflicted')
        for name in FIELDS:
            before, after = previous.fields[name], receipt.fields[name]
            if after.status == 'valid' and after != before:
                if (after.observed_at != receipt.recorded_at
                        or before.status == 'valid' and after.observed_at <= before.observed_at):
                    raise BmsAuxEvidenceRefused('conflicting equal-time source observation')


def _coverage(receipts, field, start, end):
    """Intersect source validity, durable persistence and later barriers."""
    cursor = start
    covered = timedelta(0)
    gaps = 0
    unavailable_barriers = 0
    for index, receipt in enumerate(receipts):
        current = receipt.fields[field]
        if current.status != 'valid':
            if start <= receipt.persisted_at < end:
                unavailable_barriers += 1
            continue
        next_at = receipts[index + 1].persisted_at if index + 1 < len(receipts) else end
        left = max(start, receipt.persisted_at, current.observed_at, cursor)
        right = min(end, current.valid_until, next_at)
        if right <= left:
            continue
        if left > cursor:
            gaps += 1
        covered += right - left
        cursor = right
    if cursor < end:
        gaps += 1
    seconds = (end - start).total_seconds()
    coverage = covered.total_seconds() / seconds
    quality = ('ok' if gaps == 0 and unavailable_barriers == 0
               and covered == end - start else
               'partial' if coverage >= 0.5 else 'insufficient_data')
    return {'coverage': coverage, 'covered_seconds': covered.total_seconds(),
            'window_seconds': seconds, 'gap_count': gaps,
            'unavailable_barriers': unavailable_barriers, 'quality': quality}


def qualify_bms_aux_day(local_date, *, as_of, cutover, observations,
                        site_timezone='America/Denver'):
    """Assess a completed local day; never accept a pre-cutover or partial day."""
    if not isinstance(local_date, date) or isinstance(local_date, datetime):
        raise ValueError('local_date must be a date')
    zone = ZoneInfo(site_timezone)
    start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    cutover_at, as_of_at = _utc(cutover), _utc(as_of)
    if not cutover_at <= start < end <= as_of_at:
        raise BmsAuxEvidenceRefused('auxiliary day precedes cutover or is incomplete')
    rows = tuple(islice(observations, MAX_ROWS + 1))
    if len(rows) > MAX_ROWS or not rows:
        raise BmsAuxEvidenceRefused('missing or over-budget auxiliary evidence')
    receipts = []
    previous_persisted = None
    for persisted_at, raw in rows:
        persisted = _utc(persisted_at)
        if (not max(start - TTL, cutover_at) <= persisted < end
                or previous_persisted is not None and persisted <= previous_persisted):
            raise BmsAuxEvidenceRefused('evidence row order or boundary invalid')
        receipt = parse_bms_aux_receipt(raw, persisted)
        if not start - TTL <= receipt.recorded_at < end:
            raise BmsAuxEvidenceRefused('receipt belongs to another day')
        if receipts:
            validate_receipt_successor(receipts[-1], receipt)
        receipts.append(receipt)
        previous_persisted = persisted
    if not any(start <= receipt.persisted_at < end for receipt in receipts):
        raise BmsAuxEvidenceRefused('no in-day auxiliary receipt')
    return {'source_item': ITEM, 'source_cutover': cutover_at.isoformat(),
            'local_date': local_date.isoformat(), 'window_start': start.isoformat(),
            'window_end': end.isoformat(), 'evidence_rows': len(receipts),
            'fields': {field: _coverage(receipts, field, start, end) for field in FIELDS}}
