"""One frozen clock retains original weather points through models and outcomes."""
import importlib,json
from datetime import timedelta
from pathlib import Path
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_energy_source_pipeline import make as energy_snapshot
from test_household_measured_weather import sources,set_raw
from test_household_model_pipeline import run as run_pipeline,RUNTIME


def api():return importlib.import_module('household.measured_weather_snapshot')


def make(tmp_path,monkeypatch,*,change=None):
    from household.measured_weather import prepare_measured_weather
    base,_,prepared,capture=energy_snapshot(tmp_path,monkeypatch);at=instant(prepared.to_dict()['issue']);rows=sources(at)
    if change:change(rows)
    measured=prepare_measured_weather(sources=rows,as_of=at,created_at=at+timedelta(seconds=1))
    snap=api().bind_measured_weather_snapshot(source_receipt=base.source_receipt,source_runtime_manifest=base.source_receipt['runtime_manifest'],
        weather_context=base.weather,energy_configuration=base.energy_configuration,measured_weather=measured,code_revision='e'*40)
    return snap,measured,prepared,capture,base


def test_current_points_extend_original_clock_without_changing_models(tmp_path,monkeypatch):
    snap,measured,prepared,capture,base=make(tmp_path,monkeypatch);doc=snap.to_dict()
    assert doc['schema']=='earthship-household-snapshot/v6' and doc['base_energy_source_snapshot_id']==base.snapshot_id
    assert doc['as_of']==prepared.to_dict()['issue']
    assert doc['domains']['energy']==base.to_dict()['domains']['energy']
    assert doc['domains']['thermal']==base.to_dict()['domains']['thermal']
    assert doc['domains']['weather']['solar_radiation_proxy_wm2']['value']==100
    assert doc['domains']['weather']['rain_counter_in']['value']==12.3
    assert doc['domains']['thermal']['solar_radiation_wm2']['value'] is None
    assert doc['completeness']['radiation_proxy_display'] is True
    assert doc['completeness']['rain_counter_display'] is True
    result=run_pipeline(snap,prepared)
    assert result['schema']=='earthship-household-model-plan-receipt/v5'
    assert result['output']['projections']['thermal']['output']==capture['output']
    assert result['output']['projections']['energy']['collection_binding']['configuration_binding']['nominal_bank_kwh']==20.48
    assert result['output']['projections']['measured_weather']['measured_weather_sha256']==measured.to_dict()['measured_weather_sha256']
    assert result['output']['plan_receipt']['schema']=='earthship-household-shadow-plan-receipt/v5'
    assert result['output']['automatic_actuation'] is False


