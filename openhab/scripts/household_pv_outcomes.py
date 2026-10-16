"""Versioned captured-controller-DC comparisons; potential yield stays unscored.

Predictions are the frozen scenario's hour means, integrated over exactly the
observed duration. They retain assumed losses/acceptance, not calibrated limits.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import math
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,epoch
from household.planning import _runtime_manifest
from household_snapshot import _read
from household_energy_forecast import replay_energy_forecast,forecast_runtime_manifest
from household_solar_outcomes import cohort_for,HORIZONS
from household_pv_window import account_hour

SCHEMA='earthship-household-captured-pv-outcome/v1'
REPORT='earthship-household-captured-pv-performance/v1'
MAX_BYTES=34*1048576
MODELS=('constant_load_pv','profiled_load_pv')
TARGET='reported_controller_DC_output_energy_after_acceptance'
FLAGS=dict(physical_calibration_qualified=False,causal_benefit_qualified=False,graduated=False,automatic_actuation=False)
MODULES=('household_pv_window.py','household_pv_outcomes.py','household_pv_score.py','household_pv_samples.py')
REQUIRED={'openhab/scripts/'+name for name in MODULES}|{'companion/earthship_energy/'+name for name in ('power_evidence.py','power_intervals.py')}


def outcome_runtime_manifest():
    import earthship_energy.power_evidence as power
    from household_profiled_outcomes import outcome_runtime_manifest as profiled_runtime
    result=profiled_runtime();root=Path(__file__).resolve().parent
    for name in MODULES:result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    for name in ('power_evidence.py','power_intervals.py'):result['companion/earthship_energy/'+name]=sha256(_read(Path(power.__file__).with_name(name),262144)).hexdigest()
    return result


def _context(energy,plan,profiled):
    out=energy['output'];storage=out['nominal_storage'];issue=instant(out['array_pv']['origin'])
    solar=cohort_for(energy,plan);current=out['current_flows']['pv_controller_output_w'];node=plan['inputs']['snapshot']['domains']['energy']['pv_output_power_w']
    source_epoch=node['evidence']['source_epoch'];available=solar is not None and current is not None and source_epoch is not None
    cohort=None if not available else dict(prediction_target=TARGET,original_solar_cohort=solar,power_source_epoch=source_epoch,
        comparison_rule='frozen_ending_hour_means_over_identical_qualified_duration_v1')
    forecasts={name:None for name in MODELS}
    if available:
        forecasts['constant_load_pv']={str(h):_hour(storage['trajectory'],issue,h) for h in HORIZONS}
        if profiled is not None and profiled['output']['status']=='conditional_nominal_simulation':
            forecasts['profiled_load_pv']={str(h):_hour(profiled['output']['profiled_storage']['trajectory'],issue,h) for h in HORIZONS}
    return dict(issued_at=issue.isoformat(),cohort=cohort,source_epoch=source_epoch,current_pv_w=current if available else None,
        hourly_predictions_kwh=forecasts,profiled_model_artifact_sha256=None if profiled is None or profiled['inputs']['load_source'] is None else profiled['inputs']['load_source']['artifact']['artifact_sha256'])


def _hour(trajectory,issue,h):
    row=trajectory[h-1]
    if instant(row['at'])!=issue+timedelta(hours=h):raise ValueError('matched original captured-PV target required')
    previous=0 if h==1 else trajectory[h-2]['cumulative_modeled_captured_pv_kwh']
    value=row['cumulative_modeled_captured_pv_kwh']-previous
    if not math.isfinite(value) or value<0:raise ValueError('nonnegative original captured energy required')
    return value


def _output(context,sources,assessed):
    issue=instant(context['issued_at']);rows={};available=context['cohort'] is not None
    for h in HORIZONS:
        key=str(h);end=issue+timedelta(hours=h);start=end-timedelta(hours=1);source=sources.get(key);mature=assessed>=end+timedelta(minutes=5)
        row=dict(horizon_hours=h,window_start=start.isoformat(),target_at=end.isoformat(),status='not_mature',reason=None,
            actual_known_controller_dc_kwh=None,covered_seconds=None,missing_seconds=None,coverage=None,predictions_kwh=None,errors_kwh=None,absolute_errors_kwh=None)
        account=None
        if source is not None:
            if not mature:raise ValueError('immature PV hour supplied outcome')
            account=account_hour(source,assessed_at=assessed,start=start,end=end,source_epoch=context['source_epoch'])
        if mature:
            if not available:row.update(status='scenario_or_reference_unavailable',reason='original_captured_scenario_or_PV_reference_unavailable')
            elif account is None:row.update(status='pending_source',reason='controller_output_hour_required')
            elif account['status']!='accounted':row.update(status='source_unavailable',reason=account['reason'])
            else:
                row.update(actual_known_controller_dc_kwh=account['known_controller_dc_kwh'],**{k:account[k] for k in ('covered_seconds','missing_seconds','coverage')})
                if account['coverage']<.99:row.update(status='insufficient_coverage',reason='qualified_hour_coverage_required')
                else:
                    fraction=account['covered_seconds']/3600
                    predictions={name:values[key]*fraction for name,values in context['hourly_predictions_kwh'].items() if values is not None}
                    predictions['current_pv']=context['current_pv_w']*account['covered_seconds']/3600000
                    errors={name:value-account['known_controller_dc_kwh'] for name,value in predictions.items()}
                    row.update(status='scored',reason=None,predictions_kwh=predictions,errors_kwh=errors,absolute_errors_kwh={k:abs(v) for k,v in errors.items()})
        rows[key]=row
    return dict(cohort=context['cohort'],cohort_id=None if context['cohort'] is None else identity(context['cohort']),prediction_context=context,by_horizon=rows,
        prediction_target=TARGET,prediction_basis='provisional_captured_DC_scenario_with_assumed_losses_and_acceptance',
        evaluation_scope='ending_hour_at_lead_time_over_identical_qualified_covered_intervals',
        potential_array_accuracy='unavailable_unmatched_meter_scope',**FLAGS)


def seal_pv_outcomes(*,energy_receipt,plan_receipt,hour_sources,assessed_at,runtime_manifest,energy_runtime_manifest,
                     profiled_receipt=None,profiled_runtime_manifest=None,load_runtime_manifest=None):
    energy=replay_energy_forecast(energy_receipt,plan_receipt=plan_receipt,runtime_manifest=energy_runtime_manifest)
    profiled=None
    if profiled_receipt is not None:
        from household_profiled_forecast import replay_profiled_forecast
        profiled=replay_profiled_forecast(profiled_receipt,energy_receipt=energy,plan_receipt=plan_receipt,runtime_manifest=profiled_runtime_manifest,
            energy_runtime_manifest=energy_runtime_manifest,load_runtime_manifest=load_runtime_manifest)
    runtime=_runtime_manifest(runtime_manifest);assessed=utc(assessed_at)
    if not REQUIRED<=set(runtime):raise ValueError('complete captured-PV outcome runtime required')
    if assessed<instant(energy['inputs']['assessed_at']):raise ValueError('outcome assessment precedes original decision')
    if not isinstance(hour_sources,dict) or not set(hour_sources)<={str(h) for h in HORIZONS}:raise ValueError('closed original PV hour map required')
    context=_context(energy,plan_receipt,profiled);sources=loads(canonical(hour_sources))
    pins={}
    for name,value in (('energy',energy),('plan',plan_receipt),('profiled',profiled)):
        pins[name+'_document_sha256']=None if value is None else identity(value)
        pins[name+'_receipt_sha256']=None if value is None else value['receipt_sha256']
    value=dict(schema=SCHEMA,inputs=dict(**pins,hour_sources=sources,assessed_at=assessed.isoformat()),runtime_manifest=runtime,output=_output(context,sources,assessed))
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original PV outcome required')
    return loads(canonical(value))


def validate_prediction_context(context,*,assessed,profiled_document_sha256):
    from household.evidence import digest
    if not isinstance(context,dict) or set(context)!={'issued_at','cohort','source_epoch','current_pv_w','hourly_predictions_kwh','profiled_model_artifact_sha256'}:raise ValueError('closed original prediction context required')
    if instant(context['issued_at'])>assessed:raise ValueError('future original prediction refused')
    if context['source_epoch'] is not None:epoch(context['source_epoch'])
    if context['profiled_model_artifact_sha256'] is not None:digest(context['profiled_model_artifact_sha256'])
    predictions=context['hourly_predictions_kwh']
    if not isinstance(predictions,dict) or set(predictions)!=set(MODELS):raise ValueError('closed original PV scenario map required')
    for rows in predictions.values():
        if rows is not None and (not isinstance(rows,dict) or set(rows)!={str(h) for h in HORIZONS} or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100000 for v in rows.values())):
            raise ValueError('bounded original PV predictions required')
    current=context['current_pv_w']
    if context['cohort'] is not None and (current is None or type(current) not in (int,float) or not math.isfinite(current) or not 0<=current<=4294967294 or predictions['constant_load_pv'] is None):raise ValueError('matched original PV reference required')
    cohort=context['cohort']
    if cohort is None:
        if current is not None or any(v is not None for v in predictions.values()):raise ValueError('unavailable PV context supplied predictions')
    else:
        from household_solar_outcomes import _cohort
        if (not isinstance(cohort,dict) or set(cohort)!={'prediction_target','original_solar_cohort','power_source_epoch','comparison_rule'} or
            cohort['prediction_target']!=TARGET or cohort['power_source_epoch']!=context['source_epoch'] or
            cohort['comparison_rule']!='frozen_ending_hour_means_over_identical_qualified_duration_v1'):
            raise ValueError('closed original captured-PV cohort required')
        _cohort(cohort['original_solar_cohort']);epoch(cohort['power_source_epoch'])
    artifact=context['profiled_model_artifact_sha256']
    if profiled_document_sha256 is None and (artifact is not None or predictions['profiled_load_pv'] is not None):raise ValueError('profiled prediction lacks original document')
    if predictions['profiled_load_pv'] is not None and artifact is None:raise ValueError('profiled prediction lacks original model identity')
    return context


def validate_score(value):
    from household.evidence import digest
    if (not isinstance(value,dict) or set(value)!={'schema','inputs','runtime_manifest','output','receipt_sha256'} or value['schema']!=SCHEMA or
        len(canonical(value))>MAX_BYTES or identity({k:v for k,v in value.items() if k!='receipt_sha256'})!=value['receipt_sha256']):raise ValueError('closed original captured-PV outcome required')
    runtime=_runtime_manifest(value['runtime_manifest']);inputs=value['inputs'];out=value['output']
    if not REQUIRED<=set(runtime) or not isinstance(inputs,dict) or set(inputs)!={'energy_document_sha256','energy_receipt_sha256','plan_document_sha256','plan_receipt_sha256','profiled_document_sha256','profiled_receipt_sha256','hour_sources','assessed_at'}:
        raise ValueError('closed original PV score context required')
    for name in ('energy','plan','profiled'):
        for suffix in ('document_sha256','receipt_sha256'):
            pin=inputs[name+'_'+suffix]
            if name!='profiled' or pin is not None:digest(pin)
    if (inputs['profiled_document_sha256'] is None)!=(inputs['profiled_receipt_sha256'] is None):raise ValueError('complete optional profiled pins required')
    sources=inputs['hour_sources']
    if not isinstance(sources,dict) or not set(sources)<={str(h) for h in HORIZONS}:raise ValueError('closed original PV hour map required')
    context=validate_prediction_context(out['prediction_context'],assessed=instant(inputs['assessed_at']),profiled_document_sha256=inputs['profiled_document_sha256'])
    if canonical(_output(context,sources,instant(inputs['assessed_at'])))!=canonical(out):raise ValueError('original captured-PV accounting or errors differ')
    return value


def replay_pv_outcomes(receipt,**context):
    validate_score(receipt)
    if canonical(receipt['runtime_manifest'])!=canonical(context['runtime_manifest']):raise ValueError('original PV scoring runtime differs')
    value=seal_pv_outcomes(**context,hour_sources=receipt['inputs']['hour_sources'],assessed_at=instant(receipt['inputs']['assessed_at']))
    if canonical(value)!=canonical(receipt):raise ValueError('original captured-PV score replay differs')
    return value


def build_performance(scores,*,cohort,generated_at,next_mature_at):
    generated=utc(generated_at);chosen={};cohort_id=identity(cohort)
    if not isinstance(scores,(list,tuple)) or len(scores)>192:raise ValueError('bounded original PV samples required')
    for score in scores:
        from household_pv_samples import SCHEMA as SAMPLE,validate_sample
        (validate_sample if score.get('schema')==SAMPLE else validate_score)(score)
        if score.get('schema')==SAMPLE and instant(score['verified_at'])>generated:raise ValueError('future verified PV sample refused')
        out=score['output'];issue=instant(out['prediction_context']['issued_at']);assessed=instant(score['inputs']['assessed_at'])
        if assessed>generated:raise ValueError('future original PV assessment refused')
        if out['cohort_id']!=cohort_id or issue<generated-timedelta(days=7):continue
        key=issue.replace(minute=0,second=0,microsecond=0);old=chosen.get(key)
        if old is None or (issue,-assessed.timestamp())<(instant(old['output']['prediction_context']['issued_at']),-instant(old['inputs']['assessed_at']).timestamp()):chosen[key]=score
    by={};all_days=set();targets=[];zone=ZoneInfo('America/Denver')
    for h in HORIZONS:
        models={};key=str(h)
        for name in MODELS:
            attempted=[];pairs=[];days=set()
            for score in chosen.values():
                context=score['output']['prediction_context'];row=score['output']['by_horizon'][key]
                if context['hourly_predictions_kwh'][name] is None or row['status']=='not_mature':continue
                attempted.append(row)
                if row['status']=='scored':
                    pairs.append(row);day=instant(context['issued_at']).astimezone(zone).date().isoformat();days.add(day);all_days.add(day);targets.append(instant(row['target_at']))
            n=len(pairs);errors=[row['errors_kwh'][name] for row in pairs];base=[row['errors_kwh']['current_pv'] for row in pairs]
            rmse=None if not n else math.sqrt(math.fsum(v*v for v in errors)/n);brmse=None if not n else math.sqrt(math.fsum(v*v for v in base)/n)
            models[name]=dict(count=n,attempted_count=len(attempted),unique_origin_days=len(days),mae_kwh=None if not n else math.fsum(abs(v) for v in errors)/n,
                bias_kwh=None if not n else math.fsum(errors)/n,rmse_kwh=rmse,persistence_mae_kwh=None if not n else math.fsum(abs(v) for v in base)/n,
                persistence_rmse_kwh=brmse,rmse_skill=None if not brmse else 1-rmse/brmse,
                last_target_at=None if not pairs else max(instant(row['target_at']) for row in pairs).isoformat())
        by[key]=dict(horizon_hours=h,models=models)
    if next_mature_at is not None and utc(next_mature_at)<generated:next_mature_at=generated
    result=dict(schema=REPORT,generated_at=generated.isoformat(),valid_until=(generated+timedelta(minutes=30)).isoformat(),cohort=cohort,cohort_id=cohort_id,
        by_horizon=by,unique_origin_days=len(all_days),last_target_at=None if not targets else max(targets).isoformat(),next_mature_at=None if next_mature_at is None else utc(next_mature_at).isoformat(),
        prediction_target=TARGET,evaluation_scope='provisional_scenarios_under_actual_behavior_not_causal_benefit',
        sampling_basis='first_qualified_original_per_UTC_hour_with_independent_Denver_origin_days',potential_array_accuracy='unavailable_unmatched_meter_scope',**FLAGS)
    result['report_sha256']=identity(result);return loads(canonical(result))


def main(argv=None):
    import argparse,gzip,sys
    from io import BytesIO
    from household_observation import _private_file
    from household_profiled_forecast import profiled_runtime_manifest
    from household_ac_load_artifact import runtime_manifest as load_runtime
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('receipt','energy','plan'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--profiled',type=Path);args=parser.parse_args(argv)
    try:
        paths=[(args.receipt,MAX_BYTES+65536),(args.energy,262144),(args.plan,2097152)]+([] if args.profiled is None else [(args.profiled,262144)])
        originals=[(path,limit,_private_file(path,limit)) for path,limit in paths];raw=originals[0][2][0]
        if raw.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('bounded expanded PV score required')
        receipt=loads(raw);energy,plan=[loads(row[2][0]) for row in originals[1:3]];profiled=None if len(originals)==3 else loads(originals[3][2][0])
        runtime=outcome_runtime_manifest();er=forecast_runtime_manifest();pr=None if profiled is None else profiled_runtime_manifest();lr=None if profiled is None else ({} if profiled['inputs']['load_source'] is None else load_runtime())
        if instant(receipt['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future PV outcome refused')
        value=replay_pv_outcomes(receipt,energy_receipt=energy,plan_receipt=plan,runtime_manifest=runtime,energy_runtime_manifest=er,profiled_receipt=profiled,profiled_runtime_manifest=pr,load_runtime_manifest=lr)
        if (outcome_runtime_manifest()!=runtime or forecast_runtime_manifest()!=er or profiled is not None and (profiled_runtime_manifest()!=pr or lr and load_runtime()!=lr) or
            any(_private_file(path,limit)!=original for path,limit,original in originals)):raise ValueError('PV replay inputs changed')
        sys.stdout.buffer.write(canonical(value)+b'\n');return 0
    except Exception:
        print('Captured-PV replay refused: invalid or changed original inputs.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
