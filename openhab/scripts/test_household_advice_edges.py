"""Independent domain failures, observed movement holds and resource boundaries."""
from datetime import timedelta
from copy import deepcopy
import pytest
from test_household_advice_contract import run,policy,state,snapshot
from test_household_advice_thermal import temperatures
from test_shade_position_observations import event
from local_measurement_test_support import NOW


def test_invalid_solar_model_leaves_independent_valid_ventilation_advice():
    snap=temperatures(85.,70.);s=state();s['snapshot_id']=snap.snapshot_id
    for key in ('rain','wind','security','smoke'):s['checks'][key]=dict(clear=True,observed_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=90)).isoformat(),source_ref='a'*64)
    r=run(snapshot=snap,action_state=s,projections={'solar':{'invalid':'fixture'}})
    assert r['domains']['shades']['status'] in ('unavailable','insufficient_evidence')
    assert r['domains']['ventilation']['status']=='recommendation_available'


def test_device_declaration_conflict_and_missing_member_are_not_averaged_away():
    s=state();s['shade_reports']=[event(position=50.)]
    assert run(action_state=s)['domains']['shades']['reason']=='device_declaration_conflict'
    s['declarations']=[];p=policy();p['shades']['shade_ids'].append('shade-10')
    assert run(policy=p,action_state=s)['domains']['shades']['reason']=='shade_member_unavailable'


def test_recent_unknown_origin_movement_honors_setting_without_claiming_manual_intent():
    s=state();s['declarations']=[];s['shade_reports']=[event(position=50.)]
    s['shade_movements']=[dict(shade_id='shade-9',epoch='fixture-install-1',stop_observed_at=NOW.isoformat(),event_refs=['a'*64])]
    result=run(action_state=s)['domains']['shades']
    assert result['status']=='no_change_recommended' and result['reason']=='recent_setting_hold'


def test_shade_history_exhaustion_refuses_new_data_without_erasing_originals(tmp_path,monkeypatch):
    from household.advice import shade_state
    monkeypatch.setattr(shade_state,'MAX_EVENTS',1)
    store=shade_state.ShadeHistory(tmp_path/'shade.sqlite');original=event();store.ingest(original)
    with pytest.raises(ValueError,match='capacity'):store.ingest(event(seq=2,position=50.))
    assert store.originals()==[original]


def test_small_temperature_noise_never_reverses_shade_direction():
    for temperature in (64.9,65.,65.1):
        snap=temperatures(temperature);s=state();s['snapshot_id']=snap.snapshot_id
        assert run(snapshot=snap,action_state=s)['domains']['shades']['status']=='no_change_recommended'
