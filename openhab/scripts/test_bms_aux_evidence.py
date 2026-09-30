from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from bms_aux_evidence import (BmsAuxEvidenceRefused, FIELDS, TTL,
                              parse_bms_aux_receipt, qualify_bms_aux_day,
                              validate_receipt_successor)
from bms_temperature_parity import assess_bms_temperature_parity, expected_fahrenheit


DAY = date(2026, 10, 1)
EPOCH = str(UUID(int=1))
OTHER = str(UUID(int=2))
CUTOVER = datetime(2026, 1, 1, tzinfo=timezone.utc)


def bounds(day=DAY):
    zone = ZoneInfo('America/Denver')
    return (datetime.combine(day, time.min, zone).astimezone(timezone.utc),
            datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc))


def ms(at):
    return int(at.timestamp() * 1000)


def receipt(at, seq, *, epoch=EPOCH, unavailable=(), capacity=320,
            temperature=29300):
    fields = {}
    for name, value in zip(FIELDS, (capacity, temperature)):
        fields[name] = ({'status': 'unavailable', 'reason': 'input_unavailable',
                         'observedAt': None, 'validUntil': None, 'value': None}
                        if name in unavailable else
                        {'status': 'valid', 'reason': 'ok', 'observedAt': ms(at),
                         'validUntil': ms(at + TTL), 'value': value})
    return {'version': 1, 'basis': 'discover_bms_190_native_aux_v1',
            'streamEpoch': epoch, 'sequence': seq, 'recordedAt': ms(at),
            'fields': fields}


def encoded(at, seq, **kwargs):
    return json.dumps(receipt(at, seq, **kwargs), separators=(',', ':'))


def day_rows(day=DAY, *, delay=timedelta(0)):
    start, end = bounds(day)
    count = int((end-start).total_seconds() // 60)
    return [(start + timedelta(minutes=index-1) + delay,
             encoded(start + timedelta(minutes=index-1), index+1))
            for index in range(count+1)]


def qualified(rows, day=DAY):
    return qualify_bms_aux_day(day, as_of=bounds(day)[1], cutover=CUTOVER,
                               observations=rows)


def test_complete_native_day_has_separate_100_percent_field_coverage():
    result = qualified(day_rows())
    assert result['evidence_rows'] == 1441
    assert {name: value['quality'] for name, value in result['fields'].items()} == {
        name: 'ok' for name in FIELDS}
    assert all(value['coverage'] == 1 for value in result['fields'].values())


def simultaneous_pair():
    at = bounds()[0] + timedelta(hours=1)
    previous = receipt(at, 10, capacity=296)
    previous['fields'][FIELDS[0]].update(observedAt=ms(at-timedelta(seconds=30)),
                                       validUntil=ms(at-timedelta(seconds=30)+TTL))
    latest = receipt(at, 11, capacity=300)
    return at, previous, latest


def test_independent_native_updates_same_millisecond_keep_original_expiry():
    at, first, second = simultaneous_pair()
    previous = parse_bms_aux_receipt(json.dumps(first), at)
    latest = parse_bms_aux_receipt(json.dumps(second), at+timedelta(milliseconds=1))
    validate_receipt_successor(previous, latest)
    assert latest.recorded_at == previous.recorded_at
    assert latest.fields[FIELDS[0]].observed_at == at
    assert latest.fields[FIELDS[1]] == previous.fields[FIELDS[1]]
    assert latest.fields[FIELDS[0]].valid_until == at+TTL


@pytest.mark.parametrize('bad', ['duplicate', 'conflict', 'source_regression',
                                 'recording_regression', 'epoch', 'sequence', 'durable_time'])
def test_same_clock_never_licenses_replay_or_conflicting_source(bad):
    at, first, second = simultaneous_pair()
    persisted = at+timedelta(milliseconds=1)
    if bad == 'duplicate': second['fields'] = first['fields']
    if bad == 'conflict': second['fields'][FIELDS[1]]['value'] += 100
    if bad == 'source_regression':
        second['fields'][FIELDS[0]].update(observedAt=ms(at-timedelta(seconds=60)),
                                          validUntil=ms(at-timedelta(seconds=60)+TTL))
    if bad == 'recording_regression':
        second['recordedAt'] -= 1
        for name in FIELDS:
            second['fields'][name]['observedAt'] -= 1
            second['fields'][name]['validUntil'] -= 1
    if bad == 'epoch': second = receipt(at, 1, epoch=OTHER, unavailable=FIELDS)
    if bad == 'sequence': second['sequence'] += 1
    if bad == 'durable_time': persisted = at
    with pytest.raises(BmsAuxEvidenceRefused):
        validate_receipt_successor(parse_bms_aux_receipt(json.dumps(first), at),
                                   parse_bms_aux_receipt(json.dumps(second), persisted))


def test_day_keeps_same_clock_barrier_partial_without_inventing_freshness():
    rows = day_rows()
    at, raw = rows[50]
    second = receipt(at, 52, unavailable=(FIELDS[1],))
    rows.insert(51, (at+timedelta(milliseconds=1), json.dumps(second)))
    for index in range(52, len(rows)):
        stamp, raw = rows[index]
        body = json.loads(raw); body['sequence'] += 1
        rows[index] = stamp, json.dumps(body)
    result = qualified(rows)
    assert result['fields'][FIELDS[0]]['quality'] == 'ok'
    assert result['fields'][FIELDS[1]]['quality'] == 'partial'
    assert result['fields'][FIELDS[1]]['unavailable_barriers'] == 1


def test_one_second_beyond_native_expiry_keeps_day_partial():
    start, end = bounds()
    times = [start + timedelta(minutes=index - 1)
             for index in range(int((end - start).total_seconds() // 60) + 1)]
    times.pop(7)  # one missed native update
    times[7] += timedelta(seconds=1)  # the next update is 121 seconds later
    rows = [(at, encoded(at, index + 1)) for index, at in enumerate(times)]
    result = qualified(rows)
    for field in FIELDS:
        assert result['fields'][field]['quality'] == 'partial'
        assert result['fields'][field]['gap_count'] == 1
        assert result['fields'][field]['covered_seconds'] == 86400 - 1


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 8), 23),
                                        (date(2026, 11, 1), 25)])
