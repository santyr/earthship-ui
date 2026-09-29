"""Strict raw outdoor rain-counter receipts; no fallback or I/O.

Receipt time proves that the local receiver saw a packet, not when the sensor
measured it. A separate continuous-history reader must qualify a daily total.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from uuid import UUID


_NUMBER = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z')
_MODELS = {'Fineoffset-WH65B', 'Fineoffset-WH24'}


@dataclass(frozen=True)
class RainPolicy:
    sensor_id: int
    validity_seconds: int = 120
    maximum_counter_in: float = 100000.0

    def __post_init__(self):
        if type(self.sensor_id) is not int or not 0 <= self.sensor_id <= 0xFFFFFFFF:
            raise ValueError('explicit numeric outdoor sensor identity required')
        if type(self.validity_seconds) is not int or not 1 <= self.validity_seconds <= 300:
            raise ValueError('bounded receipt validity required')
        if (type(self.maximum_counter_in) not in (int, float)
                or not math.isfinite(self.maximum_counter_in)
                or not 0 < self.maximum_counter_in <= 1000000):
            raise ValueError('finite rain-counter bound required')


def _single(packet, name):
    if hasattr(packet, 'getlist'):
        values = packet.getlist(name)
        return values[0] if len(values) == 1 else None
    return packet.get(name)


def rain_counter_receipt(packet, *, policy, stream_epoch, received_at):
    """Return an atomic raw-counter receipt, an invalid barrier, or None.

    A packet for the expected outdoor model with missing/ambiguous identity or
    counter cannot renew evidence. Known foreign IDs and unrelated models do
    not claim this stream, even if the legacy receiver processes their data.
    """
    if not isinstance(packet, Mapping) or not isinstance(policy, RainPolicy):
        raise ValueError('raw packet and explicit rain policy required')
    if not isinstance(stream_epoch, str) or str(UUID(stream_epoch)) != stream_epoch:
        raise ValueError('canonical restart epoch required')
    if (not isinstance(received_at, datetime) or received_at.tzinfo is None
            or received_at.utcoffset() is None):
        raise ValueError('aware receiver timestamp required')
    model = _single(packet, 'model')
    if not isinstance(model, str) or model not in _MODELS:
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
    at = received_at.astimezone(timezone.utc)
    record = {
        'version': 1, 'streamEpoch': stream_epoch, 'recordedAt': at.isoformat(),
        'model': 'Fineoffset-WH65B', 'sensorId': policy.sensor_id,
        'field': 'totalrainin', 'status': 'invalid',
        'reason': 'identity_missing_or_ambiguous', 'receivedAt': None,
        'validUntil': None, 'totalRainIn': None,
    }
    if sensor_id is None:
        return record
    raw = _single(packet, 'totalrainin')
    if raw is None:
        record['reason'] = 'counter_missing_or_ambiguous'
        return record
    if isinstance(raw, str):
        if len(raw) > 64 or _NUMBER.fullmatch(raw.strip()) is None:
            record['reason'] = 'counter_invalid'
            return record
        value = float(raw)
    elif type(raw) in (int, float):
        try:
            value = float(raw)
        except OverflowError:
            record['reason'] = 'counter_invalid'
            return record
    else:
        record['reason'] = 'counter_invalid'
        return record
    if not math.isfinite(value) or not 0 <= value <= policy.maximum_counter_in:
        record['reason'] = 'counter_out_of_policy'
        return record
    record.update(status='valid', reason='accepted', receivedAt=at.isoformat(),
                  validUntil=(at + timedelta(seconds=policy.validity_seconds)).isoformat(),
                  totalRainIn=value)
    return record
