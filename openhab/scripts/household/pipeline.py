"""Pure model-to-shadow-plan rederivation; numerical output grants no authority."""
from datetime import timedelta
import math
from .codec import canonical,loads,identity
from .evidence import utc
from .snapshot import HouseholdSnapshot
from .capabilities import CapabilityRegistry
from .energy_model import PreparedEnergyInputs,project_energy,bind_energy_inputs
from .thermal_model import PreparedProjection,project as project_thermal
from .intents import build_intent,EFFECT_UNITS
from .control_contracts import instant,ContractRefused
from .planning import seal_plan,_runtime_manifest,MIN_RESERVE_SOC

# Native thermal inputs and original weather sources also appear in the
# nested plan receipt. Bound the complete private envelope independently of
# the smaller source, nested-plan and public observation limits.
MAX_BYTES=2*1024*1024
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
        if not isinstance(energy_inputs,PreparedEnergyInputs):raise ValueError('snapshot-bound prepared energy context required')
        origin=energy_inputs.to_dict();row=snap['domains']['energy']['battery_soc'];ref=row['evidence']
        if (origin['snapshot_id']!=snapshot.snapshot_id or instant(origin['as_of'])!=instant(snap['as_of']) or
            instant(origin['available_at'])!=instant(snap['created_at']) or instant(origin['available_at'])>now or
            origin['battery_evidence_sha256']!=(None if ref is None else ref['digest'])):
            raise ValueError('energy origin differs from shared snapshot')
        configured=snap.get('schema') in ('earthship-household-snapshot/v5','earthship-household-snapshot/v6')
        if configured or origin['schema'] in ('earthship-household-prepared-energy/v2','earthship-household-prepared-energy/v3'):
            if canonical(bind_energy_inputs(energy_inputs.numerical,snapshot=snapshot,daily_source=origin.get('daily_source')).to_dict())!=canonical(origin):raise ValueError('original energy configuration binding differs')
        reference=energy_inputs.numerical.to_dict()['inputs']['soc_pct']
        if reference is not None and reference!=snap['domains']['energy']['battery_soc']['value']:
            raise ValueError('energy SoC reference differs from shared snapshot')
        energy=project_energy(energy_inputs.numerical)
        energy.pop('projection_sha256')
        energy['collection_binding']={key:origin[key] for key in ('snapshot_id','as_of','available_at','battery_evidence_sha256')}
        if configured:energy['collection_binding']['configuration_binding']=origin['configuration_binding']
        if 'daily_source' in origin:
            energy['collection_binding']['daily_source_sha256']=identity(origin['daily_source'])
            energy['collection_binding']['daily_prediction_day']=origin['daily_source']['prediction_day']
            energy['collection_binding']['daily_source_basis']='post_issue_retained_inputs_matched_to_published_receipt'
        energy['projection_sha256']=identity(energy)
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
    from .model_snapshot import ModelSnapshot,verify_model_binding,verify_source_runtime
    expanded=isinstance(snapshot,ModelSnapshot)
    if snap.get('schema') in ('earthship-household-snapshot/v3','earthship-household-snapshot/v4','earthship-household-snapshot/v5','earthship-household-snapshot/v6') and not expanded:raise ValueError('verified model snapshot required')
    if expanded:
        verify_source_runtime(snapshot,runtime)
        verify_model_binding(snapshot,thermal_inputs)
    coordination=loads(canonical(coordination))
    projections=_projections(snapshot,energy_inputs,thermal_inputs,thermal_runtime,now,config['horizon_hours'])
    energy_bound=snap.get('schema') in ('earthship-household-snapshot/v5','earthship-household-snapshot/v6')
    weather_bound=snap.get('schema') in ('earthship-household-snapshot/v4','earthship-household-snapshot/v5','earthship-household-snapshot/v6')
    measured_bound=snap.get('schema')=='earthship-household-snapshot/v6'
    if weather_bound:
        from .weather_snapshot import WeatherSnapshot
        from .weather_context import project_weather
        if not isinstance(snapshot,WeatherSnapshot) or thermal_inputs is None or canonical(snapshot.weather.prepared.to_dict())!=canonical(thermal_inputs.to_dict()):raise ValueError('original weather model binding differs')
        projections['weather']=project_weather(snapshot.weather)
    if energy_bound:
        from .energy_source_snapshot import EnergySourceSnapshot
        from .energy_configuration import project_energy_configuration
        if not isinstance(snapshot,EnergySourceSnapshot):raise ValueError('verified energy source snapshot required')
        projections['energy_configuration']=project_energy_configuration(snapshot.energy_configuration,as_of=instant(snap['as_of']))
    if measured_bound:
        from .measured_weather_snapshot import MeasuredWeatherSnapshot
        from .measured_weather import project_measured_weather
        if not isinstance(snapshot,MeasuredWeatherSnapshot):raise ValueError('verified measured weather snapshot required')
        projections['measured_weather']=project_measured_weather(snapshot.measured_weather,as_of=instant(snap['as_of']))
    candidates,utilities,no_action,generation=_candidates(snapshot,projections,config,now)
    plan_receipt=seal_plan(snapshot=snapshot,registry=registry,candidates=candidates,coordination=coordination,
        utilities=utilities,now=now,reserve_soc=config['reserve_soc'],horizon_hours=config['horizon_hours'],
        runtime_manifest=runtime,model_refs=[],forecast_ref=None)
    inputs=dict(snapshot=snap,registry=registry.to_dict(),energy_inputs=None if energy_inputs is None else energy_inputs.to_dict(),
        thermal_inputs=None if thermal_inputs is None else thermal_inputs.to_dict(),coordination=coordination,config=config,now=now.isoformat())
    output=dict(projections=projections,candidate_intents=[item.to_dict() for item in candidates],no_action_intent=no_action.to_dict(),
        candidate_generation=generation,thermal_comfort=_comfort(projections['thermal'],config,now),plan_receipt=plan_receipt,
        action_effects_qualified=False,automatic_actuation=False)
    if expanded:
        from .model_snapshot import snapshot_context
        inputs['source_contexts']={snapshot.snapshot_id:snapshot_context(snapshot)}
    receipt=dict(schema='earthship-household-model-plan-receipt/v'+str(5 if measured_bound else 4 if energy_bound else 3 if weather_bound else 2 if expanded else 1),inputs=inputs,runtime_manifest=runtime,output=output)
    receipt['receipt_sha256']=identity(receipt)
    if len(canonical(receipt))>MAX_BYTES:raise ValueError('bounded model/plan receipt required')
    return loads(canonical(receipt))


