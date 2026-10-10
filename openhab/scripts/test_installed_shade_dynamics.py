"""Physical domain and analytic derivatives of the isolated forecast core."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import numpy as np
import pytest

AT=datetime(2026,10,1,18,tzinfo=timezone.utc)
COEFFICIENTS=(0.002,0.02,0.001,0.002,0.005,0.005,0.01,0.001,0.0004,0.0007)


def core():
    from thermal_model import installed_shade_dynamics
    return installed_shade_dynamics


def rows(count=12):
    module=core()
    return tuple(module.InstalledShadeForcing(at=AT+timedelta(minutes=5*(i+1)),outdoor_f=55+i/10,radiation_wm2=150+i*5,indoor_shade_closed=float(i%2),outdoor_shade_present=1.0,vent_open=(i%3)/2) for i in range(count))


def test_valid_model_retains_only_identified_parameters():
    model=core().InstalledShadeDynamics(COEFFICIENTS)
    assert len(model.coefficients)==10
    assert 'solar_unshaded' not in model.parameter_names
    assert max(model.physical_spectral_radii())<1


@pytest.mark.parametrize('damage',['nonfinite','bounds','shade_order','unstable','wrong_count'])
def test_invalid_coefficients_are_refused(damage):
    values=list(COEFFICIENTS)
    if damage=='nonfinite':values[0]=float('nan')
    elif damage=='bounds':values[0]=0.51
    elif damage=='shade_order':values[2]=0.003
    elif damage=='unstable':values[0]=values[6]=values[7]=0
    else:values.pop()
    with pytest.raises(ValueError):core().InstalledShadeDynamics(tuple(values))


def test_rollout_sensitivity_matches_numerical_coefficient_derivatives():
    module=core();model=module.InstalledShadeDynamics(COEFFICIENTS)
    result=model.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=rows())
    numeric=np.zeros((2,10))
    for column in range(10):
        step=1e-7;left=list(COEFFICIENTS);right=list(COEFFICIENTS)
        left[column]-=step;right[column]+=step
        low=module.InstalledShadeDynamics(tuple(left)).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=rows()).states[-1]
        high=module.InstalledShadeDynamics(tuple(right)).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=rows()).states[-1]
        numeric[:,column]=(np.asarray(high)-low)/(2*step)
    assert np.allclose(result.sensitivities[-1],numeric,rtol=1e-5,atol=1e-5)
    assert len(result.states)==len(result.sensitivities)==12


@pytest.mark.parametrize('damage',['removed','unknown','nonfinite','wrong_grid','naive','radiation','temperature'])
def test_invalid_or_unsupported_forcing_refuses_rollout(damage):
    module=core();forcing=rows(1)[0]
    if damage=='removed':forcing=replace(forcing,outdoor_shade_present=0)
    elif damage=='unknown':forcing=replace(forcing,indoor_shade_closed=None)
    elif damage=='nonfinite':forcing=replace(forcing,vent_open=float('nan'))
    elif damage=='wrong_grid':forcing=replace(forcing,at=AT+timedelta(minutes=6))
    elif damage=='naive':forcing=replace(forcing,at=forcing.at.replace(tzinfo=None))
    elif damage=='radiation':forcing=replace(forcing,radiation_wm2=-1)
    else:forcing=replace(forcing,outdoor_f=141)
    with pytest.raises(ValueError):module.InstalledShadeDynamics(COEFFICIENTS).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=(forcing,))


def test_missing_forcing_is_not_filled_or_backdated():
    model=core().InstalledShadeDynamics(COEFFICIENTS)
    values=rows(3)
    with pytest.raises(ValueError):model.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=(values[0],values[2]))
    with pytest.raises(ValueError):model.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=())


def test_forecast_result_cannot_mutate_model_or_input_values():
    model=core().InstalledShadeDynamics(COEFFICIENTS);forcing=rows(1)
    result=model.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing)
    with pytest.raises((AttributeError,TypeError)):result.states[0][0]=99
    with pytest.raises((AttributeError,TypeError)):model.coefficients=(0,)*10
    assert forcing[0].outdoor_f==55


def test_stable_but_physically_explosive_bias_fails_72_hour_guard():
    values=list(COEFFICIENTS)
    for index in (0,1,4,6,7):values[index]=0.000001
    values[5]=0.2
    with pytest.raises(ValueError,match='physical bounds'):core().InstalledShadeDynamics(tuple(values))


def test_forecast_out_of_range_is_refused_without_clipping():
    module=core();model=module.InstalledShadeDynamics(COEFFICIENTS)
    force=module.InstalledShadeForcing(AT+timedelta(minutes=5),140,1600,0,1,0)
    with pytest.raises(ValueError,match='physical bounds'):
        model.rollout(origin_at=AT,air_f=139.9,mass_f=139.9,forcings=(force,))
