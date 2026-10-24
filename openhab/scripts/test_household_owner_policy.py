"""Original owner decisions can block shadow proposals, never grant permission."""
from pathlib import Path
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import importlib, json
import pytest
from household.codec import canonical,loads,identity
from test_household_planning import setup,candidate,NOW
from test_household_owner_sources import source as readiness

ROOT=Path(__file__).resolve().parents[2]

def api():return importlib.import_module('household.owner_policy')

def original(reason='after_dark',evaluated=None,now=NOW):
    script=(ROOT/'openhab/rules/southoutlet-cycle-installed.js').read_text()
    rule=canonical(dict(uid='hex_southoutlet_cycle',configuration={},conditions=[],triggers=[],
        actions=[dict(type='script.ScriptAction',configuration=dict(type='application/javascript',script=script))])).decode()
    evaluated=evaluated or now-timedelta(seconds=5)
    conditional=reason in ('cooldown_wait','cooldown_initialized','cycle_active','cycle_started','cycle_completed')
    status=f'reason={reason},scheduleVersion=1,evaluatedAt={evaluated.isoformat()},scheduling='+('conditional' if conditional else 'blocked')
    if conditional:status+=f',nextEligibleAt={(evaluated+timedelta(minutes=30)).isoformat()},nextPump=south'
    def row(endpoint,raw,seconds):return dict(endpoint=endpoint,raw=raw,sha256=sha256(raw.encode()).hexdigest(),requested_at=(now-timedelta(seconds=seconds)).isoformat(),received_at=(now-timedelta(seconds=seconds)).isoformat())
    return dict(schema='earthship-greywater-policy-source/v1',rule_before=row('/rules/hex_southoutlet_cycle',rule,3),
        status=row('/items/SouthOutlet_AutoStatus/state',status,2),rule_after=row('/rules/hex_southoutlet_cycle',rule,1))

def context(value=None):
    from household.owner_sources import coordination_from_policy
    snap,registry=setup()
    return coordination_from_policy(readiness(),original() if value is None else value,snapshot_id=snap.snapshot_id,
        registry=registry,horizon_hours=24,as_of=NOW)

@pytest.mark.parametrize('reason,gate',[('after_dark','curfew_allowed'),('cooldown_wait','cooldown_ready'),
    ('cooldown_initialized','cooldown_ready'),('cycle_active','owner_idle'),('cycle_started','owner_idle'),('busy','owner_idle')])
def test_explicit_current_policy_blockers_become_negative_facts(reason,gate):
    ctx=context(original(reason));entry=ctx['facts']['hex_southoutlet_cycle'][gate]
    assert loads(entry['raw'])['value'] is False
    assert ctx['policy_observations']['hex_southoutlet_cycle']['reason']==reason
    assert ctx['baseline_soc_floor'] is None
    assert all(loads(v['raw'])['value'] is False for k,v in ctx['facts']['hex_southoutlet_cycle'].items() if k!='owner_available')

