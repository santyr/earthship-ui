"""Optional rain production uses only pinned local originals and actual clocks."""
from datetime import timedelta
from importlib import import_module
import json
import pytest
from weather_learning.contracts import canonical,instant,identity
from weather_learning.archive import Archive
from weather_learning.shadow import ShadowStore
from test_rain_calibration import rain_snapshot,POLICY
from test_weather_rain_day import POLICY as NATIVE,snapshot


def api():return import_module('weather_learning.rain_runtime')


def context(tmp_path,**kw):
 m=api();archive=Archive(tmp_path/'archive');snap,start,end=rain_snapshot(hours=360);archive.store_snapshot(snap);state=ShadowStore(tmp_path/'state');at=start-timedelta(hours=3)
 native=tmp_path/'native.json';native.write_bytes(canonical(dict(version=1,sensor_id=NATIVE.sensor_id,validity_seconds=NATIVE.validity_seconds,maximum_counter_in=NATIVE.maximum_counter_in)));native.chmod(0o600)
 profile=dict(schema='earthship-rain-shadow-profile/v1',enabled=True,archive=str(archive.root),state=str(state.root),site=snap['site'],rain_policy=str(native),observation_cutover=(start-timedelta(days=1)).isoformat(),resolution_source=None,model_artifacts={},gain_model_artifacts={},runtime_manifest=m.runtime_manifest());profile.update(kw)
 path=tmp_path/'profile.json';path.write_bytes(canonical(profile));path.chmod(0o600)
 return m,state,path,profile,at


def files(root):return {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}

def reader(at):return lambda:snapshot(at-timedelta(seconds=2),10,10.)[1]


def test_disabled_profile_has_no_measurement_or_state_side_effects(tmp_path):
 m,s,p,v,at=context(tmp_path,enabled=False);before=files(s.root)
 r=m.run(p,apply=True,clock=lambda:at,origin_reader=lambda:pytest.fail('disabled read'))
 assert r['status']=='disabled' and r['retained'] is False and files(s.root)==before


def test_preview_derives_all_future_interval_kinds_without_writing(tmp_path):
 m,s,p,v,at=context(tmp_path);before=files(tmp_path)
 r=m.run(p,clock=lambda:at,origin_reader=reader(at))
 assert r['rows']==29 and set(r['interval_kinds'])=={'local_calendar_day','rolling_24_hours','remaining_day'}
 assert r['retained'] is False and files(tmp_path)==before


def test_apply_retains_original_context_and_exact_cache_emission_without_core_pointer(tmp_path):
 m,s,p,v,at=context(tmp_path);r=m.run(p,apply=True,clock=lambda:at,origin_reader=reader(at))
 assert r['retained'] and r['issued'] and r['local_candidate_rows']==0
 from weather_learning.rain_queue import RainQueue,CACHE
 q=RainQueue(s,policy=POLICY);wrapper,emission=q.load_bundle(r['bundle_sha256'])
 assert wrapper['origin_context']['status']=='available'
 assert all(i['observation_cohort_sha256']==wrapper['origin_context']['cohort_sha256'] for i in wrapper['issues'])
 assert (s.root/CACHE).read_bytes()==canonical(wrapper['public_view'])
 assert not (s.root/'current-model.json').exists()


def test_same_native_generation_is_not_reissued_or_given_a_new_clock(tmp_path):
 m,s,p,v,at=context(tmp_path);r=m.run(p,apply=True,clock=lambda:at,origin_reader=reader(at));before=files(s.root)
 later=at+timedelta(hours=1);again=m.run(p,apply=True,clock=lambda:later,origin_reader=reader(later))
 assert again['status']=='already_issued' and again['bundle_sha256']==r['bundle_sha256']
 assert files(s.root)==before


def test_unknown_current_stream_keeps_raw_heads_and_suppresses_local_probabilities(tmp_path):
 m,s,p,v,at=context(tmp_path)
 def missing():raise ConnectionError('private endpoint details')
 r=m.run(p,apply=True,clock=lambda:at,origin_reader=missing)
 assert r['rows']==29 and r['origin_status']=='unavailable' and r['local_candidate_rows']==0
 assert 'private endpoint details' not in str(r)


def test_wrong_source_profile_and_unknown_keys_fail_before_reading(tmp_path):
 m,s,p,v,at=context(tmp_path)
 for bad in [dict(v,runtime_manifest={}),dict(v,actuate=True)]:
  p.write_bytes(canonical(bad))
  with pytest.raises(ValueError):m.run(p,origin_reader=lambda:pytest.fail('invalid profile read'))
 assert not (s.root/'rain-candidates.json').exists()


def test_no_original_native_source_does_not_create_or_publish_queue(tmp_path):
 m,s,p,v,at=context(tmp_path,archive=str(tmp_path/'absent'));before=files(tmp_path)
 r=m.run(p,apply=True,clock=lambda:at,origin_reader=reader(at))
 assert r['status']=='source_unavailable' and not r['retained'] and files(tmp_path)==before


def test_global_deadline_is_not_swallowed_as_optional_origin_absence(tmp_path):
 m,s,p,v,at=context(tmp_path)
 def stop():raise TimeoutError('owner deadline')
 with pytest.raises(TimeoutError):m.run(p,clock=lambda:at,origin_reader=stop)


