"""Same-issue PV/load trajectories inform shadow candidates without authority."""
from copy import deepcopy
from datetime import timedelta
import importlib
from pathlib import Path
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_native_weather import originals


def case(tmp_path,monkeypatch,originals,*,horizon=24,profiled=False,missing_storage=False,coordination_factory=None):
    import test_household_model_pipeline as models
    from test_household_pipeline import config
    original_run=models.run
    def run(snapshot,thermal=None,**changes):
        preferences={**config(),'horizon_hours':horizon}
        coordination=dict(schema='earthship-shadow-coordination/v1',snapshotId=snapshot.snapshot_id,horizonHours=horizon,baseline_soc_floor=None,facts={})
        if coordination_factory is not None:coordination=coordination_factory(snapshot,horizon)
        return original_run(snapshot,thermal,config=preferences,coordination=coordination,**changes)
    from test_household_energy_forecast import fixture
    with monkeypatch.context() as scoped:
        scoped.setattr(models,'run',run)
        energy_api,energy_args,plan=fixture(tmp_path,monkeypatch,originals)
    if missing_storage:energy_args['topology_source']=None
    energy=energy_api.seal_energy_forecast(**energy_args)
    from household_profiled_forecast import seal_profiled_forecast,profiled_runtime_manifest
    from test_household_profiled_forecast import supported_source
    source,lr=supported_source(instant(energy['output']['array_pv']['origin'])) if profiled else (None,{})
    profile=seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=source,now=energy_args['now'],
        runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=energy_api.forecast_runtime_manifest(),load_runtime_manifest=lr)
    api=importlib.import_module('household_legacy_trajectory_plan')
    args=dict(plan_receipt=plan,energy_receipt=energy,profiled_receipt=profile,now=energy_args['now'],runtime_manifest=api.trajectory_runtime_manifest(),
        thermal_runtime=plan['inputs']['thermal_inputs']['executing_runtime'],load_runtime_manifest=lr)
    return api,args


def test_constant_load_fallback_uses_rolling_trajectory_and_preserves_all_originals(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals);before={k:canonical(args[k]) for k in ('plan_receipt','energy_receipt','profiled_receipt')}
    value=api.seal_trajectory_plan(**args);out=value['output'];storage=args['energy_receipt']['output']['nominal_storage']
    assert value['schema']=='earthship-household-trajectory-shadow-receipt/v1'
    assert out['energy_projection']['basis']=='constant_load_pv' and out['energy_projection']['selection_reason']=='load_model_unavailable'
    assert out['energy_projection']['minimum_nominal_soc_pct']==min(storage['initial_soc_pct'],*(p['nominal_soc_pct'] for p in storage['trajectory']))
    assert out['plan_receipt']['plan']['selected_intent_ids']==[] and out['automatic_actuation'] is False
    assert out['candidate_generation']['action_effects_qualified'] is False
    assert out['plan_receipt']['inputs']['coordination']==args['plan_receipt']['inputs']['coordination']
    assert {k:canonical(args[k]) for k in before}==before
    assert api.replay_trajectory_plan(value,**{k:v for k,v in args.items() if k!='now'})==value


def test_learned_load_is_selected_without_turning_model_confidence_into_action_effects(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals,profiled=True);value=api.seal_trajectory_plan(**args);out=value['output']
    assert out['energy_projection']['basis']=='profiled_load_pv'
    assert out['energy_projection']['trajectory']==args['profiled_receipt']['output']['profiled_storage']['trajectory']
    assert out['energy_projection']['load_model_artifact_sha256']==args['profiled_receipt']['inputs']['load_source']['artifact']['artifact_sha256']
    assert out['plan_receipt']['model_refs'][0]['artifact_sha256']==out['energy_projection']['load_model_artifact_sha256']
    assert out['plan_receipt']['plan']['selected_intent_ids']==[]
    for item in out['candidate_intents']:
        assert all(v is None for v in item['predictedEffects'].values()) and item['confidence']=='unavailable' and item['shadowOnly'] is True
    assert out['energy_projection']['physical_calibration_qualified'] is False


