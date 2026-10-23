"""Frozen already-published temperature points for one physical rollout."""
from bisect import bisect_left
from dataclasses import replace
from datetime import timedelta
from zoneinfo import ZoneInfo
from pathlib import PurePosixPath
from .codec import identity,canonical
from .control_contracts import instant
from weather_learning.contracts import finite,digest

SCHEMA='earthship-thermal-weather-context/v2'
FIELDS={'schema','issue','prepared_at','selection','forecast_sha256','rows','points','production_receipt','production_issue_sha256','production_emission_sha256','production_published_at','production_valid_until','source_sensor_epoch','native_runtime','site','timezone','mode','reason','solar_policy','originals','runtime_manifest','physical_calibration_qualified','automatic_actuation','context_sha256'}
SELECTION_FIELDS={'schema','state_directory','source_sensor_epoch','available_at','runtime_sha256','automatic_actuation','selection_sha256'}
POINT_FIELDS={'at','temp_f','mode','model_sha256','procedure_sha256','source_sha256','profile'}


def validate_context(value,*,issue,available,forecast=None,sensor_epoch=None):
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or
        value['context_sha256']!=identity({k:v for k,v in value.items() if k!='context_sha256'}) or len(canonical(value))>32768 or
        value['automatic_actuation'] is not False or value['physical_calibration_qualified'] is not False or
        instant(value['issue'])!=issue or not instant(value['prepared_at'])<=available<=issue or
        value['solar_policy']!='unchanged_native_ending_hour_horizontal_mean'):
        raise ValueError('bounded causal original production thermal context required')
    digest(value['forecast_sha256']);ZoneInfo(value['timezone'])
    if not isinstance(value['source_sensor_epoch'],str) or not 1<=len(value['source_sensor_epoch'])<=128 or sensor_epoch is not None and sensor_epoch!=value['source_sensor_epoch']:
        raise ValueError('original physical outdoor sensor phase required')
    selected=value['selection']
    if (not isinstance(selected,dict) or set(selected)!=SELECTION_FIELDS or selected.get('schema')!='earthship-thermal-weather-selection/v2' or selected['automatic_actuation'] is not False or
        selected['selection_sha256']!=identity({k:v for k,v in selected.items() if k!='selection_sha256'}) or
        selected['runtime_sha256']!=identity(value['runtime_manifest']) or instant(selected['available_at'])>instant(value['prepared_at'])):
        raise ValueError('original production thermal owner required')
    path=selected['state_directory']
    if (not isinstance(path,str) or len(path)>1024 or not PurePosixPath(path).is_absolute() or str(PurePosixPath(path))!=path or '..' in PurePosixPath(path).parts or
        not isinstance(selected['source_sensor_epoch'],str) or not 1<=len(selected['source_sensor_epoch'])<=128 or
        not isinstance(value['runtime_manifest'],dict) or not 1<=len(value['runtime_manifest'])<=32):
        raise ValueError('closed bounded original thermal owner required')
    for pin in value['runtime_manifest'].values():digest(pin)
    site=value['site']
    if (not isinstance(site,dict) or set(site) not in ({'latitude','longitude'},{'latitude','longitude','altitude_m'}) or
        not finite(site['latitude']) or not -90<=site['latitude']<=90 or not finite(site['longitude']) or not -180<=site['longitude']<=180):
        raise ValueError('original production thermal site required')
    rows=value['rows'];times=[instant(r['at']) for r in rows]
    if (not 2<=len(rows)<=26 or times!=sorted(set(times)) or not times[0]<=issue<times[-1] or
        any(b-a!=timedelta(hours=1) for a,b in zip(times,times[1:])) or
        any(not finite(r['tempF']) or not -40<=r['tempF']<=140 or not finite(r['radiationWm2']) or not 0<=r['radiationWm2']<=1600 for r in rows)):
        raise ValueError('complete original raw thermal brackets required')
    if forecast is not None and (identity(forecast)!=value['forecast_sha256'] or canonical(forecast['rows'])!=canonical(rows)):
        raise ValueError('original raw thermal forecast differs')
    fields=('production_receipt','production_issue_sha256','production_emission_sha256','production_published_at','production_valid_until')
    if value['mode']=='native_raw_fallback':
        if not isinstance(value['reason'],str) or not value['reason'].startswith('production_temperature_') or value['points']!=[] or value['originals']!=[] or any(value[k] is not None for k in fields):
            raise ValueError('named original native thermal fallback required')
        return value
    if (value['mode']!='confirmed_production_temperature' or value['reason'] is not None or selected['source_sensor_epoch']!=value['source_sensor_epoch'] or
        not instant(value['production_published_at'])<=instant(value['prepared_at'])<=available<=issue<instant(value['production_valid_until']) or
        not isinstance(value['originals'],list) or len(value['originals'])!=3):
        raise ValueError('original available production thermal points required')
    for k in ('production_issue_sha256','production_emission_sha256'):digest(value[k])
    for ref in value['originals']:
        if (not isinstance(ref,dict) or set(ref)!={'path','maximum','source','sha256'} or ref['source'] is not False or
            type(ref['maximum']) is not int or not 1<=ref['maximum']<=16*1024**2):
            raise ValueError('closed original thermal publication reference required')
        digest(ref['sha256'])
    points=value['points']
    if not isinstance(points,list) or [instant(p['at']) for p in points]!=[at for at in times if at>issue]:
        raise ValueError('exact original future thermal temperature points required')
    for point in points:
        if set(point)!=POINT_FIELDS or not finite(point['temp_f']) or not -40<=point['temp_f']<=140 or point['profile'] not in ('nearTerm','near24','interim48','extended'):
            raise ValueError('bounded original emitted thermal temperature point required')
        digest(point['source_sha256'])
        if point['mode']=='local_model_mean':
            digest(point['model_sha256']);digest(point['procedure_sha256'])
        elif point['mode']!='declared_native_point_fallback' or point['model_sha256'] is not None or point['procedure_sha256'] is not None:
            raise ValueError('original emitted temperature method required')
    return value


