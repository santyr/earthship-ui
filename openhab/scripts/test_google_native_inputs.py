"""Actual native adapters accept Google originals without legacy forecast SQL."""
from copy import deepcopy
from datetime import timedelta
import importlib
from pathlib import Path
from uuid import uuid4
import pytest
from weather_learning.tests.learning_fixtures import T,SITE,full_snapshot
from weather_learning.native_forecast import make_native_forecast
from weather_learning.archive import Archive

ORIGIN=T+timedelta(hours=8,minutes=15)
KNOWN=ORIGIN-timedelta(seconds=30)
ACTIONS=dict(indoor_shade_closed=.65,outdoor_shade_present=1.,vent_open=0.)

def test_native_forcing_uses_original_google_rows_without_a_weather_code_or_six_hour_incumbent_limit(monkeypatch):
    from thermal_model.installed_shade_origin import _forecast_forcing
    from thermal_model import forecast_history
    monkeypatch.setattr(forecast_history,'fetch_origin_forecast_with_receipts',lambda *a,**kw:pytest.fail('legacy forecast SQL'),raising=False)
    value=make_native_forecast(full_snapshot(),origin=ORIGIN,available_by=KNOWN,horizon_hours=24,site=SITE)
    forcings=_forecast_forcing(value,ORIGIN,ORIGIN,ACTIONS)
    assert len(forcings)==288 and forcings[0].at==ORIGIN+timedelta(minutes=5)
    assert forcings[0].outdoor_f==50 and forcings[0].radiation_wm2==100
    assert forcings[0].indoor_shade_closed==.65 and forcings[0].vent_open==0
    assert value['source']=='weathernext3' and value['rows'][0]['weatherCode'] is None

def test_google_cannot_be_relabelled_as_old_metric_receipts():
    from thermal_model.forecast_history import verify_origin_forecast_receipts
    from weather_learning.contracts import identity
    value=make_native_forecast(full_snapshot(),origin=ORIGIN,available_by=KNOWN,horizon_hours=24,site=SITE)
    value['source']='open_meteo_openhab';value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
    with pytest.raises(ValueError):verify_origin_forecast_receipts(value)

def test_google_backend_constructor_does_not_read_or_require_forecast_database_credentials(tmp_path,monkeypatch):
    from weather_learning.native_backend import make_native_backend,SCHEMA
    import thermal_temperature_runtime
    from test_thermal_sensor_epoch_history import EPOCHS
    from thermal_model.installed_shade_live_inputs import SOURCE_PATHS
    monkeypatch.setattr(thermal_temperature_runtime,'_configured_sensor_epochs',lambda env:deepcopy(EPOCHS))
    tmp_path.chmod(0o700);settings={}
    for name in SOURCE_PATHS-{'forecast_dsn_file'}:
        path=tmp_path/name;path.write_text('host=127.0.0.1 dbname=openhab user=fixture_reader password='+uuid4().hex if name=='journal_dsn_file' else uuid4().hex)
        path.chmod(0o600);settings[name]=str(path)
    settings.update(schema=SCHEMA,openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(tmp_path/'evidence'))
    archive=Archive(tmp_path/'google');archive.store_snapshot(full_snapshot())
    backend=make_native_backend(settings,archive=archive,site=SITE,shared_lock_guard=lambda:None)
    backend.verify_unchanged()
    assert not hasattr(backend,'forecast_dsn')
    value=backend.forecast_reader(issue=ORIGIN,available_by=KNOWN,horizon_hours=24)
    assert value['source']=='weathernext3'
    assert 'forecast_dsn_file' not in backend.settings

def test_missing_google_source_never_queries_old_forecast_database(tmp_path,monkeypatch):
    from test_installed_shade_live_inputs import source_backend_case
    from thermal_model import forecast_history
    backend,known,_,connections=source_backend_case(tmp_path,monkeypatch)
    backend.forecast_reader=lambda **kw:None
    monkeypatch.setattr(forecast_history,'fetch_pending_origin_forecast_with_receipts',lambda *a,**kw:pytest.fail('legacy weather fallback'),raising=False)
    with pytest.raises(ValueError,match='weather unavailable'):backend.collect(issue=known+timedelta(seconds=30),known_at=known)
    assert connections==[]

