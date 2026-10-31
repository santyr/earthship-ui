"""Preserve current refusal and expiry contracts alongside original replay fixtures."""
from datetime import timedelta
from household import planning
from test_household_owner_policy import original,context as owner_context
from test_household_planning import setup,candidate,context,NOW


def test_current_policy_fact_expiry_is_not_renewed_by_original_replay():
    snap,_=setup();coordination=owner_context(original(evaluated=NOW-timedelta(seconds=119)))
    value,reason=planning._fact(coordination['facts']['hex_southoutlet_cycle']['curfew_allowed'],
        kind='curfew_allowed',owner='hex_southoutlet_cycle',snapshot_id=snap.snapshot_id,
        now=NOW+timedelta(seconds=1),horizon_hours=24)
    assert value is None and reason=='source_stale'


def test_current_planner_refuses_legacy_device_intents_even_with_positive_utility():
    snap,registry=setup()
    for kind in ('RUN_GREYWATER_CYCLE','RUN_FEEDER_CYCLE','SET_NIGHT_LOAD_DEVICE'):
        intent=candidate(snap,kind,device='dishwasher' if kind=='SET_NIGHT_LOAD_DEVICE' else None)
        result=planning.plan(snapshot=snap,registry=registry,candidates=[intent],coordination=context(snap),
            utilities={intent.intent_id:100},now=NOW,reserve_soc=10.,horizon_hours=24)
        assert result['selected_intent_ids']==[] and result['automatic_actuation'] is False
        assert result['candidate_decisions'][0]['status']=='rejected'
