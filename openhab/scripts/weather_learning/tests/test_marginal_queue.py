"""Only confirmed original shadow emissions become durable scoring work."""
from dataclasses import replace
from datetime import timedelta
import importlib.util,json
import pytest
from learning_fixtures import T,EPOCH,SITE,native_snapshot,receipt
from test_probabilistic import POLICY,pairs
from weather_learning.contracts import instant,identity,canonical
from weather_learning.shadow import ShadowStore


def api():
    assert importlib.util.find_spec('weather_learning.marginal_queue'), 'Task7 durable marginal issue/emission queue missing'
    from weather_learning import marginal_queue
    return marginal_queue


def setup(tmp_path,*,publish=True):
    from weather_learning.probabilistic_artifacts import fit_candidates,retain_candidates
    from weather_learning.probabilistic_issue import temperature_context,prepare_marginal_issue
    from weather_learning.probabilistic_retained import prepare_marginal_source
    state=ShadowStore(tmp_path/'state');at=T+timedelta(days=15,hours=9);snapshot=native_snapshot(day=15,hours=360)
    ctx=temperature_context(receipt(at),sampled_at=at,acquired_at=at,sensor_epoch=EPOCH)
    frame=prepare_marginal_source(snapshot,assessed_at=at).forecast('temperature',target=at+timedelta(hours=1),quality=ctx.quality_at(at),origin=at)
    rows=[replace(p,forecast=replace(p.forecast,cohort_sha256=frame.cohort_sha256,grid_sha256=frame.grid_sha256)) for p in pairs()]
    fitted=fit_candidates(rows,cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,population_sha256='a'*64)
    ref=retain_candidates(state,fitted,policy=POLICY);artifacts={ref['bundle_sha256']:ref['artifact_sha256']}
    issue=prepare_marginal_issue(snapshots=[snapshot],decision=at,site=SITE,contexts={'temperature':ctx},bundles=[fitted.bundle],policy=POLICY)
    queue=api().MarginalQueue(state,policy=POLICY);key=queue.retain(issue,model_artifacts=artifacts)
    if publish:queue.publish(issue,model_artifacts=artifacts,clock=lambda:at+timedelta(seconds=1))
    return state,queue,key,issue,at,artifacts


def run(state,now,**kw):
    from weather_learning.marginal_outcomes import temperature_observation
    args=dict(now=now,policy=POLICY,observation_policy_sha256='a'*64,
        read_observation=lambda w,a:temperature_observation(receipt(instant(w['end'])),target=instant(w['end']),acquired_at=now,sensor_epoch=EPOCH,observation_policy_sha256='a'*64),apply=True,limit=8,clock=lambda:now)
    args.update(kw);return api().monitor_marginals(state,**args)


def test_preparation_alone_is_not_issued_and_confirmation_requires_cache_readback(tmp_path):
    state,q,key,issue,at,artifacts=setup(tmp_path,publish=False)
    r=run(state,at+timedelta(hours=2),read_observation=lambda *a:pytest.fail('unissued cannot score'))
    assert r['scored']==r['observations_attempted']==0 and r['prepared_not_confirmed']==1
    with pytest.raises((ValueError,FileNotFoundError)):q.confirm(key,clock=lambda:at)
    assert q.publish(issue,model_artifacts=artifacts,clock=lambda:at+timedelta(seconds=1))==key
    assert q.summary()['confirmed']==1 and q.summary()['targets']==11


def test_original_scores_survive_restart_and_completed_labels_never_refit_or_reread(tmp_path,monkeypatch):
    state,q,key,issue,at,_=setup(tmp_path)
    from weather_learning import probabilistic
    monkeypatch.setattr(probabilistic,'fit_marginal',lambda *a,**k:pytest.fail('scoring cannot refit'))
    monkeypatch.setattr(probabilistic,'fit_adaptive',lambda *a,**k:pytest.fail('scoring cannot refit'))
    first=run(state,at+timedelta(hours=1,minutes=2),limit=1)
    assert first['scored']==first['observations_attempted']==first['completed_scores']==1
    second=run(ShadowStore(state.root),at+timedelta(hours=1,minutes=3),read_observation=lambda *a:pytest.fail('completed target reread'))
    assert second['observations_attempted']==0 and second['completed_scores']==1
    with q.connect() as db:body=json.loads(db.execute('SELECT body FROM scores').fetchone()[0])
    assert body['raw']['wis'] is None and body['local']['temperature_normal']['crps'] is not None
    assert body['local']['empirical']['wis'] is not None and body['issued'] is True
    assert body['local_coverage_qualified'] is False


