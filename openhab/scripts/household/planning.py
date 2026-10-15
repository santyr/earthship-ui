"""Pure exhaustive shadow coordination under declared frozen bounds.

Coordination packets are planning inputs, not owner acknowledgements or proof of
physical safety. Missing packets block proposals. No request or transport exists.
"""
from datetime import timedelta
from hashlib import sha256
import math
import re
from .codec import canonical,loads,identity
from .evidence import utc,digest
from .snapshot import HouseholdSnapshot
from .capabilities import CapabilityRegistry
from .intents import HouseholdIntent,parse_intent
from .control_contracts import instant,ContractRefused

# Native geometry/source contexts and bracketed owner originals share this
# private envelope. Individual source and public-output bounds stay separate.
MAX_RECEIPT_BYTES=1024*1024
MAX_CANDIDATES=8
MIN_RESERVE_SOC=10.  # Existing full-bank emergency reserve; input may tighten it.
CAPABILITIES={'RUN_GREYWATER_CYCLE':'greywater-request-v1','RUN_FEEDER_CYCLE':'feeder-request-v1',
              'SET_NIGHT_LOAD_OVERRIDE':'night-load-owner-v1','SET_NIGHT_LOAD_DEVICE':'night-load-owner-v1'}
GATES={'owner_available':'capability_unavailable','owner_idle':'busy','cooldown_ready':'cooldown','curfew_allowed':'after_dark',
       'operator_unlocked':'hard_constraint','manual_override_clear':'hard_constraint'}
FACT_FIELDS={'schema','kind','owner','value','snapshotId','receivedAt','validUntil','scope','horizonHours'}
SCOPE='declared_shadow_bounds'


def _fact(entry,*,kind,owner,snapshot_id,now,horizon_hours):
    if entry is None:return None,'source_unavailable'
    try:
        if not isinstance(entry,dict) or set(entry)!={'raw','sha256'}:raise ValueError('closed original fact reference required')
        raw=entry['raw']
        if not isinstance(raw,str) or not 1<=len(raw.encode())<=2048 or sha256(raw.encode()).hexdigest()!=entry['sha256']:
            raise ValueError('original coordination bytes differ')
        value=loads(raw)
        if (set(value)!=FACT_FIELDS or value['schema']!='earthship-shadow-coordination-fact/v1' or value['kind']!=kind or
            value['owner']!=owner or value['snapshotId']!=snapshot_id or value['scope']!=SCOPE or type(value['horizonHours']) is not int or value['horizonHours']!=horizon_hours):
            raise ValueError('original coordination binding differs')
        received,until=map(instant,(value['receivedAt'],value['validUntil']))
        if received>now:return None,'source_unavailable'
        if not timedelta(0)<until-received<=timedelta(seconds=120) or now>=until or now-received>timedelta(seconds=120):
            return None,'source_stale'
        number=value['value']
        if kind=='baseline_soc_floor':
            if type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=100:raise ValueError('bounded declared floor required')
        elif type(number) is not bool:raise ValueError('explicit declared coordination state required')
        return number,None
    except (TypeError,ValueError,OverflowError,RecursionError,UnicodeError):return None,'source_unavailable'


def _source_checks(document,snapshot,now):
    rows={role:row for domain in snapshot['domains'].values() for role,row in domain.items()}
    required=['battery_soc']
    checks=[]
    for role in required:
        row=rows.get(role);ref=None if row is None else row['evidence']
        if (row is None or row['value'] is None or row['reason'] is not None or ref is None or ref['quality']!='qualified' or
            ref['digest'] not in document['evidenceRefs']):
            checks.append(dict(rule='source_freshness',status='unknown',reason='source_unavailable'));continue
        observed=instant(ref['observed_at'] or ref['received_at'])
        stale=(instant(ref['available_at'])>now or instant(ref['assessed_at'])>now or now>=instant(ref['valid_until']) or
               now-observed>timedelta(seconds=snapshot['temporal_policy']['max_age_seconds'][role]))
        checks.append(dict(rule='source_freshness',status='unknown' if stale else 'pass',reason='source_stale' if stale else None))
    return checks


