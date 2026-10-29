"""Independent-review regressions: evidence, scope, identity and isolation."""
from datetime import timedelta
from copy import deepcopy
from pathlib import Path
import pytest
from local_measurement_test_support import NOW
from test_household_advice_contract import run,policy,state,snapshot
from test_household_planning import setup,context,candidate
from test_shade_position_observations import mapping,packet,event
from household.codec import canonical


def test_current_planner_rejects_essential_and_feeder_coupled_devices():
    from household.planning import plan
    snap,registry=setup()
    for device in ('shureflo','goat-cam'):
        item=candidate(snap,'SET_NIGHT_LOAD_DEVICE',device=device)
        result=plan(snapshot=snap,registry=registry,candidates=[item],coordination=context(snap),utilities={item.intent_id:100},now=NOW,reserve_soc=10.,horizon_hours=24)
        assert result['selected_intent_ids']==[]


def test_thermal_advice_expires_at_max_age_not_only_producer_expiry():
    from household.snapshot import HouseholdSnapshot
    body=snapshot().to_dict();body.pop('snapshot_id');body['temporal_policy']['max_age_seconds']['air_temperature']=25
    ref=body['domains']['thermal']['air_temperature']['evidence'];ref['observed_at']=(NOW-timedelta(seconds=20)).isoformat()
    snap=HouseholdSnapshot(canonical(body));s=state();s['snapshot_id']=snap.snapshot_id
    report=run(snapshot=snap,action_state=s)
    assert report['recommendations'][0]['valid_until']==(NOW+timedelta(seconds=5)).isoformat()


def test_no_change_expires_with_actual_member_observation():
    from household.advice.shade_state import normalize_event
    m=mapping();m['freshness_seconds']=5
    s=state();s['declarations']=[];s['shade_reports']=[normalize_event(m,packet(position=0.))]
    r=run(action_state=s)
    assert r['domains']['shades']['reason']=='target_already_observed'
    assert r['domains']['shades']['valid_until']==(NOW+timedelta(seconds=5)).isoformat()


def test_packet_identity_cannot_be_reused_for_other_motor_or_source():
    from household.advice.shade_state import normalize_event
    p=packet();p.update(device_id='fixture-motor-9',source='fixture-position-channel')
    normalize_event(mapping(),p)
    for key in ('device_id','source'):
        other=mapping();other[key]='unrelated'
        with pytest.raises(ValueError):normalize_event(other,p)


def test_stale_energy_attribution_cannot_abort_independent_advice(tmp_path):
    import household_advice
    tmp_path.chmod(0o700);path=tmp_path/'advice-energy-baseline.json';path.write_bytes(canonical({'stale':'original'}));path.chmod(0o600)
    result=household_advice.publish_cycle_advice(record={'inputs':{'snapshot':snapshot().to_dict()}},energy=None,profiled=None,directory=tmp_path,now=NOW,guard=lambda:None)
    assert result['status']=='written' and (tmp_path/'advice.json').exists()


def test_equivalent_policy_expiry_refresh_preserves_episode_identity():
    p=policy();first=run(policy=p);p['valid_until']=(NOW+timedelta(days=2)).isoformat();p['version']='refresh-2'
    second=run(policy=p)
    assert first['policy_sha256']!=second['policy_sha256']
    assert first['recommendations'][0]['episode_id']==second['recommendations'][0]['episode_id']


def test_target_observation_archive_is_byte_bounded_and_cannot_block_main_advice(tmp_path):
    from household.advice.lifecycle import AdviceHistory
    from household.codec import identity
    import household_advice,json
    tmp_path.chmod(0o700);store=AdviceHistory(tmp_path/'advice.sqlite')
    for i in range(16):
        row=dict(event_id=identity(['event',i]),episode_id=identity(['episode',i]),kind='target_observed',at=NOW.isoformat(),snooze_until=None,corrects=None,
          evidence_refs=[identity(['source',j,i]) for j in range(26)],target='whole-house',position_open_pct=100.,shade_ids=[f'shade-{j}' for j in range(1,27)],origin='device_observation',user_motivation_known=False,thermal_benefit_verified=False)
        with store._connect() as db:db.execute('INSERT INTO physical_feedback VALUES (?,?)',(row['event_id'],canonical(row)))
    result=household_advice.publish_advice(snapshot=snapshot(),projections={},directory=tmp_path,now=NOW,guard=lambda:None)
    assert result['status']=='written' and (tmp_path/'advice.json').exists()
    raw=(tmp_path/'advice-observed-targets.json').read_bytes()
    assert len(raw)<=32768 and json.loads(raw)['omitted_count']>0


