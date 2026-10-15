"""Terrain masks are location-bound original inputs, not sunrise clocks or clouds."""
from datetime import timedelta
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import importlib,json
import pytest
from household.codec import canonical,identity
from test_household_pv_model import ORIGIN,ARRAY,model_inputs,api as pv

SITE={'latitude':38.3739919,'longitude':-105.7744609,'altitude_m':None}


def api():return importlib.import_module('household_solar_horizon')


def source(at=ORIGIN):
    d=json.loads((Path(__file__).parents[1]/'household-solar-horizon.json').read_bytes())
    d['recorded_at']=(at-timedelta(days=1)).isoformat();d['source']['retrieved_at']=d['recorded_at']
    return api().prepare_horizon_source(canonical(d),available_at=at-timedelta(seconds=1))


def test_map_skyline_has_correct_cardinals_and_wraparound_at_true_north():
    value,reason=api().horizon_configuration(source(),origin=ORIGIN,site=SITE,timezone_name='America/Denver')
    assert reason is None
    assert api().horizon_height(value['profile'],90)==4.2
    assert api().horizon_height(value['profile'],270)==8.8
    assert api().horizon_height(value['profile'],360)==api().horizon_height(value['profile'],0)==3.8
    assert api().horizon_height(value['profile'],356.25)==pytest.approx(3.45)
    assert value['validation_status']=='unvalidated_map_estimate'


@pytest.mark.parametrize('damage',['site','gap','profile_order','future_record','calibrated'])
def test_optional_unsupported_or_wrong_location_never_becomes_a_qualified_horizon(damage):
    s=source();d=json.loads(s['raw']);site=deepcopy(SITE)
    if damage=='site':site['latitude']+=.1
    if damage=='gap':d['profile'].pop()
    if damage=='profile_order':d['profile'].reverse()
    if damage=='future_record':d['recorded_at']=(ORIGIN+timedelta(seconds=1)).isoformat()
    if damage=='calibrated':d['validation_status']='calibrated'
    s['raw']=canonical(d).decode();s['sha256']=sha256(s['raw'].encode()).hexdigest()
    value,reason=api().horizon_configuration(s,origin=ORIGIN,site=site,timezone_name='America/Denver')
    assert value is None and reason is not None


def test_changed_original_source_bytes_or_availability_cannot_be_relabelled():
    s=source();s['raw']+=' '
    with pytest.raises(ValueError):api().horizon_configuration(s,origin=ORIGIN,site=SITE,timezone_name='America/Denver')
    s=source();s['available_at']=(ORIGIN+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):api().horizon_configuration(s,origin=ORIGIN,site=SITE,timezone_name='America/Denver')


def test_mountain_shade_removes_direct_beam_and_its_ground_reflection_but_retains_diffuse():
    args=dict(array=ARRAY,assumptions=pv().ASSUMPTIONS,ghi_wm2=500,elevation_degrees=5,azimuth_degrees=270,day_of_year=288,temp_f=59,wind_mph=2)
    clear=pv().array_power(**args)
    shaded=pv().array_power(**args,horizon_elevation_degrees=8.8)
    assert shaded['dni_wm2']==0 and shaded['dhi_wm2']==clear['dhi_wm2']
    assert 0<shaded['potential_dc_w']<clear['potential_dc_w']
    assert shaded['direct_beam_blocked'] is True
    assert pv().array_power(**{**args,'elevation_degrees':10},horizon_elevation_degrees=8.8)['direct_beam_blocked'] is False


def test_integrated_terrain_mask_changes_only_solar_response_and_preserves_original_weather():
    args=model_inputs();args['array']=ARRAY
    for row in args['positions']:row.update(elevation_degrees=5,azimuth_degrees=270)
    before=canonical(args['hourly_forecast']);unshaded=pv().integrate_array(**args)
    config,reason=api().horizon_configuration(source(),origin=ORIGIN,site=SITE,timezone_name='America/Denver');assert reason is None
    shaded=pv().integrate_array(**args,horizon_profile=config['profile'])
    assert 0<shaded['potential_pv_kwh']<unshaded['potential_pv_kwh']
    assert shaded['direct_sun_windows']==[] and shaded['terrain_blocked_geometry_steps']==12
    assert shaded['forecast_horizontal_irradiation_kwh_m2']==unshaded['forecast_horizontal_irradiation_kwh_m2']
    assert canonical(args['hourly_forecast'])==before
