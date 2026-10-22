"""Durable all-publication work survives restarts and original-source gaps."""
from datetime import timedelta
from dataclasses import replace
import importlib.util,json
from pathlib import Path
import pytest
from test_refresh_evaluation import sources,publication
from learning_fixtures import SITE,EPOCH,receipt
from weather_learning.contracts import instant
from weather_learning.features import local_temperature_outcome
from weather_learning.shadow import ShadowStore


def api():
    assert importlib.util.find_spec('weather_learning.refresh_queue'), 'Task6 durable refresh queue missing'
    from weather_learning import refresh_queue
    return refresh_queue


def setup(tmp_path,sources):
    attempt,result=publication(tmp_path,sources);state=ShadowStore(tmp_path/'state')
    q=api().RefreshQueue(state)
    key=q.retain(attempt,result,archive=sources[0],site=SITE,clock=lambda:instant(result['completed_at']))
    return state,q,key,attempt,result


def observed(targets,assessed):
    return {at:replace(local_temperature_outcome(receipt(at,18),target_at=at,assessed_at=assessed,sensor_epoch=EPOCH),
        available_at=at+timedelta(minutes=1)) for at in targets}


def monitor(state,archive,now,**kwargs):
    args=dict(archive=archive,site=SITE,now=now,sensor_epoch=EPOCH,observation_policy_sha256='a'*64,
        read_outcomes=observed,apply=True,limit=8)
    args.update(kwargs);return api().monitor_refresh(state,**args)


