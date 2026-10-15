"""Pure declared resource vectors and drift; never measured causal effects.

Prefixes describe an explicit sequence of optional endpoint effects. They cannot
bound excursions within an action or supply a qualified household baseline.
"""
import math
import re
from .codec import canonical,loads,identity
from .evidence import utc
from .control_contracts import instant
from .intents import EFFECT_UNITS
from .planning import replay_plan,_runtime_manifest,MAX_CANDIDATES,MAX_RECEIPT_BYTES

MAX_BYTES=1024*1024
MAX_ORDERS=16
UNITS={**EFFECT_UNITS,'comfortDegreeHours':'degF_hour','curtailmentKwh':'kWh'}
FIELDS={'schema','inputs','analysis_runtime_manifest','output','receipt_sha256'}
INPUT_FIELDS={'plan_receipt','scales','orders','assessed_at'}


def _scales(value):
    if not isinstance(value,dict) or set(value)!=set(UNITS):raise ValueError('closed explicit resource scales required')
    for scale in value.values():
        if type(scale) not in (int,float) or not math.isfinite(scale) or not 1e-9<=scale<=1e9:
            raise ValueError('bounded positive resource scales required')
    return dict(value)


def _orders(value,ids):
    if not isinstance(value,list) or len(value)>MAX_ORDERS:raise ValueError('bounded explicit order experiments required')
    names=set();result=[]
    for row in value:
        if not isinstance(row,dict) or set(row)!={'name','intent_ids'}:raise ValueError('closed explicit order required')
        name=row['name'];order=row['intent_ids']
        if not isinstance(name,str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}',name) or name=='selected' or name in names:
            raise ValueError('unique named order required')
        if not isinstance(order,list) or len(order)>MAX_CANDIDATES or any(not isinstance(key,str) or key not in ids for key in order) or len(order)!=len(set(order)):
            raise ValueError('unique original candidate order required')
        names.add(name);result.append(dict(name=name,intent_ids=list(order)))
    return result


def _vector(intent,scales):
    effects=intent['predictedEffects']
    return dict(intent_id=intent['intentId'],intent_type=intent['type'],confidence=intent['confidence'],
        effects_basis='declared_unqualified',dimensions={name:dict(value=effects.get(name),unit=unit,
            scale=scales[name],normalized=None if effects.get(name) is None else effects[name]/scales[name],
            reason='effect_unavailable' if effects.get(name) is None else None) for name,unit in UNITS.items()})


def _order(row,vectors,decisions,scales):
    order=row['intent_ids'];prefixes=[];metrics={}
    for name,unit in UNITS.items():
        known=[];unknown=[];points=[0.]
        for index,key in enumerate(order):
            value=vectors[key]['dimensions'][name]['value']
            if value is None:unknown.append(key)
            else:known.append(value)
            subtotal=math.fsum(known);net=None if unknown else subtotal
            if len(prefixes)<=index:prefixes.append(dict(intent_id=key,dimensions={}))
            prefixes[index]['dimensions'][name]=dict(value=net,known_contribution=subtotal,
                normalized=None if net is None else net/scales[name],unknown_intent_ids=list(unknown))
            if net is not None:points.append(net)
        subtotal=math.fsum(known);complete=not unknown
        metrics[name]=dict(unit=unit,scale=scales[name],fully_known=complete,
            net_change=subtotal if complete else None,normalized_net=subtotal/scales[name] if complete else None,
            known_contribution=subtotal,unknown_intent_ids=list(unknown),
            min_prefix=min(points) if complete else None,max_prefix=max(points) if complete else None,
            normalized_min_prefix=min(points)/scales[name] if complete else None,
            normalized_max_prefix=max(points)/scales[name] if complete else None,
            gross_movement=math.fsum(abs(value) for value in known) if complete else None,
            known_gross_movement=math.fsum(abs(value) for value in known))
    return dict(name=row['name'],intent_ids=list(order),prefixes=prefixes,dimensions=metrics,
        included_decisions=[decisions[key] for key in order],
        all_declared_hard_checks_pass=all(all(check['status']=='pass' for check in decisions[key]['hard_checks']) for key in order),
        physical_feasibility_qualified=False,within_action_excursions_qualified=False)


def seal_resources(*,plan_receipt,scales,orders,assessed_at,plan_runtime_manifest,analysis_runtime_manifest):
    """Rederive an original plan, then annotate declared effects without I/O."""
    if not isinstance(plan_receipt,dict) or len(canonical(plan_receipt))>MAX_RECEIPT_BYTES:raise ValueError('bounded original plan required')
    plan=replay_plan(plan_receipt,runtime_manifest=plan_runtime_manifest)
    assessed=utc(assessed_at)
    if assessed<instant(plan['inputs']['now']):raise ValueError('analysis precedes original decision')
    scales=_scales(scales);runtime=_runtime_manifest(analysis_runtime_manifest)
    candidates=[row['intent'] for row in plan['inputs']['candidates']]
    vectors={row['intentId']:_vector(row,scales) for row in candidates}
    orders=_orders(orders,set(vectors));decisions={row['intent_id']:row for row in plan['plan']['candidate_decisions']}
    selected=dict(name='selected',intent_ids=plan['plan']['selected_intent_ids'])
    output=dict(schema='earthship-household-resource-drift/v1',basis='additional_declared_optional_effects',
        snapshot_id=plan['inputs']['snapshot']['snapshot_id'],original_plan_sha256=plan['receipt_sha256'],
        scale_basis='declared_normalization_preferences',candidate_vectors=[vectors[key] for key in sorted(vectors)],
        selected_order=_order(selected,vectors,decisions,scales),
        order_experiments=[_order(row,vectors,decisions,scales) for row in orders],
        household_baseline_qualified=False,action_effects_qualified=False,causal_benefit_qualified=False,
        automatic_actuation=False,graduated=False)
    result=dict(schema='earthship-household-resource-receipt/v1',inputs=dict(plan_receipt=plan,scales=scales,
        orders=orders,assessed_at=assessed.isoformat()),analysis_runtime_manifest=runtime,output=output)
    result['receipt_sha256']=identity(result)
    if len(canonical(result))>MAX_BYTES:raise ValueError('bounded resource analysis required')
    return loads(canonical(result))


def replay_resources(receipt,*,plan_runtime_manifest,analysis_runtime_manifest):
    if not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!='earthship-household-resource-receipt/v1' or len(canonical(receipt))>MAX_BYTES:
        raise ValueError('closed bounded original resource receipt required')
    if identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})!=receipt['receipt_sha256']:
        raise ValueError('original resource receipt differs')
    runtime=_runtime_manifest(analysis_runtime_manifest)
    if canonical(runtime)!=canonical(receipt['analysis_runtime_manifest']):raise ValueError('executing resource runtime differs')
    value=receipt['inputs']
    if not isinstance(value,dict) or set(value)!=INPUT_FIELDS:raise ValueError('closed original resource inputs required')
    replayed=seal_resources(plan_receipt=value['plan_receipt'],scales=value['scales'],orders=value['orders'],
        assessed_at=instant(value['assessed_at']),plan_runtime_manifest=plan_runtime_manifest,analysis_runtime_manifest=runtime)
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived resource analysis differs')
    return replayed
