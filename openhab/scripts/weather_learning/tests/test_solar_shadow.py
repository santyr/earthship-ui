"""Solar interval and timing comparisons must retain the local proxy's limits."""
from datetime import datetime,timedelta,timezone
import json
import unittest
from weather_radiation_evidence import RadiationPolicy,radiation_receipt
from weather_learning.config import Site,COLLECTIONS
from weather_learning.contracts import identity
from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
from weather_learning.solar_shadow import capture_solar_window,solar_window_forecast,compare_solar_windows

T=datetime(2026,10,18,tzinfo=timezone.utc);START=T+timedelta(hours=19);END=START+timedelta(hours=2)
EPOCH='11111111-1111-4111-8111-111111111111';POLICY=RadiationPolicy(45)
GHI='surface_solar_radiation_downwards_1hr';DIRECT='total_sky_direct_solar_radiation_at_surface_1hr'

def source(*,start=START,values=(100,300),epoch=EPOCH):
 end=start+timedelta(hours=len(values));rows=[]
 for seq,offset in enumerate(range(-60,len(values)*3600+61,60),1):
  at=start+timedelta(seconds=offset);index=min(len(values)-1,max(0,offset//3600));watts=values[index]
  record=radiation_receipt({'model':'Fineoffset-WH65B','id':45,'light_lux':watts*126.7,'solarradiation':watts,'radio_decode_utc':at.strftime('%Y-%m-%d %H:%M:%S')},policy=POLICY,stream_epoch=epoch,received_at=at)
  record['sequence']=seq;raw=json.dumps(dict(version=2,streamEpoch=epoch,sequence=seq,faultCount=0,record=record));rows.append((at,raw))
 return dict(start=start,end=end,assessed_at=end+timedelta(seconds=120),history_start=start-timedelta(seconds=120),cutover=T-timedelta(days=1),policy=POLICY,site_timezone='UTC',observations=rows)

def snapshot(*,values=(100,300),missing=False):
 bands=[GHI+'_mean',DIRECT+'_mean'];meta=[];rows=[['id','longitude','latitude','time',*bands]]
 for hour in range(1,49):
  valid=T+timedelta(hours=hour);name='h'+str(hour);watts=values[hour-20] if 20<=hour<20+len(values) else 0
  meta.append({'system:index':name,'system:time_start':T.timestamp()*1000,'start_time':T.isoformat(),'end_time':valid.isoformat(),'forecast_hour':hour,'ingestion_time_utc':T.timestamp()*1000+1000})
  rows.append([name,-105.8,38.4,T.timestamp()*1000,None if missing and hour==20 else watts*3600,watts*1800])
 site=Site(38.3739919,-105.7744609,'UTC');parsed=parse_collection_response(dict(metadata=meta,region=rows),collection=COLLECTIONS['gridded'],bands=bands,site=site,initialized_at=T,horizon=48)
 return make_snapshot([parsed],site=site,initialized_at=T,first_seen_at=T+timedelta(hours=8),completed_at=T+timedelta(hours=8,seconds=1))

def forecast(*,values=(100,300),minute=0,missing=False,start=START,end=END):
 issued=T+timedelta(hours=18,minutes=minute)
 return solar_window_forecast(snapshot(values=values,missing=missing),issued_at=issued,completed_at=issued+timedelta(seconds=1),start=start,end=end)

class SolarComparisonTests(unittest.TestCase):
 def test_hourly_integrals_match_native_trailing_intervals_but_never_claim_calibration(self):
  original=capture_solar_window(**source());report=compare_solar_windows([forecast()],[original]);pair=report['pairs'][0]
  self.assertAlmostEqual(pair['proxy_hourly_wh_m2'][0],100);self.assertAlmostEqual(pair['proxy_hourly_wh_m2'][1],300);self.assertAlmostEqual(pair['proxy_wh_m2'],400)
  self.assertAlmostEqual(pair['diagnostics'][GHI]['energy_difference_vs_proxy_wh_m2'],0)
  self.assertAlmostEqual(pair['diagnostics'][DIRECT]['forecast_wh_m2'],200)
  self.assertFalse(report['calibrated_ghi_skill_qualified']);self.assertFalse(report['direct_component_skill_qualified'])
  self.assertFalse(report['automatic_actuation']);self.assertEqual(report['qualification'],'SHADOW_ONLY')
 def test_timing_shift_is_visible_even_when_window_energy_is_identical(self):
  report=compare_solar_windows([forecast(values=(300,100))],[capture_solar_window(**source())]);result=report['pairs'][0]['diagnostics'][GHI]
  self.assertAlmostEqual(result['energy_difference_vs_proxy_wh_m2'],0)
  self.assertAlmostEqual(result['energy_centroid_error_hours'],-.5)
  self.assertAlmostEqual(result['normalized_hourly_shape_mae'],.5)
 def test_missing_and_faulted_windows_cannot_be_replaced_with_numeric_proxy_labels(self):
  for kind in ('gap','fault','closing','legacy'):
   data=source()
   if kind=='gap':del data['observations'][20:24]
   else:
    index=-2 if kind=='closing' else 20
    at,raw=data['observations'][index];value=json.loads(raw)
    if kind=='legacy':value['version']=1;value.pop('faultCount')
    else:value['faultCount']=1
    data['observations'][index]=(at,json.dumps(value))
   with self.subTest(kind=kind),self.assertRaises(ValueError):capture_solar_window(**data)
 def test_exact_source_summary_is_rederived_even_after_an_attacker_rehashes_it(self):
  original=capture_solar_window(**source());original['summary']['irradiance_wh_m2']=900
  original['source_sha256']=identity({k:v for k,v in original.items() if k not in ('source_sha256','assessed_at')})
  with self.assertRaises(ValueError):compare_solar_windows([forecast()],[original])
 def test_latest_original_is_selected_before_common_solar_missingness(self):
  report=compare_solar_windows([forecast(),forecast(minute=30,missing=True)],[capture_solar_window(**source())])
  self.assertEqual(report['pairs'],[]);self.assertEqual(report['withheld'][0]['reason'],'INCOMPLETE_COMMON_SOLAR')
  self.assertEqual(report['decisions'][0]['issued_at'],(T+timedelta(hours=18,minutes=30)).isoformat())
 def test_window_started_before_forecast_completion_is_not_prospective(self):
  with self.assertRaises(ValueError):solar_window_forecast(snapshot(),issued_at=START-timedelta(seconds=1),completed_at=START+timedelta(seconds=1),start=START,end=END)
 def test_zero_night_exposure_is_real_but_has_no_invented_timing_or_ratio(self):
  report=compare_solar_windows([forecast(values=(0,0))],[capture_solar_window(**source(values=(0,0)))])
  result=report['pairs'][0]['diagnostics'][GHI]
  self.assertEqual(result['forecast_wh_m2'],0);self.assertIsNone(result['energy_centroid_error_hours']);self.assertIsNone(result['forecast_to_proxy_ratio'])
 def test_sensor_epochs_are_separate_and_overlapping_windows_cannot_inflate_support(self):
  second_start=START+timedelta(hours=2);second_end=END+timedelta(hours=2)
  report=compare_solar_windows([forecast(),forecast(start=second_start,end=second_end)],[capture_solar_window(**source()),capture_solar_window(**source(start=second_start,epoch='22222222-2222-4222-8222-222222222222'))])
  self.assertEqual(len(report['cohorts']),2)
  with self.assertRaises(ValueError):compare_solar_windows([forecast(),forecast(start=START+timedelta(hours=1),end=END)],[capture_solar_window(**source()),capture_solar_window(**source(start=START+timedelta(hours=1),values=(300,)))])
 def test_missing_outcomes_stay_withheld(self):
  report=compare_solar_windows([forecast()],[])
  self.assertEqual(report['pairs'],[]);self.assertEqual(report['withheld'][0]['reason'],'NO_QUALIFIED_PROXY_OUTCOME')
 def test_source_reassessment_does_not_multiply_observations(self):
  first=capture_solar_window(**source());data=source();data['assessed_at']+=timedelta(hours=1)
  report=compare_solar_windows([forecast(),forecast()],[first,capture_solar_window(**data)])
  self.assertEqual(len(report['pairs']),1)
 def test_tail_energy_and_timing_errors_remain_visible_beside_average_errors(self):
  forecasts=[];sources=[]
  for offset in (0,2,4):
   start=START+timedelta(hours=offset);end=start+timedelta(hours=2)
   forecasts.append(forecast(values=(100,300,250,250,400,400),start=start,end=end))
   sources.append(capture_solar_window(**source(start=start)))
  report=compare_solar_windows(forecasts,sources);cohort=next(iter(report['cohorts'].values()))
  result=cohort['by_window_hours']['2']['products'][GHI]
  self.assertAlmostEqual(result['energy_mae_vs_proxy_wh_m2'],500/3)
  self.assertAlmostEqual(result['energy_absolute_error_p95_vs_proxy_wh_m2'],400)
  self.assertAlmostEqual(result['centroid_absolute_error_p95_vs_proxy_hours'],.25)
 def test_one_hour_energy_pair_does_not_claim_observed_timing_accuracy(self):
  end=START+timedelta(hours=1)
  report=compare_solar_windows([forecast(values=(100,),end=end)],[capture_solar_window(**source(values=(100,)))])
  result=report['pairs'][0]['diagnostics'][GHI]
  self.assertAlmostEqual(result['forecast_wh_m2'],100)
  self.assertIsNone(result['energy_centroid_error_hours'])
  self.assertIsNone(result['normalized_hourly_shape_mae'])
 def test_fractional_hour_window_cannot_relabel_an_instantaneous_proxy_as_hourly_energy(self):
  with self.assertRaises(ValueError):solar_window_forecast(snapshot(),issued_at=T+timedelta(hours=18),completed_at=T+timedelta(hours=18,seconds=1),start=START+timedelta(minutes=15),end=END)

if __name__=='__main__':unittest.main()
