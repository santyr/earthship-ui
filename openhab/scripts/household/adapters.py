"""Adapt exact originals through mature validators, without live reads."""
from hashlib import sha256
import json
from .evidence import EvidenceRef, Observation, ROLES, utc, epoch, digest


def _original(raw, expected_sha256, *, maximum=4096):
    if raw is None:
        if expected_sha256 is not None: raise ValueError('missing source cannot claim a digest')
        return None
    digest(expected_sha256)
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > maximum:
        raise ValueError('bounded exact original source required')
    if sha256(raw.encode('utf-8')).hexdigest() != expected_sha256:
        raise ValueError('original source digest differs')
    return expected_sha256


def _unavailable(role, identity, sha, as_of, reason):
    return Observation(EvidenceRef(role, identity, sha, None, None, None, None,
                                   None, None, utc(as_of), 'unavailable', reason), None, ROLES[role][1])


def _adapt(role, identity, sha, expected_epoch, as_of, source_epoch, observed,
           received, available, until, value, *, hardware_epoch=None, parents=()):
    as_of = utc(as_of)
    if (hardware_epoch or source_epoch) != epoch(expected_epoch): reason = 'wrong_epoch'
    elif available > as_of or received > as_of: reason = 'future_source'
    elif as_of >= until: reason = 'expired_source'
    else: reason = None
    ref = EvidenceRef(role, identity, sha, source_epoch, hardware_epoch, observed,
                      received, available, until, as_of,
                      'unavailable' if reason else 'qualified', reason, parents)
    return Observation(ref, None if reason else value, ROLES[role][1])


def battery_soc(*, raw, expected_sha256, source_identity, expected_epoch, persisted_at, as_of):
    from earthship_energy.bms_evidence import parse_evidence
    epoch(expected_epoch); as_of=utc(as_of); persisted_at=utc(persisted_at)
    sha = _original(raw, expected_sha256)
    if raw is None: return _unavailable('battery_soc', source_identity, sha, as_of, 'missing_source')
    record = parse_evidence(raw, persisted_at)
    if record is None or record.status != 'valid':
        return _unavailable('battery_soc', source_identity, sha, as_of, 'source_unqualified')
    return _adapt('battery_soc', source_identity, sha, expected_epoch, as_of,
                  record.stream_epoch, record.observed_at, record.recorded_at,
                  persisted_at, record.valid_until, record.soc)


def pv_day_counter(*, raw, expected_sha256, source_identity, expected_epoch, persisted_at, as_of):
    from pv_day_evidence import parse_pv_receipt, PVDayRefused
    epoch(expected_epoch); as_of=utc(as_of); persisted_at=utc(persisted_at)
    sha = _original(raw, expected_sha256)
    if raw is None: return _unavailable('pv_day_wh', source_identity, sha, as_of, 'missing_source')
    try: record = parse_pv_receipt(raw, persisted_at)
    except PVDayRefused: return _unavailable('pv_day_wh', source_identity, sha, as_of, 'source_unqualified')
    if record.status != 'valid': return _unavailable('pv_day_wh', source_identity, sha, as_of, 'source_unqualified')
    return _adapt('pv_day_wh', source_identity, sha, expected_epoch, as_of,
                  record.epoch, record.observed_at, record.recorded_at,
                  persisted_at, record.valid_until, record.wh)


def native_temperature(*, role, raw, expected_sha256, source_identity, expected_epoch, as_of):
    from weather_temperature_sources import replay_temperature_source
    from thermal_model.temperature_history import STREAMS
    from .codec import loads
    streams = {'air_temperature': STREAMS['air'][0], 'mass_temperature': STREAMS['mass'][0], 'outdoor_temperature': STREAMS['outdoor'][0]}
    if role not in streams: raise ValueError('explicit native temperature role required')
    epoch(expected_epoch); as_of=utc(as_of)
    sha = _original(raw, expected_sha256, maximum=1024*1024)
    if raw is None: return _unavailable(role, source_identity, sha, as_of, 'missing_source')
    packet=loads(raw)
    if packet.get('stream') != streams[role]: raise ValueError('original native source stream differs')
    grid = replay_temperature_source(packet)
    if len(grid) != 1: raise ValueError('one original native target required')
    target, record = grid[0]
    if target > as_of: return _unavailable(role, source_identity, sha, as_of, 'future_source')
    if record is None: return _unavailable(role, source_identity, sha, as_of, 'source_unqualified')
    return _adapt(role, source_identity, sha, expected_epoch, as_of,
                  record['streamEpoch'], None, record['receivedAt'], record['storedAt'],
                  record['validUntil'], record['temperatureF'],
                  hardware_epoch=record['sensorEpoch'], parents=(record['snapshotSha256'],))
