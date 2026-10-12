"""Versioned native solar development data preserve original evidence barriers."""
from copy import deepcopy
from datetime import timedelta
import importlib, json, math
import pytest
from test_installed_shade_inputs import snapshot, START, END, EPOCHS
from astro_geometry import build_source, build_cache
from astro_geometry_series import build_series_request, split_series_request, build_series

RUNTIME={'binding_version':'5.2.3','collector_sha256':'e'*64,
         'libraries':{'astro_binding':'a'*64,'openhab_core':'b'*64}}


def api():return importlib.import_module('native_thermal_inputs')


def geometry(record, *, degrees=20, missing=False):
    from datetime import datetime
    start, end=map(datetime.fromisoformat,(record['start'],record['end']))
    points=[];at=start
    while at<end:points.append(at);at+=timedelta(minutes=5)
    if missing:points.pop()
    request=build_series_request(points,requested_at=end,latitude=38.3739919,
                                longitude=-105.7744609,timezone_name='America/Denver')
    caches=[]
    for chunk in split_series_request(request):
        source=build_source(chunk,observed_at=end+timedelta(seconds=1),native_runtime=RUNTIME,
            source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,
            timezone_name='America/Denver',altitude_m=None)
        output=''.join(at+'\t'+str(degrees)+'\t180\n' for at in chunk['instants']).encode()
        caches.append(build_cache(chunk,source,native_output=output,computed_at=end+timedelta(seconds=2)))
    return build_series(request,caches,expected_native_runtime=RUNTIME)


def build(record, *, degrees=20, missing=False, assessed=END+timedelta(seconds=3)):
    g=geometry(record,degrees=degrees,missing=missing)
    return api().build_native_development(record,expected_snapshot_sha256=record['snapshot_sha256'],
        sensor_epochs=EPOCHS,geometry=g,expected_series_sha256=g.sha256,assessed_at=assessed)


def select(data):
    return api().select_native_endpoints(data,horizon_hours=1,start=START,end=END)


def test_native_dataset_replays_from_both_original_dependencies_and_versions_the_formula():
    record=snapshot();original=deepcopy(record);g=geometry(record)
    data=api().build_native_development(record,expected_snapshot_sha256=record['snapshot_sha256'],
        sensor_epochs=EPOCHS,geometry=g,expected_series_sha256=g.sha256,assessed_at=END+timedelta(seconds=3))
    assert data.to_dict()['schema']=='earthship-native-solar-development-data/v1'
    assert data.to_dict()['source_snapshot_sha256']==record['snapshot_sha256']
    assert data.to_dict()['geometry']['series_sha256']==g.sha256
    assert data.to_dict()['solar_feature']['rule']=='earthship-native-clear-sky-fraction/v2'
    restored=api().replay_native_development(json.dumps(data.to_dict()).encode(),record=record,
        expected_dataset_sha256=data.sha256,expected_snapshot_sha256=record['snapshot_sha256'],
        sensor_epochs=EPOCHS,geometry=g,expected_series_sha256=g.sha256)
    assert restored.to_dict()==data.to_dict() and record==original
    point=select(restored)[0]
    assert len(point.forcings)==12 and point.origin.at==START
    assert all(row.indoor_shade_closed==0 and row.vent_open==0 for row in point.forcings)
    assert restored.release_authorized is False


@pytest.mark.parametrize('role',['air','mass'])
def test_missing_interior_temperature_is_preserved_but_endpoint_weather_remains_supported(role):
    data=build(snapshot(missing=role))
    assert START+timedelta(minutes=30) not in {row.at for row in data.development.samples}
    assert len(select(data))==1


@pytest.mark.parametrize('role',['outdoor','radiation'])
def test_missing_or_invalid_original_forcing_cannot_enter_native_endpoints(role):
    assert select(build(snapshot(missing=role)))==()


def test_native_night_does_not_replace_an_explicit_invalid_radiation_reading():
    data=build(snapshot(missing='radiation'),degrees=-1)
    assert START+timedelta(minutes=30) not in {row.at for row in data.development.weather}
    assert select(data)==()


def test_interpolated_radiation_remains_unqualified_even_at_native_night():
    data=build(snapshot(radiation_gap=True),degrees=-1)
    assert START+timedelta(minutes=30) not in {row.at for row in data.development.weather}
    assert select(data)==()


@pytest.mark.parametrize('action,state',[('outdoor_shade','removed'),('kiva','on')])
def test_future_domain_or_heat_changes_keep_the_original_whole_window_barrier(action,state):
    assert select(build(snapshot(future_action=(action,state))))==()


def test_late_received_action_cannot_be_backfilled_into_a_native_origin():
    assert select(build(snapshot(late_indoor=True)))==()


