"""Hard constraints cannot be outweighed by utility or simultaneous requests."""
import importlib,json
from datetime import timedelta
from hashlib import sha256
import pytest
from test_household_snapshot import build as snapshot
from test_household_intents import document
from test_household_capabilities import originals
from local_measurement_test_support import NOW
from household.capabilities import build_registry
from household.intents import build_intent


def api():
    assert importlib.util.find_spec('household.planning') is not None,'shadow planner missing'
    return importlib.import_module('household.planning')


def setup():
    snap=snapshot();managed,ownership=originals();registry=build_registry(managed,ownership)
    return snap,registry


def candidate(snap,kind='RUN_GREYWATER_CYCLE',delta=-1.,device=None):
    ref=snap.to_dict()['domains']['energy']['battery_soc']['evidence']['digest']
    params={} if device is None else {'device':device,'command':'ON'}
    body=document(snap,type=kind,parameters=params,evidenceRefs=[ref],confidence='low',reasonCodes=['no_optional_action'],
        predictedEffects=dict(batteryKwh=-.2,socPct=delta,thermalF=None,water=None,wearCost=1.))
    return build_intent(body,snapshot=snap,now=NOW)


def fact(snap,kind,owner,value):
    raw=json.dumps(dict(schema='earthship-shadow-coordination-fact/v1',kind=kind,owner=owner,value=value,snapshotId=snap.snapshot_id,
        horizonHours=24,receivedAt=NOW.isoformat(),validUntil=(NOW+timedelta(seconds=120)).isoformat(),scope='declared_shadow_bounds'))
    return {'raw':raw,'sha256':sha256(raw.encode()).hexdigest()}


def context(snap):
    owners=('hex_southoutlet_cycle','88bd9ec4de','hex_night_load_override')
    return dict(schema='earthship-shadow-coordination/v1',snapshotId=snap.snapshot_id,
        horizonHours=24,baseline_soc_floor=fact(snap,'baseline_soc_floor',None,12.),
        facts={owner:{kind:fact(snap,kind,owner,True) for kind in ('owner_available','owner_idle','cooldown_ready','curfew_allowed','operator_unlocked','manual_override_clear')} for owner in owners})


def run(candidates=None,ctx=None,utilities=None,**changes):
    snap,registry=setup();items=candidates(snap) if callable(candidates) else [candidate(snap)] if candidates is None else candidates
    return api().plan(snapshot=snap,registry=registry,candidates=items,coordination=context(snap) if ctx is None else ctx(snap),
        utilities={item.intent_id:10. for item in items} if utilities is None else utilities(items),
        now=NOW,reserve_soc=changes.pop('reserve_override',10.),horizon_hours=changes.pop('horizon_hours',24),**changes)


def test_optional_selection_is_shadow_only_and_sealed_deterministically():
    first=run();assert first==run()
    assert len(first['selected_intent_ids'])==1
    assert first['automatic_actuation'] is False and first['scope']=='declared_shadow_bounds'
    assert first['owner_live_gate_still_required'] is True
    assert first['baseline_scores']['no_optional_action']==0


@pytest.mark.parametrize('gate',['owner_available','owner_idle','cooldown_ready','curfew_allowed','operator_unlocked','manual_override_clear'])
def test_each_hard_gate_blocks_even_with_large_utility(gate):
    def changed(snap):
        ctx=context(snap);ctx['facts']['hex_southoutlet_cycle'][gate]=fact(snap,gate,'hex_southoutlet_cycle',False);return ctx
    result=run(ctx=changed,utilities=lambda items:{item.intent_id:1e6 for item in items})
    assert result['selected_intent_ids']==[]
    assert result['candidate_decisions'][0]['status']=='rejected'


def test_missing_coordination_never_defaults_to_permission():
    result=run(ctx=lambda snap:{**context(snap),'facts':{}})
    assert result['selected_intent_ids']==[] and result['candidate_decisions'][0]['status']=='unknown'


def test_cumulative_reserve_blocks_pair_that_each_passes_individually():
    result=run(candidates=lambda snap:[candidate(snap,delta=-2),candidate(snap,'SET_NIGHT_LOAD_DEVICE',delta=-2,device='dishwasher')])
    assert len(result['selected_intent_ids'])==1
    assert result['reserve_checks']['selected_floor_soc']==10