@pytest.mark.parametrize('horizon',[6,12,24])
def test_exact_horizon_uses_only_its_cumulative_energy_and_SOC_targets(tmp_path,monkeypatch,originals,horizon):
    api,args=case(tmp_path,monkeypatch,originals,horizon=horizon);out=api.seal_trajectory_plan(**args)['output'];storage=args['energy_receipt']['output']['nominal_storage'];projection=out['energy_projection']
    assert len(projection['trajectory'])==horizon
    assert projection['horizon_hours']==out['plan_receipt']['plan']['horizon_hours']==horizon
    assert projection['modeled_unaccepted_pv_kwh']==storage['trajectory'][horizon-1]['cumulative_modeled_unaccepted_pv_kwh']
    assert projection['minimum_nominal_soc_pct']==min(storage['initial_soc_pct'],*(r['nominal_soc_pct'] for r in storage['trajectory'][:horizon]))
    assert out['candidate_generation']['reason'] is None,out['candidate_generation']
    kinds={v['type'] for v in out['candidate_intents']}
    assert kinds==set()
    assert out['no_action_intent']['type']=='NO_ACTION'
    units=out['candidate_generation']['objective_units'];assert units['surplus_weight']=='declared_preference_points_per_nominal_unaccepted_DC_kWh'


def test_unavailable_storage_emits_no_energy_candidates_and_keeps_original_thermal_context(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals,missing_storage=True);out=api.seal_trajectory_plan(**args)['output']
    assert out['energy_projection']['status']=='unavailable' and out['candidate_intents']==[]
    assert out['energy_projection']['minimum_nominal_soc_pct'] is None
    assert out['thermal_projection_sha256']==args['plan_receipt']['output']['projections']['thermal']['projection_sha256']
    assert out['plan_receipt']['plan']['selected_intent_ids']==[]


@pytest.mark.parametrize('damage',['base_plan','energy','profile','runtime','future'])
def test_changed_or_mismatched_original_inputs_cannot_be_adopted(tmp_path,monkeypatch,originals,damage):
    api,args=case(tmp_path,monkeypatch,originals)
    if damage=='base_plan':args['plan_receipt']['output']['projections']['energy']['output']['trough_pred']=0
    elif damage=='energy':args['energy_receipt']['output']['nominal_storage']['trajectory'][0]['nominal_soc_pct']=0
    elif damage=='profile':args['profiled_receipt']['inputs']['original_energy_receipt_sha256']='f'*64
    elif damage=='runtime':args['runtime_manifest']['openhab/scripts/household_trajectory_plan.py']='f'*64
    else:args['now']+=timedelta(seconds=121)
    if damage in ('base_plan','energy','profile'):
        name={'base_plan':'plan_receipt','energy':'energy_receipt','profile':'profiled_receipt'}[damage];args[name]['receipt_sha256']=identity({k:v for k,v in args[name].items() if k!='receipt_sha256'})
    if damage=='runtime':
        value=api.seal_trajectory_plan(**args);args['runtime_manifest']=api.trajectory_runtime_manifest()
        with pytest.raises(ValueError):api.replay_trajectory_plan(value,**{k:v for k,v in args.items() if k!='now'})
    else:
        with pytest.raises(ValueError):api.seal_trajectory_plan(**args)