def replay_pipeline(receipt,*,runtime_manifest,thermal_runtime):
    if not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema'] not in ('earthship-household-model-plan-receipt/v1','earthship-household-model-plan-receipt/v2','earthship-household-model-plan-receipt/v3','earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5') or len(canonical(receipt))>MAX_BYTES:
        raise ValueError('closed bounded original model/plan receipt required')
    if identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})!=receipt['receipt_sha256']:
        raise ValueError('sealed original model/plan differs')
    runtime=_runtime_manifest(runtime_manifest)
    if canonical(runtime)!=canonical(receipt['runtime_manifest']):raise ValueError('executing model/plan runtime differs')
    value=receipt['inputs']
    expanded=receipt['schema'].endswith(('/v2','/v3','/v4','/v5'))
    if not isinstance(value,dict) or set(value)!=(INPUT_FIELDS|{'source_contexts'} if expanded else INPUT_FIELDS):raise ValueError('closed original model/plan inputs required')
    from .model_snapshot import restore_snapshot
    contexts=value.get('source_contexts')
    if expanded and (not isinstance(contexts,dict) or set(contexts)!={value['snapshot']['snapshot_id']}):raise ValueError('exact original source context required')
    snapshot=restore_snapshot(value['snapshot'],contexts)
    registry=_restore(value['registry'],CapabilityRegistry,'registry_id')
    energy=None if value['energy_inputs'] is None else PreparedEnergyInputs(canonical(value['energy_inputs']))
    thermal=None if value['thermal_inputs'] is None else PreparedProjection(canonical(value['thermal_inputs']))
    replayed=seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=energy,thermal_inputs=thermal,
        thermal_runtime=thermal_runtime,coordination=value['coordination'],config=value['config'],now=instant(value['now']),runtime_manifest=runtime)
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived original models or plan differ')
    return replayed
