"""Original delivered forecasts score only later source-qualified native truth."""
from datetime import timedelta
import importlib,json
import pytest
from test_household_models import prepared_thermal
from test_household_planning import setup,context
from test_household_pipeline import config
from household.codec import canonical,identity
from household.snapshot import HouseholdSnapshot
from household.control_contracts import instant


def api():
    assert importlib.util.find_spec('household.outcomes') is not None,'chronological household outcomes missing'
    return importlib.import_module('household.outcomes')


def inputs(tmp_path,monkeypatch):
    api()
    from household.outcome_origin import prepare_outcome_origin
    from household.pipeline import seal_pipeline
    from thermal_model.provisional_forecast import publication
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
    from thermal_model.temperature_history import STREAMS,POLICY
    from weather_temperature_evidence import TemperaturePolicy,MODELS
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_sources import build_temperature_source
    prepared,capture=prepared_thermal(tmp_path,monkeypatch);value=prepared.to_dict();issue=instant(value['issue'])
    receipts={name:dict(item=name,time=int((issue+timedelta(seconds=3+i)).timestamp()*1000),state=json.dumps(body))
        for i,(name,body) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))))}
    origin=prepare_outcome_origin(capture,receipts,code_revision='a'*40)
    snap=HouseholdSnapshot(canonical({key:item for key,item in value['snapshot'].items() if key!='snapshot_id'}));_,registry=setup()
    runtime={'household/pipeline.py':'a'*64};plan=seal_pipeline(snapshot=snap,registry=registry,energy_inputs=None,thermal_inputs=prepared,
        thermal_runtime=value['executing_runtime'],coordination={**context(snap),'facts':{},'baseline_soc_floor':None},config=config(),
        now=instant(value['snapshot']['created_at']),runtime_manifest=runtime)
    phase=snap.to_dict()['domains']['thermal']['air_temperature']['evidence']['hardware_epoch']
    stream,model,sensor_id=STREAMS['air'];policy=TemperaturePolicy(model,sensor_id,**POLICY)
    target=issue+timedelta(hours=1);observed=target-timedelta(seconds=60);assessed=target+timedelta(minutes=5)
    collector=TemperatureCollector({stream:policy},sensor_epochs={stream:phase},clock=lambda:observed,process_id=lambda:1,monotonic=lambda:1000.)
    collector.observe({'model':model,'id':str(sensor_id),MODELS[model][1]:'75'})
    source=build_temperature_source(rows=[(observed,json.dumps(collector.snapshot()))],targets=[target],assessed_at=assessed,stream=stream,policy=policy,sensor_epoch=phase)
    return dict(plan_receipt=plan,origin=origin,outcome_sources={'1':source},assessed_at=assessed,
        plan_runtime_manifest=runtime,outcome_runtime_manifest={'household/outcomes.py':'b'*64},thermal_runtime=value['executing_runtime'])


def test_original_forecast_and_mature_native_truth_rederive_model_and_persistence_errors(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);result=api().seal_outcomes(**args);pair=result['output']['thermal']['1']
    assert pair['status']=='scored' and pair['actual_f']==75.
    assert pair['errors_f']['model']==pair['predictions_f']['model']-75.
    assert pair['errors_f']['persistence']==pair['predictions_f']['persistence']-75.
    assert result['output']['thermal']['6']['status']=='not_mature'
    assert result['output']['energy']['status']=='unavailable'
    assert result['output']['automatic_actuation'] is False and result['output']['causal_benefit_qualified'] is False


@pytest.mark.parametrize('damage',['epoch','stream','target','policy','clock','extra'])
def test_changed_native_outcome_context_refuses_scoring(tmp_path,monkeypatch,damage):
    args=inputs(tmp_path,monkeypatch);packet=args['outcome_sources']['1']
    if damage=='epoch':packet['sensor_epoch']='00000000-0000-0000-0000-000000000001'
    elif damage=='stream':packet['stream']='outdoor'
    elif damage=='target':packet['targets']=[(args['assessed_at']+timedelta(hours=1)).isoformat()]
    elif damage=='policy':packet['policy']['validity_seconds']=300
    elif damage=='clock':packet['assessed_at']=(args['assessed_at']+timedelta(seconds=1)).isoformat()
    else:packet['qualified']=True
    with pytest.raises(ValueError):api().seal_outcomes(**args)


def test_missing_mature_source_does_not_count_as_zero_error(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);args['outcome_sources']={};result=api().seal_outcomes(**args)
    assert result['output']['thermal']['1']['status']=='source_unavailable'
    assert result['output']['thermal']['1']['errors_f'] is None


def test_changed_original_delivery_refuses_even_with_resealed_envelope(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch)
    from household.outcome_origin import PreparedOutcomeOrigin
    value=args['origin'].to_dict();name=next(iter(value['receipts']));value['receipts'][name]['state']='{}'
    value['origin_sha256']=identity({key:item for key,item in value.items() if key!='origin_sha256'})
    with pytest.raises(ValueError):PreparedOutcomeOrigin(canonical(value))


