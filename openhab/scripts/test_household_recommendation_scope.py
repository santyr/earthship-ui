"""Current recommendations exclude manual greywater and coupled night overrides."""
import pytest
from household.codec import canonical
from household.control_contracts import ContractRefused
from household.intents import build_intent,parse_intent,intent_to_request
from test_household_pipeline import pipeline,config
from test_household_planning import setup,run,candidate
from local_measurement_test_support import NOW


def legacy(snap,kind,command=None):
    from test_household_intents import document
    ref=snap.to_dict()['domains']['energy']['battery_soc']['evidence']['digest']
    return build_intent(document(snap,type=kind,parameters={} if command is None else {'command':command},
        evidenceRefs=[ref],confidence='low',reasonCodes=['low_soc'],
        predictedEffects=dict(batteryKwh=0.,socPct=0.,thermalF=None,water=None,wearCost=0.)),snapshot=snap,now=NOW)


def test_low_soc_and_surplus_cannot_generate_retired_broad_or_manual_actions():
    out=pipeline()['output']
    assert out['projections']['energy']['output']['curtail']>0
    assert out['projections']['energy']['output']['trough_pred']<config()['low_trough_threshold_soc_pct']
    assert out['candidate_intents']==[]
    assert out['no_action_intent']['type']=='NO_ACTION'
    assert out['plan_receipt']['plan']['planner_version']=='bounded_exhaustive_v2'
    assert out['automatic_actuation'] is False


def test_greywater_specific_validation_is_not_a_generation_prerequisite(monkeypatch):
    import household.pipeline as api
    original=api._intent
    def checked(snapshot,now,kind,*args):
        if kind=='RUN_GREYWATER_CYCLE':raise ContractRefused('planner_authority_disabled')
        return original(snapshot,now,kind,*args)
    monkeypatch.setattr(api,'_intent',checked)
    out=pipeline()['output']
    assert out['candidate_generation']['reason'] is None
    assert out['candidate_generation']['status']=='generated_shadow_only'


@pytest.mark.parametrize('kind,command',[('RUN_GREYWATER_CYCLE',None),('SET_NIGHT_LOAD_OVERRIDE','OFF'),('SET_NIGHT_LOAD_OVERRIDE','ON')])
def test_all_pass_legacy_candidates_are_rejected_without_displacing_supported_devices(kind,command):
    snap,_=setup();old=legacy(snap,kind,command)
    device=candidate(snap,'SET_NIGHT_LOAD_DEVICE',delta=0.,device='dishwasher')
    result=run(candidates=[old,device],utilities=lambda rows:{old.intent_id:1e6,device.intent_id:1.})
    assert result['selected_intent_ids']==[device.intent_id]
    decision=next(row for row in result['candidate_decisions'] if row['intent_id']==old.intent_id)
    assert decision['status']=='rejected' and decision['reason']=='planner_authority_disabled'
    assert decision['hard_checks']==[dict(rule='automated_intent_scope',status='rejected',reason='planner_authority_disabled')]
    assert result['automatic_actuation'] is False
    # Retained typed/manual records remain readable; parsing grants no request path.
    assert parse_intent(canonical(old.to_dict()).decode(),snapshot=snap,now=NOW).to_dict()==old.to_dict()
    with pytest.raises(ContractRefused,match='planner_authority_disabled'):intent_to_request(old)


def test_current_qualification_report_contains_only_supported_device_family():
    from household_observation import _qualification_report
    snap,registry=setup()
    report=_qualification_report(dict(proposals=[],receipt_sha256='a'*64,snapshot_id=snap.snapshot_id,decision_at=NOW.isoformat()),registry.to_dict())
    assert report['schema']=='earthship-household-intent-qualification/v3'
    assert [row['intent_type'] for row in report['families']]==['SET_NIGHT_LOAD_DEVICE']
    assert report['release_authorized'] is False and report['automatic_actuation'] is False
