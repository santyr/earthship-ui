"""Contact duration needs both contact evidence and communication supervision."""
from datetime import datetime, timedelta, timezone

import pytest

from services.lorawan.engine import Engine
from services.lorawan.registry import Registry
from services.lorawan.tests.test_core import NOW, config, packet, setup


def seconds(view):
    return sum(row['observed_seconds'] for row in view['daily_durations'])


def contact(engine, counter=1, at=NOW, **kwargs):
    assert engine.ingest(*packet(counter, at=at, **kwargs), received_at=at) == 'accepted'


def status(engine, counter, offset):
    contact(engine, counter, NOW + timedelta(seconds=offset), data=bytes.fromhex('01755a'))


def test_long_contact_validity_stops_at_communication_expiry(tmp_path):
    engine, store = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    original = store.history()[0]
    view = engine.snapshot(NOW + timedelta(seconds=1000))
    assert view['sensors'][0]['current_state'] == 'UNKNOWN'
    assert seconds(view) == 120
    assert sum(row['open_seconds'] for row in view['daily_durations']) == 120
    assert next(row for row in store.history() if row.get('raw_id'))['observed_at'] == original['observed_at']
    assert next(row for row in store.history() if row.get('raw_id'))['valid_until'] == original['valid_until']


@pytest.mark.parametrize('renewals,at,want', [
    ([100, 200], 1000, 320),  # continuous overlapping communication windows
    ([200], 1000, 240),      # the unsupervised 120..200 gap remains absent
    ([100, 200, 300], 1000, 350),  # communication cannot extend the contact clock
])
def test_status_renewal_intersects_original_contact_clock(tmp_path, renewals, at, want):
    freshness = 350 if renewals == [100, 200, 300] else 3600
    engine, _ = setup(tmp_path, state_stale_seconds=freshness, offline_seconds=7200)
    contact(engine)
    for counter, offset in enumerate(renewals, 2):
        status(engine, counter, offset)
    view = engine.snapshot(NOW + timedelta(seconds=at))
    assert seconds(view) == want
    assert view['sensors'][0]['last_observed_at'] == NOW.isoformat()
    assert view['sensors'][0]['valid_until'] == (NOW + timedelta(seconds=freshness)).isoformat()


@pytest.mark.parametrize('fault', ['invalid_payload', 'joined', 'counter_conflict', 'counter_regression'])
def test_status_after_fault_cannot_restore_previous_contact_duration(tmp_path, fault):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine, 10)
    at = NOW + timedelta(seconds=30)
    kwargs = dict(data=b'bad') if fault == 'invalid_payload' else dict(event='join') if fault == 'joined' else {}
    counter = 10 if fault == 'counter_conflict' else 1 if fault == 'counter_regression' else 11
    assert engine.ingest(*packet(counter, state=0, at=at, **kwargs), received_at=at) == fault
    status(engine, 11 if fault.startswith('counter_') else 12, 50)
    assert engine.snapshot(NOW + timedelta(seconds=50))['sensors'][0]['current_state'] == 'UNKNOWN'
    view = engine.snapshot(NOW + timedelta(seconds=1000))
    assert view['sensors'][0]['current_state'] == 'UNKNOWN'
    assert seconds(view) == 30


def test_contact_recovery_after_invalid_payload_starts_a_new_supervised_interval(tmp_path):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    at = NOW + timedelta(seconds=30)
    assert engine.ingest(*packet(2, at=at, data=b'bad'), received_at=at) == 'invalid_payload'
    contact(engine, 3, NOW + timedelta(seconds=100))
    assert seconds(engine.snapshot(NOW + timedelta(seconds=1000))) == 150


def test_missing_frames_status_barrier_is_not_reopened_by_renewal(tmp_path):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    status(engine, 3, 50)
    status(engine, 4, 100)
    assert seconds(engine.snapshot(NOW + timedelta(seconds=1000))) == 0
    contact(engine, 5, NOW + timedelta(seconds=200))
    assert seconds(engine.snapshot(NOW + timedelta(seconds=1000))) == 120


def test_rejoin_starts_new_epoch_and_status_cannot_bridge_to_old_contact(tmp_path):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    at = NOW + timedelta(seconds=30)
    assert engine.ingest(*packet(at=at, event='join'), received_at=at) == 'joined'
    status(engine, 1, 50)
    contact(engine, 2, NOW + timedelta(seconds=100))
    view = engine.snapshot(NOW + timedelta(seconds=1000))
    assert seconds(view) == 150
    assert view['sensors'][0]['source_epoch'] != next(row['source_epoch'] for row in engine.store.history() if row.get('frame_counter') == 1 and row.get('contact_state') == 'OPEN')


