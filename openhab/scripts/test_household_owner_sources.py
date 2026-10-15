"""Observed rule readiness cannot manufacture physical owner permissions."""
import importlib
import importlib.util
import json
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import pytest
from test_household_planning import setup, candidate, NOW
from household.codec import canonical,identity
from household.planning import plan,seal_plan,replay_plan


def api():
    assert importlib.util.find_spec('household.owner_sources') is not None, 'original owner source adapter missing'
    return importlib.import_module('household.owner_sources')


def source(status='IDLE',detail='NONE'):
    raw=json.dumps([{'uid':owner,'status':{'status':status,'statusDetail':detail},'name':'Original owner'}
                    for owner in ('hex_southoutlet_cycle','88bd9ec4de','hex_night_load_override')])
    return dict(schema='earthship-household-owner-source/v1',endpoint='/rules?summary=true',raw=raw,
        sha256=sha256(raw.encode()).hexdigest(),requested_at=(NOW-timedelta(seconds=2)).isoformat(),
        received_at=(NOW-timedelta(seconds=1)).isoformat())


def context(value=None):
    snap,registry=setup()
    return api().coordination_from_rules(source() if value is None else value,snapshot_id=snap.snapshot_id,
        registry=registry,horizon_hours=24,as_of=NOW)


def test_current_engine_readiness_only_never_proves_equipment_permission():
    ctx=context();snap,registry=setup();item=candidate(snap)
    result=plan(snapshot=snap,registry=registry,candidates=[item],coordination=ctx,utilities={item.intent_id:1e6},
        now=NOW,reserve_soc=10.,horizon_hours=24)
    checks={row['rule']:row for row in result['candidate_decisions'][0]['hard_checks']}
    assert checks['owner_available']['status']=='pass'
    for gate in ('owner_idle','cooldown_ready','curfew_allowed','operator_unlocked','manual_override_clear'):
        assert checks[gate]['status']=='unknown'
    assert ctx['baseline_soc_floor'] is None and result['selected_intent_ids']==[]
    assert result['automatic_actuation'] is False


@pytest.mark.parametrize('status,detail,expected',[('RUNNING','NONE',True),('UNINITIALIZED','DISABLED',False),
    ('UNINITIALIZED','HANDLER_INITIALIZING_ERROR',False),('FUTURE_STATE','NONE',None),('IDLE','DISABLED',None)])
def test_readiness_is_derived_only_from_known_consistent_engine_state(status,detail,expected):
    ctx=context(source(status,detail));entry=ctx['facts'].get('hex_southoutlet_cycle',{}).get('owner_available')
    assert (None if entry is None else json.loads(entry['raw'])['value']) is expected


