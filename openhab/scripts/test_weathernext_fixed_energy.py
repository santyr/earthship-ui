"""Weather forcing changes inside an original replayed array/storage model."""
from copy import deepcopy
from datetime import timedelta
import pytest
from household.codec import canonical
from household.control_contracts import instant
from test_household_native_weather import originals
from test_household_energy_forecast import fixture
from weather_learning.config import Site,COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
from weather_learning.energy_shadow import compare_fixed_energy


def google(origin,*,ghi=1000,missing=False):
 init=origin.replace(minute=0,second=0,microsecond=0)-timedelta(hours=8)
 site=Site(38.3739919,-105.7744609,'America/Denver');parts=[]
 for grid,bands,lat,lon in (
  ('station',['station_head_temperature_2m_mean'],38.35,-105.75),
  ('gridded',['surface_solar_radiation_downwards_1hr_mean','wind_speed_10m_mean'],38.4,-105.8)):
  metadata=[];region=[['id','longitude','latitude','time',*bands]]
  for hour in range(1,49):
   at=init+timedelta(hours=hour);name='hour'+str(hour)
   metadata.append({'system:index':name,'system:time_start':init.timestamp()*1000,'start_time':init.isoformat(),'end_time':at.isoformat(),'forecast_hour':hour,'ingestion_time_utc':init.timestamp()*1000+1000})
   values=[280.] if grid=='station' else [None if missing and hour==10 else ghi*3600,1.]
   region.append([name,lon,lat,init.timestamp()*1000,*values])
  parts.append(parse_collection_response(dict(metadata=metadata,region=region),collection=COLLECTIONS[grid],bands=bands,site=site,initialized_at=init,horizon=48))
 return make_snapshot(parts,site=site,initialized_at=init,first_seen_at=origin-timedelta(hours=1),completed_at=origin-timedelta(minutes=30))


def setup(tmp_path,monkeypatch,originals):
 api,args,plan=fixture(tmp_path,monkeypatch,originals);energy=api.seal_energy_forecast(**args)
 origin=instant(energy['output']['array_pv']['origin'])
 return api,args,plan,energy,origin


def test_changes_only_weather_and_keeps_battery_load_geometry_and_model_fixed(tmp_path,monkeypatch,originals):
 api,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals);snapshot=google(origin)
 before=canonical(dict(plan=plan,energy=energy,google=snapshot))
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=snapshot,assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
 assert result['status']=='COMPARED',result
 assert result['control']['array_pv']==energy['output']['array_pv']
 assert result['control']['nominal_storage']==energy['output']['nominal_storage']
 assert result['google']['array_pv']['array']==result['control']['array_pv']['array']
 assert result['google']['array_pv']['assumptions']==result['control']['array_pv']['assumptions']
 for key in ('initial_soc_pct','nominal_bank_kwh','household_ac_load_w_assumption','source_evidence_sha256','assumptions'):
  assert result['google']['nominal_storage'][key]==result['control']['nominal_storage'][key]
 assert result['google']['array_pv']['potential_pv_kwh']!=result['control']['array_pv']['potential_pv_kwh']
 assert canonical(dict(plan=plan,energy=energy,google=snapshot))==before
 assert result['automatic_actuation'] is False and result['weather_weights_imported'] is False
 assert result['qualification']=='SHADOW_ONLY'


@pytest.mark.parametrize('damage',['future','historical','missing','site'])
def test_ineligible_google_source_keeps_original_control_but_has_no_fake_google_prediction(tmp_path,monkeypatch,originals,damage):
 _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals);snapshot=google(origin,missing=damage=='missing')
 if damage=='future':snapshot['ingestion_completed_at']=(origin+timedelta(seconds=1)).isoformat()
 if damage=='historical':snapshot['historical']=True
 if damage=='site':snapshot['site']['latitude']=38.39
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=snapshot,assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
 assert result['status']=='UNAVAILABLE'
 assert result['google'] is None and result['control']['array_pv']==energy['output']['array_pv']


