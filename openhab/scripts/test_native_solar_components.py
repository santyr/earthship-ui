"""Analytic interval-energy tests independent of any acquired household outcome."""
from datetime import datetime,timedelta,timezone
from math import fsum
import importlib
import pytest

T=datetime(2026,6,21,12,tzinfo=timezone.utc)
def api():return importlib.import_module('weather_learning.solar_components')
def positions(*,start=T,count=12,elevation=30):
    return [dict(at=(start+timedelta(minutes=5*i)).isoformat(),elevation_degrees=elevation if not callable(elevation) else elevation(i),azimuth_degrees=180.) for i in range(1,count+1)]
def reconstruct(**kwargs):
    args=dict(start=T,end=T+timedelta(hours=1),total_j_m2=1800000.,direct_j_m2=1080000.,positions=positions())
    args.update(kwargs);return api().reconstruct_hour(**args)
def energy(rows,key):return fsum(row[key]*(datetime.fromisoformat(row['end'])-datetime.fromisoformat(row['start'])).total_seconds() for row in rows)

def test_literal_native_hour_means_and_constant_elevation_direct_normal_flux():
    value=reconstruct();assert value['status']=='native_components'
    assert value['mean_ghi_w_m2']==500 and value['mean_bhi_w_m2']==300 and value['mean_dhi_w_m2']==200
    assert value['segments'][0]['raw_dni_w_m2']==pytest.approx(600)
    assert energy(value['segments'],'raw_ghi_w_m2')==pytest.approx(1800000)
    assert energy(value['segments'],'raw_bhi_w_m2')==pytest.approx(1080000)
    assert value['physical_calibration_qualified'] is False and value['automatic_actuation'] is False

def test_changing_elevation_conserves_direct_energy_without_midpoint_division():
    value=reconstruct(positions=positions(elevation=lambda i:30 if i<=6 else 90))
    assert all(row['raw_dni_w_m2']==pytest.approx(400) for row in value['segments'])
    assert value['segments'][0]['raw_bhi_w_m2']==pytest.approx(200)
    assert value['segments'][-1]['raw_bhi_w_m2']==pytest.approx(400)
    assert energy(value['segments'],'raw_ghi_w_m2')==pytest.approx(1800000)
    assert energy(value['segments'],'raw_dhi_w_m2')==pytest.approx(720000)

def test_terrain_masks_direct_after_conservation_and_keeps_declared_diffuse():
    value=reconstruct(horizon_profile=[dict(azimuth_degrees=7.5*i,elevation_degrees=35.) for i in range(48)])
    assert energy(value['segments'],'raw_bhi_w_m2')==pytest.approx(1080000)
    assert energy(value['segments'],'bhi_w_m2')==0
    assert energy(value['segments'],'ghi_w_m2')==pytest.approx(720000)
    assert all(row['dhi_w_m2']==pytest.approx(200) for row in value['segments'])

def test_sunrise_and_sunset_normalize_only_actual_daylight_support():
    for rising in (True,False):
        p=positions(elevation=lambda i:30 if (i>6)==rising else -10)
        value=reconstruct(positions=p,total_j_m2=900000,direct_j_m2=540000)
        assert value['status']=='native_components'
        assert energy(value['segments'],'raw_ghi_w_m2')==pytest.approx(900000)
        assert energy(value['segments'],'raw_bhi_w_m2')==pytest.approx(540000)
        assert all(row['ghi_w_m2']==0 for row in value['segments'] if row['elevation_degrees']<=0)

def test_fractional_native_grid_and_window_slices_keep_true_hour_boundaries():
    p=positions(start=T-timedelta(minutes=12,seconds=45),count=18)
    value=reconstruct(positions=p)
    assert value['segments'][0]['start']==T.isoformat()
    assert value['segments'][-1]['end']==(T+timedelta(hours=1)).isoformat()
    assert energy(value['segments'],'raw_ghi_w_m2')==pytest.approx(1800000)
    sliced=api().slice_hour(value,start=T+timedelta(minutes=12,seconds=15),end=T+timedelta(minutes=17,seconds=15))
    assert energy(sliced,'raw_ghi_w_m2')==pytest.approx(150000)
    assert energy(sliced,'raw_bhi_w_m2')==pytest.approx(90000)

def test_diffuse_only_and_true_night_do_not_divide_by_zero():
    diffuse=reconstruct(direct_j_m2=0)
    assert all(row['raw_dni_w_m2']==0 and row['raw_dhi_w_m2']==500 for row in diffuse['segments'])
    night=reconstruct(total_j_m2=0,direct_j_m2=0,positions=positions(elevation=-20))
    assert night['status']=='native_components' and energy(night['segments'],'ghi_w_m2')==0

@pytest.mark.parametrize('changes,reason',[
    ({'direct_j_m2':None},'native_direct_unavailable'),
    ({'direct_j_m2':2000000},'direct_exceeds_total'),
    ({'positions':positions(elevation=-20)},'no_daylight_support'),
    ({'positions':positions(elevation=.01)},'reconstructed_dni_outside_bound'),
    ({'positions':positions()[1:]},'incomplete_hour_geometry'),
    ({'positions':positions()[:5]+positions()[6:]},'incomplete_hour_geometry'),
])
def test_unsupported_component_method_has_an_explicit_total_only_fallback(changes,reason):
    value=reconstruct(**changes)
    assert value['status']=='total_only_fallback' and value['reason']==reason
    assert value['segments']==[] and value['raw_total_j_m2']==1800000

@pytest.mark.parametrize('changes',[{'total_j_m2':-1},{'direct_j_m2':-1},{'total_j_m2':float('nan')},
    {'direct_j_m2':float('inf')},{'end':T+timedelta(minutes=30)}])
def test_invalid_native_energy_or_interval_is_rejected(changes):
    with pytest.raises(ValueError):reconstruct(**changes)

def test_tiny_energy_roundoff_is_named_and_original_values_are_preserved():
    value=reconstruct(total_j_m2=1800000,direct_j_m2=1800000.0001)
    assert value['status']=='native_components'
    assert value['raw_direct_j_m2']==1800000.0001
    assert value['roundoff_adjustment_j_m2']==pytest.approx(-.0001)
    assert energy(value['segments'],'raw_ghi_w_m2')==pytest.approx(1800000)

def test_geometry_is_bounded_ordered_and_not_silently_interpolated():
    p=positions();p[0]['elevation_degrees']=100
    with pytest.raises(ValueError):reconstruct(positions=p)
    with pytest.raises(ValueError):reconstruct(positions=list(reversed(positions())))
    with pytest.raises(ValueError):reconstruct(positions=positions()+positions())

def test_subnormal_projection_cannot_raise_a_division_error():
    p=positions(start=T-timedelta(minutes=5)+timedelta(microseconds=1),count=13,elevation=lambda i:1e-318 if i==1 else -20)
    value=reconstruct(positions=p)
    assert value['status']=='total_only_fallback' and value['reason']=='no_direct_projection_support'

def test_reconstructed_instantaneous_ghi_outside_model_bound_uses_declared_fallback():
    value=reconstruct(total_j_m2=5760000,direct_j_m2=5040000,positions=positions(elevation=lambda i:30 if i<=6 else 90))
    assert value['status']=='total_only_fallback' and value['reason']=='reconstructed_ghi_outside_bound'
