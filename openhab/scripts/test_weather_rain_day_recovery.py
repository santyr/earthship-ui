from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from weather_rain_day import RainDayRefused, qualify_rain_day
from weather_rain_day_recovery import qualify_rain_day_recovery
from weather_rain_evidence import RainPolicy


DAY = date(2026, 9, 29)
POLICY = RainPolicy(sensor_id=206)


def rows_for_day():
    zone = ZoneInfo('America/Denver')
    start = datetime.combine(DAY, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(DAY + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    epoch = str(uuid4())
    rows = []
    at = start - timedelta(seconds=30)
    while at <= end + timedelta(seconds=60):
        counter = 10.1 if at >= start + (end - start) / 2 else 10.0
        record = {'version': 1, 'streamEpoch': epoch, 'recordedAt': at.isoformat(),
                  'model': 'Fineoffset-WH65B', 'sensorId': 206,
                  'field': 'totalrainin', 'status': 'valid', 'reason': 'accepted',
                  'receivedAt': at.isoformat(),
                  'validUntil': (at + timedelta(seconds=120)).isoformat(),
                  'totalRainIn': counter}
        value = {'version': 1, 'streamEpoch': epoch, 'record': record,
                 'packetCount': len(rows) + 1, 'invalidPackets': 0,
                 'counterDrops': 0, 'counterJumps': 0}
        rows.append((at + timedelta(seconds=1), json.dumps(value)))
        at += timedelta(seconds=30)
    return rows, end


def mutate(rows, index, fn):
    changed = list(rows)
    at, raw = changed[index]
    value = json.loads(raw)
    fn(value)
    changed[index] = (at, json.dumps(value))
    return changed


def latch(rows, start, *, invalid=1, jumps=1):
    changed = list(rows)
    for i in range(start, len(changed)):
        at, raw = changed[i]
        value = json.loads(raw)
        value.update(invalidPackets=invalid, counterJumps=jumps)
        changed[i] = (at, json.dumps(value))
    return changed


def reject(value):
    value['record'].update(status='invalid', reason='counter_jump',
                           receivedAt=None, validUntil=None, totalRainIn=None)


def restart(value):
    epoch = str(uuid4())
    value['streamEpoch'] = epoch
    value['record']['streamEpoch'] = epoch


def candidate(rows, end):
    return qualify_rain_day_recovery(DAY, as_of=end + timedelta(seconds=120),
                                     observations=rows, policy=POLICY)


def test_explicit_single_rejected_jump_recovers_without_inventing_rain():
    rows, end = rows_for_day()
    rows = mutate(latch(rows, 100), 100, reject)
    with pytest.raises(RainDayRefused):
        qualify_rain_day(DAY, as_of=end + timedelta(seconds=120),
                         observations=rows, policy=POLICY)
    result = candidate(rows, end)
    assert result['rain_in'] == 0.1
    assert result['quarantined_jumps'] == 1
    assert result['original_receipt_count'] == len(rows)
    assert result['basis'].endswith('candidate_v2')


def test_rejected_jump_hidden_between_persistence_polls_recovers():
    rows, end = rows_for_day()
    result = candidate(latch(rows, 100), end)
    assert result['rain_in'] == 0.1
    assert result['quarantined_jumps'] == 1


@pytest.mark.parametrize('mutation,reason', [
    (lambda r: latch(r, 100, invalid=0), 'unpaired'),
    (lambda r: latch(r, 100, jumps=0), 'unpaired'),
    (lambda r: mutate(latch(r, 100), 100,
                      lambda x: x['record'].update(totalRainIn=10.01)), 'hidden jump'),
    (lambda r: mutate(mutate(latch(r, 100), 100, reject), 101,
                      lambda x: x['record'].update(totalRainIn=10.01)), 'did not recover'),
    (lambda r: mutate(mutate(latch(r, 100), 100, reject), 100,
                      lambda x: x['record'].update(
                          recordedAt=json.loads(r[99][1])['record']['recordedAt'])),
     'safe bracket'),
    (lambda r: mutate(latch(r, 1), 1, reject), 'safe bracket'),
    (lambda r: mutate(mutate(latch(r, 100), 100, reject), 101, reject), 'safe bracket'),
    (lambda r: mutate(latch(r, 100), 101,
                      lambda x: x.update(counterDrops=1)), 'counter drop'),
    (lambda r: mutate(latch(r, 100), 101, restart), 'restart'),
])
def test_unproven_recovery_is_refused(mutation, reason):
    rows, end = rows_for_day()
    with pytest.raises(RainDayRefused, match=reason):
        candidate(mutation(rows), end)


def test_rejected_jump_with_missing_next_valid_receipt_is_refused():
    rows, end = rows_for_day()
    rows = mutate(latch(rows, 100), 100, reject)
    with pytest.raises(RainDayRefused, match='recovery'):
        candidate(rows[:101], end)


def test_invalid_record_must_be_exact_collector_quarantine():
    rows, end = rows_for_day()
    rows = mutate(latch(rows, 100), 100, reject)
    rows = mutate(rows, 100, lambda x: x['record'].update(reason='expired'))
    with pytest.raises(RainDayRefused, match='unqualified rejected-jump'):
        candidate(rows, end)
