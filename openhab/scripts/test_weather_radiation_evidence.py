"""A cached/ambiguous irradiance value must never become a raw receipt."""
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import MultiDict

from weather_radiation_evidence import RadiationPolicy, radiation_receipt


AT = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
EPOCH = '831b737c-ab25-48d7-9a90-889746e56410'
POLICY = RadiationPolicy(sensor_id=206)


def packet(**changes):
    return {'model': 'Fineoffset-WH65B', 'id': '206', 'light_lux': '12670',
            'solarradiation': '100', 'radio_decode_utc': '2026-10-01 12:00:00',
            **changes}


def receipt(value=None, at=AT):
    return radiation_receipt(packet() if value is None else value, policy=POLICY,
                             stream_epoch=EPOCH, received_at=at)


def test_raw_lux_conversion_and_original_decode_time_are_retained():
    record = receipt(at=AT + timedelta(seconds=10))
    assert record['status'] == 'valid'
    assert record['lightLux'] == 12670
    assert record['irradianceWm2'] == 100
    assert record['radioDecodedAt'] == '2026-10-01T12:00:00+00:00'
    assert record['receivedAt'] == '2026-10-01T12:00:10+00:00'
    assert record['validUntil'] == '2026-10-01T12:02:00+00:00'
    assert record['timeBasis'] == 'radio_decode_utc'
    assert record['conversion'] == {'luxPerWm2': 126.7, 'maximumWm2': 1200.0,
                                     'decimalPlaces': 2}
    assert record['sourceModel'] == 'Fineoffset-WH65B'
    assert record['sensorId'] == 206


@pytest.mark.parametrize('lux,watts', [('0', '0'), ('200000', '1200'),
                                      ('1267', '10')])
def test_zero_and_clamped_values_remain_original_observations(lux, watts):
    record = receipt(packet(light_lux=lux, solarradiation=watts))
    assert record['status'] == 'valid'
    assert record['lightLux'] == float(lux)
    assert record['irradianceWm2'] == float(watts)


@pytest.mark.parametrize('field,value', [
    ('light_lux', None), ('light_lux', True), ('light_lux', '-1'),
    ('light_lux', 'nan'), ('light_lux', 'inf'), ('light_lux', 10**400),
    ('light_lux', '200001'), ('solarradiation', None),
    ('solarradiation', '99.99'), ('solarradiation', '100.01'),
    ('solarradiation', True), ('solarradiation', 'nan'),
    ('radio_decode_utc', None), ('radio_decode_utc', 'not-a-time'),
    ('radio_decode_utc', '2026-10-01T12:00:00-06:00'),
    ('radio_decode_utc', '2026-10-01 11:58:00'),
    ('radio_decode_utc', '2026-10-01 12:00:06'),
    ('id', None), ('id', True), ('id', '206.0'),
])
def test_invalid_raw_fields_identity_or_time_withhold_values(field, value):
    record = receipt(packet(**{field: value}))
    assert record['status'] == 'invalid'
    assert all(record[key] is None for key in
               ('lightLux', 'irradianceWm2', 'receivedAt', 'validUntil'))


@pytest.mark.parametrize('field', ['model', 'id', 'light_lux',
                                  'solarradiation', 'radio_decode_utc'])
def test_duplicate_fields_cannot_silently_select_a_value(field):
    value = MultiDict(packet())
    value.add(field, value[field])
    assert receipt(value)['status'] == 'invalid'


def test_foreign_sources_are_ignored_but_decoder_alias_is_retained():
    assert receipt(packet(id='999')) is None
    assert receipt(packet(model='Fineoffset-WH32B')) is None
    record = receipt(packet(model='Fineoffset-WH24'))
    assert record['status'] == 'valid'
    assert record['sourceModel'] == 'Fineoffset-WH24'


@pytest.mark.parametrize('changes', [dict(sensor_id=True), dict(sensor_id=-1),
                                    dict(validity_seconds=301),
                                    dict(validity_seconds=True)])
def test_policy_requires_explicit_bounded_identity_and_expiry(changes):
    with pytest.raises(ValueError):
        RadiationPolicy(**{**vars(POLICY), **changes})


def test_epoch_and_receiver_clock_are_not_optional():
    with pytest.raises(ValueError):
        radiation_receipt(packet(), policy=POLICY, stream_epoch='invalid', received_at=AT)
    with pytest.raises(ValueError):
        receipt(at=AT.replace(tzinfo=None))
