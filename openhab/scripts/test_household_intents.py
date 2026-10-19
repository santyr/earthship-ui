"""Shadow intent identity and provenance; translator is deliberately disabled."""
from datetime import timedelta
from dataclasses import FrozenInstanceError
from hashlib import sha256
import importlib,json
import pytest
from test_household_snapshot import build as snapshot
from local_measurement_test_support import NOW


def api():
    assert importlib.util.find_spec('household.intents') is not None,'typed household intents missing'
    return importlib.import_module('household.intents')


def document(snap,**changes):
    value=dict(schema='earthship-household-intent/v1',type='NO_ACTION',createdAt=NOW.isoformat(),
               expiresAt=(NOW+timedelta(seconds=120)).isoformat(),snapshotId=snap.snapshot_id,
               evidenceRefs=[],predictedEffects=dict(batteryKwh=None,socPct=None,thermalF=None,water=None,wearCost=None),
               confidence='unavailable',reasonCodes=['no_optional_action'],shadowOnly=True,parameters={})
    return {**value,**changes}


def test_intent_is_immutable_and_deterministically_bound_to_snapshot():
    m=api();snap=snapshot();first=m.build_intent(document(snap),snapshot=snap,now=NOW)
    assert first.to_dict()==m.build_intent(document(snap),snapshot=snap,now=NOW).to_dict()
    assert len(first.intent_id)==64
    parsed=m.parse_intent(json.dumps(first.to_dict()),snapshot=snap,now=NOW)
    assert parsed.intent_id==first.intent_id
    mutable=parsed.to_dict();mutable['predictedEffects']['batteryKwh']=123
    assert parsed.to_dict()==first.to_dict()
    with pytest.raises(FrozenInstanceError):parsed.content=b'changed'
    with pytest.raises(m.ContractRefused) as refused:m.intent_to_request(parsed)
    assert refused.value.reason_code=='planner_authority_disabled'


@pytest.mark.parametrize('damage',['unknown','active','expired','future','snapshot','unsupported','bad_effect','invented_no_action_effect','bad_reason','authority_flag','duplicate_ref'])
def test_invalid_intents_do_not_become_candidate_authority(damage):
    m=api();snap=snapshot();value=document(snap)
    if damage=='unknown':value['schema']='earthship-household-intent/v99'
    elif damage=='active':value['shadowOnly']=False
    elif damage=='expired':value['expiresAt']=NOW.isoformat()
    elif damage=='future':value['createdAt']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='snapshot':value['snapshotId']='f'*64
    elif damage=='unsupported':value['type']='DIRECT_PROVIDER_COMMAND'
    elif damage=='bad_effect':value['predictedEffects']['socPct']=True
    elif damage=='invented_no_action_effect':value['predictedEffects']['socPct']=1
    elif damage=='bad_reason':value['reasonCodes']=['made_up']
    elif damage=='authority_flag':value['enabled']=True
    else:value['evidenceRefs']=['a'*64,'a'*64]
    with pytest.raises(m.ContractRefused):m.build_intent(value,snapshot=snap,now=NOW)


def test_real_owned_shadow_action_requires_current_original_evidence():
    m=api();snap=snapshot();row=snap.to_dict()['domains']['energy']['battery_soc'];ref=row['evidence']['digest']
    value=document(snap,type='RUN_GREYWATER_CYCLE',evidenceRefs=[ref],confidence='low',reasonCodes=['hard_constraint'])
    intent=m.build_intent(value,snapshot=snap,now=NOW)
    assert intent.to_dict()['type']=='RUN_GREYWATER_CYCLE' and intent.to_dict()['shadowOnly'] is True
    with pytest.raises(m.ContractRefused):m.intent_to_request(intent)
    with pytest.raises(m.ContractRefused):m.build_intent(value,snapshot=snap,now=NOW+timedelta(seconds=100))
    with pytest.raises(m.ContractRefused):m.build_intent({**value,'evidenceRefs':['f'*64]},snapshot=snap,now=NOW)


def test_changed_effect_cannot_reuse_sealed_intent_identity():
    m=api();snap=snapshot();original=m.build_intent(document(snap),snapshot=snap,now=NOW).to_dict()
    original['expiresAt']=(NOW+timedelta(seconds=60)).isoformat()
    with pytest.raises(m.ContractRefused):m.parse_intent(json.dumps(original),snapshot=snap,now=NOW)


def test_shadow_lifetime_is_checked_without_calendar_overflow():
    from datetime import datetime,timezone
    m=api();snap=snapshot();near_limit=datetime(9999,12,31,23,59,tzinfo=timezone.utc)
    value=document(snap,createdAt=near_limit.isoformat(),expiresAt=(near_limit+timedelta(seconds=59)).isoformat())
    assert m.build_intent(value,snapshot=snap,now=near_limit).to_dict()['shadowOnly'] is True