def test_unavailable_storage_does_not_discard_independently_valid_array_potential(tmp_path,monkeypatch,originals):
 api,args,plan,_,origin=setup(tmp_path,monkeypatch,originals);args['topology_source']=None
 energy=api.seal_energy_forecast(**args)
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
 assert result['status']=='COMPARED'
 assert result['google']['array_pv']['potential_pv_kwh'] is not None
 assert result['google']['nominal_storage']['status']=='unavailable'
 assert result['google']['nominal_storage']['trajectory']==[]


def test_resource_potential_is_separate_from_demand_limited_harvest_and_no_actuals_are_invented(tmp_path,monkeypatch,originals):
 _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin,ghi=1500),assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
 pv=result['google']['array_pv'];storage=result['google']['nominal_storage']
 assert pv['potential_pv_kwh']>=storage['modeled_captured_pv_kwh']
 assert storage['modeled_unaccepted_pv_kwh']>0
 assert result['outcomes']['measured_captured_pv_kwh'] is None
 assert result['outcomes']['measured_available_pv_kwh'] is None
 assert result['outcomes']['score_status']=='NOT_SCORED'


def test_current_runtime_change_cannot_masquerade_as_original_numerical_model(tmp_path,monkeypatch,originals):
 api,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
 runtime=api.forecast_runtime_manifest();runtime['openhab/scripts/household_pv_model.py']='f'*64
 monkeypatch.setattr(api,'forecast_runtime_manifest',lambda:runtime)
 with pytest.raises(ValueError):compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))


def test_report_completion_cannot_backdate_prospective_scoring_of_started_hour(tmp_path,monkeypatch,originals):
 _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=origin+timedelta(hours=1,minutes=5),clock=lambda:origin+timedelta(hours=1,minutes=5))
 flags=result['prospective_ending_hours']
 assert flags['1'] is False and flags['2'] is False and flags['3'] is True


def test_runtime_change_during_comparison_is_refused_before_return(tmp_path,monkeypatch,originals):
 api,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
 before=api.forecast_runtime_manifest();after=dict(before);after['openhab/scripts/household_pv_model.py']='f'*64
 calls=[]
 def current():
  calls.append(True)
  return before if len(calls)==1 else after
 monkeypatch.setattr(api,'forecast_runtime_manifest',current)
 with pytest.raises(ValueError):compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))


def test_actual_completion_clock_prevents_claiming_an_already_started_hour(tmp_path,monkeypatch,originals):
 _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin),
     assessed_at=args['now']+timedelta(seconds=1),clock=lambda:origin+timedelta(hours=1,minutes=5))
 assert result['completed_at']==(origin+timedelta(hours=1,minutes=5)).isoformat()
 assert result['prospective_ending_hours']['2'] is False
 assert result['prospective_ending_hours']['3'] is True


def test_original_learned_AC_profile_is_held_fixed_when_only_weather_changes(tmp_path,monkeypatch,originals):
 from household_profiled_forecast import seal_profiled_forecast,profiled_runtime_manifest
 from test_household_profiled_forecast import supported_source
 api,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
 source,load_runtime=supported_source(origin)
 profile=seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=source,now=args['now'],
     runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=api.forecast_runtime_manifest(),load_runtime_manifest=load_runtime)
 before=canonical(profile)
 result=compare_fixed_energy(energy,plan_receipt=plan,google_snapshot=google(origin),profiled_reference=profile,
     assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
 assert result['control']['profiled']==profile['output']
 replacement=result['google']['profiled']['profiled_storage']
 assert result['google']['profiled']['status']=='conditional_nominal_simulation'
 assert replacement['load_forecast_sha256']==profile['output']['load_forecast']['forecast_sha256']
 assert replacement['household_ac_load_w_assumptions']==profile['output']['profiled_storage']['household_ac_load_w_assumptions']
 assert replacement['initial_soc_pct']==profile['output']['profiled_storage']['initial_soc_pct']
 assert result['original_profiled_sha256'] is not None and canonical(profile)==before
