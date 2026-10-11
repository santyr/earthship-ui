"""Pure model-to-shadow-plan rederivation; numerical output grants no authority."""
from datetime import timedelta
import math
from .codec import canonical,loads,identity
from .evidence import utc
from .snapshot import HouseholdSnapshot
from .capabilities import CapabilityRegistry
from .energy_model import FrozenEnergyInputs,project_energy
from .thermal_model import PreparedProjection,project as project_thermal
from .intents import build_intent,EFFECT_UNITS
from .control_contracts import instant,ContractRefused
from .planning import seal_plan,_runtime_manifest,MIN_RESERVE_SOC

MAX_BYTES=1024*1024
CONFIG_FIELDS={'horizon_hours','reserve_soc','low_trough_threshold_soc_pct','surplus_weight','reserve_weight','comfort_min_f','comfort_max_f'}
INPUT_FIELDS={'snapshot','registry','energy_inputs','thermal_inputs','coordination','config','now'}
FIELDS={'schema','inputs','runtime_manifest','output','receipt_sha256'}


def _config(value):
    if not isinstance(value,dict) or set(value)!=CONFIG_FIELDS:raise ValueError('closed planner preference config required')
    value=loads(canonical(value))
    if type(value['horizon_hours']) is not int or value['horizon_hours'] not in (6,12,24):raise ValueError('explicit supported horizon required')
    for name,low,high in (('reserve_soc',MIN_RESERVE_SOC,100),('low_trough_threshold_soc_pct',10,100),
        ('surplus_weight',0,100),('reserve_weight',0,100),('comfort_min_f',-50,150),('comfort_max_f',-50,150)):
        number=value[name]
        if type(number) not in (int,float) or not math.isfinite(number) or not low<=number<=high:raise ValueError('bounded finite preference required')
    if value['comfort_min_f']>=value['comfort_max_f']:raise ValueError('ordered comfort bounds required')
    return value


def _restore(document,kind,key):
    if not isinstance(document,dict) or key not in document:raise ValueError('original immutable identity required')
    value=kind(canonical({name:item for name,item in document.items() if name!=key}))
    if getattr(value,key)!=document[key]:raise ValueError('original immutable identity differs')
    return value


def _projections(snapshot,energy_inputs,thermal_inputs,thermal_runtime,now,horizon):
    snap=snapshot.to_dict();energy=None;thermal=None
    if energy_inputs is not None:
        if not isinstance(energy_inputs,FrozenEnergyInputs):raise ValueError('frozen energy context required')
        reference=energy_inputs.to_dict()['inputs']['soc_pct']
        if reference is not None and reference!=snap['domains']['energy']['battery_soc']['value']:
            raise ValueError('energy SoC reference differs from shared snapshot')
        energy=project_energy(energy_inputs)
    if thermal_inputs is not None:
        if not isinstance(thermal_inputs,PreparedProjection):raise ValueError('prepared original thermal context required')
        value=thermal_inputs.to_dict();original=value['snapshot']
        if canonical(thermal_runtime)!=canonical(value['executing_runtime']):raise ValueError('executing thermal model runtime differs')
        if instant(original['as_of'])!=instant(snap['as_of']) or instant(value['issue'])!=instant(snap['as_of']):
            raise ValueError('thermal origin differs from shared snapshot clock')
        if (instant(original['created_at'])>now or value['horizon_hours']<horizon or
            now>=instant(value['issue'])+timedelta(hours=value['horizon_hours'])):
            raise ValueError('thermal forecast unavailable at decision')
        for domain,role in (('thermal','air_temperature'),('thermal','mass_temperature'),('weather','outdoor_temperature')):
            if canonical(snap['domains'][domain][role])!=canonical(original['domains'][domain][role]):
                raise ValueError('thermal measurement differs from shared snapshot')
        thermal=project_thermal(thermal_inputs)
    elif thermal_runtime is not None:raise ValueError('unexpected thermal runtime context')
    return dict(energy=energy,thermal=thermal)


def _intent(snapshot,now,kind,parameters,refs,reason):
    return build_intent(dict(schema='earthship-household-intent/v1',type=kind,
        createdAt=now.isoformat(),expiresAt=(now+timedelta(seconds=120)).isoformat(),snapshotId=snapshot.snapshot_id,
        evidenceRefs=refs,predictedEffects={key:None for key in EFFECT_UNITS},confidence='unavailable',
        reasonCodes=[reason],shadowOnly=True,parameters=parameters),snapshot=snapshot,now=now)


