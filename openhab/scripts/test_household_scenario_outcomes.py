"""Household sensitivity errors use original qualified targets and matching windows."""
from copy import deepcopy
from datetime import timedelta
import importlib,json
from unittest.mock import patch
import pytest
from test_household_weather_scenarios import ORIGIN,ARRAY,HORIZON,SITE,cases
from native_solar_fixtures import geometry
from weather_learning.contracts import canonical,identity,instant

EPOCH='00000000-0000-4000-8000-000000000001'
PHASE='00000000-0000-4000-8000-000000000002'
END=ORIGIN+timedelta(hours=1);ASSESSED=END+timedelta(minutes=6)
def api():return importlib.import_module('weather_learning.scenario_household')


def inputs():
 import test_weather_energy_history as energy
 from household.battery_outcomes import build_endpoint_source
 from local_measurement_test_support import bms_evidence
 from weather_temperature_evidence import TemperaturePolicy,MODELS
 from weather_temperature_receiver import TemperatureCollector
 from weather_temperature_sources import build_temperature_source
 from thermal_model.temperature_history import STREAMS,POLICY
 p=json.dumps(dict(version=1,policy='qualified_power_evidence_v1',item_name='Power_Evidence_JSON',cutover=(ORIGIN-timedelta(days=1)).isoformat()))
 with patch.multiple(energy,START=ORIGIN,END=END,POLICY=p):energy_source=energy.source(soc=70)
 from zoneinfo import ZoneInfo
 from datetime import datetime
 energy_source['bank_start']=datetime(2026,6,1,tzinfo=ZoneInfo('America/Denver')).astimezone(ORIGIN.tzinfo).isoformat()
 energy_source['source_sha256']=identity({k:v for k,v in energy_source.items() if k!='source_sha256'})
 endpoints={}
 for at in [ORIGIN,END]:
  observed=at-timedelta(seconds=10);raw=json.loads(bms_evidence(observed,soc=70));raw['streamEpoch']=EPOCH
  endpoints[at.isoformat()]=build_endpoint_source(rows=[(observed,json.dumps(raw))],target_at=at,requested_at=at+timedelta(minutes=5),received_at=at+timedelta(minutes=5,seconds=1),item_id=613)
 temperatures={}
 for role,number in [('air',75),('mass',72)]:
  stream,model,sensor_id=STREAMS[role];policy=TemperaturePolicy(model,sensor_id,**POLICY);at=END-timedelta(seconds=10)
  collector=TemperatureCollector({stream:policy},sensor_epochs={stream:PHASE},clock=lambda:at,process_id=lambda:1,monotonic=lambda:1000.)
  collector.observe({'model':model,'id':str(sensor_id),MODELS[model][1]:str(number)})
  temperatures[role]=build_temperature_source(rows=[(at,json.dumps(collector.snapshot()))],targets=[END],assessed_at=ASSESSED,stream=stream,policy=policy,sensor_epoch=PHASE)
 bank=json.dumps(dict(version=1,timezone='America/Denver',epochs=[dict(id='synthetic-bank',start_local_date='2026-06-01',end_local_date_exclusive=None,current_analytics=True,nominal_usable_kwh=10.)]))
 return dict(start=ORIGIN,end=END,assessed_at=ASSESSED,energy_sources=[energy_source],battery_endpoint_sources=endpoints,temperature_sources=temperatures,source_epoch=EPOCH,sensor_epochs={'air':PHASE,'mass':PHASE},bank_config_raw=bank,bank_epoch='synthetic-bank',nominal_bank_kwh=10.,initial_soc_pct=70.)


def projections():
 from weather_learning.scenarios import propagate
 return [propagate(s,positions=geometry(start=ORIGIN,count=12),array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=70.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=None) for s in cases(hours=1)]


