"""Raw lux-derived irradiance receipts, never cached weather/source-health proof.

radio_decode_utc is the rtl_433 decoder's UTC clock, not sensor measurement time.
The legacy conversion is a proxy, not a calibrated pyranometer reading.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from uuid import UUID

MODELS = {'Fineoffset-WH65B', 'Fineoffset-WH24'}
CONVERSION = {'luxPerWm2': 126.7, 'maximumWm2': 1200.0, 'decimalPlaces': 2}
NUMBER = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z')


@dataclass(frozen=True)
class RadiationPolicy:
    sensor_id: int
    validity_seconds: int = 120

    def __post_init__(self):
        if type(self.sensor_id) is not int or not 0 <= self.sensor_id <= 0xFFFFFFFF:
            raise ValueError('explicit numeric station identity required')
        if type(self.validity_seconds) is not int or not 1 <= self.validity_seconds <= 300:
            raise ValueError('bounded radiation validity required')


def single(packet, key):
    if hasattr(packet, 'getlist'):
        values = packet.getlist(key)
        return values[0] if len(values) == 1 else None
    return packet.get(key)


def number(value, maximum):
    if isinstance(value, str):
        if len(value) > 64 or NUMBER.fullmatch(value.strip()) is None:
            return None
    elif type(value) not in (int, float):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and 0 <= result <= maximum else None


def invalid(record, reason):
    return {**record, 'status': 'invalid', 'reason': reason, 'receivedAt': None,
            'validUntil': None, 'lightLux': None, 'irradianceWm2': None}


def radiation_receipt(packet, *, policy, stream_epoch, received_at):
    if not isinstance(packet, Mapping) or not isinstance(policy, RadiationPolicy):
        raise ValueError('raw packet and explicit radiation policy required')
    if not isinstance(stream_epoch, str) or str(UUID(stream_epoch)) != stream_epoch:
        raise ValueError('canonical restart epoch required')
    if (not isinstance(received_at, datetime) or received_at.tzinfo is None
            or received_at.utcoffset() is None):
        raise ValueError('aware receiver timestamp required')
    model = single(packet, 'model')
    models = packet.getlist('model') if hasattr(packet, 'getlist') else [model]
    if not any(isinstance(value, str) and value in MODELS for value in models):
        return None
    at = received_at.astimezone(timezone.utc)
    record = {'version': 1, 'streamEpoch': stream_epoch, 'recordedAt': at.isoformat(),
              'model': 'Fineoffset-WH65B', 'sourceModel': model,
              'sensorId': policy.sensor_id, 'field': 'light_lux',
              'status': 'invalid', 'reason': 'model_ambiguous',
              'timeBasis': 'radio_decode_utc', 'radioDecodedAt': None,
              'receivedAt': None, 'validUntil': None, 'lightLux': None,
              'irradianceWm2': None, 'conversion': dict(CONVERSION)}
    if model is None:
        return record
    raw_id = single(packet, 'id')
    sid = None
    if type(raw_id) is int and 0 <= raw_id <= 0xFFFFFFFF:
        sid = raw_id
    elif isinstance(raw_id, str) and re.fullmatch(r'[0-9]{1,10}', raw_id):
        sid = int(raw_id) if int(raw_id) <= 0xFFFFFFFF else None
    if sid is not None and sid != policy.sensor_id:
        return None
    if sid is None:
        return invalid(record, 'identity_missing_or_ambiguous')
    lux = number(single(packet, 'light_lux'), 200000)
    if lux is None:
        return invalid(record, 'lux_invalid')
    watts = number(single(packet, 'solarradiation'), 1200)
    if watts is None or watts != round(min(lux / 126.7, 1200.0), 2):
        return invalid(record, 'conversion_missing_or_mismatched')
    stamp = single(packet, 'radio_decode_utc')
    if not isinstance(stamp, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', stamp):
        return invalid(record, 'source_time_invalid')
    try:
        decoded = datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    except ValueError:
        return invalid(record, 'source_time_invalid')
    record['radioDecodedAt'] = decoded.isoformat()
    if decoded > at + timedelta(seconds=5):
        return invalid(record, 'source_time_future')
    deadline = min(decoded, at) + timedelta(seconds=policy.validity_seconds)
    if at >= deadline:
        return invalid(record, 'source_time_expired')
    return {**record, 'status': 'valid', 'reason': 'accepted',
            'receivedAt': at.isoformat(), 'validUntil': deadline.isoformat(),
            'lightLux': lux, 'irradianceWm2': watts}
