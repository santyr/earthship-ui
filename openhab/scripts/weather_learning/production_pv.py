"""Source-bound fresh electrical fit for native-component production PV.

This reuses the declared bounded effective-gain formula on the new baseline.
It neither reuses incumbent coefficients nor grants physical/control authority.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from math import fsum
from pathlib import Path
from zoneinfo import ZoneInfo
from weather_source_files import _read
import json
from .contracts import canonical,identity,digest,instant,finite
from .evidence import utc
from .probabilistic import _Frozen,_freeze
from .probabilistic_artifacts import numerical_environment
from .production_model_admission import _authorization
from .weights import target_weights,validate_support
from household_pv_components import MODEL_RULE,project_window_components

ROOT=Path(__file__).resolve().parents[3]
POLICY_PATH='docs/operations/weathernext3-capabilities/production-pv-policy.json'
BASELINE_FILES=tuple('openhab/scripts/'+n for n in (
 'household_pv_components.py','household_pv_model.py','household_solar_horizon.py',
 'weather_learning/solar_components.py','weather_learning/native_solar_forecast.py',
 'weather_learning/solar_pairing.py','weather_learning/contracts.py','weather_learning/weights.py',
 'household/codec.py','household/control_contracts.py','household/evidence.py',
 'weather_learning/native_forecast.py','weather_learning/features.py','weather_learning/config.py',
 'weather_learning/evidence.py','weather_learning/normalize.py','weather_learning/weathernext_ee.py',
 'weather_learning/historical.py','weather_learning/solar_experiment.py','weather_learning/pv_training_sources.py'))
CONTEXT={'measurement_cohort_sha256','solar_grid_sha256','system_sha256','horizon_sha256','power_policy_sha256','timezone','training_availability_basis'}
BASES={'retrospective_assumed_full_cycle_9h','retrospective_recorded_ingestion_next_whole_hour'}
SCHEMA='earthship-production-component-pv-calibration/v1'
FIELDS={'schema','baseline_rule','context','training_availability_basis','cutoff','actual_completed_at','ready_at','expires_at','model','population_sha256','training_inputs_sha256','original_pair_sha256s','source_available_at','policy_sha256','authorization_policy_sha256','source_manifest','numerical_environment','procedure_sha256','issued','physical_calibration_qualified','probability_claim','automatic_actuation'}
ROW_FIELDS={'start','end','origin','native_w','total_only_w','outcome_w','fixed_gain','fixed_gain_source_sha256','forecast_sha256','energy_source_sha256','outcome_available_at','cohort_sha256','availability_basis','native_supported','fallback_reason','azimuth_degrees','pair_sha256'}
MAX_BYTES=2*1024**2

class ComponentCalibration(_Frozen):
    __slots__=()

def _policy():return json.loads(_read(ROOT/POLICY_PATH,8192,source=True))

def baseline_manifest():
    return {n:sha256(_read(ROOT/n,262144,source=True)).hexdigest() for n in BASELINE_FILES}

def source_manifest():
    return baseline_manifest()|{n:sha256(_read(ROOT/n,262144,source=True)).hexdigest() for n in (
     'openhab/scripts/weather_learning/production_pv.py','openhab/scripts/weather_source_files.py',
     'openhab/scripts/weather_learning/production_model_admission.py',
     'openhab/scripts/weather_learning/probabilistic.py',
     'openhab/scripts/weather_learning/probabilistic_artifacts.py',POLICY_PATH,
     'docs/operations/weathernext3-capabilities/deployment-policy.json')}

def _context(value):
    if not isinstance(value,dict) or set(value)!=CONTEXT or value['training_availability_basis'] not in BASES:
        raise ValueError('closed native-grid/power/array training context required')
    for k in CONTEXT-{'timezone','training_availability_basis'}:digest(value[k])
    ZoneInfo(value['timezone'])
    return json.loads(canonical(value))

def _rows(rows,context,cutoff,source_available_at):
    policy=_policy()
    if not isinstance(rows,list) or not 1<=len(rows)<=policy['maximum_pairs'] or len(canonical(rows))>16*1024**2 or not isinstance(source_available_at,dict):
        raise ValueError('bounded original matched component pairs required')
    seen=set();selected=[]
    cohort=identity(dict(measurement=context['measurement_cohort_sha256'],solar_grid=context['solar_grid_sha256']))
    for row in rows:
        if (not isinstance(row,dict) or set(row)!=ROW_FIELDS or row['pair_sha256']!=identity({k:v for k,v in row.items() if k!='pair_sha256'}) or
            row['cohort_sha256']!=cohort or row['availability_basis']!=context['training_availability_basis'] or
            row['pair_sha256'] in seen or not instant(row['origin'])<instant(row['start'])<instant(row['end']) or
            not 0<(instant(row['end'])-instant(row['start'])).total_seconds()<=300 or
            any(not finite(row[k]) or not 0<=row[k]<=20000 for k in ('native_w','total_only_w','outcome_w')) or
            type(row['native_supported']) is not bool or (row['fallback_reason'] is None)!=row['native_supported'] or
            not finite(row['azimuth_degrees']) or not 0<=row['azimuth_degrees']<360):
            raise ValueError('unchanged coherent original component pair required')
        for k in ('pair_sha256','forecast_sha256','energy_source_sha256'):digest(row[k])
        if row['fixed_gain_source_sha256'] is not None:digest(row['fixed_gain_source_sha256'])
        if not finite(row['fixed_gain']) or not .5<=row['fixed_gain']<=1.5:raise ValueError('original diagnostic gain differs')
        seen.add(row['pair_sha256']);source=instant(source_available_at[row['forecast_sha256']])
        outcome=instant(row['outcome_available_at']);end=instant(row['end'])
        if outcome<end:raise ValueError('actual label arrival must follow its target')
        lead=(end-instant(row['origin'])).total_seconds()/3600
        if end<cutoff and source<cutoff and outcome<cutoff and row['native_supported'] and row['native_w']>=20 and 0<lead<=policy['maximum_lead_hours']:
            selected.append(json.loads(canonical(row)))
    return sorted(selected,key=lambda r:(instant(r['end']),instant(r['origin']),r['pair_sha256']))

def _training_identity(selected,context,arrivals):
    return identity(dict(rows=selected,context=context,source_available_at=arrivals))

def _load(body,*,current):
    policy=_policy()
    if (not isinstance(body,dict) or set(body)!=FIELDS|{'calibration_sha256'} or body['schema']!=SCHEMA or body['baseline_rule']!=MODEL_RULE or
        body['calibration_sha256']!=identity({k:v for k,v in body.items() if k!='calibration_sha256'}) or len(canonical(body))>MAX_BYTES or
        any(body[k] is not False for k in ('issued','physical_calibration_qualified','probability_claim','automatic_actuation')) or body['policy_sha256']!=identity(policy)):
        raise ValueError('unchanged native-component calibration required')
    context=_context(body['context']);model=body['model']
    if not isinstance(model,dict) or set(model)!={'schema','gain','support','trained_at','training_start','training_end','training_pair_sha256s','model_sha256'} or model['schema']!='earthship-component-effective-gain/v1':
        raise ValueError('closed fitted component gain required')
    support=validate_support(model['support'])
    for name in ('population_sha256','training_inputs_sha256','policy_sha256','authorization_policy_sha256','procedure_sha256'):digest(body[name])
    for name in ('training_pair_sha256s',):
        pins=model[name]
        if not isinstance(pins,list) or len(pins)!=support['forecast_pairs'] or len(set(pins))!=len(pins) or pins!=body['original_pair_sha256s']:
            raise ValueError('original unique component training membership required')
        for pin in pins:digest(pin)
    for pin,at in body['source_available_at'].items():
        digest(pin)
        if instant(at)>=instant(body['cutoff']):raise ValueError('actual source unavailable at fit cutoff')
    if body['procedure_sha256']!=identity(dict(method=policy,source_manifest=body['source_manifest'],numerical_environment=body['numerical_environment'])):
        raise ValueError('original component fitting procedure differs')
    if (model['model_sha256']!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or
        not finite(model['gain']) or not .5<=model['gain']<=1.5 or support['timezone']!=context['timezone'] or
        support['unique_measured_targets']<policy['minimum_targets'] or support['local_target_dates']<policy['minimum_local_target_dates'] or
        not instant(model['training_end'])<instant(body['cutoff'])<=instant(model['trained_at'])<=instant(body['actual_completed_at']) or
        body['ready_at']!=body['actual_completed_at'] or instant(body['expires_at'])!=instant(body['ready_at'])+timedelta(days=policy['model_validity_days']) or
        body['training_availability_basis']!=context['training_availability_basis']):
        raise ValueError('original fitted support/clocks required')
    if current and (body['source_manifest']!=source_manifest() or body['numerical_environment']!=numerical_environment()):
        raise ValueError('component baseline or fitting environment changed')
    obj=object.__new__(ComponentCalibration);object.__setattr__(obj,'_raw',canonical(body));return obj

def load_calibration(body,*,at):
    if isinstance(body,ComponentCalibration):body=body.to_dict()
    result=_load(body,current=True)
    if not instant(body['ready_at'])<=utc(at)<instant(body['expires_at']):raise ValueError('original component fit unavailable or expired')
    return result

def fit_calibration(*,rows,context,cutoff,source_available_at,population_sha256,pair_producer_manifest,authorization,authorization_sha256,clock=lambda:datetime.now(timezone.utc),previous=None):
    _authorization(authorization,authorization_sha256);context=_context(context);cutoff=utc(cutoff);started=utc(clock());policy=_policy();digest(population_sha256)
    if cutoff>started or pair_producer_manifest!=baseline_manifest():raise ValueError('actual fit time and original matching pair producer required')
    manifest=source_manifest();environment=numerical_environment();selected=_rows(rows,context,cutoff,source_available_at)
    arrivals={p:source_available_at[p] for p in sorted({r['forecast_sha256'] for r in selected})}
    training=_training_identity(selected,context,arrivals)
    if previous is not None:
        old=_load(previous.to_dict(),current=False).to_dict()
        if (old['training_inputs_sha256']==training and old['source_manifest']==manifest and old['numerical_environment']==environment and
            old['authorization_policy_sha256']==authorization_sha256 and instant(old['ready_at'])<=started<instant(old['expires_at'])):
            return previous,False
    weights,support=target_weights(selected,target=lambda r:(r['start'],r['end']),evidence=lambda r:(r['outcome_w'],r['energy_source_sha256']),
        at=lambda r:r['start'],cohort=lambda r:r['cohort_sha256'],timezone=context['timezone'])
    if support['unique_measured_targets']<policy['minimum_targets'] or support['local_target_dates']<policy['minimum_local_target_dates']:
        raise ValueError('at least24 measured targets on3 local dates required')
    denominator=fsum(w*r['native_w']**2 for w,r in zip(weights,selected))
    gain=max(.5,min(1.5,fsum(w*r['native_w']*r['outcome_w'] for w,r in zip(weights,selected))/denominator))
    model=dict(schema='earthship-component-effective-gain/v1',gain=gain,support=support,trained_at=started.isoformat(),
        training_start=min(r['start'] for r in selected),training_end=max(r['end'] for r in selected),training_pair_sha256s=[r['pair_sha256'] for r in selected])
    model['model_sha256']=identity(model);finished=utc(clock())
    if finished<started or source_manifest()!=manifest or numerical_environment()!=environment:raise ValueError('original fit source/environment/clock changed')
    value=dict(schema=SCHEMA,baseline_rule=MODEL_RULE,context=context,training_availability_basis=context['training_availability_basis'],cutoff=cutoff.isoformat(),
        actual_completed_at=finished.isoformat(),ready_at=finished.isoformat(),expires_at=(finished+timedelta(days=policy['model_validity_days'])).isoformat(),
        model=model,population_sha256=population_sha256,training_inputs_sha256=training,original_pair_sha256s=[r['pair_sha256'] for r in selected],source_available_at=arrivals,
        policy_sha256=identity(policy),authorization_policy_sha256=authorization_sha256,source_manifest=manifest,numerical_environment=environment,
        procedure_sha256=identity(dict(method=policy,source_manifest=manifest,numerical_environment=environment)),
        issued=False,physical_calibration_qualified=False,probability_claim=False,automatic_actuation=False)
    result=_freeze(ComponentCalibration,value,'calibration_sha256');_load(result.to_dict(),current=True);return result,True

def project_calibrated(calibration,*,forecast,positions,system_raw,horizon_raw,measurement_cohort_sha256,power_policy_sha256,start,end,authorize):
    from .native_forecast import validate_native_forecast
    from .native_solar_forecast import SCHEMA as FORECAST_SCHEMA
    forecast=validate_native_forecast(forecast);origin=instant(forecast['origin'])
    if forecast['schema']!=FORECAST_SCHEMA:raise ValueError('actual native component forecast required')
    model=load_calibration(calibration,at=origin);body=model.to_dict();context=body['context']
    if (sha256(system_raw).hexdigest()!=context['system_sha256'] or sha256(horizon_raw).hexdigest()!=context['horizon_sha256'] or
        measurement_cohort_sha256!=context['measurement_cohort_sha256'] or power_policy_sha256!=context['power_policy_sha256'] or
        forecast['site']['timezone']!=context['timezone'] or forecast['rows'][0]['solar']['grid_sha256']!=context['solar_grid_sha256']):
        raise ValueError('original grid/power/array/terrain calibration context changed')
    def owner():
        check=json.loads(canonical(body))
        if not callable(authorize) or authorize(check) is not True or check!=body:raise PermissionError('unchanged current component production owner required')
    owner();system=json.loads(system_raw);horizon=json.loads(horizon_raw)
    raw=project_window_components(array=system['array'],forecast=forecast,positions=positions,start=start,end=end,timezone_name=context['timezone'],horizon_profile=horizon['profile'])
    gain=body['model']['gain'];adjusted=json.loads(canonical(raw));adjusted.pop('projection_sha256')
    adjusted.update(schema='earthship-calibrated-native-component-pv/v1',calibration_sha256=body['calibration_sha256'],calibration_model_sha256=body['model']['model_sha256'],
        raw_projection_sha256=raw['projection_sha256'],raw_potential_pv_kwh=raw['potential_pv_kwh'])
    # A coefficient fitted to native decomposition must not calibrate a
    # different total-only fallback baseline under the same model identity.
    midnight=datetime.combine(utc(start).astimezone(ZoneInfo(context['timezone'])).date()+timedelta(days=1),datetime.min.time(),ZoneInfo(context['timezone'])).astimezone(timezone.utc)
    today=[];applied=0
    if len(adjusted['steps'])!=len(adjusted['segments']):raise ValueError('complete original component step grid required')
    for step,segment in zip(adjusted['steps'],adjusted['segments']):
        if (step['start'],step['end'])!=(segment['start'],segment['end']):raise ValueError('same original PV integration segments required')
        use=segment['method']=='native_components';factor=gain if use else 1.;applied+=use
        step['potential_pv_kwh']*=factor;segment['potential_dc_w']*=factor
        a,b=instant(step['start']),instant(step['end'])
        today.append(segment['potential_dc_w']*max(0.,(min(b,midnight)-a).total_seconds())/3600000)
    adjusted.update(potential_pv_kwh=fsum(r['potential_pv_kwh'] for r in adjusted['steps']),remaining_today_potential_kwh=fsum(today),
        calibration_scope='raw_total_only_fallback' if not applied else 'native_components_only' if applied==len(adjusted['steps']) else 'mixed_native_and_raw_fallback',
        calibrated_segments=applied,raw_fallback_segments=len(adjusted['steps'])-applied)
    adjusted['projection_sha256']=identity(adjusted);owner()
    value=dict(schema='earthship-prepared-production-component-pv/v1',calibration_sha256=body['calibration_sha256'],raw_projection=raw,calibrated_projection=adjusted,
        issued=False,physical_calibration_qualified=False,probability_claim=False,automatic_actuation=False)
    value['projection_sha256']=identity(value);return value

def retain_calibration(state,calibration):
    from .shadow import _directory
    body=_load(calibration.to_dict(),current=True).to_dict();pin=body['calibration_sha256']
    _directory(state.root/'production-models')
    state._write(state.root/'production-models'/(pin+'.json'),body,immutable=True)
    if read_calibration(state,pin,at=instant(body['ready_at'])).to_dict()!=body:raise ValueError('original component fit readback differs')
    return pin

def read_calibration(state,pin,*,at):
    from .shadow import _read
    digest(pin);body=_read(state.root/'production-models'/(pin+'.json'),MAX_BYTES)
    if body.get('calibration_sha256')!=pin:raise ValueError('original retained component fit differs')
    return load_calibration(body,at=at)

def storage_projection(prepared,*,initial_soc_pct,nominal_bank_kwh,load_ac_w):
    from household_pv_model import simulate_storage
    if (not isinstance(prepared,dict) or prepared.get('schema')!='earthship-prepared-production-component-pv/v1' or
        prepared.get('projection_sha256')!=identity({k:v for k,v in prepared.items() if k!='projection_sha256'}) or
        any(prepared.get(k) is not False for k in ('issued','physical_calibration_qualified','probability_claim','automatic_actuation'))):
        raise ValueError('original prepared calibrated component projection required')
    raw=prepared['raw_projection'];pv=prepared['calibrated_projection']
    if (raw['projection_sha256']!=identity({k:v for k,v in raw.items() if k!='projection_sha256'}) or
        pv['projection_sha256']!=identity({k:v for k,v in pv.items() if k!='projection_sha256'}) or
        pv['raw_projection_sha256']!=raw['projection_sha256'] or pv['calibration_sha256']!=prepared['calibration_sha256']):
        raise ValueError('original calibrated steps required')
    value=simulate_storage(steps=pv['steps'],initial_soc_pct=initial_soc_pct,nominal_bank_kwh=nominal_bank_kwh,load_ac_w=load_ac_w)
    value.update(calibration_sha256=prepared['calibration_sha256'],pv_projection_sha256=pv['projection_sha256'],physical_calibration_qualified=False,automatic_actuation=False)
    return value
