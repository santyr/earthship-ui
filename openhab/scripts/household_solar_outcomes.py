#!/usr/bin/env python3
"""Matched original SoC outcomes for conditional solar/load storage scenarios."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse,math,sys
from household.codec import canonical,loads,identity
from household.evidence import utc,digest,epoch
from household.control_contracts import instant
from household.planning import _runtime_manifest
from household.battery_outcomes import endpoint_value,HORIZONS
from household.model_snapshot import restore_snapshot
from household.energy_persistence import project_persistence
from household_energy_forecast import replay_energy_forecast,forecast_runtime_manifest as current_forecast_runtime
from household_snapshot import _read

MAX_BYTES=65536
MODELS=('pv_load_scenario','constant_power','hold_soc')
SCHEMA='earthship-household-solar-storage-outcome/v1'
REPORT='earthship-household-solar-storage-performance/v1'
COHORT_FIELDS={'model_rule','model_sources_sha256','system_sha256','horizon_sha256','topology_sha256','bank_epoch','nominal_bank_kwh','source_epoch'}
INPUT_FIELDS={'forecast_receipt_sha256','forecast_document_sha256','plan_receipt_sha256','plan_document_sha256','endpoint_sources','assessed_at'}
FLAGS=('physical_calibration_qualified','causal_benefit_qualified','graduated','automatic_actuation')


def energy_outcome_runtime_manifest():
    result=current_forecast_runtime();root=Path(__file__).resolve().parent
    for name in ('household_solar_outcomes.py','household_battery_source.py','household_solar_score.py','household_energy_state.py'):
        result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    return result


def cohort_for(forecast,plan):
    storage=forecast['output']['nominal_storage']
    if storage['status']!='conditional_nominal_simulation':return None
    inputs=forecast['inputs'];energy=plan['inputs']['snapshot']['domains']['energy']
    bank=energy['physical_bank_epoch']['value'];source=energy['battery_soc']['evidence']['source_epoch']
    if not isinstance(bank,str) or not 1<=len(bank)<=128:return None
    epoch(source)
    # Bind the complete retained prediction closure, including load-flow and
    # configuration helpers. Operational scoring/publication modules are separate.
    model_sources=forecast['runtime_manifest']
    return dict(model_rule=storage['model_rule'],model_sources_sha256=identity(model_sources),system_sha256=inputs['system_source']['sha256'],
        horizon_sha256=inputs['horizon_source']['sha256'],topology_sha256=inputs['topology_source']['sha256'],bank_epoch=bank,
        nominal_bank_kwh=storage['nominal_bank_kwh'],source_epoch=source)


def matched_reference(plan):
    """Rederive the original reference independently of saved plan outputs."""
    saved=plan['output']['projections'].get('energy_persistence')
    if saved is None:return None
    inputs=plan['inputs'];snapshot=restore_snapshot(inputs['snapshot'],inputs['source_contexts'])
    original=project_persistence(snapshot=snapshot,metric_source=inputs.get('energy_persistence_source'),
        horizon_hours=inputs['config']['horizon_hours'],now=instant(inputs['now']))
    if canonical(saved)!=canonical(original):raise ValueError('original constant-power reference differs')
    return original if original['status']=='projected_nominal_baseline' and original['horizon_hours']==24 else None


def _cohort(value):
    if not isinstance(value,dict) or set(value)!=COHORT_FIELDS or value['model_rule']!='array_potential_constant_AC_load_nominal_storage_v1':raise ValueError('closed solar storage cohort required')
    for key in ('model_sources_sha256','system_sha256','horizon_sha256','topology_sha256'):digest(value[key])
    epoch(value['source_epoch'])
    if not isinstance(value['bank_epoch'],str) or not 1<=len(value['bank_epoch'])<=128 or not _number(value['nominal_bank_kwh'],.001,10000):raise ValueError('original nominal bank identity required')
    return value


def _number(value,low,high):return type(value) in (int,float) and math.isfinite(value) and low<=value<=high


def seal_energy_outcomes(*,forecast_receipt,plan_receipt,endpoint_sources,assessed_at,forecast_runtime_manifest,outcome_runtime_manifest):
    forecast=replay_energy_forecast(forecast_receipt,plan_receipt=plan_receipt,runtime_manifest=forecast_runtime_manifest)
    assessed=utc(assessed_at);runtime=_runtime_manifest(outcome_runtime_manifest)
    if not {'openhab/scripts/'+name for name in ('household_solar_outcomes.py','household_battery_source.py','household_solar_score.py','household_energy_state.py')}<=set(runtime):raise ValueError('complete solar outcome source closure required')
    issue=instant(forecast['output']['array_pv']['origin']);decision=instant(forecast['inputs']['assessed_at'])
    if not issue<=decision<=issue+timedelta(seconds=120) or assessed<decision:raise ValueError('original scenario issue or assessment differs')
    if not isinstance(endpoint_sources,dict) or not set(endpoint_sources)<={str(h) for h in HORIZONS}:raise ValueError('closed mature endpoint map required')
    sources=loads(canonical(endpoint_sources));storage=forecast['output']['nominal_storage'];baseline=matched_reference(plan_receipt)
    cohort=cohort_for(forecast,plan_receipt);available=cohort is not None and baseline is not None and baseline['status']=='projected_nominal_baseline'
    if available and (baseline['origin']!=issue.isoformat() or baseline['initial_soc_pct']!=storage['initial_soc_pct'] or baseline['nominal_bank_kwh']!=storage['nominal_bank_kwh']):raise ValueError('matched reference origin differs')
    predictions={}
    if available:
        for h in HORIZONS:
            point=storage['trajectory'][h-1];reference=baseline['trajectory'][h]
            if instant(point['at'])!=issue+timedelta(hours=h) or point['at']!=reference['at']:raise ValueError('original scenario/reference target differs')
            predictions[str(h)]=dict(pv_load_scenario=point['nominal_soc_pct'],constant_power=reference['nominal_soc_pct'],hold_soc=storage['initial_soc_pct'])
    origin=None if not available else dict(issued_at=issue.isoformat(),initial_soc_pct=storage['initial_soc_pct'],predictions_by_horizon_soc_pct=predictions)
    pairs={}
    for h in HORIZONS:
        key=str(h);target=issue+timedelta(hours=h);source=sources.get(key)
        row=dict(horizon_hours=h,target_at=target.isoformat(),status='not_mature',reason=None,actual_soc_pct=None,predictions_soc_pct=None,errors_soc_pct=None,absolute_errors_soc_pct=None)
        if assessed<target+timedelta(minutes=5):
            if source is not None:raise ValueError('immature scenario endpoint supplied evidence')
        elif not available:
            # Supplied originals still need integrity checks without a usable forecast.
            if source is not None:endpoint_value(source,target=target,assessed=assessed,source_epoch=None)
            row.update(status='scenario_or_reference_unavailable',reason='matched_forecasts_unavailable')
        else:
            actual,reason=endpoint_value(source,target=target,assessed=assessed,source_epoch=cohort['source_epoch'])
            row.update(status='pending_source' if source is None else 'source_unavailable',reason=reason)
            if actual is not None:
                values=predictions[key];errors={name:values[name]-actual for name in MODELS}
                row.update(status='scored',reason=None,actual_soc_pct=actual,predictions_soc_pct=values,errors_soc_pct=errors,absolute_errors_soc_pct={name:abs(v) for name,v in errors.items()})
        pairs[key]=row
    output=dict(evaluation_scope='conditional_solar_load_storage_under_actual_behavior',cohort=cohort if available else None,
        cohort_id=identity(cohort) if available else None,origin=origin,by_horizon=pairs,pv_energy_accuracy='unavailable_unmatched_meter_scope',
        outcome_quality='qualified_atomic_soc_when_scored',**{k:False for k in FLAGS})
    inputs=dict(forecast_receipt_sha256=forecast['receipt_sha256'],forecast_document_sha256=sha256(canonical(forecast)).hexdigest(),
        plan_receipt_sha256=plan_receipt['receipt_sha256'],plan_document_sha256=sha256(canonical(plan_receipt)).hexdigest(),endpoint_sources=sources,assessed_at=assessed.isoformat())
    value=dict(schema=SCHEMA,inputs=inputs,outcome_runtime_manifest=runtime,output=output);value['receipt_sha256']=identity(value)
    return validate_score(loads(canonical(value)))


def validate_score(value):
    if (not isinstance(value,dict) or set(value)!={'schema','inputs','outcome_runtime_manifest','output','receipt_sha256'} or value['schema']!=SCHEMA or len(canonical(value))>MAX_BYTES or
        identity({k:v for k,v in value.items() if k!='receipt_sha256'})!=value['receipt_sha256']):raise ValueError('closed original solar score required')
    inputs=value['inputs'];out=value['output']
    if not isinstance(inputs,dict) or set(inputs)!=INPUT_FIELDS:raise ValueError('closed score originals required')
    for key in INPUT_FIELDS-{'endpoint_sources','assessed_at'}:digest(inputs[key])
    _runtime_manifest(value['outcome_runtime_manifest']);assessed=instant(inputs['assessed_at'])
    if (not isinstance(out,dict) or set(out)!={'evaluation_scope','cohort','cohort_id','origin','by_horizon','pv_energy_accuracy','outcome_quality',*FLAGS} or
        out['evaluation_scope']!='conditional_solar_load_storage_under_actual_behavior' or out['outcome_quality']!='qualified_atomic_soc_when_scored' or
        out['pv_energy_accuracy']!='unavailable_unmatched_meter_scope' or any(out[k] is not False for k in FLAGS) or
        not isinstance(out['by_horizon'],dict) or set(out['by_horizon'])!={str(h) for h in HORIZONS} or not isinstance(inputs['endpoint_sources'],dict) or not set(inputs['endpoint_sources'])<=set(out['by_horizon'])):raise ValueError('closed conditional score output required')
    origin=out['origin'];cohort=out['cohort']
    if cohort is not None:
        _cohort(cohort)
        if identity(cohort)!=out['cohort_id'] or not isinstance(origin,dict) or set(origin)!={'issued_at','initial_soc_pct','predictions_by_horizon_soc_pct'}:raise ValueError('original cohort and predictions required')
        if instant(origin['issued_at'])>assessed or not _number(origin['initial_soc_pct'],0,100) or set(origin['predictions_by_horizon_soc_pct'])!={str(h) for h in HORIZONS}:raise ValueError('bounded original prediction clock required')
        for predictions in origin['predictions_by_horizon_soc_pct'].values():
            if not isinstance(predictions,dict) or set(predictions)!=set(MODELS) or any(not _number(v,0,100) for v in predictions.values()) or predictions['hold_soc']!=origin['initial_soc_pct']:raise ValueError('original matched predictions required')
    elif origin is not None or out['cohort_id'] is not None:raise ValueError('unavailable forecast supplied origin')
    for key,row in out['by_horizon'].items():
        if not isinstance(row,dict) or set(row)!={'horizon_hours','target_at','status','reason','actual_soc_pct','predictions_soc_pct','errors_soc_pct','absolute_errors_soc_pct'}:raise ValueError('closed original endpoint pair required')
        h=int(key);target=instant(row['target_at']);mature=assessed>=target+timedelta(minutes=5)
        if type(row['horizon_hours']) is not int or row['horizon_hours']!=h or origin is not None and target!=instant(origin['issued_at'])+timedelta(hours=h):raise ValueError('matched endpoint target differs')
        numeric=('actual_soc_pct','predictions_soc_pct','errors_soc_pct','absolute_errors_soc_pct')
        if row['status']=='not_mature':
            if mature or row['reason'] is not None or key in inputs['endpoint_sources']:raise ValueError('immature pair differs')
        elif not mature:raise ValueError('terminal pair precedes maturity')
        elif row['status']=='scenario_or_reference_unavailable':
            if cohort is not None or row['reason']!='matched_forecasts_unavailable':raise ValueError('unavailable scenario differs')
            if key in inputs['endpoint_sources']:endpoint_value(inputs['endpoint_sources'][key],target=target,assessed=assessed,source_epoch=None)
        elif row['status']=='pending_source':
            if cohort is None or key in inputs['endpoint_sources'] or row['reason']!='endpoint_source_required':raise ValueError('pending pair supplied evidence')
        elif row['status'] in ('scored','source_unavailable') and cohort is not None:
            actual,reason=endpoint_value(inputs['endpoint_sources'].get(key),target=target,assessed=assessed,source_epoch=cohort['source_epoch'])
            if row['reason']!=reason or row['actual_soc_pct']!=actual or (actual is not None)!=(row['status']=='scored'):raise ValueError('original endpoint outcome differs')
            if actual is not None:
                expected=origin['predictions_by_horizon_soc_pct'][key]
                if row['predictions_soc_pct']!=expected:raise ValueError('saved as-issued prediction differs')
                for field in ('errors_soc_pct','absolute_errors_soc_pct'):
                    if not isinstance(row[field],dict) or set(row[field])!=set(MODELS):raise ValueError('matched error map required')
                    for name in MODELS:
                        number=expected[name]-actual;number=abs(number) if field=='absolute_errors_soc_pct' else number
                        if not _number(row[field][name],-100,100) or not math.isclose(row[field][name],number,rel_tol=0,abs_tol=1e-10):raise ValueError('saved error arithmetic differs')
                continue
        else:raise ValueError('supported endpoint status required')
        if any(row[k] is not None for k in numeric):raise ValueError('unknown endpoint supplied numbers')
    return value


def replay_energy_outcomes(receipt,*,forecast_receipt,plan_receipt,forecast_runtime_manifest,outcome_runtime_manifest):
    validate_score(receipt)
    if canonical(receipt['outcome_runtime_manifest'])!=canonical(outcome_runtime_manifest):raise ValueError('original outcome runtime differs')
    result=seal_energy_outcomes(forecast_receipt=forecast_receipt,plan_receipt=plan_receipt,endpoint_sources=receipt['inputs']['endpoint_sources'],
        assessed_at=instant(receipt['inputs']['assessed_at']),forecast_runtime_manifest=forecast_runtime_manifest,outcome_runtime_manifest=outcome_runtime_manifest)
    if canonical(result)!=canonical(receipt):raise ValueError('original solar outcome differs')
    return result


def build_energy_performance(scores,*,cohort,generated_at,next_mature_at):
    _cohort(cohort);generated=utc(generated_at);cohort_id=identity(cohort);terminal={};hours={}
    if not isinstance(scores,(list,tuple)) or len(scores)>192:raise ValueError('bounded hourly score sample required')
    for score in scores:
        validate_score(score);out=score['output'];issued=None if out['origin'] is None else instant(out['origin']['issued_at'])
        if instant(score['inputs']['assessed_at'])>generated:raise ValueError('future score refused')
        if out['cohort_id']!=cohort_id:continue
        if canonical(out['cohort'])!=canonical(cohort):raise ValueError('scored cohort differs')
        if issued<generated-timedelta(days=7):continue
        hour=issued.replace(minute=0,second=0,microsecond=0);pin=score['inputs']['forecast_receipt_sha256']
        if hour in hours and hours[hour]!=pin:raise ValueError('more than one original per UTC hour')
        hours[hour]=pin
        for key,row in out['by_horizon'].items():
            if row['status'] in ('not_mature','pending_source'):continue
            lookup=(pin,key)
            if lookup in terminal and canonical(terminal[lookup][1])!=canonical(row):raise ValueError('conflicting terminal score')
            terminal[lookup]=(issued,row)
    by={};all_days=set();targets=[]
    for h in HORIZONS:
        attempted=[(issued,row) for (_,key),(issued,row) in terminal.items() if key==str(h)];scored=[(issued,row) for issued,row in attempted if row['status']=='scored']
        days={issued.astimezone(ZoneInfo('America/Denver')).date() for issued,_ in scored};all_days.update(days)
        last=max((instant(row['target_at']) for _,row in scored),default=None)
        if last is not None:targets.append(last)
        n=len(scored);mae=bias=rmse=skill=None
        if n:
            mae={name:math.fsum(row['absolute_errors_soc_pct'][name] for _,row in scored)/n for name in MODELS}
            bias={name:math.fsum(row['errors_soc_pct'][name] for _,row in scored)/n for name in MODELS}
            rmse={name:math.sqrt(math.fsum(row['errors_soc_pct'][name]**2 for _,row in scored)/n) for name in MODELS}
            skill={name:None if rmse[name]==0 else 1-rmse['pv_load_scenario']/rmse[name] for name in ('constant_power','hold_soc')}
        by[str(h)]=dict(count=n,attempted_count=len(attempted),unique_origin_days=len(days),mae_soc_pct=mae,bias_soc_pct=bias,rmse_soc_pct=rmse,rmse_skill=skill,last_target_at=None if last is None else last.isoformat())
    report=dict(schema=REPORT,generated_at=generated.isoformat(),valid_until=(generated+timedelta(minutes=30)).isoformat(),cohort_id=cohort_id,
        model_rule=cohort['model_rule'],by_horizon=by,unique_origin_days=len(all_days),last_target_at=None if not targets else max(targets).isoformat(),
        next_mature_at=None if next_mature_at is None else utc(next_mature_at).isoformat(),sampling_basis='one_origin_per_utc_hour',
        validation_scope='sealed_producer_endpoint_pairs',pv_energy_accuracy='unavailable_unmatched_meter_scope',**{k:False for k in FLAGS})
    report['report_sha256']=identity(report);return loads(canonical(report))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('receipt','forecast','plan'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        originals={name:_read(getattr(args,name),maximum,private=True) for name,maximum in (('receipt',MAX_BYTES),('forecast',262144),('plan',2097152))}
        record,forecast,plan=(loads(originals[name]) for name in ('receipt','forecast','plan'))
        if instant(record['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future score assessment refused')
        runtime=energy_outcome_runtime_manifest();fr=current_forecast_runtime()
        result=replay_energy_outcomes(record,forecast_receipt=forecast,plan_receipt=plan,forecast_runtime_manifest=fr,outcome_runtime_manifest=runtime)
        if energy_outcome_runtime_manifest()!=runtime or current_forecast_runtime()!=fr or any(_read(getattr(args,name),maximum,private=True)!=originals[name] for name,maximum in (('receipt',MAX_BYTES),('forecast',262144),('plan',2097152))):raise ValueError('original replay files changed')
        sys.stdout.buffer.write(canonical(result)+b'\n');return 0
    except Exception:
        print('Solar storage outcome replay refused: invalid or changed original context.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
