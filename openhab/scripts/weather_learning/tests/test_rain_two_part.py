"""One causal, bounded two-part model; no probability from missing/all-dry data."""
from datetime import date,datetime,timedelta,timezone
from importlib import import_module
import pytest
from test_rain_calibration import POLICY,PRODUCTS,rain_snapshot,resolution_document
from test_weather_rain_day import POLICY as NATIVE,EPOCH,snapshot as counter_packet
from weather_learning.rain_calibration import make_forecast,make_observation
from weather_learning.contracts import instant


def api():return import_module('weather_learning.rain_two_part')


def population(*,all_dry=False,days=12):
 first=datetime(2026,6,1,tzinfo=timezone.utc);last=first+timedelta(days=days);rows=[];at=first-timedelta(seconds=30);counter=10.;wet_seen=set()
 while at<=last+timedelta(seconds=90):
  index=(at-first).days
  if not all_dry and 0<=index<days and index%4<2 and at>=first+timedelta(days=index,hours=12) and index not in wet_seen:counter+=.12;wet_seen.add(index)
  rows.append(counter_packet(at,len(rows)+1,counter));at+=timedelta(seconds=90)
 fore=[];out=[];resolution=None
 for day in range(days):
  target=(first+timedelta(days=day)).date();source,start,end=rain_snapshot(target,'UTC',mean_mm=.25 if day%4<2 else .001);issue=start-timedelta(hours=3)
  fore.append(make_forecast(snapshot=source,start=start,end=end,issued_at=issue,completed_at=issue+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability'))
  before=[r for r in rows if r[0]<start];originals=before[-1:]+[r for r in rows if start<=r[0]<=end+timedelta(seconds=120)]
  args=dict(start=start,end=end,requested_at=end+timedelta(seconds=120),received_at=end+timedelta(seconds=121),cutover=first-timedelta(days=1),observations=originals,policy=NATIVE,resolution_source=None,experiment_policy=POLICY)
  if resolution is None:resolution=resolution_document(args)
  args['resolution_source']=resolution;out.append(make_observation(**args))
 return fore,out


@pytest.fixture(scope='module')
def balanced():return population()


def future(mean_mm):
 source,start,end=rain_snapshot(date(2026,6,15),'UTC',mean_mm=mean_mm);issue=start-timedelta(hours=3)
 return make_forecast(snapshot=source,start=start,end=end,issued_at=issue,completed_at=issue+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')


def fit(balanced):
 fore,out=balanced;issue=instant(future(.25).to_dict()['issued_at']);return api().fit_two_part(fore,out,cutoff=issue-timedelta(hours=1),fitted_at=issue-timedelta(minutes=59),policy=POLICY)


def test_two_part_model_uses_training_climatology_and_conditional_positive_amount(balanced):
 result=fit(balanced);assert result['status']=='fitted'
 assert result['support']['wet_targets']==result['support']['below_threshold_targets']==6
 assert result['support']['wet_events']==3 and result['support']['independent_target_dates']==12
 assert result['model']['climatology_probability']==.5
 cohort=balanced[1][0].to_dict()['cohort_sha256'];high=api().predict_two_part(result['model'],future(.25),observation_cohort_sha256=cohort,policy=POLICY);low=api().predict_two_part(result['model'],future(.001),observation_cohort_sha256=cohort,policy=POLICY)
 assert 0<=low['probability_wet']<.5<high['probability_wet']<=1
 assert high['conditional_wet_mean_mm']==pytest.approx(3.048,abs=1e-8)
 assert high['mean_depth_mm']==pytest.approx(high['probability_wet']*high['conditional_wet_mean_mm']+(1-high['probability_wet'])*high['subthreshold_mean_mm'])
 assert high['native_google_probability'] is high['probability_calibration_qualified'] is high['automatic_actuation'] is False
 assert high['target']['start']==future(.25).to_dict()['start'] and high['target']['interval_kind']=='local_calendar_day'


def test_all_dry_data_refuses_the_challenger_before_numerical_fitting(monkeypatch):
 module=api();data=population(all_dry=True)
 import numpy as np
 def forbidden(*a,**kw):pytest.fail('all-dry data reached coefficient fitting')
 monkeypatch.setattr(np.linalg,'solve',forbidden);result=fit(data)
 assert result['status']=='insufficient_evidence' and result['model'] is None
 assert result['support']['wet_targets']==result['support']['wet_events']==0


def test_duplicate_issues_do_not_inflate_training_dates_or_independent_events(balanced):
 fore,out=balanced;result=fit((fore+fore,out+out))
 assert result['support']['independent_target_dates']==12 and result['support']['wet_events']==3
 assert result['support']['wet_targets']==6 and result['model']['climatology_probability']==.5


def test_late_label_acquisition_cannot_enter_an_earlier_fit(balanced):
 fore,out=balanced;original=out[0].to_dict();request=original['request'];late=datetime(2026,6,20,tzinfo=timezone.utc)
 delayed=make_observation(start=instant(request['start']),end=instant(request['end']),requested_at=late,received_at=late+timedelta(seconds=1),cutover=instant(request['cutover']),observations=[(instant(at),raw) for at,raw in original['sources']['observations']],policy=NATIVE,resolution_source=original['sources']['resolution_source'],experiment_policy=POLICY)
 result=fit((fore,[delayed,*out[1:]]))
 assert result['status']=='insufficient_evidence' and result['model'] is None
 assert result['support']['training_targets']==11


def test_unseen_gauge_context_or_future_model_has_no_supported_probability(balanced):
 result=fit(balanced);prediction=api().predict_two_part(result['model'],future(.25),observation_cohort_sha256='f'*64,policy=POLICY)
 assert prediction['status']=='insufficient_evidence' and prediction['probability_wet'] is None
 assert prediction['mean_depth_mm'] is None


def test_mixed_forecast_context_cannot_be_hidden_by_independent_date_selection(balanced):
 from weather_learning.rain_calibration import make_forecast
 fore,out=balanced
 source,start,end=rain_snapshot(date(2026,6,1),'America/Denver',mean_mm=.25);issue=start-timedelta(hours=3)
 other=make_forecast(snapshot=source,start=start,end=end,issued_at=issue,completed_at=issue+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')
 with pytest.raises(ValueError,match='coherent.*forecast context'):fit(([other,*fore],out))


def test_missing_latest_head_does_not_restore_an_earlier_complete_decision(balanced):
 fore,out=balanced;source,start,end=rain_snapshot(date(2026,6,1),'UTC',mean_mm=.25,missing=PRODUCTS[1]);issue=start-timedelta(hours=2)
 later=make_forecast(snapshot=source,start=start,end=end,issued_at=issue,completed_at=issue+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')
 result=fit(([later,*fore],out))
 assert result['status']=='insufficient_evidence' and result['support']['training_targets']==11
 assert result['withheld']['missing_precipitation_head']==1


def test_changing_numerical_sources_cannot_retag_old_rain_weights(balanced,monkeypatch):
 result=fit(balanced);module=api();monkeypatch.setattr(module,'numerical_sources',lambda:{'different.py':'0'*64})
 with pytest.raises(ValueError,match='numerical sources'):module.predict_two_part(result['model'],future(.25),observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY)


def test_model_completed_after_issue_has_no_historical_prediction(balanced):
 result=fit(balanced);from weather_learning.contracts import identity
 model=result['model'];model['fitted_at']=future(.25).to_dict()['start'];model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'})
 result=api().predict_two_part(model,future(.25),observation_cohort_sha256=balanced[1][0].to_dict()['cohort_sha256'],policy=POLICY)
 assert result['status']=='insufficient_evidence' and result['reason']=='model_not_available_before_decision'


def test_only_a_known_below_threshold_interval_separates_wet_events():
 module=api()
 def pair(label,i):return dict(date=str(i),observation=dict(event=dict(event_label=label)))
 assert module.support([pair(v,i) for i,v in enumerate([1,None,1,None,1])])['wet_events']==1
 assert module.support([pair(v,i) for i,v in enumerate([1,None,0,None,1])])['wet_events']==2