def test_native_backend_retains_local_original_sources_with_google_weather(tmp_path,monkeypatch):
    from test_installed_shade_live_inputs import source_backend_case
    from thermal_model import forecast_history
    backend,known,_,connections=source_backend_case(tmp_path,monkeypatch)
    init=known.replace(minute=0,second=0,microsecond=0)-timedelta(hours=8)
    source=full_snapshot(init)
    backend.forecast_reader=lambda **kw:make_native_forecast(source,origin=kw['issue'],available_by=kw['available_by'],horizon_hours=kw['horizon_hours'],site=SITE)
    monkeypatch.setattr(forecast_history,'fetch_pending_origin_forecast_with_receipts',lambda *a,**kw:pytest.fail('legacy weather query'),raising=False)
    result=backend.collect(issue=known+timedelta(seconds=30),known_at=known)
    assert result['forecast']['source']=='weathernext3'
    assert set(result['native_source_paths'])=={'air','mass','outdoor'}
    assert all(Path(path).is_file() for path in result['native_source_paths'].values())
    assert connections

from test_household_native_thermal import originals

def google_context(tmp_path,monkeypatch,originals,source_factory=full_snapshot):
    from test_household_native_thermal import context,CODE
    from household.codec import canonical
    from household.control_contracts import instant
    from household.weather_context import prepare_native_cycle_contexts,project_weather,PreparedWeatherContext
    from household.thermal_model import project
    from astro_geometry_series import replay_series
    import native_thermal_forecast
    old,k=context(tmp_path,monkeypatch,originals)
    origin=instant(old['issued_at']);available=instant(old['inputs_available_at'])
    source=source_factory(origin.replace(minute=0,second=0,microsecond=0)-timedelta(hours=8))
    inputs=deepcopy(old['inputs'])
    inputs['forecast']=make_native_forecast(source,origin=origin,available_by=available,horizon_hours=24,site=SITE)
    packet=old['geometry']
    geometry=replay_series(canonical(packet),request=packet['request'],expected_series_sha256=old['geometry_series_sha256'],expected_native_runtime=packet['native_runtime'])
    capture=native_thermal_forecast.build_capture(old['candidate'],inputs,geometry=geometry,runtime=k['runtime'],
        expected_artifact_sha256=k['expected_artifact_sha256'],expected_geometry_sha256=geometry.sha256,
        issue=origin,available=available,published=instant(old['published_at']))
    thermal,weather=prepare_native_cycle_contexts(capture,code_revision=CODE,runtime=k['runtime'],
        expected_artifact_sha256=k['expected_artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    return capture,k,inputs,thermal,weather

def test_google_capture_projects_into_frozen_household_thermal_and_physical_energy(tmp_path,monkeypatch,originals):
    from household.weather_context import project_weather,PreparedWeatherContext
    from household.thermal_model import project
    from household.codec import canonical
    capture,k,inputs,thermal,weather=google_context(tmp_path,monkeypatch,originals)
    result=project_weather(weather)
    assert result['provider']=='weathernext3'
    assert result['weather_snapshot_sha256']==inputs['forecast']['snapshot_sha256']
    assert result['weather_forecast_sha256']==inputs['forecast']['forecast_sha256']
    assert all(row['weatherCode'] is None for row in result['hourly_forecast'])
    assert project(thermal)['output']==capture['output']
    assert len(result['forcings'])==288
    # The original household plan/energy fixture now receives actual verified
    # Google contexts. No numerical model or provenance validator is replaced.
    import test_household_energy_forecast as energy_fixture
    monkeypatch.setattr(energy_fixture,'made',lambda *args:(capture,k,thermal,weather))
    api,args,plan=energy_fixture.fixture(tmp_path,monkeypatch,originals)
    energy=api.seal_energy_forecast(**args)
    assert energy['output']['array_pv']['status']=='projected_provisional_array_potential'
    assert energy['output']['array_pv']['potential_pv_kwh']>0
    code=plan['inputs']['snapshot']['domains']['weather']['forecast_weather_codes']
    assert code['value'] is None and code['reason']=='unsupported_forecast_weather_code'
    assert code['evidence']['quality']=='unavailable'
    assert weather.to_dict()['schema']=='earthship-household-prepared-weather/v4'
    assert result['schema']=='earthship-household-weather-projection/v4'

    before=project_weather(weather)
    import builtins
    def forbidden(*args,**kwargs):pytest.fail('I/O in frozen Google household projection')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert project_weather(PreparedWeatherContext(canonical(weather.to_dict())))==before

def test_native_building_domain_refuses_an_otherwise_valid_google_timezone():
    from weather_learning.config import Site
    from thermal_model.installed_shade_origin import _forecast_forcing
    source=full_snapshot();source['site']['timezone']='UTC'
    other_site=Site(SITE.latitude,SITE.longitude,'UTC')
    value=make_native_forecast(source,origin=ORIGIN,available_by=KNOWN,horizon_hours=24,site=other_site)
    with pytest.raises(ValueError,match='site differs'):_forecast_forcing(value,ORIGIN,ORIGIN,ACTIONS)

def test_native_execution_manifest_pins_the_new_google_source_dependencies():
    from native_thermal_artifact import current_native_runtime
    runtime=current_native_runtime()
    sources=runtime['base_runtime']['source_manifest']
    assert all(name in sources for name in ('weather_learning/native_forecast.py','weather_learning/native_backend.py',
        'weather_learning/weathernext_ee.py','weather_learning/features.py','weather_learning/transport.py'))

def test_real_google_runtime_requires_fresh_fit_and_fits_existing_private_candidate_budget(tmp_path,monkeypatch,originals):
    import native_thermal_artifact as artifacts
    from test_native_thermal_artifact import fixture
    from household.codec import canonical
    paths,_,created=fixture(tmp_path,originals)
    runtime=artifacts.current_native_runtime()
    with pytest.raises(ValueError,match='fit environment/source closure differs'):
        artifacts.build_native_candidate(originals=paths,runtime=runtime,created_at=created)
    # Run a fresh bounded fit on the synthetic local dataset under the actual
    # source/interpreter binding. Never relabel the old fixture fitting receipt.
    from native_thermal_fit import fit_native_development
    from test_installed_shade_inputs import START,END
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    record,data,geometry,_=originals
    fit=fit_native_development(data,expected_dataset_sha256=data.sha256,training_start=START,
        training_end=END,guard=lambda:None,timeout_seconds=20)
    assert artifacts.current_native_runtime()==runtime
    fresh=tmp_path/'fresh-fit-evidence.json'
    fresh.write_bytes(canonical(dict(schema=artifacts.FIT_EVIDENCE_SCHEMA,created_at=(END+timedelta(seconds=5)).isoformat(),
        code_revision='e'*40,fit_runtime=runtime,fit=fit,release_authorized=False,production_model_changed=False)))
    fresh.chmod(0o600);paths['fit_evidence']=fresh
    candidate=artifacts.build_native_candidate(originals=paths,runtime=runtime,created_at=created)
    assert len(canonical(candidate))<=16384
    directory=tmp_path/'candidate';directory.mkdir(mode=0o700)
    path=artifacts.write_native_candidate(directory,candidate,assessed_at=created,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'])
    assert artifacts.read_native_candidate(path,assessed_at=created,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'])==candidate

def large_snapshot(init):
    import random
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    randomizer=random.Random(742);parts=[]
    for original in full_snapshot(init,hours=360)['source_originals']:
        raw=deepcopy(original['payload']);old_bands=raw['region'][0][4:]
        variables=[name.rsplit('_',1)[0] for name in old_bands]
        statistics=('mean','p10','p25','p50','p75','p90')
        raw['region'][0]=raw['region'][0][:4]+[variable+'_'+statistic for variable in variables for statistic in statistics]
        for row in raw['region'][1:]:
            values=row[4:];row[4:]=[value*(1+randomizer.uniform(-.001,.001)) for value in values for _ in statistics]
        parts.append(parse_collection_response(raw,collection=original['collection'],bands=raw['region'][0][4:],site=SITE,initialized_at=init,horizon=360))
    return make_snapshot(parts,site=SITE,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))

def test_full_original_google_data_can_exceed_legacy_private_context_bound_without_expanding_old_schemas(tmp_path,monkeypatch,originals):
    from household.codec import canonical,identity
    from household.weather_context import PreparedWeatherContext,project_weather,MAX_BYTES
    capture,k,inputs,thermal,weather=google_context(tmp_path,monkeypatch,originals,source_factory=large_snapshot)
    assert MAX_BYTES<len(weather.content)<=524288
    result=project_weather(weather)
    assert result['schema']=='earthship-household-weather-projection/v4'
    assert result['provider']=='weathernext3' and result['solar_geometry']
    assert len(result['hourly_forecast'])==26
    legacy=weather.to_dict();legacy['schema']='earthship-household-prepared-weather/v3'
    legacy['weather_sha256']=identity({key:value for key,value in legacy.items() if key!='weather_sha256'})
    with pytest.raises(ValueError):PreparedWeatherContext(canonical(legacy))
    import test_household_energy_forecast as energy_fixture
    monkeypatch.setattr(energy_fixture,'made',lambda *args:(capture,k,thermal,weather))
    api,args,plan=energy_fixture.fixture(tmp_path,monkeypatch,originals)
    assert api.seal_energy_forecast(**args)['output']['array_pv']['status']=='projected_provisional_array_potential'
