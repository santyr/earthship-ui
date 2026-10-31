"""Validate retained component originals without reissuing or rerunning models.

Power scores describe the original constituent integration bins of a confirmed
daily total. They are neither observed daily energy nor metrology calibration.
No current selector, numerical environment or current model is consulted.
"""
from datetime import timedelta
from hashlib import sha256
from math import fsum,isclose
from .contracts import identity,canonical,digest,instant,finite

ENVELOPE='earthship-confirmed-component-daily-forecast/v1'
POPULATION='constituent_five_minute_power_of_published_daily_totals'
RECEIPT_FIELDS={'schema','issued','view','provider','native_forecast','geometry_series_sha256s','geometry_positions','system_source','horizon_source','calibration_original','calibration_policy','component_windows','owner_profile_sha256','owner_runtime_manifest','automatic_actuation','receipt_sha256'}
EMISSION_FIELDS={'schema','receipt_sha256','view_bytes_sha256','published_at','calibration_sha256','issued','score_days','source_population','score_basis','score_from_at','automatic_actuation','emission_sha256'}


def _original(value,key,schema):
    if (not isinstance(value,dict) or value.get('schema')!=schema or value.get(key)!=identity({k:v for k,v in value.items() if k!=key})):
        raise ValueError('unchanged original component '+key+' required')
    digest(value[key]);return value


def confirmed(receipt,emission,*,before):
    _original(receipt,'receipt_sha256','earthship-daily-pv-potential-receipt/v2')
    _original(emission,'emission_sha256','earthship-confirmed-component-daily-emission/v1')
    if (set(receipt)!=RECEIPT_FIELDS or set(emission)!=EMISSION_FIELDS or receipt['issued'] is not False or
        emission['issued'] is not True or receipt['automatic_actuation'] is not False or emission['automatic_actuation'] is not False or
        emission['receipt_sha256']!=receipt['receipt_sha256'] or emission['view_bytes_sha256']!=sha256(canonical(receipt['view'])).hexdigest() or
        emission['score_basis']!=POPULATION or emission['score_from_at']!=emission['published_at'] or
        emission['source_population']!='actual_published_daily_totals_and_original_constituent_power' or len(canonical(receipt))>8*1024**2):
        raise ValueError('original confirmed component publication required')
    view=receipt['view'];origin=instant(view['generatedAt']);published=instant(emission['published_at'])
    if (view.get('schema')!='earthship-daily-pv-potential/v4' or view.get('automatic_actuation') is not False or
        view.get('physical_calibration_qualified') is not False or not origin<=published<=origin+timedelta(seconds=85) or published>before):
        raise ValueError('component forecast must be published before scored hour')
    calibration=receipt['calibration_original'];_original(calibration,'calibration_sha256','earthship-production-component-pv-calibration/v1')
    model=calibration['model'];_original(model,'model_sha256','earthship-component-effective-gain/v1')
    policy=receipt['calibration_policy'];c=view['calibration']
    if (calibration['issued'] is not False or any(calibration[k] is not False for k in ('physical_calibration_qualified','probability_claim','automatic_actuation')) or
        not finite(model['gain']) or not .5<=model['gain']<=1.5 or
        calibration['policy_sha256']!=identity(policy) or
        calibration['procedure_sha256']!=identity(dict(method=policy,source_manifest=calibration['source_manifest'],numerical_environment=calibration['numerical_environment'])) or
        c['calibrationSha256']!=calibration['calibration_sha256'] or emission['calibration_sha256']!=calibration['calibration_sha256'] or
        c['modelSha256']!=model['model_sha256'] or c['procedureSha256']!=calibration['procedure_sha256'] or c['policySha256']!=calibration['policy_sha256'] or
        c['baselineRule']!=calibration['baseline_rule']):
        raise ValueError('original component model/procedure differs')
    if not instant(model['trained_at'])<=instant(calibration['ready_at']):raise ValueError('original component fit clocks differ')
    context=calibration['context']
    native=receipt['native_forecast']
    _original(native,'forecast_sha256','earthship-weathernext-native-forecast/v2')
    for field,pin in (('system_source','system_sha256'),('horizon_source','horizon_sha256')):
        if sha256(receipt[field]['raw'].encode()).hexdigest()!=context[pin] or receipt[field]['sha256']!=context[pin]:
            raise ValueError('original component physical context differs')
    if (view['systemSha256']!=context['system_sha256'] or view['horizonSha256']!=context['horizon_sha256'] or
        view['timezone']!=context['timezone'] or view['geometrySha256']!=identity(receipt['geometry_series_sha256s']) or
        receipt['native_forecast']['forecast_sha256']!=view['weatherSha256'] or receipt['native_forecast']['origin']!=view['generatedAt']):
        raise ValueError('original component forecast context differs')
    return dict(schema=ENVELOPE,receipt=receipt,emission=emission)


