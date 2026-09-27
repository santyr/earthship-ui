"""Source-only Dooya motor-report intervals; no listener, learning or actuation.

Rows are one shade's already-joined OpenHAB diagnostic, availability and scalar
position history. A future reader must prove that join and persistence coverage.
This module never substitutes bridge cache or command acknowledgements for a
motor Report, and never extends an old report with periodic re-publication.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import islice
import json
import math


MAX_ROWS = 10000
MAX_WINDOW = timedelta(days=2)
MAX_REPORT_AGE = timedelta(minutes=30)
CLOCK_SKEW = timedelta(seconds=60)
ROW_KEYS = frozenset(('stored_at', 'diagnostic_state', 'availability', 'scalar_position'))


@dataclass(frozen=True)
class ShadeInterval:
    start: datetime
    end: datetime
    percent_closed: int
    percent_open: int
    report_received_at: datetime
    stored_at: datetime


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware shade timestamp required')
    return value.astimezone(timezone.utc)


def _position(value):
    if type(value) is int and 0 <= value <= 100:
        return value
    if isinstance(value, str) and 1 <= len(value) <= 3 and value.isascii() and value.isdecimal():
        number = int(value)
        if str(number) == value and number <= 100:
            return number
    return None


def _motor_report(row, stored_at):
    if row['availability'] is not True or not isinstance(row['diagnostic_state'], str):
        return None
    raw = row['diagnostic_state']
    if len(raw) > 8192:
        return None
    try:
        size = len(raw.encode('utf-8'))
    except UnicodeEncodeError:
        return None
    if size > 8192:
        return None
    try:
        state = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if (not isinstance(state, dict) or type(state.get('schema_version')) is not int
            or state['schema_version'] != 1 or state.get('source') != 'motor_report'
            or state.get('stale') is not False):
        return None
    position = state.get('reported_position')
    timestamp = state.get('report_received_at')
    if (type(position) is not int or not 0 <= position <= 100
            or type(timestamp) not in (int, float) or not math.isfinite(timestamp)
            or _position(row['scalar_position']) != position):
        return None
    try:
        received_at = datetime.fromtimestamp(timestamp, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    if not -CLOCK_SKEW <= stored_at - received_at <= MAX_REPORT_AGE:
        return None
    return received_at, position


def qualified_shade_intervals(rows, *, start, end):
    """Return covered percent-open intervals for one shade, as known by end.

    Rows must be strictly ordered by persistence time and include a bounded
    pre-window carry row when one exists. Invalid/offline rows are barriers.
    Historical transitions become knowable no earlier than persistence time.
    """
    start, end = _utc(start), _utc(end)
    if not start < end or end - start > MAX_WINDOW:
        raise ValueError('bounded shade window required')
    rows = tuple(islice(rows, MAX_ROWS + 1))
    if len(rows) > MAX_ROWS:
        raise ValueError('shade row bound exceeded')
    intervals = []
    previous_at = None
    last_report = None
    current = None

    def close(until):
        if current is None:
            return
        received, position, stored = current
        low = max(start, stored, received)
        high = min(end, until, received + MAX_REPORT_AGE)
        if low < high:
            intervals.append(ShadeInterval(low, high, position, 100 - position,
                                           received, stored))

    for row in rows:
        if not isinstance(row, dict) or set(row) != ROW_KEYS:
            raise ValueError('closed shade history row required')
        stored = _utc(row['stored_at'])
        if previous_at is not None and stored <= previous_at:
            raise ValueError('shade history must be strictly ordered')
        previous_at = stored
        if stored >= end:
            continue  # A later correction cannot rewrite an earlier origin.
        parsed = _motor_report(row, stored)
        if parsed is not None and last_report is not None:
            if parsed == last_report and current is not None:
                continue  # Periodic re-publication does not extend receipt age.
            if parsed[0] <= last_report[0]:
                parsed = None  # Out-of-order or old-after-barrier receipt.
        close(stored)
        current = None if parsed is None else (parsed[0], parsed[1], stored)
        if parsed is not None:
            last_report = parsed
    close(end)
    return tuple(intervals)