def test_targets_replay_native_sources_and_keep_potential_captured_and_hourly_SOC_distinct():
 args=inputs();before=canonical({k:v for k,v in args.items() if k not in ('start','end','assessed_at')});value=api().household_targets(**args);r=value.to_dict()['targets']
 assert r['potential_array_proxy_kwh']['value']==pytest.approx(1.)
 assert r['captured_controller_dc_kwh']['value']==pytest.approx(1.)
 assert r['minimum_hour_grid_soc_pct']['value']==70.
 assert r['indoor_air_f']['value']==75. and r['north_wall_f']['value']==72.
 assert r['minimum_hour_grid_soc_pct']['basis']=='origin_and_elapsed_hour_endpoints; not continuous trough'
 assert r['potential_array_proxy_kwh']['physical_calibration_qualified'] is False
 assert api().HouseholdTargets(value.content).to_dict()==value.to_dict()
 assert canonical({k:v for k,v in args.items() if k not in ('start','end','assessed_at')})==before


def test_household_scores_compare_original_simulations_and_never_fill_missing_thermal_prediction():
 target=api().household_targets(**inputs());pred=projections();r=api().score_household(pred,targets=target)
 assert r['support']['forecast_origins']==1 and r['support']['local_dates']==1 and r['support']['scenarios']==3
 for row,p in zip(r['scenarios'],pred):
  assert row['errors']['potential_array_proxy_kwh']==pytest.approx(p['pv']['potential_pv_kwh']-1.)
  assert row['errors']['captured_controller_dc_kwh']==pytest.approx(p['nominal_storage']['modeled_captured_pv_kwh']-1.)
  assert row['errors']['minimum_hour_grid_soc_pct']==pytest.approx(p['minimum_nominal_soc_pct']-70.)
  assert row['errors']['indoor_air_f'] is row['errors']['north_wall_f'] is None
 assert r['disposition']=='insufficient_evidence' and r['probability_claim'] is r['automatic_actuation'] is False


def test_censored_potential_and_incomplete_capture_are_withheld_without_becoming_zero():
 args=inputs();args['energy_sources'][0]['rows']['power'][1][1]='invalid';s=args['energy_sources'][0];s['source_sha256']=identity({k:v for k,v in s.items() if k!='source_sha256'})
 targets=api().household_targets(**args).to_dict()['targets']
 assert targets['potential_array_proxy_kwh']['value'] is None
 assert targets['captured_controller_dc_kwh']['value'] is None
 assert targets['minimum_hour_grid_soc_pct']['value']==70.


@pytest.mark.parametrize('damage',['future','epoch','target','bank','origin'])
def test_future_or_wrong_scope_household_sources_are_refused_or_withheld(damage):
 args=inputs()
 if damage=='future':args['assessed_at']=END-timedelta(minutes=1)
 elif damage=='epoch':args['source_epoch']='00000000-0000-4000-8000-000000000003'
 elif damage=='target':args['temperature_sources']['air']['targets']=[(END+timedelta(hours=1)).isoformat()]
 elif damage=='bank':args['nominal_bank_kwh']=11.
 else:args['initial_soc_pct']=99.
 if damage in ('future','target','bank'):
  with pytest.raises(ValueError):api().household_targets(**args)
 else:
  target=api().household_targets(**args).to_dict()['targets']['minimum_hour_grid_soc_pct'];assert target['value'] is None and target['reason']


def test_resealed_derived_household_values_cannot_bypass_original_source_replay():
 value=api().household_targets(**inputs()).to_dict();value['targets']['captured_controller_dc_kwh']['value']=0.
 value['target_sha256']=identity({k:v for k,v in value.items() if k!='target_sha256'})
 with pytest.raises(ValueError):api().HouseholdTargets(canonical(value))


