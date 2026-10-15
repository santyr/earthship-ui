"""Compact verified samples and rolling as-issued profile comparisons.

The owned scorer pins each sample to its complete original score file. Subsequent
report refreshes check those file bytes and this compact arithmetic, avoiding
repeated parsing of all historical electrical receipts.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo
import math
from household.codec import canonical,loads,identity
from household.evidence import utc,digest
from household.control_contracts import instant
from household_profiled_outcomes import validate_score,SOC_MODELS,LOAD_MODELS,FLAGS,HORIZONS,_number
from household_ac_load_model import POLICY

SCHEMA='earthship-profiled-energy-verified-sample/v1'
REPORT='earthship-household-profiled-energy-performance/v1'
FIELDS={'schema','score_document_sha256','score_receipt_sha256','profiled_receipt_sha256','score_assessed_at','verified_at',
    'reference_origin','hour_source_pins','endpoint_source_pins','output','sample_sha256'}


def summarize_verified_score(score,*,verified_at):
    score=validate_score(score);at=utc(verified_at)
    if at<instant(score['inputs']['assessed_at']):raise ValueError('sample verification precedes original score')
    value=dict(schema=SCHEMA,score_document_sha256=identity(score),score_receipt_sha256=score['receipt_sha256'],profiled_receipt_sha256=score['inputs']['profiled_receipt_sha256'],
        score_assessed_at=score['inputs']['assessed_at'],verified_at=at.isoformat(),reference_origin=score['reference_score']['output']['origin'],
        hour_source_pins={k:v['source_sha256'] for k,v in score['inputs']['hour_sources'].items()},
        endpoint_source_pins={k:v['source_sha256'] for k,v in score['reference_score']['inputs']['endpoint_sources'].items()},output=score['output'])
    value['sample_sha256']=identity(value);return validate_sample(loads(canonical(value)))


def _same(actual,expected):
    if isinstance(expected,dict):
        return isinstance(actual,dict) and set(actual)==set(expected) and all(_same(actual[k],v) for k,v in expected.items())
    return type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=0,abs_tol=1e-10)


def validate_sample(value):
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or len(canonical(value))>32768 or
        identity({k:v for k,v in value.items() if k!='sample_sha256'})!=value['sample_sha256']):raise ValueError('closed original verified profile sample required')
    for k in ('score_document_sha256','score_receipt_sha256','profiled_receipt_sha256'):digest(value[k])
    assessed=instant(value['score_assessed_at']);verified=instant(value['verified_at'])
    if verified<assessed:raise ValueError('sample verification precedes original score')
    for key in ('hour_source_pins','endpoint_source_pins'):
        refs=value[key]
        if not isinstance(refs,dict) or not set(refs)<={str(h) for h in HORIZONS}:raise ValueError('bounded original outcome pins required')
        for pin in refs.values():digest(pin)
    out=value['output'];origin=out['origin'];cohort=out['cohort'];reference=value['reference_origin']
    if (not isinstance(out,dict) or set(out)!={'cohort','cohort_id','origin','load_by_horizon','soc_by_horizon','load_evaluation','pv_energy_accuracy',*FLAGS} or
        any(out[k] is not False for k in FLAGS) or out['load_evaluation']!='hour_ending_at_lead_time_over_qualified_covered_intervals' or out['pv_energy_accuracy']!='unavailable_unmatched_meter_scope'):
        raise ValueError('closed observational sample output required')
    if cohort is None:
        if origin is not None or out['cohort_id'] is not None:raise ValueError('unavailable sample supplied model origin')
    else:
        if (not isinstance(cohort,dict) or set(cohort)!={'evaluation_scope','original_solar_cohort','profiled_runtime_sha256','load_algorithm_runtime_sha256','load_policy_sha256'} or
            cohort['evaluation_scope']!='rolling_as_issued_model_versions' or identity(cohort)!=out['cohort_id']):raise ValueError('original rolling profile cohort required')
        for key in ('profiled_runtime_sha256','load_algorithm_runtime_sha256','load_policy_sha256'):digest(cohort[key])
        from household_solar_outcomes import _cohort
        _cohort(cohort['original_solar_cohort'])
        if (not isinstance(origin,dict) or set(origin)!={'issued_at','model_artifact_sha256','model_sha256','predictions'} or
            not isinstance(reference,dict) or set(reference)!={'issued_at','initial_soc_pct','predictions_by_horizon_soc_pct'} or
            origin['issued_at']!=reference['issued_at'] or not _number(reference['initial_soc_pct'],0,100)):
            raise ValueError('original profile and reference origins required')
        digest(origin['model_artifact_sha256']);digest(origin['model_sha256'])
        if instant(origin['issued_at'])>assessed or set(origin['predictions'])!={str(h) for h in HORIZONS} or set(reference['predictions_by_horizon_soc_pct'])!={str(h) for h in HORIZONS}:
            raise ValueError('complete original profile predictions required')
    for domain,models in (('load',LOAD_MODELS),('soc',SOC_MODELS)):
        rows=out[domain+'_by_horizon']
        if not isinstance(rows,dict) or set(rows)!={str(h) for h in HORIZONS}:raise ValueError('complete sample horizons required')
        for h in HORIZONS:
            key=str(h);row=rows[key];target=instant(row['target_at']);mature=assessed>=target+timedelta(minutes=5)
            common={'horizon_hours','target_at','status','reason'}
            metric={'window_start','actual_known_ac_kwh','covered_seconds','missing_seconds','coverage','predictions_kwh','errors_kwh','absolute_errors_kwh'} if domain=='load' else {'actual_soc_pct','predictions_soc_pct','errors_soc_pct','absolute_errors_soc_pct'}
            if not isinstance(row,dict) or set(row)!=common|metric or type(row['horizon_hours']) is not int or row['horizon_hours']!=h or origin is not None and target!=instant(origin['issued_at'])+timedelta(hours=h):
                raise ValueError('original sample target differs')
            if domain=='load' and instant(row['window_start'])!=target-timedelta(hours=1):raise ValueError('original sample hour differs')
            if row['status']=='not_mature':
                if mature or row['reason'] is not None or key in value['hour_source_pins' if domain=='load' else 'endpoint_source_pins']:raise ValueError('immature sample supplied outcome')
            elif not mature:raise ValueError('terminal sample precedes maturity')
            elif row['status'] not in ({'scored','pending_source','source_unavailable','scenario_or_reference_unavailable','insufficient_coverage'} if domain=='load' else {'scored','pending_source','source_unavailable','scenario_or_reference_unavailable'}):
                raise ValueError('supported sample status required')
            if row['status'] in {'scored','insufficient_coverage'}:
                if origin is None:raise ValueError('unavailable sample supplied numeric accuracy')
                prediction=origin['predictions'][key]
                if (not isinstance(prediction,dict) or set(prediction)!={'load_mean_ac_w','current_load_w','profiled_soc_pct'} or
                    not _number(prediction['load_mean_ac_w'],0,20000) or not _number(prediction['current_load_w'],0,20000) or not _number(prediction['profiled_soc_pct'],0,100)):
                    raise ValueError('bounded original sample prediction required')
                if domain=='load':
                    covered=row['covered_seconds'];missing=row['missing_seconds'];coverage=row['coverage'];actual=row['actual_known_ac_kwh']
                    if (key not in value['hour_source_pins'] or not _number(covered,0,3600) or not _number(missing,0,3600) or not _number(coverage,0,1) or
                        not _same(covered+missing,3600) or not _same(coverage,covered/3600) or not _number(actual,0,20*covered/3600)):
                        raise ValueError('original sample coverage or energy differs')
                    if (coverage>=POLICY['minimum_coverage'])!=(row['status']=='scored'):raise ValueError('sample coverage does not qualify')
                    expected=dict(profiled_load=prediction['load_mean_ac_w']*covered/3600000,current_load=prediction['current_load_w']*covered/3600000)
                    suffix='kwh'
                else:
                    if key not in value['endpoint_source_pins'] or not _number(row['actual_soc_pct'],0,100):raise ValueError('qualified sample endpoint required')
                    original=reference['predictions_by_horizon_soc_pct'][key]
                    if not isinstance(original,dict) or set(original)!={'pv_load_scenario','constant_power','hold_soc'} or any(not _number(v,0,100) for v in original.values()) or original['hold_soc']!=reference['initial_soc_pct']:
                        raise ValueError('original sample references differ')
                    expected=dict(profiled_load_pv=prediction['profiled_soc_pct'],constant_load_pv=original['pv_load_scenario'],constant_power=original['constant_power'],hold_soc=original['hold_soc'])
                    actual=row['actual_soc_pct'];suffix='soc_pct'
                if row['status']=='scored':
                    errors={k:v-actual for k,v in expected.items()}
                    if row['reason'] is not None or not _same(row['predictions_'+suffix],expected) or not _same(row['errors_'+suffix],errors) or not _same(row['absolute_errors_'+suffix],{k:abs(v) for k,v in errors.items()}):
                        raise ValueError('original verified sample arithmetic differs')
                    continue
                if row['reason']!='qualified_hour_coverage_required':raise ValueError('sample coverage reason differs')
                if any(row[k] is not None for k in ('predictions_kwh','errors_kwh','absolute_errors_kwh')):raise ValueError('sparse sample supplied accuracy')
                continue
            numeric=metric-{'window_start'}
            if any(row[k] is not None for k in numeric):raise ValueError('unknown sample supplied numeric accuracy')
    return value


def build_performance(samples,*,cohort,generated_at,next_mature_at):
    generated=utc(generated_at);cohort_id=identity(cohort);chosen={}
    if not isinstance(samples,(list,tuple)) or len(samples)>192:raise ValueError('bounded original hourly samples required')
    for item in samples:
        sample=validate_sample(item);out=sample['output']
        if instant(sample['verified_at'])>generated:raise ValueError('future verified sample refused')
        if out['cohort_id']!=cohort_id:continue
        issue=instant(out['origin']['issued_at'])
        if issue<generated-timedelta(days=7):continue
        key=issue.replace(minute=0,second=0,microsecond=0);old=chosen.get(key)
        if old is not None:
            old_issue=instant(old['output']['origin']['issued_at'])
            if issue>old_issue:continue
            if issue==old_issue:
                if sample['profiled_receipt_sha256']!=old['profiled_receipt_sha256']:raise ValueError('conflicting same-issued original profile sample')
                if instant(sample['score_assessed_at'])<=instant(old['score_assessed_at']):continue
        chosen[key]=sample
    result={};zone=ZoneInfo('America/Denver')
    for h in HORIZONS:
        domains={}
        for domain,models,suffix in (('load',LOAD_MODELS,'kwh'),('soc',SOC_MODELS,'soc_pct')):
            all_rows=[(s,s['output'][domain+'_by_horizon'][str(h)]) for s in chosen.values()]
            paired=[(s,r) for s,r in all_rows if r['status']=='scored'];count=len(paired)
            row=dict(count=count,attempted_count=sum(r['status']!='not_mature' for _,r in all_rows),
                unique_origin_days=len({instant(s['output']['origin']['issued_at']).astimezone(zone).date() for s,_ in paired}),
                model_version_count=len({s['output']['origin']['model_artifact_sha256'] for s,_ in paired}),
                mae_kwh=None,bias_kwh=None,rmse_kwh=None) if domain=='load' else dict(count=count,attempted_count=sum(r['status']!='not_mature' for _,r in all_rows),
                    unique_origin_days=len({instant(s['output']['origin']['issued_at']).astimezone(zone).date() for s,_ in paired}),model_version_count=len({s['output']['origin']['model_artifact_sha256'] for s,_ in paired}),mae_soc_pct=None,bias_soc_pct=None,rmse_soc_pct=None)
            row['status']='collecting' if count==0 else 'observed';row['excluded_count']=sum(r['status'] not in {'scored','not_mature'} for _,r in all_rows)
            if count:
                row['mae_'+suffix]={m:math.fsum(abs(r['errors_'+suffix][m]) for _,r in paired)/count for m in models}
                row['bias_'+suffix]={m:math.fsum(r['errors_'+suffix][m] for _,r in paired)/count for m in models}
                row['rmse_'+suffix]={m:math.sqrt(math.fsum(r['errors_'+suffix][m]**2 for _,r in paired)/count) for m in models}
            domains[domain]=row
        result[str(h)]=domains
    if next_mature_at is not None and not generated-timedelta(days=7)<=utc(next_mature_at)<=generated+timedelta(hours=24,minutes=5):raise ValueError('bounded next profile maturity required')
    value=dict(schema=REPORT,generated_at=generated.isoformat(),valid_until=(generated+timedelta(minutes=30)).isoformat(),cohort_id=cohort_id,
        evaluation_scope='rolling_as_issued_model_versions',model_version_count=len({s['output']['origin']['model_artifact_sha256'] for s in chosen.values()}),
        by_horizon=result,next_mature_at=None if next_mature_at is None else utc(next_mature_at).isoformat(),load_window='hour_ending_at_lead_time',
        load_coverage_policy='at_least_99_percent_both_predictions_on_identical_covered_intervals',pv_energy_accuracy='unavailable_unmatched_meter_scope',**FLAGS)
    value['report_sha256']=identity(value)
    return loads(canonical(value))
