from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from bms_aux_evidence import (BmsAuxEvidenceRefused, FIELDS, TTL,
                              parse_bms_aux_receipt, qualify_bms_aux_day)


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
