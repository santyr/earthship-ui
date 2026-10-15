"""Array geometry and interval semantics, independently checked against pvlib."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import importlib,json
import pytest

REFERENCE=json.loads((Path(__file__).parent/'fixtures/pvlib-array-reference.json').read_bytes())
ARRAY=dict(module_count=12,module_nameplate_w=350,dc_nameplate_w=4200,surface_azimuth_degrees=165.,surface_tilt_degrees=57.4)
ORIGIN=datetime(2026,10,15,0,30,15,tzinfo=timezone.utc)


def api():
    module=importlib.import_module('household_pv_model')
    return module


@pytest.mark.parametrize('row',REFERENCE['rows'])
def test_array_response_matches_independent_pvlib_reference(row):
    inputs={k:row[k] for k in ('ghi_wm2','elevation_degrees','azimuth_degrees','day_of_year','temp_f','wind_mph')}
    result=api().array_power(array=ARRAY,assumptions=api().ASSUMPTIONS,**inputs)
    for key in ('dni_wm2','dhi_wm2','poa_wm2','temperature_proxy_c','potential_dc_w'):
        assert result[key]==pytest.approx(row[key],rel=1e-10,abs=1e-9)


def model_inputs(*,origin=ORIGIN,hours=1,missing_wind=False):
    start=origin.replace(minute=0,second=0,microsecond=0)
    rows=[dict(at=(start+timedelta(hours=i)).isoformat(),radiationWm2=[100.,200.,400.,600.][i] if i<4 else 600.,tempF=59.,windMph=None if missing_wind else 0.) for i in range(hours+3)]
    positions=[dict(at=(origin+timedelta(minutes=5*i)).isoformat(),elevation_degrees=60.,azimuth_degrees=165.) for i in range(1,hours*12+1)]
    array={**ARRAY,'surface_tilt_degrees':0.};assumptions={**api().ASSUMPTIONS,'gamma_pdc_per_c':0.,'dc_loss_multiplier':1.}
    return dict(array=array,assumptions=assumptions,hourly_forecast=rows,positions=positions,origin=origin,horizon_hours=hours,timezone_name='America/Denver')


def test_hour_end_radiation_means_split_partial_hours_without_a_forward_shift():
    result=api().integrate_array(**model_inputs())
    # 29m45s at200W/m2 then30m15s at400W/m2, flat4.2kW array.
    assert result['potential_pv_kwh']==pytest.approx(1.2635)
    assert result['trajectory'][0]['start']==ORIGIN.isoformat()
    assert result['trajectory'][0]['end']==(ORIGIN+timedelta(hours=1)).isoformat()


def test_daylight_geometry_never_becomes_measured_radiation_or_night_generation():
    args=model_inputs()
    for p in args['positions']:p['elevation_degrees']=-1.
    result=api().integrate_array(**args)
    assert result['potential_pv_kwh']==0
    assert all(row['potential_pv_kwh']==0 for row in result['trajectory'])
    assert args['hourly_forecast'][1]['radiationWm2']==200.


@pytest.mark.parametrize('damage',['missing_geometry','future_grid','missing_radiation','unordered_weather'])
def test_missing_or_changed_numerical_coverage_never_fills_with_zero(damage):
    args=model_inputs()
    if damage=='missing_geometry':args['positions'].pop()
    if damage=='future_grid':args['positions'][0]['at']=(ORIGIN+timedelta(minutes=6)).isoformat()
    if damage=='missing_radiation':args['hourly_forecast'][1]['radiationWm2']=None
    if damage=='unordered_weather':args['hourly_forecast'].reverse()
    with pytest.raises(ValueError):api().integrate_array(**args)


def test_dst_fallback_keeps_24_distinct_elapsed_hour_bins():
    origin=datetime(2026,11,1,7,30,15,tzinfo=timezone.utc)
    result=api().integrate_array(**model_inputs(origin=origin,hours=24))
    assert len(result['trajectory'])==24
    assert len({row['end'] for row in result['trajectory']})==24
    assert result['trajectory'][-1]['end']==(origin+timedelta(hours=24)).isoformat()
    assert result['remaining_today_potential_kwh']<result['potential_pv_kwh']


def test_missing_wind_uses_an_explicit_provisional_assumption():
    result=api().integrate_array(**model_inputs(missing_wind=True))
    assert result['missing_wind_assumption_used'] is True
    assert result['assumptions']['missing_wind_m_s']==1.


def source(at=ORIGIN):
    raw=json.loads((Path(__file__).parents[1]/'household-pv-system.json').read_bytes())
    raw['recorded_at']=(at-timedelta(days=1)).isoformat()
    return api().prepare_system_source(json.dumps(raw).encode(),available_at=at-timedelta(seconds=1))


def test_original_system_source_keeps_the_phone_reference_and_approximate_azimuth():
    system,reason=api().system_configuration(source(),ORIGIN)
    assert reason is None
    assert system['array']['surface_tilt_degrees']==57.4
    assert system['array']['surface_azimuth_degrees']==165.
    assert system['orientation_source']['inclinometer_reading_degrees']==32.6


@pytest.mark.parametrize('damage',['hash','future'])
def test_changed_or_late_original_system_source_is_refused(damage):
    value=source()
    if damage=='hash':value['sha256']='a'*64
    else:value['available_at']=(ORIGIN+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):api().system_configuration(value,ORIGIN)


def test_optional_unsupported_or_missing_geometry_configuration_stays_unknown():
    assert api().system_configuration(None,ORIGIN)==(None,'pv_system_unavailable')
    value=source();raw=json.loads(value['raw']);raw['array']['surface_tilt_degrees']=32.6
    from hashlib import sha256
    value['raw']=json.dumps(raw);value['sha256']=sha256(value['raw'].encode()).hexdigest()
    assert api().system_configuration(value,ORIGIN)==(None,'unsupported_pv_system_configuration')


def test_pure_numerical_model_requires_no_io(monkeypatch):
    args=model_inputs();expected=api().integrate_array(**args)
    import builtins,urllib.request
    def forbidden(*a,**k):pytest.fail('I/O at frozen PV model boundary')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    assert api().integrate_array(**args)==expected


def test_storage_headroom_changes_capture_without_changing_solar_or_household_load():
    origin=ORIGIN
    steps=[dict(start=origin.isoformat(),end=(origin+timedelta(hours=1)).isoformat(),potential_pv_kwh=1.)]
    low=api().simulate_storage(steps=steps,initial_soc_pct=50.,nominal_bank_kwh=10.,load_ac_w=500.)
    full=api().simulate_storage(steps=steps,initial_soc_pct=99.,nominal_bank_kwh=10.,load_ac_w=500.)
    assert low['trajectory'][0]['nominal_soc_pct']==pytest.approx(54.5)
    assert low['modeled_captured_pv_kwh']==pytest.approx(1.)
    assert full['modeled_captured_pv_kwh']==pytest.approx(.631578947368421)
    assert full['modeled_unaccepted_pv_kwh']>0
    assert low['household_ac_load_w_assumption']==full['household_ac_load_w_assumption']==500.
    assert low['potential_pv_kwh']==full['potential_pv_kwh']==1.
    assert full['balance_closed'] is False and full['physical_calibration_qualified'] is False
    assert full['system_dc_overhead_measured'] is False


def test_storage_model_retains_unserved_energy_instead_of_negative_soc():
    steps=[dict(start=ORIGIN.isoformat(),end=(ORIGIN+timedelta(hours=1)).isoformat(),potential_pv_kwh=0.)]
    result=api().simulate_storage(steps=steps,initial_soc_pct=1.,nominal_bank_kwh=10.,load_ac_w=1000.)
    assert result['trajectory'][0]['nominal_soc_pct']==0.
    assert result['modeled_unserved_dc_kwh']>0
    assert result['automatic_actuation'] is False


def test_integrated_substeps_conserve_hourly_potential_for_storage_simulation():
    result=api().integrate_array(**model_inputs())
    assert sum(row['potential_pv_kwh'] for row in result['steps'])==pytest.approx(1.2635)
    assert result['steps'][0]['start']==ORIGIN.isoformat()
    assert result['steps'][-1]['end']==(ORIGIN+timedelta(hours=1)).isoformat()
