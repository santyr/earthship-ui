"""Bounded prior-regularized native development fitting never claims release."""
from datetime import timedelta
import importlib,time
import numpy as np
import pytest
from test_native_thermal_inputs import build
from test_installed_shade_inputs import snapshot,START,END
from thermal_model.provisional_fit import DEFAULT_PRIOR

def api():return importlib.import_module('native_thermal_fit')


def fit(data,**kwargs):
    return api().fit_native_development(data,expected_dataset_sha256=data.sha256,
        training_start=START,training_end=END,guard=lambda:None,timeout_seconds=20,**kwargs)


def test_native_batches_objective_derivatives_match_finite_differences():
    data=build(snapshot())
    batches=api().prepare_native_batches(data,training_start=START,training_end=END,deadline=time.monotonic()+20,guard=lambda:None)
    from thermal_model.installed_shade_fit import _objective
    value,gradient,_=_objective(DEFAULT_PRIOR,batches)
    numeric=[]
    for column in range(10):
        low=list(DEFAULT_PRIOR);high=list(DEFAULT_PRIOR);low[column]-=1e-7;high[column]+=1e-7
        numeric.append((_objective(tuple(high),batches)[0]-_objective(tuple(low),batches)[0])/(2e-7))
    assert np.allclose(gradient,numeric,rtol=1e-5,atol=1e-5)
    assert all(not array.flags.writeable for batch in batches for array in batch)


def test_real_short_native_fit_preserves_weak_support_and_complete_lineage(monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1');data=build(snapshot());result=fit(data)
    assert result['schema']=='earthship-native-solar-provisional-fit/v1'
    assert result['dataset_sha256']==data.sha256 and result['geometry_series_sha256']==data.geometry.sha256
    assert result['source_snapshot_sha256']==data.development.source_snapshot_sha256
    assert result['final_objective']<=result['initial_objective']
    assert result['confidence']=='low' and not result['graduated'] and not result['automatic_actuation']
    assert result['conditioning_rank']<10 and result['normalized_condition_number'] is None
    assert result['endpoint_count']==1 and result['horizon_support']=={'1':1,'6':0,'12':0,'24':0}


def test_native_fit_requires_explicit_workload_optin_and_matching_dataset(monkeypatch):
    monkeypatch.delenv('EARTHSHIP_QUALIFICATION_FIT',raising=False);monkeypatch.delenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT',raising=False)
    data=build(snapshot())
    with pytest.raises(ValueError):fit(data)
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    with pytest.raises(ValueError):api().fit_native_development(data,expected_dataset_sha256='f'*64,
        training_start=START,training_end=END,guard=lambda:None,timeout_seconds=20)


@pytest.mark.parametrize('reason',['expired','resource'])
def test_native_fit_refuses_expired_budget_or_resource_guard_before_optimizer(reason,monkeypatch):
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1');data=build(snapshot())
    def refused():raise ValueError('test resource refusal')
    monkeypatch.setattr(api(),'minimize',lambda *a,**k:pytest.fail('refused fit ran optimizer'))
    if reason=='expired':
        with pytest.raises(ValueError):api().prepare_native_batches(data,training_start=START,training_end=END,deadline=time.monotonic()-1,guard=lambda:None)
    else:
        with pytest.raises(ValueError):api().fit_native_development(data,expected_dataset_sha256=data.sha256,
            training_start=START,training_end=END,guard=refused,timeout_seconds=20)
