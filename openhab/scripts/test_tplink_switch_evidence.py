from datetime import date, datetime, timedelta, timezone
import json
import uuid
from zoneinfo import ZoneInfo

import pytest

from tplink_switch_evidence import (
    BASIS, FIELDS, SwitchEvidenceRefused, parse_switch_receipt, qualify_switch_day,
)


DAY = date(2026, 9, 29)
EPOCH = str(uuid.UUID('323e214a-8752-46b4-9e11-e5d6bceaf138'))


def millis(value):
    return int(value.timestamp() * 1000)


def bounds(day=DAY):
    zone = ZoneInfo('America/Denver')
    start = datetime.combine(day, datetime.min.time(), zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc)
    return start, end


def row(at, sequence, *, states=None, epoch=EPOCH):
    states = states or ('OFF', 'ON')
    fields = {}
    for name, value in zip(FIELDS, states):
        fields[name] = ({'status': 'unavailable', 'reason': 'source_unavailable',
                         'observedAt': None, 'validUntil': None, 'value': None}
                        if value is None else
                        {'status': 'valid', 'reason': 'ok', 'observedAt': millis(at),
                         'validUntil': millis(at + timedelta(seconds=90)), 'value': value})
    body = {'version': 1, 'basis': BASIS, 'streamEpoch': epoch,
            'sequence': sequence, 'recordedAt': millis(at), 'fields': fields}
    return (at + timedelta(milliseconds=1), json.dumps(body, separators=(',', ':')))


def complete_rows(day=DAY):
    start, end = bounds(day)
    first = start - timedelta(seconds=30)
    count = int((end - first).total_seconds() // 60) + 1
    return [row(first + timedelta(seconds=60 * index), index + 1)
            for index in range(count)]


def qualify(rows=None, day=DAY, **kwargs):
    start, end = bounds(day)
    return qualify_switch_day(day, as_of=kwargs.pop('as_of', end),
                              cutover=kwargs.pop('cutover', start),
                              observations=complete_rows(day) if rows is None else rows,
                              **kwargs)


def test_exact_receipt_schema_and_persistence_time():
    start, _ = bounds()
    parsed = parse_switch_receipt(*reversed(row(start, 1)))
    assert parsed.sequence == 1
    assert parsed.fields[FIELDS[0]].value == 'OFF'
    assert parsed.fields[FIELDS[1]].value == 'ON'


@pytest.mark.parametrize('mutate', [
    lambda body: body.update(version=True),
    lambda body: body.update(basis='item_state_only'),
    lambda body: body.update(streamEpoch='not-a-uuid'),
    lambda body: body.update(sequence=0),
    lambda body: body['fields'][FIELDS[0]].update(value='ON '),
    lambda body: body['fields'][FIELDS[0]].update(validUntil=body['recordedAt'] + 1),
    lambda body: body['fields'][FIELDS[0]].update(observedAt=body['recordedAt'] + 1),
    lambda body: body['fields'][FIELDS[1]].update(extra='unexpected'),
])
def test_malformed_envelopes_refuse(mutate):
    persisted, raw = row(bounds()[0], 1)
    body = json.loads(raw); mutate(body)
    with pytest.raises(SwitchEvidenceRefused):
        parse_switch_receipt(json.dumps(body), persisted)


def test_duplicate_key_future_persistence_and_oversized_rows_refuse():
    persisted, raw = row(bounds()[0], 1)
    for value, at in [
        (raw.replace('"version":1', '"version":1,"version":1'), persisted),
        (raw, persisted - timedelta(seconds=1)),
        (raw + ' ' * 4096, persisted),
    ]:
        with pytest.raises(SwitchEvidenceRefused):
            parse_switch_receipt(value, at)


def test_full_local_day_uses_carry_in_and_observed_switch_intervals():
    result = qualify()
    assert result['evidence_rows'] == len(complete_rows())
    assert result['source_item'] == 'TPLink_Switch_Evidence_JSON'
    for field in FIELDS:
        assert result['fields'][field]['coverage'] == 1.0
        assert result['fields'][field]['gap_count'] == 0
        assert result['fields'][field]['quality'] == 'ok'
    assert result['fields'][FIELDS[0]]['observed_on_seconds'] == 0
    assert result['fields'][FIELDS[1]]['observed_on_seconds'] == 86400


def test_one_unavailable_field_degrades_only_that_field():
    rows = complete_rows()
    at = rows[300][0] - timedelta(milliseconds=1)
    rows[300] = row(at, 301, states=(None, 'ON'))
    result = qualify(rows)
    assert result['fields'][FIELDS[0]]['quality'] == 'partial'
    assert result['fields'][FIELDS[0]]['gap_count'] >= 1
    assert result['fields'][FIELDS[0]]['unavailable_barriers'] == 1
    assert result['fields'][FIELDS[1]]['quality'] == 'ok'


def test_source_reported_on_time_tracks_changes_without_held_item_history():
    rows = complete_rows()
    for index in range(60, 180):
        at = rows[index][0] - timedelta(milliseconds=1)
        rows[index] = row(at, index + 1, states=('ON', 'ON'))
    result = qualify(rows)
    assert result['fields'][FIELDS[0]]['observed_on_seconds'] == 7200
    assert result['fields'][FIELDS[0]]['coverage'] == 1.0


def test_missing_middle_sequence_and_unbarriered_restart_refuse():
    rows = complete_rows()
    with pytest.raises(SwitchEvidenceRefused, match='sequence gap'):
        qualify(rows[:300] + rows[301:])
    at = rows[300][0] - timedelta(milliseconds=1)
    rows[300] = row(at, 1, epoch=str(uuid.uuid4()))
    with pytest.raises(SwitchEvidenceRefused, match='unbarriered'):
        qualify(rows)


def test_incomplete_day_and_pre_cutover_history_refuse():
    start, end = bounds()
    with pytest.raises(SwitchEvidenceRefused, match='incomplete'):
        qualify(as_of=end - timedelta(seconds=1))
    with pytest.raises(SwitchEvidenceRefused, match='cutover'):
        qualify(cutover=start + timedelta(seconds=1))


def test_dst_fall_back_day_has_25_hour_window():
    day = date(2026, 11, 1)
    result = qualify(day=day)
    assert result['fields'][FIELDS[0]]['window_seconds'] == 90000
    assert result['fields'][FIELDS[1]]['coverage'] == 1.0