def test_same_owner_intents_conflict_with_deterministic_tie_break():
    def items(snap):return [candidate(snap,'SET_NIGHT_LOAD_DEVICE',device='dishwasher'),candidate(snap,'SET_NIGHT_LOAD_DEVICE',device='shureflo')]
    a=run(candidates=items);b=run(candidates=lambda snap:list(reversed(items(snap))))
    assert a==b and len(a['selected_intent_ids'])==1
    assert any(row['status']=='superseded' for row in a['candidate_decisions'])


@pytest.mark.parametrize('damage',['digest','future','expired','owner','scope','snapshot'])
def test_bad_original_fact_binding_cannot_pass_a_hard_gate(damage):
    def changed(snap):
        ctx=context(snap);entry=ctx['facts']['hex_southoutlet_cycle']['owner_available'];raw=json.loads(entry['raw'])
        if damage=='digest':entry['sha256']='0'*64
        else:
            if damage=='future':raw['receivedAt']=(NOW+timedelta(seconds=1)).isoformat()
            elif damage=='expired':raw['validUntil']=NOW.isoformat()
            elif damage=='owner':raw['owner']='other-owner'
            elif damage=='scope':raw['scope']='live_authorization'
            else:raw['snapshotId']='f'*64
            entry['raw']=json.dumps(raw);entry['sha256']=sha256(entry['raw'].encode()).hexdigest()
        return ctx
    result=run(ctx=changed)
    assert result['selected_intent_ids']==[]


def test_exhaustive_selection_beats_a_greedy_first_action():
    def items(snap):return [candidate(snap,delta=-2),candidate(snap,'SET_NIGHT_LOAD_DEVICE',delta=-1,device='dishwasher'),candidate(snap,delta=-1)]
    def utilities(items):return {item.intent_id:score for item,score in zip(items,(10.,6.,6.))}
    result=run(candidates=items,utilities=utilities)
    assert result['objective']['total']==12. and result['baseline_scores']['greedy']==10.
    assert len(result['selected_intent_ids'])==2


def test_bounded_candidates_and_duplicate_identity_refused():
    snap,_=setup();item=candidate(snap)
    with pytest.raises(ValueError):run(candidates=[item]*9)
    with pytest.raises(ValueError):run(candidates=[item,item])


def test_explicit_horizon_is_bound_and_bad_horizons_refused():
    result=run(horizon_hours=24)
    assert result['horizon_hours']==24
    with pytest.raises(ValueError):run(horizon_hours=48)
    with pytest.raises(ValueError):run(horizon_hours=6)
    result=run(horizon_hours=6,ctx=lambda snap:{**context(snap),'horizonHours':6})
    assert result['selected_intent_ids']==[]


def test_no_action_does_not_claim_to_repair_an_unsafe_baseline():
    result=run(ctx=lambda snap:{**context(snap),'baseline_soc_floor':fact(snap,'baseline_soc_floor',None,8.)})
    assert result['selected_intent_ids']==[] and result['status']=='baseline_outside_reserve'


def test_originals_and_complete_decisions_replay_without_live_reads():
    snap,registry=setup();items=[candidate(snap)]
    receipt=api().seal_plan(snapshot=snap,registry=registry,candidates=items,coordination=context(snap),
        utilities={items[0].intent_id:10.},now=NOW,reserve_soc=10.,horizon_hours=24,
        runtime_manifest={'household/planning.py':'a'*64},model_refs=[],forecast_ref=None)
    assert api().replay_plan(receipt,runtime_manifest={'household/planning.py':'a'*64})==receipt
    assert receipt['plan']['selected_intent_ids']==[items[0].intent_id]


@pytest.mark.parametrize('damage',['output','input','runtime','ref','extra'])
def test_changed_plan_or_provenance_cannot_reuse_sealed_receipt(damage):
    snap,registry=setup();items=[candidate(snap)]
    receipt=api().seal_plan(snapshot=snap,registry=registry,candidates=items,coordination=context(snap),
        utilities={items[0].intent_id:10.},now=NOW,reserve_soc=10.,horizon_hours=24,
        runtime_manifest={'household/planning.py':'a'*64},model_refs=[],forecast_ref=None)
    runtime={'household/planning.py':'a'*64}
    if damage=='output':receipt['plan']['selected_intent_ids']=[]
    elif damage=='input':receipt['inputs']['reserve_soc']=99.
    elif damage=='runtime':runtime['household/planning.py']='b'*64
    elif damage=='ref':receipt['inputs']['candidates'][0]['intent']['evidenceRefs']=['f'*64]
    else:receipt['authorization']=True
    with pytest.raises(ValueError):api().replay_plan(receipt,runtime_manifest=runtime)