@pytest.mark.parametrize('damage',['projection','candidates','effects','chosen','input_pin'])
def test_resealing_new_outputs_never_bypasses_rederivation(tmp_path,monkeypatch,originals,damage):
    api,args=case(tmp_path,monkeypatch,originals);value=api.seal_trajectory_plan(**args)
    if damage=='projection':value['output']['energy_projection']['minimum_nominal_soc_pct']=0
    elif damage=='candidates':value['output']['candidate_intents']=[] if value['output']['candidate_intents'] else [{}]
    elif damage=='effects':value['output']['candidate_generation']['action_effects_qualified']=True
    elif damage=='chosen':value['output']['plan_receipt']['plan']['selected_intent_ids']=['f'*64]
    else:value['inputs']['plan_document_sha256']='f'*64
    value['receipt_sha256']=identity({k:v for k,v in value.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api.replay_trajectory_plan(value,**{k:v for k,v in args.items() if k!='now'})


def test_absent_profile_is_a_declared_constant_load_fallback(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals);args['profiled_receipt']=None
    value=api.seal_trajectory_plan(**args)
    assert value['inputs']['profiled_document_sha256'] is None
    assert value['output']['energy_projection']['basis']=='constant_load_pv'


def test_replay_opens_no_live_readers_and_CLI_checks_external_original_bytes(tmp_path,monkeypatch,originals,capsys):
    api,args=case(tmp_path,monkeypatch,originals);value=api.seal_trajectory_plan(**args)
    import socket,urllib.request,psycopg2
    def forbidden(*a,**kw):pytest.fail('live data during shadow replay')
    for module,name in ((socket,'create_connection'),(urllib.request,'urlopen'),(psycopg2,'connect')):monkeypatch.setattr(module,name,forbidden)
    assert api.replay_trajectory_plan(value,**{k:v for k,v in args.items() if k!='now'})==value
    command=[]
    for name,document in (('receipt',value),('plan',args['plan_receipt']),('energy',args['energy_receipt']),('profiled',args['profiled_receipt'])):
        path=tmp_path/(name+'.json');path.write_bytes(canonical(document));path.chmod(0o600);command.extend(['--'+name,str(path)])
    assert api.main(command)==0 and loads(capsys.readouterr().out)==value
    (tmp_path/'energy.json').write_bytes(b'{}')
    assert api.main(command)==1 and 'replay refused' in capsys.readouterr().err


def declared_gates(snapshot,horizon):
    from household.planning import GATES
    at=instant(snapshot.to_dict()['created_at'])
    def fact(kind,owner,value):
        raw=canonical(dict(schema='earthship-shadow-coordination-fact/v1',kind=kind,owner=owner,value=value,snapshotId=snapshot.snapshot_id,
            horizonHours=horizon,receivedAt=at.isoformat(),validUntil=(at+timedelta(seconds=120)).isoformat(),scope='declared_shadow_bounds')).decode()
        from hashlib import sha256
        return dict(raw=raw,sha256=sha256(raw.encode()).hexdigest())
    return dict(schema='earthship-shadow-coordination/v1',snapshotId=snapshot.snapshot_id,horizonHours=horizon,
        baseline_soc_floor=fact('baseline_soc_floor',None,90.),facts={owner:{name:fact(name,owner,True) for name in GATES}
            for owner in ('hex_southoutlet_cycle','88bd9ec4de','hex_night_load_override')})


def test_nominal_model_cannot_supply_action_effects_even_when_every_declared_gate_passes(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals,coordination_factory=declared_gates)
    out=api.seal_trajectory_plan(**args)['output'];plan=out['plan_receipt']['plan']
    assert out['candidate_intents']==[] and plan['reserve_checks']['baseline_floor_soc']==90
    assert plan['planner_version']=='bounded_exhaustive_v2'
    assert plan['selected_intent_ids']==[]
    for row in plan['candidate_decisions']:
        checks={v['rule']:v for v in row['hard_checks']}
        assert checks['battery_reserve']['status']=='unknown' and checks['battery_reserve']['reason']=='unqualified_effect'
        assert all(checks[name]['status']=='pass' for name in ('owner_available','owner_idle','cooldown_ready','curfew_allowed','operator_unlocked','manual_override_clear'))


def test_same_SOC_different_original_snapshot_cannot_supply_the_energy_trajectory(tmp_path,monkeypatch,originals):
    first=tmp_path/'first';other=tmp_path/'other';first.mkdir();other.mkdir()
    api,args=case(first,monkeypatch,originals);_,second=case(other,monkeypatch,originals)
    a,b=args['plan_receipt']['inputs']['snapshot'],second['plan_receipt']['inputs']['snapshot']
    assert a['domains']['energy']['battery_soc']['value']==b['domains']['energy']['battery_soc']['value']
    assert a['snapshot_id']!=b['snapshot_id']
    args['energy_receipt']=second['energy_receipt']
    with pytest.raises(ValueError):api.seal_trajectory_plan(**args)


def test_expired_measurement_does_not_inherit_a_nominal_trajectory_permission(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals);snap=args['plan_receipt']['inputs']['snapshot'];origin=instant(snap['as_of'])
    end=min(instant(snap['domains']['energy'][role]['evidence']['valid_until']) for role in ('battery_soc','estimated_load_w'))
    assert args['now']<end<=origin+timedelta(seconds=120)
    args['now']=end;out=api.seal_trajectory_plan(**args)['output']
    assert out['candidate_generation']['reason']=='source_stale' and out['candidate_intents']==[]
    assert out['plan_receipt']['plan']['selected_intent_ids']==[]