def _candidate_checks(item,*,snapshot,registry,coordination,now,reserve_soc,baseline,horizon_hours):
    document=item.to_dict();checks=[];owner=None
    try:parse_intent(item.content.decode(),snapshot=snapshot,now=now)
    except ContractRefused as error:
        return None,[dict(rule='intent_identity_and_freshness',status='rejected',reason=error.reason_code)]
    checks.append(dict(rule='intent_identity_and_freshness',status='pass',reason=None))
    checks.extend(_source_checks(document,snapshot.to_dict(),now))
    capability=registry['capabilities'].get(CAPABILITIES.get(document['type']))
    if capability is None:
        checks.append(dict(rule='registered_capability',status='unknown',reason='capability_unavailable'))
    else:
        checks.append(dict(rule='registered_capability',status='pass',reason=None))
        owner=capability['ownerRule']
        for gate,reason in GATES.items():
            value,invalid=_fact(coordination['facts'].get(owner,{}).get(gate),kind=gate,owner=owner,snapshot_id=snapshot.snapshot_id,now=now,horizon_hours=horizon_hours)
            checks.append(dict(rule=gate,status='unknown' if invalid else 'pass' if value else 'rejected',reason=invalid or (None if value else reason)))
    delta=document['predictedEffects']['socPct']
    if baseline is None or delta is None:
        checks.append(dict(rule='battery_reserve',status='unknown',reason='unqualified_effect'))
    else:
        floor=baseline+delta
        checks.append(dict(rule='battery_reserve',status='pass' if reserve_soc<=floor<=100 else 'rejected',reason=None if reserve_soc<=floor<=100 else 'low_soc' if floor<reserve_soc else 'hard_constraint'))
    return owner,checks


