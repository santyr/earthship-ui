from datetime import datetime, timezone

import pytest
from werkzeug.datastructures import MultiDict

from weather_rain_evidence import RainPolicy, rain_counter_receipt


AT = datetime(2026, 9, 29, 1, 0, tzinfo=timezone.utc)
EPOCH = '8cae4972-6e28-4f93-bf4e-0fa03199dd62'
POLICY = RainPolicy(sensor_id=206)


def receipt(packet):
    return rain_counter_receipt(packet, policy=POLICY, stream_epoch=EPOCH,
                                received_at=AT)


def test_valid_raw_zero_and_unchanged_counter_are_fresh_receipts():
    for value in ('0', '10.25'):
        row = receipt({'model': 'Fineoffset-WH65B', 'id': '206',
                       'totalrainin': value})
        assert row['status'] == 'valid'
        assert row['totalRainIn'] == float(value)
        assert row['receivedAt'] == AT.isoformat()
        assert row['validUntil'] == '2026-09-29T01:02:00+00:00'


def test_wh24_alias_and_foreign_identity():
    assert receipt({'model': 'Fineoffset-WH24', 'id': '206',
                    'totalrainin': '1'})['status'] == 'valid'
    assert receipt({'model': 'Fineoffset-WH65B', 'id': '207',
                    'totalrainin': '1'}) is None
    assert receipt({'model': 'Fineoffset-WH32B', 'id': '206',
                    'totalrainin': '1'}) is None


@pytest.mark.parametrize('packet,reason', [
    ({'model': 'Fineoffset-WH65B', 'totalrainin': '1'},
     'identity_missing_or_ambiguous'),
    ({'model': 'Fineoffset-WH65B', 'id': '206'},
     'counter_missing_or_ambiguous'),
    ({'model': 'Fineoffset-WH65B', 'id': '206', 'totalrainin': '-1'},
     'counter_invalid'),
    ({'model': 'Fineoffset-WH65B', 'id': '206', 'totalrainin': 'nan'},
     'counter_invalid'),
    ({'model': 'Fineoffset-WH65B', 'id': '206', 'totalrainin': '100001'},
     'counter_out_of_policy'),
    (MultiDict([('model', 'Fineoffset-WH65B'), ('id', '206'),
                ('totalrainin', '1'), ('totalrainin', '2')]),
     'counter_missing_or_ambiguous'),
    (MultiDict([('model', 'Fineoffset-WH65B'), ('id', '206'),
                ('id', '207'), ('totalrainin', '1')]),
     'identity_missing_or_ambiguous'),
])
def test_missing_malformed_and_duplicate_fields_make_barriers(packet, reason):
    row = receipt(packet)
    assert row['status'] == 'invalid'
    assert row['reason'] == reason
    assert row['receivedAt'] is None
    assert row['totalRainIn'] is None


def test_receiver_time_and_policy_must_be_explicit_and_bounded():
    with pytest.raises(ValueError, match='aware receiver timestamp'):
        rain_counter_receipt({}, policy=POLICY, stream_epoch=EPOCH,
                             received_at=datetime(2026, 9, 29))
    with pytest.raises(ValueError, match='receipt validity'):
        RainPolicy(sensor_id=206, validity_seconds=0)
    with pytest.raises(ValueError, match='sensor identity'):
        RainPolicy(sensor_id=True)
    assert receipt({'model': ['Fineoffset-WH65B'], 'id': '206',
                    'totalrainin': '1'}) is None
    row = receipt({'model': 'Fineoffset-WH65B', 'id': '206',
                   'totalrainin': 10 ** 1000})
    assert row['status'] == 'invalid' and row['totalRainIn'] is None
