"""Original weather enriches one snapshot without physical action authority."""
import importlib
from pathlib import Path
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant,ContractRefused
from household.intents import build_intent,EFFECT_UNITS
from test_household_weather_context import make as weather
from test_household_model_snapshot import source_at
from test_household_model_pipeline import run as model_pipeline,RUNTIME


def api():return importlib.import_module('household.weather_snapshot')


def make(tmp_path,monkeypatch):
    context,prepared,capture=weather(tmp_path,monkeypatch);source=source_at(instant(prepared.to_dict()['issue']))
    snap=api().bind_weather_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],weather_context=context,code_revision='e'*40)
    return snap,context,prepared,capture


def test_original_weather_and_operator_context_enrich_same_native_clock(tmp_path,monkeypatch):
    snap,context,prepared,capture=make(tmp_path,monkeypatch);doc=snap.to_dict();model=prepared.to_dict()
    assert doc['schema']=='earthship-household-snapshot/v4'
    assert doc['as_of']==model['issue'] and doc['created_at']==model['snapshot']['created_at']
    assert doc['domains']['thermal']['mass_temperature']==model['snapshot']['domains']['thermal']['mass_temperature']
    assert doc['domains']['weather']['forecast_issue']['value']['issued_at']==capture['inputs']['forecast']['issued_at']
    assert doc['domains']['weather']['outdoor_trajectory']['value']==[{'at':r['at'],'temperature_f':r['outdoor_f']} for r in model['forcings']]
    assert doc['domains']['weather']['radiation_trajectory']['value']==[{'at':r['at'],'radiation_wm2':r['radiation_wm2']} for r in model['forcings']]
    assert doc['domains']['weather']['wind_speed']['value'] is None and doc['domains']['weather']['precipitation']['value'] is None
    assert doc['domains']['thermal']['ventilation_state']['value']['window'] is None
    assert doc['domains']['thermal']['ventilation_state']['value']['skylight'] is None
    assert doc['domains']['thermal']['shade_state']['value']['actuator_position'] is None
    assert doc['planner_authority']=='none'


def test_weather_metadata_cannot_authorize_physical_action_refs(tmp_path,monkeypatch):
    snap,_,_,_=make(tmp_path,monkeypatch);doc=snap.to_dict();at=instant(doc['created_at']);from datetime import timedelta
    body=dict(schema='earthship-household-intent/v1',type='RUN_GREYWATER_CYCLE',createdAt=at.isoformat(),expiresAt=(at+timedelta(seconds=120)).isoformat(),
        snapshotId=snap.snapshot_id,evidenceRefs=[doc['domains']['weather']['forecast_issue']['evidence']['digest']],predictedEffects={name:None for name in EFFECT_UNITS},
        confidence='unavailable',reasonCodes=['unqualified_effect'],shadowOnly=True,parameters={})
    with pytest.raises(ContractRefused) as error:build_intent(body,snapshot=snap,now=at)
    assert error.value.reason_code=='source_unavailable'


def test_weather_pipeline_replays_all_models_and_deduplicated_plan_context(tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    from household.planning import replay_plan
    from household.weather_context import project_weather
    snap,context,prepared,_=make(tmp_path,monkeypatch);result=model_pipeline(snap,prepared)
    assert result['schema']=='earthship-household-model-plan-receipt/v3'
    assert result['output']['projections']['weather']==project_weather(context)
    assert result['output']['candidate_intents']
    plan=result['output']['plan_receipt'];assert plan['schema']=='earthship-household-shadow-plan-receipt/v3'
    assert set(plan['inputs']['source_contexts'])=={snap.snapshot_id}
    assert plan['inputs']['validation_snapshots']=={}
    assert all(item['validation_snapshot_id']==snap.snapshot_id and 'validation_snapshot' not in item for item in plan['inputs']['candidates'])
    assert replay_plan(plan,runtime_manifest=RUNTIME)==plan
    assert replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])==result
    assert plan['plan']['selected_intent_ids']==[] and result['output']['automatic_actuation'] is False


def test_weather_replay_has_no_live_reads(tmp_path,monkeypatch):
    snap,_,prepared,_=make(tmp_path,monkeypatch);result=model_pipeline(snap,prepared)
    import builtins,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('read inside weather/model/plan replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    from household.pipeline import replay_pipeline
    assert replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])==result


