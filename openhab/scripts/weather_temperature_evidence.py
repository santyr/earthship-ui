"""Pure temperature receipt evidence. No I/O, persisted fallback or learning.

An adapter must pass raw request fields BEFORE receiver fallback/conversion,
its own aware receipt clock, an explicit reviewed identity/range/expiry policy,
and a fresh process epoch. Receipt time is not a sensor measurement timestamp.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from uuid import UUID

MODELS = {
    'Fineoffset-WH65B': ('Fineoffset-WH65B', 'tempf'),
    'Fineoffset-WH24': ('Fineoffset-WH65B', 'tempf'),
    'Fineoffset-WH32B': ('Fineoffset-WH32B', 'tempinf'),
    'AmbientWeather-WH31E': ('AmbientWeather-WH31E', 'tempinf'),
}
NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z')


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class TemperaturePolicy:
    model: str
    sensor_id: int
    minimum_f: float
    maximum_f: float
    validity_seconds: int

    def __post_init__(self):
        if self.model not in MODELS or MODELS[self.model][0] != self.model:
            raise ValueError('canonical supported model required')
        if type(self.sensor_id) is not int or not 0 <= self.sensor_id <= 0xFFFFFFFF:
            raise ValueError('numeric sensor identity required')
        if not _finite(self.minimum_f) or not _finite(self.maximum_f) or self.minimum_f >= self.maximum_f:
            raise ValueError('finite ordered temperature policy bounds required')
        if type(self.validity_seconds) is not int or not 1 <= self.validity_seconds <= 300:
            raise ValueError('bounded receipt validity required')


def _single(packet, key):
    # Flask MultiDict duplicates must not silently choose one provenance/value.
    if hasattr(packet, 'getlist'):
        values = packet.getlist(key)
        return values[0] if len(values) == 1 else None
    return packet.get(key)


def temperature_receipt(packet, *, policy, stream_epoch, received_at):
    """Return one atomic receipt, or None for an unrelated model/known foreign ID.

    Missing/ambiguous ID or temperature for the expected model produces an
    invalid barrier with no usable value/timestamp/expiry. It cannot renew a
    saved observation. Unknown models and known foreign IDs never claim this
    configured stream. No identity is inferred from previously displayed data.
    """
    if not isinstance(policy, TemperaturePolicy) or not isinstance(packet, Mapping):
        raise ValueError('explicit policy and raw packet mapping required')
    if not isinstance(stream_epoch, str) or str(UUID(stream_epoch)) != stream_epoch:
        raise ValueError('canonical restart epoch required')
    if not isinstance(received_at, datetime) or received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError('aware receiver timestamp required')
    at = received_at.astimezone(timezone.utc)
    raw_model = _single(packet, 'model')
    if not isinstance(raw_model, str) or raw_model not in MODELS or MODELS[raw_model][0] != policy.model:
        return None
    raw_id = _single(packet, 'id')
    sensor_id = None
    if type(raw_id) is int and 0 <= raw_id <= 0xFFFFFFFF:
        sensor_id = raw_id
    elif isinstance(raw_id, str) and re.fullmatch(r'[0-9]{1,10}', raw_id):
        candidate = int(raw_id)
        if candidate <= 0xFFFFFFFF:
            sensor_id = candidate
    if sensor_id is not None and sensor_id != policy.sensor_id:
        return None
    record = {
        'version': 1, 'streamEpoch': stream_epoch,
        'recordedAt': at.isoformat(), 'model': policy.model,
        'sensorId': policy.sensor_id, 'field': MODELS[policy.model][1],
        'status': 'invalid', 'reason': 'identity_missing_or_ambiguous',
        'receivedAt': None, 'validUntil': None, 'temperatureF': None,
    }
    if sensor_id is None:
        return record
    raw = _single(packet, record['field'])
    if raw is None:
        record['reason'] = 'temperature_missing_or_ambiguous'
        return record
    if isinstance(raw, str):
        if len(raw) > 64 or not NUMBER.fullmatch(raw.strip()):
            record['reason'] = 'temperature_invalid'
            return record
        value = float(raw)
    elif _finite(raw):
        value = float(raw)
    else:
        record['reason'] = 'temperature_invalid'
        return record
    if not math.isfinite(value) or not policy.minimum_f <= value <= policy.maximum_f:
        record['reason'] = 'temperature_out_of_policy'
        return record
    record.update(status='valid', reason='accepted', receivedAt=at.isoformat(),
                  validUntil=(at + timedelta(seconds=policy.validity_seconds)).isoformat(),
                  temperatureF=value)
    return record
