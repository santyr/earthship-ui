"""Chronological conditional battery baselines; no causal or release authority."""
from datetime import timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
import math
import re
from .codec import canonical,loads,identity
from .evidence import utc,digest,epoch
from .control_contracts import instant
from .pipeline import replay_pipeline
from .planning import _runtime_manifest
from earthship_energy.bms_evidence import parse_evidence

HORIZONS=(1,6,12,24)
SOURCE_FIELDS={'schema','source_identity','item_id','target_at','query_start','query_end','requested_at','received_at','rows','source_sha256'}
SCORE_FIELDS={'schema','inputs','outcome_runtime_manifest','output','receipt_sha256'}
INPUT_FIELDS={'plan_receipt_sha256','plan_document_sha256','endpoint_sources','assessed_at'}
MAX_SCORE_BYTES=65536
COHORT_FIELDS={'model_rule','model_source_sha256','bank_epoch','nominal_bank_kwh','source_epoch'}


def build_endpoint_source(*,rows,target_at,requested_at,received_at,item_id):
    target,requested,received=map(utc,(target_at,requested_at,received_at))
    if not target+timedelta(minutes=5)<=requested<=received or received-requested>timedelta(seconds=15):
        raise ValueError('mature bounded endpoint collection required')
    if type(item_id) is not int or not 0<=item_id<=2147483647:raise ValueError('unique bounded original Item mapping required')
    if not isinstance(rows,(list,tuple)) or len(rows)>2:raise ValueError('bounded latest original rows required')
    start=target-timedelta(seconds=120);originals=[];previous=None
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('original endpoint row required')
        at,raw=row;at=utc(at)
        if (not start<=at<=target or previous is not None and at>=previous or
            raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096)):
            raise ValueError('ambiguous or out-of-window endpoint originals')
        previous=at;originals.append([at.isoformat(),raw])
    body=dict(schema='earthship-household-battery-endpoint-source/v1',source_identity='BMS_SOC_Evidence_JSON',
        item_id=item_id,target_at=target.isoformat(),query_start=start.isoformat(),query_end=target.isoformat(),
        requested_at=requested.isoformat(),received_at=received.isoformat(),rows=originals)
    body['source_sha256']=identity(body);return loads(canonical(body))


def endpoint_value(source,*,target,assessed,source_epoch):
    if source is None:return None,'endpoint_source_required'
    if not isinstance(source,dict) or set(source)!=SOURCE_FIELDS or source['source_identity']!='BMS_SOC_Evidence_JSON':
        raise ValueError('closed fixed endpoint source required')
    expected=build_endpoint_source(rows=[(instant(at),raw) for at,raw in source['rows']],target_at=instant(source['target_at']),
        requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=source['item_id'])
    if canonical(expected)!=canonical(source) or instant(source['target_at'])!=target or instant(source['received_at'])>assessed:
        raise ValueError('original endpoint identity or clocks differ')
    if not source['rows']:return None,'endpoint_source_missing'
    at,raw=source['rows'][0];record=None if raw is None else parse_evidence(raw,instant(at))
    if record is None:return None,'endpoint_source_unqualified'
    if record.status!='valid':return None,'endpoint_source_unavailable'
    if record.stream_epoch!=source_epoch:return None,'endpoint_source_epoch_changed'
    if not record.recorded_at<=target<record.valid_until:return None,'endpoint_source_expired'
    if len(source['rows'])==2:
        previous_at,previous_raw=source['rows'][1]
        previous=None if previous_raw is None else parse_evidence(previous_raw,instant(previous_at))
        if previous is not None and previous.stream_epoch==record.stream_epoch and previous.recorded_at>record.recorded_at:
            return None,'endpoint_record_clock_regressed'
    return record.soc,None


def _cohort(plan,baseline):
    snapshot=plan['inputs']['snapshot'];energy=snapshot['domains']['energy']
    return dict(model_rule=baseline['model_rule'],model_source_sha256=plan['runtime_manifest']['openhab/scripts/household/energy_persistence.py'],
        bank_epoch=energy['physical_bank_epoch']['value'],nominal_bank_kwh=baseline['nominal_bank_kwh'],
        source_epoch=energy['battery_soc']['evidence']['source_epoch'])