@pytest.mark.parametrize('damage',['hash','future','reversed','duplicate','wrong_endpoint','oversize'])
def test_changed_or_ambiguous_originals_refuse(damage):
    value=source()
    if damage=='hash':value['sha256']='a'*64
    elif damage=='future':value['received_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='reversed':value['requested_at']=NOW.isoformat()
    elif damage=='wrong_endpoint':value['endpoint']='/rules/execute'
    else:
        rows=json.loads(value['raw']);rows.append(rows[0])
        value['raw']=json.dumps(rows) if damage=='duplicate' else ' '*65537
        value['sha256']=sha256(value['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):context(value)


def test_expired_observation_does_not_renew_readiness():
    value=source();value['requested_at']=(NOW-timedelta(seconds=122)).isoformat();value['received_at']=(NOW-timedelta(seconds=121)).isoformat()
    ctx=context(value);assert ctx['facts']=={}


def test_missing_source_is_explicitly_unknown():
    snap,registry=setup()
    ctx=api().coordination_from_rules(None,snapshot_id=snap.snapshot_id,registry=registry,horizon_hours=24,as_of=NOW)
    assert ctx['facts']=={} and ctx['owner_source'] is None


def test_plan_replay_rederives_original_readiness_and_rejects_forged_gate():
    snap,registry=setup();item=candidate(snap);ctx=context();runtime={'household/planning.py':'a'*64}
    receipt=seal_plan(snapshot=snap,registry=registry,candidates=[item],coordination=ctx,utilities={item.intent_id:1.},
        now=NOW,reserve_soc=10.,horizon_hours=24,runtime_manifest=runtime,model_refs=[],forecast_ref=None)
    assert replay_plan(receipt,runtime_manifest=runtime)==receipt
    bad=deepcopy(receipt);facts=bad['inputs']['coordination']['facts']['hex_southoutlet_cycle']
    facts['owner_idle']=facts['owner_available'];bad['receipt_sha256']=identity({k:v for k,v in bad.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_plan(bad,runtime_manifest=runtime)


def test_collector_retains_bounded_original_rule_summary(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch);original=source();calls=[]
    def read(*,remaining):
        assert remaining()>0;calls.append(1);return original['raw']
    collector.rule_reader=read
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['schema']=='earthship-household-cycle-sources/v5'
    assert result['owner_source']['raw']==original['raw'] and calls==[1]
    assert result['owner_source']['requested_at']==now.isoformat()
    assert result['owner_source']['received_at']==now.isoformat()


def test_real_cycle_binds_original_readiness_and_preserves_thermal(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household.control_contracts import instant
    from household_cycle import derive_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch);original=source();issue=instant(capture['issued_at'])
    original.update(requested_at=(issue-timedelta(seconds=3)).isoformat(),received_at=args['originals']['captured_at'])
    args['originals'].update(schema='earthship-household-cycle-sources/v3',daily_energy_source=None,owner_source=original)
    result=derive_cycle(**args)
    assert result['inputs']['coordination']['owner_source']==original
    assert set(result['inputs']['coordination']['facts'])=={'hex_southoutlet_cycle','88bd9ec4de','hex_night_load_override'}
    assert result['output']['projections']['thermal']['output']==capture['output']
    assert result['output']['automatic_actuation'] is False


@pytest.mark.parametrize('raw',['[], "injected":true','[{"uid":"x","uid":"y"}]'])
def test_original_summary_must_be_one_unambiguous_json_array(raw):
    value=source();value.update(raw=raw,sha256=sha256(raw.encode()).hexdigest())
    with pytest.raises(ValueError):context(value)


def test_decision_after_expiry_keeps_original_readiness_expired():
    snap,registry=setup();original=source();item=candidate(snap)
    original.update(requested_at=(NOW-timedelta(seconds=119)).isoformat(),received_at=(NOW-timedelta(seconds=118)).isoformat())
    ctx=context(original)
    result=plan(snapshot=snap,registry=registry,candidates=[item],coordination=ctx,utilities={item.intent_id:1.},
        now=NOW+timedelta(seconds=1),reserve_soc=10.,horizon_hours=24)
    checks={row['rule']:row for row in result['candidate_decisions'][0]['hard_checks']}
    assert checks['owner_available']['reason']=='source_stale'


@pytest.mark.parametrize('failure',['unavailable','invalid'])
def test_optional_owner_read_failure_preserves_other_originals(failure,tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch)
    def read(**kw):
        if failure=='unavailable':raise OSError('unavailable')
        return 'not json'
    collector.rule_reader=read
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['owner_source'] is None
    assert result['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000


def test_rule_reader_uses_only_bounded_summary_get(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,_=collector_fixture(tmp_path,monkeypatch);calls=[];raw=source()['raw'].encode()
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def geturl(self):return collector.base+'/rules?summary=true'
        def read(self,maximum):
            assert maximum==65537;return raw
    class Opener:
        def open(self,request,*,timeout):
            assert request.get_method()=='GET' and request.full_url==collector.base+'/rules?summary=true'
            assert 0<timeout<=2;calls.append(1);return Response()
    collector.opener=Opener()
    assert collector._rules_http(remaining=lambda:2.)==raw.decode()
    assert calls==[1]


@pytest.mark.parametrize('failure',['nested_json','truncated_http'])
def test_malformed_optional_rule_transport_never_discards_other_domains(failure,tmp_path,monkeypatch):
    from http.client import IncompleteRead
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch)
    def read(**kw):
        if failure=='truncated_http':raise IncompleteRead(b'[',10)
        return '['*16000+']'*16000
    collector.rule_reader=read
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['owner_source'] is None
    assert result['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000