def test_measured_pipeline_replay_has_no_reads(tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    snap,_,prepared,_,_=make(tmp_path,monkeypatch);result=run_pipeline(snap,prepared)
    import builtins
    def forbidden(*a,**k):pytest.fail('I/O in measured-weather replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])==result


def test_missing_point_does_not_suppress_bank_or_other_weather(tmp_path,monkeypatch):
    snap,_,_,_,_=make(tmp_path,monkeypatch,change=lambda rows:set_raw(rows['radiation'],None));doc=snap.to_dict()
    assert doc['domains']['energy']['nominal_bank_kwh']['value']==20.48
    assert doc['domains']['weather']['rain_counter_in']['value']==12.3
    assert doc['completeness']['radiation_proxy_display'] is False and doc['completeness']['rain_counter_display'] is True


@pytest.mark.parametrize('version',[5,6])
def test_genuinely_distinct_candidate_retains_its_own_original_context(version,tmp_path,monkeypatch):
    from household.planning import seal_plan,replay_plan
    from household.intents import parse_intent
    from test_household_planning import setup
    if version==5:
        from household.energy_source_snapshot import bind_energy_source_snapshot
        from test_household_model_snapshot import source_at
        root,_,prepared,_=energy_snapshot(tmp_path,monkeypatch);source=source_at(instant(prepared.to_dict()['issue'])-timedelta(seconds=1))
        other=bind_energy_source_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],weather_context=root.weather,
            energy_configuration=root.energy_configuration,code_revision='e'*40)
        assert other.source_receipt!=root.source_receipt
    else:
        from household.measured_weather import prepare_measured_weather
        root,_,prepared,_,_=make(tmp_path,monkeypatch);rows=sources(instant(prepared.to_dict()['issue']))
        native=json.loads(rows['rain']['raw']);native['record']['totalRainIn']=12.4;native['packetCount']=2
        set_raw(rows['rain'],json.dumps(native));measured=prepare_measured_weather(sources=rows,as_of=instant(prepared.to_dict()['issue']),created_at=instant(prepared.to_dict()['issue'])+timedelta(seconds=1))
        other=api().bind_measured_weather_snapshot(source_receipt=root.source_receipt,source_runtime_manifest=root.source_receipt['runtime_manifest'],
            weather_context=root.weather,energy_configuration=root.energy_configuration,measured_weather=measured,code_revision='e'*40)
        assert other.measured_weather.to_dict()!=root.measured_weather.to_dict()
    generated=run_pipeline(other,prepared);now=instant(generated['inputs']['now'])
    from household.pipeline import _intent
    ref=other.to_dict()['domains']['energy']['battery_soc']['evidence']['digest']
    intent=_intent(other,now,'SET_NIGHT_LOAD_DEVICE',{'device':'dishwasher','command':'OFF'},[ref],'low_soc')
    _,registry=setup();coordination={**generated['inputs']['coordination'],'snapshotId':root.snapshot_id}
    plan=seal_plan(snapshot=root,registry=registry,candidates=[intent],coordination=coordination,utilities={intent.intent_id:1.},
        now=now,reserve_soc=10.,horizon_hours=24,runtime_manifest=RUNTIME,model_refs=[],forecast_ref=None)
    assert root.snapshot_id!=other.snapshot_id
    assert set(plan['inputs']['validation_snapshots'])=={other.snapshot_id}
    assert set(plan['inputs']['source_contexts'])=={root.snapshot_id,other.snapshot_id}
    assert plan['plan']['selected_intent_ids']==[]
    assert replay_plan(plan,runtime_manifest=RUNTIME)==plan


@pytest.mark.parametrize('version',[5,6])
def test_actual_enclosing_outcome_replays_full_source_context(version,tmp_path,monkeypatch):
    from household.outcomes import seal_outcomes,replay_outcomes
    from household.outcome_origin import prepare_native_outcome_origin
    from native_thermal_forecast import publication
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
    if version==5:snap,_,prepared,capture=energy_snapshot(tmp_path,monkeypatch)
    else:snap,_,prepared,capture,_=make(tmp_path,monkeypatch)
    issue=instant(prepared.to_dict()['issue']);plan=run_pipeline(snap,prepared)
    receipts={name:dict(item=name,time=int((issue+timedelta(seconds=3+i)).timestamp()*1000),state=json.dumps(body))
        for i,(name,body) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))))}
    origin=prepare_native_outcome_origin(capture,receipts,code_revision='a'*40,runtime=capture['candidate']['runtime'],expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    arguments=dict(plan_receipt=plan,origin=origin,outcome_sources={},assessed_at=issue+timedelta(hours=1,minutes=5),
        plan_runtime_manifest=RUNTIME,outcome_runtime_manifest={'household/outcomes.py':'b'*64},thermal_runtime=prepared.to_dict()['executing_runtime'])
    result=seal_outcomes(**arguments)
    assert result['inputs']['plan_receipt']==plan and result['output']['causal_benefit_qualified'] is False
    assert replay_outcomes(result,plan_runtime_manifest=RUNTIME,outcome_runtime_manifest=arguments['outcome_runtime_manifest'],thermal_runtime=arguments['thermal_runtime'])==result


def test_operational_measured_source_closure_is_complete(tmp_path,monkeypatch,capsys):
    import subprocess,sys,os
    from household_pipeline import pipeline_runtime_manifest,verify_source_closure,MEASURED_VALIDATORS
    from household.power_snapshot import compile_power_inputs
    from household_outcomes import outcome_runtime_manifest,original_plan_runtime
    snap,measured,prepared,_,_=make(tmp_path,monkeypatch);runtime=pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    original=snap.source_receipt['inputs'];source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=runtime)
    snap=api().bind_measured_weather_snapshot(source_receipt=source,source_runtime_manifest=runtime,weather_context=snap.weather,
        energy_configuration=snap.energy_configuration,measured_weather=measured,code_revision='e'*40)
    result=run_pipeline(snap,prepared,runtime_manifest=runtime);verify_source_closure(result,runtime)
    assert original_plan_runtime(result,actual=outcome_runtime_manifest())==runtime
    for name in MEASURED_VALIDATORS:
        key='openhab/scripts/'+name;assert key in runtime
        with pytest.raises(ValueError):verify_source_closure(result,{k:v for k,v in runtime.items() if k!=key})
    environment={**os.environ,'PYTHONPATH':os.pathsep.join(value for value in sys.path if value)}
    for name,record in [('household_pipeline.py',result),('household_plan.py',result['output']['plan_receipt'])]:
        path=tmp_path/(name+'.json');path.write_bytes(canonical(record));path.chmod(0o600)
        response=subprocess.run([sys.executable,str(Path(__file__).with_name(name)),'--receipt',str(path)],capture_output=True,text=True,timeout=60,env=environment)
        # Synthetic native model runtimes require the explicit in-process
        # fixture hook. A cold process must enforce the actual runtime identity.
        assert response.returncode==1
        assert 'invalid or changed original context' in response.stderr
        module=importlib.import_module(name.removesuffix('.py'))
        assert module.main(['--receipt',str(path)])==0
        assert json.loads(capsys.readouterr().out)==record