def plan(*,snapshot,registry,candidates,coordination,utilities,now,reserve_soc,horizon_hours):
    """Maximize declared utility only after every hard bound has passed."""
    if not isinstance(snapshot,HouseholdSnapshot) or not isinstance(registry,CapabilityRegistry):raise ValueError('immutable source context required')
    if type(horizon_hours) is not int or horizon_hours not in (6,12,24):raise ValueError('explicit supported horizon required')
    now=utc(now);snap=snapshot.to_dict()
    if instant(snap['as_of'])>now or instant(snap['created_at'])>now:raise ValueError('snapshot unavailable at decision')
    if not isinstance(candidates,(tuple,list)) or len(candidates)>MAX_CANDIDATES or any(not isinstance(item,HouseholdIntent) for item in candidates):
        raise ValueError('bounded typed candidates required')
    if type(reserve_soc) not in (int,float) or not math.isfinite(reserve_soc) or not MIN_RESERVE_SOC<=reserve_soc<=100:raise ValueError('bounded explicit reserve required')
    if isinstance(coordination,dict) and coordination.get('schema') in ('earthship-shadow-coordination/v2','earthship-shadow-coordination/v3'):
        from .owner_sources import validate_coordination
        coordination=validate_coordination(coordination,snapshot_id=snapshot.snapshot_id,registry=registry,
            horizon_hours=horizon_hours,as_of=instant(snap['as_of']))
    if not isinstance(coordination,dict) or set(coordination)!={'schema','snapshotId','baseline_soc_floor','facts','horizonHours'} or coordination['schema']!='earthship-shadow-coordination/v1' or coordination['snapshotId']!=snapshot.snapshot_id or type(coordination['horizonHours']) is not int or coordination['horizonHours']!=horizon_hours:
        raise ValueError('closed frozen coordination context required')
    registry=registry.to_dict()
    coordination=loads(canonical(coordination))
    if len(canonical(coordination))>65536 or not isinstance(coordination['facts'],dict) or len(coordination['facts'])>8:raise ValueError('bounded owner facts required')
    for owner,facts in coordination['facts'].items():
        if not isinstance(owner,str) or not 1<=len(owner)<=128 or not isinstance(facts,dict) or not set(facts)<=set(GATES):raise ValueError('closed owner fact map required')
    items=sorted(candidates,key=lambda item:item.intent_id);ids=[item.intent_id for item in items]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate intent identity refused')
    if not isinstance(utilities,dict) or set(utilities)!=set(ids) or any(type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e6 for value in utilities.values()):
        raise ValueError('bounded declared objective required')
    utilities=dict(utilities)
    baseline,baseline_reason=_fact(coordination['baseline_soc_floor'],kind='baseline_soc_floor',owner=None,snapshot_id=snapshot.snapshot_id,now=now,horizon_hours=horizon_hours)
    checks={};owners={};eligible=[]
    for item in items:
        owner,results=_candidate_checks(item,snapshot=snapshot,registry=registry,coordination=coordination,now=now,reserve_soc=reserve_soc,baseline=baseline,horizon_hours=horizon_hours)
        checks[item.intent_id]=results;owners[item.intent_id]=owner
        if all(row['status']=='pass' for row in results):eligible.append(item)
    def feasible(selected):
        selected_owners=[owners[item.intent_id] for item in selected]
        return len(set(selected_owners))==len(selected_owners) and (not selected or reserve_soc<=baseline+math.fsum(item.to_dict()['predictedEffects']['socPct'] for item in selected)<=100)
    def score(selected):return math.fsum(utilities[item.intent_id] for item in selected)
    best=[];best_score=0.
    for mask in range(1,1<<len(eligible)):
        selected=[item for index,item in enumerate(eligible) if mask&(1<<index)]
        if not feasible(selected):continue
        value=score(selected);keys=[item.intent_id for item in selected]
        if value>best_score or value==best_score and tuple(keys)<tuple(item.intent_id for item in best):best,best_score=selected,value
    selected_ids=[item.intent_id for item in best];selected_owners={owners[key] for key in selected_ids}
    decisions=[]
    for item in items:
        key=item.intent_id;failed=[row for row in checks[key] if row['status']!='pass']
        if failed:
            failure=next((row for row in failed if row['status']=='rejected'),failed[0]);status='rejected' if failure['status']=='rejected' else 'unknown';reason=failure['reason']
        elif key in selected_ids:status,reason='accepted',None
        elif owners[key] in selected_owners:status,reason='superseded','intent_conflict'
        elif not feasible(best+[item]):status,reason='deferred','hard_constraint'
        else:status,reason='deferred','no_optional_action'
        decisions.append(dict(intent_id=key,status=status,reason=reason,hard_checks=checks[key]))
    greedy=[]
    for item in sorted(eligible,key=lambda item:(-utilities[item.intent_id],item.intent_id)):
        if utilities[item.intent_id]>0 and feasible(greedy+[item]):greedy.append(item)
    status='selected_shadow_candidates' if best else 'input_incomplete' if baseline is None else 'baseline_outside_reserve' if baseline<reserve_soc else 'input_incomplete' if any(row['status']=='unknown' for row in decisions) else 'no_optional_action_preferred'
    result=dict(status=status,horizon_hours=horizon_hours,planner_version='bounded_exhaustive_v1',schema='earthship-household-shadow-plan/v1',scope=SCOPE,as_of=now.isoformat(),snapshot_id=snapshot.snapshot_id,
        registry_sha256=identity(registry),coordination_sha256=identity(coordination),selected_intent_ids=selected_ids,candidate_decisions=decisions,
        constraint_catalog=[dict(rule=name,classification='HARD_CONSTRAINT') for name in ('intent_identity_and_freshness','source_freshness','registered_capability',*GATES,'battery_reserve','owner_exclusivity','cumulative_battery_reserve')],
        objective=dict(unit='normalized_declared_preference_points',components={key:utilities[key] for key in sorted(ids)},total=best_score),
        reserve_checks=dict(reserve_soc=reserve_soc,minimum_reserve_soc=MIN_RESERVE_SOC,baseline_floor_soc=baseline,baseline_reason=baseline_reason,selected_floor_soc=None if baseline is None else baseline+math.fsum(item.to_dict()['predictedEffects']['socPct'] for item in best)),
        baseline_scores=dict(no_optional_action=0.,greedy=score(greedy),actual_household=None,current_owner_policy=None),
        baseline_reasons=dict(actual_household='source_unavailable',current_owner_policy='source_unavailable'),
        solver=dict(name='bounded_exhaustive_v1',max_candidates=MAX_CANDIDATES,subsets_examined=1<<len(eligible)),
        owner_live_gate_still_required=True,action_effects_qualified=False,automatic_actuation=False)
    result['plan_sha256']=identity(result)
    if len(canonical(result))>65536:raise ValueError('bounded shadow plan required')
    return result


