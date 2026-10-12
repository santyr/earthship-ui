"""Sealed exact-instant native solar geometry, outside the fitted v1 runtime.

Calculated geometry is neither measured weather nor control authority. The
retained native batch is replayed without an RPC, interpolation, or fallback.
Adopting this v2 elevation rule requires a separately versioned model/refit.
"""
from bisect import bisect_left
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from astro_forecast_context import _supported_calculation_version

REQUEST_SCHEMA = 'earthship-astro-geometry-request/v1'
SOURCE_SCHEMA = 'earthship-astro-geometry-source/v1'
CACHE_SCHEMA = 'earthship-native-solar-geometry/v1'
SOLAR_RULE = 'earthship-native-solar-elevation/v2'
ALGORITHM = 'org.openhab.binding.astro.internal.calc.SunCalc#getPosition'
MAX_POINTS, MAX_OUTPUT_BYTES, MAX_CACHE_BYTES = 256, 32768, 131072
REQUEST_FIELDS = {'schema', 'requested_at', 'site', 'timezone', 'instants', 'request_sha256'}
SOURCE_FIELDS = {'schema', 'source_thing', 'status', 'observed_at', 'site',
                 'timezone', 'native_runtime', 'algorithm', 'resolution_us', 'source_sha256'}
CACHE_FIELDS = {'schema', 'rule', 'request', 'source', 'computed_at', 'native_output',
                'native_output_sha256', 'positions', 'cache_sha256'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(value, field):
    return sha256(_canonical({k: v for k, v in value.items() if k != field})).hexdigest()


def _hash(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('original geometry identity required')
    return value


def _instant(value, *, exact=False):
    if isinstance(value, str):
        if not 1 <= len(value) <= 64:
            raise ValueError('bounded geometry timestamp required')
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('valid geometry timestamp required') from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware geometry timestamp required')
    value = value.astimezone(timezone.utc)
    if exact and value.microsecond % 1000:
        raise ValueError('native millisecond timestamp required; rounding is forbidden')
    return value


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError('finite physical geometry quantity required')
    return float(value)


def _site(latitude, longitude):
    return {'latitude': _number(latitude, -90, 90), 'longitude': _number(longitude, -180, 180)}


def _zone(name):
    if not isinstance(name, str) or not 1 <= len(name) <= 64:
        raise ValueError('explicit geometry timezone required')
    try:
        ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError('known geometry timezone required') from None
    return name


def _request(value):
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS or value['schema'] != REQUEST_SCHEMA:
        raise ValueError('closed geometry request required')
    if value['request_sha256'] != _digest(value, 'request_sha256'):
        raise ValueError('original geometry request changed')
    _hash(value['request_sha256']);_zone(value['timezone'])
    if (not isinstance(value['site'], dict) or set(value['site']) != {'latitude', 'longitude'} or
            value['site'] != _site(**value['site'])):
        raise ValueError('explicit request site required')
    requested = _instant(value['requested_at'])
    if value['requested_at'] != requested.isoformat():
        raise ValueError('canonical request availability required')
    points = value['instants']
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError('bounded nonempty native geometry batch required')
    canonical = [_instant(at, exact=True).isoformat() for at in points]
    if points != canonical or points != sorted(set(points)):
        raise ValueError('unique ordered exact native instants required')
    return deepcopy(value)


def build_request(instants, *, requested_at, latitude, longitude, timezone_name):
    if not isinstance(instants, (list, tuple)) or not 1 <= len(instants) <= MAX_POINTS:
        raise ValueError('bounded nonempty native geometry batch required')
    points = sorted({_instant(at, exact=True).isoformat() for at in instants})
    value = dict(schema=REQUEST_SCHEMA, requested_at=_instant(requested_at).isoformat(),
                 site=_site(latitude, longitude), timezone=_zone(timezone_name), instants=points)
    value['request_sha256'] = _digest(value, 'request_sha256')
    return _request(value)


def _runtime(value):
    if (not isinstance(value, dict) or set(value) != {'binding_version', 'libraries', 'collector_sha256'} or
            not _supported_calculation_version('openhab-astro-' + str(value['binding_version']))):
        raise ValueError('supported explicit native calculation runtime required')
    _hash(value['collector_sha256'])
    libraries = value['libraries']
    if (not isinstance(libraries, dict) or not 2 <= len(libraries) <= 16 or
            not {'astro_binding', 'openhab_core'} <= set(libraries)):
        raise ValueError('complete bounded native library identities required')
    for role, identity in libraries.items():
        if not isinstance(role, str) or re.fullmatch('[a-z][a-z0-9_]{0,63}', role) is None:
            raise ValueError('explicit native library role required')
        _hash(identity)
    return deepcopy(value)


def _source(value, request):
    if (not isinstance(value, dict) or set(value) != SOURCE_FIELDS or
            value['schema'] != SOURCE_SCHEMA or value['source_thing'] != 'astro:sun:local' or
            value['status'] != 'ONLINE' or value['algorithm'] != ALGORITHM or
            type(value['resolution_us']) is not int or value['resolution_us'] != 1000):
        raise ValueError('closed native calculation source required')
    if value['source_sha256'] != _digest(value, 'source_sha256'):
        raise ValueError('original native calculation source changed')
    _hash(value['source_sha256']);_runtime(value['native_runtime'])
    site = value['site']
    if (not isinstance(site, dict) or set(site) != {'latitude', 'longitude', 'altitude_m'} or
            _site(site['latitude'], site['longitude']) != request['site'] or
            value['timezone'] != request['timezone']):
        raise ValueError('native calculation site/timezone mismatch')
    if site['altitude_m'] is not None:
        _number(site['altitude_m'], -500, 10000)
    observed = _instant(value['observed_at'])
    if value['observed_at'] != observed.isoformat() or observed < _instant(request['requested_at']):
        raise ValueError('original source acquisition availability required')
    return deepcopy(value)


def build_source(request, *, observed_at, native_runtime, source_status,
                 latitude, longitude, timezone_name, altitude_m):
    request = _request(request)
    value = dict(schema=SOURCE_SCHEMA, source_thing='astro:sun:local', status=source_status,
                 observed_at=_instant(observed_at).isoformat(),
                 site={**_site(latitude, longitude), 'altitude_m': altitude_m},
                 timezone=_zone(timezone_name), native_runtime=_runtime(native_runtime),
                 algorithm=ALGORITHM, resolution_us=1000)
    value['source_sha256'] = _digest(value, 'source_sha256')
    return _source(value, request)


def _positions(raw, request):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_OUTPUT_BYTES or not raw.endswith(b'\n'):
        raise ValueError('bounded original native batch output required')
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError:
        raise ValueError('native timestamp/numeric output required') from None
    if len(lines) != len(request['instants']):
        raise ValueError('complete exact native geometry coverage required')
    result = []
    for text, expected in zip(lines, request['instants']):
        columns = text.split('\t')
        if len(columns) != 3 or _instant(columns[0], exact=True).isoformat() != expected:
            raise ValueError('native requested timestamp/order mismatch')
        for number in columns[1:]:
            if re.fullmatch(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?', number) is None:
                raise ValueError('explicit finite native angle required')
        elevation = _number(float(columns[1]), -90, 90)
        azimuth = _number(float(columns[2]), 0, 360)
        result.append(dict(at=expected, elevation_degrees=elevation, azimuth_degrees=azimuth))
    return result


def _validate(value, request, expected_native_runtime):
    request = _request(request)
    if (not isinstance(value, dict) or set(value) != CACHE_FIELDS or
            value['schema'] != CACHE_SCHEMA or value['rule'] != SOLAR_RULE or
            value['cache_sha256'] != _digest(value, 'cache_sha256') or value['request'] != request):
        raise ValueError('original versioned native geometry cache required')
    _hash(value['cache_sha256']);source = _source(value['source'], request)
    if source['native_runtime'] != _runtime(expected_native_runtime):
        raise ValueError('native geometry runtime differs from original pin')
    computed = _instant(value['computed_at'])
    if value['computed_at'] != computed.isoformat() or computed < _instant(source['observed_at']):
        raise ValueError('native calculation chronology differs')
    if not isinstance(value['native_output'], str):
        raise ValueError('original native output required')
    rows = value['positions']
    if not isinstance(rows, list) or len(rows) != len(request['instants']):
        raise ValueError('complete native angle records required')
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'at', 'elevation_degrees', 'azimuth_degrees'}:
            raise ValueError('closed native angle record required')
        _number(row['elevation_degrees'], -90, 90)
        _number(row['azimuth_degrees'], 0, 360)
    raw = value['native_output'].encode()
    if (value['native_output_sha256'] != sha256(raw).hexdigest() or
            value['positions'] != _positions(raw, request)):
        raise ValueError('geometry differs from retained native calculation')
    if len(_canonical(value)) > MAX_CACHE_BYTES:
        raise ValueError('bounded native geometry cache required')
    return deepcopy(value)


class NativeGeometryCache:
    """Validated immutable bytes and angles; callers receive copies of records."""
    __slots__ = ('_encoded', '_times', '_angles')

    def __init__(self, value, *, request, expected_native_runtime):
        value = _validate(value, request, expected_native_runtime)
        object.__setattr__(self, '_encoded', _canonical(value))
        object.__setattr__(self, '_times', tuple(row['at'] for row in value['positions']))
        object.__setattr__(self, '_angles', tuple(row['elevation_degrees'] for row in value['positions']))

    def __setattr__(self, key, value):
        raise AttributeError('native geometry cache is immutable')

    @property
    def sha256(self):
        return self.to_dict()['cache_sha256']

    def to_dict(self):
        return json.loads(self._encoded)

    def elevation_degrees(self, at):
        key = _instant(at, exact=True).isoformat();index = bisect_left(self._times, key)
        if index == len(self._times) or self._times[index] != key:
            raise KeyError('requested native geometry unavailable')
        return self._angles[index]

    def elevation_sin(self, at):
        return math.sin(math.radians(self.elevation_degrees(at)))

    def is_thermal_night(self, at):
        return self.elevation_degrees(at) <= 0

    def descriptor(self):
        value = self.to_dict();source = value['source']
        return dict(rule=SOLAR_RULE, cache_sha256=value['cache_sha256'],
                    request_sha256=value['request']['request_sha256'],
                    source_sha256=source['source_sha256'], native_runtime=source['native_runtime'],
                    site=source['site'], timezone=source['timezone'], computed_at=value['computed_at'])


def build_cache(request, source, *, native_output, computed_at):
    request = _request(request);source = _source(source, request)
    positions = _positions(native_output, request)
    value = dict(schema=CACHE_SCHEMA, rule=SOLAR_RULE, request=request, source=source,
                 computed_at=_instant(computed_at).isoformat(), native_output=native_output.decode('ascii'),
                 native_output_sha256=sha256(native_output).hexdigest(), positions=positions)
    value['cache_sha256'] = _digest(value, 'cache_sha256')
    return NativeGeometryCache(value, request=request, expected_native_runtime=source['native_runtime'])


def replay_cache(raw, *, request, expected_cache_sha256, expected_native_runtime):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_CACHE_BYTES:
        raise ValueError('bounded retained geometry cache required')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:raise ValueError('duplicate geometry field')
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite geometry JSON')))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('retained geometry JSON required') from None
    if not isinstance(value, dict) or value.get('cache_sha256') != _hash(expected_cache_sha256):
        raise ValueError('retained geometry identity differs from original pin')
    return NativeGeometryCache(value, request=request, expected_native_runtime=expected_native_runtime)