def test_changed_score_refuses_even_when_outer_receipt_is_resealed(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);result=api().seal_outcomes(**args)
    result['output']['thermal']['1']['errors_f']['model']=0.
    result['receipt_sha256']=identity({key:value for key,value in result.items() if key!='receipt_sha256'})
    with pytest.raises(ValueError):api().replay_outcomes(result,plan_runtime_manifest=args['plan_runtime_manifest'],
        outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=args['thermal_runtime'])


def test_score_replay_never_reads_live_or_original_files(tmp_path,monkeypatch):
    import builtins,psycopg2
    from pathlib import Path
    args=inputs(tmp_path,monkeypatch);result=api().seal_outcomes(**args)
    def forbidden(*a,**k):pytest.fail('read inside pure chronological scoring')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert api().replay_outcomes(result,plan_runtime_manifest=args['plan_runtime_manifest'],outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=args['thermal_runtime'])==result


def test_daily_evidence_units_report_no_independence_or_causal_claim(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);mod=api();assert hasattr(mod,'summarize_outcomes'),'chronological summary missing'
    receipt=mod.seal_outcomes(**args)
    summary=mod.summarize_outcomes([receipt],plan_runtime_manifest=args['plan_runtime_manifest'],outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=args['thermal_runtime'])
    group=summary['by_horizon']['1']
    assert group['raw_pair_count']==1 and group['unique_daily_units']==1 and group['unique_observations']==1
    assert group['model']['mae_f']==receipt['output']['thermal']['1']['absolute_errors_f']['model']
    assert summary['cohort_policy']['independence_assessed'] is False
    assert summary['graduated'] is False and summary['causal_benefit_qualified'] is False
    assert summary['by_horizon']['6']['model']['mae_f'] is None


def test_reassessing_same_original_endpoint_cannot_inflate_evidence(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);mod=api();assert hasattr(mod,'summarize_outcomes'),'chronological summary missing'
    first=mod.seal_outcomes(**args);args['assessed_at']+=timedelta(seconds=1)
    args['outcome_sources']['1']['assessed_at']=args['assessed_at'].isoformat();second=mod.seal_outcomes(**args)
    assert first['receipt_sha256']!=second['receipt_sha256']
    with pytest.raises(ValueError):mod.summarize_outcomes([first,second],plan_runtime_manifest=args['plan_runtime_manifest'],outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=args['thermal_runtime'])


def test_summary_replays_source_scores_before_accepting_counts(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);mod=api();assert hasattr(mod,'summarize_outcomes'),'chronological summary missing'
    receipt=mod.seal_outcomes(**args);receipt['output']['thermal']['1']['actual_f']=0.
    receipt['receipt_sha256']=identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})
    with pytest.raises(ValueError):mod.summarize_outcomes([receipt],plan_runtime_manifest=args['plan_runtime_manifest'],outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=args['thermal_runtime'])


def test_native_null_barrier_keeps_mature_outcome_unavailable(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);args['outcome_sources']['1']['native_rows'][0][1]=None
    result=api().seal_outcomes(**args)
    assert result['output']['thermal']['1']['status']=='source_unavailable'
    assert result['output']['thermal']['1']['errors_f'] is None


def test_source_packet_before_maturity_is_refused(tmp_path,monkeypatch):
    args=inputs(tmp_path,monkeypatch);args['assessed_at']-=timedelta(microseconds=1)
    args['outcome_sources']['1']['assessed_at']=args['assessed_at'].isoformat()
    with pytest.raises(ValueError):api().seal_outcomes(**args)


def test_distinct_valid_artifacts_are_not_pooled_into_one_cohort(tmp_path,monkeypatch):
    first_path=tmp_path/'first';second_path=tmp_path/'second';first_path.mkdir();second_path.mkdir()
    first_args=inputs(first_path,monkeypatch);second_args=inputs(second_path,monkeypatch);mod=api()
    assert hasattr(mod,'summarize_outcomes'),'chronological summary missing'
    first=mod.seal_outcomes(**first_args);second=mod.seal_outcomes(**second_args)
    assert first['output']['model_identity']!=second['output']['model_identity']
    with pytest.raises(ValueError):mod.summarize_outcomes([first,second],plan_runtime_manifest=first_args['plan_runtime_manifest'],
        outcome_runtime_manifest=first_args['outcome_runtime_manifest'],thermal_runtime=first_args['thermal_runtime'])


