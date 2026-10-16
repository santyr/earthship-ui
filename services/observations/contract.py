"""Physical observations are evidence, never estimates, requests or commands."""
import json
import math
from datetime import datetime, timezone
from hashlib import sha256

# Units are deliberately specific. Raw moisture and calibrated moisture differ.
TYPES = {
    'contact_state': ('state', ('OPEN', 'CLOSED')),
    'tamper': ('boolean', None), 'leak': ('boolean', None), 'motion': ('boolean', None),
    'air_temperature': ('degC', (-80, 100)), 'relative_humidity': ('percent', (0, 100)),
    'water_depth': ('m', (0, 20)), 'water_flow': ('L/min', (0, 10000)),
    'water_counter': ('L', (0, 1e12)), 'line_pressure': ('kPa', (0, 10000)),
    'pump_runtime': ('s', (0, 1e12)), 'equipment_temperature': ('degC', (-80, 250)),
    'soil_moisture_raw': ('raw', (0, 1e9)), 'soil_moisture': ('percent', (0, 100)),
    'soil_temperature': ('degC', (-80, 100)), 'soil_conductivity': ('mS/cm', (0, 100)),
    'illuminance': ('lux', (0, 1e7)), 'co2': ('ppm', (0, 1e6)),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError('duplicate JSON field')
            out[key] = value
        return out
    def refuse(_):
        raise ValueError('nonfinite JSON')
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=refuse)
    if not isinstance(value, dict):
        raise ValueError('JSON object required')
    return value


def instant(value):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.utcoffset() is None:
        raise ValueError('aware source clock required')
    return parsed.astimezone(timezone.utc)


def digest(raw):
    return sha256(raw).hexdigest()


def measurement(kind, value, unit):
    if kind not in TYPES or unit != TYPES[kind][0]:
        raise ValueError('explicit supported observation and unit required')
    bounds = TYPES[kind][1]
    if kind == 'contact_state':
        if value not in bounds:
            raise ValueError('physical contact state required')
    elif unit == 'boolean':
        if type(value) is not bool:
            raise ValueError('boolean physical observation required')
    elif type(value) not in (int, float) or not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
        raise ValueError('bounded finite physical observation required')
    return dict(observation_type=kind, value=value, unit=unit)


def normalize(*, sensor, kind, value, unit, observed_at, received_at, valid_until,
              source_identity, raw_sha256, source_epoch, timestamp_basis, synthetic,
              qualified=False, diagnostics=None):
    point = measurement(kind, value, unit)
    received_at, valid_until = instant(received_at), instant(valid_until)
    observed_at = None if observed_at is None else instant(observed_at)
    if kind not in sensor['observation_types'] or type(synthetic) is not bool or type(qualified) is not bool:
        raise ValueError('registered physical observation required')
    if observed_at is not None and observed_at > received_at:
        raise ValueError('future physical observation refused')
    if valid_until <= (observed_at or received_at):
        raise ValueError('explicit positive validity required')
    if timestamp_basis not in ('device_clock', 'network_reception', 'provider_receipt', 'unknown'):
        raise ValueError('explicit source timestamp basis required')
    import re
    from uuid import UUID
    if not isinstance(raw_sha256, str) or not re.fullmatch('[0-9a-f]{64}', raw_sha256):
        raise ValueError('exact original digest required')
    if str(UUID(source_epoch)) != source_epoch or UUID(source_epoch).int == 0:
        raise ValueError('canonical source epoch required')
    if not isinstance(source_identity, str) or not 1 <= len(source_identity) <= 256:
        raise ValueError('bounded original source identity required')
    if qualified and (synthetic or not sensor['source_verified'] or timestamp_basis == 'unknown'):
        raise ValueError('commissioned real provenance required for qualification')
    return dict(schema='earthship-observation/v1', sensor_id=sensor['sensor_id'],
        device_id=sensor['device_id'], transport=sensor['transport'], **point,
        observed_at=None if observed_at is None else observed_at.isoformat(),
        received_at=received_at.isoformat(), valid_until=valid_until.isoformat(),
        timestamp_basis=timestamp_basis, source_identity=source_identity,
        provenance=dict(raw_sha256=raw_sha256, source_epoch=source_epoch,
                        hardware_epoch=sensor['hardware_epoch']),
        quality='qualified' if qualified else 'synthetic' if synthetic else 'unqualified',
        synthetic=synthetic, diagnostics=diagnostics or {})
