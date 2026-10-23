"""Task accounting and useful choices through the existing nominal storage integrator."""
from datetime import timedelta
from copy import deepcopy
from test_household_advice_contract import run,policy,snapshot
from local_measurement_test_support import NOW
from household.codec import identity
from household_ac_load_model import RULE


def energy_case():
    # Local fixture: 24 complete elapsed hours; 1kW task initially in the first
    # dark hour. Solar starts next hour, so delaying avoids a hand-computable dip.
    origin=NOW
    # NOW is an exact hour in the maintained fixture.
    p=policy();p['energy']['loads']=[dict(id='dishwasher',devices=['dishwasher'],approved_discretionary=True,essential=False,
      power_w=1000.,duration_minutes=60,baseline_start=origin.isoformat(),deadline=(origin+timedelta(hours=4)).isoformat(),interruptible=False,profile_basis='operator_declared')]
    rows=[dict(at=(origin+timedelta(hours=i+1)).isoformat(),mean_ac_w=1100. if i==0 else 100.,ac_kwh=1.1 if i==0 else .1) for i in range(24)]
    forecast=dict(schema='earthship-ac-load-forecast/v1',model_rule=RULE,status='projected',origin=origin.isoformat(),model_sha256='a'*64,total_ac_kwh=3.4,trajectory=rows)
    forecast['forecast_sha256']=identity(forecast)
    steps=[dict(start=(origin+timedelta(hours=i)).isoformat(),end=(origin+timedelta(hours=i+1)).isoformat(),potential_pv_kwh=0. if i==0 else 2.) for i in range(24)]
    snap=snapshot();inputs=dict(snapshot_id=snap.snapshot_id,source_ref='d'*64,available_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=100)).isoformat(),steps=steps,
       initial_soc_pct=100.,nominal_bank_kwh=10.,baseline_load_forecast=forecast,task_baseline_included='dishwasher')
    return p,{'flexible_energy':inputs}


def test_delay_removes_original_task_before_rescheduling_without_double_counting():
    p,projections=energy_case();r=run(policy=p,projections=projections)
    assert r['domains']['energy']['status']=='recommendation_available',r['domains']['energy']
    rec=next(r for r in r['recommendations'] if r['kind']=='FLEXIBLE_LOAD_TIMING')
    assert rec['effects']['energy_kwh']==0. and rec['effects']['soc_pct']>0
    assert 'Delay dishwasher' in rec['action']
    assert rec['evidence_basis']=='model_compared'


def test_no_useful_task_never_invites_waste_even_at_full_battery():
    p,projections=energy_case();p['energy']['loads']=[]
    assert run(policy=p,projections=projections)['domains']['energy']['reason']=='no_approved_useful_flexible_task'


def test_essential_and_greywater_collateral_are_excluded():
    for key,value in [('essential',True),('devices',['dishwasher','greywater'])]:
        p,projections=energy_case();p['energy']['loads'][0][key]=value
        assert run(policy=p,projections=projections)['domains']['energy']['reason']=='no_approved_useful_flexible_task'


def test_two_loads_cannot_spend_same_headroom():
    p,projections=energy_case();other=deepcopy(p['energy']['loads'][0]);other['id']='washer';p['energy']['loads'].append(other)
    r=run(policy=p,projections=projections)
    assert r['domains']['energy']['status']=='conditional'
    assert not any(row['kind']=='FLEXIBLE_LOAD_TIMING' for row in r['recommendations'])


def test_missing_profile_and_infeasible_deadline_have_precise_reasons():
    p,projections=energy_case();p['energy']['loads'][0]['power_w']=None
    assert run(policy=p,projections=projections)['domains']['energy']['reason']=='flexible_load_profile_missing'
    p,projections=energy_case();p['energy']['loads'][0]['deadline']=NOW.isoformat()
    assert run(policy=p,projections=projections)['domains']['energy']['reason']=='task_deadline_infeasible'