def test_declared_battery_floor_cannot_exceed_physical_percentage_range():
    result=run(candidates=lambda snap:[candidate(snap,delta=100)])
    assert result['selected_intent_ids']==[] and result['candidate_decisions'][0]['reason']=='hard_constraint'


def test_replay_performs_no_live_or_original_file_reads(tmp_path,monkeypatch):
    import builtins,psycopg2
    from pathlib import Path
    snap,registry=setup();items=[candidate(snap)]
    manifest={'household/planning.py':'a'*64}
    receipt=api().seal_plan(snapshot=snap,registry=registry,candidates=items,coordination=context(snap),
        utilities={items[0].intent_id:10.},now=NOW,reserve_soc=10.,horizon_hours=24,
        runtime_manifest=manifest,model_refs=[],forecast_ref=None)
    def forbidden(*args,**kwargs):pytest.fail('live read inside pure plan replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    assert api().replay_plan(receipt,runtime_manifest=manifest)==receipt


def test_plan_cli_refuses_special_files_without_blocking(tmp_path):
    import subprocess,sys,os
    from pathlib import Path
    script=Path(__file__).with_name('household_plan.py');assert script.exists(),'plan replay CLI missing'
    fifo=tmp_path/'receipt';os.mkfifo(fifo,0o600)
    result=subprocess.run([sys.executable,str(script),'--receipt',str(fifo)],capture_output=True,text=True,timeout=3)
    assert result.returncode==1 and not result.stdout and 'Traceback' not in result.stderr


def test_plan_cli_refuses_unbounded_or_invalid_private_receipts(tmp_path):
    import subprocess,sys
    from pathlib import Path
    script=Path(__file__).with_name('household_plan.py');assert script.exists(),'plan replay CLI missing'
    receipt=tmp_path/'receipt';receipt.write_text('{"unexpected":"private-context-must-not-be-printed"}');receipt.chmod(0o600)
    result=subprocess.run([sys.executable,str(script),'--receipt',str(receipt)],capture_output=True,text=True,timeout=5)
    assert result.returncode==1 and not result.stdout and 'private-context' not in result.stderr


def test_cli_replays_complete_private_receipt_against_actual_runtime(tmp_path):
    import subprocess,sys
    from pathlib import Path
    from household_snapshot import runtime_manifest
    snap,registry=setup();items=[candidate(snap)];script=Path(__file__).with_name('household_plan.py')
    runtime=runtime_manifest();runtime['openhab/scripts/household_plan.py']=sha256(script.read_bytes()).hexdigest()
    receipt=api().seal_plan(snapshot=snap,registry=registry,candidates=items,coordination=context(snap),
        utilities={items[0].intent_id:10.},now=NOW,reserve_soc=10.,horizon_hours=24,runtime_manifest=runtime,model_refs=[],forecast_ref=None)
    source=tmp_path/'plan.json';source.write_text(json.dumps(receipt));source.chmod(0o600)
    result=subprocess.run([sys.executable,str(script),'--receipt',str(source)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt
    receipt['runtime_manifest']['openhab/scripts/household_plan.py']='f'*64
    from household.codec import identity
    receipt['receipt_sha256']=identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})
    source.write_text(json.dumps(receipt))
    refused=subprocess.run([sys.executable,str(script),'--receipt',str(source)],capture_output=True,text=True,timeout=10)
    assert refused.returncode==1 and not refused.stdout


def test_emergency_reserve_cannot_be_weakened_by_planner_input():
    with pytest.raises(ValueError):run(reserve_override=0.)


def test_unknown_owner_busy_state_does_not_become_idle_permission():
    def changed(snap):
        ctx=context(snap);ctx['facts']['hex_southoutlet_cycle'].pop('owner_idle',None);return ctx
    result=run(ctx=changed)
    assert result['selected_intent_ids']==[] and result['candidate_decisions'][0]['status']=='unknown'


@pytest.mark.parametrize('failure,seconds,reason',[
    ('expired',120,'intent_expired'),('stale',100,'source_stale'),
    ('snapshot',0,'snapshot_mismatch')])
def test_replay_preserves_original_validation_context_for_rejected_candidates(failure,seconds,reason):
    snap,registry=setup();item=candidate(snap)
    decision_snapshot=snapshot(config_revision='c'*64) if failure=='snapshot' else snap
    receipt=api().seal_plan(snapshot=decision_snapshot,registry=registry,candidates=[item],
        coordination=context(decision_snapshot),utilities={item.intent_id:10.},
        now=NOW+timedelta(seconds=seconds),reserve_soc=10.,horizon_hours=24,
        runtime_manifest={'household/planning.py':'a'*64},model_refs=[],forecast_ref=None)
    assert receipt['plan']['selected_intent_ids']==[]
    assert receipt['plan']['candidate_decisions'][0]['reason']==reason
    assert api().replay_plan(receipt,runtime_manifest={'household/planning.py':'a'*64})==receipt


@pytest.mark.parametrize('damage',['extra','snapshot','validation_clock'])
def test_replay_refuses_changed_original_candidate_context_even_when_resealed(damage):
    from household.codec import identity
    snap,registry=setup();item=candidate(snap)
    receipt=api().seal_plan(snapshot=snap,registry=registry,candidates=[item],
        coordination=context(snap),utilities={item.intent_id:10.},now=NOW,
        reserve_soc=10.,horizon_hours=24,runtime_manifest={'household/planning.py':'a'*64},model_refs=[],forecast_ref=None)
    entry=receipt['inputs']['candidates'][0]
    if damage=='extra':entry['authorized']=True
    elif damage=='snapshot':entry['validation_snapshot']['snapshot_id']='f'*64
    else:entry['validated_at']=(NOW+timedelta(seconds=120)).isoformat()
    receipt['receipt_sha256']=identity({key:value for key,value in receipt.items() if key!='receipt_sha256'})
    with pytest.raises(ValueError):api().replay_plan(receipt,runtime_manifest={'household/planning.py':'a'*64})


def test_feeder_is_excluded_from_new_shadow_optimization_even_with_complete_facts():
    result=run(candidates=lambda snap:[candidate(snap,'RUN_FEEDER_CYCLE',delta=0)],
        utilities=lambda items:{item.intent_id:1e6 for item in items})
    assert result['selected_intent_ids']==[]
    decision=result['candidate_decisions'][0]
    assert decision['status']=='rejected' and decision['reason']=='planner_authority_disabled'
    assert result['automatic_actuation'] is False
    declared={row['rule'] for row in result['constraint_catalog']}
    assert all(check['rule'] in declared for check in decision['hard_checks'])


def test_excluded_feeder_cannot_displace_an_in_scope_optional_candidate():
    def items(snap):return [candidate(snap),candidate(snap,'RUN_FEEDER_CYCLE',delta=0)]
    result=run(candidates=items,utilities=lambda rows:{item.intent_id:score for item,score in zip(rows,(10.,1e6))})
    snap,_=setup();greywater=candidate(snap)
    assert result['selected_intent_ids']==[greywater.intent_id]
    feeder=next(row for row in result['candidate_decisions'] if row['intent_id']!=greywater.intent_id)
    assert feeder['status']=='rejected' and feeder['reason']=='planner_authority_disabled'


def test_retained_feeder_plan_requires_its_original_producer_instead_of_reinterpretation():
    from pathlib import Path
    from household.codec import loads
    original=loads((Path(__file__).with_name('fixtures')/'household-feeder-plan-original-v1.json').read_bytes())
    assert original['inputs']['candidates'][0]['intent']['type']=='RUN_FEEDER_CYCLE'
    assert len(original['plan']['selected_intent_ids'])==1
    before=__import__('copy').deepcopy(original)
    current={'household/planning.py':sha256(Path(api().__file__).read_bytes()).hexdigest()}
    with pytest.raises(ValueError,match='executing planner runtime differs'):
        api().replay_plan(original,runtime_manifest=current)
    # Merely claiming the old hash must not turn a historical acceptance into
    # a current rejection with the original receipt identity.
    with pytest.raises(ValueError,match='rederived original plan differs'):
        api().replay_plan(original,runtime_manifest=original['runtime_manifest'])
    assert original==before
