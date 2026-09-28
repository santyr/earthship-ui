"""Strict, read-only day totals from source-bound MPPT60 Wh receipts.

This module has no OpenHAB or database writer. A caller must independently
resolve the exact evidence Item/table and fetch original ordered JDBC rows.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
from itertools import islice
from uuid import UUID
from zoneinfo import ZoneInfo


FIELD = 'mppt60.pv_day_wh'
BASIS = 'mppt60_native_pv_day_wh'
TTL = timedelta(seconds=90)
MAX_ROWS = 5000
MAX_WH = 100000
MIN_COVERAGE = 0.995
UNAVAILABLE = {'source_unavailable', 'input_unavailable', 'invalid_input', 'input_stale'}


class PVDayRefused(ValueError):
    """A daily total cannot be qualified from the supplied evidence."""


@dataclass(frozen=True)
class PVReceipt:
    epoch: str
    sequence: int
    recorded_at: datetime
    status: str
    observed_at: datetime | None
    valid_until: datetime | None
    wh: int | None


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise PVDayRefused('timestamp must be aware')
    return value.astimezone(timezone.utc)


def _millis(value):
    if type(value) is not int or not 0 < value <= 2**53 - 1:
        raise PVDayRefused('invalid millisecond timestamp')
    try:
        return (datetime.fromtimestamp(value // 1000, timezone.utc)
                + timedelta(milliseconds=value % 1000))
    except (OverflowError, OSError, ValueError) as exc:
        raise PVDayRefused('invalid millisecond timestamp') from exc


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PVDayRefused('duplicate JSON key')
        result[key] = value
    return result


def parse_pv_receipt(raw, persisted_at):
    """Parse one exact v1 receipt; malformed rows are barriers, never skipped."""
    persisted = _utc(persisted_at)
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 4096:
        raise PVDayRefused('missing or oversized PV evidence row')
    try:
        value = json.loads(raw, object_pairs_hook=_unique)
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise PVDayRefused('invalid PV evidence JSON') from exc
    if (not isinstance(value, dict) or set(value) != {
            'version', 'basis', 'streamEpoch', 'sequence', 'recordedAt', 'fields'}
            or type(value['version']) is not int or value['version'] != 1
            or value['basis'] != BASIS or not isinstance(value['fields'], dict)
            or set(value['fields']) != {FIELD}):
        raise PVDayRefused('invalid PV evidence envelope')
    epoch = value['streamEpoch']
    try:
        if type(epoch) is not str or str(UUID(epoch)) != epoch:
            raise ValueError('noncanonical epoch')
    except ValueError as exc:
        raise PVDayRefused('invalid stream epoch') from exc
    sequence = value['sequence']
    if type(sequence) is not int or not 0 < sequence <= 2**53 - 1:
        raise PVDayRefused('invalid sequence')
    recorded = _millis(value['recordedAt'])
    if recorded > persisted:
        raise PVDayRefused('receipt persisted before recording')
    field = value['fields'][FIELD]
    if not isinstance(field, dict) or set(field) != {
            'status', 'reason', 'observedAt', 'validUntil', 'wh'}:
        raise PVDayRefused('invalid PV field')
    if field['status'] == 'unavailable':
        if field['reason'] not in UNAVAILABLE or any(
                field[key] is not None for key in ('observedAt', 'validUntil', 'wh')):
            raise PVDayRefused('invalid unavailable PV field')
        return PVReceipt(epoch, sequence, recorded, 'unavailable', None, None, None)
    if field['status'] != 'valid' or field['reason'] != 'ok':
        raise PVDayRefused('invalid PV field status')
    observed, until = _millis(field['observedAt']), _millis(field['validUntil'])
    wh = field['wh']
    if (not observed <= recorded < until or until != observed + TTL
            or type(wh) is not int or not 0 <= wh <= MAX_WH):
        raise PVDayRefused('invalid or expired PV counter observation')
    return PVReceipt(epoch, sequence, recorded, 'valid', observed, until, wh)


def qualify_pv_day(local_date, *, as_of, observations, site_timezone='America/Denver'):
    """Require a complete local day of original receipts and a terminal Wh poll.

    ``observations`` contains ordered (persisted_at, raw JSON) JDBC rows in
    [local midnight, next local midnight). A short midnight carry may precede
    the device's zero reset; one reset is allowed only in the first two minutes.
    A producer restart must begin a new epoch with an unavailable seq-1 barrier.
    """
    if not isinstance(local_date, date) or isinstance(local_date, datetime):
        raise ValueError('local_date must be a date')
    zone = ZoneInfo(site_timezone)
    start = datetime.combine(local_date, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    if _utc(as_of) < end:
        raise PVDayRefused('PV day is incomplete')
    rows = tuple(islice(observations, MAX_ROWS + 1))
    if len(rows) > MAX_ROWS:
        raise PVDayRefused('PV evidence row budget exceeded')
    if not rows:
        raise PVDayRefused('PV evidence absent')
    receipts = []
    previous_persisted = None
    for persisted_at, raw in rows:
        persisted = _utc(persisted_at)
        if not start <= persisted < end or (previous_persisted is not None
                                             and persisted <= previous_persisted):
            raise PVDayRefused('PV evidence row order or day boundary invalid')
        receipt = parse_pv_receipt(raw, persisted)
        if receipt.recorded_at < start or receipt.recorded_at >= end:
            raise PVDayRefused('PV receipt belongs to another day')
        if receipts:
            previous = receipts[-1]
            if receipt.recorded_at <= previous.recorded_at:
                raise PVDayRefused('PV receipt clock regressed or conflicted')
            if receipt.epoch == previous.epoch:
                if receipt.sequence != previous.sequence + 1:
                    raise PVDayRefused('PV evidence sequence gap or replay')
            elif receipt.sequence != 1 or receipt.status != 'unavailable':
                raise PVDayRefused('unbarriered PV stream restart')
        receipts.append(receipt)
        previous_persisted = persisted

    valid = [receipt for receipt in receipts if receipt.status == 'valid']
    if not valid:
        raise PVDayRefused('no valid PV counter observation')
    reset_at = None
    previous_wh = None
    for receipt in valid:
        if previous_wh is not None and receipt.wh < previous_wh:
            if (reset_at is not None or receipt.recorded_at > start + timedelta(minutes=2)
                    or receipt.wh > 100):
                raise PVDayRefused('PV daily counter decreased outside reset window')
            reset_at = receipt.recorded_at
        previous_wh = receipt.wh
    if reset_at is not None:
        valid = [receipt for receipt in valid if receipt.recorded_at >= reset_at]
    if (valid[0].recorded_at > start + timedelta(minutes=3)
            or valid[-1].recorded_at < end - timedelta(minutes=2)
            or valid[-1].valid_until < end):
        raise PVDayRefused('PV day lacks boundary observations')

    covered_until = start
    covered = timedelta(0)
    for index, receipt in enumerate(receipts):
        if receipt.status != 'valid' or (reset_at is not None
                                          and receipt.recorded_at < reset_at):
            continue
        left = max(start, receipt.observed_at, covered_until)
        right = min(end, receipt.valid_until)
        if index + 1 < len(receipts):
            right = min(right, receipts[index + 1].recorded_at)
        if right > left:
            covered += right - left
            covered_until = right
    coverage = covered / (end - start)
    if coverage < MIN_COVERAGE:
        raise PVDayRefused('PV source coverage below threshold')
    return {
        'local_date': local_date.isoformat(),
        'window_start': start.isoformat(), 'window_end': end.isoformat(),
        'basis': BASIS, 'pv_kwh': max(receipt.wh for receipt in valid) / 1000,
        'coverage': coverage, 'receipt_count': len(receipts),
    }