@pytest.mark.parametrize('damage',['missing_geometry','future_geometry','wrong_series_pin'])
def test_native_geometry_must_completely_cover_the_dataset_and_be_available(damage):
    record=snapshot();g=geometry(record,missing=damage=='missing_geometry')
    with pytest.raises(ValueError):api().build_native_development(record,
        expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=EPOCHS,geometry=g,
        expected_series_sha256='f'*64 if damage=='wrong_series_pin' else g.sha256,
        assessed_at=END if damage=='future_geometry' else END+timedelta(seconds=3))


def test_native_clear_sky_fraction_uses_only_pinned_geometry_and_preserves_bounds():
    record=snapshot();g=geometry(record,degrees=30)
    # sin(30)=0.5; literal formula from the unchanged calibration constants.
    expected=200/(1050*0.5**1.15)
    assert api().native_clear_sky_fraction(200,START,geometry=g)==pytest.approx(expected)
    assert api().native_clear_sky_fraction(1600,START,geometry=g)==1.3
    assert api().native_clear_sky_fraction(0,START,geometry=g)==0
    assert api().native_clear_sky_fraction(200,START,geometry=geometry(record,degrees=-1))==0
    with pytest.raises(KeyError):api().native_clear_sky_fraction(200,END,geometry=g)
    with pytest.raises(ValueError):api().native_clear_sky_fraction(float('nan'),START,geometry=g)


def test_native_data_are_immutable_and_corrupt_replay_cannot_reseal_measurements():
    record=snapshot();g=geometry(record);data=build(record);value=data.to_dict()
    value['samples'][0]['air_f']=90
    with pytest.raises(ValueError):api().replay_native_development(json.dumps(value).encode(),record=record,
        expected_dataset_sha256=data.sha256,expected_snapshot_sha256=record['snapshot_sha256'],
        sensor_epochs=EPOCHS,geometry=g,expected_series_sha256=g.sha256)
    value=data.to_dict();value['samples'].clear();assert data.development.samples
    with pytest.raises(AttributeError):data.development=()



def recapture(record):
    from datetime import datetime
    from thermal_model.training_inputs import _Series, _Journal, capture_training_inputs_v2
    start,end=map(datetime.fromisoformat,(record['start'],record['end']))
    return capture_training_inputs_v2(start=start,end=end,series_reader=_Series(record),
        journal=_Journal(record),clock=lambda:end,revision_reader=lambda:record['collection_code_revision'])


def test_missing_station_radiation_uses_only_native_night_and_records_inference():
    record=snapshot();record['series_by_role']['radiation']=[];record=recapture(record)
    data=build(record,degrees=-1)
    assert len(data.development.samples)==14 and len(data.development.weather)==14
    assert {row.radiation_provenance for row in data.development.weather}=={'native_solar_night_zero'}
    assert all(row.radiation_wm2==0 for row in data.development.weather)
    assert len(select(data))==1
    assert build(record,degrees=20).development.samples==()


def test_native_day_discards_every_legacy_inferred_night_zero(monkeypatch):
    import test_installed_shade_inputs as source_fixture
    from datetime import datetime
    monkeypatch.setattr(source_fixture,'START',START+timedelta(hours=12))
    record=source_fixture.snapshot();record['series_by_role']['radiation']=[];record=recapture(record)
    # The source snapshot was genuinely rebuilt using the prior nighttime rule.
    assert record['dataset_manifest']['radiation_provenance_counts']['astronomical_night_zero']==14
    data=build(record,degrees=20,assessed=datetime.fromisoformat(record['end'])+timedelta(seconds=3))
    assert data.development.samples==() and data.development.weather==()
    assert data.to_dict()['quality']['rejected_counts']['missing_required']==14


def test_native_daylight_changes_only_historical_reconstruction_and_manual_unknown_wins():
    record=snapshot();record['events']=[e for e in record['events'] if e['action']=='outdoor_shade'];record=recapture(record)
    day=build(record,degrees=20).development.samples[0]
    night=build(record,degrees=-1).development.samples[0]
    assert (day.vent_open,day.indoor_shade_closed)==(0,1)
    assert (night.vent_open,night.indoor_shade_closed)==(1,0)
    assert day.vent_confidence==night.vent_confidence==0.35
    record=snapshot();record['events'][2]['state']='unknown';record=recapture(record)
    assert build(record,degrees=-1).development.samples[0].vent_open is None



def test_native_endpoint_identity_cannot_be_consumed_by_the_legacy_geometry_fitter():
    from thermal_model.installed_shade_fit import _prepare_batches
    data=build(snapshot());points=select(data)
    with pytest.raises(ValueError):_prepare_batches(points)
    assert points[0].dataset_sha256==data.sha256
    assert points[0].series_sha256==data.geometry.sha256
