"""Thermal input uses already emitted temperature points, never a second model."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from test_production_forecast import serving,NOW
from test_production_public import confirmed
from weather_learning.contracts import canonical,identity,instant

@pytest.fixture
def context_case(serving,tmp_path):
 from weather_learning.production_public import retain_public_view
 import thermal_weather_source as source
 state,product,emission=confirmed(serving,tmp_path);view=retain_public_view(state,emission['emission_sha256'])
 body=product.to_dict();epoch=body['origin_contexts']['temperature']['sensor_epoch']
 issue=NOW+timedelta(minutes=5,seconds=15);hour=issue.replace(minute=0,second=0,microsecond=0)
 first=next(iter(body['source_originals'].values()))['site'];site={k:first[k] for k in ('latitude','longitude')};zone=first['timezone']
 geometry=SimpleNamespace(descriptor=lambda:{'site':site,'timezone':zone},to_dict=lambda:{'native_runtime':{'test':'original_native_geometry'}})
 forecast=dict(source='weathernext3',rows=[dict(at=(hour+timedelta(hours=i)).isoformat(),tempF=50.+i,radiationWm2=300.,windMph=2.) for i in range(4)])
 selection=dict(schema='earthship-thermal-weather-selection/v2',state_directory=str(state.root),source_sensor_epoch=epoch,
  available_at=(issue-timedelta(minutes=1)).isoformat(),runtime_sha256=identity(source.production_conditioning_runtime()),automatic_actuation=False)
 selection['selection_sha256']=identity(selection);path=tmp_path/'selection.json';path.write_bytes(canonical(selection));path.chmod(0o600)
 args=dict(selection=path,forecast=forecast,geometry=geometry,issue=issue,sensor_epoch=epoch,guard=lambda:None,clock=lambda:issue-timedelta(seconds=2))
 return source,args,state,body,emission,view

def test_actual_confirmed_points_replace_thermal_temperature_without_new_model_inference(context_case):
 source,args,state,body,emission,view=context_case
 value=source.collect_context(**args)
 assert value['schema']=='earthship-thermal-weather-context/v2' and value['mode']=='confirmed_production_temperature'
 assert value['production_emission_sha256']==emission['emission_sha256']
 assert value['source_sensor_epoch']==args['sensor_epoch']
 assert value['solar_policy']=='unchanged_native_ending_hour_horizontal_mean'
 assert value['automatic_actuation'] is False and value['physical_calibration_qualified'] is False
 actual=json.loads(emission['attempt_original']['states']['Forecast_10Day_JSON'])
 points={instant(p['at']):p['tempF'] for d in actual['days'] for p in d['hours']}
 assert all(p['temp_f']==points[instant(p['at'])] for p in value['points'])
 source.verify_bindings(value,guard=lambda:None)

def test_new_conditioning_interpolates_from_measured_initial_state_and_preserves_native_radiation_actions(context_case):
 from household.thermal_weather_conditioning import apply_conditioning
 from thermal_model.installed_shade_dynamics import InstalledShadeForcing
 source,args,*_=context_case;value=source.collect_context(**args);issue=args['issue']
 target=issue+timedelta(minutes=5);fraction=(target-target.replace(minute=0,second=0,microsecond=0)).total_seconds()/3600
 raw=InstalledShadeForcing(target,50.+fraction,300.,.25,0.,1.)
 result=apply_conditioning((raw,),value,issue=issue,available=args['clock'](),initial_outdoor_f=53.)
 first=value['points'][0];weight=(target-issue)/(instant(first['at'])-issue)
 assert result[0].outdoor_f==pytest.approx(53.+weight*(first['temp_f']-53.))
 assert result[0].radiation_wm2==raw.radiation_wm2
 assert (result[0].indoor_shade_closed,result[0].outdoor_shade_present,result[0].vent_open)==(.25,0.,1.)
 assert raw.outdoor_f==50.+fraction

@pytest.mark.parametrize('damage',['missing','expired','wrong_phase'])
def test_unusable_production_temperatures_are_named_raw_fallbacks(context_case,damage):
 from household.thermal_weather_conditioning import apply_conditioning
 from thermal_model.installed_shade_dynamics import InstalledShadeForcing
 source,args,state,*_=context_case
 if damage=='missing':(state.root/'production-forecast.json').unlink()
 elif damage=='expired':args['clock']=lambda:args['issue']+timedelta(hours=2)
 else:args['sensor_epoch']='different-thermal-outdoor-phase'
 if damage=='expired':
  args['issue']+=timedelta(hours=2);args['clock']=lambda:args['issue']-timedelta(seconds=2)
  for row in args['forecast']['rows']:row['at']=(instant(row['at'])+timedelta(hours=2)).isoformat()
 value=source.collect_context(**args)
 assert value['mode']=='native_raw_fallback' and value['reason'].startswith('production_temperature_')
 assert value['points']==[]
 raw=InstalledShadeForcing(args['issue']+timedelta(minutes=5),51.,300.,1.,0.,0.)
 assert apply_conditioning((raw,),value,issue=args['issue'],available=args['clock'](),initial_outdoor_f=53.)==(raw,)

def test_changed_immutable_confirmation_refuses_existing_frozen_thermal_context(context_case):
 source,args,state,body,emission,_=context_case;value=source.collect_context(**args)
 path=state.root/'production-emissions'/(emission['emission_sha256']+'.json');path.write_bytes(path.read_bytes()+b'\\n')
 with pytest.raises(ValueError):source.verify_bindings(value,guard=lambda:None)

def test_retained_thermal_replay_uses_its_original_confirmation_after_latest_view_moves(context_case):
 source,args,state,*_=context_case;value=source.collect_context(**args)
 (state.root/'production-forecast.json').unlink()
 source.verify_bindings(value,guard=lambda:None)
 assert value['mode']=='confirmed_production_temperature'

def test_thermal_collection_never_refits_or_runs_weather_models_again(context_case,monkeypatch):
 source,args,*_=context_case
 import weather_learning.production_forecast as forecast
 import weather_learning.production_model_admission as admission
 def forbidden(*a,**k):pytest.fail('weather inference or compilation in thermal consumer')
 monkeypatch.setattr(forecast,'prepare_production_forecast',forbidden);monkeypatch.setattr(admission,'predict_production',forbidden)
 assert source.collect_context(**args)['mode']=='confirmed_production_temperature'

def test_new_context_requires_original_confirmation_points_and_closed_owner(context_case):
 from household.thermal_weather_conditioning import validate_context
 source,args,*_=context_case;value=source.collect_context(**args)
 for damage in ('point','clock','authority','owner'):
  bad=deepcopy(value)
  if damage=='point':bad['points'][0]['temp_f']+=1
  elif damage=='clock':bad['production_published_at']=(args['issue']+timedelta(seconds=1)).isoformat()
  elif damage=='authority':bad['automatic_actuation']=True
  else:bad['selection']['extra']='changed'
  if damage!='point':
   bad['context_sha256']=identity({k:v for k,v in bad.items() if k!='context_sha256'})
  with pytest.raises(ValueError):validate_context(bad,issue=args['issue'],available=args['clock'](),forecast=args['forecast'],sensor_epoch=args['sensor_epoch'])
