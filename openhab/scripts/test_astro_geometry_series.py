"""Complete multi-batch native coverage, including externally pinned replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib, json, math
import pytest
from astro_geometry import build_source, build_cache

NOW = datetime(2026, 10, 12, 22, tzinfo=timezone.utc)
RUNTIME = {'binding_version': '5.2.3', 'collector_sha256': 'e'*64,
           'libraries': {'astro_binding': 'a'*64, 'openhab_core': 'b'*64}}


def api(): return importlib.import_module('astro_geometry_series')


def fixtures(count=257):
    points = [NOW + timedelta(minutes=5*i) for i in range(count)]
    request = api().build_series_request(points, requested_at=NOW,
        latitude=38.3739919, longitude=-105.7744609, timezone_name='America/Denver')
    caches = []
    for index, chunk in enumerate(api().split_series_request(request)):
        source = build_source(chunk, observed_at=NOW+timedelta(seconds=index+1),
            native_runtime=RUNTIME, source_status='ONLINE', latitude=38.3739919,
            longitude=-105.7744609, timezone_name='America/Denver', altitude_m=None)
        # Literal synthetic native angles; crosses the horizon between batches.
        degrees = (-1, 0, 20)[index % 3]
        output = ''.join(at + '\t' + str(degrees) + '\t180\n' for at in chunk['instants']).encode()
        caches.append(build_cache(chunk, source, native_output=output,
            computed_at=NOW+timedelta(seconds=index+2)))
    return points, request, caches


def seal(value):
    value['series_sha256'] = sha256(json.dumps({k:v for k,v in value.items() if k!='series_sha256'},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return value


def test_complete_three_batch_coverage_replays_without_services():
    points, request, caches = fixtures()
    series = api().build_series(request, caches, expected_native_runtime=RUNTIME)
    assert [len(c.to_dict()['positions']) for c in caches] == [128, 128, 1]
    restored = api().replay_series(json.dumps(series.to_dict()).encode(), request=request,
        expected_series_sha256=series.sha256, expected_native_runtime=RUNTIME)
    assert restored.to_dict() == series.to_dict()
    assert restored.elevation_degrees(points[0]) == -1
    assert restored.elevation_degrees(points[128]) == 0
    assert restored.elevation_sin(points[-1]) == pytest.approx(math.sin(math.radians(20)))
    assert restored.is_thermal_night(points[0]) and restored.is_thermal_night(points[128])
    assert not restored.is_thermal_night(points[-1])
    assert restored.descriptor()['available_at'] == (NOW+timedelta(seconds=4)).isoformat()
    assert restored.descriptor()['point_count'] == 257


@pytest.mark.parametrize('damage', ['missing', 'reordered', 'overlap', 'extra'])
def test_series_refuses_partial_reordered_or_extra_native_batches(damage):
    _, request, caches = fixtures()
    if damage == 'missing': caches.pop()
    if damage == 'reordered': caches.reverse()
    if damage == 'overlap': caches[1] = caches[0]
    if damage == 'extra': caches.append(caches[-1])
    with pytest.raises(ValueError): api().build_series(request, caches, expected_native_runtime=RUNTIME)


@pytest.mark.parametrize('damage', ['request', 'geometry', 'runtime', 'source', 'extra_field'])
def test_resealed_series_still_validates_each_original_native_cache(damage):
    _, request, caches = fixtures(1)
    series = api().build_series(request, caches, expected_native_runtime=RUNTIME)
    value = series.to_dict(); cache = value['caches'][0]
    if damage == 'request': cache['request']['site']['latitude'] = 39
    if damage == 'geometry': cache['positions'][0]['elevation_degrees'] = 30
    if damage == 'runtime': cache['source']['native_runtime']['libraries']['astro_binding'] = 'f'*64
    if damage == 'source': cache['source']['timezone'] = 'UTC'
    if damage == 'extra_field': value['authorizes_action'] = True
    seal(value)
    with pytest.raises(ValueError): api().replay_series(json.dumps(value).encode(), request=request,
        expected_series_sha256=value['series_sha256'], expected_native_runtime=RUNTIME)


def test_series_cannot_change_original_external_request_or_runtime_pins():
    _, request, caches = fixtures(1)
    series = api().build_series(request, caches, expected_native_runtime=RUNTIME)
    altered = deepcopy(request); altered['instants'][0] = (NOW+timedelta(seconds=1)).isoformat()
    altered['request_sha256'] = sha256(json.dumps({k:v for k,v in altered.items() if k!='request_sha256'},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    runtime = deepcopy(RUNTIME); runtime['binding_version'] = '5.2.4'
    for original, identity in ((altered, RUNTIME), (request, runtime)):
        with pytest.raises(ValueError): api().replay_series(json.dumps(series.to_dict()).encode(),
            request=original, expected_series_sha256=series.sha256, expected_native_runtime=identity)


def test_series_data_are_copies_and_missing_geometry_never_falls_back():
    points, request, caches = fixtures(1)
    series = api().build_series(request, caches, expected_native_runtime=RUNTIME)
    value = series.to_dict(); value['caches'][0]['positions'][0]['elevation_degrees'] = 60
    assert series.elevation_degrees(points[0]) == -1
    with pytest.raises(KeyError): series.elevation_sin(NOW+timedelta(minutes=1))
    with pytest.raises(AttributeError): series._angles = (60,)


@pytest.mark.parametrize('kind', ['empty', 'oversize', 'submillisecond'])
def test_complete_series_request_has_a_finite_exact_coverage_budget(kind):
    points = [] if kind == 'empty' else [NOW+timedelta(seconds=i) for i in range(8193)] if kind == 'oversize' else ['2026-10-12T22:00:00.000000001+00:00']
    with pytest.raises(ValueError): api().build_series_request(points, requested_at=NOW,
        latitude=38.3739919, longitude=-105.7744609, timezone_name='America/Denver')


def test_unpinned_or_duplicate_json_cannot_replay():
    _, request, caches = fixtures(1)
    series = api().build_series(request, caches, expected_native_runtime=RUNTIME)
    raw = json.dumps(series.to_dict()).encode()
    duplicate = raw.replace(b'{', b'{"schema":"duplicate",', 1)
    for content, identity in ((raw, 'f'*64), (duplicate, series.sha256)):
        with pytest.raises(ValueError): api().replay_series(content, request=request,
            expected_series_sha256=identity, expected_native_runtime=RUNTIME)
