from datetime import datetime, timedelta, timezone
import json

import pytest
from weather_temperature_evidence import TemperaturePolicy, temperature_receipt
from weather_temperature_reader import select_temperature_at

AT = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
EPOCH = '831b737c-ab25-48d7-9a90-889746e56410'
POLICY = TemperaturePolicy('Fineoffset-WH32B', 235, -80, 160, 120)


def raw(offset=0, value='70', epoch=EPOCH):
    record = temperature_receipt({'model': POLICY.model, 'id': '235', 'tempinf': value}, policy=POLICY,
        stream_epoch=epoch, received_at=AT + timedelta(seconds=offset))
    return json.dumps({'version': 1, 'streamEpoch': epoch, 'records': {'indoor': record}}, allow_nan=False)


def select(rows, target=60, **kwargs):
    context = {'target': AT + timedelta(seconds=target), 'assessed_at': AT + timedelta(hours=1),
               'history_start': AT - timedelta(minutes=5), 'stream': 'indoor', 'policy': POLICY}
    context.update(kwargs)
    return select_temperature_at([(AT + timedelta(seconds=t), value) for t, value in rows], **context)


def test_unchanged_qualified_state_is_used_without_a_nearby_value_change():
    result = select([(0, raw())], target=100)
    assert result['temperatureF'] == 70
    assert result['receivedAt'] == AT
    assert result['storedAt'] == AT
    assert len(result['snapshotSha256']) == 64


def test_post_target_change_is_never_chosen_even_when_closer():
    result = select([(0, raw()), (61, raw(61, '90'))])
    assert result['temperatureF'] == 70
    assert select([(61, raw(61, '90'))]) is None


@pytest.mark.parametrize('target,qualified', [(0, True), (119, True), (120, False), (121, False)])
def test_exact_expiry(target, qualified):
    assert (select([(0, raw())], target=target) is not None) == qualified


@pytest.mark.parametrize('barrier', ['invalid', 'unknown', 'malformed', 'wrong_id'])
def test_latest_barrier_does_not_fall_back_to_older_valid_receipt(barrier):
    document = json.loads(raw(30))
    if barrier == 'invalid': document = json.loads(raw(30, 'invalid'))
    if barrier == 'unknown': document['records']['indoor'] = None
    if barrier == 'wrong_id': document['records']['indoor']['sensorId'] = 999
    latest = 'bad JSON' if barrier == 'malformed' else json.dumps(document)
    assert select([(0, raw()), (30, latest)]) is None
    assert select([(0, raw()), (30, latest), (40, raw())]) is None
    assert select([(0, raw()), (30, latest), (40, raw(40))])['temperatureF'] == 70


def test_restart_unknown_envelope_cannot_resurrect_prior_epoch_value():
    epoch = '2e06bb58-5ac7-4b72-b31d-96a8be0f6bb8'
    unknown = json.dumps({'version': 1, 'streamEpoch': epoch, 'records': {'indoor': None}})
    assert select([(0, raw()), (30, unknown), (40, raw(0, epoch=epoch))]) is None
    assert select([(0, raw()), (30, unknown), (40, raw(40, epoch=epoch))])['streamEpoch'] == epoch


def test_failed_revival_is_itself_a_barrier_to_earlier_receipts():
    rows = [(0, raw()), (30, raw(30, 'invalid')), (40, raw())]
    assert select(rows + [(50, raw(35))]) is None
    assert select(rows + [(50, raw(45))])['receivedAt'] == AT + timedelta(seconds=45)


@pytest.mark.parametrize('latest', [raw(0), raw(30, '80')])
def test_receipt_time_regression_or_conflicting_same_receipt_is_a_barrier(latest):
    assert select([(0, raw()), (30, raw(30)), (40, latest)]) is None


@pytest.mark.parametrize('field,value', [('version', True), ('sensorId', True), ('temperatureF', True),
    ('temperatureF', '70'), ('temperatureF', 999), ('field', 'humidity'), ('reason', 'other'),
    ('validUntil', '2026-09-10T12:10:00+00:00'), ('receivedAt', '2026-09-10T11:59:59+00:00')])
def test_record_contract_mismatch_is_unqualified(field, value):
    doc = json.loads(raw()); doc['records']['indoor'][field] = value
    assert select([(0, json.dumps(doc))]) is None


def test_future_receipt_and_naive_or_unsorted_history_fail_closed():
    assert select([(0, raw(1))]) is None
    assert select([(10, raw()), (0, raw())]) is None
    assert select([(0, raw()), (0, raw(value='71'))]) is None
    assert select([(0, raw()), (0, raw())]) is not None
    assert select([(0, raw())], assessed_at=AT) is None
    assert select([(0, raw())], history_start=AT) is None
    assert select([(0, raw())], target=60, assessed_at=AT.replace(tzinfo=None)) is None


def test_bounds_and_duplicate_json_keys_are_rejected():
    assert select([(0, 'x' * 8193)]) is None
    assert select([(0, raw().replace('"version": 1', '"version":1,"version":1', 1))]) is None
    assert select([(0, raw())] * 10001) is None
    assert select([]) is None


def test_offset_equivalent_target_is_same_instant():
    result = select_temperature_at([(AT, raw())],
        target=(AT + timedelta(seconds=60)).astimezone(timezone(timedelta(hours=-6))),
        assessed_at=AT + timedelta(hours=1), history_start=AT - timedelta(minutes=5), stream='indoor', policy=POLICY)
    assert result['temperatureF'] == 70


def test_fall_back_repeated_hour_uses_actual_elapsed_instants():
    received = datetime.fromisoformat('2026-11-01T01:59:30-06:00')
    target = datetime.fromisoformat('2026-11-01T01:00:30-07:00')
    record = temperature_receipt({'model': POLICY.model, 'id': 235, 'tempinf': '70'}, policy=POLICY,
                                 stream_epoch=EPOCH, received_at=received)
    envelope = json.dumps({'version': 1, 'streamEpoch': EPOCH, 'records': {'indoor': record}})
    result = select_temperature_at([(received, envelope)], target=target, assessed_at=target,
        history_start=target - timedelta(minutes=5), stream='indoor', policy=POLICY)
    assert result['temperatureF'] == 70
    assert (target - result['receivedAt']).total_seconds() == 60
