from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from weather_rain_day import RainDayRefused, parse_rain_snapshot, qualify_rain_day
from weather_rain_evidence import RainPolicy


POLICY = RainPolicy(sensor_id=206)
DAY = date(2026, 9, 29)
EPOCH = str(uuid4())


def bounds(day=DAY):
    zone = ZoneInfo('America/Denver')
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    return start, end


def snapshot(at, count, value, *, epoch=EPOCH, invalid=0, drops=0, jumps=0):
    record = {
        'version': 1, 'streamEpoch': epoch, 'recordedAt': at.isoformat(),
        'model': 'Fineoffset-WH65B', 'sensorId': 206, 'field': 'totalrainin',
        'status': 'valid', 'reason': 'accepted', 'receivedAt': at.isoformat(),
        'validUntil': (at + timedelta(seconds=120)).isoformat(),
        'totalRainIn': value,
    }
    envelope = {
        'version': 1, 'streamEpoch': epoch, 'record': record,
        'packetCount': count, 'invalidPackets': invalid,
        'counterDrops': drops, 'counterJumps': jumps,
    }
    return (at + timedelta(seconds=1), json.dumps(envelope))


def day_rows(day=DAY):
    start, end = bounds(day)
    rows = []
    at = start - timedelta(seconds=30)
    while at <= end + timedelta(seconds=60):
        value = 10.1 if at >= start + (end - start) / 2 else 10.0
        rows.append(snapshot(at, len(rows) + 1, value))
        at += timedelta(seconds=90)
    return rows


def qualify(rows, day=DAY):
    _start, end = bounds(day)
    return qualify_rain_day(day, as_of=end + timedelta(seconds=120),
                            observations=rows, policy=POLICY)


def change(rows, index, **fields):
    at, raw = rows[index]
    value = json.loads(raw)
    for name, item in fields.items():
        scope, key = name.split('__', 1) if '__' in name else (None, name)
        if scope == 'record':
            value['record'][key] = item
        else:
            value[key] = item
    updated = list(rows)
    updated[index] = (at, json.dumps(value))
    return updated


def change_epoch(rows, index):
    epoch = str(uuid4())
    return change(rows, index, streamEpoch=epoch, record__streamEpoch=epoch)


def test_complete_monotone_day_yields_bounded_source_total():
    result = qualify(day_rows())
    assert result['basis'] == 'source_bound_counter_bracket_v1'
    assert result['rain_in'] == 0.1
    assert result['uncertainty_in'] == 0
    assert result['receipt_count'] == len(day_rows())


@pytest.mark.parametrize('day,expected_hours', [
    (date(2026, 3, 8), 23), (date(2026, 11, 1), 25),
])
def test_exact_local_day_boundaries_across_dst(day, expected_hours):
    start, end = bounds(day)
    assert (end - start).total_seconds() == expected_hours * 3600
    assert qualify(day_rows(day), day)['rain_in'] == 0.1


@pytest.mark.parametrize('mutation,reason', [
    (lambda rows: rows[2:], 'bracket missing'),
    (lambda rows: rows[:-1], 'bracket missing'),
    (lambda rows: rows[:100] + rows[102:], 'coverage gap'),
    (lambda rows: change(rows, 100, invalidPackets=1), 'fault'),
    (lambda rows: change(rows, 100, counterDrops=1), 'fault'),
    (lambda rows: change(rows, 100, counterJumps=1), 'fault'),
    (lambda rows: change_epoch(rows, 100), 'restarted'),
    (lambda rows: change(rows, 100, record__totalRainIn=9), 'regressed'),
    (lambda rows: change(rows, 100, packetCount=1), 'replay'),
    (lambda rows: change(rows, 100, record__status='invalid'), 'unavailable'),
])
def test_missing_faulted_replayed_or_unavailable_day_is_refused(mutation, reason):
    with pytest.raises(RainDayRefused, match=reason):
        qualify(mutation(day_rows()))


def test_midnight_rain_ambiguity_is_not_hidden_in_a_single_number():
    rows = day_rows()
    # A physically possible rise between the final pre-midnight packet and
    # first post-midnight packet cannot be assigned to either date.
    rows = change(rows, -1, record__totalRainIn=10.2)
    with pytest.raises(RainDayRefused, match='uncertainty'):
        qualify(rows)


def test_small_midnight_ambiguity_is_explicit_and_bounded():
    rows = change(day_rows(), -1, record__totalRainIn=10.11)
    result = qualify(rows)
    assert result['rain_in'] == 0.105
    assert result['uncertainty_in'] == 0.01


def test_incomplete_day_future_row_and_duplicate_json_are_refused():
    rows = day_rows()
    _, end = bounds()
    with pytest.raises(RainDayRefused, match='incomplete'):
        qualify_rain_day(DAY, as_of=end - timedelta(seconds=1),
                         observations=rows, policy=POLICY)
    with pytest.raises(RainDayRefused, match='bounded window'):
        qualify_rain_day(DAY, as_of=end, observations=rows, policy=POLICY)
    at, raw = rows[0]
    malformed = raw.replace('"version": 1,', '"version": 1, "version": 1,', 1)
    with pytest.raises(RainDayRefused, match='duplicate JSON key'):
        parse_rain_snapshot(malformed, at, POLICY)


def test_nonfinite_oversized_and_wrong_sensor_are_refused():
    at, raw = day_rows()[0]
    with pytest.raises(RainDayRefused, match='oversized'):
        parse_rain_snapshot(raw + ' ' * 4096, at, POLICY)
    with pytest.raises(RainDayRefused, match='nonfinite'):
        parse_rain_snapshot(raw.replace('"totalRainIn": 10.0',
                                        '"totalRainIn": NaN'), at, POLICY)
    wrong = json.loads(raw)
    wrong['record']['sensorId'] = 999
    with pytest.raises(RainDayRefused, match='unavailable'):
        parse_rain_snapshot(json.dumps(wrong), at, POLICY)