RECEIPT_FIELDS={'schema','inputs','runtime_manifest','model_refs','forecast_ref','plan','receipt_sha256'}
INPUT_FIELDS={'snapshot','registry','candidates','coordination','utilities','now','reserve_soc','horizon_hours'}


def _runtime_manifest(value):
    if not isinstance(value,dict) or not 1<=len(value)<=64:raise ValueError('bounded explicit runtime manifest required')
    for name,sha in value.items():
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_./-]{1,192}',name) or name.startswith('/') or '..' in name:
            raise ValueError('bounded runtime source name required')
        digest(sha)
    return dict(value)


def _references(models,forecast,now,horizon):
    if not isinstance(models,list) or len(models)>8:raise ValueError('bounded model identities required')
    for model in models:
        if not isinstance(model,dict) or set(model)!={'artifact_sha256','runtime_sha256','projection_sha256','available_at','valid_until','confidence'}:
            raise ValueError('closed model reference required')
        for key in ('artifact_sha256','runtime_sha256','projection_sha256'):digest(model[key])
        if model['confidence'] not in ('unavailable','low','medium','high') or not instant(model['available_at'])<=now<instant(model['valid_until']):raise ValueError('model unavailable at decision')
    if forecast is not None:
        if not isinstance(forecast,dict) or set(forecast)!={'original_sha256','issued_at','available_at','horizon_hours'}:raise ValueError('closed original forecast reference required')
        digest(forecast['original_sha256'])
        if type(forecast['horizon_hours']) is not int or forecast['horizon_hours']!=horizon or not instant(forecast['issued_at'])<=instant(forecast['available_at'])<=now:
            raise ValueError('forecast unavailable at decision')


def seal_plan(*,runtime_manifest,model_refs,forecast_ref,**arguments):
    runtime=_runtime_manifest(runtime_manifest);now=utc(arguments['now'])
    model_refs=loads(canonical({'models':model_refs}))['models']
    forecast_ref=loads(canonical({'forecast':forecast_ref}))['forecast']
    _references(model_refs,forecast_ref,now,arguments['horizon_hours'])
    arguments={**arguments,'candidates':tuple(arguments['candidates']),'coordination':loads(canonical(arguments['coordination'])),'utilities':dict(arguments['utilities'])}
    output=plan(**arguments)
    inputs=dict(snapshot=arguments['snapshot'].to_dict(),registry=arguments['registry'].to_dict(),
        candidates=[dict(intent=item.to_dict(),validation_snapshot=item.snapshot.to_dict(),validated_at=item.validated_at.isoformat())
                    for item in sorted(arguments['candidates'],key=lambda item:item.intent_id)],
        coordination=arguments['coordination'],utilities=arguments['utilities'],now=now.isoformat(),reserve_soc=arguments['reserve_soc'],horizon_hours=arguments['horizon_hours'])
    from .model_snapshot import ModelSnapshot,verify_source_runtime,snapshot_context
    for item in (arguments['snapshot'],*(candidate.snapshot for candidate in arguments['candidates'])):
        if isinstance(item,ModelSnapshot):verify_source_runtime(item,runtime)
        elif item.to_dict().get('schema') in ('earthship-household-snapshot/v3','earthship-household-snapshot/v4','earthship-household-snapshot/v5','earthship-household-snapshot/v6'):raise ValueError('verified model snapshot required')
    contexts={item.snapshot_id:snapshot_context(item) for item in (arguments['snapshot'],*(candidate.snapshot for candidate in arguments['candidates'])) if isinstance(item,ModelSnapshot)}
    weather_bound=any(item.to_dict().get('schema') in ('earthship-household-snapshot/v4','earthship-household-snapshot/v5','earthship-household-snapshot/v6') for item in (arguments['snapshot'],*(candidate.snapshot for candidate in arguments['candidates'])))
    energy_bound=any(item.to_dict().get('schema') in ('earthship-household-snapshot/v5','earthship-household-snapshot/v6') for item in (arguments['snapshot'],*(candidate.snapshot for candidate in arguments['candidates'])))
    measured_bound=any(item.to_dict().get('schema')=='earthship-household-snapshot/v6' for item in (arguments['snapshot'],*(candidate.snapshot for candidate in arguments['candidates'])))
    version=5 if measured_bound else 4 if energy_bound else 3 if weather_bound else 2 if contexts else 1
    if weather_bound:
        inputs['validation_snapshots']={item.snapshot.snapshot_id:item.snapshot.to_dict() for item in arguments['candidates'] if item.snapshot.snapshot_id!=arguments['snapshot'].snapshot_id}
        inputs['candidates']=[dict(intent=item.to_dict(),validation_snapshot_id=item.snapshot.snapshot_id,validated_at=item.validated_at.isoformat()) for item in sorted(arguments['candidates'],key=lambda item:item.intent_id)]
    if contexts:inputs['source_contexts']=contexts
    receipt=loads(canonical(dict(schema='earthship-household-shadow-plan-receipt/v'+str(version),inputs=inputs,runtime_manifest=runtime,
        model_refs=model_refs,forecast_ref=forecast_ref,plan=output)))
    receipt['receipt_sha256']=identity(receipt)
    if len(canonical(receipt))>MAX_RECEIPT_BYTES:raise ValueError('bounded sealed plan receipt required')
    return receipt


