"""An opt-in original must contain the means required by its real consumers."""
from datetime import timedelta
import json
from pathlib import Path
import pytest
import capability_fixtures
from capability_fixtures import reader
from learning_fixtures import T,SITE
from weather_learning.archive import Archive
from weather_learning.capabilities import profile,enabled_profiles
from weather_learning.capability_acquisition import Backoff
from weather_learning.capability_publish import build_capability_report
from weather_learning.probabilistic_retained import prepare_marginal_source
from weather_learning.worker import collect_once

NAME='uncertainty-complete-v1'


def test_previous_profile_identities_and_budgets_remain_exact():
 contract=json.loads((Path(__file__).resolve().parents[4]/'docs/operations/weathernext3-capabilities/profile-contract.json').read_bytes())
 for old in contract['profiles']:
  assert profile(old['name']).signature==old['profile_sha256']
 p=profile(NAME)
 assert len(p.bands)==14
 for grid,variable in [('station','station_head_temperature_2m'),('gridded','surface_solar_radiation_downwards_1hr'),('gridded','wind_speed_10m')]:
  for stat in ('mean','p10','p50','p90'):assert (grid,variable+'_'+stat) in p.bands
 assert (p.max_bytes,p.max_seconds,p.max_requests,p.attempts)==(8*1024**2,75,32,2)
 assert enabled_profiles()==(profile('core-v1'),)
 with pytest.raises(ValueError,match='one uncertainty'):enabled_profiles(('uncertainty-v1',NAME))


def test_mean_quantile_original_reaches_temperature_display_and_marginal_sources(tmp_path,monkeypatch):
 original=capability_fixtures.raw_response
 def differing_mean(grid,bands,init,horizon,**kwargs):
  raw=original(grid,bands,init,horizon,**kwargs)
  if 'station_head_temperature_2m_mean' in bands:
   pos=4+list(bands).index('station_head_temperature_2m_mean')
   for row in raw['region'][1:]:row[pos]+=3
  return raw
 monkeypatch.setattr(capability_fixtures,'raw_response',differing_mean)
 r,now=reader()
 def clock():now[0]+=timedelta(milliseconds=1);return now[0]
 r.clock=clock
 a=Archive(tmp_path/'archive')
 def collect():return collect_once(r,a,probe=False,horizon=360,include_interim=True,optional_profiles=(NAME,),clock=clock,free_bytes=10**9)
 result=collect();groups=result['capabilities']
 assert len(groups)==2 and all(g['status']=='collected' for g in groups)
 assert result['acquisition_budget']['requests_used']<=32 and result['acquisition_budget']['response_bytes_used']<=8*1024**2
 actual={g['snapshot_sha256']:a.read(g['snapshot_sha256']) for g in groups}
 report=build_capability_report(a,decision=clock(),site=SITE)
 assert report['sources'] and {s['snapshot_sha256'] for s in report['sources']}<=set(actual)
 hour=report['groups']['temperature']['hours'][0]
 assert (hour['mean_c'],hour['p50_c'],hour['p10_c'],hour['p90_c'])==(13,10,8,12)
 assert actual[hour['source_sha256']]['ingestion_completed_at']==next(s['available_at'] for s in report['sources'] if s['snapshot_sha256']==hour['source_sha256'])
 for snapshot in actual.values():
  source=prepare_marginal_source(snapshot,assessed_at=clock());target=T+timedelta(hours=5)
  for kind in ('temperature','solar_proxy','wind'):
   frame=source.forecast(kind,target=target,quality={'fixture':'synthetic'},origin=clock())
   assert frame is not None and frame.forecast_sha256==snapshot['snapshot_sha256']
   if kind=='temperature':assert (frame.baseline,frame.p50)==(13,10)
   elif kind=='solar_proxy':assert frame.p50==100
   else:assert frame.p10 is frame.p50 is frame.p90 is None # endpoint quantiles are not hourly-mean quantiles
 before={p.name:p.read_bytes() for p in a.objects.glob('*.json')};r.ee.queries.clear();now[0]+=timedelta(minutes=5)
 repeated=collect()
 assert all(g['status']=='cached' for g in repeated['capabilities']) and r.ee.queries==[]
 assert {p.name:p.read_bytes() for p in a.objects.glob('*.json')}==before


def test_profile_switch_keeps_six_retry_slots_and_preserves_unrelated_cooldowns(tmp_path):
 b=Backoff(tmp_path);run={'start_time':T.isoformat()}
 for name,horizons in [('uncertainty-v1',(48,360)),('atmosphere-v1',(48,360)),('rain-uncertainty-v1',(360,))]:
  for h in horizons:b.record(profile(name),run,h,T+timedelta(hours=2),'unavailable','partial_delivery')
 others={k:v for k,v in b.value['entries'].items() if not k.startswith('uncertainty-v1:')}
 b.value.update(quota_failures=1,quota_retry_at=(T+timedelta(hours=3)).isoformat())
 for h in (48,360):b.record(profile(NAME),run,h,T+timedelta(hours=2),'unavailable','partial_delivery')
 reread=Backoff(tmp_path)
 assert len(reread.value['entries'])==5
 assert all(reread.value['entries'][k]==v for k,v in others.items())
 assert not any(k.startswith('uncertainty-v1:') for k in reread.value['entries'])
 assert reread.value['quota_failures']==1 and reread.value['quota_retry_at']==(T+timedelta(hours=3)).isoformat()
 assert reread.path.stat().st_size<16384


@pytest.mark.parametrize('failed_band,median_present',[
 ('station_head_temperature_2m_p25',False),
 ('surface_solar_radiation_downwards_1hr_p50',True),
])
def test_partial_complete_profile_keeps_the_core_and_available_grid(tmp_path,failed_band,median_present):
 r,now=reader();r.ee.fail_band=failed_band
 def clock():now[0]+=timedelta(milliseconds=1);return now[0]
 r.clock=clock;a=Archive(tmp_path/'archive')
 result=collect_once(r,a,probe=False,horizon=360,optional_profiles=(NAME,),clock=clock,free_bytes=10**9)
 assert result['status']=='ARCHIVED'
 assert result['capabilities'][0]['status']=='unavailable' and result['capabilities'][0]['reason']=='partial_delivery'
 report=build_capability_report(a,decision=clock(),site=SITE)
 assert report['status']=='available'
 assert (report['groups']['temperature']['hours'][0]['p50_c'] is not None)==median_present
 # The primary deterministic source still requires fields absent from the optional original.
 core=a.eligible_snapshot(now[0],T+timedelta(hours=340),required_variables={'station_head_temperature_2m','total_precipitation_1hr','total_cloud_cover'})
 assert core['snapshot_sha256']==result['snapshot_sha256']