def test_dst_day_uses_real_elapsed_time(day, hours):
    result = qualified(day_rows(day), day)
    assert all(value['window_seconds'] == hours * 3600
               and value['quality'] == 'ok' for value in result['fields'].values())


def test_unavailable_temperature_does_not_invalidate_capacity_coverage():
    rows = day_rows()
    at, _ = rows[5]
    rows[5] = (at, encoded(at, 6, unavailable=(FIELDS[1],)))
    result = qualified(rows)
    assert result['fields'][FIELDS[0]]['quality'] == 'ok'
    assert result['fields'][FIELDS[1]]['quality'] == 'partial'
    assert result['fields'][FIELDS[1]]['unavailable_barriers'] == 1


def test_receipt_cannot_backdate_quality_before_durable_persistence():
    rows = day_rows(delay=timedelta(seconds=10))
    result = qualified(rows)
    # The pre-midnight carry was persisted before start, so it still covers
    # midnight. A delayed first in-day row does not invent a fresh gap.
    assert result['fields'][FIELDS[0]]['quality'] == 'ok'
    start, end = bounds()
    first = (start + timedelta(seconds=10), encoded(start, 1))
    result = qualified([first])
    assert result['fields'][FIELDS[0]]['covered_seconds'] <= 110
    assert result['fields'][FIELDS[0]]['quality'] == 'insufficient_data'


@pytest.mark.parametrize('mutation', [
    lambda body: {**body, 'basis': 'legacy'},
    lambda body: {**body, 'sequence': True},
    lambda body: {**body, 'recordedAt': True},
    lambda body: {**body, 'streamEpoch': 'bad'},
    lambda body: {**body, 'fields': {**body['fields'], FIELDS[0]: {
        **body['fields'][FIELDS[0]], 'value': 451}}},
    lambda body: {**body, 'fields': {**body['fields'], FIELDS[1]: {
        **body['fields'][FIELDS[1]], 'validUntil': body['fields'][FIELDS[1]]['validUntil']+1}}},
])
def test_malformed_receipt_is_refused(mutation):
    at = bounds()[0]
    with pytest.raises(BmsAuxEvidenceRefused):
        parse_bms_aux_receipt(json.dumps(mutation(receipt(at, 1))), at)


def test_duplicate_key_and_oversized_row_are_refused():
    at = bounds()[0]
    with pytest.raises(BmsAuxEvidenceRefused):
        parse_bms_aux_receipt(encoded(at, 1).replace('"version":1', '"version":1,"version":1'), at)
    with pytest.raises(BmsAuxEvidenceRefused):
        parse_bms_aux_receipt(' ' * 4097, at)
    with pytest.raises(BmsAuxEvidenceRefused):
        parse_bms_aux_receipt('\ud800', at)
    unavailable = receipt(at, 1, unavailable=FIELDS)
    unavailable['fields'][FIELDS[0]]['reason'] = []
    with pytest.raises(BmsAuxEvidenceRefused):
        parse_bms_aux_receipt(json.dumps(unavailable), at)


