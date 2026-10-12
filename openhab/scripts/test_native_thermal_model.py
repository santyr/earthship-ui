"""Native geometry uses unchanged physical equations and analytic derivatives."""
from dataclasses import replace
from datetime import timedelta
import importlib,math
import numpy as np
import pytest
from test_installed_shade_dynamics import AT,COEFFICIENTS,rows
from astro_geometry import build_source,build_cache
from astro_geometry_series import build_series_request,split_series_request,build_series
from thermal_model.installed_shade_dynamics import InstalledShadeDynamics
from thermal_model.solar import solar_elevation_sin

RUNTIME={'binding_version':'5.2.3','collector_sha256':'e'*64,'libraries':{'astro_binding':'a'*64,'openhab_core':'b'*64}}

def api():return importlib.import_module('native_thermal_model')

def geometry(forcings,*,degrees=30,match_legacy=False,missing=False):
    points=[row.at for row in forcings]
    if missing:points.pop()
    request=build_series_request(points,requested_at=AT,latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')
    caches=[]
    for chunk in split_series_request(request):
        source=build_source(chunk,observed_at=AT+timedelta(seconds=1),native_runtime=RUNTIME,source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
        from datetime import datetime
        lines=[]
        for at in chunk['instants']:
            elevation=math.degrees(math.asin(solar_elevation_sin(datetime.fromisoformat(at)))) if match_legacy else degrees
            lines.append(at+'\t'+repr(elevation)+'\t180\n')
        caches.append(build_cache(chunk,source,native_output=''.join(lines).encode(),computed_at=AT+timedelta(seconds=2)))
    return build_series(request,caches,expected_native_runtime=RUNTIME)

def model(g,coefficients=COEFFICIENTS):return api().NativeInstalledShadeDynamics(coefficients,geometry=g,expected_series_sha256=g.sha256)


def test_same_geometry_has_legacy_state_and_sensitivity_parity():
    forcing=rows();g=geometry(forcing,match_legacy=True)
    old=InstalledShadeDynamics(COEFFICIENTS).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing)
    new=model(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing)
    assert np.allclose(new.states,old.states,rtol=0,atol=1e-12)
    assert np.allclose(new.sensitivities,old.sensitivities,rtol=0,atol=1e-10)
    assert model(g).rule=='earthship-native-installed-shade-dynamics/v2'


def test_native_rollout_sensitivities_match_independent_finite_differences():
    forcing=rows();g=geometry(forcing);rolled=model(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing)
    numeric=np.zeros((2,10))
    for column in range(10):
        low=list(COEFFICIENTS);high=list(COEFFICIENTS);low[column]-=1e-7;high[column]+=1e-7
        a=model(g,tuple(low)).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states[-1]
        b=model(g,tuple(high)).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states[-1]
        numeric[:,column]=(np.asarray(b)-a)/(2e-7)
    assert np.allclose(rolled.sensitivities[-1],numeric,rtol=1e-5,atol=1e-5)


@pytest.mark.parametrize('damage',['removed','unknown','nan','grid','radiation','temperature'])
def test_native_model_preserves_forcing_domain_and_physical_guards(damage):
    forcing=rows();g=geometry(forcing);bad=forcing[0]
    if damage=='removed':bad=replace(bad,outdoor_shade_present=0)
    if damage=='unknown':bad=replace(bad,indoor_shade_closed=None)
    if damage=='nan':bad=replace(bad,vent_open=float('nan'))
    if damage=='grid':bad=replace(bad,at=AT+timedelta(minutes=6))
    if damage=='radiation':bad=replace(bad,radiation_wm2=-1)
    if damage=='temperature':bad=replace(bad,outdoor_f=141)
    with pytest.raises(ValueError):model(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=(bad,))


def test_missing_geometry_is_refused_even_when_radiation_is_zero():
    forcing=tuple(replace(row,radiation_wm2=0) for row in rows(2));g=geometry(forcing,missing=True)
    with pytest.raises(KeyError):model(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing)


def test_native_model_retains_coefficient_stability_stress_and_original_geometry_pin():
    g=geometry(rows());values=list(COEFFICIENTS)
    for index in (0,1,4,6,7):values[index]=1e-6
    values[5]=0.2
    with pytest.raises(ValueError):model(g,tuple(values))
    with pytest.raises(ValueError):api().NativeInstalledShadeDynamics(COEFFICIENTS,geometry=g,expected_series_sha256='f'*64)
    with pytest.raises((AttributeError,TypeError)):model(g).coefficients=(0,)*10