def inputs(envelope,source,*,assessed_at):
    if not isinstance(envelope,dict) or set(envelope)!={'schema','receipt','emission'} or envelope['schema']!=ENVELOPE:
        raise ValueError('original confirmed component envelope required')
    receipt=envelope['receipt'];emission=envelope['emission']
    confirmed(receipt,emission,before=instant(source['start']))
    if instant(source['received_at'])>assessed_at:raise ValueError('original power not yet available')
    calibration=receipt['calibration_original'];context=calibration['context'];view=receipt['view'];origin=instant(view['generatedAt'])
    # Preserve the cohort identity sealed by the original training producer.
    measurement=identity(dict(policy=source['policy_raw'],bank_start=source['bank_start'],items=source['items']))
    if measurement!=context['measurement_cohort_sha256'] or sha256(source['policy_raw'].encode()).hexdigest()!=context['power_policy_sha256']:
        raise ValueError('original component measured-power cohort differs')
    windows=receipt['component_windows'];days=view['days'];steps=[];seen=set();found=set()
    if not isinstance(windows,list) or not 1<=len(windows)<=10 or not isinstance(days,list) or not 1<=len(days)<=10:
        raise ValueError('bounded original daily component windows required')
    available={d['projectionSha256']:d for d in days if d['status']=='available'}
    if len(available)!=sum(d['status']=='available' for d in days):raise ValueError('unique original daily component windows required')
    gain=calibration['model']['gain']
    for window in windows:
        _original(window,'window_sha256','earthship-owned-production-component-window/v1')
        pin=window['window_sha256'];day=available.get(pin)
        if day is None or pin in found or window['issued'] is not False or window['automatic_actuation'] is not False or window['physical_calibration_qualified'] is not False:
            raise ValueError('same original published component window required')
        found.add(pin);raw=window['raw_projection'];projection=window['projection']
        for p in (raw,projection):
            if p['projection_sha256']!=identity({k:v for k,v in p.items() if k!='projection_sha256'}):raise ValueError('original component projection differs')
            if (p['forecast_sha256']!=view['weatherSha256'] or p['geometry_sha256']!=identity(receipt['geometry_positions']) or
                p['origin']!=day['fromAt'] or p['through']!=day['throughAt'] or p['automatic_actuation'] is not False or p['physical_calibration_qualified'] is not False):
                raise ValueError('original daily constituent source differs')
        if (window['calibration_sha256']!=calibration['calibration_sha256'] or not isclose(raw['potential_pv_kwh'],day['uncalibratedPotentialKwh'],abs_tol=1e-9) or
            not isclose(projection['potential_pv_kwh'],day['potentialKwh'],abs_tol=1e-9) or projection['calibration_scope']!=day['calibrationScope'] or
            not len(raw['steps'])==len(raw['segments'])==len(projection['steps'])==len(projection['segments']) or not 1<=len(raw['steps'])<=300):
            raise ValueError('original daily integration differs')
        adjusted=window['mode']=='selected_native_gain'
        if adjusted and not instant(calibration['ready_at'])<=origin<instant(calibration['expires_at']):
            raise ValueError('original model unavailable at forecast issue')
        if window['mode'] not in ('selected_native_gain','native_components_raw_fallback'):raise ValueError('original component mode required')
        last=instant(day['fromAt'])
        for r,s,p,t in zip(raw['segments'],raw['steps'],projection['segments'],projection['steps']):
            a,b=instant(r['start']),instant(r['end']);key=a,b
            if (key in seen or not origin<=a==last<b<=instant(day['throughAt']) or b-a>timedelta(minutes=5) or
                any((v['start'],v['end'])!=(r['start'],r['end']) for v in (s,p,t)) or
                not all(finite(v['potential_dc_w']) and 0<=v['potential_dc_w']<=30000 for v in (r,p))):
                raise ValueError('complete original daily integration bins required')
            seen.add(key);last=b;use=adjusted and r['method']=='native_components'
            if p['method']!=r['method'] or not isclose(p['potential_dc_w'],r['potential_dc_w']*(gain if use else 1.),rel_tol=1e-10,abs_tol=1e-8):
                raise ValueError('native-only original adjustment differs')
            for segment,step in ((r,s),(p,t)):
                if not isclose(step['potential_pv_kwh'],segment['potential_dc_w']*(b-a).total_seconds()/3600000,rel_tol=1e-10,abs_tol=1e-9):
                    raise ValueError('original component power/energy differs')
            steps.append(dict(start=r['start'],end=r['end'],uncalibrated_w=r['potential_dc_w'],potential_w=p['potential_dc_w'],calibration_applied=use))
        if last!=instant(day['throughAt']) or any(not isclose(fsum(s['potential_pv_kwh'] for s in p['steps']),p['potential_pv_kwh'],abs_tol=1e-9) for p in (raw,projection)):
            raise ValueError('complete original published daily energy required')
    if found!=set(available):raise ValueError('all available original daily windows required')
    metadata=dict(schema='earthship-pv-prospective-hour-score/v4',model_sha256=calibration['model']['model_sha256'],calibration_sha256=calibration['calibration_sha256'],
        procedure_sha256=calibration['procedure_sha256'],calibration_policy_sha256=calibration['policy_sha256'],measurement_cohort_sha256=measurement,
        solar_grid_sha256=context['solar_grid_sha256'],baseline_rule=calibration['baseline_rule'],forecast_emission_sha256=emission['emission_sha256'],
        forecast_published_at=emission['published_at'],metric_population=POPULATION,target_timezone=view['timezone'])
    return view,steps,receipt['receipt_sha256'],metadata