def test_sequence_gap_and_unbarriered_restart_refuse_entire_day():
    rows = day_rows()
    at, _ = rows[3]
    rows[3] = (at, encoded(at, 99))
    with pytest.raises(BmsAuxEvidenceRefused, match='sequence'):
        qualified(rows)
    rows = day_rows()
    rows[3] = (at, encoded(at, 1, epoch=OTHER))
    with pytest.raises(BmsAuxEvidenceRefused, match='restart'):
        qualified(rows)


def test_barriered_restart_is_allowed_but_not_full_quality():
    rows = day_rows()
    at, _ = rows[3]
    rows = rows[:3] + [(at, encoded(at, 1, epoch=OTHER, unavailable=FIELDS))]
    rows += [(stamp, encoded(stamp, index-2, epoch=OTHER))
             for index, (stamp, _) in enumerate(day_rows()[4:], start=4)]
    result = qualified(rows)
    assert all(value['quality'] == 'partial' for value in result['fields'].values())


def test_partial_and_pre_cutover_days_never_qualify():
    rows = day_rows()
    with pytest.raises(BmsAuxEvidenceRefused):
        qualify_bms_aux_day(DAY, as_of=bounds()[1] - timedelta(seconds=1),
                            cutover=CUTOVER, observations=rows)
    with pytest.raises(BmsAuxEvidenceRefused):
        qualify_bms_aux_day(DAY, as_of=bounds()[1],
                            cutover=bounds()[0] + timedelta(seconds=1), observations=rows)
    with pytest.raises(BmsAuxEvidenceRefused, match='boundary'):
        qualify_bms_aux_day(DAY, as_of=bounds()[1],
                            cutover=bounds()[0], observations=rows)


def test_temperature_parity_scores_raw_changes_not_unchanged_item_age():
    rows = day_rows()
    for index in range(100, len(rows)):
        at, _ = rows[index]
        raw = 29400 if index < 200 else 29300
        rows[index] = (at, encoded(at, index + 1, temperature=raw))
    start, end = bounds()
    derived = [(start - timedelta(minutes=1), 68.0),
               (rows[100][0] + timedelta(seconds=1), 69.8),
               (rows[200][0] + timedelta(seconds=1), 68.0)]
    result = assess_bms_temperature_parity(
        DAY, as_of=end, cutover=CUTOVER, observations=rows,
        derived_points=derived)
    assert result['source_temperature_quality'] == 'ok'
    assert result['raw_transitions'] == 2
    assert result['checked_transitions'] == 2
    assert result['status'] == 'observed_consistent'
    assert result['mismatches'] == []
    # The held Fahrenheit value remains legitimate for the rest of this day.
    assert derived[-1][0] < end - timedelta(hours=20)


def test_temperature_parity_refuses_wrong_derived_value_and_sequence_gap():
    rows = day_rows()
    for index in range(100, len(rows)):
        at, _ = rows[index]
        rows[index] = (at, encoded(at, index + 1, temperature=29400))
    start, end = bounds()
    held = [(start - timedelta(minutes=1), 68.0)]
    result = assess_bms_temperature_parity(
        DAY, as_of=end, cutover=CUTOVER, observations=rows,
        derived_points=held)
    assert result['status'] == 'mismatch'
    assert result['checked_transitions'] == 1
    assert result['mismatches'][0]['expected_f'] == 69.8
    at, _ = rows[500]
    rows[500] = (at, encoded(at, 999, temperature=29400))
    with pytest.raises(BmsAuxEvidenceRefused, match='sequence'):
        assess_bms_temperature_parity(
            DAY, as_of=end, cutover=CUTOVER, observations=rows,
            derived_points=held)


def test_temperature_parity_reports_no_change_without_inventing_evidence():
    start, end = bounds()
    result = assess_bms_temperature_parity(
        DAY, as_of=end, cutover=CUTOVER, observations=day_rows(),
        derived_points=[(start - timedelta(minutes=1), 68.0)])
    assert result['status'] == 'insufficient_changes'
    assert result['checked_transitions'] == 0
    assert expected_fahrenheit(29300) == 68.0