@pytest.mark.parametrize('damage',['derived_value','original_source','context_digest'])
def test_resealed_outer_receipt_cannot_replace_measured_originals(damage,tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    snap,_,prepared,_,_=make(tmp_path,monkeypatch);result=run_pipeline(snap,prepared)
    if damage=='derived_value':result['inputs']['snapshot']['domains']['weather']['light_lux']['value']+=1
    else:
        context=result['inputs']['source_contexts'][snap.snapshot_id]['measured_weather']
        if damage=='original_source':context['sources']['rain']['raw']+=' '
        else:context['measured_weather_sha256']='f'*64
    result['receipt_sha256']=identity({k:v for k,v in result.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=prepared.to_dict()['executing_runtime'])


def test_generic_v6_cannot_bypass_verified_type(tmp_path,monkeypatch):
    from household.snapshot import HouseholdSnapshot
    snap,_,prepared,_,_=make(tmp_path,monkeypatch)
    fake=HouseholdSnapshot(snap.content)
    with pytest.raises(ValueError):run_pipeline(fake,prepared)


def test_original_measured_reference_cannot_outlive_receiver_deadline(tmp_path,monkeypatch):
    from household.intents import build_intent,EFFECT_UNITS
    from household.control_contracts import ContractRefused
    snap,_,prepared,_,_=make(tmp_path,monkeypatch);at=instant(prepared.to_dict()['issue'])+timedelta(seconds=118)
    ref=snap.to_dict()['domains']['weather']['solar_radiation_proxy_wm2']['evidence']
    body=dict(schema='earthship-household-intent/v1',type='RUN_GREYWATER_CYCLE',createdAt=at.isoformat(),
        expiresAt=(at+timedelta(seconds=120)).isoformat(),snapshotId=snap.snapshot_id,evidenceRefs=[ref['digest']],
        predictedEffects={key:None for key in EFFECT_UNITS},confidence='unavailable',reasonCodes=['unqualified_effect'],shadowOnly=True,parameters={})
    with pytest.raises(ContractRefused) as error:build_intent(body,snapshot=snap,now=at)
    assert error.value.reason_code=='source_stale'


def test_missing_original_collector_module_refuses_full_source_closure(tmp_path,monkeypatch):
    from household_pipeline import pipeline_runtime_manifest,verify_source_closure
    from household.power_snapshot import compile_power_inputs
    snap,measured,prepared,_,_=make(tmp_path,monkeypatch)
    complete=pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    partial={name:sha for name,sha in complete.items() if name!='openhab/scripts/household/measured_weather_capture.py'}
    original=snap.source_receipt['inputs'];source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=partial)
    snap=api().bind_measured_weather_snapshot(source_receipt=source,source_runtime_manifest=partial,weather_context=snap.weather,
        energy_configuration=snap.energy_configuration,measured_weather=measured,code_revision='e'*40)
    result=run_pipeline(snap,prepared,runtime_manifest=partial)
    with pytest.raises(ValueError):verify_source_closure(result,complete)
