"""Weather-only attribution under an original fixed thermal numerical runtime.

This temporary pre-cutover control adapter never creates a model artifact or
relabels a modified forcing sequence as an original prepared projection.
"""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from .contracts import identity,instant
from .evidence import utc
from .features import prospective_snapshot


def _source_manifest():
    directory=Path(__file__).resolve().parent
    names=('thermal_shadow.py','features.py','contracts.py','config.py','normalize.py','weathernext_ee.py','evidence.py')
    return {'weather_learning/'+name:sha256((directory/name).read_bytes()).hexdigest() for name in names}


def compare_fixed_thermal(reference,*,plan_receipt,google_snapshot,assessed_at,clock=lambda:datetime.now(timezone.utc)):
    """Use original source modules on sys.path; hash their executing bytes afresh.

    Replay the bound plan/energy control before using its original thermal
    capsule. Preserve the control's hourly interpolation and five-minute native
    geometry. A later completion may make early hours retrospective; it never
    backdates availability or turns this attribution into a prospective issue.
    """
    from household_energy_forecast import forecast_runtime_manifest,replay_energy_forecast
    from household.model_snapshot import restore_snapshot
    from household.thermal_model import project,_geometry
    from native_thermal_model import NativeInstalledShadeDynamics,RULE
    from thermal_model.installed_shade_dynamics import InstalledShadeForcing
    assessed_at=utc(assessed_at);sources=_source_manifest();runtime=forecast_runtime_manifest()
    reference=replay_energy_forecast(reference,plan_receipt=plan_receipt,runtime_manifest=runtime)
    if assessed_at<instant(reference['inputs']['assessed_at']):raise ValueError('comparison precedes original control availability')
    snapshot=restore_snapshot(plan_receipt['inputs']['snapshot'],plan_receipt['inputs']['source_contexts'])
    weather=snapshot.weather;prepared=weather.prepared;value=prepared.to_dict()
    if value['schema']!='earthship-household-prepared-thermal/v2':raise ValueError('original native thermal control required')
    original=project(prepared);geometry=_geometry(value);origin=instant(value['issue'])
    body=dict(schema='earthship-weathernext-fixed-thermal-attribution/v1',qualification='SHADOW_ONLY',
        status='UNAVAILABLE',reason=None,origin=origin.isoformat(),assessed_at=assessed_at.isoformat(),
        original_energy_sha256=identity(reference),original_plan_sha256=identity(plan_receipt),
        original_prepared_sha256=value['prepared_sha256'],original_capture_sha256=value['original_capture_sha256'],
        artifact_sha256=value['artifact_sha256'],model_rule=value['model_rule'],fixed_runtime_sha256=identity(runtime),
        attribution_source_manifest=sources,geometry_series_sha256=value['geometry_series_sha256'],
        fixed_inputs={key:value[key] for key in ('coefficients','initial','actions','horizon_hours')},
        control=dict(provider='openmeteo',output=original['output']),google=None,
        changed_inputs=['hourly_station_temperature','hourly_ghi'],
        forcing_rule='original_linear_hourly_interpolation_on_same_native_five_minute_grid',
        native_direct_radiation_used=False,weather_weights_imported=False,model_fitting=False,
        comparison_scope='fixed_model_weather_forcing_attribution_only',
        outcomes=dict(score_status='NOT_SCORED',measured_hourly_air_f=None),prospective_ending_hours={},
        physical_calibration_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    try:
        google=prospective_snapshot(google_snapshot,issued_at=origin)
        descriptor=geometry.descriptor();site=descriptor['site']
        if (google['site']['latitude'],google['site']['longitude'],google['site']['timezone'])!=(site['latitude'],site['longitude'],descriptor['timezone']):
            raise ValueError('authoritative thermal/Google site differs')
        index={(p['variable'],instant(p['valid_at'])):p['value'] for p in google['points'] if p['statistic']=='mean'}
        from household.weather_context import project_weather
        context=project_weather(weather);hourly=[]
        for row in context['hourly_forecast']:
            at=instant(row['at']);temp=index.get(('station_head_temperature_2m',at));ghi=index.get(('surface_solar_radiation_downwards_1hr',at))
            if temp is None or ghi is None:raise ValueError('complete Google temperature/GHI required')
            hourly.append((at,temp*9/5+32,ghi))
        forcings=[];i=0
        for row in value['forcings']:
            at=instant(row['at'])
            while i+1<len(hourly)-1 and hourly[i+1][0]<at:i+=1
            left,right=hourly[i],hourly[i+1];fraction=(at-left[0])/(right[0]-left[0])
            if not 0<=fraction<=1:raise ValueError('Google thermal forcing cannot extrapolate')
            forcings.append(InstalledShadeForcing(**{**row,'at':at,'outdoor_f':left[1]+fraction*(right[1]-left[1]),
                'radiation_wm2':left[2]+fraction*(right[2]-left[2])}))
        import native_thermal_artifact
        selector=getattr(native_thermal_artifact,'fit_profile',None)
        if selector is not None:
            profile=selector(weather.original_capture['candidate']['fit'])
            if profile['rule']!=value['model_rule']:raise ValueError('original thermal model family differs')
            model_type=profile['model']
        else:
            if value['model_rule']!=RULE:raise ValueError('unsupported original thermal model family')
            model_type=NativeInstalledShadeDynamics
        initial=value['initial'];model=model_type(tuple(value['coefficients']),geometry=geometry,expected_series_sha256=value['geometry_series_sha256'])
        rolled=model.rollout(origin_at=origin,air_f=initial['air'],mass_f=initial['mass'],forcings=tuple(forcings))
        trajectory=[dict(at=row.at.isoformat(),air_f=state[0],mass_f=state[1]) for n,(row,state) in enumerate(zip(forcings,rolled.states),1) if n%12==0]
        body.update(status='COMPARED',google=dict(provider='weathernext3',trajectory=trajectory,
            first_forcing=asdict(forcings[0])|{'at':forcings[0].at.isoformat()},
            forcings_sha256=identity([asdict(row)|{'at':row.at.isoformat()} for row in forcings])),
            google_snapshot_sha256=google['snapshot_sha256'],google_initialized_at=google['initialized_at'],
            google_available_at=google['ingestion_completed_at'])
    except (ValueError,KeyError,TypeError,OverflowError):
        body['reason']='GOOGLE_FORCING_UNAVAILABLE_OR_INCOMPATIBLE'
    if forecast_runtime_manifest()!=runtime or _source_manifest()!=sources:
        raise ValueError('fixed numerical or attribution source changed during comparison')
    completed=utc(clock())
    if completed<assessed_at:raise ValueError('comparison completion precedes assessment')
    body['completed_at']=completed.isoformat()
    if body['status']=='COMPARED':
        body['prospective_ending_hours']={str(h):completed<=origin+timedelta(hours=h-1) for h in range(1,value['horizon_hours']+1)}
    return body|{'report_sha256':identity(body)}
