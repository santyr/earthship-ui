"""Bounded useful flexible-load comparisons using existing nominal storage."""
from .contracts import closed,number
from .policy import EXCLUDED
from ..control_contracts import instant
from ..codec import identity


def energy_advice(report,snap,projections,policy,state,now):
    from . import _domain,_reading,_compare,_recommend
    p=policy['energy']
    if p is None:return _domain('unavailable','energy_policy_missing',['energy'])
    eligible=[load for load in p['loads'] if load['approved_discretionary'] and not load['essential'] and not {v.lower() for v in (set(load['devices'])|{load['id']})}&{v.lower() for v in EXCLUDED}]
    if not eligible:return _domain('no_change_recommended','no_approved_useful_flexible_task')
    if len(eligible)>1:return _domain('conditional','multiple_tasks_require_shared_allocation',['choose_one_flexible_task'])
    load=eligible[0]
    if load['power_w'] is None or load['duration_minutes'] is None:return _domain('insufficient_evidence','flexible_load_profile_missing',['power_w','duration_minutes'])
    soc=_reading(snap,'energy','battery_soc',now)
    if soc is None:return _domain('insufficient_evidence','battery_evidence_unavailable',['battery_soc'])
    inputs=projections.get('flexible_energy')
    if inputs is None:return _domain('insufficient_evidence','bound_energy_scenario_unavailable',['pv_storage_and_baseline_load_profile'])
    closed(inputs,{'snapshot_id','source_ref','available_at','valid_until','steps','initial_soc_pct','nominal_bank_kwh','baseline_load_forecast','task_baseline_included'})
    if inputs['snapshot_id']!=report['snapshot_id'] or not instant(inputs['available_at'])<=now<instant(inputs['valid_until']):raise ValueError('energy scenario source differs')
    number(inputs['nominal_bank_kwh'],.001,10000)
    if inputs['initial_soc_pct']!=soc['value'] or inputs['task_baseline_included']!=load['id']:raise ValueError('explicit baseline task accounting required')
    from .energy_compare import compare_load_windows
    result=compare_load_windows(inputs=inputs,load=load,now=now,reserve=p['reserve_soc_pct'])
    if result['reason'] is not None:return _domain('conditional',result['reason'],comparison=result['comparison'])
    base=result['baseline'];best=result['best'];delta=best['minimum_soc']-base['minimum_soc']
    if best['start']==base['start'] or delta<p['minimum_benefit_soc_pct']:
        return _domain('no_change_recommended','no_material_reserve_advantage',comparison=result['comparison'])
    baseline=dict(state=load['baseline_start'],basis='declared_scheduled_task',revision=identity(load),until=instant(inputs['valid_until']),ref=identity(load))
    rec=_recommend(report,policy,'FLEXIBLE_LOAD_TIMING',load['id'],f'Delay {load["id"]} until {best["start"]}; finish by {load["deadline"]}',baseline,
        'The compared schedule improves the minimum modeled nominal reserve while completing this useful task before its deadline.',result['comparison'],[soc,dict(ref=inputs['source_ref'],until=instant(inputs['valid_until']))],
        effects=dict(thermal_f=None,soc_pct=delta,energy_kwh=0.),start=instant(best['start']),end=instant(load['deadline']),action_spec=dict(scheduled_start=best['start']))
    if rec:
        rec['limitations'].append('Task energy is shifted once; independent fixed demand remains in the baseline. Modeled reserve is not a protection guarantee.')
        rec['model_refs']=[inputs['baseline_load_forecast']['model_sha256']]
        rec['recommendation_id']=identity({k:v for k,v in rec.items() if k!='recommendation_id'})
    return _domain('recommendation_available','flexible_load_reserve_comparison',comparison=result['comparison'])
