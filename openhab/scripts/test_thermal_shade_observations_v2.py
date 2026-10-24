"""Synthetic adapter-v2 receipt histories; no producer, model, or actuator IO."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json

import pytest

try:
    from thermal_model import shade_observations_v2 as v2
except ImportError:
    v2 = None

T = datetime(2026, 10, 24, 18, tzinfo=timezone.utc)
SESSION = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
EPOCH = '11111111-1111-4111-8111-111111111111'
BRIDGE = 'AABBCCDDEEFF'
DEVICE = '0000000000000001'
PROFILE = {'schema': 'earthship-dooya-observation-profile/v2', 'shade_id': 'shade-01',
           'bridge_id': BRIDGE, 'device_id': DEVICE, 'commissioned_epoch': EPOCH,
           'commissioning_ref': 'synthetic-commissioning-record-only'}
PROFILE['source_identity_sha256'] = hashlib.sha256(json.dumps(
    {key: PROFILE[key] for key in ('bridge_id', 'device_id', 'commissioned_epoch')},
    sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def state(at=T, position=25, stamp='20261024180000000', session=SESSION, generation=1, **changes):
    observation = {'id': f'{session}:{generation}:{stamp}', 'received_at': at.timestamp(),
        'validated_at': at.timestamp(), 'received_monotonic': 100.0,
        'upstream_message_id': stamp, 'measurement_time_known': False, 'hardware_boot_known': False,
        'ordering_contract': 'working_calendar_msg_id', 'freshness_basis': 'validated_unique_report_receipt',
        'delayed_delivery_excluded': False, 'origin': 'unknown', 'adapter_session_id': session,
        'source_generation': generation, 'bridge_id': BRIDGE, 'device_id': DEVICE,
        'device_type': '10000000', 'commissioned_epoch': EPOCH,
        'source_identity_sha256': PROFILE['source_identity_sha256']}
    result = {'schema_version': 2, 'source': 'motor_report', 'reported_position': position,
        'report_received_at': at.timestamp(), 'current_position': position, 'usable': True,
        'stale': False, 'action_qualified': False, 'movement_state': 'stationary_reported',
        'requested_target': None, 'report': {'currentPosition': position, 'wirelessMode': 1, 'type': 1},
        'cache': {}, 'observation': observation, 'adapter_session_id': session,
        'source_generation': generation,
        'usable_interval': {'clock': 'adapter_monotonic', 'start': 100.0, 'end': 1900.0}}
    result.update(changes)
    return result


def service(at=T, session=SESSION, generation=1, **changes):
    return {'schema_version': 2, 'adapter_session_id': session, 'source_generation': generation,
            'ready': True, 'emitted_at': at.timestamp(), 'automatic_released': False,
            'receipt_journal_healthy': True, **changes}


def bridge(at=T, session=SESSION, generation=1, **changes):
    return {'schema_version': 2, 'adapter_session_id': session, 'source_generation': generation,
            'bridge_id': BRIDGE, 'reachable': True, 'emitted_at': at.timestamp(), **changes}


def joined(at=T, diagnostic=None, **changes):
    return {'stored_at': at, 'diagnostic_state': json.dumps(state() if diagnostic is None else diagnostic),
        'availability': 'ON', 'scalar_position': '25', 'service_availability': 'ON',
        'bridge_availability': 'ON', 'service_state': json.dumps(service()),
        'bridge_state': json.dumps(bridge()), 'provider_status': 'ONLINE',
        'diagnostic_reconciled': True, **changes}


def read(rows, *, end=T + timedelta(seconds=60), profile=None):
    assert v2 is not None, 'New separate v2 observation reader required'
    return v2.qualified_shade_intervals_v2(rows, profile=PROFILE if profile is None else profile,
        start=T, end=end, as_of=end)


def test_separate_v2_module_exists_without_replacing_original():
    assert v2 is not None, 'New separate v2 observation reader required'
    assert importlib.util.find_spec('thermal_model.shade_observations')


@pytest.mark.parametrize('position', [0, 25, 50, 75, 100])
def test_partial_individual_positions_keep_original_provenance_without_action_qualification(position):
    history = read([joined(diagnostic=state(position=position), scalar_position=str(position))])
    assert len(history.intervals) == 1 and len(history.observations) == 1
    interval = history.intervals[0]
    assert (interval.start, interval.end, interval.percent_closed, interval.percent_open) == (
        T, T + timedelta(seconds=60), position, 100-position)
    original = history.observations[0]
    assert original.received_at == T and original.validated_at == T
    assert original.upstream_message_id == '20261024180000000'
    assert original.commissioned_epoch == EPOCH
    assert original.source_identity_sha256 == PROFILE['source_identity_sha256']
    assert original.commissioning_ref == PROFILE['commissioning_ref']
    assert original.actor == 'unknown' and not original.measurement_time_known
    assert not original.hardware_boot_known and not original.action_qualified
    assert history.schema == 'earthship-dooya-observation-history/v2'
    assert history.qualification_scope == 'received_report_continuity_only'
    assert not history.action_qualified and not history.preference_qualified


@pytest.mark.parametrize('changes', [{'availability': 'OFF'}, {'service_availability': 'OFF'},
    {'bridge_availability': 'OFF'}, {'provider_status': None}, {'provider_status': 'OFFLINE'},
    {'scalar_position': '26'}, {'diagnostic_reconciled': False},
    {'service_state': json.dumps(service(ready=False))},
    {'bridge_state': json.dumps(bridge(reachable=False))},
    {'service_state': json.dumps(service(session='different-session'))},
    {'bridge_state': json.dumps(bridge(generation=2))},
    {'bridge_state': json.dumps(bridge(bridge_id='FFEEDDCCBBAA'))}])
def test_composite_liveness_and_session_fail_closed_while_history_stays_original(changes):
    history = read([joined(**changes)])
    assert not history.intervals
    assert history.observations[0].percent_closed == 25
    assert history.observations[0].received_at == T


@pytest.mark.parametrize('path,value', [
    (('schema_version',), 1), (('reported_position',), True), (('source',), 'bridge_cache'),
    (('observation','source_identity_sha256'), '0'*64),
    (('observation','commissioned_epoch'), '22222222-2222-4222-8222-222222222222'),
    (('observation','device_id'), '0000000000000002'),
    (('observation','origin'), 'manual'), (('observation','measurement_time_known'), True),
    (('observation','received_at'), T.timestamp()+1),
    (('observation','upstream_message_id'), 'opaque-id'),
    (('observation','received_monotonic'), float('nan'))])
def test_wrong_or_malformed_identity_never_becomes_v2_observation(path, value):
    diagnostic = state()
    target = diagnostic
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    history = read([joined(diagnostic=diagnostic)])
    assert not history.observations and not history.intervals


def test_stale_or_moving_snapshot_retains_last_known_observation_only():
    history = read([joined(diagnostic=state(usable=False, stale=True, current_position=None,
                                         movement_state='uncertain', requested_target=100))])
    assert not history.intervals
    assert history.observations[0].percent_closed == 25
    assert history.observations[0].received_at == T


def test_duplicate_new_publication_clock_never_extends_original_usable_interval():
    initial = state()
    initial['usable_interval']['end'] = 110.0
    duplicate = deepcopy(initial)
    duplicate['usable_interval']['end'] = 1900.0
    rows = [joined(diagnostic=initial), joined(T+timedelta(seconds=5), diagnostic=duplicate,
        service_state=json.dumps(service(T+timedelta(seconds=5))),
        bridge_state=json.dumps(bridge(T+timedelta(seconds=5))))]
    history = read(rows)
    assert len(history.observations) == 1
    assert history.intervals[-1].end == T+timedelta(seconds=10)


def test_offline_then_duplicate_cannot_restore_receipt_freshness():
    rows = [joined(), joined(T+timedelta(seconds=5), availability='OFF'),
            joined(T+timedelta(seconds=10))]
    history = read(rows)
    assert [(part.start,part.end) for part in history.intervals] == [(T,T+timedelta(seconds=5))]
    assert len(history.observations) == 1


def test_health_expiry_closes_interval_and_new_health_cannot_revive_old_report():
    rows = [joined(), joined(T+timedelta(seconds=100),
        service_state=json.dumps(service(T+timedelta(seconds=100))),
        bridge_state=json.dumps(bridge(T+timedelta(seconds=100))))]
    history = read(rows, end=T+timedelta(seconds=150))
    assert [(part.start,part.end) for part in history.intervals] == [(T,T+timedelta(seconds=90))]


def test_out_of_order_report_does_not_retimestamp_or_reopen_position():
    later = state(T+timedelta(seconds=5), 75, '20261024175959000')
    history = read([joined(), joined(T+timedelta(seconds=5), diagnostic=later, scalar_position='75')])
    assert len(history.observations) == 1
    assert history.intervals[-1].end == T+timedelta(seconds=5)


def test_same_observation_identifier_cannot_change_position_or_timestamps():
    changed = state(position=75)
    history = read([joined(), joined(T+timedelta(seconds=5), diagnostic=changed, scalar_position='75')])
    assert len(history.observations) == 1 and history.observations[0].percent_closed == 25
    assert history.intervals[-1].end == T+timedelta(seconds=5)


def test_missing_provider_role_or_policy_inputs_are_not_silently_substituted():
    assert v2 is not None
    streams = {key: [] for key in v2.ITEM_ROLES}
    streams.pop('provider_status')
    with pytest.raises(ValueError): v2.join_change_only_shade_rows_v2(streams,start=T,end=T+timedelta(seconds=60))
    # Observation acquisition has no automation preference or OverrideSwitch input.
    with pytest.raises(TypeError):
        v2.qualified_shade_intervals_v2([joined()],profile=PROFILE,start=T,
            end=T+timedelta(seconds=60),as_of=T+timedelta(seconds=60),zone_preference=False)


def test_change_only_join_keeps_ties_and_online_transition_as_barriers():
    assert v2 is not None
    carry = T-timedelta(seconds=1)
    values = joined()
    streams = {key:[{'stored_at':carry,'state':values[key]}] for key in v2.ITEM_ROLES}
    streams['diagnostic_state'] = [{'stored_at':T+timedelta(seconds=2),'state':json.dumps(state())}]
    streams['scalar_position'] = [{'stored_at':T+timedelta(seconds=2),'state':'25'}]
    rows = v2.join_change_only_shade_rows_v2(streams,start=T,end=T+timedelta(seconds=60))
    assert not read(rows).intervals
    streams['diagnostic_state'].append({'stored_at':T+timedelta(seconds=3),'state':json.dumps(state())})
    history = read(v2.join_change_only_shade_rows_v2(streams,start=T,end=T+timedelta(seconds=60)))
    assert history.intervals[0].start == T+timedelta(seconds=3)


def test_closed_window_bounds_and_duplicate_timestamps_refuse_whole_read():
    for rows in ([joined(),joined()], [joined(T+timedelta(seconds=60))], [joined()]*10001):
        with pytest.raises(ValueError): read(rows)
    with pytest.raises(ValueError): read([joined()], end=T+timedelta(days=3))
    assert v2 is not None
    with pytest.raises(ValueError):
        v2.qualified_shade_intervals_v2([],profile=PROFILE,start=T,end=T+timedelta(seconds=60),as_of=T)


@pytest.mark.parametrize('changes', [
    {'bridge_state':json.dumps(bridge(generation=True))},
    {'service_state':json.dumps(service(emitted_at=True))},
    {'service_state':json.dumps(service(T-timedelta(seconds=91)))},
    {'bridge_state':json.dumps(bridge(T+timedelta(seconds=6)))},
])
def test_malformed_or_expired_health_is_never_current(changes):
    history=read([joined(**changes)])
    assert not history.intervals
    assert len(history.observations)==1


def test_duplicate_json_keys_nonfinite_unknown_fields_and_deep_input_are_barriers():
    duplicate=json.dumps(state()).replace('"schema_version": 2','"schema_version": 1, "schema_version": 2')
    deep={'level':0}
    for _ in range(20): deep={'next':deep}
    for raw in (duplicate,json.dumps(state(unknown=float('nan'))),json.dumps(state(unknown=deep))):
        history=read([joined(diagnostic_state=raw)])
        assert not history.observations and not history.intervals


def test_original_v1_reader_never_accepts_new_v2_schema():
    from thermal_model.shade_observations import qualified_shade_intervals
    original_rows=[{'stored_at':T,'diagnostic_state':json.dumps(state()),
                    'availability':True,'scalar_position':'25'}]
    assert qualified_shade_intervals(original_rows,start=T,end=T+timedelta(seconds=60))==()


def test_previous_session_last_known_observation_cannot_be_republished_as_current():
    diagnostic=state(adapter_session_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    history=read([joined(diagnostic=diagnostic)])
    assert history.observations[0].adapter_session_id==SESSION
    assert not history.intervals


def test_shorter_original_interval_claim_stays_visible_at_its_storage_boundary():
    initial=state()
    initial['usable_interval']['end']=130.0
    shorter=deepcopy(initial)
    shorter['usable_interval']['end']=110.0
    history=read([joined(diagnostic=initial),joined(T+timedelta(seconds=5),diagnostic=shorter)])
    assert [(part.start,part.end,part.original_receipt_usable_until) for part in history.intervals]==[
        (T,T+timedelta(seconds=5),T+timedelta(seconds=30)),
        (T+timedelta(seconds=5),T+timedelta(seconds=10),T+timedelta(seconds=10))]
