"""The explicit marginal producer uses retained weather and private source pins."""
from pathlib import Path
from datetime import timedelta
import importlib.util,json
import pytest
from learning_fixtures import T,EPOCH,SITE,receipt,native_snapshot
from weather_learning.contracts import canonical


def api():
    assert importlib.util.find_spec('weather_learning.marginal_runtime'), 'Task7 explicit marginal producer missing'
    from weather_learning import marginal_runtime
    return marginal_runtime


def context(tmp_path,**kw):
    from test_marginal_queue import setup
    from weather_learning.archive import Archive
    from daily_temperature_runtime import SOURCE_POLICY
    state,_,_,_,at,refs=setup(tmp_path,publish=False);archive=Archive(tmp_path/'archive');archive.store_snapshot(native_snapshot(day=15,hours=360))
    policy=tmp_path/'temperature.json';policy.write_bytes(canonical(dict(version=2,streams=dict(outdoor=dict(SOURCE_POLICY,sensor_epoch=EPOCH)))));policy.chmod(0o600)
    config=dict(schema='earthship-marginal-production-profile/v1',enabled=True,archive=str(archive.root),state=str(state.root),site=SITE.__dict__,model_artifacts=refs,
        temperature_policy=str(policy),temperature_db_config=str(tmp_path/'missing-db.json'),solar_origin_context=None,runtime_manifest=api().runtime_manifest())
    config.update(kw);path=tmp_path/'marginal.json';path.write_bytes(canonical(config));path.chmod(0o600)
    return state,path,config,at


def files(root):return {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_disabled_profile_does_not_read_measurements_or_publish_state(tmp_path):
    assert api();state,path,_,at=context(tmp_path,enabled=False);before=files(state.root)
    result=api().run(path,apply=True,clock=lambda:at,temperature_reader=lambda *a:pytest.fail('disabled profile must not query'))
    assert result['status']=='disabled' and result['retained'] is False and files(state.root)==before


def test_preview_reads_origin_before_decision_without_mutating_state(tmp_path):
    assert api();state,path,_,at=context(tmp_path);before=files(state.root);calls=[]
    def reader(target,policy,epoch):calls.append(target);return receipt(target)
    result=api().run(path,apply=False,clock=lambda:at,temperature_reader=reader)
    assert result['rows']==30 and result['local_candidate_rows']==24 and result['retained'] is False
    assert calls==[at] and files(state.root)==before


def test_explicit_apply_publishes_separate_raw_local_shadow_cache(tmp_path):
    assert api();state,path,_,at=context(tmp_path)
    result=api().run(path,apply=True,clock=lambda:at,temperature_reader=lambda target,*a:receipt(target))
    cache=json.loads((state.root/'marginal-candidates.json').read_bytes())
    assert result['retained'] is True and cache['product']=='read_only_unselected_shadow'
    assert cache['rows'][0]['raw']['p50'] is None and cache['rows'][0]['local']['temperature_normal']['mean']>11
    assert cache['local_coverage_qualified'] is False and cache['automatic_actuation'] is False
    assert not (state.root/'current-model.json').exists()


def test_closed_profile_and_exact_source_manifest_fail_before_measurement_read(tmp_path):
    assert api();state,path,config,at=context(tmp_path)
    for changed in (dict(config,action=True),dict(config,runtime_manifest={})):
        path.write_bytes(canonical(changed))
        with pytest.raises(ValueError,match='profile|source|runtime'):
            api().run(path,clock=lambda:at,temperature_reader=lambda *a:pytest.fail('invalid profile must fail before read'))
    assert not (state.root/'marginal-candidates.json').exists()


def test_incompatible_original_model_stays_raw_fallback_without_weight_relabel(tmp_path,monkeypatch):
    assert api();state,path,_,at=context(tmp_path);before=files(state.root/'marginal-models')
    from weather_learning import probabilistic_artifacts
    changed=probabilistic_artifacts.numerical_manifest();changed[next(iter(changed))]='f'*64
    monkeypatch.setattr(probabilistic_artifacts,'numerical_manifest',lambda:changed)
    result=api().run(path,apply=True,clock=lambda:at,temperature_reader=lambda target,*a:receipt(target))
    assert result['status']=='raw_fallback' and result['local_candidate_rows']==0 and files(state.root/'marginal-models')==before
    cache=json.loads((state.root/'marginal-candidates.json').read_bytes())
    assert all(all(v is None for v in r['local'].values()) for r in cache['rows'])


def test_origin_dependency_failure_preserves_raw_and_resource_failure_propagates(tmp_path):
    assert api();state,path,_,at=context(tmp_path)
    def missing(*a):raise ConnectionError('private dependency')
    result=api().run(path,clock=lambda:at,temperature_reader=missing)
    assert result['status']=='raw_fallback' and result['rows']==30
    def stopped(*a):raise MemoryError('allocation')
    with pytest.raises(MemoryError):api().run(path,clock=lambda:at,temperature_reader=stopped)


def test_database_driver_failure_keeps_optional_raw_forecast_available(tmp_path):
    import psycopg2
    assert api();_,path,_,at=context(tmp_path)
    def unavailable(*a):raise psycopg2.OperationalError('private database details')
    result=api().run(path,clock=lambda:at,temperature_reader=unavailable)
    assert result['status']=='raw_fallback' and result['rows']==30
    assert 'private database details' not in str(result)


def test_cli_failure_after_confirmed_cache_write_reports_unknown_partial_state(tmp_path,monkeypatch,capsys):
    assert api();state,path,_,at=context(tmp_path)
    from weather_learning.marginal_queue import MarginalQueue
    publish=MarginalQueue.publish
    def publish_then_fail(self,*args,**kw):
        publish(self,*args,**kw)
        raise OSError('private post-publication failure')
    monkeypatch.setattr(MarginalQueue,'publish',publish_then_fail)
    run=api().run
    monkeypatch.setattr(api(),'run',lambda path,**kw:run(path,clock=lambda:at,**kw))
    assert api().main(['--profile',str(path),'--apply'])==1
    body=json.loads(capsys.readouterr().out)
    assert (state.root/'marginal-candidates.json').exists()
    assert body['retained'] is None and body['emission_status']=='unknown_partial_state'
    assert 'private post-publication failure' not in str(body)
