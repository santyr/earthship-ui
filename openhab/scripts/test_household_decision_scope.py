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
