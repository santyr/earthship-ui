"""Actual acquisitions, native conventions and durable movements are separate from targets."""
from datetime import timedelta
from copy import deepcopy
import importlib
import pytest
from local_measurement_test_support import NOW


def api():return importlib.import_module('household.advice.shade_state')


def mapping(**changes):
    return dict(schema='earthship-shade-mapping/v1',shade_id='shade-9',zone='living',device_id='fixture-motor-9',epoch='fixture-install-1',
        source='fixture-position-channel',convention='closed_100',native_max=100.,resolution=0.1,feedback_basis='independent_position',
        valid_from=(NOW-timedelta(days=1)).isoformat(),freshness_seconds=120,**changes)


def packet(seq=1,position=100.,**changes):
    value=dict(device_id='fixture-motor-9',source='fixture-position-channel',event_id=f'acquisition-{seq}',sequence=seq,native_position=position,native_target=None,movement='stopped',origin='unknown',
        observed_at=NOW.isoformat(),received_at=NOW.isoformat(),available_at=NOW.isoformat(),online=True,time_basis='source_observed')
    value.update(changes);return value


def event(seq=1,position=100.,**changes):return api().normalize_event(mapping(),packet(seq,position,**changes))


def test_opposite_conventions_and_native_precision_are_explicit():
    a=event(position=37.4)
    m=mapping();m['convention']='open_100'
    b=api().normalize_event(m,packet(position=62.6))
    assert a['position_open_pct']==pytest.approx(62.6) and b['position_open_pct']==62.6
    assert a['native_position']==37.4 and a['mapping_sha256']!=b['mapping_sha256']


def test_command_target_is_never_a_position_and_motion_never_satisfies():
    row=event(position=20.,native_target=0.,movement='opening')
    assert row['position_open_pct']==80.
    assert not api().target_observed([row],{'shade-9':80.},now=NOW)
    m=mapping();m['feedback_basis']='travel_time_estimate'
    estimated=api().normalize_event(m,packet(position=0.))
    assert not api().target_observed([estimated],{'shade-9':100.},now=NOW)


def test_fresh_same_valued_acquisition_refreshes_but_held_old_value_does_not(tmp_path):
    store=api().ShadeHistory(tmp_path/'shades.sqlite')
    assert store.ingest(event())=='retained'
    later=NOW+timedelta(seconds=30)
    fresh=event(seq=2,observed_at=later.isoformat(),received_at=later.isoformat(),available_at=later.isoformat())
    assert store.ingest(fresh)=='retained'
    assert store.current(now=later)[0]['observed_at']==later.isoformat()
    old=event(seq=3,received_at=(later+timedelta(seconds=10)).isoformat(),available_at=(later+timedelta(seconds=10)).isoformat())
    assert store.ingest(old)=='out_of_order'
    assert store.current(now=NOW+timedelta(seconds=151))==[]


def test_duplicate_out_of_order_reconnect_and_epoch_replacement(tmp_path):
    store=api().ShadeHistory(tmp_path/'shades.sqlite');a=event();store.ingest(a)
    assert store.ingest(a)=='duplicate'
    changed=deepcopy(a);changed['native_position']=5.
    with pytest.raises(ValueError):store.ingest(changed)
    off=event(seq=2,online=False)
    store.ingest(off);assert store.current(now=NOW)==[]
    m=mapping();m['epoch']='fixture-install-2';m['valid_from']=(NOW+timedelta(seconds=1)).isoformat()
    next_at=NOW+timedelta(seconds=2)
    new=api().normalize_event(m,packet(seq=1,position=0.,observed_at=next_at.isoformat(),received_at=next_at.isoformat(),available_at=next_at.isoformat()))
    store.ingest(new)
    assert store.current(now=next_at)[0]['epoch']=='fixture-install-2'
    assert store.current(now=NOW)[0:]==[] # no future state; prior offline record holds


def test_partial_manual_movement_is_retained_across_restart_with_originals(tmp_path):
    path=tmp_path/'shades.sqlite';store=api().ShadeHistory(path);store.ingest(event())
    for seq,position,movement in ((2,80.,'opening'),(3,62.5,'opening'),(4,62.5,'stopped')):
        at=NOW+timedelta(seconds=seq)
        store.ingest(event(seq,position,movement=movement,origin='manual',observed_at=at.isoformat(),received_at=at.isoformat(),available_at=at.isoformat()))
    episodes=api().ShadeHistory(path).movements()
    assert len(episodes)==1
    assert episodes[0]['from_open_pct']==0. and episodes[0]['to_open_pct']==37.5
    assert len(episodes[0]['event_refs'])==4
    assert episodes[0]['origin']=='manual' and episodes[0]['thermal_benefit_verified'] is False


def test_group_completion_requires_each_fresh_stopped_member():
    one=event(position=0.)
    assert api().target_observed([one],{'shade-9':100.},now=NOW)
    assert not api().target_observed([one],{'shade-9':100.,'shade-10':100.},now=NOW)
    assert not api().target_observed([one],{'shade-9':100.},now=NOW+timedelta(seconds=121))


@pytest.mark.parametrize('damage',['preview','future','extra','out_of_range','bad_mapping'])
def test_invalid_observations_do_not_enter_history(damage):
    m=mapping();p=packet()
    if damage=='preview':m['feedback_basis']='preview'
    elif damage=='future':p['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='extra':p['command']='ON'
    elif damage=='out_of_range':p['native_position']=101.
    else:m['resolution']=0.
    with pytest.raises(ValueError):api().normalize_event(m,p)
