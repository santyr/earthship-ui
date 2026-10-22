"""Constructed weather through an original native air/wall model, never selection."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from astro_geometry_series import replay_series
from native_thermal_artifact import current_native_runtime,fit_profile,_read,LIMITS
from native_thermal_forecast import validate_capture
from .contracts import canonical,identity,instant

SCHEMA='earthship-original-native-thermal-scenario-context/v1'
FIELDS={'schema','capture','runtime','artifact_sha256','capture_sha256','context_sha256'}
_SEAL=object()


class NativeScenarioContext:
    __slots__=('_content','_seal')
    def __init__(self,*args,**kwargs):raise TypeError('prepare a verified original native scenario context')
    def __setattr__(self,name,value):raise AttributeError('native scenario context is immutable')
    def to_dict(self):
        _require(self);return json.loads(self._content)


def _require(value):
    if type(value) is not NativeScenarioContext or getattr(value,'_seal',None) is not _SEAL:raise ValueError('verified original native scenario context required')


def _runtime(runtime,guard):
    if canonical(runtime)!=canonical(current_native_runtime(guard=guard)):raise ValueError('original native model producer differs from current numerical runtime')


def prepare_native_context(capture,*,runtime,expected_capture_sha256,expected_artifact_sha256,guard=lambda:None):
    _runtime(runtime,guard)
    original=validate_capture(capture,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,check_budget=guard)
    value=dict(schema=SCHEMA,capture=original,runtime=deepcopy(runtime),artifact_sha256=expected_artifact_sha256,capture_sha256=expected_capture_sha256)
    value['context_sha256']=identity(value);context=object.__new__(NativeScenarioContext)
    object.__setattr__(context,'_content',canonical(value));object.__setattr__(context,'_seal',_SEAL);guard();return context


def restore_native_context(value,*,guard=lambda:None):
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or len(canonical(value))>8*1024**2 or value['context_sha256']!=identity({k:v for k,v in value.items() if k!='context_sha256'})):raise ValueError('closed original native scenario context required')
    result=prepare_native_context(value['capture'],runtime=value['runtime'],expected_capture_sha256=value['capture_sha256'],expected_artifact_sha256=value['artifact_sha256'],guard=guard)
    if canonical(result.to_dict())!=canonical(value):raise ValueError('original native context differs')
    return result


def geometry_positions(context):
    value=context.to_dict();packet=value['capture']['geometry']
    geometry=replay_series(canonical(packet),request=packet['request'],expected_series_sha256=value['capture']['geometry_series_sha256'],expected_native_runtime=packet['native_runtime'])
    return geometry,[{k:p[k] for k in ('at','elevation_degrees','azimuth_degrees')} for cache in packet['caches'] for p in cache['positions']]


def _dependencies(context,guard):
    value=context.to_dict();_runtime(value['runtime'],guard);capture=value['capture']
    for role,reference in capture['candidate']['originals'].items():
        guard();raw,_=_read(Path(reference['path']),LIMITS[role])
        if sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('original native fitted dependency changed')
    import native_thermal_forecast as native
    native.replay_binding(capture['native_origin_binding'],capture['inputs']['origin_temperatures'],issue_at=instant(capture['issued_at']),check_budget=guard)
    if capture.get('weather_conditioning') is not None:
        from thermal_weather_source import verify_bindings
        verify_bindings(capture['weather_conditioning'],guard=guard)


def _forcings(rows,origin,hours,actions):
    from household_pv_components import _point
    from thermal_model.installed_shade_origin import ending_hour_mean
    from thermal_model.installed_shade_dynamics import InstalledShadeForcing,STEP
    times=[instant(r['at']) for r in rows];radiation=[r['radiationWm2'] for r in rows];out=[]
    for i in range(1,hours*12+1):
        at=origin+i*STEP;temperature,_=_point(rows,times,at)
        out.append(InstalledShadeForcing(at,temperature,ending_hour_mean(times,radiation,at-STEP,at),actions['indoor_shade_closed'],actions['outdoor_shade_present'],actions['vent_open']))
    return tuple(out)


def project_native_scenario(scenario,context,*,positions,guard=lambda:None):
    from .scenarios import validate_scenario
    _require(context);v=validate_scenario(scenario);value=context.to_dict();capture=value['capture'];original=capture['inputs']['forecast'];base=v['original_forecast']
    if (v['origin']!=capture['issued_at'] or not 1<=v['horizon_hours']<=original['horizon_hours'] or base['snapshot_sha256']!=original['snapshot_sha256'] or base['site']!=original['site'] or len(base['rows'])>len(original['rows'])):raise ValueError('scenario must use the original native capture weather and origin')
    keys=('at','tempF','radiationWm2','windMph','weatherCode')
    if canonical([{k:r[k] for k in keys} for r in base['rows']])!=canonical(original['rows'][:len(base['rows'])]):raise ValueError('original native scalar weather differs')
    _dependencies(context,guard);geometry,expected_positions=geometry_positions(context);count=v['horizon_hours']*12
    if canonical(positions)!=canonical(expected_positions[:count]):raise ValueError('scenario must retain exact original native geometry')
    output=capture['output'];initial=output['initial'];actions=output['origin_actions'];origin=instant(v['origin'])
    forcings=_forcings(v['rows'],origin,v['horizon_hours'],actions)
    if capture.get('weather_conditioning') is not None:
        forcings=_condition(forcings,v['rows'],capture,initial['outdoor_f'])
    profile=fit_profile(capture['candidate']['fit']);model=profile['model'](tuple(capture['candidate']['fit']['coefficients']),geometry=geometry,expected_series_sha256=geometry.sha256)
    rolled=model.rollout(origin_at=origin,air_f=initial['air_f'],mass_f=initial['mass_f'],forcings=forcings,guard=guard)
    trajectory=[dict(at=r.at.isoformat(),air_f=state[0],mass_f=state[1]) for i,(r,state) in enumerate(zip(forcings,rolled.states),1) if i%12==0]
    parity=None
    if v['recipe']['name']=='central':
        parity=max(abs(r[name]-saved[name]) for r,saved in zip(trajectory,output['trajectory']) for name in ('air_f','mass_f'))
        if parity>1e-9:raise ValueError('central native scenario no longer matches original model trajectory')
    _dependencies(context,guard)
    return dict(status='unqualified_native_model_sensitivity',reason=None,indoor_air_f=trajectory[-1]['air_f'],north_wall_f=trajectory[-1]['mass_f'],trajectory=trajectory,initial=initial,origin_actions=actions,model_sha256=value['artifact_sha256'],model_rule=profile['rule'],model_runtime_sha256=capture['candidate']['runtime_sha256'],original_capture_sha256=value['capture_sha256'],native_geometry_sha256=geometry.sha256,central_parity_max_abs_f=parity,radiation_input_scope='same original native scalar forecast field; components do not replace a local proxy or fitted heat-gain basis',weather_conditioning='original admitted model capsules reapplied to constructed rows' if capture.get('weather_conditioning') is not None else 'original unconditioned native input contract',physical_calibration_qualified=False,probability_claim=False,automatic_actuation=False)


def _condition(forcings,rows,capture,initial_outdoor_f):
    """Compose existing correction kernels for constructed rows, not original receipts."""
    from bisect import bisect_left
    from dataclasses import replace
    from types import SimpleNamespace
    from household.thermal_weather_conditioning import validate_context
    from .site_calibration import _calculate
    from .historical_serving import temperature_features
    from .irradiance_learning import irradiance_features
    from household_solar_horizon import horizon_height
    from household_pv_components import _point
    from thermal_model.installed_shade_origin import ending_hour_mean
    issue=instant(capture['issued_at']);available=instant(capture['inputs_available_at'])
    original=validate_context(capture['weather_conditioning'],issue=issue,available=available)
    if [r['at'] for r in rows]!=[r['at'] for r in original['rows']]:raise ValueError('constructed conditioning must retain exact original time grid')
    models=original['admission']['models'];times=[instant(r['at']) for r in rows]
    raw_origin=rows[0]['tempF'] if times[0]==issue else _point(rows,times,issue)[0]
    bias=(initial_outdoor_f-raw_origin)*5/9;temperatures={};radiation=[]
    points={p['at']:p for p in original['midpoint_positions']}
    for row,at in zip(rows,times):
        corrected=row['radiationWm2']
        if at>issue:
            raw_c=(row['tempF']-32)*5/9;features=temperature_features(SimpleNamespace(target_at=at,mean_c=raw_c),origin=issue,origin_bias_c=bias,timezone_name=original['timezone'])
            temperatures[at]=max(-40.,min(60.,_calculate(models['outdoor_temperature_c'],features,raw_c)))*9/5+32
            p=points[(at-timedelta(minutes=30)).isoformat()]
            if p['elevation_degrees']>0:
                position=dict(p,horizon_elevation_degrees=horizon_height(original['admission']['horizon_profile'],p['azimuth_degrees']))
                features=irradiance_features(corrected,lead_hours=(at-issue).total_seconds()/3600,target=at,position=position)
                corrected=max(0.,min(1600.,_calculate(models['irradiance_w_m2'],features,corrected)))
        radiation.append(corrected)
    first_future=next(t for t in times if t>issue);out=[];start=issue
    for row in forcings:
        i=bisect_left(times,row.at)
        if not 1<=i<len(times):raise ValueError('complete constructed conditioning brackets required')
        if row.at<=first_future:temperature=initial_outdoor_f+(row.at-issue)/(first_future-issue)*(temperatures[first_future]-initial_outdoor_f)
        else:temperature=temperatures[times[i-1]]+(row.at-times[i-1])/(times[i]-times[i-1])*(temperatures[times[i]]-temperatures[times[i-1]])
        out.append(replace(row,outdoor_f=temperature,radiation_wm2=ending_hour_mean(times,radiation,start,row.at)));start=row.at
    return tuple(out)