def replay_plan(receipt,*,runtime_manifest):
    if not isinstance(receipt,dict) or set(receipt)!=RECEIPT_FIELDS or receipt['schema'] not in ('earthship-household-shadow-plan-receipt/v1','earthship-household-shadow-plan-receipt/v2','earthship-household-shadow-plan-receipt/v3','earthship-household-shadow-plan-receipt/v4','earthship-household-shadow-plan-receipt/v5') or len(canonical(receipt))>MAX_RECEIPT_BYTES:
        raise ValueError('closed bounded original plan receipt required')
    if identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})!=receipt['receipt_sha256']:raise ValueError('sealed original plan differs')
    runtime=_runtime_manifest(runtime_manifest)
    if canonical(runtime)!=canonical(receipt['runtime_manifest']):raise ValueError('executing planner runtime differs')
    value=receipt['inputs']
    expanded=receipt['schema'].endswith(('/v2','/v3','/v4','/v5'));weather_bound=receipt['schema'].endswith(('/v3','/v4','/v5'))
    fields=INPUT_FIELDS|({'source_contexts'} if expanded else set())|({'validation_snapshots'} if weather_bound else set())
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('closed original plan inputs required')
    from .model_snapshot import restore_snapshot
    contexts=value.get('source_contexts')
    if expanded and (not isinstance(contexts,dict) or not 1<=len(contexts)<=MAX_CANDIDATES+1):raise ValueError('bounded original source contexts required')
    snapshot=restore_snapshot(value['snapshot'],contexts)
    registry_document=value['registry']
    registry=CapabilityRegistry(canonical({key:item for key,item in registry_document.items() if key!='registry_id'}))
    if registry.registry_id!=registry_document['registry_id']:raise ValueError('original registry identity differs')
    now=instant(value['now'])
    if not isinstance(value['candidates'],list) or len(value['candidates'])>MAX_CANDIDATES:raise ValueError('bounded original candidate set required')
    candidates=[]
    documents=value.get('validation_snapshots',{})
    if weather_bound and (not isinstance(documents,dict) or len(documents)>MAX_CANDIDATES):raise ValueError('bounded original validation snapshots required')
    for item in value['candidates']:
        candidate_fields={'intent','validated_at','validation_snapshot_id' if weather_bound else 'validation_snapshot'}
        if not isinstance(item,dict) or set(item)!=candidate_fields:
            raise ValueError('closed original candidate validation context required')
        original=(value['snapshot'] if item['validation_snapshot_id']==snapshot.snapshot_id else documents.get(item['validation_snapshot_id'])) if weather_bound else item['validation_snapshot']
        if not isinstance(original,dict) or 'snapshot_id' not in original:
            raise ValueError('original candidate snapshot required')
        validation_snapshot=restore_snapshot(original,contexts)
        candidates.append(parse_intent(canonical(item['intent']).decode(),snapshot=validation_snapshot,now=instant(item['validated_at'])))
    replayed=seal_plan(snapshot=snapshot,registry=registry,candidates=candidates,coordination=value['coordination'],utilities=value['utilities'],
        now=now,reserve_soc=value['reserve_soc'],horizon_hours=value['horizon_hours'],runtime_manifest=runtime,model_refs=receipt['model_refs'],forecast_ref=receipt['forecast_ref'])
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived original plan differs')
    return replayed
