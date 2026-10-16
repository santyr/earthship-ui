"""Measured regimes are distinguished from transferred solar priors."""
import time
import numpy as np
import pytest
from native_thermal_inputs import select_native_endpoints
from native_thermal_fit import fit_native_development,prepare_native_batches
from test_native_thermal_inputs import build
from test_installed_shade_inputs import snapshot,START,END
from thermal_model.provisional_fit import DEFAULT_PRIOR
from native_joint_shade import expand_installed_prior

@pytest.mark.parametrize('state',['installed','removed'])
def test_joint_endpoints_accept_either_known_regime_and_freeze_original_outdoor_state(state):
    data=build(snapshot(initial_outdoor=state))
    points=select_native_endpoints(data,horizon_hours=1,start=START,end=END,joint=True)
    assert len(points)==1
    assert all(r.outdoor_shade_present==(state=='installed') for r in points[0].forcings)
    if state=='removed':assert not select_native_endpoints(data,horizon_hours=1,start=START,end=END)

def test_joint_objective_gradient_matches_independent_finite_differences():
    from native_joint_shade import objective
    data=build(snapshot(initial_outdoor='removed'))
    batches=prepare_native_batches(data,training_start=START,training_end=END,deadline=time.monotonic()+20,guard=lambda:None,joint=True)
    p=expand_installed_prior(DEFAULT_PRIOR);loss,gradient,_=objective(p,batches)
    numerical=[]
    for i in range(14):
        a=list(p);b=list(p);a[i]-=1e-7;b[i]+=1e-7
        numerical.append((objective(tuple(b),batches)[0]-objective(tuple(a),batches)[0])/(2e-7))
    assert np.allclose(gradient,numerical,rtol=1e-5,atol=1e-5)
    assert all(not a.flags.writeable for batch in batches for a in batch)

@pytest.mark.parametrize('state',['installed','removed'])
def test_joint_fit_keeps_unobserved_regimes_explicitly_prior_only(state,monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1');data=build(snapshot(initial_outdoor=state))
    f=fit_native_development(data,expected_dataset_sha256=data.sha256,training_start=START,training_end=END,guard=lambda:None,timeout_seconds=20,joint=True)
    assert len(f['coefficients'])==14 and f['schema']=='earthship-native-solar-provisional-fit/v2'
    assert f['model_rule']=='earthship-native-joint-shade-dynamics/v3'
    assert f['shade_context']['nominal_shade_rejection_fraction']==.65
    observed='outdoor_only' if state=='installed' else 'unshaded'
    assert f['regime_support'][observed]['endpoint_count']==1
    assert all(s['status']=='prior_only' for k,s in f['regime_support'].items() if k!=observed)
    assert f['confidence']=='low' and f['prediction_intervals'] is None and not f['automatic_actuation']

def test_solar_support_never_uses_samples_after_the_training_cutoff():
    from datetime import timedelta
    from native_joint_shade import regime_support
    data=build(snapshot());s=regime_support(data,(),start=START,end=START+timedelta(minutes=10))
    assert sum(r['daylight_sample_count'] for r in s.values())==2

def test_night_endpoints_do_not_claim_observed_solar_gain():
    from native_joint_shade import regime_support
    data=build(snapshot(initial_outdoor='removed'),degrees=-1)
    points=select_native_endpoints(data,horizon_hours=1,start=START,end=END,joint=True)
    s=regime_support(data,points);assert s['unshaded']['endpoint_count']==1
    assert s['unshaded']['daylight_sample_count']==0 and s['unshaded']['status']=='prior_only'
