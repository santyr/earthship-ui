"""Profiled storage changes the load forcing while preserving the original PV model."""
from datetime import timedelta
from copy import deepcopy
import importlib
import pytest
from test_household_ac_load_model import learn,END
from household_pv_model import simulate_storage
from household.codec import identity


def scenario():
    api,model=learn();issue=END+timedelta(hours=2)
    load=api.project_load(model,origin=issue,now=issue)
    steps=[dict(start=(issue+timedelta(hours=i)).isoformat(),end=(issue+timedelta(hours=i+1)).isoformat(),potential_pv_kwh=0.) for i in range(24)]
    return dict(steps=steps,initial_soc_pct=80.,nominal_bank_kwh=20.48,load_forecast=load)


def test_profiled_storage_accounts_hourly_load_and_keeps_sources_unchanged():
    args=scenario();original=deepcopy(args)
    result=importlib.import_module('household_profiled_storage').simulate_profiled_storage(**args)
    assert args==original and len(result['trajectory'])==24
    load=args['load_forecast']['total_ac_kwh']
    expected=20.48*.8-load/.95/.95
    assert result['trajectory'][-1]['nominal_energy_kwh']==pytest.approx(expected)
    assert result['load_forecast_sha256']==args['load_forecast']['forecast_sha256']
    assert result['load_assumption']=='profiled_mean_held_within_each_elapsed_hour'
    assert result['automatic_actuation'] is False and result['physical_calibration_qualified'] is False


def test_constant_profile_is_numerically_equal_to_the_original_constant_load_integrator():
    args=scenario();forecast=args['load_forecast']
    for row in forecast['trajectory']:row['mean_ac_w']=400.;row['ac_kwh']=.4
    forecast['total_ac_kwh']=9.6;forecast['forecast_sha256']=identity({k:v for k,v in forecast.items() if k!='forecast_sha256'})
    for row in args['steps']:row['potential_pv_kwh']=.8
    actual=importlib.import_module('household_profiled_storage').simulate_profiled_storage(**args)
    old=simulate_storage(steps=args['steps'],initial_soc_pct=80.,nominal_bank_kwh=20.48,load_ac_w=400.)
    for row,reference in zip(actual['trajectory'],old['trajectory']):
        assert row['at']==reference['at']
        for key in row:
            if key!='at':assert row[key]==pytest.approx(reference[key],abs=1e-10)


@pytest.mark.parametrize('damage',['changed_load','target_gap','PV_gap','short_load','negative_load','before_origin'])
def test_mismatched_or_changed_load_and_PV_arguments_refuse(damage):
    args=scenario();load=args['load_forecast']
    if damage=='changed_load':load['trajectory'][0]['mean_ac_w']+=1
    elif damage=='target_gap':load['trajectory'][1]['at']=load['trajectory'][0]['at']
    elif damage=='PV_gap':args['steps'].pop(4)
    elif damage=='short_load':load['trajectory'].pop()
    elif damage=='negative_load':load['trajectory'][0]['mean_ac_w']=-1
    else:args['steps'][0]['start']=(END-timedelta(hours=1)).isoformat()
    if damage!='changed_load':load['forecast_sha256']=identity({k:v for k,v in load.items() if k!='forecast_sha256'})
    with pytest.raises(ValueError):importlib.import_module('household_profiled_storage').simulate_profiled_storage(**args)
