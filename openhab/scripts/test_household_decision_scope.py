"""Current scope excludes protected operations; immutable producers remain replayable."""
from test_household_pipeline import pipeline, config, energy_inputs
from test_household_planning import setup, context, candidate
from local_measurement_test_support import NOW
from household import pipeline as current, planning


def test_surplus_generates_no_greywater_or_uninspected_curtailment_macro():
    snap,registry=setup()
    result=current.seal_pipeline(snapshot=snap,registry=registry,energy_inputs=energy_inputs(),thermal_inputs=None,
        thermal_runtime=None,coordination=context(snap),config=config(),now=NOW,runtime_manifest={'household/pipeline.py':'a'*64})
    assert result['output']['candidate_intents']==[]
    assert result['output']['automatic_actuation'] is False


def test_injected_legacy_pump_and_broad_macro_cannot_be_selected():
    snap,registry=setup()
    for kind in ('RUN_GREYWATER_CYCLE','RUN_FEEDER_CYCLE','SET_NIGHT_LOAD_OVERRIDE'):
        if kind=='SET_NIGHT_LOAD_OVERRIDE':
            from test_household_intents import document
            from household.intents import build_intent
            item=build_intent(document(snap,type=kind,parameters={'command':'OFF'},evidenceRefs=[snap.to_dict()['domains']['energy']['battery_soc']['evidence']['digest']]),snapshot=snap,now=NOW)
        else:item=candidate(snap,kind)
        result=planning.plan(snapshot=snap,registry=registry,candidates=[item],coordination=context(snap),
            utilities={item.intent_id:100},now=NOW,reserve_soc=10.,horizon_hours=24)
        assert result['selected_intent_ids']==[]
        assert result['candidate_decisions'][0]['status']=='rejected'


def test_old_original_replays_using_its_original_producer():
    from household import legacy_pipeline
    snap,registry=setup()
    old=legacy_pipeline.seal_pipeline(snapshot=snap,registry=registry,energy_inputs=energy_inputs(),thermal_inputs=None,
        thermal_runtime=None,coordination=context(snap),config=config(),now=NOW,runtime_manifest={'household/pipeline.py':'a'*64})
    assert any(row['type']=='RUN_GREYWATER_CYCLE' for row in old['output']['candidate_intents'])
    assert current.replay_pipeline(old,runtime_manifest=old['runtime_manifest'],thermal_runtime=None)==old


def test_current_expanded_pipeline_and_nested_plan_cli_bind_source_shapes(tmp_path):
    from test_household_model_snapshot import source_at
    from household.model_snapshot import bind_model_snapshot
    from household.power_snapshot import compile_power_inputs
    from household_pipeline import pipeline_runtime_manifest
    from test_household_model_pipeline import run
    import test_household_model_pipeline as original_fixture
    import subprocess,sys,json,os
    from pathlib import Path
    from household.codec import canonical
    runtime=pipeline_runtime_manifest(expanded=True);original=source_at(NOW)['inputs']
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=runtime)
    snap=bind_model_snapshot(source_receipt=source,source_runtime_manifest=runtime,thermal_inputs=None,code_revision='e'*40)
    old=original_fixture.seal_pipeline
    try:
        original_fixture.seal_pipeline=current.seal_pipeline
        report=run(snap,runtime_manifest=runtime)
    finally:original_fixture.seal_pipeline=old
    assert report['schema']=='earthship-household-model-plan-receipt/v7'
    assert report['output']['plan_receipt']['schema']=='earthship-household-shadow-plan-receipt/v6'
    env={**os.environ,'PYTHONPATH':os.pathsep.join(p for p in sys.path if p)}
    for module,receipt in [('household_pipeline.py',report),('household_plan.py',report['output']['plan_receipt'])]:
        path=tmp_path/(module+'.json');path.write_bytes(canonical(receipt));path.chmod(0o600)
        result=subprocess.run([sys.executable,str(Path(__file__).with_name(module)),'--receipt',str(path)],capture_output=True,text=True,env=env,timeout=15)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)==receipt
