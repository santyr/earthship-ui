"""Display-only action details must come from fully replayed original intents."""
from datetime import timedelta
from household.codec import identity
from household_observation import observe_pipeline,materialize
from test_household_observation import policy_record,RUNTIME,NOW,materializer_fixture
import pytest,json


def test_v4_action_parameters_and_clocks_are_exact_replayed_original_values():
    record=policy_record()
    view=observe_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=NOW,include_action_details=True)
    assert view['schema']=='earthship-household-observation/v4'
    original={i['intentId']:i for i in record['output']['candidate_intents']}
    for p in view['proposals']:
        i=original[p['intent_id']]
        assert p['parameters']==i['parameters'] and p['created_at']==i['createdAt'] and p['expires_at']==i['expiresAt']
    night=next(p for p in view['proposals'] if p['type']=='SET_NIGHT_LOAD_OVERRIDE')
    assert night['parameters']=={'command':'OFF'} and not night['selected']
    assert view['automatic_actuation'] is False and view['qualification_report']['release_authorized'] is False


def test_legacy_observation_contract_remains_available_and_reverification_never_renews_actions():
    record=policy_record();legacy=observe_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=NOW)
    assert legacy['schema']=='earthship-household-observation/v3' and 'parameters' not in legacy['proposals'][0]
    early=observe_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=NOW,include_action_details=True)
    later=observe_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=NOW+timedelta(minutes=10),include_action_details=True)
    assert early['proposals']==later['proposals'] and early['valid_until']==later['valid_until']
    assert later['planner_mode']=='unavailable'


def test_tampered_action_cannot_survive_replay_even_if_outer_receipt_is_resealed():
    record=policy_record();next(i for i in record['output']['candidate_intents'] if i['type']=='SET_NIGHT_LOAD_OVERRIDE')['parameters']['command']='ON'
    record['receipt_sha256']=identity({k:v for k,v in record.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):observe_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=None,observed_at=NOW,include_action_details=True)


def test_materializer_publishes_v4_from_current_coordination_and_upgrades_known_v3(tmp_path):
    from household_pipeline import pipeline_runtime_manifest
    from household.codec import canonical
    source,target,_=materializer_fixture(tmp_path);record=policy_record(runtime_manifest=pipeline_runtime_manifest())
    source.write_bytes(canonical(record));legacy=observe_pipeline(record,runtime_manifest=pipeline_runtime_manifest(),thermal_runtime=None,observed_at=NOW)
    target.write_bytes(canonical(legacy));target.chmod(0o600)
    result=materialize(source,target,clock=lambda:NOW)
    assert result['status']=='observation_written' and json.loads(target.read_bytes())['schema']=='earthship-household-observation/v4'
