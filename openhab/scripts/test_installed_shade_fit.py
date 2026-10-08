"""Constrained development horizon identification, never release evidence."""
from dataclasses import replace
from datetime import timedelta
import time
import numpy as np
import pytest
from test_installed_shade_dynamics import AT, COEFFICIENTS
from test_installed_shade_inputs import snapshot, START, END, EPOCHS
from thermal_model.installed_shade_dynamics import InstalledShadeDynamics, InstalledShadeForcing
from thermal_model.installed_shade_inputs import DevelopmentEndpoint
from thermal_model.schema import ThermalSample


def module():
    from thermal_model import installed_shade_fit
    return installed_shade_fit


def endpoints(days=8):
    rng=np.random.default_rng(14);model=InstalledShadeDynamics(COEFFICIENTS);result=[]
    for day in range(days):
        at=AT+timedelta(days=day)
        air=float(rng.uniform(65,80));mass=float(rng.uniform(64,75))
        indoor=float(day%2);vent=float((day//2)%3)/2
        forcing=tuple(InstalledShadeForcing(at+timedelta(minutes=5*(i+1)),float(rng.uniform(45,80)),float(rng.uniform(100,500)),indoor,1.,vent) for i in range(12))
        final=model.rollout(origin_at=at,air_f=air,mass_f=mass,forcings=forcing).states[-1]
        origin=ThermalSample(at,air,mass,None,forcing[0].outdoor_f,200,vent,1,indoor,1,1,1,1,True,mode='warm')
        target=replace(origin,at=forcing[-1].at,air_f=final[0],mass_f=final[1])
        result.append(DevelopmentEndpoint(origin,target,forcing,'a'*64))
    return tuple(result)


@pytest.fixture
def optin(monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')


def test_vectorized_loss_and_gradient_match_exact_core_and_finite_differences():
    m=module();points=endpoints();batches=m._prepare_batches(points)
    p=np.asarray(COEFFICIENTS);loss,gradient,sensitivity=m._objective(p,batches)
    assert loss<1e-20 and sensitivity.shape==(16,10)
    shifted=p.copy();shifted[1]*=1.08
    loss,gradient,_=m._objective(shifted,batches)
    assert loss>0
    numeric=[]
    for index in range(10):
        step=np.zeros(10);step[index]=1e-7
        numeric.append((m._objective(shifted+step,batches)[0]-m._objective(shifted-step,batches)[0])/2e-7)
    assert np.allclose(gradient,numeric,rtol=1e-5,atol=1e-6)


def test_constrained_fit_reduces_loss_and_retains_exact_physics(optin):
    m=module();initial=list(COEFFICIENTS);initial[1]*=1.12
    fit=m._fit_endpoints(endpoints(),initial=tuple(initial),deadline=time.monotonic()+25)
    assert fit.final_objective<fit.initial_objective*.01
    assert fit.conditioning_rank==10 and fit.normalized_condition_number<m.NORMALIZED_CONDITION_NUMBER_LIMIT
    assert fit.model==InstalledShadeDynamics(fit.model.coefficients)
    assert fit.release_authorized is False


def test_rank_deficiency_is_refused_before_solver(optin,monkeypatch):
    m=module();points=endpoints();points=tuple(replace(point,origin=replace(point.origin,indoor_shade_closed=0),forcings=tuple(replace(row,indoor_shade_closed=0) for row in point.forcings)) for point in points)
    monkeypatch.setattr(m,'minimize',lambda *args,**kwargs:pytest.fail('rank deficient inputs reached solver'))
    with pytest.raises(ValueError,match='rank deficient'):m._fit_endpoints(points,initial=COEFFICIENTS,deadline=time.monotonic()+20)


def test_fitting_optin_precedes_any_solver_or_source_work(monkeypatch):
    m=module();monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','0');monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0')
    monkeypatch.setattr(m,'build_development_inputs',lambda *args,**kwargs:pytest.fail('source work before optin'))
    with pytest.raises(ValueError,match='opt-in'):m.fit_development_inputs({},expected_snapshot_sha256='a'*64,sensor_epochs=EPOCHS,assessed_at=END,training_start=START,training_end=END,initial=COEFFICIENTS)


def test_source_bound_training_refuses_missing_required_horizons_before_optimizer(optin,monkeypatch):
    m=module();record=snapshot();monkeypatch.setattr(m,'minimize',lambda *args,**kwargs:pytest.fail('incomplete horizon support reached solver'))
    with pytest.raises(ValueError,match='horizon'):m.fit_development_inputs(record,expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=EPOCHS,assessed_at=END,training_start=START,training_end=END,initial=COEFFICIENTS)


def test_short_history_does_not_claim_coefficient_stability():
    m=module();assessment=m._assess_stability(endpoints(),COEFFICIENTS,refitter=lambda _:pytest.fail('short history refit'))
    assert not assessment.assessed and assessment.independent_days==8
    assert assessment.refits==() and assessment.max_bound_span_fraction is None


def test_block_refits_remove_every_window_touching_withheld_days():
    m=module();points=endpoints(24);seen=[]
    def fit(retained):seen.append(retained);return COEFFICIENTS
    result=m._assess_stability(points,COEFFICIENTS,refitter=fit)
    assert result.assessed and len(result.refits)==4 and result.max_bound_span_fraction==0
    assert sum(len(row.omitted_days) for row in result.refits)==24
    for refit,retained in zip(result.refits,seen):
        omitted=set(refit.omitted_days)
        assert all(point.origin.at.astimezone(m.DENVER).date().isoformat() not in omitted and point.target.at.astimezone(m.DENVER).date().isoformat() not in omitted for point in retained)
    assert result.release_authorized is False


def test_instability_is_refused_without_relaxing_span_threshold():
    m=module();changed=list(COEFFICIENTS);changed[1]+=.14
    with pytest.raises(ValueError,match='instability'):m._assess_stability(endpoints(24),COEFFICIENTS,refitter=lambda _:tuple(changed))


def test_expired_fit_deadline_stops_before_optimizer(optin,monkeypatch):
    m=module();monkeypatch.setattr(m,'minimize',lambda *args,**kwargs:pytest.fail('expired workload reached solver'))
    with pytest.raises(ValueError,match='deadline'):m._fit_endpoints(endpoints(),initial=COEFFICIENTS,deadline=time.monotonic()-1)


@pytest.mark.parametrize('failure',['optimizer','nonfinite','shade_order','worsening'])
def test_solver_failure_invalid_physics_and_worsening_never_return_model(optin,monkeypatch,failure):
    from types import SimpleNamespace
    m=module();p=np.asarray(COEFFICIENTS).copy()
    if failure=='nonfinite':p[0]=float('nan')
    elif failure=='shade_order':p[2]=p[3]+.0001
    elif failure=='worsening':p[1]*=1.1
    x=(p-np.asarray(m.LOWER))/(np.asarray(m.UPPER)-m.LOWER)
    monkeypatch.setattr(m,'minimize',lambda *args,**kwargs:SimpleNamespace(success=failure!='optimizer',x=x,nit=1))
    with pytest.raises(ValueError):m._fit_endpoints(endpoints(),initial=COEFFICIENTS,deadline=time.monotonic()+20)


def test_normalized_near_singularity_is_refused():
    m=module();matrix=np.eye(10);matrix[:,9]=matrix[:,8]+1e-10*matrix[:,9]
    assert np.linalg.matrix_rank(matrix)==10
    with pytest.raises(ValueError,match='ill-conditioned'):m._conditioning(matrix)


def test_overlapping_windows_are_counted_separately_from_local_dates():
    m=module();points=endpoints(3);first=points[0]
    overlapping=replace(first,origin=replace(first.origin,at=first.origin.at+timedelta(minutes=10)),target=replace(first.target,at=first.target.at+timedelta(minutes=10)))
    assert m._nonoverlap_count((first,overlapping,points[1]))==2



def test_original_native_snapshot_binding_and_exclusive_training_cutoff(optin,monkeypatch):
    m=module();record=snapshot(steps=576);cutoff=START+timedelta(hours=30);calls=[]
    model=InstalledShadeDynamics(COEFFICIENTS)
    def fitter(points,**kwargs):
        calls.append(points)
        return m.EndpointFit(model,1.,.5,10,10.,1)
    monkeypatch.setattr(m,'_fit_endpoints',fitter)
    result=m.fit_development_inputs(record,expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=EPOCHS,assessed_at=START+timedelta(hours=48),training_start=START,training_end=cutoff,initial=COEFFICIENTS)
    assert len(calls)==1 and all(START<=p.origin.at<p.target.at<cutoff for p in calls[0])
    assert {len(p.forcings)//12 for p in calls[0]}=={1,6,12,24}
    assert result.source_snapshot_sha256==record['snapshot_sha256']
    assert result.sensor_epochs==tuple(sorted(EPOCHS.items()))
    assert result.training_end==cutoff and not result.stability.assessed
    assert result.release_authorized is False and result.as_issued_evidence is False
    assert all(count<=dict(result.origin_counts)[h] for h,count in result.independent_window_counts)


@pytest.mark.parametrize('timeout',[True,0,91,float('inf'),float('nan')])
def test_invalid_deadline_budget_is_refused_before_source_work(optin,monkeypatch,timeout):
    m=module();monkeypatch.setattr(m,'build_development_inputs',lambda *args,**kwargs:pytest.fail('invalid timeout reached source work'))
    with pytest.raises(ValueError,match='timeout'):m.fit_development_inputs({},expected_snapshot_sha256='a'*64,sensor_epochs=EPOCHS,assessed_at=END,training_start=START,training_end=END,initial=COEFFICIENTS,timeout_seconds=timeout)



def test_block_refit_cannot_silently_drop_an_entire_training_horizon():
    m=module();points=endpoints(24);point=points[0]
    forcing=tuple(replace(row,at=point.origin.at+timedelta(minutes=5*(index+1)),radiation_wm2=0,outdoor_f=55) for index,row in enumerate(point.forcings*6))
    final=InstalledShadeDynamics(COEFFICIENTS).rollout(origin_at=point.origin.at,air_f=point.origin.air_f,mass_f=point.origin.mass_f,forcings=forcing).states[-1]
    longer=replace(point,target=replace(point.target,at=forcing[-1].at,air_f=final[0],mass_f=final[1]),forcings=forcing)
    with pytest.raises(ValueError,match='horizon'):m._assess_stability(points+(longer,),COEFFICIENTS,refitter=lambda _:COEFFICIENTS)