def test_later_source_and_forged_generic_snapshot_are_refused(tmp_path,monkeypatch):
    from datetime import timedelta
    from household.snapshot import HouseholdSnapshot
    snap,context,prepared,_=make(tmp_path,monkeypatch)
    later=source_at(instant(prepared.to_dict()['issue'])+timedelta(seconds=1))
    with pytest.raises(ValueError):api().bind_weather_snapshot(source_receipt=later,source_runtime_manifest=later['runtime_manifest'],weather_context=context,code_revision='e'*40)
    with pytest.raises(ValueError):model_pipeline(HouseholdSnapshot(snap.content),prepared)
    doc=snap.to_dict();doc.pop('snapshot_id');doc['domains']['weather']['outdoor_trajectory']['value'][0]['temperature_f']+=1
    with pytest.raises(ValueError):api().WeatherSnapshot(canonical(doc),snap.original_source,snap.original_weather)


@pytest.mark.parametrize('damage',['source_context','weather_projection','validation_snapshot','unused_snapshot'])
def test_resealed_weather_receipt_cannot_change_original_or_derived_context(damage,tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    snap,_,prepared,_=make(tmp_path,monkeypatch);result=model_pipeline(snap,prepared)
    if damage=='source_context':result['inputs']['source_contexts'][snap.snapshot_id]['weather_inputs']['original_capture']['data']='invalid'
    elif damage=='weather_projection':result['output']['projections']['weather']['forcings'][0]['outdoor_f']+=1
    elif damage=='validation_snapshot':result['output']['plan_receipt']['inputs']['candidates'][0]['validation_snapshot_id']='f'*64
    else:result['output']['plan_receipt']['inputs']['validation_snapshots']['f'*64]=snap.to_dict()
    result['receipt_sha256']=identity({k:v for k,v in result.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])


def test_distinct_candidate_validation_context_is_preserved(tmp_path,monkeypatch):
    from household.planning import seal_plan,replay_plan
    from household.intents import parse_intent
    from test_household_planning import setup
    snap,_,prepared,_=make(tmp_path,monkeypatch);result=model_pipeline(snap,prepared);candidate=result['output']['candidate_intents'][0]
    intent=parse_intent(canonical(candidate).decode(),snapshot=snap,now=instant(result['inputs']['now']))
    # A different root must reject this candidate, but retain its actual
    # original validation snapshot so offline replay can prove that decision.
    other=api().bind_weather_snapshot(source_receipt=snap.source_receipt,source_runtime_manifest=snap.source_receipt['runtime_manifest'],weather_context=snap.weather,code_revision='f'*40)
    _,registry=setup();ctx={**result['inputs']['coordination'],'snapshotId':other.snapshot_id}
    plan=seal_plan(snapshot=other,registry=registry,candidates=[intent],coordination=ctx,utilities={intent.intent_id:1.},
        now=instant(result['inputs']['now']),reserve_soc=10.,horizon_hours=24,runtime_manifest=RUNTIME,model_refs=[],forecast_ref=None)
    assert set(plan['inputs']['validation_snapshots'])=={snap.snapshot_id}
    assert plan['plan']['selected_intent_ids']==[]
    assert replay_plan(plan,runtime_manifest=RUNTIME)==plan


def test_old_pipeline_versions_keep_original_structure():
    from test_household_pipeline import pipeline
    from test_household_model_pipeline import model_free
    assert pipeline()['schema']=='earthship-household-model-plan-receipt/v1'
    old=model_pipeline(model_free())
    assert old['schema']=='earthship-household-model-plan-receipt/v2'
    assert set(old['output']['projections'])=={'energy','thermal'}
    assert 'validation_snapshots' not in old['output']['plan_receipt']['inputs']


def test_operational_weather_source_closure_and_plan_restore(tmp_path,monkeypatch,capsys):
    import subprocess,sys,json,os
    from household_pipeline import pipeline_runtime_manifest,verify_source_closure
    from household.power_snapshot import compile_power_inputs
    from household_outcomes import original_plan_runtime,outcome_runtime_manifest
    from household.weather_snapshot import bind_weather_snapshot
    snap,context,prepared,_=make(tmp_path,monkeypatch);runtime=pipeline_runtime_manifest(expanded=True);original=snap.source_receipt['inputs']
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=runtime)
    snap=bind_weather_snapshot(source_receipt=source,source_runtime_manifest=runtime,weather_context=context,code_revision='e'*40)
    receipt=model_pipeline(snap,prepared,runtime_manifest=runtime)
    verify_source_closure(receipt,runtime)
    assert original_plan_runtime(receipt,actual=outcome_runtime_manifest())==runtime
    environment={**os.environ,'PYTHONPATH':os.pathsep.join(value for value in sys.path if value)}
    for name,record in [('household_pipeline.py',receipt),('household_plan.py',receipt['output']['plan_receipt'])]:
        path=tmp_path/(name+'.json');path.write_bytes(canonical(record));path.chmod(0o600)
        result=subprocess.run([sys.executable,str(Path(__file__).with_name(name)),'--receipt',str(path)],capture_output=True,text=True,timeout=45,env=environment)
        # Both CLIs verify the original weather runtime. This mathematical
        # fixture intentionally pins a synthetic model runtime, so a cold
        # process must reject it; its explicit in-process hook permits replay.
        assert result.returncode==1
        assert 'invalid or changed original context' in result.stderr
        module=importlib.import_module(name.removesuffix('.py'))
        assert module.main(['--receipt',str(path)])==0
        assert json.loads(capsys.readouterr().out)==record
    partial={'openhab/scripts/household/power_snapshot.py':runtime['openhab/scripts/household/power_snapshot.py']}
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=partial)
    snap=bind_weather_snapshot(source_receipt=source,source_runtime_manifest=partial,weather_context=context,code_revision='e'*40)
    incomplete=model_pipeline(snap,prepared,runtime_manifest=runtime)
    with pytest.raises(ValueError):original_plan_runtime(incomplete,actual=outcome_runtime_manifest())