def test_current_after_dark_reason_survives_missing_other_permissions_and_replay():
    from household.planning import plan,seal_plan,replay_plan
    snap,registry=setup();item=candidate(snap,'RUN_GREYWATER_CYCLE');ctx=context();runtime={'household/owner_policy.py':'a'*64}
    receipt=seal_plan(snapshot=snap,registry=registry,candidates=[item],coordination=ctx,utilities={item.intent_id:1e6},
        now=NOW,reserve_soc=10.,horizon_hours=24,runtime_manifest=runtime,model_refs=[],forecast_ref=None)
    assert receipt['plan']['candidate_decisions'][0]['reason']=='planner_authority_disabled'
    assert loads(ctx['facts']['hex_southoutlet_cycle']['curfew_allowed']['raw'])['value'] is False
    assert receipt['plan']['selected_intent_ids']==[] and not receipt['plan']['automatic_actuation']
    assert replay_plan(receipt,runtime_manifest=runtime)==receipt
    bad=deepcopy(receipt);entry=bad['inputs']['coordination']['facts']['hex_southoutlet_cycle']['curfew_allowed']
    fact=loads(entry['raw']);fact['value']=True;entry['raw']=canonical(fact).decode();entry['sha256']=sha256(entry['raw'].encode()).hexdigest()
    bad['receipt_sha256']=identity({k:v for k,v in bad.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):replay_plan(bad,runtime_manifest=runtime)

def test_reading_old_status_does_not_renew_freshness():
    ctx=context(original(evaluated=NOW-timedelta(seconds=120)))
    assert ctx['policy_observations']=={} and set(ctx['facts']['hex_southoutlet_cycle'])=={'owner_available'}

def test_positive_or_unknown_report_never_manufactures_permission():
    for reason in ['cycle_completed','low_soc','future_reason']:
        ctx=context(original(reason));assert set(ctx['facts']['hex_southoutlet_cycle'])=={'owner_available'}

def mutate_status(source,raw):
    source['status']['raw']=raw;source['status']['sha256']=sha256(raw.encode()).hexdigest()

@pytest.mark.parametrize('damage',['hash','endpoint','future_evaluation','reversed_requests','late_read','duplicate_key','future_schedule','wrong_schedule','rule_changed','rule_owner','rule_condition'])
def test_corrupt_or_inconsistent_originals_refuse(damage):
    value=original()
    if damage=='hash':value['status']['sha256']='a'*64
    elif damage=='endpoint':value['status']['endpoint']='/items/Other/state'
    elif damage=='future_evaluation':value=original(evaluated=NOW+timedelta(seconds=1))
    elif damage=='reversed_requests':value['rule_after']['requested_at']=(NOW-timedelta(seconds=10)).isoformat()
    elif damage=='late_read':value['rule_after']['received_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='duplicate_key':mutate_status(value,value['status']['raw']+',reason=busy')
    elif damage=='future_schedule':
        value=original('cooldown_wait');mutate_status(value,value['status']['raw'].replace((NOW-timedelta(seconds=5)+timedelta(minutes=30)).isoformat(),(NOW+timedelta(days=1)).isoformat()))
    elif damage=='wrong_schedule':mutate_status(value,value['status']['raw'].replace('scheduling=blocked','scheduling=conditional'))
    else:
        rule=loads(value['rule_after']['raw'])
        if damage=='rule_changed':rule['configuration']={'changed':True}
        elif damage=='rule_owner':rule['uid']='other_owner'
        else:rule['conditions']=[{'type':'unrecognized'}]
        value['rule_after']['raw']=canonical(rule).decode();value['rule_after']['sha256']=sha256(value['rule_after']['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):context(value)

def test_unknown_stable_policy_source_is_retained_without_deriving_facts():
    value=original()
    for name in ['rule_before','rule_after']:
        rule=loads(value[name]['raw']);rule['actions'][0]['configuration']['script']+='\n// changed policy'
        value[name]['raw']=canonical(rule).decode();value[name]['sha256']=sha256(value[name]['raw'].encode()).hexdigest()
    ctx=context(value);assert ctx['policy_source']==value and ctx['policy_observations']=={}
    assert set(ctx['facts']['hex_southoutlet_cycle'])=={'owner_available'}

def test_decision_after_evaluation_expiry_does_not_use_blocker_as_current():
    from household.planning import _fact
    snap,registry=setup();ctx=context(original(evaluated=NOW-timedelta(seconds=119)))
    value,reason=_fact(ctx['facts']['hex_southoutlet_cycle']['curfew_allowed'],kind='curfew_allowed',
        owner='hex_southoutlet_cycle',snapshot_id=snap.snapshot_id,now=NOW+timedelta(seconds=1),horizon_hours=24)
    assert value is None and reason=='source_stale'


def test_collector_keeps_bracketed_policy_originals(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch);value=original(now=now);calls=[]
    def read(*,remaining):
        assert remaining()>0;calls.append(1);return value
    collector.policy_reader=read
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['schema']=='earthship-household-cycle-sources/v8' and result['policy_source']==value and calls==[1]

@pytest.mark.parametrize('failure',['transport','malformed','nested','truncated'])
def test_optional_policy_failure_preserves_source_domains(failure,tmp_path,monkeypatch):
    from http.client import IncompleteRead
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch)
    def read(**kw):
        if failure=='transport':raise OSError('unavailable')
        if failure=='nested':raise RecursionError('malformed')
        if failure=='truncated':raise IncompleteRead(b'{',4)
        return {'bad':'source'}
    collector.policy_reader=read
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['policy_source'] is None
    assert result['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000

def test_policy_transport_is_three_bounded_fixed_gets(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch);value=original(now=now);calls=[]
    def get(endpoint,*,maximum,remaining):
        remaining();calls.append((endpoint,maximum));return value[['rule_before','status','rule_after'][len(calls)-1]]['raw'].encode()
    collector._get_original=get
    result=collector._policy_http(remaining=lambda:2.)
    assert calls==[('/rules/hex_southoutlet_cycle',65536),('/items/SouthOutlet_AutoStatus/state',2048),('/rules/hex_southoutlet_cycle',65536)]
    assert result['status']['raw']==value['status']['raw']

def test_full_cycle_retains_policy_and_rederives_original_negative_gate(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household_cycle import derive_cycle
    from household.control_contracts import instant
    args,capture=derived_fixture(tmp_path,monkeypatch);issue=instant(capture['issued_at']);value=original(now=issue)
    args['originals'].update(schema='earthship-household-cycle-sources/v4',daily_energy_source=None,owner_source=None,policy_source=value)
    record=derive_cycle(**args);ctx=record['inputs']['coordination']
    assert ctx['schema']=='earthship-shadow-coordination/v3' and ctx['policy_source']==value
    assert loads(ctx['facts']['hex_southoutlet_cycle']['curfew_allowed']['raw'])['value'] is False
    assert record['output']['projections']['thermal']['output']==capture['output']
    assert not record['output']['automatic_actuation']
    args['originals']['captured_at']=(issue-timedelta(seconds=2)).isoformat()
    with pytest.raises(ValueError,match='policy observation'):derive_cycle(**args)


def test_optional_policy_transport_cannot_swallow_external_deadline(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch);expired=[False]
    def guard():
        if expired[0]:raise ValueError('external issue deadline')
    def read(**kw):expired[0]=True;raise TimeoutError('optional transport ended')
    collector.policy_reader=read
    with pytest.raises(ValueError,match='external issue deadline'):
        collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=guard)

@pytest.mark.parametrize('damage',['observations','source','positive_fact'])
def test_coordination_rederives_all_claims_from_original_policy(damage):
    from household.owner_sources import validate_coordination
    ctx=context();snap,registry=setup()
    if damage=='observations':ctx['policy_observations']['hex_southoutlet_cycle']['reason']='cooldown_wait'
    elif damage=='source':mutate_status(ctx['policy_source'],ctx['policy_source']['status']['raw'].replace('after_dark','busy'))
    else:
        entry=ctx['facts']['hex_southoutlet_cycle']['curfew_allowed'];value=loads(entry['raw']);value['value']=True
        entry['raw']=canonical(value).decode();entry['sha256']=sha256(entry['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):validate_coordination(ctx,snapshot_id=snap.snapshot_id,registry=registry,horizon_hours=24,as_of=NOW)
