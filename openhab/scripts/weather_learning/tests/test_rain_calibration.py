"""Complete rain intervals and gauge-aware events keep original source semantics."""
from copy import deepcopy
from datetime import date,datetime,time,timedelta,timezone
from importlib import import_module
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import pytest
from weather_learning.contracts import canonical,identity
from weather_learning.config import Site,COLLECTIONS
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot

POLICY=json.loads((Path(__file__).resolve().parents[4]/'docs/operations/weathernext3-capabilities/rain-calibration-protocol.json').read_bytes())
PRODUCTS=('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr')
def api():return import_module('weather_learning.rain_calibration')


def rain_snapshot(day=date(2026,10,20),zone='America/Denver',missing=None,hours=60):
 local=ZoneInfo(zone);start=datetime.combine(day,time.min,local).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),time.min,local).astimezone(timezone.utc)
 init=start-timedelta(hours=12);init=init.replace(hour=init.hour//6*6);site=Site(40.,-105.,zone);bands=[p+'_'+s for p in PRODUCTS for s in ('mean','p10','p50','p90')]
 raw=dict(metadata=[],region=[['id','longitude','latitude','time',*bands]])
 for h in range(1,hours+1):
  at=init+timedelta(hours=h);raw['metadata'].append(dict(**{'system:index':'rain'+str(h)},start_time=init.isoformat(),end_time=at.isoformat(),forecast_hour=h,ingestion_time_utc=init.timestamp()+900))
  values=[None if missing==p else .001*(i+1) if s=='mean' else 0. for i,p in enumerate(PRODUCTS) for s in ('mean','p10','p50','p90')]
  raw['region'].append(['rain'+str(h),site.longitude,site.latitude,at.timestamp()*1000,*values])
 source=parse_collection_response(raw,collection=COLLECTIONS['gridded'],bands=bands,site=site,initialized_at=init,horizon=hours)
 snapshot=make_snapshot([source],site=site,initialized_at=init,first_seen_at=init+timedelta(minutes=20),completed_at=init+timedelta(minutes=21))
 return snapshot,start,end


def forecast(day=date(2026,10,20),zone='America/Denver',**kwargs):
 snap,start,end=rain_snapshot(day,zone,**kwargs);issued=start-timedelta(hours=3)
 return api().make_forecast(snapshot=snap,start=start,end=end,issued_at=issued,completed_at=issued+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')


@pytest.mark.parametrize('day,hours',[(date(2026,3,8),23),(date(2026,11,1),25)])
def test_three_heads_use_actual_DST_day_and_never_add_marginal_quantiles(day,hours):
 value=forecast(day).to_dict()
 assert value['hours']==hours and value['products_mm']==dict(zip(PRODUCTS,[hours,2*hours,3*hours]))
 assert value['interval_kind']=='local_calendar_day' and value['as_issued_score'] is False
 assert len(value['hourly_statistics'][PRODUCTS[0]])==hours
 assert all(row['statistics']['p10']==row['statistics']['p50']==row['statistics']['p90']==0 for row in value['hourly_statistics'][PRODUCTS[0]])
 with pytest.raises(ValueError):api().total_depth(forecast(day),statistic='p10')
 assert api().RainForecast(canonical(value)).to_dict()==value


def test_rolling_24h_and_complete_remaining_hours_keep_distinct_targets():
 snap,start,end=rain_snapshot(date(2026,11,1));issued=start-timedelta(hours=3)
 rolling=api().make_forecast(snapshot=snap,start=start,end=start+timedelta(hours=24),issued_at=issued,completed_at=issued+timedelta(seconds=1),interval_kind='rolling_24_hours',availability_basis='recorded_ingestion_availability')
 assert rolling.to_dict()['products_mm'][PRODUCTS[0]]==24. and forecast(date(2026,11,1)).to_dict()['products_mm'][PRODUCTS[0]]==25.
 issued=start+timedelta(hours=8);completed=issued+timedelta(seconds=1)
 remaining=api().make_forecast(snapshot=snap,start=start+timedelta(hours=9),end=end,issued_at=issued,completed_at=completed,interval_kind='remaining_day',availability_basis='recorded_ingestion_availability')
 assert remaining.to_dict()['products_mm'][PRODUCTS[0]]==16. and remaining.to_dict()['hours']==16
 assert remaining.to_dict()['forecast_sha256']!=rolling.to_dict()['forecast_sha256']


def test_missing_head_keeps_others_but_excludes_the_whole_decision_from_matched_comparison():
 value=forecast(missing=PRODUCTS[1]).to_dict()
 assert value['products_mm'][PRODUCTS[0]]==24 and value['products_mm'][PRODUCTS[1]] is None and value['products_mm'][PRODUCTS[2]]==72
 assert value['common_complete_targets'] is False


def test_rain_forecast_replay_refuses_resealed_depth_and_wrong_interval_semantics():
 value=forecast().to_dict();value['products_mm'][PRODUCTS[0]]=0.;value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
 with pytest.raises(ValueError):api().RainForecast(canonical(value))
 snap,start,end=rain_snapshot(date(2026,11,1))
 with pytest.raises(ValueError):api().make_forecast(snapshot=snap,start=start,end=end,issued_at=start-timedelta(hours=3),completed_at=start-timedelta(hours=2),interval_kind='rolling_24_hours',availability_basis='recorded_ingestion_availability')


def test_fractional_first_hour_and_late_publication_cannot_be_labeled_complete_rain():
 snap,start,end=rain_snapshot()
 for issued,completed,left in [(start-timedelta(seconds=1),start,start),(start-timedelta(seconds=1),start+timedelta(seconds=1),start),(start-timedelta(hours=3),start-timedelta(hours=2),start+timedelta(seconds=15))]:
  with pytest.raises(ValueError):api().make_forecast(snapshot=snap,start=left,end=end,issued_at=issued,completed_at=completed,interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')


@pytest.mark.parametrize('observed,uncertainty,resolution,label',[(0.,0.,.254,'below_threshold'),(1.,0.,.254,'wet'),(.5,.2,.254,'ambiguous'),(.2,0.,.01,'ambiguous')])
def test_event_labels_bind_gauge_resolution_and_boundary_uncertainty(observed,uncertainty,resolution,label):
 result=api().classify_event(observed_mm=observed,uncertainty_mm=uncertainty,measured_resolution_mm=resolution,policy=POLICY)
 assert result['classification']==label
 assert result['threshold_mm']==pytest.approx(max(.2,2*resolution))
 assert result['physical_calibration_qualified'] is False
 assert result['event_label']==(1 if label=='wet' else 0 if label=='below_threshold' else None)


def test_missing_measured_resolution_preserves_depth_without_inventing_event_class():
 result=api().classify_event(observed_mm=2.,uncertainty_mm=.254,measured_resolution_mm=None,policy=POLICY)
 assert result['observed_mm']==2. and result['event_label'] is None
 assert result['reason']=='measured_resolution_required' and result['classification']=='insufficient_evidence'


def observed_inputs():
 from test_weather_rain_day import bounds,day_rows,POLICY as native_policy
 left,right=bounds()
 return dict(start=left,end=right,requested_at=right+timedelta(minutes=2),received_at=right+timedelta(minutes=2,seconds=1),cutover=left-timedelta(days=1),observations=day_rows(),policy=native_policy,resolution_source=None,experiment_policy=POLICY)


def resolution_document(args):
 from dataclasses import asdict
 return dict(schema='earthship-independent-rain-counter-resolution/v1',source_item='Weather_Rain_Evidence_JSON',sensor_id=args['policy'].sensor_id,observation_policy_sha256=identity(asdict(args['policy'])),basis='independently_counted_local_gauge_tips',measured_at=(args['start']-timedelta(days=3)).isoformat(),available_at=(args['start']-timedelta(days=2)).isoformat(),resolution_mm=.254,trials=[dict(counter_before_in=1.,counter_after_in=1.01,independent_tip_count=1),dict(counter_before_in=2.,counter_after_in=2.02,independent_tip_count=2),dict(counter_before_in=3.,counter_after_in=3.03,independent_tip_count=3)])


def test_rain_observation_replays_original_counters_and_uses_actual_acquisition_clock():
 args=observed_inputs();value=api().make_observation(**args);body=value.to_dict()
 assert body['observed_mm']==pytest.approx(2.54)
 assert body['available_at']==args['received_at'].isoformat()
 assert body['event']['classification']=='insufficient_evidence'
 assert body['event']['event_label'] is None and body['resolution_status']=='not_supplied'
 assert api().RainObservation(value.content).to_dict()==body
 assert body['automatic_actuation'] is body['physical_calibration_qualified'] is False


def test_independent_resolution_measurement_binds_policy_and_raw_tip_trials():
 args=observed_inputs();args['resolution_source']=resolution_document(args);value=api().make_observation(**args).to_dict()
 assert value['resolution_status']=='source_bound_independent_measurement'
 assert value['event']['classification']=='wet' and value['event']['threshold_mm']==pytest.approx(.508)
 assert value['resolution_source_sha256']==identity(args['resolution_source'])


@pytest.mark.parametrize('damage',['wrong_sensor','wrong_policy','unverified_spec','late','inconsistent_trials'])
def test_bad_resolution_withholds_occurrence_while_preserving_continuous_counter_depth(damage):
 args=observed_inputs();doc=resolution_document(args)
 if damage=='wrong_sensor':doc['sensor_id']+=1
 elif damage=='wrong_policy':doc['observation_policy_sha256']='f'*64
 elif damage=='unverified_spec':doc['basis']='manufacturer_specification_only'
 elif damage=='late':doc['available_at']=(args['received_at']+timedelta(days=1)).isoformat()
 else:doc['trials'][0]['counter_after_in']=1.02
 args['resolution_source']=doc;body=api().make_observation(**args).to_dict()
 assert body['observed_mm']==pytest.approx(2.54) and body['event']['event_label'] is None
 assert body['resolution_status']=='source_unavailable' and body['resolution_reason']


@pytest.mark.parametrize('damage',['value','clock','barrier','cutover'])
def test_observed_rain_cannot_be_resealed_with_a_new_total_or_earlier_availability(damage):
 args=observed_inputs()
 if damage=='barrier':args['observations'][100]=(args['observations'][100][0],None)
 elif damage=='cutover':args['cutover']=args['start']+timedelta(seconds=1)
 if damage in ('barrier','cutover'):
  with pytest.raises(ValueError):api().make_observation(**args)
  return
 body=api().make_observation(**args).to_dict()
 if damage=='value':body['observed_mm']=0.
 else:body['available_at']=args['start'].isoformat()
 body['observation_sha256']=identity({k:v for k,v in body.items() if k!='observation_sha256'})
 with pytest.raises(ValueError):api().RainObservation(canonical(body))
