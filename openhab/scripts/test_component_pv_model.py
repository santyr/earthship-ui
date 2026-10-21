"""Shared component-aware physics, with the legacy numerical path frozen."""
from datetime import timedelta
import importlib
import pytest
from native_solar_fixtures import T,SITE,ARRAY,HORIZON,snapshot,geometry
from weather_learning.native_forecast import make_native_component_forecast
from household_pv_model import array_power,integrate_array,simulate_storage,ASSUMPTIONS

ORIGIN=T+timedelta(hours=1,minutes=15)
def api():return importlib.import_module('household_pv_components')
def forecast(*,direct=1080000,hours=1):
    return make_native_component_forecast(snapshot(hours=30,direct_j=direct),origin=ORIGIN,available_by=T+timedelta(hours=1),horizon_hours=hours,site=SITE)
def project(**kwargs):
    args=dict(array=ARRAY,forecast=forecast(),positions=geometry(count=36),origin=ORIGIN,horizon_hours=1,timezone_name='UTC',horizon_profile=HORIZON)
    args.update(kwargs);return api().integrate_array_components(**args)

def test_original_total_only_point_arithmetic_is_numerically_unchanged():
    value=array_power(array=ARRAY,assumptions=ASSUMPTIONS,ghi_wm2=500,elevation_degrees=30,azimuth_degrees=180,day_of_year=172,temp_f=68,wind_mph=4.473872584108804,horizon_elevation_degrees=0)
    assert value['dni_wm2']==pytest.approx(822.1023432001716,abs=1e-10)
    assert value['dhi_wm2']==pytest.approx(88.94882839991425,abs=1e-10)
    assert value['potential_dc_w']==pytest.approx(646.0545088248534,abs=1e-10)

def test_native_component_point_keeps_the_same_electrical_assumptions():
    value=api().array_power_components(array=ARRAY,ghi_wm2=500,dni_wm2=600,dhi_wm2=200,elevation_degrees=30,
        azimuth_degrees=180,temp_f=68,wind_mph=4.473872584108804)
    assert value['poa_wm2']==pytest.approx(712.9165124598852)
    assert value['dni_wm2']==600 and value['dhi_wm2']==200
    # The same transposition/electrical inputs must reproduce the old point
    # output; only decomposition has a new source/identity.
    same=api().array_power_components(array=ARRAY,ghi_wm2=500,dni_wm2=822.1023432001716,dhi_wm2=88.94882839991425,
        elevation_degrees=30,azimuth_degrees=180,temp_f=68,wind_mph=4.473872584108804)
    assert same['potential_dc_w']==pytest.approx(646.0545088248534,abs=1e-10)

def test_complete_geometry_integrates_conserved_components_on_fractional_origin():
    value=project();point=api().array_power_components(array=ARRAY,ghi_wm2=500,dni_wm2=600,dhi_wm2=200,
        elevation_degrees=30,azimuth_degrees=180,temp_f=68,wind_mph=4.473872584108804)
    assert value['model_rule']==api().MODEL_RULE
    assert value['potential_pv_kwh']==pytest.approx(point['potential_dc_w']/1000)
    assert value['forecast_horizontal_irradiation_kwh_m2']==pytest.approx(.5)
    assert value['source_support']['native_hours']==2 and value['source_support']['fallback_hours']==0
    assert value['physical_calibration_qualified'] is False and value['automatic_actuation'] is False

def test_missing_direct_has_fallback_inclusive_policy_equal_to_original_baseline():
    f=forecast(direct=None);value=project(forecast=f)
    old=integrate_array(array=ARRAY,assumptions=ASSUMPTIONS,hourly_forecast=f['rows'],positions=geometry(start=ORIGIN,count=12),
        origin=ORIGIN,horizon_hours=1,timezone_name='UTC',horizon_profile=HORIZON)
    assert value['potential_pv_kwh']==pytest.approx(old['potential_pv_kwh'])
    assert value['source_support']['native_hours']==0 and value['source_support']['fallback_hours']==2
    assert value['source_support']['fallback_reasons']=={'native_direct_unavailable':2}

def test_missing_source_hour_prefix_does_not_rescale_hour_energy_into_remaining_window():
    value=project(positions=geometry(start=ORIGIN,count=12))
    assert value['source_support']['native_hours']==0
    assert value['source_support']['fallback_reasons']=={'incomplete_hour_geometry':2}
    assert value['forecast_horizontal_irradiation_kwh_m2']==pytest.approx(.5)
    assert value['potential_pv_kwh']==pytest.approx(.6460545088248534)

def test_geometry_gap_inside_prediction_window_is_unavailable_not_a_fabricated_projection():
    p=geometry(count=36);p.pop(18)
    with pytest.raises(ValueError):project(positions=p)

def test_historical_pair_baseline_and_daily_potential_use_the_same_kernel():
    f=forecast(hours=12);p=geometry(count=144)
    start=ORIGIN+timedelta(minutes=15);end=start+timedelta(minutes=5)
    pair=api().interval_baseline_components(array=ARRAY,forecast=f,positions=p,start=start,end=end,horizon_profile=HORIZON)
    prediction=api().project_window_components(array=ARRAY,forecast=f,positions=p,start=start,end=end,timezone_name='UTC',horizon_profile=HORIZON)
    assert pair['baseline_w']==pytest.approx(prediction['potential_pv_kwh']*12000)
    assert pair['baseline_rule']==api().MODEL_RULE and pair['forecast_sha256']==f['forecast_sha256']
    from daily_pv_potential import project_days_components
    day=project_days_components(dates=['2026-06-21'],forecast=f,positions=p,array=ARRAY,horizon_profile=HORIZON,timezone_name='UTC',issued_at=ORIGIN)[0]
    full=api().project_window_components(array=ARRAY,forecast=f,positions=p,start=ORIGIN,end=T+timedelta(hours=12),timezone_name='UTC',horizon_profile=HORIZON)
    assert day['potentialKwh']==pytest.approx(full['potential_pv_kwh'])
    assert day['modelRule']==api().MODEL_RULE

