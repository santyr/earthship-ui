"""Source-only v2 received-Report history, separate from the immutable v1 reader.

Eight independently persisted roles must reconcile; provider_status is an
observational Item containing the actual provider Thing's ONLINE/OFFLINE state.
It requires a prepared collector/Item at future installation, never an assumed
ONLINE value. No policy preference, model feature, training label, or motor
command participates. Receipt continuity does not certify physical measurement
age, actor, causal completion, or thermal/action qualification.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from itertools import islice
import hashlib
import json
import math
import re
import uuid

MAX_ROWS = 10000
MAX_WINDOW = timedelta(days=2)
MAX_REPORT_AGE = timedelta(minutes=30)
MAX_HEALTH_AGE = timedelta(seconds=90)
CLOCK_SKEW = timedelta(seconds=5)
MAX_VALUE_BYTES = 8192
ITEM_ROLES = ('diagnostic_state', 'availability', 'scalar_position',
              'service_availability', 'bridge_availability', 'service_state',
              'bridge_state', 'provider_status')
ROW_KEYS = frozenset(('stored_at', 'diagnostic_reconciled', *ITEM_ROLES))
CHANGE_KEYS = frozenset(('stored_at', 'state'))


@dataclass(frozen=True)
class ReportObservationV2:
    shade_id: str
    observation_id: str
    adapter_session_id: str
    source_generation: int
    bridge_id: str
    device_id: str
    commissioned_epoch: str
    source_identity_sha256: str
    commissioning_ref: str
    percent_closed: int
    percent_open: int
    received_at: datetime
    validated_at: datetime
    received_monotonic: float
    upstream_message_id: str
    known_at: datetime
    actor: str = 'unknown'
    measurement_time_known: bool = False
    hardware_boot_known: bool = False
    delayed_delivery_excluded: bool = False
    action_qualified: bool = False
    preference_qualified: bool = False
    schema: str = 'earthship-dooya-report-observation/v2'


@dataclass(frozen=True)
class ShadeReceivedIntervalV2:
    start: datetime
    end: datetime
    observation: ReportObservationV2
    original_receipt_usable_until: datetime
    qualification_scope: str = 'received_report_continuity_only'
    action_qualified: bool = False
    measurement_time_known: bool = False

    @property
    def percent_closed(self): return self.observation.percent_closed

    @property
    def percent_open(self): return self.observation.percent_open


@dataclass(frozen=True)
class ShadeHistoryV2:
    observations: tuple
    intervals: tuple
    schema: str = 'earthship-dooya-observation-history/v2'
    family: str = 'dooya_report_receipt'
    qualification_scope: str = 'received_report_continuity_only'
    action_qualified: bool = False
    preference_qualified: bool = False
    measurement_time_known: bool = False
    actor: str = 'unknown'


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware v2 shade timestamp required')
    return value.astimezone(timezone.utc)


def _window(start, end, as_of=None):
    start, end = _utc(start), _utc(end)
    if not start < end or end-start > MAX_WINDOW or (as_of is not None and end > _utc(as_of)):
        raise ValueError('bounded elapsed v2 shade window required')
    return start, end


def _text(value, maximum=128):
    return (type(value) is str and 0 < len(value) <= maximum
            and value.isascii() and all(ord(char) >= 32 for char in value))


def _uuid(value):
    try:
        return type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _number(value):
    return ((type(value) is int and -(2**53) < value < 2**53)
            or (type(value) is float and math.isfinite(value)))


def _timestamp(value):
    if not _number(value):
        raise ValueError('invalid v2 receipt time')
    try:
        return datetime.fromtimestamp(value, timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise ValueError('invalid v2 receipt time') from None


def _generation(value):
    return type(value) is int and 0 <= value < 2**53


def _position(value):
    if type(value) is int and 0 <= value <= 100:
        return value
    if type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]?|100)', value):
        return int(value)
    return None


def _message_time(value):
    if type(value) is not str or re.fullmatch(r'[0-9]{17}', value) is None:
        raise ValueError('unknown v2 report ordering')
    return datetime.strptime(value, '%Y%m%d%H%M%S%f')


def _unique(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise ValueError('duplicate diagnostic key')
        value[key] = child
    return value


def _json(raw):
    if type(raw) is not str or len(raw) > MAX_VALUE_BYTES:
        raise ValueError('invalid v2 diagnostic')
    try:
        if len(raw.encode('utf-8')) > MAX_VALUE_BYTES:
            raise ValueError()
        value = json.loads(raw, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(value) is not dict:
            raise ValueError()
        stack = [(value, 0)]
        count = 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if depth > 16 or count > 1024:
                raise ValueError()
            if type(node) is dict:
                stack.extend((child, depth+1) for child in node.values())
            elif type(node) is list:
                stack.extend((child, depth+1) for child in node)
            elif type(node) is float and not math.isfinite(node):
                raise ValueError()
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ValueError('invalid v2 diagnostic') from None


def validate_profile_v2(profile):
    required = {'schema', 'shade_id', 'bridge_id', 'device_id', 'commissioned_epoch',
                'source_identity_sha256', 'commissioning_ref'}
    if (type(profile) is not dict or set(profile) != required
            or profile['schema'] != 'earthship-dooya-observation-profile/v2'
            or not _text(profile['shade_id'], 64)
            or re.fullmatch(r'[A-Za-z0-9_-]+', profile['shade_id']) is None
            or not _text(profile['commissioning_ref'])
            or not _uuid(profile['commissioned_epoch'])
            or any(type(profile[key]) is not str or re.fullmatch(r'[0-9A-F]{12,32}', profile[key]) is None
                   for key in ('bridge_id', 'device_id'))):
        raise ValueError('private commissioned v2 shade profile required')
    identity = {key: profile[key] for key in ('bridge_id', 'device_id', 'commissioned_epoch')}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=True).encode('ascii')).hexdigest()
    if profile['source_identity_sha256'] != digest:
        raise ValueError('commissioned v2 shade identity mismatch')
    return dict(profile)


def _same_session(first, second):
    return (_text(first.get('adapter_session_id')) and _text(second.get('adapter_session_id'))
            and first['adapter_session_id'] == second.get('adapter_session_id')
            and _generation(first.get('source_generation'))
            and _generation(second.get('source_generation'))
            and first['source_generation'] == second.get('source_generation'))


def _report(raw, stored, profile):
    value = _json(raw)
    original = value.get('observation')
    position = value.get('reported_position')
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 2
            or value.get('source') != 'motor_report' or type(position) is not int
            or not 0 <= position <= 100 or type(original) is not dict
            or not _text(original.get('adapter_session_id'))
            or not _generation(original.get('source_generation'))
            or original.get('device_type') != '10000000'
            or any(original.get(key) != profile[key] for key in
                   ('bridge_id', 'device_id', 'commissioned_epoch', 'source_identity_sha256'))
            or original.get('origin') != 'unknown'
            or original.get('measurement_time_known') is not False
            or original.get('hardware_boot_known') is not False
            or original.get('delayed_delivery_excluded') is not False
            or original.get('ordering_contract') != 'working_calendar_msg_id'
            or original.get('freshness_basis') != 'validated_unique_report_receipt'):
        raise ValueError('unqualified v2 original report')
    upstream = original.get('upstream_message_id')
    _message_time(upstream)  # This orders the working ID contract, never measurement time.
    identifier = f"{original['adapter_session_id']}:{original['source_generation']}:{upstream}"
    if original.get('id') != identifier:
        raise ValueError('v2 observation identity mismatch')
    received = _timestamp(original.get('received_at'))
    validated = _timestamp(original.get('validated_at'))
    if (value.get('report_received_at') != original['received_at']
            or type(value.get('report_received_at')) not in (int, float)
            or not _number(original.get('received_monotonic'))
            or original['received_monotonic'] < 0 or validated < received
            or received > stored+CLOCK_SKEW or validated > stored+CLOCK_SKEW):
        raise ValueError('v2 observation receipt mismatch')
    observation = ReportObservationV2(profile['shade_id'], identifier,
        original['adapter_session_id'], original['source_generation'], profile['bridge_id'],
        profile['device_id'], profile['commissioned_epoch'], profile['source_identity_sha256'],
        profile['commissioning_ref'], position, 100-position, received, validated, original['received_monotonic'], upstream, stored)
    interval = value.get('usable_interval')
    if (type(interval) is not dict or set(interval) != {'clock','start','end'}
            or interval['clock'] != 'adapter_monotonic'
            or not _number(interval['start']) or not _number(interval['end'])
            or interval['start'] != observation.received_monotonic
            or not interval['start'] < interval['end']):
        return observation, value, received
    duration = min(interval['end']-interval['start'], MAX_REPORT_AGE.total_seconds())
    return observation, value, received+timedelta(seconds=duration)


def _live(row):
    return (all(row[key] == 'ON' for key in
                ('availability', 'service_availability', 'bridge_availability'))
            and row['provider_status'] == 'ONLINE')


def _health(row, value, observation, stored, profile):
    service, bridge = _json(row['service_state']), _json(row['bridge_state'])
    if (any(type(part.get('schema_version')) is not int or part['schema_version'] != 2
            for part in (service,bridge))
            or not _same_session(service, bridge) or not _same_session(value, service)
            or not _same_session(value, {'adapter_session_id':observation.adapter_session_id,
                                         'source_generation':observation.source_generation})
            or service.get('ready') is not True or bridge.get('reachable') is not True
            or bridge.get('bridge_id') != profile['bridge_id']):
        raise ValueError('unreconciled v2 health')
    deadlines = []
    for part in (service,bridge):
        emitted = _timestamp(part.get('emitted_at'))
        if not -CLOCK_SKEW <= stored-emitted <= MAX_HEALTH_AGE:
            raise ValueError('expired v2 health')
        deadlines.append(emitted+MAX_HEALTH_AGE)
    return min(deadlines)


def join_change_only_shade_rows_v2(streams, *, start, end):
    start,end = _window(start,end)
    if type(streams) is not dict or set(streams) != set(ITEM_ROLES):
        raise ValueError('eight exact v2 shade history roles required')
    events = []
    for role in ITEM_ROLES:
        previous, carries = None, 0
        for row in streams[role]:
            if type(row) is not dict or set(row) != CHANGE_KEYS:
                raise ValueError('closed v2 shade change row required')
            at = _utc(row['stored_at'])
            if previous is not None and at <= previous:
                raise ValueError('v2 Item history must be strictly ordered')
            if at >= end:
                raise ValueError('future v2 Item history row')
            carries += int(at < start)
            if carries > 1:
                raise ValueError('one v2 pre-window carry per Item required')
            previous = at
            events.append((at,role,row['state']))
            if len(events) > MAX_ROWS:
                raise ValueError('v2 shade row bound exceeded')
    events.sort(key=lambda event:event[0])
    states, joined, needs_diagnostic = dict.fromkeys(ITEM_ROLES), [], True
    index = 0
    while index < len(events):
        at, changed = events[index][0], set()
        previously_live = _live(states)
        while index < len(events) and events[index][0] == at:
            _,role,raw = events[index]
            states[role] = raw
            changed.add(role)
            index += 1
        if len(changed)>1 or not _live(states) or not previously_live:
            needs_diagnostic = True
        elif changed == {'diagnostic_state'}:
            needs_diagnostic = False
        joined.append({'stored_at':at, **states, 'diagnostic_reconciled':not needs_diagnostic})
    return tuple(joined)


def qualified_shade_intervals_v2(rows, *, profile, start, end, as_of):
    """Retain individual positions and strictly local receipt-usable intervals.

    Independent writes cannot be backdated or treated as atomic. A duplicate
    after an outage/barrier cannot reopen coverage. Fresh health can maintain
    existing continuity, but never extends an original Report's usable interval.
    """
    start,end = _window(start,end,as_of)
    profile = validate_profile_v2(profile)
    rows = tuple(islice(rows,MAX_ROWS+1))
    if len(rows)>MAX_ROWS:
        raise ValueError('v2 shade row bound exceeded')
    originals, bounds, blocked, intervals = {}, {}, set(), []
    previous, latest_order, current = None, None, None

    def close(until):
        if current is None:
            return
        original, low, high = current
        high = min(end,until,high)
        if low < high:
            part = ShadeReceivedIntervalV2(low,high,original,bounds[original.observation_id])
            if (intervals and intervals[-1].end == part.start and intervals[-1].observation == original
                    and intervals[-1].original_receipt_usable_until == part.original_receipt_usable_until):
                intervals[-1] = replace(intervals[-1],end=part.end)
            else:
                intervals.append(part)

    for row in rows:
        if type(row) is not dict or set(row) != ROW_KEYS:
            raise ValueError('closed v2 joined shade row required')
        stored = _utc(row['stored_at'])
        if (previous is not None and stored <= previous) or stored >= end:
            raise ValueError('v2 shade history must be ordered and closed as-of')
        previous = stored
        if current is not None:
            close(stored)
            if stored > current[2]:
                blocked.add(current[0].observation_id)
        previous_current, current = current, None
        try:
            original,value,receipt_end = _report(row['diagnostic_state'],stored,profile)
            identifier = original.observation_id
            if identifier in originals:
                original = replace(original,known_at=originals[identifier].known_at)
                if original != originals[identifier]:
                    raise ValueError('conflicting duplicate v2 observation')
                bounds[identifier] = min(bounds[identifier],receipt_end)
            else:
                order = _message_time(original.upstream_message_id)
                if latest_order is not None and order <= latest_order:
                    raise ValueError('non-increasing v2 report order')
                latest_order = order
                originals[identifier], bounds[identifier] = original,receipt_end
            stationary = (value.get('usable') is True and value.get('stale') is False
                and value.get('action_qualified') is False and value.get('movement_state') == 'stationary_reported'
                and type(value.get('current_position')) is int
                and value['current_position'] == original.percent_closed)
            if not _live(row) or not stationary:
                blocked.add(identifier)
                raise ValueError('unusable v2 report')
            if row['diagnostic_reconciled'] is not True or _position(row['scalar_position']) != original.percent_closed:
                raise ValueError('unreconciled v2 scalar')
            health_end = _health(row,value,original,stored,profile)
            if identifier in blocked:
                raise ValueError('historical v2 observation after barrier')
            high = min(bounds[identifier],health_end)
            low = max(start,stored,original.received_at,original.validated_at)
            if low < min(end,high):
                current = (original,low,high)
        except (ValueError,TypeError,KeyError,OverflowError):
            if previous_current is not None:
                blocked.add(previous_current[0].observation_id)
    close(end)
    return ShadeHistoryV2(tuple(originals.values()),tuple(intervals))
