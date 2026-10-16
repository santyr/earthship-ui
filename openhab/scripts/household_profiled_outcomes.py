"""Matched as-issued AC demand and conditional storage outcomes; no actuation."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import math
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,digest
from household.planning import _runtime_manifest
from household_snapshot import _read
from household_profiled_forecast import replay_profiled_forecast,forecast_cohort
from household_solar_outcomes import seal_energy_outcomes,validate_score as validate_reference,energy_outcome_runtime_manifest,HORIZONS
from household_ac_load_window import account_hour
from household_ac_load_model import POLICY

SCHEMA='earthship-household-profiled-energy-outcome/v1'
MAX_BYTES=5*1048576
SOC_MODELS=('profiled_load_pv','constant_load_pv','constant_power','hold_soc')
LOAD_MODELS=('profiled_load','current_load')
REQUIRED={'openhab/scripts/'+name for name in ('household_profiled_outcomes.py','household_ac_load_window.py','household_profiled_forecast.py','household_profiled_storage.py','household_profiled_score.py','household_profiled_state.py','household_profiled_samples.py')}
FLAGS=dict(physical_calibration_qualified=False,causal_benefit_qualified=False,graduated=False,automatic_actuation=False)


def outcome_runtime_manifest():
    result=energy_outcome_runtime_manifest();root=Path(__file__).resolve().parent
    for name in REQUIRED:result[name]=sha256(_read(root/Path(name).name,262144)).hexdigest()
    return result


def _number(value,low,high):return type(value) in (int,float) and math.isfinite(value) and low<=value<=high


def _pairs(origin,reference,hour_sources,assessed):
    issue=instant(reference['output']['by_horizon']['1']['target_at'])-timedelta(hours=1);load_rows={};soc_rows={}
    available=origin is not None
    for h in HORIZONS:
        key=str(h);target=issue+timedelta(hours=h);base=reference['output']['by_horizon'][key];source=hour_sources.get(key);mature=assessed>=target+timedelta(minutes=5)
        prediction=None if origin is None else origin['predictions'][key]
        row=dict(horizon_hours=h,window_start=(target-timedelta(hours=1)).isoformat(),target_at=target.isoformat(),status='not_mature',reason=None,
            actual_known_ac_kwh=None,covered_seconds=None,missing_seconds=None,coverage=None,predictions_kwh=None,errors_kwh=None,absolute_errors_kwh=None)
        account=None
        if source is not None:
            if not mature:raise ValueError('immature load hour supplied evidence')
            account=account_hour(source,assessed_at=assessed,start=target-timedelta(hours=1),end=target)
        if mature:
            if not available:row.update(status='scenario_or_reference_unavailable',reason='matched_forecasts_unavailable')
            elif account is None:row.update(status='pending_source',reason='hour_source_required')
            elif account['status']!='accounted':row.update(status='source_unavailable',reason=account['reason'])
            else:
                row.update(actual_known_ac_kwh=account['known_ac_kwh'],covered_seconds=account['covered_seconds'],missing_seconds=account['missing_seconds'],coverage=account['coverage'])
                if account['coverage']<POLICY['minimum_coverage']:row.update(status='insufficient_coverage',reason='qualified_hour_coverage_required')
                else:
                    # Both frozen hourly means are integrated over exactly the
                    # same observed duration. Unobserved time supplies no zeros.
                    predictions=dict(profiled_load=prediction['load_mean_ac_w']*account['covered_seconds']/3600000,current_load=prediction['current_load_w']*account['covered_seconds']/3600000)
                    errors={k:v-account['known_ac_kwh'] for k,v in predictions.items()}
                    row.update(status='scored',reason=None,predictions_kwh=predictions,errors_kwh=errors,absolute_errors_kwh={k:abs(v) for k,v in errors.items()})
        load_rows[key]=row
        soc=dict(horizon_hours=h,target_at=target.isoformat(),status=base['status'],reason=base['reason'],actual_soc_pct=None,predictions_soc_pct=None,errors_soc_pct=None,absolute_errors_soc_pct=None)
        if mature and not available:soc.update(status='scenario_or_reference_unavailable',reason='matched_forecasts_unavailable')
        elif available and base['status']=='scored':
            values=dict(profiled_load_pv=prediction['profiled_soc_pct'],constant_load_pv=base['predictions_soc_pct']['pv_load_scenario'],constant_power=base['predictions_soc_pct']['constant_power'],hold_soc=base['predictions_soc_pct']['hold_soc'])
            errors={k:v-base['actual_soc_pct'] for k,v in values.items()}
            soc.update(actual_soc_pct=base['actual_soc_pct'],predictions_soc_pct=values,errors_soc_pct=errors,absolute_errors_soc_pct={k:abs(v) for k,v in errors.items()})
        soc_rows[key]=soc
    return load_rows,soc_rows


def cohort_for_profiled(forecast,energy_receipt,plan_receipt):
    return forecast_cohort(forecast,energy_receipt,plan_receipt)


def seal_profiled_outcomes(*,profiled_receipt,energy_receipt,plan_receipt,hour_sources,endpoint_sources,assessed_at,runtime_manifest,forecast_runtime_manifest,energy_runtime_manifest,load_runtime_manifest):
    forecast=replay_profiled_forecast(profiled_receipt,energy_receipt=energy_receipt,plan_receipt=plan_receipt,runtime_manifest=forecast_runtime_manifest,
        energy_runtime_manifest=energy_runtime_manifest,load_runtime_manifest=load_runtime_manifest)
    runtime=_runtime_manifest(runtime_manifest);assessed=utc(assessed_at)
    if not REQUIRED<=set(runtime):raise ValueError('complete profiled outcome runtime required')
    reference=seal_energy_outcomes(forecast_receipt=energy_receipt,plan_receipt=plan_receipt,endpoint_sources=endpoint_sources,assessed_at=assessed,
        forecast_runtime_manifest=energy_runtime_manifest,outcome_runtime_manifest=runtime)
    if not isinstance(hour_sources,dict) or not set(hour_sources)<={str(h) for h in HORIZONS}:raise ValueError('closed original load hour map required')
    sources=loads(canonical(hour_sources));out=forecast['output'];origin=cohort=None
    if out['status']=='conditional_nominal_simulation' and reference['output']['cohort'] is not None:
        source=forecast['inputs']['load_source'];profile=source['artifact']['profile']
        cohort=cohort_for_profiled(forecast,energy_receipt,plan_receipt)
        origin=dict(issued_at=out['issued_at'],model_artifact_sha256=source['artifact']['artifact_sha256'],model_sha256=profile['model_sha256'],predictions={})
        for h in HORIZONS:
            load=out['load_forecast']['trajectory'][h-1];storage=out['profiled_storage']['trajectory'][h-1]
            if load['at']!=storage['at'] or instant(load['at'])!=instant(out['issued_at'])+timedelta(hours=h):raise ValueError('matched original profiled target required')
            origin['predictions'][str(h)]=dict(load_mean_ac_w=load['mean_ac_w'],current_load_w=out['current_load_persistence_w'],profiled_soc_pct=storage['nominal_soc_pct'])
    load_rows,soc_rows=_pairs(origin,reference,sources,assessed)
    value=dict(schema=SCHEMA,inputs=dict(profiled_receipt_sha256=forecast['receipt_sha256'],profiled_document_sha256=identity(forecast),
        energy_receipt_sha256=energy_receipt['receipt_sha256'],plan_receipt_sha256=plan_receipt['receipt_sha256'],hour_sources=sources,assessed_at=assessed.isoformat()),
        runtime_manifest=runtime,reference_score=reference,output=dict(cohort=cohort,cohort_id=None if cohort is None else identity(cohort),origin=origin,
            load_by_horizon=load_rows,soc_by_horizon=soc_rows,load_evaluation='hour_ending_at_lead_time_over_qualified_covered_intervals',
            pv_energy_accuracy='unavailable_unmatched_meter_scope',**FLAGS))
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original profiled outcome required')
    return loads(canonical(value))


def validate_score(value):
    if (not isinstance(value,dict) or set(value)!={'schema','inputs','runtime_manifest','reference_score','output','receipt_sha256'} or value['schema']!=SCHEMA or
        len(canonical(value))>MAX_BYTES or identity({k:v for k,v in value.items() if k!='receipt_sha256'})!=value['receipt_sha256']):raise ValueError('closed original profiled outcome required')
    inputs=value['inputs'];out=value['output'];runtime=_runtime_manifest(value['runtime_manifest']);ref=validate_reference(value['reference_score'])
    if (not REQUIRED<=set(runtime) or canonical(ref['outcome_runtime_manifest'])!=canonical(runtime) or
        not isinstance(inputs,dict) or set(inputs)!={'profiled_receipt_sha256','profiled_document_sha256','energy_receipt_sha256','plan_receipt_sha256','hour_sources','assessed_at'}):
        raise ValueError('closed original profiled score context required')
    for k in ('profiled_receipt_sha256','profiled_document_sha256','energy_receipt_sha256','plan_receipt_sha256'):digest(inputs[k])
    if inputs['energy_receipt_sha256']!=ref['inputs']['forecast_receipt_sha256'] or inputs['plan_receipt_sha256']!=ref['inputs']['plan_receipt_sha256'] or inputs['assessed_at']!=ref['inputs']['assessed_at']:
        raise ValueError('original reference score binding differs')
    if (not isinstance(out,dict) or set(out)!={'cohort','cohort_id','origin','load_by_horizon','soc_by_horizon','load_evaluation','pv_energy_accuracy',*FLAGS} or
        any(out[k] is not False for k in FLAGS) or out['load_evaluation']!='hour_ending_at_lead_time_over_qualified_covered_intervals' or out['pv_energy_accuracy']!='unavailable_unmatched_meter_scope' or
        not isinstance(inputs['hour_sources'],dict) or not set(inputs['hour_sources'])<={str(h) for h in HORIZONS}):raise ValueError('closed observational profiled output required')
    origin=out['origin'];cohort=out['cohort']
    if cohort is None:
        if origin is not None or out['cohort_id'] is not None:raise ValueError('unavailable load scenario supplied origin')
    else:
        if (not isinstance(cohort,dict) or set(cohort)!={'evaluation_scope','original_solar_cohort','profiled_runtime_sha256','load_algorithm_runtime_sha256','load_policy_sha256'} or
            cohort['evaluation_scope']!='rolling_as_issued_model_versions' or cohort['original_solar_cohort']!=ref['output']['cohort'] or identity(cohort)!=out['cohort_id']):raise ValueError('closed rolling model cohort required')
        for k in ('profiled_runtime_sha256','load_algorithm_runtime_sha256','load_policy_sha256'):digest(cohort[k])
        if not isinstance(origin,dict) or set(origin)!={'issued_at','model_artifact_sha256','model_sha256','predictions'} or origin['issued_at']!=ref['output']['origin']['issued_at']:
            raise ValueError('original profiled prediction clock differs')
        digest(origin['model_artifact_sha256']);digest(origin['model_sha256'])
        if not isinstance(origin['predictions'],dict) or set(origin['predictions'])!={str(h) for h in HORIZONS}:raise ValueError('complete original profiled predictions required')
        for prediction in origin['predictions'].values():
            if (not isinstance(prediction,dict) or set(prediction)!={'load_mean_ac_w','current_load_w','profiled_soc_pct'} or
                not _number(prediction['load_mean_ac_w'],0,20000) or not _number(prediction['current_load_w'],0,20000) or not _number(prediction['profiled_soc_pct'],0,100)):
                raise ValueError('bounded original profiled predictions required')
    load,soc=_pairs(origin,ref,inputs['hour_sources'],instant(inputs['assessed_at']))
    if canonical(load)!=canonical(out['load_by_horizon']) or canonical(soc)!=canonical(out['soc_by_horizon']):raise ValueError('matched original profiled outcome differs')
    return value


def replay_profiled_outcomes(receipt,**context):
    validate_score(receipt)
    if canonical(receipt['runtime_manifest'])!=canonical(context['runtime_manifest']):raise ValueError('original profiled outcome runtime differs')
    result=seal_profiled_outcomes(**context,hour_sources=receipt['inputs']['hour_sources'],endpoint_sources=receipt['reference_score']['inputs']['endpoint_sources'],assessed_at=instant(receipt['inputs']['assessed_at']))
    if canonical(result)!=canonical(receipt):raise ValueError('original profiled outcome replay differs')
    return result


def main(argv=None):
    import argparse,gzip,sys
    from datetime import datetime,timezone
    from io import BytesIO
    from household_observation import _private_file
    from household_profiled_forecast import profiled_runtime_manifest
    from household_energy_forecast import forecast_runtime_manifest
    from household_ac_load_artifact import runtime_manifest as model_runtime
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('receipt','forecast','energy','plan'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        originals=[(path,maximum,_private_file(path,maximum)) for path,maximum in ((args.receipt,MAX_BYTES+65536),(args.forecast,262144),(args.energy,262144),(args.plan,2097152))]
        raw=originals[0][2][0]
        if raw.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('bounded original profile score required')
        receipt=loads(raw);forecast,energy,plan=[loads(value[0]) for _,_,value in originals[1:]]
        runtime=outcome_runtime_manifest();fr=profiled_runtime_manifest();er=forecast_runtime_manifest();lr={} if forecast['inputs']['load_source'] is None else model_runtime()
        if instant(receipt['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future profile outcome assessment refused')
        result=replay_profiled_outcomes(receipt,profiled_receipt=forecast,energy_receipt=energy,plan_receipt=plan,runtime_manifest=runtime,
            forecast_runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=lr)
        if (outcome_runtime_manifest()!=runtime or profiled_runtime_manifest()!=fr or forecast_runtime_manifest()!=er or lr and model_runtime()!=lr or
            any(_private_file(path,maximum)!=value for path,maximum,value in originals)):raise ValueError('original profile score replay inputs changed')
        sys.stdout.buffer.write(canonical(result)+b'\n');return 0
    except Exception:
        print('Profiled outcome replay refused: invalid or changed original inputs.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
