"""Compact arithmetic-checked admissions tied to retained full PV outcome originals."""
from datetime import timedelta
import math
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import digest,utc
from household_pv_outcomes import validate_score,validate_prediction_context,MODELS,FLAGS,HORIZONS,TARGET

SCHEMA='earthship-household-captured-pv-verified-sample/v1'
MAX_BYTES=32768


def summarize_verified_score(score,*,verified_at):
    score=validate_score(score);verified=utc(verified_at)
    if verified<instant(score['inputs']['assessed_at']):raise ValueError('PV verification precedes outcome assessment')
    value=dict(schema=SCHEMA,verified_at=verified.isoformat(),score_document_sha256=identity(score),score_receipt_sha256=score['receipt_sha256'],
        runtime_sha256=identity(score['runtime_manifest']),inputs={k:v for k,v in score['inputs'].items() if k!='hour_sources'},
        hour_source_pins={k:v['source_sha256'] for k,v in score['inputs']['hour_sources'].items()},output=score['output'])
    value['sample_sha256']=identity(value);return validate_sample(loads(canonical(value)))


def number(v,lo=0,hi=1e12):return type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi

def same(a,b):
    if isinstance(b,dict):return isinstance(a,dict) and set(a)==set(b) and all(same(a[k],v) for k,v in b.items())
    return number(a,-1e12) and math.isclose(a,b,rel_tol=0,abs_tol=1e-10)