def apply_conditioning(forcings,context,*,issue,available,initial_outdoor_f):
    value=validate_context(context,issue=issue,available=available)
    if not finite(initial_outdoor_f) or not -40<=initial_outdoor_f<=140:raise ValueError('qualified original outdoor initial state required')
    if value['mode']=='native_raw_fallback':return tuple(forcings)
    rows=value['rows'];times=[instant(r['at']) for r in rows];points=value['points'];targets=[instant(p['at']) for p in points];temperatures=[p['temp_f'] for p in points]
    result=[];last=issue
    from thermal_model.installed_shade_dynamics import STEP
    from thermal_model.installed_shade_origin import ending_hour_mean
    for row in forcings:
        index=bisect_left(times,row.at)
        if row.at!=last+STEP or not 1<=index<len(times):raise ValueError('original five-minute thermal forcing grid required')
        fraction=(row.at-times[index-1])/(times[index]-times[index-1])
        raw=rows[index-1]['tempF']+fraction*(rows[index]['tempF']-rows[index-1]['tempF'])
        radiation=ending_hour_mean(times,[p['radiationWm2'] for p in rows],last,row.at)
        if abs(row.outdoor_f-raw)>1e-9 or abs(row.radiation_wm2-radiation)>1e-9:raise ValueError('unchanged original raw thermal forcings required')
        at=bisect_left(targets,row.at)
        if at==0:outdoor=initial_outdoor_f+(row.at-issue)/(targets[0]-issue)*(temperatures[0]-initial_outdoor_f)
        else:outdoor=temperatures[at-1]+(row.at-targets[at-1])/(targets[at]-targets[at-1])*(temperatures[at]-temperatures[at-1])
        result.append(replace(row,outdoor_f=outdoor));last=row.at
    return tuple(result)