def test_energy_comparisons_include_selected_late_window_and_unchanged_baseline():
    from test_household_advice_energy import energy_case
    from household.advice.energy_compare import compare_load_windows
    p,projections=energy_case();inputs=projections['flexible_energy'];load=p['energy']['loads'][0]
    load['deadline']=(NOW+timedelta(hours=12)).isoformat()
    for i,row in enumerate(inputs['steps']):row['potential_pv_kwh']=0. if i<10 else 2.
    result=compare_load_windows(inputs=inputs,load=load,now=NOW,reserve=20.)
    assert result['best']['start']==(NOW+timedelta(hours=10)).isoformat()
    assert any(result['best']['start'] in r['alternative'] for r in result['comparison'])
    assert any(r['alternative']=='Leave unchanged' for r in result['comparison'])


def test_night_load_devices_are_not_current_ml_planning_candidates():
    from household.planning import plan
    snap,registry=setup();item=candidate(snap,'SET_NIGHT_LOAD_DEVICE',device='dishwasher')
    result=plan(snapshot=snap,registry=registry,candidates=[item],coordination=context(snap),utilities={item.intent_id:100},now=NOW,reserve_soc=10.,horizon_hours=24)
    assert result['selected_intent_ids']==[]


def test_one_physical_motor_cannot_satisfy_two_logical_shade_targets():
    from household.advice.shade_state import normalize_event,target_observed
    first=mapping();second=mapping();second['shade_id']='shade-10'
    p=packet(position=0.)
    rows=[normalize_event(first,p),normalize_event(second,p)]
    assert not target_observed(rows,{'shade-9':100.,'shade-10':100.},now=NOW)


@pytest.mark.parametrize('device',['Goat_Plugs_Outlet1_Switch','Goat_Plugs_Outlet2_Switch','OverrideSwitch','FeederOverride','NightLoadOverride_Request'])
def test_real_protected_item_aliases_cannot_become_discretionary_tasks(device):
    from test_household_advice_energy import energy_case
    p,projections=energy_case();p['energy']['loads'][0]['devices']=[device]
    result=run(policy=p,projections=projections)
    assert result['domains']['energy']['reason']=='no_approved_useful_flexible_task'


def test_large_optional_model_context_does_not_take_down_independent_advice(tmp_path):
    import household_advice
    tmp_path.chmod(0o700)
    result=household_advice.publish_advice(snapshot=snapshot(),projections={'thermal_evaluation_context':{'unsupported_payload':'x'*600000}},directory=tmp_path,now=NOW,guard=lambda:None)
    assert result['status']=='written' and result['auxiliary_status']=='unavailable'


def test_unrelated_energy_policy_refresh_does_not_resurrect_shade_advice():
    p=policy();first=run(policy=p);p['energy']['reserve_soc_pct']=30.;second=run(policy=p)
    assert first['recommendations'][0]['episode_id']==second['recommendations'][0]['episode_id']


def test_native_device_and_source_identifiers_are_retained_without_aliasing():
    from household.advice.shade_state import normalize_event
    m=mapping();m['device_id']='dooya:rf:AA:10/03';m['source']='mqtt:topic:mosquitto/shade-9/state'
    p=packet(device_id=m['device_id'],source=m['source'])
    value=normalize_event(m,p)
    assert value['device_id']==m['device_id'] and value['source']==m['source']


def test_report_precision_does_not_turn_a_nearby_stop_into_target_completion():
    from household.advice.shade_state import normalize_event,target_observed
    m=mapping();m['resolution']=1.
    row=normalize_event(m,packet(position=1.))
    assert row['position_open_pct']==99.
    assert not target_observed([row],{'shade-9':100.},now=NOW)