def validate_sample(value):
    if (not isinstance(value,dict) or set(value)!={'schema','verified_at','score_document_sha256','score_receipt_sha256','runtime_sha256','inputs','hour_source_pins','output','sample_sha256'} or
        value['schema']!=SCHEMA or len(canonical(value))>MAX_BYTES or identity({k:v for k,v in value.items() if k!='sample_sha256'})!=value['sample_sha256']):raise ValueError('closed verified PV sample required')
    for k in ('score_document_sha256','score_receipt_sha256','runtime_sha256'):digest(value[k])
    inputs=value['inputs'];out=value['output'];context=out['prediction_context'];assessed=instant(inputs['assessed_at']);issue=instant(context['issued_at'])
    if issue>assessed or assessed>instant(value['verified_at']):raise ValueError('original PV sample clocks differ')
    if set(inputs)!={'energy_document_sha256','energy_receipt_sha256','plan_document_sha256','plan_receipt_sha256','profiled_document_sha256','profiled_receipt_sha256','assessed_at'}:raise ValueError('closed verified original pins required')
    for k,v in inputs.items():
        if k!='assessed_at' and (not k.startswith('profiled_') or v is not None):digest(v)
    if (inputs['profiled_document_sha256'] is None)!=(inputs['profiled_receipt_sha256'] is None):raise ValueError('complete optional original pins required')
    validate_prediction_context(context,assessed=assessed,profiled_document_sha256=inputs['profiled_document_sha256'])
    pins=value['hour_source_pins']
    if not isinstance(pins,dict) or not set(pins)<={str(h) for h in HORIZONS}:raise ValueError('closed original PV source pins required')
    for pin in pins.values():digest(pin)
    if (set(out)!={'cohort','cohort_id','prediction_context','by_horizon','prediction_target','prediction_basis','evaluation_scope','potential_array_accuracy',*FLAGS} or
        any(out[k] is not False for k in FLAGS) or out['cohort']!=context['cohort'] or out['cohort_id']!=(None if context['cohort'] is None else identity(context['cohort'])) or
        out['prediction_target']!=TARGET or out['prediction_basis']!='provisional_captured_DC_scenario_with_assumed_losses_and_acceptance' or
        out['evaluation_scope']!='ending_hour_at_lead_time_over_identical_qualified_covered_intervals' or out['potential_array_accuracy']!='unavailable_unmatched_meter_scope' or
        not isinstance(out['by_horizon'],dict) or set(out['by_horizon'])!={str(h) for h in HORIZONS}):raise ValueError('closed observational PV sample required')
    if (set(context)!={'issued_at','cohort','source_epoch','current_pv_w','hourly_predictions_kwh','profiled_model_artifact_sha256'} or
        not isinstance(context['hourly_predictions_kwh'],dict) or set(context['hourly_predictions_kwh'])!=set(MODELS)):raise ValueError('closed original PV predictions required')
    for predictions in context['hourly_predictions_kwh'].values():
        if predictions is not None and (not isinstance(predictions,dict) or set(predictions)!={str(h) for h in HORIZONS} or any(not number(v,0,100000) for v in predictions.values())):raise ValueError('bounded original hourly means required')
    for h in HORIZONS:
        key=str(h);row=out['by_horizon'][key];end=issue+timedelta(hours=h);mature=assessed>=end+timedelta(minutes=5)
        if (set(row)!={'horizon_hours','window_start','target_at','status','reason','actual_known_controller_dc_kwh','covered_seconds','missing_seconds','coverage','predictions_kwh','errors_kwh','absolute_errors_kwh'} or
            type(row['horizon_hours']) is not int or row['horizon_hours']!=h or instant(row['window_start'])!=end-timedelta(hours=1) or instant(row['target_at'])!=end):raise ValueError('original verified PV target differs')
        status=row['status'];numbers=('actual_known_controller_dc_kwh','covered_seconds','missing_seconds','coverage','predictions_kwh','errors_kwh','absolute_errors_kwh')
        if status=='not_mature':
            if mature or row['reason'] is not None or key in pins:raise ValueError('immature PV sample supplied outcome')
        elif not mature:raise ValueError('terminal PV sample precedes maturity')
        elif status in ('scored','insufficient_coverage'):
            covered=row['covered_seconds'];actual=row['actual_known_controller_dc_kwh']
            if (key not in pins or context['cohort'] is None or not number(covered,0,3600) or not number(row['missing_seconds'],0,3600) or
                not same(covered+row['missing_seconds'],3600) or not same(row['coverage'],covered/3600) or not number(actual,0,4294967294*covered/3600000) or
                (row['coverage']>=.99)!=(status=='scored')):raise ValueError('original PV sample coverage differs')
            if status=='scored':
                if context['hourly_predictions_kwh']['constant_load_pv'] is None or not number(context['current_pv_w'],0,4294967294):raise ValueError('matched original PV scenario/reference required')
                predictions={name:values[key]*covered/3600 for name,values in context['hourly_predictions_kwh'].items() if values is not None};predictions['current_pv']=context['current_pv_w']*covered/3600000
                errors={name:v-actual for name,v in predictions.items()}
                if row['reason'] is not None or not same(row['predictions_kwh'],predictions) or not same(row['errors_kwh'],errors) or not same(row['absolute_errors_kwh'],{k:abs(v) for k,v in errors.items()}):raise ValueError('original verified PV errors differ')
                continue
            if row['reason']!='qualified_hour_coverage_required' or any(row[k] is not None for k in ('predictions_kwh','errors_kwh','absolute_errors_kwh')):raise ValueError('sparse sample supplied PV accuracy')
            continue
        elif status=='pending_source':
            if key in pins or context['cohort'] is None or row['reason']!='controller_output_hour_required':raise ValueError('pending PV sample differs')
        elif status=='source_unavailable':
            if key not in pins or context['cohort'] is None or row['reason'] not in ('ambiguous_source_sequence','original_power_epoch_differs','original_power_epoch_unavailable'):raise ValueError('unavailable PV source differs')
        elif status=='scenario_or_reference_unavailable':
            if context['cohort'] is not None or row['reason']!='original_captured_scenario_or_PV_reference_unavailable':raise ValueError('unavailable PV prediction differs')
        else:raise ValueError('supported original PV sample status required')
        if any(row[k] is not None for k in numbers):raise ValueError('unknown PV sample supplied numbers')
    return value
