"""One replayed plan informs qualification; absent release evidence stays absent."""
from datetime import timedelta
from copy import deepcopy
import json
import pytest
from test_household_observation import observe,policy_record,NOW

GATES=('deterministic_replay','evidence_contracts','hard_constraints','unknown_fails_closed',
       'independent_windows','input_stability','model_error_uncertainty','baseline_comparison',
       'reason_codes','no_planner_rollback','no_provider_write_path','owner_safety_recheck')


def test_all_registered_intent_families_have_all_twelve_unqualified_release_gates():
    record=policy_record();before=deepcopy(record);view=observe(record)
    assert view['schema']=='earthship-household-observation/v3'
    report=view['qualification_report']
    assert report['schema']=='earthship-household-intent-qualification/v1'
    assert report['scope']=='original_plan_evidence' and report['status']=='not_qualified'
    assert report['receipt_sha256']==record['receipt_sha256']
    assert report['snapshot_id']==view['snapshot_id'] and report['decision_at']==view['decision_at']
    assert report['release_authorized'] is False and report['automatic_actuation'] is False
    assert {r['intent_type'] for r in report['families']}=={'RUN_GREYWATER_CYCLE','RUN_FEEDER_CYCLE','SET_NIGHT_LOAD_OVERRIDE','SET_NIGHT_LOAD_DEVICE'}
    for family in report['families']:
        assert tuple(g['id'] for g in family['gates'])==GATES
        assert family['status']=='not_qualified' and family['release_authorized'] is False
        gates={g['id']:g for g in family['gates']}
        assert gates['deterministic_replay']['evidence_status']=='observed'
        for key in GATES[4:]:assert gates[key]['evidence_status']=='unavailable'
    assert record==before


def test_actual_unknown_checks_are_observed_only_for_their_own_proposal_family():
    view=observe(policy_record());families={r['intent_type']:r for r in view['qualification_report']['families']}
    grey=families['RUN_GREYWATER_CYCLE'];feeder=families['RUN_FEEDER_CYCLE']
    assert grey['proposal_count']==1 and feeder['proposal_count']==0
    assert grey['gates'][2]['evidence_status']=='observed'
    assert grey['gates'][3]['evidence_status']=='observed'
    assert feeder['gates'][2]['evidence_status']=='unavailable'
    assert feeder['gates'][3]['evidence_status']=='unavailable'
    assert grey['gates'][7]['reason']=='policy_performance_not_qualified'


def test_no_proposals_and_later_verification_never_create_qualification():
    record=policy_record(energy_inputs=None);a=observe(record);b=observe(record,at=NOW+timedelta(hours=1))
    assert a['qualification_report']==b['qualification_report']
    assert all(row['proposal_count']==0 for row in a['qualification_report']['families'])
    assert all(row['gates'][2]['evidence_status']=='unavailable' for row in a['qualification_report']['families'])
    assert a['valid_until']==b['valid_until'] and b['planner_mode']=='unavailable'


def test_assessment_is_after_complete_replay_not_a_caller_claim():
    record=policy_record();record['output']['action_effects_qualified']=True
    from household.codec import identity
    record['receipt_sha256']=identity({k:v for k,v in record.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):observe(record)


def test_assessment_adds_no_transport_or_translation_calls(monkeypatch):
    record=policy_record()
    import household.intents as intents
    def forbidden(*a,**kw):pytest.fail('qualification tried request translation')
    monkeypatch.setattr(intents,'intent_to_request',forbidden)
    report=observe(record)['qualification_report']
    assert report['status']=='not_qualified' and '/home/' not in json.dumps(report)


def test_materializer_upgrades_v2_cache_without_changing_issued_original(tmp_path):
    from household.codec import canonical
    from household_pipeline import pipeline_runtime_manifest
    import household_observation as api
    root=tmp_path/'private';root.mkdir(mode=0o700)
    record=policy_record(runtime_manifest=pipeline_runtime_manifest());source=root/'receipt.json';target=root/'observation.json'
    source.write_bytes(canonical(record));source.chmod(0o600);before=source.read_bytes()
    api.materialize(source,target,clock=lambda:NOW)
    old=json.loads(target.read_bytes());old.pop('qualification_report');old['schema']='earthship-household-observation/v2'
    for proposal in old['proposals']:
        for key in ('parameters','created_at','expires_at'):proposal.pop(key)
    target.write_bytes(canonical(old))
    api.materialize(source,target,clock=lambda:NOW+timedelta(minutes=1))
    assert json.loads(target.read_bytes())['schema']=='earthship-household-observation/v4'
    assert source.read_bytes()==before and target.stat().st_nlink==1
