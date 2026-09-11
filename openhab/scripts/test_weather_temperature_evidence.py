from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from weather_temperature_evidence import TemperaturePolicy, temperature_receipt

AT = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
EPOCH = '831b737c-ab25-48d7-9a90-889746e56410'
# Test-only policy, not a deployed identity or manufacturer operating range.
POLICY = TemperaturePolicy('Fineoffset-WH32B', 235, -80, 160, 120)


def receipt(packet=None, **kwargs):
    return temperature_receipt(packet if packet is not None else {'model': POLICY.model, 'id': '235', 'tempinf': '70'},
                               policy=kwargs.pop('policy', POLICY), stream_epoch=kwargs.pop('stream_epoch', EPOCH),
                               received_at=kwargs.pop('received_at', AT), **kwargs)


def test_atomic_valid_receipt_has_exact_closed_fields_and_no_learning_output():
    record = receipt()
    assert record == {'version': 1, 'streamEpoch': EPOCH, 'recordedAt': AT.isoformat(),
                      'model': POLICY.model, 'sensorId': 235, 'field': 'tempinf',
                      'status': 'valid', 'reason': 'accepted', 'receivedAt': AT.isoformat(),
                      'validUntil': (AT + timedelta(seconds=120)).isoformat(), 'temperatureF': 70.0}
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize('value', [None, '', 'nan', 'inf', '-inf', '1e999', True, float('nan'), 10**400, {}, [], '70F', '-81', '161'])
def test_invalid_or_missing_temperature_never_renews_a_value(value):
    record = receipt({'model': POLICY.model, 'id': '235', 'tempinf': value, 'humidityin': '50'})
    assert record['status'] == 'invalid'
    assert all(record[key] is None for key in ('receivedAt', 'validUntil', 'temperatureF'))
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize('sensor_id', [None, '', True, 'test-a', '235.0', -1, 2**32])
def test_missing_or_invalid_identity_cannot_claim_freshness(sensor_id):
    record = receipt({'model': POLICY.model, 'id': sensor_id, 'tempinf': '70'})
    assert record['reason'] == 'identity_missing_or_ambiguous'
    assert record['temperatureF'] is None


@pytest.mark.parametrize('packet', [
    {'model': 'Fineoffset-WH32B', 'id': '193', 'tempinf': '70'},
    {'model': 'AmbientWeather-WH31E', 'id': '235', 'tempinf': '70'},
    {'model': 'unknown', 'id': '235', 'tempinf': '70'},
])
def test_other_sources_do_not_update_configured_stream(packet):
    assert receipt(packet) is None


def test_same_value_new_packet_advances_receipt_time_but_does_not_change_old_record():
    first = receipt()
    second = receipt(received_at=AT + timedelta(seconds=60))
    assert first['temperatureF'] == second['temperatureF'] == 70
    assert first['receivedAt'] == AT.isoformat()
    assert second['receivedAt'] == (AT + timedelta(seconds=60)).isoformat()
    assert first['validUntil'] != second['validUntil']


def test_request_timestamp_is_not_trusted_and_no_saved_fallback_is_used():
    packet = {'model': POLICY.model, 'id': '235', 'timestamp': '2099-01-01', 'previous_tempinf': '70'}
    assert receipt(packet)['status'] == 'invalid'
    packet['tempinf'] = '71'
    assert receipt(packet)['receivedAt'] == AT.isoformat()


def test_outdoor_alias_still_requires_actual_forwarded_id():
    policy = TemperaturePolicy('Fineoffset-WH65B', 206, -80, 160, 120)
    packet = {'model': 'Fineoffset-WH24', 'tempf': '70'}
    assert receipt(packet, policy=policy)['status'] == 'invalid'
    packet['id'] = 206
    assert receipt(packet, policy=policy)['model'] == 'Fineoffset-WH65B'
    assert receipt(packet, policy=policy)['status'] == 'valid'


def test_duplicate_http_fields_cannot_select_one_value_silently():
    from werkzeug.datastructures import MultiDict
    for key in ['id', 'tempinf']:
        packet = MultiDict([('model', POLICY.model), ('id', '235'), ('tempinf', '70')])
        packet.add(key, '999')
        assert receipt(packet)['status'] == 'invalid'


def test_explicit_epoch_and_aware_clock_are_required_and_preserved():
    with pytest.raises(ValueError): receipt(stream_epoch='not-an-epoch')
    with pytest.raises(ValueError): receipt(received_at=AT.replace(tzinfo=None))
    assert receipt(stream_epoch=str(uuid4()))['streamEpoch'] != receipt()['streamEpoch']
    offset_clock = AT.astimezone(timezone(timedelta(hours=-6)))
    assert receipt(received_at=offset_clock)['receivedAt'] == AT.isoformat()


@pytest.mark.parametrize('field,value', [('model', 'Fineoffset-WH24'), ('sensor_id', True), ('sensor_id', -1),
                                       ('minimum_f', float('nan')), ('maximum_f', -100),
                                       ('validity_seconds', 0), ('validity_seconds', 301), ('validity_seconds', True)])
def test_policy_must_be_explicit_and_bounded(field, value):
    values = vars(POLICY).copy(); values[field] = value
    with pytest.raises(ValueError): TemperaturePolicy(**values)
