"""Pure, thermal-only local weather correction over retained original inputs."""
from bisect import bisect_left
from dataclasses import replace
from datetime import timedelta
from math import fsum
from types import SimpleNamespace
from .codec import canonical,identity
from .control_contracts import instant
from weather_learning.contracts import finite,digest
from weather_learning.site_calibration import _calculate
from weather_learning.irradiance_learning import irradiance_features
from weather_learning.historical_serving import temperature_features
from household_solar_horizon import horizon_height,_profile

KINDS={'outdoor_temperature_c','irradiance_w_m2'}
CAPSULE_FIELDS={'schema','kind','feature_names','centers','scales','coefficients','intercept','correction_limit','trained_at','cutoff','training_end','training_data_sha256','model_sha256','timezone','capsule_sha256'}
ADMISSION_FIELDS={'schema','admitted_at','expires_at','models','source_sensor_epoch','horizon_profile','originals','runtime_manifest','source_experiments','physical_calibration_qualified','automatic_actuation','admission_sha256'}
CONTEXT_FIELDS={'schema','issue','prepared_at','admission','admission_ref','selection','forecast_sha256','rows','midpoint_positions','geometry_refs','native_runtime','site','timezone','automatic_actuation','context_sha256'}


def capsule(model):
    from weather_learning.site_calibration import _model
    model=_model(model)
    value={key:model[key] for key in CAPSULE_FIELDS-{'schema','capsule_sha256'}}
    value['schema']='earthship-thermal-weather-model-capsule/v1';value['capsule_sha256']=identity(value)
    return value


def validate_admission(value,*,issue):
    if (not isinstance(value,dict) or set(value)!=ADMISSION_FIELDS or value['schema']!='earthship-thermal-weather-admission/v1' or
            value['admission_sha256']!=identity({k:v for k,v in value.items() if k!='admission_sha256'}) or
            value['automatic_actuation'] is not False or value['physical_calibration_qualified'] is not False or
            set(value['models'])!=KINDS or not instant(value['admitted_at'])<=issue<instant(value['expires_at'])):
        raise ValueError('original available thermal weather admission required')
    if not isinstance(value['source_sensor_epoch'],str) or not 1<=len(value['source_sensor_epoch'])<=128:raise ValueError('original outdoor sensor phase required')
    for kind,model in value['models'].items():
        n=len(model.get('feature_names',[]))
        if (set(model)!=CAPSULE_FIELDS or model['schema']!='earthship-thermal-weather-model-capsule/v1' or model['kind']!=kind or
                model['capsule_sha256']!=identity({k:v for k,v in model.items() if k!='capsule_sha256'}) or not 1<=n<=16 or
                model['feature_names']!=sorted(set(model['feature_names'])) or any(len(model[k])!=n for k in ('centers','scales','coefficients')) or
                not all(finite(x) for key in ('centers','scales','coefficients') for x in model[key]) or any(x<=0 for x in model['scales']) or
                not finite(model['intercept']) or not finite(model['correction_limit']) or not 0<model['correction_limit']<=(6 if kind=='outdoor_temperature_c' else 1000) or
                not instant(model['training_end'])<instant(model['cutoff'])<=instant(model['trained_at'])<=instant(value['admitted_at']) or
                issue>=instant(model['trained_at'])+timedelta(days=14)):
            raise ValueError('bounded original thermal model capsule required')
        digest(model['model_sha256']);digest(model['training_data_sha256'])
    if not isinstance(value['horizon_profile'],list) or len(value['horizon_profile'])!=48:raise ValueError('original declared horizon required')
    _profile(value['horizon_profile'])
    for pin in value['runtime_manifest'].values():digest(pin)
    return value


def validate_context(value,*,issue,available,forecast=None,sensor_epoch=None):
    if isinstance(value,dict) and value.get('schema')=='earthship-thermal-weather-context/v2':
        from .production_weather_conditioning import validate_context as validate_production
        return validate_production(value,issue=issue,available=available,forecast=forecast,sensor_epoch=sensor_epoch)
    if (not isinstance(value,dict) or set(value)!=CONTEXT_FIELDS or value['schema']!='earthship-thermal-weather-context/v1' or
            value['context_sha256']!=identity({k:v for k,v in value.items() if k!='context_sha256'}) or value['automatic_actuation'] is not False or
            instant(value['issue'])!=issue or not instant(value['prepared_at'])<=available<=issue or len(canonical(value))>32768):
        raise ValueError('bounded causal thermal weather context required')
    admission=validate_admission(value['admission'],issue=issue)
    if instant(admission['admitted_at'])>instant(value['prepared_at']):raise ValueError('thermal weather model was unavailable during collection')
    if sensor_epoch is not None and admission['source_sensor_epoch']!=sensor_epoch:raise ValueError('thermal weather source sensor phase differs')
    from zoneinfo import ZoneInfo
    ZoneInfo(value['timezone'])
    if any(model['timezone']!=value['timezone'] for model in admission['models'].values()):raise ValueError('original model and weather timezones differ')
    site=value['site']
    if not isinstance(site,dict) or set(site) not in ({'latitude','longitude'},{'latitude','longitude','altitude_m'}) or not finite(site['latitude']) or not -90<=site['latitude']<=90 or not finite(site['longitude']) or not -180<=site['longitude']<=180:raise ValueError('original thermal weather site required')
    digest(value['forecast_sha256'])
    if forecast is not None and (identity(forecast)!=value['forecast_sha256'] or canonical(forecast['rows'])!=canonical(value['rows'])):raise ValueError('original raw Google forcing differs')
    rows=value['rows'];times=[instant(r['at']) for r in rows]
    if not 2<=len(rows)<=26 or times!=sorted(set(times)) or any(b-a!=timedelta(hours=1) for a,b in zip(times,times[1:])):
        raise ValueError('original complete hourly brackets required')
    if not times[0]<=issue<times[-1] or any(not finite(r['tempF']) or not -40<=r['tempF']<=140 or not finite(r['radiationWm2']) or not 0<=r['radiationWm2']<=1600 for r in rows):
        raise ValueError('finite original thermal weather required')
    points=value['midpoint_positions'];expected=[(at-timedelta(minutes=30)).isoformat() for at in times if at>issue]
    if not isinstance(points,list) or [p['at'] for p in points]!=expected:raise ValueError('exact native hourly midpoint coverage required')
    for p in points:
        if (set(p)!={'at','elevation_degrees','azimuth_degrees'} or not finite(p['elevation_degrees']) or not -90<=p['elevation_degrees']<=90 or
                not finite(p['azimuth_degrees']) or not 0<=p['azimuth_degrees']<=360):raise ValueError('bounded original native midpoint required')
    return value