def seal_battery_outcomes(*,plan_receipt,endpoint_sources,assessed_at,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime):
    plan=replay_pipeline(plan_receipt,runtime_manifest=plan_runtime_manifest,thermal_runtime=thermal_runtime)
    if plan['schema']!='earthship-household-model-plan-receipt/v6':raise ValueError('original versioned battery projection required')
    runtime=_runtime_manifest(outcome_runtime_manifest);assessed=utc(assessed_at)
    baseline=plan['output']['projections']['energy_persistence'];issue=instant(plan['inputs']['snapshot']['as_of'])
    decision=instant(plan['inputs']['now'])
    if not issue<=decision<=issue+timedelta(seconds=120) or assessed<decision:raise ValueError('original baseline issue or assessment clock differs')
    supported=tuple(h for h in HORIZONS if h<=plan['inputs']['config']['horizon_hours'])
    if not isinstance(endpoint_sources,dict) or not set(endpoint_sources)<={str(h) for h in supported}:raise ValueError('closed endpoint source map required')
    endpoint_sources=loads(canonical(endpoint_sources));available=baseline['status']=='projected_nominal_baseline'
    cohort=_cohort(plan,baseline) if available else None
    origin=None if not available else dict(issued_at=issue.isoformat(),initial_soc_pct=baseline['initial_soc_pct'],battery_power_w=baseline['battery_power_w'],
        projection_sha256=baseline['projection_sha256'])
    pairs={}
    for hours in supported:
        key=str(hours);target=issue+timedelta(hours=hours);source=endpoint_sources.get(key)
        row=dict(horizon_hours=hours,target_at=target.isoformat(),status='not_mature',reason=None,actual_soc_pct=None,
            predictions_soc_pct=None,errors_soc_pct=None,absolute_errors_soc_pct=None)
        if assessed<target+timedelta(minutes=5):
            if source is not None:raise ValueError('immature battery target supplied outcome evidence')
        elif not available:
            row.update(status='baseline_unavailable',reason=baseline['reason'])
        else:
            actual,reason=endpoint_value(source,target=target,assessed=assessed,source_epoch=cohort['source_epoch'])
            row.update(status='pending_source' if source is None else 'source_unavailable',reason=reason)
            if actual is not None:
                point=baseline['trajectory'][hours]
                if instant(point['at'])!=target:raise ValueError('original battery target differs')
                predicted=dict(constant_power=point['nominal_soc_pct'],hold_soc=baseline['initial_soc_pct'])
                errors={name:value-actual for name,value in predicted.items()}
                row.update(status='scored',reason=None,actual_soc_pct=actual,predictions_soc_pct=predicted,
                    errors_soc_pct=errors,absolute_errors_soc_pct={name:abs(value) for name,value in errors.items()})
        pairs[key]=row
    out=dict(evaluation_scope='conditional_battery_persistence_under_actual_behavior',cohort=cohort,
        cohort_id=None if cohort is None else identity(cohort),origin=origin,by_horizon=pairs,
        outcome_quality='qualified_atomic_soc_when_scored',physical_calibration_qualified=False,
        causal_benefit_qualified=False,graduated=False,automatic_actuation=False)
    result=dict(schema='earthship-household-battery-outcome-receipt/v1',inputs=dict(plan_receipt_sha256=plan['receipt_sha256'],
        plan_document_sha256=sha256(canonical(plan)).hexdigest(),endpoint_sources=endpoint_sources,assessed_at=assessed.isoformat()),
        outcome_runtime_manifest=runtime,output=out)
    result['receipt_sha256']=identity(result)
    if len(canonical(result))>MAX_SCORE_BYTES:raise ValueError('bounded compact battery score required')
    return loads(canonical(result))


