"""Only byte-confirmed rain shadow emissions mature into bounded durable scores."""
from datetime import timedelta
from importlib import import_module
import json
import pytest
from weather_learning.contracts import instant,canonical
from weather_learning.shadow import ShadowStore
from weather_learning.rain_calibration import make_forecast
from weather_learning.rain_issues import make_issue
from test_rain_calibration import POLICY,rain_snapshot
from test_rain_history import read
from test_weather_rain_history import Connection
from test_weather_rain_day import DAY,bounds


def api():return import_module('weather_learning.rain_queue')


def setup(tmp_path,*,publish=True,cohort=None):
 module=api();state=ShadowStore(tmp_path/'state');q=module.RainQueue(state,policy=POLICY)
 capture=read(Connection());source,start,end=rain_snapshot(DAY);decision=start-timedelta(hours=1)
 f=make_forecast(snapshot=source,start=start,end=end,issued_at=decision,completed_at=decision+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')
 issue=make_issue(f,model=None,observation_cohort_sha256=cohort or capture.observation().to_dict()['cohort_sha256'],policy=POLICY,prepared_at=decision+timedelta(seconds=1),mode='prospective_shadow')
 key=q.publish([issue],clock=lambda:decision+timedelta(seconds=2)) if publish else q.retain([issue])
 return module,state,q,issue,key,start,end


def run(module,state,now,*,apply=True,read_acquisition=None,limit=1):
 clock=[now]
 def acquire(work,assessed):
  assert (work['start'],work['end'])==tuple(t.isoformat() for t in bounds())
  times=iter([clock[0],clock[0]+timedelta(seconds=1)]);value=read(Connection(),clock=lambda:next(times));clock[0]+=timedelta(seconds=1);return value
 return module.monitor_rain(state,now=now,policy=POLICY,observation_policy_sha256='a'*64,read_acquisition=acquire if read_acquisition is None else read_acquisition,clock=lambda:clock[0],limit=limit,apply=apply)


def test_absent_optional_rain_index_has_no_read_or_state_side_effect(tmp_path):
 module=api();state=ShadowStore(tmp_path/'state');before={p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
 result=run(module,state,bounds()[1]+timedelta(minutes=2),read_acquisition=lambda *a:pytest.fail('disabled rain read'))
 assert result['status']=='not_enabled' and result['observations_attempted']==0
 assert {p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}==before


def test_retention_is_not_emission_and_cannot_authorize_scores(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False)
 r=run(m,s,end+timedelta(minutes=2),read_acquisition=lambda *a:pytest.fail('unemitted issue cannot read a label'))
 assert r['scored']==0 and r['prepared_not_confirmed']==1 and r['completed_scores']==0
 assert q.summary()['confirmed']==0


def test_natural_maturity_scores_original_once_across_restart_without_refitting(tmp_path,monkeypatch):
 m,s,q,issue,key,start,end=setup(tmp_path)
 import weather_learning.rain_two_part as fitter
 monkeypatch.setattr(fitter,'fit_two_part',lambda *a,**k:pytest.fail('monitor must not refit'))
 early=run(m,s,end+timedelta(seconds=119),read_acquisition=lambda *a:pytest.fail('immature label read'))
 assert early['observations_attempted']==0
 r=run(m,s,end+timedelta(seconds=120));assert r['scored']==r['completed_scores']==1 and r['observations_attempted']==1
 assert r['comparisons']['records']==1 and r['comparisons']['probability_calibration_qualified'] is False
 m.RainQueue(s,policy=POLICY)
 again=run(m,s,end+timedelta(hours=1),read_acquisition=lambda *a:pytest.fail('completed original was read twice'))
 assert again['completed_scores']==1 and again['observations_attempted']==0


def test_preview_preserves_every_original_index_emission_and_capture_byte(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path);before={p:p.read_bytes() for p in s.root.rglob('*') if p.is_file()}
 r=run(m,s,end+timedelta(seconds=120),apply=False)
 assert r['would_score']==1 and r['scored']==0
 assert {p:p.read_bytes() for p in s.root.rglob('*') if p.is_file()}==before


def test_late_cache_emission_is_retained_but_never_called_as_issued(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False)
 q.publish([issue],clock=lambda:start+timedelta(seconds=1))
 r=run(m,s,end+timedelta(minutes=2),read_acquisition=lambda *a:pytest.fail('late emission cannot read a label'))
 assert r['scored']==0 and r['capacity']['late_emission_targets']==1


def test_confirm_requires_exact_actual_cache_bytes(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False)
 s._write(s.root/m.CACHE,{'wrong':'original'})
 with pytest.raises(ValueError,match='cache'):q.confirm(key,clock=lambda:start-timedelta(minutes=30))
 assert q.summary()['confirmed']==0


def test_cache_write_before_index_commit_is_recoverable_with_actual_readback(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False)
 wrapper=q.original(key);s._write(s.root/m.CACHE,wrapper['public_view']);q.db.unlink()
 recovered=m.RainQueue(s,policy=POLICY);recovered.recover(clock=lambda:start-timedelta(minutes=30))
 assert recovered.summary()['confirmed']==1
 r=run(m,s,end+timedelta(minutes=2));assert r['scored']==1


def test_missing_producer_original_defers_and_recovery_never_substitutes_current_code(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path);wrapper=q.original(key);p=q.producers/(wrapper['producer_sha256']+'.json');raw=p.read_bytes();p.unlink()
 r=run(m,s,end+timedelta(minutes=2),read_acquisition=lambda *a:pytest.fail('missing original cannot read a label'))
 assert r['withheld']['missing_original']==1 and r['scored']==0
 p.write_bytes(raw);p.chmod(0o600)
 r=run(m,s,end+timedelta(hours=2));assert r['scored']==1


def test_new_measurement_epoch_withholds_local_policy_but_retains_raw_comparison(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,cohort='f'*64)
 r=run(m,s,end+timedelta(minutes=2));assert r['scored']==1
 with q.connect() as db:value=json.loads(db.execute('SELECT body FROM scores').fetchone()[0])
 assert value['measurement_cohort_compatible'] is False
 assert value['local']['probability_wet'] is None and value['local']['reason']=='measurement_cohort_changed'
 assert value['raw']['total_precipitation_1hr']['absolute_error_mm']==pytest.approx(24-2.54)


def test_expired_uncaptured_work_is_visible_and_does_not_query_forever(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path)
 r=run(m,s,end+timedelta(days=8),read_acquisition=lambda *a:pytest.fail('expired uncaptured work queried'))
 assert r['expired']==1 and r['observations_attempted']==0 and r['completed_scores']==0


def test_global_timeout_propagates_without_fabricated_score(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path)
 def stop(*a):raise TimeoutError('global deadline')
 with pytest.raises(TimeoutError):run(m,s,end+timedelta(minutes=2),read_acquisition=stop)
 with q.connect() as db:assert db.execute('SELECT COUNT(*) FROM scores').fetchone()[0]==0


def test_rain_originals_share_existing_shadow_capacity_guard(tmp_path):
 s=ShadowStore(tmp_path/'state');directory=s.root/'rain-issues';directory.mkdir(mode=0o700)
 p=directory/'capacity.json'
 with p.open('wb') as f:f.truncate(2*1024**3)
 p.chmod(0o600)
 with pytest.raises(ValueError,match='capacity'):s._write(s.root/'weather-outcomes/new.json',{'no':'overrun'})


def test_equivalent_json_with_different_cache_bytes_is_not_emission_proof(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False);view=q.original(key)['public_view']
 p=s.root/m.CACHE;p.write_text(json.dumps(view,indent=2)+'\n');p.chmod(0o600)
 with pytest.raises(ValueError,match='cache'):q.confirm(key,clock=lambda:start-timedelta(minutes=30))
 assert q.summary()['confirmed']==0


def test_saved_score_keeps_grid_availability_and_original_artifact_identity(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path);run(m,s,end+timedelta(minutes=2))
 with q.connect() as db:value=json.loads(db.execute('SELECT body FROM scores').fetchone()[0])
 f=issue.to_dict()['forecast']
 assert value['grid_sha256']==f['grid_sha256'] and value['timezone']==f['site']['timezone']
 assert value['availability_basis']==f['availability_basis']
 assert value['local_model_sha256'] is None and value['gain_model_sha256'] is None


def test_future_report_keeps_unavailable_candidate_coverage_and_raw_fallback(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path);r=run(m,s,end+timedelta(minutes=2))
 c=next(iter(r['comparisons']['cohorts'].values()))
 assert c['local']['predicted_records']==0 and c['local']['brier'] is None
 assert c['local']['fallback_mae_mm']==c['raw_mae_mm']['total_precipitation_1hr']
 assert c['gain']['predicted_records']==0


def test_backdated_query_availability_cannot_be_reused_as_a_new_capture(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path)
 old=read(Connection())
 r=run(m,s,end+timedelta(hours=1),read_acquisition=lambda *a:old)
 assert r['scored']==0 and r['withheld']['invalid_acquisition']==1
 assert list((s.root/'weather-outcomes').glob('*.rain.json'))==[]


def test_old_completed_scores_remain_durable_outside_the_report_window(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path);run(m,s,end+timedelta(minutes=2))
 r=run(m,s,end+timedelta(days=35),read_acquisition=lambda *a:pytest.fail('completed original reread'))
 assert r['completed_scores']==1 and r['comparisons']['records']==0
 assert r['report_target_window_days']==28


def test_late_horizon_original_is_not_lost_to_a_recent_issue_lookback(tmp_path):
 from test_weather_rain_day import day_rows,POLICY as native
 from weather_learning.rain_history import read_interval
 from weather_learning.rain_issues import make_issue
 m=api();s=ShadowStore(tmp_path/'state');q=m.RainQueue(s,policy=POLICY)
 source,first,last=rain_snapshot(DAY,hours=360);start=first+timedelta(days=13);end=start+timedelta(days=1);issued=first-timedelta(hours=3)
 f=make_forecast(snapshot=source,start=start,end=end,issued_at=issued,completed_at=issued+timedelta(seconds=1),interval_kind='local_calendar_day',availability_basis='recorded_ingestion_availability')
 rows=day_rows(start.astimezone(__import__('zoneinfo').ZoneInfo('America/Denver')).date());clock=[end+timedelta(minutes=2)]
 def acquire(work,assessed):
  times=iter([clock[0],clock[0]+timedelta(seconds=1)])
  a=read_interval(lambda:Connection(carry=rows[0],rows=rows[1:]),start=start,end=end,cutover=first-timedelta(days=1),policy=native,resolution_source=None,experiment_policy=POLICY,clock=lambda:next(times));clock[0]+=timedelta(seconds=1);return a
 # The expected epoch can be unknown initially; raw scoring must still mature.
 issue=make_issue(f,model=None,observation_cohort_sha256='f'*64,policy=POLICY,prepared_at=issued+timedelta(seconds=1),mode='prospective_shadow')
 q.publish([issue],clock=lambda:issued+timedelta(seconds=2))
 r=m.monitor_rain(s,now=clock[0],policy=POLICY,observation_policy_sha256='a'*64,read_acquisition=acquire,clock=lambda:clock[0],limit=1,apply=True)
 assert r['scored']==1 and r['completed_scores']==1 and r['observations_attempted']==1


def test_score_cohorts_do_not_pool_different_original_grids(tmp_path):
 from copy import deepcopy
 from weather_learning.contracts import identity
 m,s,q,issue,key,start,end=setup(tmp_path);run(m,s,end+timedelta(minutes=2))
 with q.connect() as db:r=json.loads(db.execute('SELECT body FROM scores').fetchone()[0])
 other=deepcopy(r);other['grid_sha256']='f'*64;other['score_sha256']=identity({k:v for k,v in other.items() if k!='score_sha256'})
 assert len(m._comparisons([r,other])['cohorts'])==2
 other['raw']['total_precipitation_1hr']['absolute_error_mm']=0.
 with pytest.raises(ValueError,match='unchanged'):m._comparisons([other])


def test_original_v1_wrapper_keeps_its_original_two_hour_view_lifetime(tmp_path):
 from weather_learning.contracts import identity
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False);current=q.original(key)
 legacy=dict(schema='earthship-retained-rain-shadow/v1',issues=current['issues'],producer_sha256=current['producer_sha256'],public_view=m.public_view(current['issues']),automatic_actuation=False);legacy['wrapper_sha256']=identity(legacy);oldkey=legacy['wrapper_sha256']
 s._write(q.originals/(oldkey+'.json'),legacy,immutable=True);q._register(legacy);s._write(s.root/m.CACHE,legacy['public_view']);q.confirm(oldkey,clock=lambda:start-timedelta(minutes=30))
 loaded,emitted=q.load_bundle(oldkey)
 assert loaded['public_view']['schema']=='earthship-rain-shadow-view/v1'
 assert instant(loaded['public_view']['valid_until'])-instant(loaded['public_view']['generated_at'])==timedelta(hours=2)
 assert current['public_view']['schema']=='earthship-rain-shadow-view/v2'
 assert instant(current['public_view']['valid_until'])-instant(current['public_view']['generated_at'])==timedelta(hours=6)


def test_supported_original_probability_scores_against_training_only_climatology_without_refitting(tmp_path,monkeypatch):
 from test_rain_two_part import population,fit,future
 from test_weather_rain_day import POLICY as native,snapshot as packet
 from weather_learning.rain_history import read_interval
 import weather_learning.rain_two_part as fitter
 m=api();data=population();model=fit(data)['model'];f=future(.25);body=f.to_dict();start,end=map(instant,(body['start'],body['end']));original=data[1][0].to_dict();source=original['sources']
 issue=make_issue(f,model=model,observation_cohort_sha256=original['cohort_sha256'],policy=POLICY,prepared_at=instant(body['issued_at'])+timedelta(seconds=1),mode='prospective_shadow')
 s=ShadowStore(tmp_path/'state');q=m.RainQueue(s,policy=POLICY);q.publish([issue],clock=lambda:instant(body['issued_at'])+timedelta(seconds=2))
 rows=[];at=start-timedelta(seconds=30)
 while at<=end+timedelta(seconds=120):
  rows.append(packet(at,len(rows)+1,10.+(.12 if at>=start+timedelta(hours=12) else 0.)));at+=timedelta(seconds=90)
 clock=[end+timedelta(seconds=120)]
 def acquire(work,assessed):
  times=iter([clock[0],clock[0]+timedelta(seconds=1)]);a=read_interval(lambda:Connection(carry=rows[0],rows=rows[1:]),start=start,end=end,cutover=instant(original['request']['cutover']),policy=native,resolution_source=source['resolution_source'],experiment_policy=POLICY,clock=lambda:next(times));clock[0]+=timedelta(seconds=1);return a
 monkeypatch.setattr(fitter,'fit_two_part',lambda *a,**k:pytest.fail('scoring invoked a fit'))
 r=m.monitor_rain(s,now=clock[0],policy=POLICY,observation_policy_sha256='a'*64,read_acquisition=acquire,clock=lambda:clock[0],limit=1,apply=True)
 c=next(iter(r['comparisons']['cohorts'].values()));assert r['scored']==1 and c['local']['predicted_records']==1
 assert c['local']['training_only_climatology_brier']==.25 and c['local']['brier']<.25
 assert c['context']['local_model_sha256']==model['model_sha256'] and r['probability_calibration_qualified'] is False


def test_publication_lock_rechecks_confirmed_generation_before_replacing_cache(tmp_path):
 m,s,q,issue,key,start,end=setup(tmp_path,publish=False);first=q.publish([issue],generation='a'*64,clock=lambda:start-timedelta(minutes=50));before={p:p.read_bytes() for p in s.root.rglob('*') if p.is_file()}
 body=issue.to_dict();later=make_issue(__import__('weather_learning.rain_calibration',fromlist=['RainForecast']).RainForecast(canonical(body['forecast'])),model=None,observation_cohort_sha256=body['observation_cohort_sha256'],policy=POLICY,prepared_at=instant(body['prepared_at'])+timedelta(minutes=1),mode='prospective_shadow')
 second=q.publish([later],generation='a'*64,clock=lambda:start-timedelta(minutes=45))
 assert second==first and {p:p.read_bytes() for p in s.root.rglob('*') if p.is_file()}==before