def apply_conditioning(forcings,context,*,issue,available,initial_outdoor_f):
    if isinstance(context,dict) and context.get('schema')=='earthship-thermal-weather-context/v2':
        from .production_weather_conditioning import apply_conditioning as apply_production
        return apply_production(forcings,context,issue=issue,available=available,initial_outdoor_f=initial_outdoor_f)
    """Return new thermal forcings; preserve raw weather and all action values."""
    value=validate_context(context,issue=issue,available=available);admission=value['admission'];rows=value['rows'];times=[instant(r['at']) for r in rows]
    positions={p['at']:p for p in value['midpoint_positions']};models=admission['models'];outside=models['outdoor_temperature_c'];solar=models['irradiance_w_m2']
    index=bisect_left(times,issue)
    if index==0 and times[0]==issue:raw_origin=rows[0]['tempF']
    else:
        left,right=rows[index-1],rows[index];fraction=(issue-times[index-1])/(times[index]-times[index-1]);raw_origin=left['tempF']+fraction*(right['tempF']-left['tempF'])
    initial_c=(initial_outdoor_f-32)*5/9;bias=initial_c-(raw_origin-32)*5/9
    if not finite(initial_c) or not -40<=initial_c<=60:raise ValueError('qualified current outdoor origin required')
    temperatures={};irradiance={}
    for row,at in zip(rows,times):
        if at<=issue:continue
        raw_c=(row['tempF']-32)*5/9;features=temperature_features(SimpleNamespace(target_at=at,mean_c=raw_c),origin=issue,origin_bias_c=bias,timezone_name=value['timezone'])
        temperatures[at]=max(-40.,min(60.,_calculate(outside,features,raw_c)))*9/5+32
        p=positions[(at-timedelta(minutes=30)).isoformat()];raw=row['radiationWm2'];corrected=raw
        if p['elevation_degrees']>0:
            position=dict(p,horizon_elevation_degrees=horizon_height(admission['horizon_profile'],p['azimuth_degrees']))
            features=irradiance_features(raw,lead_hours=(at-issue).total_seconds()/3600,target=at,position=position)
            corrected=max(0.,min(1600.,_calculate(solar,features,raw)))
        irradiance[at]=corrected
    from thermal_model.installed_shade_origin import ending_hour_mean
    from thermal_model.installed_shade_dynamics import STEP
    raw_radiation=[r["radiationWm2"] for r in rows]
    corrected_radiation=[irradiance.get(at,r["radiationWm2"]) for r,at in zip(rows,times)]
    first_future=next(at for at in times if at>issue);result=[];start=issue
    for row in forcings:
        i=bisect_left(times,row.at)
        if not 1<=i<len(times):raise ValueError('complete original thermal brackets required')
        left,right=rows[i-1],rows[i];fraction=(row.at-times[i-1])/(times[i]-times[i-1]);raw_outside=left['tempF']+fraction*(right['tempF']-left['tempF'])
        if row.at!=start+STEP:raise ValueError('complete original five-minute thermal grid required')
        raw_mean=ending_hour_mean(times,raw_radiation,start,row.at)
        if abs(raw_outside-row.outdoor_f)>1e-9 or abs(raw_mean-row.radiation_wm2)>1e-9:raise ValueError('unchanged original thermal forcing grid required')
        if row.at<=first_future:
            fraction=(row.at-issue)/(first_future-issue);outdoor=initial_outdoor_f+fraction*(temperatures[first_future]-initial_outdoor_f)
        else:outdoor=temperatures[times[i-1]]+fraction*(temperatures[times[i]]-temperatures[times[i-1]])
        result.append(replace(row,outdoor_f=outdoor,radiation_wm2=ending_hour_mean(times,corrected_radiation,start,row.at)))
        start=row.at
    return tuple(result)
