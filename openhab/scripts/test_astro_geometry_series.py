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

# Terrain daylight uses complete original cache replay, never live astronomy.
def daylight_fixture(day='2026-10-20', *, angles=None, omit=None, available=None,
                     latitude=38.3739919, timezone_name='America/Denver'):
    from pathlib import Path
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(timezone_name)
    start_local = datetime.fromisoformat(day).replace(tzinfo=zone)
    start = start_local.astimezone(timezone.utc)
    end = (start_local + timedelta(days=1)).astimezone(timezone.utc)
    now = start + timedelta(hours=12)
    available = available or now - timedelta(hours=1)
    points = [start + timedelta(seconds=300*i) for i in range(1, int((end-start).total_seconds())//300+1)
              if i != omit]
    request = api().build_series_request(points, requested_at=available-timedelta(seconds=2),
        latitude=latitude, longitude=-105.7744609, timezone_name=timezone_name)
    caches = []
    for chunk in api().split_series_request(request):
        source = build_source(chunk, observed_at=available-timedelta(seconds=1),
            native_runtime=RUNTIME, source_status='ONLINE', latitude=latitude,
            longitude=-105.7744609, timezone_name=timezone_name, altitude_m=None)
        rows = []
        for at in chunk['instants']:
            index = int((datetime.fromisoformat(at)-start).total_seconds())//300
            elevation, azimuth = (angles or {}).get(index, (-5, 180))
            rows.append(f'{at}\t{elevation}\t{azimuth}\n')
        caches.append(build_cache(chunk, source, native_output=''.join(rows).encode(), computed_at=available))
    series = api().build_series(request, caches, expected_native_runtime=RUNTIME)
    horizon = json.loads((Path(__file__).resolve().parents[2]/'openhab/household-solar-horizon.json').read_bytes())
    horizon['recorded_at'] = horizon['source']['retrieved_at'] = (available-timedelta(hours=1)).isoformat()
    for row in horizon['profile']: row['elevation_degrees'] = 10
    return json.dumps(series.to_dict()).encode(), json.dumps(horizon).encode(), now, start, end


def daylight_api(): return importlib.import_module('site_daylight')


def test_terrain_daylight_masks_native_angles_and_returns_only_closed_public_evidence():
    from household.codec import identity
    raw, horizon, now, start, end = daylight_fixture(angles={1:(5,180),2:(5,180),4:(20,180),5:(5,0),6:(0,180)})
    report = daylight_api().project_day(raw, horizon, now)
    value = json.loads(raw)
    assert report == dict(schema='earthship-terrain-daylight/v1',
        method='native-five-minute-terrain-endpoint-mask/v1', day='2026-10-20', timezone='America/Denver',
        calculatedAt=now.isoformat(), dayStartAt=start.isoformat(), validUntil=end.isoformat(),
        geometryAvailableAt=value['caches'][0]['computed_at'], geometrySha256=value['series_sha256'],
        horizonSha256=sha256(horizon).hexdigest(), sourceRuntimeSha256=identity(RUNTIME), daySeconds=86400,
        terrainSunlightSeconds=300, unobstructedSunlightSeconds=1200,
        firstSunAt=(start+timedelta(minutes=15)).isoformat(), lastSunAt=(start+timedelta(minutes=20)).isoformat(),
        resolutionSeconds=300, confidence='unvalidated_map_estimate', physical_calibration_qualified=False,
        automatic_actuation=False)
    flat = json.loads(horizon)
    for row in flat['profile']: row['elevation_degrees'] = 0
    assert daylight_api().project_day(raw,json.dumps(flat).encode(),now)['terrainSunlightSeconds'] == 1200


def test_terrain_daylight_sums_disjoint_windows_rather_than_first_to_last_span():
    raw, horizon, now, start, _ = daylight_fixture(angles={1:(20,180),2:(20,180),4:(20,180)})
    report = daylight_api().project_day(raw,horizon,now)
    assert report['terrainSunlightSeconds'] == 900
    assert report['firstSunAt'] == start.isoformat()
    assert report['lastSunAt'] == (start+timedelta(minutes=20)).isoformat()


def test_terrain_daylight_wraps_true_north_and_excludes_equality_with_skyline():
    raw, horizon, now, _, _ = daylight_fixture(angles={1:(10,356.25),2:(10.1,356.25),3:(0,0)})
    body=json.loads(horizon);body['profile'][-1]['elevation_degrees']=20;body['profile'][0]['elevation_degrees']=0
    report=daylight_api().project_day(raw,json.dumps(body).encode(),now)
    assert report['terrainSunlightSeconds']==300
    assert report['unobstructedSunlightSeconds']==600


def test_terrain_daylight_zero_sun_is_known_zero_with_no_synthetic_boundaries():
    raw,horizon,now,_,_=daylight_fixture()
    report=daylight_api().project_day(raw,horizon,now)
    assert report['terrainSunlightSeconds']==report['unobstructedSunlightSeconds']==0
    assert report['firstSunAt'] is None and report['lastSunAt'] is None


@pytest.mark.parametrize('day,seconds', [('2026-03-08',82800),('2026-11-01',90000)])
def test_terrain_daylight_uses_actual_denver_dst_day_endpoints(day,seconds):
    raw,horizon,now,start,end=daylight_fixture(day,angles={1:(20,180),seconds//300:(20,180)})
    report=daylight_api().project_day(raw,horizon,now)
    assert report['daySeconds']==seconds
    assert report['terrainSunlightSeconds']==600
    assert report['firstSunAt']==start.isoformat() and report['lastSunAt']==end.isoformat()


@pytest.mark.parametrize('damage', ['site','timezone','previous_day','future','tampered','gap','naive','horizon_future','horizon_shape','duplicate'])
def test_terrain_daylight_refuses_missing_or_incompatible_original_evidence(damage):
    raw,horizon,now,_,_=daylight_fixture()
    if damage=='site': raw,_,_,_,_=daylight_fixture(latitude=39)
    if damage=='timezone': raw,_,_,_,_=daylight_fixture(timezone_name='UTC')
    if damage=='previous_day': raw,_,_,_,_=daylight_fixture('2026-10-19')
    if damage=='future': raw,_,_,_,_=daylight_fixture(available=now+timedelta(seconds=1))
    if damage=='gap': raw,_,_,_,_=daylight_fixture(omit=15)
    if damage=='tampered':
        value=json.loads(raw);value['caches'][0]['positions'][0]['elevation_degrees']=70;raw=json.dumps(seal(value)).encode()
    if damage=='naive':now=now.replace(tzinfo=None)
    if damage=='horizon_future':
        body=json.loads(horizon);body['recorded_at']=(now+timedelta(seconds=1)).isoformat();horizon=json.dumps(body).encode()
    if damage=='horizon_shape':
        body=json.loads(horizon);body['unknown']=True;horizon=json.dumps(body).encode()
    if damage=='duplicate':raw=raw.replace(b'{',b'{"schema":"duplicate",',1)
    with pytest.raises(ValueError):daylight_api().project_day(raw,horizon,now)


def private_daylight_cache(tmp_path, *, angles=None):
    raw,horizon,now,_,_=daylight_fixture(angles=angles)
    root=tmp_path/'geometry';root.mkdir(mode=0o700)
    path=root/'original.geometry.json';path.write_bytes(raw);path.chmod(0o600)
    horizon_path=tmp_path/'horizon.json';horizon_path.write_bytes(horizon);horizon_path.chmod(0o644)
    return root,path,horizon_path,now


def test_terrain_daylight_cache_and_cli_are_read_only_and_never_emit_private_inputs(tmp_path,capsys):
    root,path,horizon,now=private_daylight_cache(tmp_path,angles={1:(20,180)})
    before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (path,horizon)}
    assert daylight_api().main(['--geometry-root',str(root),'--horizon',str(horizon)],clock=lambda:now)==0
    output=capsys.readouterr();report=json.loads(output.out)
    assert report['terrainSunlightSeconds']==300 and output.err==''
    assert all(text not in output.out for text in (str(tmp_path),'latitude','longitude','native_output'))
    assert {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (path,horizon)}==before
    assert len(output.out.encode())<=16384


@pytest.mark.parametrize('damage',['missing','empty','public_root','public_file','symlink_file','hardlink','symlink_root','horizon_writable','horizon_symlink','oversize','too_many','mutated'])
def test_terrain_daylight_cache_refuses_unsafe_or_unavailable_inputs(tmp_path,capsys,monkeypatch,damage):
    import os
    root,path,horizon,now=private_daylight_cache(tmp_path)
    if damage=='missing': root=tmp_path/'missing'
    if damage=='empty':path.unlink()
    if damage=='public_root':root.chmod(0o755)
    if damage=='public_file':path.chmod(0o644)
    if damage=='symlink_file':
        other=tmp_path/'other';path.rename(other);path.symlink_to(other)
    if damage=='hardlink':os.link(path,tmp_path/'hardlink')
    if damage=='symlink_root':
        link=tmp_path/'link';link.symlink_to(root,target_is_directory=True);root=link
    if damage=='horizon_writable':horizon.chmod(0o666)
    if damage=='horizon_symlink':
        link=tmp_path/'horizon-link';link.symlink_to(horizon);horizon=link
    if damage=='oversize':path.write_bytes(b' '*524289)
    if damage=='too_many':
        for i in range(8192):
            extra=root/f'{i}.geometry.json';extra.write_bytes(b'{}');extra.chmod(0o600)
    if damage=='mutated':
        original=os.read
        def changing(fd,size):
            result=original(fd,size)
            if result:
                with path.open('ab') as stream:stream.write(b' ')
            return result
        monkeypatch.setattr(daylight_api().os,'read',changing)
    assert daylight_api().main(['--geometry-root',str(root),'--horizon',str(horizon)],clock=lambda:now)==1
    output=capsys.readouterr()
    assert json.loads(output.out)=={'status':'unavailable'}
    assert output.err=='Terrain daylight unavailable.\n'
    assert str(tmp_path) not in output.out+output.err


def test_terrain_daylight_cache_selects_newest_available_qualified_series(tmp_path):
    root,path,horizon,now=private_daylight_cache(tmp_path,angles={1:(20,180)})
    newer,_,_,_,_=daylight_fixture(angles={1:(20,180),2:(20,180)},available=now-timedelta(minutes=1))
    fresh=root/'new.geometry.json';fresh.write_bytes(newer);fresh.chmod(0o600)
    invalid=root/'bad.geometry.json';invalid.write_bytes(b'{}');invalid.chmod(0o600)
    future,_,_,_,_=daylight_fixture(available=now+timedelta(seconds=1))
    future_path=root/'future.geometry.json';future_path.write_bytes(future);future_path.chmod(0o600)
    assert daylight_api().read_day(root,horizon,now)['terrainSunlightSeconds']==600


def test_terrain_daylight_refuses_cache_population_change_during_replay(tmp_path,monkeypatch):
    root,path,horizon,now=private_daylight_cache(tmp_path)
    original=daylight_api().project_day
    def changed(raw,horizon_raw,at):
        report=original(raw,horizon_raw,at)
        arrival=root/'arriving.geometry.json';arrival.write_bytes(path.read_bytes());arrival.chmod(0o600)
        return report
    monkeypatch.setattr(daylight_api(),'project_day',changed)
    with pytest.raises(ValueError):daylight_api().read_day(root,horizon,now)


def test_terrain_daylight_cache_deadline_returns_generic_unavailable(tmp_path,capsys,monkeypatch):
    root,_,horizon,now=private_daylight_cache(tmp_path)
    ticks=iter([0,9])
    monkeypatch.setattr(daylight_api().timing,'monotonic',lambda:next(ticks))
    assert daylight_api().main(['--geometry-root',str(root),'--horizon',str(horizon)],clock=lambda:now)==1
    output=capsys.readouterr()
    assert json.loads(output.out)=={'status':'unavailable'} and output.err=='Terrain daylight unavailable.\n'


def test_terrain_daylight_invalid_cli_does_not_reflect_private_arguments(capsys):
    assert daylight_api().main(['--unknown=/private/site/coordinates'])==1
    output=capsys.readouterr()
    assert json.loads(output.out)=={'status':'unavailable'}
    assert output.err=='Terrain daylight unavailable.\n'


def test_terrain_daylight_long_lived_cache_prefilters_historical_originals(tmp_path,monkeypatch):
    root,path,horizon,now=private_daylight_cache(tmp_path,angles={1:(20,180)})
    # Distinct, fully sealed historical native series, with no pruning or index.
    for i in range(1,130):
        day=(datetime(2026,10,20)-timedelta(days=i)).date().isoformat()
        raw,_,_,_,_=daylight_fixture(day)
        old=root/f'{i:04}.geometry.json';old.write_bytes(raw);old.chmod(0o600)
    original=daylight_api().project_day
    replayed=[]
    def tracked(raw,horizon_raw,at):
        replayed.append(json.loads(raw)['request']['instants'][0])
        return original(raw,horizon_raw,at)
    monkeypatch.setattr(daylight_api(),'project_day',tracked)
    report=daylight_api().read_day(root,horizon,now)
    assert report['terrainSunlightSeconds']==300
    assert len(replayed)==1  # Historical requests never reach costly native replay.
    assert len(list(root.glob('*.geometry.json')))==130


@pytest.mark.parametrize('raw', [b'[]',b'null',b'"scalar"',b'1',b'true'])
def test_terrain_daylight_skips_nonobject_json_without_losing_valid_current_cache(tmp_path,raw):
    root,_,horizon,now=private_daylight_cache(tmp_path,angles={1:(20,180)})
    malformed=root/'nonobject.geometry.json';malformed.write_bytes(raw);malformed.chmod(0o600)
    assert daylight_api().read_day(root,horizon,now)['terrainSunlightSeconds']==300