def test_outcome_cli_refuses_special_or_nonprivate_files(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    script=Path(__file__).with_name('household_outcomes.py');assert script.exists(),'outcome CLI missing'
    fifo=tmp_path/'fifo';os.mkfifo(fifo,0o600);public=tmp_path/'public';public.write_text('{}');public.chmod(0o644)
    for path in (fifo,public):
        result=subprocess.run([sys.executable,str(script),'--receipt',str(path)],capture_output=True,text=True,timeout=5)
        assert result.returncode==1 and not result.stdout and 'Traceback' not in result.stderr


def test_outcome_cli_checks_complete_original_plan_dependency_closure():
    import importlib
    assert importlib.util.find_spec('household_outcomes') is not None,'outcome CLI missing'
    from household_outcomes import original_plan_runtime,outcome_runtime_manifest
    actual=outcome_runtime_manifest()
    with pytest.raises(ValueError):original_plan_runtime({'runtime_manifest':{'openhab/scripts/household/pipeline.py':actual['openhab/scripts/household/pipeline.py']}},actual=actual)
    from household_pipeline import pipeline_runtime_manifest
    original={'runtime_manifest':pipeline_runtime_manifest()}
    assert original_plan_runtime(original,actual=actual)==original['runtime_manifest']
    original['runtime_manifest']['openhab/scripts/household/pipeline.py']='f'*64
    with pytest.raises(ValueError):original_plan_runtime(original,actual=actual)


def test_outcome_cli_replays_owned_mathematical_fixture_with_original_runtime(tmp_path,monkeypatch):
    import os,sys,subprocess
    from pathlib import Path
    assert importlib.util.find_spec('household_outcomes') is not None,'outcome CLI missing'
    from household_outcomes import outcome_runtime_manifest
    from household_pipeline import pipeline_runtime_manifest
    from household.pipeline import seal_pipeline
    from household.capabilities import CapabilityRegistry
    args=inputs(tmp_path,monkeypatch);plan=args['plan_receipt'];source=plan['inputs']
    snap=HouseholdSnapshot(canonical({key:value for key,value in source['snapshot'].items() if key!='snapshot_id'}))
    registry=CapabilityRegistry(canonical({key:value for key,value in source['registry'].items() if key!='registry_id'}))
    from household.thermal_model import PreparedProjection
    runtime=pipeline_runtime_manifest();args['plan_runtime_manifest']=runtime;args['outcome_runtime_manifest']=outcome_runtime_manifest()
    args['plan_receipt']=seal_pipeline(snapshot=snap,registry=registry,energy_inputs=None,thermal_inputs=PreparedProjection(canonical(source['thermal_inputs'])),
        thermal_runtime=args['thermal_runtime'],coordination=source['coordination'],config=source['config'],now=instant(source['now']),runtime_manifest=runtime)
    receipt=api().seal_outcomes(**args);path=tmp_path/'score.json';path.write_bytes(canonical(receipt));path.chmod(0o600)
    # Execute the owned same-byte fixture interpreter with the parent's package
    # search paths; hosted group-writable interpreter metadata is not release proof.
    environment={**os.environ,'PYTHONPATH':os.pathsep.join(value for value in sys.path if value)}
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('household_outcomes.py')),'--receipt',str(path)],capture_output=True,text=True,timeout=20,env=environment)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt


@pytest.mark.parametrize('damage',['epoch','measurement','plan_snapshot'])
def test_resealed_origin_cannot_substitute_sensor_or_source_snapshot(tmp_path,monkeypatch,damage):
    args=inputs(tmp_path,monkeypatch);value=args['origin'].to_dict();prepared=value['prepared_thermal'];snap=prepared['snapshot']
    if damage=='epoch':
        phase='00000000-0000-0000-0000-000000000001'
        snap['domains']['thermal']['air_temperature']['evidence']['hardware_epoch']=phase
        from thermal_model.temperature_history import STREAMS,POLICY
        from weather_temperature_evidence import TemperaturePolicy,MODELS
        from weather_temperature_receiver import TemperatureCollector
        from weather_temperature_sources import build_temperature_source,replay_temperature_source
        stream,model,sensor_id=STREAMS['air'];policy=TemperaturePolicy(model,sensor_id,**POLICY)
        target=instant(args['outcome_sources']['1']['targets'][0]);observed=target-timedelta(seconds=60)
        collector=TemperatureCollector({stream:policy},sensor_epochs={stream:phase},clock=lambda:observed,process_id=lambda:1,monotonic=lambda:1000.)
        collector.observe({'model':model,'id':str(sensor_id),MODELS[model][1]:'75'})
        packet=build_temperature_source(rows=[(observed,json.dumps(collector.snapshot()))],targets=[target],assessed_at=args['assessed_at'],stream=stream,policy=policy,sensor_epoch=phase)
        assert replay_temperature_source(packet)[0][1]['sensorEpoch']==phase
        args['outcome_sources']={'1':packet}
    elif damage=='measurement':snap['domains']['thermal']['air_temperature']['value']+=1
    else:snap['code_revision']='b'*40
    snap['snapshot_id']=identity({key:item for key,item in snap.items() if key!='snapshot_id'})
    prepared['prepared_sha256']=identity({key:item for key,item in prepared.items() if key!='prepared_sha256'})
    value['origin_sha256']=identity({key:item for key,item in value.items() if key!='origin_sha256'})
    from household.outcome_origin import PreparedOutcomeOrigin
    with pytest.raises(ValueError):
        args['origin']=PreparedOutcomeOrigin(canonical(value))
        api().seal_outcomes(**args)