def test_a_new_near_profile_does_not_hide_available_full_horizon_originals(tmp_path):
 m,s,p,v,at=context(tmp_path);archive=Archive(v['archive']);near,start,end=rain_snapshot(hours=48)
 near['first_seen_at']=(instant(near['first_seen_at'])+timedelta(minutes=30)).isoformat();near['ingestion_completed_at']=(instant(near['ingestion_completed_at'])+timedelta(minutes=30)).isoformat();archive.store_snapshot(near)
 r=m.run(p,clock=lambda:at,origin_reader=reader(at))
 assert r['rows']==29 and len(r['source_snapshot_sha256s'])==2


def test_latest_incomplete_head_does_not_restore_an_older_successful_forecast(tmp_path):
 from test_rain_calibration import PRODUCTS
 m,s,p,v,at=context(tmp_path);archive=Archive(v['archive']);later,start,end=rain_snapshot(hours=360,missing=PRODUCTS[1])
 later['first_seen_at']=(instant(later['first_seen_at'])+timedelta(minutes=30)).isoformat();later['ingestion_completed_at']=(instant(later['ingestion_completed_at'])+timedelta(minutes=30)).isoformat();archive.store_snapshot(later)
 r=m.run(p,clock=lambda:at,origin_reader=reader(at))
 assert r['rows']==29 and r['complete_comparison_rows']==0


def test_supported_explicit_model_is_a_local_shadow_without_installing_a_selection(tmp_path):
 from test_rain_two_part import population,fit
 from hashlib import sha256
 m,s,p,v,at=context(tmp_path);data=population();model=fit(data)['model'];fsource,start,end=rain_snapshot(__import__('datetime').date(2026,6,15),'UTC',hours=360,mean_mm=.25);archive=Archive(v['archive']);archive.store_snapshot(fsource);at=start-timedelta(hours=3)
 origin=data[1][0].to_dict();resolution=tmp_path/'resolution.json';resolution.write_bytes(canonical(origin['sources']['resolution_source']));resolution.chmod(0o600)
 artifact=tmp_path/'model.json';artifact.write_bytes(canonical(model));artifact.chmod(0o600)
 v.update(site=fsource['site'],observation_cutover=origin['request']['cutover'],resolution_source=str(resolution),model_artifacts={model['model_sha256']:dict(path=str(artifact),file_sha256=sha256(artifact.read_bytes()).hexdigest())});p.write_bytes(canonical(v));before=files(s.root)
 r=m.run(p,clock=lambda:at,origin_reader=reader(at))
 assert r['local_candidate_rows']>0 and r['probability_calibration_qualified'] is False
 assert r['selected_pointer_installed'] is False and files(s.root)==before


def test_post_cache_write_failure_reports_uncertainty_and_recovers_original_generation(tmp_path,monkeypatch,capsys):
 from weather_learning.rain_queue import RainQueue,CACHE
 m,s,p,v,at=context(tmp_path);real_run=m.run;real_confirm=RainQueue.confirm
 def fail(*a,**k):raise ValueError('after actual cache write')
 monkeypatch.setattr(RainQueue,'confirm',fail)
 monkeypatch.setattr(m,'run',lambda profile,apply=False,guard=lambda:None:real_run(profile,apply=apply,clock=lambda:at,guard=guard,origin_reader=reader(at)))
 assert m.main(['--profile',str(p),'--apply'])==1
 result=json.loads(capsys.readouterr().out);assert result['retained'] is None and result['emission_status']=='unknown_partial_state'
 assert (s.root/CACHE).exists();old=(s.root/CACHE).read_bytes()
 monkeypatch.setattr(RainQueue,'confirm',real_confirm)
 recovered=real_run(p,apply=True,clock=lambda:at+timedelta(minutes=1),origin_reader=reader(at+timedelta(minutes=1)))
 assert recovered['status']=='already_issued' and (s.root/CACHE).read_bytes()==old
 assert RainQueue(s,policy=POLICY).summary()['confirmed']==1


def test_unseen_season_does_not_claim_usable_local_shadow_status(tmp_path):
 from test_rain_two_part import population,fit
 from hashlib import sha256
 m,s,p,v,at=context(tmp_path);data=population();model=fit(data)['model'];source,start,end=rain_snapshot(__import__('datetime').date(2026,10,20),'UTC',hours=360)
 Archive(v['archive']).store_snapshot(source);at=start-timedelta(hours=3);o=data[1][0].to_dict()
 resolution=tmp_path/'resolution.json';resolution.write_bytes(canonical(o['sources']['resolution_source']));resolution.chmod(0o600)
 artifact=tmp_path/'model.json';artifact.write_bytes(canonical(model));artifact.chmod(0o600)
 v.update(site=source['site'],observation_cutover=o['request']['cutover'],resolution_source=str(resolution),model_artifacts={model['model_sha256']:dict(path=str(artifact),file_sha256=sha256(artifact.read_bytes()).hexdigest())});p.write_bytes(canonical(v))
 r=m.run(p,clock=lambda:at,origin_reader=reader(at))
 assert r['local_candidate_rows']==0 and r['status']=='raw_shadow'


def test_already_issued_generation_reports_an_expired_cache_without_refreshing_it(tmp_path):
 m,s,p,v,at=context(tmp_path);first=m.run(p,apply=True,clock=lambda:at,origin_reader=reader(at));before=files(s.root)
 later=at+timedelta(hours=7);r=m.run(p,apply=True,clock=lambda:later,origin_reader=reader(later))
 assert r['status']=='already_issued' and r['cache_current'] is False
 assert r['bundle_sha256']==first['bundle_sha256'] and files(s.root)==before
