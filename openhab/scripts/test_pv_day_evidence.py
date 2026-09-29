import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from pv_day_evidence import PVDayRefused, parse_pv_receipt, qualify_pv_day


EPOCH = '00000000-0000-4000-8000-000000000001'
NEXT_EPOCH = '00000000-0000-4000-8000-000000000002'
DAY = date(2026, 9, 26)


def bounds(day=DAY):
    zone = ZoneInfo('America/Denver')
    return (datetime.combine(day, time.min, zone).astimezone(timezone.utc),
            datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc))


def millis(value):
    return int(value.timestamp() * 1000)


def receipt(at, sequence, wh=8298, *, epoch=EPOCH, status='valid'):
    field = ({'status': 'valid', 'reason': 'ok', 'observedAt': millis(at),
              'validUntil': millis(at + timedelta(seconds=90)), 'wh': wh}
             if status == 'valid' else
             {'status': 'unavailable', 'reason': status, 'observedAt': None,
              'validUntil': None, 'wh': None})
    return {'version': 1, 'basis': 'mppt60_native_pv_day_wh',
            'streamEpoch': epoch, 'sequence': sequence, 'recordedAt': millis(at),
            'fields': {'mppt60.pv_day_wh': field}}


def rows(day=DAY):
    start, end = bounds(day)
    points = []
    at = start + timedelta(seconds=30)
    sequence = 1
    while at < end:
        # The native day counter may remain unchanged for long periods.
        wh = 0 if at < start + timedelta(hours=7) else 8298
        points.append((at + timedelta(milliseconds=1),
                       json.dumps(receipt(at, sequence, wh))))
        sequence += 1
        at += timedelta(minutes=1)
    return points


def qualify(points, day=DAY):
    return qualify_pv_day(day, as_of=bounds(day)[1] + timedelta(seconds=1),
                          observations=points)


def change(points, index, update):
    result = list(points)
    persisted, raw = result[index]
    value = json.loads(raw)
    update(value)
    result[index] = (persisted, json.dumps(value))
    return result


def test_complete_change_only_counter_day_qualifies_without_inventing_generation():
    result = qualify(rows())
    assert result['pv_kwh'] == 8.298
    assert result['receipt_count'] == 1440
    assert result['coverage'] > 0.999
    assert result['basis'] == 'mppt60_native_pv_day_wh'


@pytest.mark.parametrize('day', [date(2026, 3, 8), date(2026, 11, 1)])
def test_local_dst_day_has_real_23_or_25_hour_window(day):
    result = qualify(rows(day), day)
    assert result['receipt_count'] == (bounds(day)[1] - bounds(day)[0]) / timedelta(minutes=1)
    assert result['coverage'] > 0.999


def test_missing_sequence_refuses_even_when_short_gap_keeps_coverage_high():
    points = rows()
    with pytest.raises(PVDayRefused, match='sequence gap'):
        qualify(points[:500] + points[501:])


def test_duplicate_or_out_of_order_persistence_timestamp_refuses():
    points = rows()
    duplicate = list(points)
    duplicate[500] = (duplicate[499][0], duplicate[500][1])
    with pytest.raises(PVDayRefused, match='row order'):
        qualify(duplicate)
    with pytest.raises(PVDayRefused, match='sequence gap|row order'):
        qualify(points[:500] + [points[501], points[500]] + points[502:])
    def same_clock(value):
        recorded = json.loads(points[499][1])['recordedAt']
        value['recordedAt'] = recorded
        value['fields']['mppt60.pv_day_wh']['observedAt'] = recorded
        value['fields']['mppt60.pv_day_wh']['validUntil'] = recorded + 90000
    same_recording = change(points, 500, same_clock)
    with pytest.raises(PVDayRefused, match='clock regressed or conflicted'):
        qualify(same_recording)


@pytest.mark.parametrize('bad', [
    lambda value: value.update(basis='derived_item'),
    lambda value: value['fields']['mppt60.pv_day_wh'].update(wh=100001),
    lambda value: value['fields']['mppt60.pv_day_wh'].update(validUntil=value['recordedAt'] + 1),
    lambda value: value.update(extra=True),
])
def test_invalid_or_untrusted_receipt_refuses_whole_day(bad):
    with pytest.raises(PVDayRefused):
        qualify(change(rows(), 500, bad))


