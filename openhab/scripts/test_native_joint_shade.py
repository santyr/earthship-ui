"""Four distinct solar regimes, explicit priors and independent numerical checks."""
from dataclasses import replace
import importlib
import numpy as np
import pytest
from test_native_thermal_model import geometry,AT,COEFFICIENTS,rows,model

def api():return importlib.import_module('native_joint_shade')
def joint(g):return api().NativeJointShadeDynamics(api().expand_installed_prior(COEFFICIENTS),geometry=g,expected_series_sha256=g.sha256)
def test_installed_response_preserves_the_original_numerical_model():
    forcing=rows();g=geometry(forcing)
    assert np.allclose(joint(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states,model(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states,rtol=0,atol=1e-12)
def test_all_four_regimes_and_65_percent_prior_have_correct_solar_ordering():
    forcing=rows(1);g=geometry(forcing);m=joint(g);values={}
    for indoor in (0,1):
        for outdoor in (0,1):
            row=replace(forcing[0],indoor_shade_closed=indoor,outdoor_shade_present=outdoor)
            zero=replace(row,radiation_wm2=0)
            values[indoor,outdoor]=np.asarray(m.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=(row,)).states[0])-m.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=(zero,)).states[0]
        assert np.allclose(values[indoor,1],values[indoor,0]*.35,rtol=0,atol=1e-12)
    for out in (0,1):assert np.all(values[1,out]<=values[0,out])
def test_joint_sensitivities_match_finite_differences_in_removed_regime():
    forcing=tuple(replace(r,outdoor_shade_present=0) for r in rows());g=geometry(forcing);m=joint(g)
    actual=np.asarray(m.rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).sensitivities[-1]);numeric=np.zeros((2,14))
    for i in range(14):
        low=list(m.coefficients);high=list(m.coefficients);low[i]-=1e-7;high[i]+=1e-7
        a=api().NativeJointShadeDynamics(tuple(low),geometry=g,expected_series_sha256=g.sha256).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states[-1]
        b=api().NativeJointShadeDynamics(tuple(high),geometry=g,expected_series_sha256=g.sha256).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=forcing).states[-1]
        numeric[:,i]=(np.asarray(b)-a)/(2e-7)
    assert np.allclose(actual,numeric,rtol=1e-5,atol=1e-5)
def test_nominal_rating_and_zone_contract_do_not_invent_positions_or_weights():
    c=api().shade_contract()
    assert c['nominal_shade_rejection_fraction']==.65 and c['transmission_prior']==pytest.approx(.35)
    assert [r['id'] for r in c['outdoor_zones']]==['kitchen','living_room','bedroom_bathroom']
    assert c['outdoor_zones'][2]['rooms']==['Bedroom','Bathroom']
    assert c['automatic_reinstallation'] is False and 'zone_weights' not in c
@pytest.mark.parametrize('value',[None,float('nan'),-1,2])
def test_unknown_or_invalid_shade_state_remains_invalid(value):
    forcing=rows(1);g=geometry(forcing)
    with pytest.raises(ValueError):joint(g).rollout(origin_at=AT,air_f=72,mass_f=70,forcings=(replace(forcing[0],outdoor_shade_present=value),))
