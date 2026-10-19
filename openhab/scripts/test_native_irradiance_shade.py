"""Heat input tracks irradiance rather than inverse solar elevation."""
from dataclasses import replace
import importlib
import numpy as np
import pytest
from test_native_thermal_model import rows,geometry,AT,COEFFICIENTS
from native_joint_shade import expand_installed_prior

def api():return importlib.import_module('native_irradiance_shade')
def test_equal_irradiance_has_equal_heat_input_at_different_daylight_elevations():
    forcing=rows(1);low=geometry(forcing,degrees=2);high=geometry(forcing,degrees=60)
    a=api().normalize_forcings(origin_at=AT,forcings=forcing,geometry=low)
    b=api().normalize_forcings(origin_at=AT,forcings=forcing,geometry=high)
    assert a==b
    assert sum(a[0][1:5])==pytest.approx(forcing[0].radiation_wm2)
def test_solar_heat_input_is_linear_and_native_night_remains_zero():
    forcing=rows(1);g=geometry(forcing,degrees=2)
    low=tuple(replace(r,radiation_wm2=20) for r in forcing);high=tuple(replace(r,radiation_wm2=200) for r in forcing)
    a=api().normalize_forcings(origin_at=AT,forcings=low,geometry=g)[0]
    b=api().normalize_forcings(origin_at=AT,forcings=high,geometry=g)[0]
    assert np.allclose(a[1:5],np.asarray(b[1:5])*.1)
    night=api().normalize_forcings(origin_at=AT,forcings=high,geometry=geometry(forcing,degrees=-1))[0]
    assert sum(night[1:5])==0
    assert api().RULE=='earthship-native-irradiance-shade-dynamics/v4'
def test_irradiance_rollout_derivatives_match_independent_finite_differences():
    forcing=tuple(replace(r,outdoor_shade_present=0) for r in rows());g=geometry(forcing)
    coeff=expand_installed_prior(COEFFICIENTS);cls=api().NativeIrradianceShadeDynamics
    rolled=cls(coeff,geometry=g,expected_series_sha256=g.sha256).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing)
    numeric=np.zeros((2,14))
    for i in range(14):
        a=list(coeff);b=list(coeff);a[i]-=1e-7;b[i]+=1e-7
        low=cls(tuple(a),geometry=g,expected_series_sha256=g.sha256).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states[-1]
        high=cls(tuple(b),geometry=g,expected_series_sha256=g.sha256).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states[-1]
        numeric[:,i]=(np.asarray(high)-low)/(2e-7)
    assert np.allclose(rolled.sensitivities[-1],numeric,rtol=1e-5,atol=1e-5)
