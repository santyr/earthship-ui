"""Chronological forecast errors under actual behavior, never causal action value."""
from datetime import timedelta
from .codec import canonical,loads,identity
from .evidence import utc
from .control_contracts import instant
from .outcome_origin import PreparedOutcomeOrigin
from .thermal_model import project
from .pipeline import replay_pipeline
from .planning import _runtime_manifest
from thermal_model.temperature_history import STREAMS,POLICY,_validate_sensor_receipt
from weather_temperature_sources import replay_temperature_source

HORIZONS=(1,6,12,24)
MAX_BYTES=4*1024*1024
MAX_PACKET_BYTES=128*1024
FIELDS={'schema','inputs','outcome_runtime_manifest','output','receipt_sha256'}
INPUT_FIELDS={'plan_receipt','origin','outcome_sources','assessed_at'}


def _outcome(packet,*,target,assessed,phase):
    if packet is None:return None
    if not isinstance(packet,dict) or len(canonical(packet))>MAX_PACKET_BYTES:raise ValueError('bounded original endpoint packet required')
    stream,model,sensor_id=STREAMS['air']
    if (packet.get('stream')!=stream or packet.get('sensor_epoch')!=phase or
        packet.get('policy')!=dict(model=model,sensor_id=sensor_id,**POLICY) or
        packet.get('targets')!=[target.isoformat()] or packet.get('assessed_at')!=assessed.isoformat() or
        not isinstance(packet.get('native_rows'),list) or len(packet['native_rows'])>128):
        raise ValueError('original outcome query context differs')
    rows=replay_temperature_source(packet)
    if len(rows)!=1 or rows[0][0]!=target:raise ValueError('original outcome target differs')
    receipt=rows[0][1]
    if receipt is not None:_validate_sensor_receipt(receipt,target,sensor_epoch=phase)
    return receipt


def seal_outcomes(*,plan_receipt,origin,outcome_sources,assessed_at,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime):
    if not isinstance(origin,PreparedOutcomeOrigin):raise ValueError('verified prepared delivered origin required')
    assessed=utc(assessed_at);runtime=_runtime_manifest(outcome_runtime_manifest)
    original_plan=replay_pipeline(plan_receipt,runtime_manifest=plan_runtime_manifest,thermal_runtime=thermal_runtime)
    projection=original_plan['output']['projections']['thermal']
    if projection is None:raise ValueError('original thermal model unavailable')
    expected=project(origin.prepared);source=origin.prepared.to_dict()
    if (canonical(projection['output'])!=canonical(expected['output']) or
        projection['original_capture_sha256']!=expected['original_capture_sha256'] or
        canonical(source['executing_runtime'])!=canonical(thermal_runtime)):
        raise ValueError('delivered forecast differs from household projection')
    issue=instant(source['issue']);published=instant(source['snapshot']['created_at'])
    if assessed<published:raise ValueError('outcome assessment precedes original issue')
    horizon=original_plan['inputs']['config']['horizon_hours'];supported=tuple(h for h in HORIZONS if h<=horizon)
    if not isinstance(outcome_sources,dict) or not set(outcome_sources)<={str(h) for h in supported}:
        raise ValueError('closed bounded endpoint source map required')
    outcome_sources=loads(canonical(outcome_sources))
    phase=source['snapshot']['domains']['thermal']['air_temperature']['evidence']['hardware_epoch']
    pairs={}
    for hours in supported:
        target=issue+timedelta(hours=hours);packet=outcome_sources.get(str(hours))
        pair=dict(horizon_hours=hours,target_at=target.isoformat(),status='not_mature',actual_f=None,
            outcome_receipt=None,source_packet_sha256=None,predictions_f=None,errors_f=None,absolute_errors_f=None,
            comfort=None,source_quality='unavailable')
        if assessed>=target+timedelta(minutes=5):
            observed=_outcome(packet,target=target,assessed=assessed,phase=phase)
            pair['status']='source_unavailable'
            if packet is not None:pair['source_packet_sha256']=identity(packet)
            if observed is not None:
                predicted=projection['output']['trajectory'][hours-1]
                if instant(predicted['at'])!=target:raise ValueError('original prediction target differs')
                actual=float(observed['temperatureF']);predictions=dict(model=predicted['air_f'],persistence=projection['output']['initial']['air_f'])
                cfg=original_plan['inputs']['config']
                pair.update(status='scored',actual_f=actual,outcome_receipt=observed,predictions_f=predictions,
                    errors_f={name:value-actual for name,value in predictions.items()},absolute_errors_f={name:abs(value-actual) for name,value in predictions.items()},
                    comfort=dict(unit='endpoint_degF',minimum_f=cfg['comfort_min_f'],maximum_f=cfg['comfort_max_f'],
                        actual_outside_bounds=not cfg['comfort_min_f']<=actual<=cfg['comfort_max_f']),source_quality='qualified')
        elif packet is not None:raise ValueError('immature endpoint cannot supply outcome truth')
        pairs[str(hours)]=pair
    output=dict(evaluation_scope='retrospective_planner_from_original_delivered_forecast',
        model_identity=dict(artifact_sha256=source['artifact_sha256'],original_runtime_sha256=source['runtime_sha256'],sensor_epoch=phase),
        original_capture_sha256=source['original_capture_sha256'],original_delivery_verified=True,issued_at=issue.isoformat(),
        thermal=pairs,energy=dict(status='unavailable',reason='qualified_overnight_minimum_required'),
        action_feasibility=dict(status='unavailable',reason='source_linked_owner_execution_outcomes_required'),
        deterministic_policy_comparison=dict(status='unavailable',reason='source_linked_policy_baseline_required'),
        counterfactual_uncertainty=dict(status='unavailable',reason='qualified_action_response_model_required'),
        causal_benefit_qualified=False,graduated=False,automatic_actuation=False)
    result=dict(schema='earthship-household-outcome-receipt/v1',inputs=dict(plan_receipt=original_plan,origin=origin.to_dict(),
        outcome_sources=outcome_sources,assessed_at=assessed.isoformat()),outcome_runtime_manifest=runtime,output=output)
    result['receipt_sha256']=identity(result)
    if len(canonical(result))>MAX_BYTES:raise ValueError('bounded original household outcome receipt required')
    return loads(canonical(result))


def replay_outcomes(receipt,*,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime):
    if not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!='earthship-household-outcome-receipt/v1' or len(canonical(receipt))>MAX_BYTES:
        raise ValueError('closed bounded original outcome receipt required')
    if identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})!=receipt['receipt_sha256']:
        raise ValueError('original outcome receipt differs')
    runtime=_runtime_manifest(outcome_runtime_manifest)
    if canonical(runtime)!=canonical(receipt['outcome_runtime_manifest']):raise ValueError('executing outcome runtime differs')
    value=receipt['inputs']
    if not isinstance(value,dict) or set(value)!=INPUT_FIELDS:raise ValueError('closed original outcome inputs required')
    origin=PreparedOutcomeOrigin(canonical(value['origin']))
    replayed=seal_outcomes(plan_receipt=value['plan_receipt'],origin=origin,outcome_sources=value['outcome_sources'],assessed_at=instant(value['assessed_at']),
        plan_runtime_manifest=plan_runtime_manifest,outcome_runtime_manifest=runtime,thermal_runtime=thermal_runtime)
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived original outcome scores differ')
    return replayed
