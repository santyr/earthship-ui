"""Complete immutable native geometry coverage assembled from bounded batches.

The series binds original native calculations to one exact requested timestamp
set. It does not acquire data, fit models, infer measured irradiance, or grant
release/control authority. Consumers must version their dataset/model contract.
"""
from bisect import bisect_left
from copy import deepcopy
import json
import math
import astro_geometry as geometry

REQUEST_SCHEMA = 'earthship-astro-geometry-series-request/v1'
SERIES_SCHEMA = 'earthship-native-solar-geometry-series/v1'
MAX_POINTS, BATCH_POINTS, MAX_BYTES = 8192, 128, 4 * 1024 * 1024
REQUEST_FIELDS = geometry.REQUEST_FIELDS
SERIES_FIELDS = {'schema', 'rule', 'request', 'native_runtime', 'caches', 'series_sha256'}


def _request(value):
    if (not isinstance(value, dict) or set(value) != REQUEST_FIELDS or
            value['schema'] != REQUEST_SCHEMA or
            value['request_sha256'] != geometry._digest(value, 'request_sha256')):
        raise ValueError('original complete geometry series request required')
    geometry._hash(value['request_sha256']); geometry._zone(value['timezone'])
    site = value['site']
    if (not isinstance(site, dict) or set(site) != {'latitude', 'longitude'} or
            site != geometry._site(**site)):
        raise ValueError('explicit series site required')
    requested = geometry._instant(value['requested_at'])
    if value['requested_at'] != requested.isoformat():
        raise ValueError('canonical original series availability required')
    points = value['instants']
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError('bounded complete native series required')
    canonical = [geometry._instant(at, exact=True).isoformat() for at in points]
    if points != canonical or points != sorted(set(points)):
        raise ValueError('ordered unique exact native series instants required')
    return deepcopy(value)


def build_series_request(instants, *, requested_at, latitude, longitude, timezone_name):
    if not isinstance(instants, (list, tuple)) or not 1 <= len(instants) <= MAX_POINTS:
        raise ValueError('bounded complete native series required')
    value = dict(schema=REQUEST_SCHEMA,
        requested_at=geometry._instant(requested_at).isoformat(),
        site=geometry._site(latitude, longitude), timezone=geometry._zone(timezone_name),
        instants=sorted({geometry._instant(at, exact=True).isoformat() for at in instants}))
    value['request_sha256'] = geometry._digest(value, 'request_sha256')
    return _request(value)


def split_series_request(request):
    """Return deterministic complete requests, each within the native worker bound."""
    request = _request(request); points = request['instants']
    return [geometry.build_request(points[i:i+BATCH_POINTS],
        requested_at=request['requested_at'], latitude=request['site']['latitude'],
        longitude=request['site']['longitude'], timezone_name=request['timezone'])
        for i in range(0, len(points), BATCH_POINTS)]


def _validate(value, request, expected_native_runtime):
    request = _request(request); runtime = geometry._runtime(expected_native_runtime)
    if (not isinstance(value, dict) or set(value) != SERIES_FIELDS or
            value['schema'] != SERIES_SCHEMA or value['rule'] != geometry.SOLAR_RULE or
            value['series_sha256'] != geometry._digest(value, 'series_sha256')):
        raise ValueError('original versioned native geometry series required')
    geometry._hash(value['series_sha256'])
    if _request(value['request']) != request or geometry._runtime(value['native_runtime']) != runtime:
        raise ValueError('series request/runtime differs from original pins')
    chunks = split_series_request(request); caches = value['caches']
    if not isinstance(caches, list) or len(caches) != len(chunks):
        raise ValueError('complete bounded native batch coverage required')
    site = None
    for cache, chunk in zip(caches, chunks):
        if not isinstance(cache, dict):
            raise ValueError('retained original native batch required')
        if geometry._request(cache.get('request')) != chunk:
            raise ValueError('exact ordered native batch coverage required')
        restored = geometry.replay_cache(geometry._canonical(cache), request=chunk,
            expected_cache_sha256=cache.get('cache_sha256'), expected_native_runtime=runtime)
        original = restored.to_dict()['source']['site']
        if site is not None and original != site:
            raise ValueError('configured native site changed between batches')
        site = original
    if len(geometry._canonical(value)) > MAX_BYTES:
        raise ValueError('bounded retained native series required')
    return deepcopy(value)


class NativeGeometrySeries:
    """Exact geometry lookup with immutable retained originals and no fallback."""
    __slots__ = ('_encoded', '_times', '_angles', '_sha256')

    def __init__(self, value, *, request, expected_native_runtime):
        value = _validate(value, request, expected_native_runtime)
        rows = [row for cache in value['caches'] for row in cache['positions']]
        object.__setattr__(self, '_encoded', geometry._canonical(value))
        object.__setattr__(self, '_times', tuple(row['at'] for row in rows))
        object.__setattr__(self, '_angles', tuple(row['elevation_degrees'] for row in rows))
        object.__setattr__(self, '_sha256', value['series_sha256'])

    def __setattr__(self, key, value):
        raise AttributeError('native geometry series is immutable')

    @property
    def sha256(self): return self._sha256

    def to_dict(self): return json.loads(self._encoded)

    def elevation_degrees(self, at):
        key = geometry._instant(at, exact=True).isoformat(); index = bisect_left(self._times, key)
        if index == len(self._times) or self._times[index] != key:
            raise KeyError('requested native series geometry unavailable')
        return self._angles[index]

    def elevation_sin(self, at): return math.sin(math.radians(self.elevation_degrees(at)))

    def is_thermal_night(self, at): return self.elevation_degrees(at) <= 0

    def descriptor(self):
        value = self.to_dict(); caches = value['caches']
        return dict(rule=geometry.SOLAR_RULE, series_sha256=self.sha256,
            request_sha256=value['request']['request_sha256'],
            native_runtime=value['native_runtime'], site=caches[0]['source']['site'],
            timezone=value['request']['timezone'], point_count=len(self._times),
            available_at=max(cache['computed_at'] for cache in caches),
            cache_sha256s=[cache['cache_sha256'] for cache in caches])


def build_series(request, caches, *, expected_native_runtime):
    request = _request(request); chunks = split_series_request(request)
    if (not isinstance(caches, (list, tuple)) or len(caches) != len(chunks) or
            any(type(cache) is not geometry.NativeGeometryCache for cache in caches)):
        raise ValueError('complete validated original native batches required')
    value = dict(schema=SERIES_SCHEMA, rule=geometry.SOLAR_RULE, request=request,
        native_runtime=geometry._runtime(expected_native_runtime),
        caches=[cache.to_dict() for cache in caches])
    value['series_sha256'] = geometry._digest(value, 'series_sha256')
    return NativeGeometrySeries(value, request=request, expected_native_runtime=expected_native_runtime)


def replay_series(raw, *, request, expected_series_sha256, expected_native_runtime):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('bounded retained native series required')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('duplicate native series field')
            value[key] = item
        return value
    def nonfinite(_): raise ValueError('nonfinite native series JSON')
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('retained native series JSON required') from None
    if not isinstance(value, dict) or value.get('series_sha256') != geometry._hash(expected_series_sha256):
        raise ValueError('native series differs from original external identity')
    return NativeGeometrySeries(value, request=request, expected_native_runtime=expected_native_runtime)
