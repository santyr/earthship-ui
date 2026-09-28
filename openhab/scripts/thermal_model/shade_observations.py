"""Source-only Dooya motor-report intervals; no listener, learning or actuation.

Rows are one shade's OpenHAB diagnostic, availability and scalar position
histories. A future JDBC reader must prove source coverage and correct Item IDs.
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
CHANGE_KEYS = frozenset(('stored_at', 'state'))


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


def join_change_only_shade_rows(diagnostics, availability, positions, *, start, end):
    """Join three bounded Item histories as known at each persistence timestamp.

    Each stream supplies at most one last pre-window carry row and changes before
    end. Unknown values stay unknown. Cross-Item timestamp ties are barriers:
    separate Item writes cannot be assumed atomic merely because their stored
    timestamps have the same resolution. No transition is backdated.
    """
    start, end = _utc(start), _utc(end)
    if not start < end or end - start > MAX_WINDOW:
        raise ValueError('bounded shade window required')
    events = []
    for name, stream in (('diagnostic_state', diagnostics),
                         ('availability', availability),
                         ('scalar_position', positions)):
        previous = None
        carries = 0
        for row in stream:
            if not isinstance(row, dict) or set(row) != CHANGE_KEYS:
                raise ValueError('closed shade change row required')
            at = _utc(row['stored_at'])
            if previous is not None and at <= previous:
                raise ValueError('shade Item history must be strictly ordered')
            if at >= end:
                raise ValueError('future shade Item history row')
            if at < start:
                carries += 1
                if carries > 1:
                    raise ValueError('one pre-window carry per shade Item required')
            previous = at
            events.append((at, name, row['state']))
            if len(events) > MAX_ROWS:
                raise ValueError('shade row bound exceeded')
    events.sort(key=lambda event: event[0])
    states = dict.fromkeys(('diagnostic_state', 'availability', 'scalar_position'))
    needs_diagnostic = True
    joined = []
    index = 0
    while index < len(events):
        at = events[index][0]
        changed = set()
        prior_availability = states['availability']
        while index < len(events) and events[index][0] == at:
            _, name, value = events[index]
            states[name] = value
            changed.add(name)
            index += 1
        if (len(changed) > 1 or states['availability'] != 'ON'
                or ('availability' in changed and prior_availability != 'ON')):
            needs_diagnostic = True
        elif changed == {'diagnostic_state'}:
            needs_diagnostic = False
        joined.append(dict(stored_at=at, diagnostic_state=states['diagnostic_state'],
                           availability=states['availability'] == 'ON' and not needs_diagnostic,
                           scalar_position=states['scalar_position']))
    return tuple(joined)


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