def test_storage_propagates_the_same_component_steps_and_keeps_nominal_scope():
    pv=project();out=api().storage_from_components(pv,initial_soc_pct=50,nominal_bank_kwh=10,load_ac_w=100)
    old=simulate_storage(steps=pv['steps'],initial_soc_pct=50,nominal_bank_kwh=10,load_ac_w=100)
    assert out['potential_pv_kwh']==pytest.approx(pv['potential_pv_kwh'])
    assert out['end_soc_pct']==pytest.approx(old['trajectory'][-1]['nominal_soc_pct'])
    assert out['physical_calibration_qualified'] is False and out['automatic_actuation'] is False


def test_fractional_windows_are_additive_on_changing_geometry_and_point_weather():
    source=snapshot(hours=30,temperature_k=lambda h:280+h*2)
    f=make_native_component_forecast(source,origin=ORIGIN,available_by=T+timedelta(hours=1),horizon_hours=2,site=SITE)
    positions=geometry(start=T-timedelta(minutes=2,seconds=15),count=65,elevation=lambda i:20+i/2)
    middle=ORIGIN+timedelta(minutes=27,seconds=19)
    args=dict(array=ARRAY,forecast=f,positions=positions,timezone_name='UTC',horizon_profile=HORIZON)
    full=api().project_window_components(**args,start=ORIGIN,end=ORIGIN+timedelta(hours=1))
    a=api().project_window_components(**args,start=ORIGIN,end=middle)
    b=api().project_window_components(**args,start=middle,end=ORIGIN+timedelta(hours=1))
    assert a['potential_pv_kwh']+b['potential_pv_kwh']==pytest.approx(full['potential_pv_kwh'],abs=1e-12)
    assert a['forecast_horizontal_irradiation_kwh_m2']+b['forecast_horizontal_irradiation_kwh_m2']==pytest.approx(full['forecast_horizontal_irradiation_kwh_m2'])


@pytest.mark.parametrize('day,hours',[('2026-03-08',23),('2026-11-01',25)])
def test_component_daily_projection_uses_actual_local_dst_elapsed_time(monkeypatch,day,hours):
    from datetime import datetime,time,date,timezone
    from zoneinfo import ZoneInfo
    import native_solar_fixtures as fixtures
    from daily_pv_potential import project_days_components
    zone=ZoneInfo('America/Denver');origin=datetime.combine(date.fromisoformat(day),time.min,zone).astimezone(timezone.utc)
    source_t=origin-timedelta(hours=2)
    monkeypatch.setattr(fixtures,'T',source_t)
    f=make_native_component_forecast(fixtures.snapshot(hours=30),origin=origin,available_by=origin-timedelta(hours=1),horizon_hours=hours,site=SITE)
    positions=geometry(start=origin-timedelta(hours=1),count=(hours+2)*12)
    row=project_days_components(dates=[day],forecast=f,positions=positions,array=ARRAY,horizon_profile=HORIZON,timezone_name='America/Denver',issued_at=origin)[0]
    assert row['status']=='available' and row['scope']=='full_day'
    assert datetime.fromisoformat(row['throughAt'])-datetime.fromisoformat(row['fromAt'])==timedelta(hours=hours)
    point=api().array_power_components(array=ARRAY,ghi_wm2=500,dni_wm2=600,dhi_wm2=200,elevation_degrees=30,azimuth_degrees=180,temp_f=68,wind_mph=4.473872584108804)
    assert row['potentialKwh']==pytest.approx(hours*point['potential_dc_w']/1000)


def test_total_only_benchmark_shares_the_requested_inputs_without_changing_v1():
    candidate=project();benchmark=project(force_total_only=True)
    assert benchmark['source_support']==dict(native_hours=0,fallback_hours=2,fallback_reasons={'total_only_benchmark':2})
    assert benchmark['forecast_sha256']==candidate['forecast_sha256']
    assert benchmark['geometry_sha256']==candidate['geometry_sha256']
    assert benchmark['forecast_horizontal_irradiation_kwh_m2']==pytest.approx(.5)
    assert benchmark['potential_pv_kwh']==pytest.approx(.6460545088248534)
    assert candidate['potential_pv_kwh']!=pytest.approx(benchmark['potential_pv_kwh'])


def test_matched_benchmark_has_a_distinct_pair_and_projection_identity():
    args=dict(array=ARRAY,forecast=forecast(),positions=geometry(count=36),start=ORIGIN,end=ORIGIN+timedelta(minutes=5),horizon_profile=HORIZON)
    native=api().interval_baseline_components(**args)
    total=api().interval_baseline_components(**args,force_total_only=True)
    projection=project(force_total_only=True)
    assert total['baseline_rule']!=native['baseline_rule']
    assert total['baseline_rule']==projection['model_rule']==api().BENCHMARK_RULE
    assert total['benchmark']=='total_only' and native['benchmark']=='native_with_total_only_fallback'
