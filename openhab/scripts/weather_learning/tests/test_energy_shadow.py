"""Precipitation comparisons must use common original forecasts and real receipts."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
import json
import unittest

from weather_rain_evidence import RainPolicy,rain_counter_receipt
from weather_learning.config import Site,COLLECTIONS
from weather_learning.contracts import identity
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
from weather_learning.energy_shadow import capture_rain_day,rain_day_forecast,compare_rain_products

DAY=date(2026,10,18);START=datetime(2026,10,18,tzinfo=timezone.utc)
POLICY=RainPolicy(45);EPOCH='11111111-1111-4111-8111-111111111111'
PRODUCTS=('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr')

def source(day=DAY,epoch=EPOCH):
 start=datetime.combine(day,datetime.min.time(),timezone.utc);rows=[]
 for i in range(1441):
  at=start+timedelta(minutes=i)
  record=rain_counter_receipt({'model':'Fineoffset-WH65B','id':45,'totalrainin':1+i*.1/1440},policy=POLICY,stream_epoch=epoch,received_at=at)
  raw=json.dumps(dict(version=1,streamEpoch=epoch,record=record,packetCount=i+1,invalidPackets=0,counterDrops=0,counterJumps=0))
  rows.append((at,raw))
 return dict(local_date=day,as_of=start+timedelta(days=1,minutes=2),cutover=START-timedelta(days=2),policy=POLICY,site_timezone='UTC',observations=rows)

def snapshot(day=DAY,missing=False):
 start=datetime.combine(day,datetime.min.time(),timezone.utc);init=start-timedelta(days=1)
 bands=[p+'_mean' for p in PRODUCTS];metadata=[];region=[['id','longitude','latitude','time',*bands]]
 for hour in range(1,49):
  at=init+timedelta(hours=hour);name='h'+str(hour)
  metadata.append({'system:index':name,'system:time_start':init.timestamp()*1000,'start_time':init.isoformat(),'end_time':at.isoformat(),'forecast_hour':hour,'ingestion_time_utc':init.timestamp()*1000+1000})
  region.append([name,-105.8,38.4,init.timestamp()*1000,.001,.002,None if missing and hour==25 else .003])
 site=Site(38.3739919,-105.7744609,'UTC')
 parsed=parse_collection_response(dict(metadata=metadata,region=region),collection=COLLECTIONS['gridded'],bands=bands,site=site,initialized_at=init,horizon=48)
 return make_snapshot([parsed],site=site,initialized_at=init,first_seen_at=init+timedelta(hours=8),completed_at=init+timedelta(hours=8,minutes=1))

def forecast(day=DAY,hour=20,missing=False):
 start=datetime.combine(day,datetime.min.time(),timezone.utc)
 return rain_day_forecast(snapshot(day,missing),issued_at=start-timedelta(days=1)+timedelta(hours=hour),completed_at=start-timedelta(days=1)+timedelta(hours=hour,seconds=1),local_date=day)

class RainComparisonTests(unittest.TestCase):
 def test_replays_source_receipts_and_scores_each_product_on_common_day(self):
  original=capture_rain_day(**source());report=compare_rain_products([forecast()],[original])
  cohort=next(iter(report['cohorts'].values()))
  self.assertEqual(cohort['days'],1)
  self.assertAlmostEqual(cohort['products'][PRODUCTS[0]]['mae_mm'],21.46)
  self.assertAlmostEqual(cohort['products'][PRODUCTS[1]]['bias_mm'],45.46)
  self.assertEqual(cohort['by_observed_regime']['wet']['days'],1)
  self.assertEqual(report['qualification'],'SHADOW_ONLY');self.assertIsNone(report['selected_product'])
  self.assertFalse(report['automatic_actuation']);self.assertEqual(report['pairs'][0]['outcome_sha256'],original['source_sha256'])
 def test_invalid_or_incomplete_local_history_cannot_become_a_numeric_label(self):
  for kind in ('gap','invalid','partial','cutover'):
   data=source()
   if kind=='gap':del data['observations'][100:110]
   if kind=='invalid':
    at,raw=data['observations'][100];obj=json.loads(raw);obj['invalidPackets']=1;data['observations'][100]=(at,json.dumps(obj))
   if kind=='partial':data['as_of']=START+timedelta(hours=23)
   if kind=='cutover':data['cutover']=START+timedelta(seconds=1)
   with self.subTest(kind=kind),self.assertRaises(ValueError):capture_rain_day(**data)
 def test_forged_normalized_forecast_or_outcome_summary_is_refused(self):
  data=snapshot();data['points'][30]['value']=500
  with self.assertRaises(ValueError):rain_day_forecast(data,issued_at=START-timedelta(hours=4),completed_at=START-timedelta(hours=4)+timedelta(seconds=1),local_date=DAY)
  original=capture_rain_day(**source());original['summary']['rain_in']=5
  original['source_sha256']=identity({k:v for k,v in original.items() if k!='source_sha256'})
  with self.assertRaises(ValueError):compare_rain_products([forecast()],[original])
 def test_latest_before_day_origin_is_selected_before_missing_product_checks(self):
  report=compare_rain_products([forecast(hour=19),forecast(hour=20,missing=True)],[capture_rain_day(**source())])
  self.assertEqual(report['cohorts'],{});self.assertEqual(len(report['withheld']),1)
  self.assertEqual(report['withheld'][0]['reason'],'INCOMPLETE_COMMON_PRODUCTS')
  self.assertEqual(report['decisions'][0]['issued_at'],(START-timedelta(hours=4)).isoformat())
 def test_late_issue_or_historical_source_cannot_enter_prospective_scoring(self):
  for late in (True,False):
   data=snapshot()
   if not late:data['historical']=True
   with self.subTest(late=late),self.assertRaises(ValueError):rain_day_forecast(data,issued_at=START if late else START-timedelta(hours=4),completed_at=START+timedelta(seconds=1) if late else START-timedelta(hours=4)+timedelta(seconds=1),local_date=DAY)
 def test_issue_completed_after_midnight_cannot_be_used_for_day_ahead_scoring(self):
  with self.assertRaises(ValueError):rain_day_forecast(snapshot(),issued_at=START-timedelta(seconds=1),completed_at=START+timedelta(seconds=1),local_date=DAY)
 def test_dry_and_boundary_uncertain_days_stay_distinct_from_wet(self):
  sources=[];forecasts=[]
  for offset,uncertain in ((0,False),(1,True)):
   day=DAY+timedelta(days=offset);data=source(day);rows=[]
   for index,(at,raw) in enumerate(data['observations']):
    obj=json.loads(raw);obj['record']['totalRainIn']=1 if not uncertain or index==0 else 1.01
    if uncertain and index==0:
     at-=timedelta(seconds=30);obj['record'].update(recordedAt=at.isoformat(),receivedAt=at.isoformat(),validUntil=(at+timedelta(seconds=120)).isoformat())
    rows.append((at,json.dumps(obj)))
   data['observations']=rows;sources.append(capture_rain_day(**data));forecasts.append(forecast(day))
  report=compare_rain_products(forecasts,sources);cohort=next(iter(report['cohorts'].values()))
  self.assertEqual(set(cohort['by_observed_regime']),{'dry','boundary_uncertain'})
  self.assertAlmostEqual(report['pairs'][1]['boundary_uncertainty_mm'],.254)
  self.assertLess(cohort['products'][PRODUCTS[0]]['mae_lower_bound_mm'],cohort['products'][PRODUCTS[0]]['mae_upper_bound_mm'])
 def test_sensor_epochs_are_partitioned_without_global_pooled_skill(self):
  other=DAY+timedelta(days=1)
  report=compare_rain_products([forecast(),forecast(other)],[capture_rain_day(**source()),capture_rain_day(**source(other,'22222222-2222-4222-8222-222222222222'))])
  self.assertEqual(len(report['cohorts']),2);self.assertTrue(all(c['days']==1 for c in report['cohorts'].values()));self.assertNotIn('mae_mm',report)
 def test_same_epoch_days_share_one_cohort_and_are_not_double_counted(self):
  other=DAY+timedelta(days=1)
  report=compare_rain_products([forecast(),forecast(other)],[capture_rain_day(**source()),capture_rain_day(**source(other))])
  self.assertEqual(len(report['cohorts']),1);self.assertEqual(next(iter(report['cohorts'].values()))['days'],2)
 def test_absent_label_is_withheld_and_never_reconstructed_from_current_state(self):
  report=compare_rain_products([forecast()],[])
  self.assertEqual(report['cohorts'],{});self.assertEqual(report['withheld'][0]['reason'],'NO_QUALIFIED_OUTCOME')
 def test_reassessment_does_not_duplicate_pair_but_conflicting_source_refuses(self):
  first=capture_rain_day(**source());data=source();data['as_of']+=timedelta(hours=1);second=capture_rain_day(**data)
  report=compare_rain_products([forecast(),forecast()],[first,second]);self.assertEqual(len(report['pairs']),1)
  changed=source();at,raw=changed['observations'][10];changed['observations'][10]=(at,raw+' ')
  with self.assertRaises(ValueError):compare_rain_products([forecast()],[first,capture_rain_day(**changed)])

if __name__=='__main__':unittest.main()