def test_hardware_epoch_replacement_excludes_previous_duration_and_coverage(tmp_path):
    engine, store = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    replacement = Engine(Registry(config(state_stale_seconds=3600, offline_seconds=7200,
        hardware_epoch='33333333-3333-4333-8333-333333333333')), store)
    status(replacement, 1, 50)
    assert seconds(replacement.snapshot(NOW + timedelta(seconds=1000))) == 0
    contact(replacement, 2, NOW + timedelta(seconds=100))
    assert seconds(replacement.snapshot(NOW + timedelta(seconds=1000))) == 120


@pytest.mark.parametrize('start,end,expected', [
    ('2026-10-20T05:59:30+00:00', '2026-10-20T06:02:30+00:00', {'2026-10-19': 30, '2026-10-20': 90}),
    # Entire Denver civil days across both clock changes have 23 and 25 hours.
    ('2026-03-08T07:00:00+00:00', '2026-03-09T07:00:00+00:00', {'2026-03-08': 82800, '2026-03-09': 3600}),
    ('2026-11-01T06:00:00+00:00', '2026-11-02T08:00:00+00:00', {'2026-11-01': 90000, '2026-11-02': 3600}),
])
def test_communication_coverage_splits_at_denver_midnight_and_dst(tmp_path, start, end, expected):
    start, end = datetime.fromisoformat(start), datetime.fromisoformat(end)
    duration = int((end-start).total_seconds())
    communication = 120 if duration == 180 else duration
    engine, _ = setup(tmp_path, state_stale_seconds=duration+1000,
        communication_stale_seconds=communication, offline_seconds=duration+2000)
    contact(engine, at=start)
    rows = engine.snapshot(end)['daily_durations']
    assert {row['date']: row['observed_seconds'] for row in rows} == expected
    assert all(row['open_seconds'] == row['observed_seconds'] for row in rows)


def test_delayed_receipt_does_not_invent_communication_before_first_receipt(tmp_path):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    received = NOW + timedelta(seconds=60)
    assert engine.ingest(*packet(at=NOW), received_at=received) == 'accepted'
    assert seconds(engine.snapshot(NOW + timedelta(seconds=1000))) == 120


def test_contact_recovery_at_same_timestamp_as_fault_uses_journal_order(tmp_path):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    at = NOW + timedelta(seconds=30)
    assert engine.ingest(*packet(2, at=at, data=b'bad'), received_at=at) == 'invalid_payload'
    contact(engine, 3, at)
    assert engine.snapshot(at)['sensors'][0]['current_state'] == 'OPEN'
    assert seconds(engine.snapshot(NOW + timedelta(seconds=1000))) == 150


def test_device_clock_contact_received_after_fault_restores_supervision_at_receipt(tmp_path):
    engine, _ = setup(tmp_path, decoder='dragino_ds03a_lb/v1', state_stale_seconds=3600, offline_seconds=7200)
    def reading(offset):
        return bytes.fromhex('01000001000025') + int((NOW + timedelta(seconds=offset)).timestamp()).to_bytes(4, 'big')
    contact(engine, data=reading(0), port=2)
    bad = NOW + timedelta(seconds=30)
    assert engine.ingest(*packet(2, at=bad, data=b'bad', port=2), received_at=bad) == 'invalid_payload'
    received = NOW + timedelta(seconds=100)
    assert engine.ingest(*packet(3, at=received, data=reading(20), port=2), received_at=received) == 'accepted'
    assert engine.snapshot(received)['sensors'][0]['current_state'] == 'OPEN'
    # Original evidence ends at the next contact's source time (20 seconds);
    # new supervision starts at receipt (100..220), preserving both clocks.
    assert seconds(engine.snapshot(NOW + timedelta(seconds=1000))) == 140


def test_archived_datalog_renews_communication_at_receipt_without_renewing_contact(tmp_path):
    engine, _ = setup(tmp_path, decoder='dragino_ds03a_lb/v1', state_stale_seconds=350, offline_seconds=7200)
    reading = bytes.fromhex('01000001000025') + int(NOW.timestamp()).to_bytes(4, 'big')
    contact(engine, data=reading, port=2)
    received = NOW + timedelta(seconds=100)
    archived = bytes.fromhex('80000001000025') + int((NOW-timedelta(seconds=100)).timestamp()).to_bytes(4, 'big')
    assert engine.ingest(*packet(2, at=received, data=archived, port=3), received_at=received) == 'accepted'
    view = engine.snapshot(NOW + timedelta(seconds=1000))
    assert seconds(view) == 220
    assert view['sensors'][0]['last_observed_at'] == NOW.isoformat()
    assert view['sensors'][0]['valid_until'] == (NOW + timedelta(seconds=350)).isoformat()


def test_missing_frame_barrier_censors_old_evidence_but_not_recovery_packet(tmp_path):
    engine, _ = setup(tmp_path, state_stale_seconds=3600, offline_seconds=7200)
    contact(engine)
    contact(engine, 3, NOW, state=0)
    view = engine.snapshot(NOW + timedelta(seconds=1000))
    assert seconds(view) == 120
    assert sum(row['open_seconds'] for row in view['daily_durations']) == 0
