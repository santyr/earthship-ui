#!/usr/bin/env python3
"""Same-issue nominal energy trajectories inform a separate, disabled shadow plan."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import argparse,sys
from household.codec import canonical,loads,identity
from household.evidence import utc
from household.control_contracts import instant,ContractRefused
from household.model_snapshot import restore_snapshot
from household.capabilities import CapabilityRegistry
from household.pipeline import replay_pipeline,_intent
from household.legacy_planning import seal_plan,_runtime_manifest
from household_energy_forecast import replay_energy_forecast,forecast_runtime_manifest
from household_profiled_forecast import replay_profiled_forecast,profiled_runtime_manifest,MODULES
from household_outcomes import original_plan_runtime
from household_snapshot import _read

SCHEMA='earthship-household-trajectory-shadow-receipt/v1'
MAX_BYTES=2*1024*1024
FIELDS={'schema','inputs','runtime_manifest','load_runtime_manifest','output','receipt_sha256'}
INPUTS={'plan_document_sha256','plan_receipt_sha256','energy_document_sha256','energy_receipt_sha256',
        'profiled_document_sha256','profiled_receipt_sha256','assessed_at'}
OWN='openhab/scripts/household_trajectory_plan.py'
PROFILE_KEYS={'openhab/scripts/'+name for name in MODULES}


def trajectory_runtime_manifest():
    result=forecast_runtime_manifest();result.update(profiled_runtime_manifest())
    result[OWN]=sha256(_read(Path(__file__).resolve(),262144)).hexdigest()
    return result


def _runtime_parts(value):
    runtime=_runtime_manifest(value)
    if not PROFILE_KEYS|{OWN}<=set(runtime):raise ValueError('complete trajectory planner runtime required')
    return runtime,{k:v for k,v in runtime.items() if k not in PROFILE_KEYS|{OWN}},{k:runtime[k] for k in PROFILE_KEYS}


def _original(value,maximum):
    raw=canonical(value)
    if len(raw)>maximum:raise ValueError('bounded original trajectory context required')
    return loads(raw)


def _source_refs(snapshot,now):
    """Fresh measured inputs and forecast provenance, never model confidence."""
    doc=snapshot.to_dict();refs=[]
    for domain,role in (('energy','battery_soc'),('energy','estimated_load_w')):
        row=doc['domains'][domain][role];ref=row['evidence']
        if row['value'] is None or row['reason'] is not None or ref is None or ref['quality']!='qualified':return [],'source_unavailable'
        observed=ref['observed_at'] or ref['received_at'];age=doc['temporal_policy']['max_age_seconds'].get(role)
        if observed is None or type(age) is not int or age<=0:return [],'source_unavailable'
        if (instant(ref['available_at'])>now or instant(ref['assessed_at'])>now or now>=instant(ref['valid_until']) or
            now-instant(observed)>timedelta(seconds=age)):return [],'source_stale'
        refs.append(ref['digest'])
    # Forecast provenance is a retained context, never a measured observation.
    row=doc['domains']['weather']['forecast_issue'];ref=row['evidence']
    if row['value'] is None or row['reason'] is not None or ref is None or ref['quality']!='retained_forecast_context':return [],'source_unavailable'
    if instant(ref['available_at'])>now or now>=instant(ref['valid_until']):return [],'source_stale'
    return list(dict.fromkeys(refs)),None


def _projection(energy,profiled,*,origin,now,horizon):
    storage=energy['output']['nominal_storage'];basis='constant_load_pv';selected=None
    why='load_scenario_unavailable' if profiled is None else profiled['output']['reason']
    if profiled is not None and profiled['output']['status']=='conditional_nominal_simulation':
        source=profiled['inputs']['load_source'];until=source['artifact']['profile']['valid_until']
        if until is not None and now<instant(until):
            storage=profiled['output']['profiled_storage'];basis='profiled_load_pv';selected=source;why=None
        else:why='load_model_expired'
    result=dict(status='unavailable',reason='storage_trajectory_unavailable',basis=None,selection_reason=why,origin=origin.isoformat(),horizon_hours=horizon,
        initial_soc_pct=None,minimum_nominal_soc_pct=None,final_nominal_soc_pct=None,modeled_captured_pv_kwh=None,modeled_unaccepted_pv_kwh=None,
        modeled_unserved_dc_kwh=None,load_model_artifact_sha256=None,trajectory=[],physical_calibration_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    available=(selected is not None or storage['status']=='conditional_nominal_simulation')
    if not available:return result,None
    rows=storage['trajectory'][:horizon]
    if len(rows)!=horizon or any(instant(r['at'])!=origin+timedelta(hours=i+1) for i,r in enumerate(rows)):raise ValueError('complete same-issue energy horizon required')
    initial=storage['initial_soc_pct'];last=rows[-1]
    result.update(status='projected_nominal_scenario',reason=None,basis=basis,initial_soc_pct=initial,
        minimum_nominal_soc_pct=min(initial,*(r['nominal_soc_pct'] for r in rows)),final_nominal_soc_pct=last['nominal_soc_pct'],
        modeled_captured_pv_kwh=last['cumulative_modeled_captured_pv_kwh'],modeled_unaccepted_pv_kwh=last['cumulative_modeled_unaccepted_pv_kwh'],
        modeled_unserved_dc_kwh=last['cumulative_modeled_unserved_dc_kwh'],load_model_artifact_sha256=None if selected is None else selected['artifact']['artifact_sha256'],trajectory=rows)
    return result,selected


def seal_trajectory_plan(*,plan_receipt,energy_receipt,profiled_receipt,now,runtime_manifest,thermal_runtime,load_runtime_manifest):
    runtime,er,fr=_runtime_parts(runtime_manifest);now=utc(now)
    plan=_original(plan_receipt,MAX_BYTES);energy=_original(energy_receipt,262144)
    profiled=None if profiled_receipt is None else _original(profiled_receipt,262144)
    if plan.get('schema')!='earthship-household-model-plan-receipt/v6':raise ValueError('configured original rolling plan required')
    original_runtime=original_plan_runtime(plan,actual=runtime)
    replay_pipeline(plan,runtime_manifest=original_runtime,thermal_runtime=thermal_runtime)
    replay_energy_forecast(energy,plan_receipt=plan,runtime_manifest=er)
    if profiled is not None:
        replay_profiled_forecast(profiled,energy_receipt=energy,plan_receipt=plan,runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=load_runtime_manifest)
    elif load_runtime_manifest:raise ValueError('absent load scenario cannot bind model runtime')
    snap=plan['inputs']['snapshot'];origin=instant(snap['as_of']);config=plan['inputs']['config'];horizon=config['horizon_hours']
    if instant(energy['output']['array_pv']['origin'])!=origin:raise ValueError('energy issue differs from frozen shared snapshot')
    clocks=[instant(plan['inputs']['now']),instant(energy['inputs']['assessed_at'])]
    if profiled is not None:clocks.append(instant(profiled['inputs']['assessed_at']))
    if not max(clocks)<=now<=origin+timedelta(seconds=120):raise ValueError('bounded same-issue shadow decision clock required')
    snapshot=restore_snapshot(snap,plan['inputs']['source_contexts']);registry_doc=plan['inputs']['registry']
    registry=CapabilityRegistry(canonical({k:v for k,v in registry_doc.items() if k!='registry_id'}))
    if registry.registry_id!=registry_doc['registry_id']:raise ValueError('original registry identity differs')
    projection,load_source=_projection(energy,profiled,origin=origin,now=now,horizon=horizon)
    refs,reason=_source_refs(snapshot,now);candidates=[];utilities={}
    if reason is None and projection['status']!='projected_nominal_scenario':reason=projection['reason']
    if reason is None:
        specs=[];excess=projection['modeled_unaccepted_pv_kwh'];minimum=projection['minimum_nominal_soc_pct']
        if excess>0:specs.append(('RUN_GREYWATER_CYCLE',{},'unqualified_effect',excess*config['surplus_weight']))
        if minimum<config['low_trough_threshold_soc_pct']:
            specs.append(('SET_NIGHT_LOAD_OVERRIDE',{'command':'OFF'},'low_soc',(config['low_trough_threshold_soc_pct']-minimum)*config['reserve_weight']))
        try:
            for kind,parameters,why,utility in specs:
                item=_intent(snapshot,now,kind,parameters,refs,why);candidates.append(item);utilities[item.intent_id]=utility
        except ContractRefused as error:reason=error.reason_code;candidates=[];utilities={}
    candidates.sort(key=lambda item:item.intent_id)
    model_refs=[]
    if load_source is not None:
        profile=load_source['artifact']['profile']
        model_refs.append(dict(artifact_sha256=load_source['artifact']['artifact_sha256'],runtime_sha256=identity(load_runtime_manifest),
            projection_sha256=profiled['output']['load_forecast']['forecast_sha256'],available_at=load_source['available_at'],valid_until=profile['valid_until'],confidence='low'))
    selected=profiled if load_source is not None else energy
    shadow=seal_plan(snapshot=snapshot,registry=registry,candidates=candidates,coordination=plan['inputs']['coordination'],utilities=utilities,
        now=now,reserve_soc=config['reserve_soc'],horizon_hours=horizon,runtime_manifest=runtime,model_refs=model_refs,
        forecast_ref=dict(original_sha256=identity(selected),issued_at=origin.isoformat(),available_at=selected['inputs']['assessed_at'],horizon_hours=horizon))
    thermal=plan['output']['projections']['thermal']
    generation=dict(status='unavailable' if reason else 'generated_shadow_only',reason=reason,action_effects_qualified=False,
        input_qualification='conditional_uncalibrated_scenario',objective_units=dict(surplus_weight='declared_preference_points_per_nominal_unaccepted_DC_kWh',
            reserve_weight='declared_preference_points_per_nominal_soc_percentage_point'))
    value=dict(schema=SCHEMA,inputs=dict(plan_document_sha256=identity(plan),plan_receipt_sha256=plan['receipt_sha256'],energy_document_sha256=identity(energy),
        energy_receipt_sha256=energy['receipt_sha256'],profiled_document_sha256=None if profiled is None else identity(profiled),
        profiled_receipt_sha256=None if profiled is None else profiled['receipt_sha256'],assessed_at=now.isoformat()),runtime_manifest=runtime,load_runtime_manifest=dict(load_runtime_manifest),
        output=dict(snapshot_id=snapshot.snapshot_id,energy_projection=projection,thermal_projection_sha256=None if thermal is None else thermal['projection_sha256'],
            candidate_generation=generation,candidate_intents=[item.to_dict() for item in candidates],no_action_intent=_intent(snapshot,now,'NO_ACTION',{},[],'no_optional_action').to_dict(),
            plan_receipt=shadow,action_effects_qualified=False,automatic_actuation=False))
    value['receipt_sha256']=identity(value)
    return _original(value,MAX_BYTES)


def replay_trajectory_plan(receipt,**context):
    if (not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!=SCHEMA or len(canonical(receipt))>MAX_BYTES or
        not isinstance(receipt['inputs'],dict) or set(receipt['inputs'])!=INPUTS or
        identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})!=receipt['receipt_sha256'] or
        canonical(receipt['runtime_manifest'])!=canonical(context['runtime_manifest']) or canonical(receipt['load_runtime_manifest'])!=canonical(context['load_runtime_manifest'])):
        raise ValueError('closed original trajectory shadow receipt required')
    value=seal_trajectory_plan(now=instant(receipt['inputs']['assessed_at']),**context)
    if canonical(value)!=canonical(receipt):raise ValueError('original trajectory shadow plan differs')
    return value


def main(argv=None):
    from datetime import datetime,timezone
    from household_pipeline import thermal_execution_runtime
    from household_ac_load_artifact import runtime_manifest as load_runtime
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('receipt','plan','energy'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--profiled',type=Path);args=parser.parse_args(argv)
    try:
        files=[(p,_read(p,limit,private=True)) for p,limit in ((args.receipt,MAX_BYTES),(args.plan,MAX_BYTES),(args.energy,262144))]
        if args.profiled is not None:files.append((args.profiled,_read(args.profiled,262144,private=True)))
        receipt,plan,energy=[loads(raw) for _,raw in files[:3]];profiled=None if len(files)==3 else loads(files[3][1])
        if instant(receipt['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future shadow decision refused')
        runtime=trajectory_runtime_manifest();thermal=thermal_execution_runtime(Path(__file__).resolve().parent,plan['inputs']['thermal_inputs'])
        lr={} if profiled is None or profiled['inputs']['load_source'] is None else load_runtime()
        value=replay_trajectory_plan(receipt,plan_receipt=plan,energy_receipt=energy,profiled_receipt=profiled,runtime_manifest=runtime,thermal_runtime=thermal,load_runtime_manifest=lr)
        if (trajectory_runtime_manifest()!=runtime or thermal_execution_runtime(Path(__file__).resolve().parent,plan['inputs']['thermal_inputs'])!=thermal or
            lr and load_runtime()!=lr or any(_read(p,MAX_BYTES,private=True)!=raw for p,raw in files)):raise ValueError('original shadow inputs or executing runtime changed')
        sys.stdout.buffer.write(canonical(value)+b'\n');return 0
    except Exception:
        print('Trajectory shadow replay refused: invalid or changed original context.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