def _score_record(record):
    if (not isinstance(record,dict) or set(record)!=SCORE_FIELDS or record['schema']!='earthship-household-battery-outcome-receipt/v1' or
        len(canonical(record))>MAX_SCORE_BYTES or not isinstance(record['inputs'],dict) or set(record['inputs'])!=INPUT_FIELDS or
        identity({k:v for k,v in record.items() if k!='receipt_sha256'})!=record['receipt_sha256']):
        raise ValueError('closed original battery score required')
    digest(record['inputs']['plan_receipt_sha256']);digest(record['inputs']['plan_document_sha256'])
    _runtime_manifest(record['outcome_runtime_manifest'])
    inputs=record['inputs'];out=record['output'];assessed=instant(inputs['assessed_at'])
    fields={'evaluation_scope','cohort','cohort_id','origin','by_horizon','outcome_quality','physical_calibration_qualified','causal_benefit_qualified','graduated','automatic_actuation'}
    if (not isinstance(out,dict) or set(out)!=fields or out['evaluation_scope']!='conditional_battery_persistence_under_actual_behavior' or
        out['outcome_quality']!='qualified_atomic_soc_when_scored' or any(out[k] is not False for k in ('physical_calibration_qualified','causal_benefit_qualified','graduated','automatic_actuation'))):
        raise ValueError('closed observational outcome required')
    if not isinstance(out['by_horizon'],dict) or not 1<=len(out['by_horizon'])<=4 or not set(out['by_horizon'])<={str(h) for h in HORIZONS}:
        raise ValueError('bounded report horizons required')
    if not isinstance(inputs['endpoint_sources'],dict) or not set(inputs['endpoint_sources'])<=set(out['by_horizon']):raise ValueError('bounded endpoint map required')
    origin=out['origin'];cohort=out['cohort']
    def finite(value,low,high):
        return type(value) in (int,float) and math.isfinite(value) and low<=value<=high
    if cohort is not None:
        _validate_cohort(cohort)
        if identity(cohort)!=out['cohort_id'] or not isinstance(origin,dict) or set(origin)!={'issued_at','initial_soc_pct','battery_power_w','projection_sha256'}:
            raise ValueError('closed origin and cohort required')
        digest(origin['projection_sha256']);issued=instant(origin['issued_at'])
        if issued>assessed or not finite(origin['initial_soc_pct'],0,100) or not finite(origin['battery_power_w'],-1000000,1000000):raise ValueError('bounded original prediction required')
    elif origin is not None or out['cohort_id'] is not None:raise ValueError('unavailable baseline cannot supply origin')
    for key,row in out['by_horizon'].items():
        if not isinstance(row,dict) or set(row)!={'horizon_hours','target_at','status','reason','actual_soc_pct','predictions_soc_pct','errors_soc_pct','absolute_errors_soc_pct'}:raise ValueError('closed endpoint pair required')
        hours=int(key);target=instant(row['target_at']);mature=assessed>=target+timedelta(minutes=5)
        if type(row['horizon_hours']) is not int or row['horizon_hours']!=hours or cohort is not None and target!=issued+timedelta(hours=hours):raise ValueError('original horizon differs')
        numeric=('actual_soc_pct','predictions_soc_pct','errors_soc_pct','absolute_errors_soc_pct')
        if row['status']=='not_mature':
            if mature or row['reason'] is not None or key in inputs['endpoint_sources']:raise ValueError('immature endpoint differs')
        elif not mature:raise ValueError('terminal endpoint precedes maturity')
        elif row['status']=='pending_source':
            if cohort is None or row['reason']!='endpoint_source_required' or key in inputs['endpoint_sources']:raise ValueError('pending acquisition cannot supply original evidence')
        elif row['status']=='baseline_unavailable':
            if cohort is not None or not isinstance(row['reason'],str) or re.fullmatch('[a-z][a-z0-9_]{0,79}',row['reason']) is None:raise ValueError('unavailable baseline reason required')
        elif row['status'] in ('scored','source_unavailable') and cohort is not None:
            actual,reason=endpoint_value(inputs['endpoint_sources'].get(key),target=target,assessed=assessed,source_epoch=cohort['source_epoch'])
            if row['reason']!=reason or row['actual_soc_pct']!=actual or (actual is not None)!=(row['status']=='scored'):raise ValueError('endpoint status differs from original source')
            if actual is not None:
                for field in numeric[1:]:
                    values=row[field]
                    if not isinstance(values,dict) or set(values)!={'constant_power','hold_soc'} or any(not finite(v,-100 if field=='errors_soc_pct' else 0,100) for v in values.values()):raise ValueError('bounded endpoint errors required')
                continue
        else:raise ValueError('supported endpoint status required')
        if any(row[k] is not None for k in numeric):raise ValueError('unknown endpoint cannot supply numbers')
    return record


def replay_battery_outcomes(receipt,*,plan_receipt,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime):
    _score_record(receipt);value=receipt['inputs']
    if value['plan_receipt_sha256']!=plan_receipt['receipt_sha256'] or value['plan_document_sha256']!=sha256(canonical(plan_receipt)).hexdigest():
        raise ValueError('battery score original plan differs')
    result=seal_battery_outcomes(plan_receipt=plan_receipt,endpoint_sources=value['endpoint_sources'],assessed_at=instant(value['assessed_at']),
        plan_runtime_manifest=plan_runtime_manifest,outcome_runtime_manifest=outcome_runtime_manifest,thermal_runtime=thermal_runtime)
    if canonical(result)!=canonical(receipt):raise ValueError('rederived battery outcome differs')
    return result


def _validate_cohort(cohort):
    if not isinstance(cohort,dict) or set(cohort)!=COHORT_FIELDS or cohort['model_rule']!='constant_net_dc_power_nominal_capacity_v1':
        raise ValueError('closed supported battery cohort required')
    digest(cohort['model_source_sha256']);epoch(cohort['source_epoch'])
    if not isinstance(cohort['bank_epoch'],str) or not 1<=len(cohort['bank_epoch'])<=128:raise ValueError('original bank epoch required')
    capacity=cohort['nominal_bank_kwh']
    if type(capacity) not in (int,float) or not math.isfinite(capacity) or not .001<=capacity<=10000:raise ValueError('bounded nominal capacity required')