def test_336h_target_scores_once_after_late_discovery_with_timely_first_capture(tmp_path):
    from weather_learning.marginal_outcomes import captured_observations,temperature_observation
    state,q,key,issue,at,_=setup(tmp_path);row=issue.to_dict()['rows'][-1];target=instant(row['forecast']['target_end']);ready=target+timedelta(minutes=2)
    work=dict(kind='temperature',start=target.isoformat(),end=target.isoformat())
    captured_observations(state,[work],now=ready,observation_policy_sha256='a'*64,read=lambda w,a:temperature_observation(receipt(target),target=target,acquired_at=ready,sensor_epoch=EPOCH,observation_policy_sha256='a'*64),apply=True,clock=lambda:ready)
    now=target+timedelta(days=20)
    with q.connect() as db:db.execute('DELETE FROM targets WHERE target<>?',(target.isoformat(),))
    first=run(state,now,read_observation=lambda *a:pytest.fail('first capture must be reused'),limit=1)
    assert first['scored']==1
    second=run(ShadowStore(state.root),now+timedelta(minutes=1),read_observation=lambda *a:pytest.fail('completed336h target reread'),limit=1)
    assert second['observations_attempted']==0 and second['completed_scores']==1


def test_preview_preserves_original_index_emission_and_capture_bytes(tmp_path):
    state,q,_,_,at,_=setup(tmp_path);before={p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
    value=run(state,at+timedelta(hours=1,minutes=2),limit=1,apply=False)
    assert value['would_score']==1 and value['scored']==0
    assert {p:p.read_bytes() for p in state.root.rglob('*') if p.is_file()}==before


def test_missing_original_model_is_retry_dependency_not_a_new_prediction(tmp_path):
    state,q,_,_,at,refs=setup(tmp_path);path=state.root/'marginal-models'/(next(iter(refs.values()))+'.json');raw=path.read_bytes();path.unlink()
    value=run(state,at+timedelta(hours=1,minutes=2),limit=1,read_observation=lambda *a:pytest.fail('missing model cannot read label'))
    assert value['scored']==0 and value['withheld']['missing_original']==1
    path.write_bytes(raw);path.chmod(0o600)
    recovered=run(state,at+timedelta(hours=2,minutes=3),limit=1)
    assert recovered['scored']==1


def test_fsynced_emission_recovers_after_index_registration_loss(tmp_path):
    state,q,key,_,_,_=setup(tmp_path)
    with q.connect() as db:db.execute('DELETE FROM targets');db.execute('DELETE FROM issues')
    recovered=api().MarginalQueue(state,policy=POLICY).recover(limit=1)
    assert recovered['recovered']==1 and q.summary()['confirmed']==1 and q.summary()['targets']==11


def test_rehashed_original_wrapper_cannot_replace_indexed_generation(tmp_path):
    _,q,key,_,_,_=setup(tmp_path);p=q.originals/(key+'.json');body=json.loads(p.read_bytes())
    body['model_artifacts']={};body['wrapper_sha256']=identity({k:v for k,v in body.items() if k!='wrapper_sha256'});p.write_bytes(canonical(body))
    with pytest.raises(ValueError,match='original|generation'):q.load(key)


def test_unknown_late_observation_is_withheld_and_row_budget_is_strict(tmp_path):
    state,q,_,_,at,_=setup(tmp_path)
    value=run(state,at+timedelta(days=10),limit=1)
    assert value['scored']==0 and value['withheld']['outcome_arrived_late']==1
    with pytest.raises(ValueError):run(state,at,limit=9)
    with q.connect() as db:assert db.execute('PRAGMA max_page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]<=64*1024**2


def test_scoring_never_rebuilds_the_original_public_view_with_later_renderer(tmp_path,monkeypatch):
    state,q,key,_,at,_=setup(tmp_path)
    monkeypatch.setattr(api(),'public_issue',lambda *a,**k:pytest.fail('later renderer cannot rewrite original emission'))
    q.load(key)
    assert run(state,at+timedelta(hours=1,minutes=2),limit=1)['scored']==1


def test_recovery_of_cache_without_confirmation_uses_actual_recovery_clock(tmp_path):
    state,q,key,issue,at,_=setup(tmp_path,publish=False)
    state._write(state.root/api().CACHE,api().public_issue(issue.to_dict(),policy=POLICY))
    recovery=at+timedelta(hours=1,minutes=10)
    q.recover(clock=lambda:recovery)
    assert q.summary()['late_emission_targets']==1
    _,emission=q.load(key);assert emission['cache_write_completed_at']==recovery.isoformat()
    assert run(state,recovery,read_observation=lambda *a:pytest.fail('already-past first target was never confirmed in time'))['observations_attempted']==0


def test_backwards_clock_after_cache_write_cannot_confirm_publication(tmp_path):
    state,q,key,issue,at,artifacts=setup(tmp_path,publish=False)
    ticks=iter((at+timedelta(seconds=10),at+timedelta(seconds=5)))
    with pytest.raises(ValueError,match='clock|publication'):
        q.publish(issue,model_artifacts=artifacts,clock=lambda:next(ticks))
    assert q.summary()['confirmed']==0