def test_weather_stale_sources_and_translator_remain_fail_closed(tmp_path,monkeypatch):
    from datetime import timedelta
    from household.intents import parse_intent,intent_to_request
    snap,_,prepared,_=make(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of'])+timedelta(seconds=101)
    result=model_pipeline(snap,prepared,now=at)
    assert result['output']['candidate_intents']==[]
    assert result['output']['candidate_generation']['reason']=='source_stale'
    intent=parse_intent(canonical(result['output']['no_action_intent']).decode(),snapshot=snap,now=at)
    with pytest.raises(ContractRefused) as error:intent_to_request(intent)
    assert error.value.reason_code=='planner_authority_disabled'


def test_one_snapshot_reuses_immutable_weather_validation_during_planning(tmp_path,monkeypatch):
    snap,context,prepared,_=make(tmp_path,monkeypatch)
    from household import weather_context
    from household.weather_context import project_weather
    original=weather_context._original;validated=[]
    def validate(value):
        validated.append(value['weather_sha256'])
        return original(value)
    monkeypatch.setattr(weather_context,'_original',validate)
    expected=project_weather(context)
    result=model_pipeline(snap,prepared)
    assert result['inputs']['source_contexts'][snap.snapshot_id]['weather_inputs']==context.to_dict()
    assert project_weather(snap.weather)==expected
    detached=snap.weather.original_capture;detached['inputs']['forecast']['rows'][0]['windMph']+=1
    assert project_weather(snap.weather)==expected
    assert validated==[context.to_dict()['weather_sha256']]


def test_reused_weather_context_does_not_cache_source_freshness(tmp_path,monkeypatch):
    from datetime import timedelta
    snap,context,prepared,_=make(tmp_path,monkeypatch)
    before=model_pipeline(snap,prepared)
    stale=model_pipeline(snap,prepared,now=instant(snap.to_dict()['as_of'])+timedelta(seconds=101))
    assert snap.weather.to_dict()==context.to_dict()
    assert before['output']['candidate_generation']['status']=='generated_shadow_only'
    assert stale['output']['candidate_generation']['status']=='unavailable'
    assert stale['output']['candidate_generation']['reason']=='source_stale'
