"""Actual production emissions mature under one bounded, recoverable evaluator."""
from datetime import timedelta
import json
import pytest
from test_production_forecast import serving,NOW
from test_production_emissions import published
from weather_learning.contracts import instant
from weather_learning.shadow import ShadowStore
from weather_learning.production_emissions import retain_prepared,confirm_publication
from learning_fixtures import EPOCH,receipt


def setup(serving,tmp_path,*,confirmed=True):
 product,attempt,result=published(serving);state=ShadowStore(tmp_path/'queue-state')
 retain_prepared(state,product,provider=serving['provider'],now=NOW)
 emission=confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result) if confirmed else None
 return state,product,emission


def run(state,now,**kwargs):
 from weather_learning.production_queue import monitor_production
 from weather_learning.marginal_outcomes import temperature_observation,wind_observation
 from weather_learning.correction_monitor import wind_outcome
 def read(work,assessed):
  target=instant(work['end'])
  if work['kind']=='temperature':return temperature_observation(receipt(target),target=target,acquired_at=now,sensor_epoch=EPOCH,observation_policy_sha256='c'*64)
  start=instant(work['start']);rows=[(start+timedelta(minutes=i),2.) for i in range(61)]
  return wind_observation(wind_outcome(rows,start=start,assessed_at=now,source_available_at=now,unit='mph'),acquired_at=now,observation_policy_sha256='c'*64)
 return monitor_production(state,**(dict(now=now,observation_policy_sha256='c'*64,read_observation=read,limit=1,apply=True,clock=lambda:now)|kwargs))


def test_unconfirmed_preparation_never_creates_scoring_work_or_reads_observations(serving,tmp_path):
 state,_,_=setup(serving,tmp_path,confirmed=False)
 result=run(state,NOW+timedelta(hours=2),read_observation=lambda *args:pytest.fail('unissued cannot be scored'))
 assert result['observations_attempted']==result['scored']==0 and result['prepared_not_confirmed']==1
 assert not (state.root/'production-scores.sqlite3').exists()


def test_confirmed_forecast_scores_once_and_restart_never_refits_or_rereads(serving,tmp_path,monkeypatch):
 from weather_learning import probabilistic
 state,_,emission=setup(serving,tmp_path);now=NOW.replace(minute=0)+timedelta(hours=1,minutes=3)
 monkeypatch.setattr(probabilistic,'fit_marginal',lambda *a,**k:pytest.fail('monitor refitted a model'))
 first=run(state,now);assert first['scored']==first['completed_scores']==first['observations_attempted']==1
 assert first['comparisons']['cohorts'][0]['active_policy']['mae']<.5
 assert first['comparisons']['cohorts'][0]['raw']['mae']==2
 again=run(ShadowStore(state.root),now+timedelta(minutes=1),read_observation=lambda *args:pytest.fail('completed target reread'))
 assert again['completed_scores']==1 and again['observations_attempted']==0
 from weather_learning.production_queue import ProductionQueue
 with ProductionQueue(state).connect() as db:score=json.loads(db.execute('SELECT body FROM scores').fetchone()[0])
 assert score['emission_sha256']==emission['emission_sha256'] and score['local']['absolute_error']<.5


def test_preview_leaves_persistent_originals_and_index_bytes_unchanged(serving,tmp_path):
 state,_,_=setup(serving,tmp_path);now=NOW.replace(minute=0)+timedelta(hours=1,minutes=3)
 before={p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
 result=run(state,now,apply=False)
 assert result['would_score']==1 and result['scored']==0
 assert {p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}==before


def test_fsynced_emissions_recover_after_index_loss_without_clock_renewal(serving,tmp_path):
 from weather_learning.production_queue import ProductionQueue
 state,_,emission=setup(serving,tmp_path);queue=ProductionQueue(state)
 queue.register(emission['emission_sha256']);path=state.root/'production-emissions'/(emission['emission_sha256']+'.json');before=path.read_bytes()
 with queue.connect() as db:db.execute('DELETE FROM targets');db.execute('DELETE FROM emissions')
 result=run(state,NOW.replace(minute=0)+timedelta(hours=1,minutes=3))
 assert result['scored']==1 and path.read_bytes()==before


def test_unavailable_original_is_named_dependency_before_any_label_read(serving,tmp_path):
 from weather_learning.production_queue import ProductionQueue
 state,product,emission=setup(serving,tmp_path);queue=ProductionQueue(state);queue.register(emission['emission_sha256'])
 path=state.root/'production-issues'/(product.to_dict()['issue_sha256']+'.json');raw=path.read_bytes();path.unlink()
 result=run(state,NOW.replace(minute=0)+timedelta(hours=1,minutes=3),read_observation=lambda *args:pytest.fail('missing original cannot read labels'))
 assert result['scored']==0 and result['withheld']['missing_original']==1
 path.write_bytes(raw);path.chmod(0o600)
 result=run(state,NOW.replace(minute=0)+timedelta(hours=2,minutes=4))
 assert result['scored']==1


def test_targets_with_no_timely_original_capture_expire_without_late_queries(serving,tmp_path):
 state,_,_=setup(serving,tmp_path)
 result=run(state,NOW+timedelta(days=10),limit=48,read_observation=lambda *args:pytest.fail('expired target queried'))
 assert result['observations_attempted']==result['scored']==0 and result['expired']>0


def test_zero_budget_has_no_label_reads_and_global_ceiling_is_not_expanded(serving,tmp_path):
 state,_,_=setup(serving,tmp_path)
 assert run(state,NOW+timedelta(hours=3),limit=0,read_observation=lambda *args:pytest.fail('zero allowance queried'))['observations_attempted']==0
 with pytest.raises(ValueError):run(state,NOW,limit=49)



def test_changed_sensor_cohort_is_a_completed_diagnostic_not_a_valid_score(serving,tmp_path):
 from weather_learning.marginal_outcomes import temperature_observation
 state,_,_=setup(serving,tmp_path);now=NOW.replace(minute=0)+timedelta(hours=1,minutes=3);epoch='00000000-0000-4000-8000-000000000099'
 def read(work,assessed):
  target=instant(work['end']);return temperature_observation(receipt(target,epoch=epoch),target=target,acquired_at=now,sensor_epoch=epoch,observation_policy_sha256='c'*64)
 value=run(state,now,read_observation=read)
 assert value['completed_scores']==0 and value['completed_diagnostics']==1
 assert value['comparisons']['incompatible_records']==1 and value['comparisons']['cohorts']==[]


def test_late_discovery_reuses_timely_original_capture_after_the_seven_day_deadline(serving,tmp_path):
 from weather_learning.marginal_outcomes import captured_observations,temperature_observation
 state,_,emission=setup(serving,tmp_path);ref=next(r for r in emission['score_rows'] if r['kind']=='temperature');target=instant(ref['at']);ready=target+timedelta(minutes=2)
 work=dict(kind='temperature',start=target.isoformat(),end=target.isoformat())
 captured_observations(state,[work],now=ready,observation_policy_sha256='c'*64,
  read=lambda *a:temperature_observation(receipt(target),target=target,acquired_at=ready,sensor_epoch=EPOCH,observation_policy_sha256='c'*64),apply=True,clock=lambda:ready)
 value=run(state,target+timedelta(days=10),read_observation=lambda *a:pytest.fail('timely original must be reused'))
 assert value['scored']==1 and value['completed_scores']==1