def build_performance(scores,*,cohort,generated_at,next_mature_at):
    """Fold immutable producer-validated pairs; full origin replay is separate."""
    _validate_cohort(cohort);generated=utc(generated_at);cohort_id=identity(cohort)
    if not isinstance(scores,(tuple,list)) or len(scores)>1024:raise ValueError('bounded producer score set required')
    terminal={};hourly={}
    for score in scores:
        _score_record(score);out=score['output'];assessed=instant(score['inputs']['assessed_at'])
        if assessed>generated:raise ValueError('future scored pair refused')
        if out.get('cohort_id')!=cohort_id:continue
        if canonical(out['cohort'])!=canonical(cohort):raise ValueError('battery cohort identity differs')
        origin=out['origin'];issued=instant(origin['issued_at']);hour=issued.replace(minute=0,second=0,microsecond=0)
        original=score['inputs']['plan_receipt_sha256']
        if hour in hourly and hourly[hour]!=original:raise ValueError('more than one sampled origin per UTC hour')
        hourly[hour]=original
        for key,row in out['by_horizon'].items():
            hours=int(key)
            if hours not in HORIZONS or row['horizon_hours']!=hours or instant(row['target_at'])!=issued+timedelta(hours=hours):
                raise ValueError('bounded original report target required')
            if row['status'] in ('not_mature','pending_source'):continue
            if row['status']=='scored':
                actual,reason=endpoint_value(score['inputs']['endpoint_sources'].get(key),target=instant(row['target_at']),assessed=assessed,source_epoch=cohort['source_epoch'])
                if reason is not None or actual!=row['actual_soc_pct']:raise ValueError('saved endpoint observation differs')
                energy=cohort['nominal_bank_kwh']*origin['initial_soc_pct']/100+origin['battery_power_w']*hours/1000
                predictions=dict(constant_power=100*min(cohort['nominal_bank_kwh'],max(0.,energy))/cohort['nominal_bank_kwh'],hold_soc=origin['initial_soc_pct'])
                for name,value in predictions.items():
                    error=value-actual
                    if (not math.isclose(row['predictions_soc_pct'][name],value,rel_tol=0,abs_tol=1e-10) or
                        not math.isclose(row['errors_soc_pct'][name],error,rel_tol=0,abs_tol=1e-10) or
                        not math.isclose(row['absolute_errors_soc_pct'][name],abs(error),rel_tol=0,abs_tol=1e-10)):
                        raise ValueError('saved endpoint arithmetic differs')
            elif row['status'] not in ('source_unavailable','baseline_unavailable'):raise ValueError('unsupported terminal outcome')
            lookup=(original,key)
            if lookup in terminal and canonical(terminal[lookup][1])!=canonical(row):raise ValueError('conflicting terminal outcome')
            terminal[lookup]=(issued,row)
    by={};targets=[];all_days=set()
    for hours in HORIZONS:
        rows=[(issued,row) for (_,key),(issued,row) in terminal.items() if key==str(hours)]
        scored=[(issued,row) for issued,row in rows if row['status']=='scored'];days={issued.astimezone(ZoneInfo('America/Denver')).date() for issued,_ in scored}
        all_days.update(days);latest=max((instant(row['target_at']) for _,row in scored),default=None)
        if latest is not None:targets.append(latest)
        by[str(hours)]=dict(count=len(scored),attempted_count=len(rows),unique_origin_days=len(days),
            mae_soc_pct=None if not scored else {name:math.fsum(row['absolute_errors_soc_pct'][name] for _,row in scored)/len(scored) for name in ('constant_power','hold_soc')},
            bias_soc_pct=None if not scored else {name:math.fsum(row['errors_soc_pct'][name] for _,row in scored)/len(scored) for name in ('constant_power','hold_soc')},
            last_target_at=None if latest is None else latest.isoformat())
    report=dict(schema='earthship-household-battery-performance/v1',generated_at=generated.isoformat(),valid_until=(generated+timedelta(minutes=30)).isoformat(),
        cohort_id=cohort_id,model_rule=cohort['model_rule'],by_horizon=by,unique_origin_days=len(all_days),
        last_target_at=None if not targets else max(targets).isoformat(),next_mature_at=None if next_mature_at is None else utc(next_mature_at).isoformat(),
        sampling_basis='one_origin_per_utc_hour',validation_scope='sealed_producer_endpoint_pairs',physical_calibration_qualified=False,
        causal_benefit_qualified=False,graduated=False,automatic_actuation=False)
    report['report_sha256']=identity(report);return loads(canonical(report))
