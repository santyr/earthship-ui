"""Pure v2 contracts; no owner migration, network or physical writes."""
from datetime import datetime,timedelta,timezone
from dataclasses import FrozenInstanceError
import importlib,json
from pathlib import Path
import re
import pytest

NOW=datetime(2026,10,11,12,tzinfo=timezone.utc)


def api():
    assert importlib.util.find_spec('household.control_contracts') is not None,'common household v2 contract missing'
    return importlib.import_module('household.control_contracts')


def request(**changes):
    return dict(schema='earthship-control-request/v2',requestId='req-example-01',intentId=None,
                intentType='RUN_GREYWATER_CYCLE',source='ui',requestedAt=NOW.isoformat(),
                expiresAt=(NOW+timedelta(seconds=60)).isoformat(),snapshotId=None,
                plannerVersion=None,parameters={},**changes) if not changes else {**request(),**changes}


@pytest.mark.parametrize('source',['ui','schedule','planner','operator','recovery'])
def test_all_sources_share_same_bounds_and_do_not_authorize_action(source):
    value=request(source=source)
    if source=='planner':value.update(intentId='a'*64,snapshotId='b'*64,plannerVersion='shadow-v1')
    parsed=api().parse_request(json.dumps(value),now=NOW)
    assert parsed.to_dict()==value and not hasattr(parsed,'send')
    returned=parsed.to_dict();returned['parameters']['command']='OFF'
    assert parsed.to_dict()==value
    with pytest.raises(FrozenInstanceError):parsed.content=b'altered'
    with pytest.raises(api().ContractRefused):api().parse_request(json.dumps(value),now=NOW+timedelta(seconds=60))


@pytest.mark.parametrize('damage',['unknown_schema','missing_expiry','future','expired','stale','long_lifetime','planner_missing','unknown_parameter','wrong_type','extra','oversized','duplicate'])
def test_invalid_request_is_refused_with_stable_reason(damage):
    m=api();value=request();now=NOW
    if damage=='unknown_schema':value['schema']='earthship-control-request/v99'
    elif damage=='missing_expiry':del value['expiresAt']
    elif damage=='future':now-=timedelta(seconds=1)
    elif damage=='expired':now+=timedelta(seconds=60)
    elif damage=='stale':now+=timedelta(seconds=121);value['expiresAt']=(NOW+timedelta(minutes=10)).isoformat()
    elif damage=='long_lifetime':value['expiresAt']=(NOW+timedelta(seconds=121)).isoformat()
    elif damage=='planner_missing':value['source']='planner'
    elif damage=='unknown_parameter':value['parameters']={'actuator':'SouthOutlet_Outlet2_Switch'}
    elif damage=='wrong_type':value['parameters']=[]
    elif damage=='extra':value['authorization']='must-not-appear-in-errors'
    elif damage=='oversized':value['requestId']='x'*5000
    raw=json.dumps(value)
    if damage=='duplicate':raw=raw[:-1]+',"source":"planner"}'
    with pytest.raises(m.ContractRefused) as refused:m.parse_request(raw,now=now)
    assert refused.value.reason_code in m.REASON_CODES
    assert 'must-not-appear' not in str(refused.value)


def test_owner_hard_max_overrides_longer_expiry():
    m=api();value=request(expiresAt=(NOW+timedelta(seconds=120)).isoformat())
    with pytest.raises(m.ContractRefused) as refused:m.parse_request(json.dumps(value),now=NOW+timedelta(seconds=31),owner_max_age_seconds=30)
    assert refused.value.reason_code=='request_stale'
    for age in (True,0,121):
        with pytest.raises(ValueError):m.parse_request(json.dumps(request()),now=NOW,owner_max_age_seconds=age)


@pytest.mark.parametrize('kind,parameters',[('RUN_FEEDER_CYCLE',{}),('SET_NIGHT_LOAD_OVERRIDE',{'command':'OFF'}),('SET_NIGHT_LOAD_DEVICE',{'device':'goat-cam','command':'ON'})])
def test_supported_parameters_follow_existing_owned_contracts(kind,parameters):
    m=api();value=request(intentType=kind,parameters=parameters)
    assert m.parse_request(json.dumps(value),now=NOW).to_dict()==value
    if parameters:
        parameters={**parameters,'command':'TOGGLE'}
        with pytest.raises(m.ContractRefused):m.parse_request(json.dumps(request(intentType=kind,parameters=parameters)),now=NOW)