def test_all_same_day_publications_get_independent_bounded_targets(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    later=tmp_path/'later';later.mkdir(mode=0o700)
    attempt,result=publication(later,(*sources[:3],sources[3]+timedelta(minutes=1)))
    second=q.retain(attempt,result,archive=sources[0],site=SITE,clock=lambda:instant(result['completed_at']))
    assert key!=second
    assert q.summary()['decisions']==2 and q.summary()['targets']==62
    with state._connect() as db:assert db.execute('SELECT COUNT(*) FROM issues').fetchone()[0]==0


def test_original_registration_is_idempotent_and_scores_survive_restart(tmp_path,sources):
    state,q,key,attempt,result=setup(tmp_path,sources)
    assert q.retain(attempt,result,archive=sources[0],site=SITE,clock=lambda:sources[3]+timedelta(minutes=1))==key
    now=sources[3]+timedelta(hours=2)
    first=monitor(state,sources[0],now,limit=1)
    assert first['scored']==1 and first['observations_attempted']==1
    second=monitor(ShadowStore(state.root),sources[0],now,limit=1)
    assert second['scored']==1  # progresses to next due target, not the completed one
    assert second['completed_scores']==2


def test_long336h_target_matures_once_even_when_discovery_is_late(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    record=q.load(key,archive=sources[0],site=SITE)
    at=instant(record.to_dict()['targets'][-1]['target_at'])
    assert record.to_dict()['targets'][-1]['offset_from_first_hour']==336
    def only_last(targets,assessed):return {t:v for t,v in observed(targets,assessed).items() if t==at}
    now=at+timedelta(days=20)
    first=monitor(state,sources[0],now,limit=32,read_outcomes=only_last)
    assert first['scored']==1
    second=monitor(ShadowStore(state.root),sources[0],now+timedelta(minutes=1),limit=32,
        read_outcomes=lambda *args:pytest.fail('all other targets deferred and336hscore must not be reread'))
    assert second['observations_attempted']==0 and second['completed_scores']==1


def test_missing_original_source_is_dependency_not_current_forecast_fallback(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    p=sources[0].objects/(sources[2]+'.json');raw=p.read_bytes();p.unlink()
    now=sources[3]+timedelta(hours=2)
    result=monitor(state,sources[0],now,limit=1)
    assert result['scored']==0 and result['withheld']['missing_original']==1
    p.write_bytes(raw);p.chmod(0o600)
    result=monitor(state,sources[0],now+timedelta(hours=2),limit=1)
    assert result['scored']==1


def test_preview_does_not_change_index_or_issue_bytes(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    before={p:p.read_bytes() for p in [q.db,*q.originals.glob('*.json')]}
    preview=monitor(state,sources[0],sources[3]+timedelta(hours=2),limit=1,apply=False)
    assert preview['would_score']==1 and preview['scored']==0
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_fsync_original_can_recover_after_index_registration_is_lost(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    with q.connect() as db:
        db.execute('DELETE FROM targets');db.execute('DELETE FROM decisions')
    assert api().RefreshQueue(state).recover(limit=1)['recovered']==1
    assert q.summary()['decisions']==1 and q.summary()['targets']==31


def test_rehashed_wrapper_cannot_replace_original_index_generation(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    p=q.originals/(key+'.json');value=json.loads(p.read_bytes())
    value['decision']['targets'][0]['forecasts']['actual_serving']['value_c']=99
    from weather_learning.contracts import identity,canonical
    value['wrapper_sha256']=identity({k:v for k,v in value.items() if k!='wrapper_sha256'})
    p.write_bytes(canonical(value))
    with pytest.raises(ValueError,match='original'):
        q.load(key,archive=sources[0],site=SITE)


def test_database_and_due_work_are_bounded_and_late_observations_withheld(tmp_path,sources):
    state,q,key,_,_=setup(tmp_path,sources)
    with q.connect() as db:
        assert db.execute('PRAGMA max_page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]<=64*1024**2
    with pytest.raises(ValueError):monitor(state,sources[0],sources[3],limit=33)
    def late(targets,assessed):return {at:replace(o,available_at=at+timedelta(days=8)) for at,o in observed(targets,assessed).items()}
    result=monitor(state,sources[0],sources[3]+timedelta(days=30),limit=1,read_outcomes=late)
    assert result['scored']==0 and result['withheld']['outcome_unqualified']==1


def test_first_actual_observation_capture_is_shared_across_forecast_origins(tmp_path,sources):
    state,_,_,_,_=setup(tmp_path,sources);at=sources[3].replace(minute=0)+timedelta(hours=1)
    assert hasattr(api(),'captured_refresh_outcomes'), 'actual first acquisition must be retained per observed target'
    first=api().captured_refresh_outcomes(state,[at],assessed_at=at+timedelta(minutes=2),sensor_epoch=EPOCH,
        observation_policy_sha256='a'*64,read_temperature=lambda targets,now:{t:receipt(t,18) for t in targets},apply=True,
        clock=lambda:at+timedelta(minutes=2,seconds=1))
    second=api().captured_refresh_outcomes(state,[at],assessed_at=at+timedelta(hours=1),sensor_epoch=EPOCH,
        observation_policy_sha256='a'*64,read_temperature=lambda *args:pytest.fail('original capture must be reused'),apply=True,
        clock=lambda:at+timedelta(hours=1))
    assert first[at].available_at==second[at].available_at==at+timedelta(minutes=2,seconds=1)
    assert first[at].receipt_digest==second[at].receipt_digest


def test_preview_observation_capture_has_no_persistent_side_effects(tmp_path,sources):
    state,_,_,_,_=setup(tmp_path,sources);at=sources[3].replace(minute=0)+timedelta(hours=1)
    assert hasattr(api(),'captured_refresh_outcomes'), 'explicit original acquisition adapter missing'
    before=set(state.root.rglob('*'))
    result=api().captured_refresh_outcomes(state,[at],assessed_at=at+timedelta(minutes=2),sensor_epoch=EPOCH,
        observation_policy_sha256='a'*64,read_temperature=lambda targets,now:{t:receipt(t,18) for t in targets},apply=False,
        clock=lambda:at+timedelta(minutes=2,seconds=1))
    assert result[at].available_at==at+timedelta(minutes=2,seconds=1)
    assert set(state.root.rglob('*'))==before


def test_missing_old_target_retry_does_not_starve_a_new_unattempted_target(tmp_path,sources):
    state,_,_,_,_=setup(tmp_path,sources);now=sources[3]+timedelta(hours=2)
    monitor(state,sources[0],now,limit=1,read_outcomes=lambda *args:{})
    requested=[]
    def read(targets,assessed):requested.extend(targets);return observed(targets,assessed)
    monitor(state,sources[0],now+timedelta(hours=1),limit=1,read_outcomes=read)
    assert requested==[sources[3].replace(minute=0)+timedelta(hours=2)]


def test_post_query_acquisition_is_assessed_at_real_completion_not_backdated_start(tmp_path,sources):
    state,_,_,_,_=setup(tmp_path,sources)
    at=sources[3].replace(minute=0)+timedelta(hours=1);now=at+timedelta(minutes=2)
    clock=lambda:now+timedelta(seconds=1)
    def read(targets,assessed):
        return api().captured_refresh_outcomes(state,targets,assessed_at=assessed,sensor_epoch=EPOCH,
            observation_policy_sha256='a'*64,read_temperature=lambda ts,a:{t:receipt(t,18) for t in ts},apply=True,clock=clock)
    result=monitor(state,sources[0],now,limit=1,read_outcomes=read,clock=clock)
    assert result['scored']==1
    assert result['generated_at']==(now+timedelta(seconds=1)).isoformat()
    assert len(list((state.root/'weather-outcomes').glob('*.refresh.json')))==1