def test_duplicate_json_key_is_a_barrier_not_last_value_wins():
    at = bounds()[0] + timedelta(seconds=30)
    raw = json.dumps(receipt(at, 1)).replace('"version": 1,', '"version": 1, "version": 1,')
    with pytest.raises(PVDayRefused, match='duplicate JSON key'):
        parse_pv_receipt(raw, at + timedelta(milliseconds=1))


def test_long_unavailable_interval_fails_coverage():
    points = rows()
    for index in range(600, 620):
        points = change(points, index, lambda value: value['fields']['mppt60.pv_day_wh'].update(
            status='unavailable', reason='source_unavailable', observedAt=None,
            validUntil=None, wh=None))
    with pytest.raises(PVDayRefused, match='coverage'):
        qualify(points)


def test_restart_needs_explicit_new_epoch_start_barrier():
    points = rows()
    for index in range(700, len(points)):
        def revise(value, index=index):
            value['streamEpoch'] = NEXT_EPOCH
            value['sequence'] = index - 699
            if index == 700:
                value['fields']['mppt60.pv_day_wh'] = {
                    'status': 'unavailable', 'reason': 'input_unavailable',
                    'observedAt': None, 'validUntil': None, 'wh': None}
        points = change(points, index, revise)
    assert qualify(points)['pv_kwh'] == 8.298
    unbarriered = change(points, 700, lambda value: value['fields']['mppt60.pv_day_wh'].update(
        status='valid', reason='ok', observedAt=value['recordedAt'],
        validUntil=value['recordedAt'] + 90000, wh=8298))
    with pytest.raises(PVDayRefused, match='unbarriered'):
        qualify(unbarriered)


def test_midnight_carry_reset_allowed_once_but_midday_decrease_refused():
    points = rows()
    carried = change(points, 0, lambda value: value['fields']['mppt60.pv_day_wh'].update(wh=8298))
    assert qualify(carried)['pv_kwh'] == 8.298
    dropped = change(points, 750, lambda value: value['fields']['mppt60.pv_day_wh'].update(wh=100))
    with pytest.raises(PVDayRefused, match='decreased'):
        qualify(dropped)


def test_zero_reset_in_last_three_minutes_preserves_daily_peak():
    points = rows()
    for index in (-2, -1):
        points = change(points, index, lambda value: value['fields'][
            'mppt60.pv_day_wh'].update(wh=0))
    assert qualify(points)['pv_kwh'] == 8.298

    carried = change(points, 0, lambda value: value['fields'][
        'mppt60.pv_day_wh'].update(wh=12000))
    assert qualify(carried)['pv_kwh'] == 8.298


def test_terminal_reset_refuses_early_or_nonzero_drop_and_later_generation():
    points = rows()
    early = list(points)
    for index in range(len(points) - 4, len(points)):
        early = change(early, index, lambda value: value['fields'][
            'mppt60.pv_day_wh'].update(wh=0))
    with pytest.raises(PVDayRefused, match='decreased'):
        qualify(early)

    nonzero = list(points)
    for index in (-2, -1):
        nonzero = change(nonzero, index, lambda value: value['fields'][
            'mppt60.pv_day_wh'].update(wh=100))
    with pytest.raises(PVDayRefused, match='decreased'):
        qualify(nonzero)

    rising = change(points, -2, lambda value: value['fields'][
        'mppt60.pv_day_wh'].update(wh=0))
    rising = change(rising, -1, lambda value: value['fields'][
        'mppt60.pv_day_wh'].update(wh=1))
    with pytest.raises(PVDayRefused, match='rose after terminal reset'):
        qualify(rising)


def test_terminal_receipt_and_complete_day_are_required():
    with pytest.raises(PVDayRefused, match='boundary'):
        qualify(rows()[:-3])
    with pytest.raises(PVDayRefused, match='incomplete'):
        qualify_pv_day(DAY, as_of=bounds()[1] - timedelta(seconds=1), observations=rows())


def test_row_budget_refuses_unbounded_input():
    points = rows()
    with pytest.raises(PVDayRefused, match='row budget'):
        qualify(points + [points[-1]] * (5001 - len(points)))
