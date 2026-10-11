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