def _candidates(snapshot,projections,config,now):
    no_action=_intent(snapshot,now,'NO_ACTION',{},[],'no_optional_action')
    energy=projections['energy'];items=[];utilities={};reason=None
    if energy is None or energy['output']['trough_pred'] is None:
        reason='source_unavailable'
    else:
        row=snapshot.to_dict()['domains']['energy']['battery_soc'];ref=row['evidence']
        if row['value'] is None or row['reason'] is not None or ref is None or ref['quality']!='qualified':reason='source_unavailable'
        else:
            try:
                # Same typed source validator as the final arbiter, not a numeric fallback.
                _intent(snapshot,now,'RUN_GREYWATER_CYCLE',{},[ref['digest']],'unqualified_effect')
            except ContractRefused as error:reason=error.reason_code
        if reason is None:
            output=energy['output'];specs=[]
            if output['curtail']>0:
                specs.append(('RUN_GREYWATER_CYCLE',{},'unqualified_effect',output['curtail']*config['surplus_weight']))
            if output['trough_pred']<config['low_trough_threshold_soc_pct']:
                specs.append(('SET_NIGHT_LOAD_OVERRIDE',{'command':'OFF'},'low_soc',
                    (config['low_trough_threshold_soc_pct']-output['trough_pred'])*config['reserve_weight']))
            for kind,parameters,why,utility in specs:
                item=_intent(snapshot,now,kind,parameters,[ref['digest']],why)
                items.append(item);utilities[item.intent_id]=utility
    items.sort(key=lambda item:item.intent_id)
    return items,utilities,no_action,dict(status='unavailable' if reason else 'generated_shadow_only',reason=reason,
        action_effects_qualified=False,input_qualification='not_assessed',
        objective_units=dict(surplus_weight='declared_preference_points_per_curtailment_proxy_hour',
            reserve_weight='declared_preference_points_per_predicted_soc_percentage_point'))


def _comfort(thermal,config,now):
    if thermal is None:return None
    start=instant(thermal['output']['generated_at']);end=start+timedelta(hours=config['horizon_hours'])
    values=[row['air_f'] for row in thermal['output']['trajectory'] if start<instant(row['at'])<=end]
    return dict(basis='hourly_baseline_forecast',horizon_hours=config['horizon_hours'],
        below_minimum_samples=sum(value<config['comfort_min_f'] for value in values),
        above_maximum_samples=sum(value>config['comfort_max_f'] for value in values),
        samples=len(values),unit='hourly_samples',counterfactual_effects_qualified=False)


def seal_pipeline(*,snapshot,registry,energy_inputs,thermal_inputs,thermal_runtime,coordination,config,now,runtime_manifest):
    if not isinstance(snapshot,HouseholdSnapshot) or not isinstance(registry,CapabilityRegistry):raise ValueError('immutable shared context required')
    now=utc(now);config=_config(config);runtime=_runtime_manifest(runtime_manifest)
    snap=snapshot.to_dict()
    if instant(snap['as_of'])>now or instant(snap['created_at'])>now:raise ValueError('shared snapshot unavailable at decision')
    coordination=loads(canonical(coordination))
    projections=_projections(snapshot,energy_inputs,thermal_inputs,thermal_runtime,now,config['horizon_hours'])
    candidates,utilities,no_action,generation=_candidates(snapshot,projections,config,now)
    plan_receipt=seal_plan(snapshot=snapshot,registry=registry,candidates=candidates,coordination=coordination,
        utilities=utilities,now=now,reserve_soc=config['reserve_soc'],horizon_hours=config['horizon_hours'],
        runtime_manifest=runtime,model_refs=[],forecast_ref=None)
    inputs=dict(snapshot=snap,registry=registry.to_dict(),energy_inputs=None if energy_inputs is None else energy_inputs.to_dict(),
        thermal_inputs=None if thermal_inputs is None else thermal_inputs.to_dict(),coordination=coordination,config=config,now=now.isoformat())
    output=dict(projections=projections,candidate_intents=[item.to_dict() for item in candidates],no_action_intent=no_action.to_dict(),
        candidate_generation=generation,thermal_comfort=_comfort(projections['thermal'],config,now),plan_receipt=plan_receipt,
        action_effects_qualified=False,automatic_actuation=False)
    receipt=dict(schema='earthship-household-model-plan-receipt/v1',inputs=inputs,runtime_manifest=runtime,output=output)
    receipt['receipt_sha256']=identity(receipt)
    if len(canonical(receipt))>MAX_BYTES:raise ValueError('bounded model/plan receipt required')
    return loads(canonical(receipt))


def replay_pipeline(receipt,*,runtime_manifest,thermal_runtime):
    if not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!='earthship-household-model-plan-receipt/v1' or len(canonical(receipt))>MAX_BYTES:
        raise ValueError('closed bounded original model/plan receipt required')
    if identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})!=receipt['receipt_sha256']:
        raise ValueError('sealed original model/plan differs')
    runtime=_runtime_manifest(runtime_manifest)
    if canonical(runtime)!=canonical(receipt['runtime_manifest']):raise ValueError('executing model/plan runtime differs')
    value=receipt['inputs']
    if not isinstance(value,dict) or set(value)!=INPUT_FIELDS:raise ValueError('closed original model/plan inputs required')
    snapshot=_restore(value['snapshot'],HouseholdSnapshot,'snapshot_id')
    registry=_restore(value['registry'],CapabilityRegistry,'registry_id')
    energy=None if value['energy_inputs'] is None else FrozenEnergyInputs(canonical(value['energy_inputs']))
    thermal=None if value['thermal_inputs'] is None else PreparedProjection(canonical(value['thermal_inputs']))
    replayed=seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=energy,thermal_inputs=thermal,
        thermal_runtime=thermal_runtime,coordination=value['coordination'],config=value['config'],now=instant(value['now']),runtime_manifest=runtime)
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived original models or plan differ')
    return replayed
