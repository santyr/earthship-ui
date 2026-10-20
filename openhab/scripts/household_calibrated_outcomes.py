"""Matched calibrated/raw PV storage outcomes from retained original forecasts."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import json
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household_calibrated_energy import replay,runtime_manifest as forecast_runtime
from household.battery_outcomes import endpoint_value,HORIZONS
from household_ac_load_window import account_hour
from household_ac_load_model import POLICY

SCHEMA='earthship-household-calibrated-energy-outcome/v1'
MAX_BYTES=5*1048576
SOC_MODELS=('calibrated_pv','raw_pv','hold_soc')
FLAGS=dict(physical_calibration_qualified=False,causal_benefit_qualified=False,graduated=False,automatic_actuation=False)


def runtime_manifest():
    result=forecast_runtime();root=Path(__file__).resolve().parent
    for name in ('household_calibrated_outcomes.py','household_calibrated_score.py','household_battery_source.py','household/battery_outcomes.py','household_ac_load_window.py','household_ac_load_model.py'):
        result['openhab/scripts/'+name]=sha256((root/name).read_bytes()).hexdigest()
    return result


def _predictions(forecast,plan,profiled):
    out=forecast['output'];issue=instant(out['issued_at']);storage=out['profiled_storage'];raw=out['uncalibrated_profiled_storage']
    available=storage['status']=='conditional_nominal_simulation';load=None if profiled is None else profiled['output']['load_forecast']
    load_available=load is not None and load['status']=='projected'
    initial=out.get('storage_initial_conditions',{});energy=plan['inputs']['snapshot']['domains']['energy']
    source=energy['battery_soc'].get('evidence');epoch=None if source is None else source['source_epoch']
    calibration=json.loads(forecast['inputs']['calibration_raw'])['final_model']['model_sha256']
    model=None if profiled is None or profiled['inputs']['load_source'] is None else profiled['inputs']['load_source']['artifact']['profile']['model_sha256']
    cohort=dict(calibration_model_sha256=calibration,forecast_runtime_sha256=identity(forecast['runtime_manifest']),
        physical_bank_epoch=energy['physical_bank_epoch']['value'],nominal_bank_kwh=initial.get('nominal_bank_kwh'),source_epoch=epoch)
    rows={}
    for h in HORIZONS:
        target=issue+timedelta(hours=h);soc=None;mean=None
        if available:
            a,b=storage['trajectory'][h-1],raw['trajectory'][h-1]
            if instant(a['at'])!=target or instant(b['at'])!=target:raise ValueError('same original storage targets required')
            soc=dict(calibrated_pv=a['nominal_soc_pct'],raw_pv=b['nominal_soc_pct'],hold_soc=storage['initial_soc_pct'])
        if load_available:
            row=load['trajectory'][h-1]
            if instant(row['at'])!=target:raise ValueError('same original AC target required')
            mean=row['mean_ac_w']
        rows[str(h)]=dict(target_at=target.isoformat(),soc_predictions=soc,load_mean_ac_w=mean,
            current_load_w=initial.get('current_load_w') if initial.get('current_load_reason') is None else None)
    return dict(issued_at=issue.isoformat(),calibration_model_sha256=calibration,load_model_sha256=model,
        cohort=cohort,cohort_id=identity(cohort),by_horizon=rows)


def _score_rows(origin,*,hour_sources,endpoint_sources,assessed):
    output={}
    for h in HORIZONS:
        key=str(h);prediction=origin['by_horizon'][key];target=instant(prediction['target_at']);start=target-timedelta(hours=1)
        if target!=instant(origin['issued_at'])+timedelta(hours=h):raise ValueError('original horizon target required')
        mature=assessed>=target+timedelta(minutes=5);hour=hour_sources.get(key);endpoint=endpoint_sources.get(key)
        if not mature and (hour is not None or endpoint is not None):raise ValueError('immature target supplied outcome evidence')
        soc=dict(status='not_mature',reason=None,actual_soc_pct=None,predictions_soc_pct=None,errors_soc_pct=None,absolute_errors_soc_pct=None)
        load=dict(status='not_mature',reason=None,actual_known_ac_kwh=None,covered_seconds=None,missing_seconds=None,coverage=None,
            predictions_kwh=None,errors_kwh=None,absolute_errors_kwh=None)
        if mature:
            actual,reason=endpoint_value(endpoint,target=target,assessed=assessed,source_epoch=origin['cohort']['source_epoch'])
            if prediction['soc_predictions'] is None:soc.update(status='scenario_unavailable',reason='qualified_initial_storage_state_required')
            elif endpoint is None:soc.update(status='pending_source',reason=reason)
            elif actual is None:soc.update(status='source_unavailable',reason=reason)
            else:
                values=prediction['soc_predictions'];errors={k:v-actual for k,v in values.items()}
                soc.update(status='scored',actual_soc_pct=actual,predictions_soc_pct=values,errors_soc_pct=errors,absolute_errors_soc_pct={k:abs(v) for k,v in errors.items()})
            account=None if hour is None else account_hour(hour,assessed_at=assessed,start=start,end=target)
            if prediction['load_mean_ac_w'] is None:load.update(status='scenario_unavailable',reason='qualified_load_forecast_required')
            elif account is None:load.update(status='pending_source',reason='hour_source_required')
            elif account['status']!='accounted':load.update(status='source_unavailable',reason=account['reason'])
            else:
                load.update(actual_known_ac_kwh=account['known_ac_kwh'],covered_seconds=account['covered_seconds'],missing_seconds=account['missing_seconds'],coverage=account['coverage'])
                if account['coverage']<POLICY['minimum_coverage']:load.update(status='insufficient_coverage',reason='qualified_hour_coverage_required')
                else:
                    duration=account['covered_seconds']/3600000
                    values=dict(learned_ac=prediction['load_mean_ac_w']*duration,
                        current_ac=None if prediction['current_load_w'] is None else prediction['current_load_w']*duration)
                    errors={k:None if v is None else v-account['known_ac_kwh'] for k,v in values.items()}
                    load.update(status='scored',predictions_kwh=values,errors_kwh=errors,absolute_errors_kwh={k:None if v is None else abs(v) for k,v in errors.items()})
        output[key]=dict(horizon_hours=h,target_at=target.isoformat(),window_start=start.isoformat(),soc=soc,load=load)
    return output


def seal_outcomes(*,forecast,energy,plan,profiled,hour_sources,endpoint_sources,assessed_at):
    forecast=replay(forecast,energy=energy,plan=plan,profiled=profiled);assessed=utc(assessed_at)
    if assessed<instant(forecast['inputs']['assessed_at']):raise ValueError('outcome assessment precedes original forecast')
    for sources in (hour_sources,endpoint_sources):
        if not isinstance(sources,dict) or not set(sources)<={str(h) for h in HORIZONS}:raise ValueError('closed original outcome source map required')
    hours=loads(canonical(hour_sources));endpoints=loads(canonical(endpoint_sources));origin=_predictions(forecast,plan,profiled)
    value=dict(schema=SCHEMA,inputs=dict(forecast_document_sha256=identity(forecast),forecast_receipt_sha256=forecast['receipt_sha256'],
        energy_document_sha256=identity(energy),plan_document_sha256=identity(plan),profiled_document_sha256=None if profiled is None else identity(profiled),
        assessed_at=assessed.isoformat(),hour_sources=hours,endpoint_sources=endpoints,origin=origin),runtime_manifest=runtime_manifest(),
        output=dict(issued_at=origin['issued_at'],cohort_id=origin['cohort_id'],calibration_model_sha256=origin['calibration_model_sha256'],
            load_model_sha256=origin['load_model_sha256'],by_horizon=_score_rows(origin,hour_sources=hours,endpoint_sources=endpoints,assessed=assessed),
            load_evaluation='hour_ending_at_lead_time_over_qualified_covered_intervals',pv_energy_accuracy='unavailable_unmatched_meter_scope',**FLAGS))
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded calibrated outcome receipt required')
    return loads(canonical(value))


def validate_score(value):
    if (not isinstance(value,dict) or set(value)!={'schema','inputs','runtime_manifest','output','receipt_sha256'} or value['schema']!=SCHEMA or
        len(canonical(value))>MAX_BYTES or identity({k:v for k,v in value.items() if k!='receipt_sha256'})!=value['receipt_sha256']):raise ValueError('unchanged calibrated outcome required')
    inputs=value['inputs'];out=value['output'];origin=inputs['origin']
    if any(out[k] is not False for k in FLAGS) or origin['cohort_id']!=identity(origin['cohort']) or out['cohort_id']!=origin['cohort_id']:
        raise ValueError('observational calibrated outcome required')
    expected=_score_rows(origin,hour_sources=inputs['hour_sources'],endpoint_sources=inputs['endpoint_sources'],assessed=instant(inputs['assessed_at']))
    if canonical(out['by_horizon'])!=canonical(expected):raise ValueError('original calibrated outcome arithmetic differs')
    return value


def replay_outcomes(value,*,forecast,energy,plan,profiled):
    validate_score(value)
    if value['runtime_manifest']!=runtime_manifest():raise ValueError('calibrated outcome runtime differs')
    inputs=value['inputs'];expected=seal_outcomes(forecast=forecast,energy=energy,plan=plan,profiled=profiled,
        hour_sources=inputs['hour_sources'],endpoint_sources=inputs['endpoint_sources'],assessed_at=instant(inputs['assessed_at']))
    if canonical(value)!=canonical(expected):raise ValueError('original calibrated outcome differs')
    return expected


SAMPLE='earthship-calibrated-energy-verified-sample/v1'
REPORT='earthship-household-calibrated-energy-performance/v1'


def summarize_score(score,*,verified_at,score_file_sha256):
    score=validate_score(score);verified=utc(verified_at)
    if verified<instant(score['inputs']['assessed_at']):raise ValueError('verification precedes score')
    value=dict(schema=SAMPLE,score_document_sha256=identity(score),score_file_sha256=score_file_sha256,
        score_receipt_sha256=score['receipt_sha256'],forecast_document_sha256=score['inputs']['forecast_document_sha256'],
        verified_at=verified.isoformat(),assessed_at=score['inputs']['assessed_at'],origin=score['inputs']['origin'],
        hour_source_pins={k:v['source_sha256'] for k,v in score['inputs']['hour_sources'].items()},
        endpoint_source_pins={k:v['source_sha256'] for k,v in score['inputs']['endpoint_sources'].items()},output=score['output'])
    value['sample_sha256']=identity(value);return validate_sample(loads(canonical(value)))


def validate_sample(value):
    from math import isfinite,isclose
    from household.evidence import digest
    fields={'schema','score_document_sha256','score_file_sha256','score_receipt_sha256','forecast_document_sha256','verified_at','assessed_at','origin','hour_source_pins','endpoint_source_pins','output','sample_sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['schema']!=SAMPLE or len(canonical(value))>32768 or
        value['sample_sha256']!=identity({k:v for k,v in value.items() if k!='sample_sha256'})):raise ValueError('closed verified calibrated sample required')
    for key in ('score_document_sha256','score_file_sha256','score_receipt_sha256','forecast_document_sha256'):digest(value[key])
    assessed=instant(value['assessed_at']);origin=value['origin'];out=value['output']
    if instant(value['verified_at'])<assessed or origin['cohort_id']!=identity(origin['cohort']) or out['cohort_id']!=origin['cohort_id'] or out['issued_at']!=origin['issued_at'] or out['calibration_model_sha256']!=origin['calibration_model_sha256'] or out['load_model_sha256']!=origin['load_model_sha256'] or any(out[k] is not False for k in FLAGS):raise ValueError('original observational cohort required')
    if out['pv_energy_accuracy']!='unavailable_unmatched_meter_scope' or out['load_evaluation']!='hour_ending_at_lead_time_over_qualified_covered_intervals' or set(out['by_horizon'])!={str(h) for h in HORIZONS}:raise ValueError('fixed matched sample scope required')
    for key in ('hour_source_pins','endpoint_source_pins'):
        if not isinstance(value[key],dict) or not set(value[key])<={str(h) for h in HORIZONS}:raise ValueError('bounded source pins required')
        for pin in value[key].values():digest(pin)
    def number(n,low,high):return type(n) in (int,float) and isfinite(n) and low<=n<=high
    for h in HORIZONS:
        key=str(h);row=out['by_horizon'][key];target=instant(origin['issued_at'])+timedelta(hours=h)
        if row['horizon_hours']!=h or instant(row['target_at'])!=target or instant(row['window_start'])!=target-timedelta(hours=1):raise ValueError('matched sample target required')
        for name,actual,predictions,errors,absolute,models,bounds,pin_key in (
            ('soc','actual_soc_pct','predictions_soc_pct','errors_soc_pct','absolute_errors_soc_pct',SOC_MODELS,(0,100),'endpoint_source_pins'),
            ('load','actual_known_ac_kwh','predictions_kwh','errors_kwh','absolute_errors_kwh',('learned_ac','current_ac'),(0,20),'hour_source_pins')):
            metric=row[name]
            if metric['status']!='scored':
                if any(metric[k] is not None for k in (predictions,errors,absolute)):raise ValueError('unavailable sample supplied errors')
                continue
            if assessed<target+timedelta(minutes=5) or key not in value[pin_key] or not number(metric[actual],*bounds):raise ValueError('mature qualified sample required')
            if name=='load' and (not number(metric['covered_seconds'],0,3600) or not number(metric['missing_seconds'],0,3600) or not number(metric['coverage'],POLICY['minimum_coverage'],1) or not isclose(metric['coverage'],metric['covered_seconds']/3600,abs_tol=1e-10) or not isclose(metric['covered_seconds']+metric['missing_seconds'],3600,abs_tol=1e-7)):raise ValueError('qualified matched AC coverage required')
            for field in (predictions,errors,absolute):
                if set(metric[field])!=set(models):raise ValueError('closed sample model set required')
            for model in models:
                prediction=metric[predictions][model]
                if name=='load' and model=='current_ac' and prediction is None:
                    if metric[errors][model] is not None or metric[absolute][model] is not None:raise ValueError('unavailable current load supplied error')
                    continue
                if not number(prediction,*bounds) or not number(metric[errors][model],-bounds[1],bounds[1]) or not number(metric[absolute][model],0,bounds[1]) or not isclose(metric[errors][model],prediction-metric[actual],abs_tol=1e-10) or not isclose(metric[absolute][model],abs(metric[errors][model]),abs_tol=1e-10):raise ValueError('original calibrated sample arithmetic differs')
    return value


def performance(samples,*,origin,generated_at):
    from math import fsum
    from zoneinfo import ZoneInfo
    now=utc(generated_at);accepted=[];seen=set()
    for value in samples:
        value=validate_sample(value)
        if instant(value['verified_at'])>now:raise ValueError('future verified score supplied')
        if value['origin']['cohort_id']!=origin['cohort_id']:continue
        issue=instant(value['origin']['issued_at'])
        if not now-timedelta(days=7)<=issue<=now:continue
        key=issue.replace(minute=0,second=0,microsecond=0)
        if key in seen:raise ValueError('one sampled origin per cohort hour required')
        seen.add(key);accepted.append(value)
    result={}
    for h in HORIZONS:
        mature=[s['output']['by_horizon'][str(h)] for s in accepted if now>=instant(s['origin']['issued_at'])+timedelta(hours=h,minutes=5)]
        soc=[r['soc'] for r in mature if r['soc']['status']=='scored'];load=[r['load'] for r in mature if r['load']['status']=='scored'];current=[r for r in load if r['absolute_errors_kwh']['current_ac'] is not None]
        def mean(rows,key,model):return None if not rows else fsum(r[key][model] for r in rows)/len(rows)
        result[str(h)]=dict(soc=dict(attempted_count=len(mature),count=len(soc),mae_soc_pct={m:mean(soc,'absolute_errors_soc_pct',m) for m in SOC_MODELS}),
            load=dict(attempted_count=len(mature),count=len(load),current_count=len(current),mae_kwh=dict(learned_ac=mean(load,'absolute_errors_kwh','learned_ac'),current_ac=mean(current,'absolute_errors_kwh','current_ac'))))
    zone=ZoneInfo('America/Denver');issues=[s['origin']['issued_at'] for s in accepted]
    value=dict(schema=REPORT,generated_at=now.isoformat(),valid_until=(now+timedelta(hours=1)).isoformat(),cohort_id=origin['cohort_id'],
        calibration_model_sha256=origin['calibration_model_sha256'],model_version_count=len({s['origin']['load_model_sha256'] for s in accepted if s['origin']['load_model_sha256'] is not None}),
        independent_origin_days=len({instant(t).astimezone(zone).date() for t in issues}),first_issue=min(issues) if issues else None,last_issue=max(issues) if issues else None,
        by_horizon=result,**FLAGS)
    value['view_sha256']=identity(value);return value