def fractional_inputs():
 args=inputs();offset=timedelta(seconds=15);start,end=args['start']+offset,args['end']+offset
 from household.battery_outcomes import build_endpoint_source
 args['battery_endpoint_sources']={}
 for key,source in inputs()['battery_endpoint_sources'].items():
  target=instant(key)+offset
  args['battery_endpoint_sources'][target.isoformat()]=build_endpoint_source(rows=[(instant(at),raw) for at,raw in source['rows']],target_at=target,requested_at=instant(source['requested_at'])+offset,received_at=instant(source['received_at'])+offset,item_id=source['item_id'])
 import test_weather_energy_history as energy
 from test_household_pv_window import raw
 policy=args['energy_sources'][0]['policy_raw']
 with patch.multiple(energy,START=END,END=END+timedelta(hours=1),POLICY=policy):following=energy.source(soc=70)
 following['rows']['power']=[[at,raw(instant(at),61+i,2000)] for i,(at,_) in enumerate(following['rows']['power'])]
 following['bank_start']=args['energy_sources'][0]['bank_start'];following['source_sha256']=identity({k:v for k,v in following.items() if k!='source_sha256'})
 args['energy_sources'].append(following);args.update(start=start,end=end,assessed_at=END+timedelta(hours=1,minutes=6))
 from weather_temperature_sources import build_temperature_source
 from weather_temperature_evidence import TemperaturePolicy
 args['temperature_sources']={role:build_temperature_source(rows=[(instant(at),raw) for at,raw in packet['native_rows']],targets=[end],assessed_at=args['assessed_at'],stream=packet['stream'],policy=TemperaturePolicy(**packet['policy']),sensor_epoch=packet['sensor_epoch']) for role,packet in args['temperature_sources'].items()}
 return args


def test_fractional_native_origin_scores_exact_power_overlap_and_unshifted_endpoint_truth():
 args=fractional_inputs();targets=api().household_targets(**args).to_dict()['targets']
 expected=(3585*1000+15*2000)/3600000
 assert targets['potential_array_proxy_kwh']['value']==pytest.approx(expected)
 assert targets['captured_controller_dc_kwh']['value']==pytest.approx(expected)
 assert targets['minimum_hour_grid_soc_pct']['value']==70.
 assert targets['indoor_air_f']['value']==75. and targets['north_wall_f']['value']==72.


def test_fractional_window_missing_boundary_hour_withholds_energy_only():
 args=fractional_inputs();args['energy_sources']=args['energy_sources'][:1]
 targets=api().household_targets(**args).to_dict()['targets']
 assert targets['potential_array_proxy_kwh']['value'] is None
 assert targets['captured_controller_dc_kwh']['value'] is None
 assert targets['minimum_hour_grid_soc_pct']['value']==70.
 assert targets['indoor_air_f']['value']==75.



def padded_energy_inputs(hours,rows_per_hour,width):
 import test_weather_energy_history as energy
 from test_household_pv_window import raw
 args=inputs();policy=args['energy_sources'][0]['policy_raw'];sources=[]
 for hour in range(hours):
  start=ORIGIN+timedelta(hours=hour)
  with patch.multiple(energy,START=start,END=start+timedelta(hours=1),POLICY=policy):source=energy.source(soc=70)
  source['rows']['power']=[]
  for index in range(rows_per_hour):
   at=start+timedelta(seconds=index*3600/rows_per_hour);value=raw(at,index+1,1000);source['rows']['power'].append([at.isoformat(),value+' '*max(0,width-len(value))])
  source['bank_start']=args['energy_sources'][0]['bank_start'];source['source_sha256']=identity({k:v for k,v in source.items() if k!='source_sha256'});sources.append(source)
 args.update(end=ORIGIN+timedelta(hours=hours),assessed_at=ORIGIN+timedelta(hours=hours+1),energy_sources=sources,battery_endpoint_sources={},temperature_sources={})
 return args


def test_full_24h_original_energy_collection_can_exceed_single_receipt_bound():
 args=padded_energy_inputs(24,300,2500)
 assert len(canonical(args['energy_sources']))>16*1024**2
 result=api().household_targets(**args)
 assert result.to_dict()['targets']['captured_controller_dc_kwh']['value']==pytest.approx(24.)
 assert result.to_dict()['targets']['potential_array_proxy_kwh']['value']==pytest.approx(24.)
 assert api().HouseholdTargets(result.content).to_dict()==result.to_dict()


def test_outcome_collection_does_not_admit_oversized_individual_energy_receipt():
 args=padded_energy_inputs(1,6000,3000)
 with pytest.raises(ValueError):api().household_targets(**args)


def test_household_outcome_record_refuses_valid_aggregate_over_48_mib():
 args=padded_energy_inputs(4,4500,3000)
 assert all(len(canonical(s))<16*1024**2 for s in args['energy_sources'])
 with pytest.raises(ValueError):api().household_targets(**args)