def result(requested,status='accepted',reason='accepted',**changes):
    req=requested.to_dict()
    return dict(schema='earthship-control-result/v2',requestId=req['requestId'],intentId=req['intentId'],
                status=status,reasonCode=reason,ownerVersion='greywater-owner-v2',at=NOW.isoformat(),snapshotId=req['snapshotId'])|changes


def test_results_are_exactly_correlated_and_acceptance_does_not_mean_completion():
    m=api();req=m.parse_request(json.dumps(request()),now=NOW)
    accepted=m.parse_result(json.dumps(result(req)),request=req,now=NOW,expected_owner_version='greywater-owner-v2')
    assert not accepted.owner_reports_completion
    completed=m.parse_result(json.dumps(result(req,'completed','completed',at=(NOW+timedelta(minutes=20)).isoformat())),request=req,now=NOW+timedelta(minutes=20),expected_owner_version='greywater-owner-v2')
    assert completed.owner_reports_completion
    assert m.validate_result_sequence([accepted,completed],request=req)=='completed'
    with pytest.raises(m.ContractRefused):m.validate_result_sequence([completed],request=req)
    for key,value in [('requestId','different-id-123'),('snapshotId','c'*64),('intentId','d'*64),('status','complete'),('reasonCode','unregistered'),('ownerVersion','wrong-owner')]:
        with pytest.raises(m.ContractRefused):m.parse_result(json.dumps(result(req,**{key:value})),request=req,now=NOW,expected_owner_version='greywater-owner-v2')
    assert m.legacy_result_status('complete')=='completed'
    assert m.legacy_result_status('accepted')=='accepted'


def test_age_default_matches_source_owned_limits():
    m=api();root=Path(__file__).resolve().parents[2]
    for name in ['feeder-owner.js','southoutlet-cycle.js','night-load-owner.js']:
        source=(root/'openhab/rules'/name).read_text()
        assert re.search(r'const MAX_REQUEST_AGE_MS = 2 \* 60 \* 1000;',source)
    assert m.MAX_OWNER_AGE_SECONDS==120


@pytest.mark.parametrize('key,value',[('source',[]),('source',{}),('intentType',[]),('intentType',{})])
def test_malformed_labels_fail_with_catalogued_refusal(key,value):
    m=api()
    with pytest.raises(m.ContractRefused):m.parse_request(json.dumps(request(**{key:value})),now=NOW)


@pytest.mark.parametrize('key,value',[('status',[]),('reasonCode',{})])
def test_malformed_result_labels_fail_with_catalogued_refusal(key,value):
    m=api();req=m.parse_request(json.dumps(request()),now=NOW)
    with pytest.raises(m.ContractRefused):m.parse_result(json.dumps(result(req,**{key:value})),request=req,now=NOW,expected_owner_version='greywater-owner-v2')


def test_non_utf8_request_is_refused_without_encoding_exception():
    m=api()
    with pytest.raises(m.ContractRefused):m.parse_request('\ud800',now=NOW)


def test_reported_start_cannot_follow_request_expiry_but_completion_can():
    m=api();req=m.parse_request(json.dumps(request()),now=NOW)
    with pytest.raises(m.ContractRefused) as refused:
        m.parse_result(json.dumps(result(req,'running','running',at=(NOW+timedelta(seconds=60)).isoformat())),request=req,now=NOW+timedelta(seconds=60),expected_owner_version='greywater-owner-v2')
    assert refused.value.reason_code=='request_expired'


def test_calendar_limit_uses_duration_without_timestamp_overflow():
    m=api();near_limit=datetime(9999,12,31,23,59,tzinfo=timezone.utc)
    value=request(requestedAt=near_limit.isoformat(),expiresAt=(near_limit+timedelta(seconds=59)).isoformat())
    assert m.parse_request(json.dumps(value),now=near_limit).to_dict()==value
