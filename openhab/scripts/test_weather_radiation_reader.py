from datetime import datetime, timedelta, timezone
import json

import pytest

from weather_radiation_evidence import RadiationPolicy, invalid, radiation_receipt
from weather_radiation_reader import select_radiation_at, select_radiation_window

AT = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
POLICY = RadiationPolicy(206)
EPOCH = '00000000-0000-4000-8000-000000000001'


def raw(offset=0, *, sequence=1, faults=0, value=100, version=2, epoch=EPOCH,
        changes=None, record_changes=None):
    at = AT + timedelta(seconds=offset)
    record = radiation_receipt({'model': 'Fineoffset-WH65B', 'id': '206',
        'light_lux': str(value * 126.7), 'solarradiation': str(value),
        'radio_decode_utc': at.strftime('%Y-%m-%d %H:%M:%S')},
        policy=POLICY, stream_epoch=epoch, received_at=at)
    record['sequence'] = sequence
    if record_changes:
        record.update(record_changes)
    envelope = dict(version=version, streamEpoch=epoch, sequence=sequence, record=record)
    if version == 2:
        envelope['faultCount'] = faults
    if changes:
        envelope.update(changes)
    return json.dumps(envelope)


def at(rows, target=60):
    return select_radiation_at(rows, target=AT + timedelta(seconds=target),
        assessed_at=AT + timedelta(seconds=400), history_start=AT - timedelta(seconds=120),
        cutover=AT - timedelta(hours=1), policy=POLICY)


def window(rows, start=0, end=120):
    return select_radiation_window(rows, start=AT + timedelta(seconds=start),
        end=AT + timedelta(seconds=end), assessed_at=AT + timedelta(seconds=400),
        history_start=AT - timedelta(seconds=120), cutover=AT - timedelta(hours=1), policy=POLICY)


def test_original_receipts_and_night_zero_are_qualified_without_future_lookup():
    rows = [(AT, raw(value=0)), (AT + timedelta(seconds=61), raw(61, sequence=2, value=200))]
    result = at(rows)
    assert result['irradianceWm2'] == 0 and result['lightLux'] == 0
    assert result['radioDecodedAt'] == AT and result['validUntil'] == AT + timedelta(seconds=120)
    assert result['fault_visibility'] == 'verified'
    assert at(rows, 120)['irradianceWm2'] == 200
    assert at([(AT, raw())], 120) is None


@pytest.mark.parametrize('bad', [None, 'NULL', '{', 'x' * 8193,
    raw(changes={'version': True}), raw(changes={'sequence': True}),
    raw(changes={'faultCount': -1}), raw(changes={'extra': 0}),
    raw(record_changes={'sensorId': 999}), raw(record_changes={'timeBasis': 'poll'}),
    raw(record_changes={'receivedAt': '2026-10-03T12:00:01Z'}),
    raw(record_changes={'validUntil': '2026-10-03T13:00:00Z'}),
    raw(record_changes={'lightLux': True}), raw(record_changes={'irradianceWm2': 101}),
    raw(record_changes={'conversion': {'luxPerWm2': 127, 'maximumWm2': 1200, 'decimalPlaces': 2}}),
    raw().replace('"version": 2', '"version": 2, "version": 2'),
    raw().replace('12670.0', 'NaN'),
])
def test_bad_rows_are_barriers_not_skipped_candidates(bad):
    rows = [(AT - timedelta(seconds=30), raw(-30)), (AT + timedelta(seconds=20), bad)]
    assert at(rows) is None
    result = window(rows)
    assert result['status'] == 'partial' and result['irradiance_wh_m2'] is None


def test_delay_and_duplicate_restoration_do_not_backfill_or_renew():
    original = raw()
    rows = [(AT + timedelta(seconds=10), original), (AT + timedelta(seconds=100), original)]
    result = window(rows)
    assert result['covered_seconds'] == 110
    assert result['status'] == 'partial'
    assert at(rows, 120) is None


def test_fault_counter_exposes_hidden_invalid_record_without_fabricating_observations():
    rows = [(AT, raw()), (AT + timedelta(seconds=30), raw(30, sequence=3, faults=1)),
            (AT + timedelta(seconds=60), raw(60, sequence=5, faults=1))]
    assert at(rows)['irradianceWm2'] == 100  # New valid source recovers forward only.
    result = window(rows)
    assert 'source_fault' in result['reasons'] and result['status'] == 'partial'
    assert result['covered_seconds'] == 90 and result['irradiance_wh_m2'] is None


def test_valid_downsampling_is_not_a_fault_and_legacy_gaps_are_not_clean():
    rows = [(AT, raw()), (AT + timedelta(seconds=30), raw(30, sequence=3)),
            (AT + timedelta(seconds=60), raw(60, sequence=5)),
            (AT + timedelta(seconds=120), raw(120, sequence=9))]
    result = window(rows)
    assert result['status'] == 'ok' and result['covered_seconds'] == 120
    assert result['irradiance_wh_m2'] == pytest.approx(100 / 30)
    legacy = [(at, json.dumps({k: v for k, v in json.loads(body).items() if k != 'faultCount'}).replace('"version": 2', '"version": 1'))
              for at, body in rows]
    assert at(legacy)['fault_visibility'] == 'unverified'
    assert window(legacy)['status'] == 'partial'


@pytest.mark.parametrize('changes', [
    {'sequence': 0}, {'sequence': 1, 'value': 101},
    {'sequence': 2, 'record_changes': {'radioDecodedAt': '2026-10-03T11:59:59Z'}},
])
def test_sequence_conflict_or_native_time_regression_cannot_recover(changes):
    assert at([(AT, raw()), (AT + timedelta(seconds=30), raw(30, **changes))]) is None


def test_expired_barrier_cannot_be_recovered_by_restored_old_record():
    expired = json.loads(raw())
    expired['faultCount'] = 1
    expired['record'] = invalid(expired['record'], 'expired')
    rows = [(AT, raw()), (AT + timedelta(seconds=20), json.dumps(expired)),
            (AT + timedelta(seconds=30), raw())]
    assert at(rows) is None
    rows.append((AT + timedelta(seconds=40), raw(40, sequence=2, faults=1)))
    assert at(rows)['radioDecodedAt'] == AT + timedelta(seconds=40)


def test_restart_and_counter_regression_never_authorize_a_clean_window():
    other = '00000000-0000-4000-8000-000000000002'
    rows = [(AT, raw()), (AT + timedelta(seconds=30), raw(30, epoch=other))]
    assert at(rows)['streamEpoch'] == other
    assert 'restart' in window(rows)['reasons'] and window(rows)['status'] == 'partial'
    rows = [(AT, raw(sequence=2, faults=1)), (AT + timedelta(seconds=30), raw(30, sequence=3, faults=0))]
    assert at(rows) is None


def test_same_native_record_with_changed_fault_counter_is_a_barrier():
    before = raw(sequence=2)
    after = json.loads(before)
    after['faultCount'] = 1
    assert at([(AT, before), (AT + timedelta(seconds=30), json.dumps(after))]) is None


def test_closed_epoch_cannot_reappear_even_with_newly_claimed_source_time():
    other = '00000000-0000-4000-8000-000000000002'
    rows = [(AT, raw()), (AT + timedelta(seconds=20), raw(20, epoch=other)),
            (AT + timedelta(seconds=30), raw(30, sequence=2))]
    assert at(rows) is None


def test_cutover_future_assessment_bounds_and_conflicting_rows_refuse():
    with pytest.raises(ValueError):
        select_radiation_window([], start=AT, end=AT + timedelta(seconds=60),
            assessed_at=AT, history_start=AT - timedelta(seconds=120), cutover=AT, policy=POLICY)
    assert select_radiation_at([(AT, raw())], target=AT, assessed_at=AT,
        history_start=AT - timedelta(seconds=120), cutover=AT + timedelta(seconds=1), policy=POLICY) is None
    with pytest.raises(ValueError):
        window([(AT, raw()), (AT, raw(value=0))])


def test_exact_end_barrier_invalidates_hidden_fault_interval_before_midnight():
    rows = [(AT, raw()), (AT + timedelta(seconds=120), raw(120, sequence=3, faults=1))]
    assert window(rows)['status'] == 'partial'
    assert window(rows)['covered_seconds'] == 0


def test_post_end_closing_receipt_never_contributes_future_values():
    rows = [(AT, raw()), (AT + timedelta(seconds=130), raw(130, sequence=2, value=1000))]
    result = window(rows)
    assert result['status'] == 'ok' and result['irradiance_wh_m2'] == pytest.approx(100 / 30)
    assert result['observed_high_w_m2'] == 100
    assert window(rows[:1])['irradiance_wh_m2'] is None


def test_many_overlapping_fault_intervals_are_swept_without_double_counting():
    rows = [(AT + timedelta(seconds=16 * i + 2), raw(16 * i, sequence=1 + 2 * i, faults=i))
            for i in range(2001)]
    end = rows[-1][0]
    result = select_radiation_window(rows, start=rows[0][0], end=end, assessed_at=end,
        history_start=AT - timedelta(seconds=120), cutover=AT - timedelta(hours=1), policy=POLICY)
    assert result['status'] == 'partial' and result['covered_seconds'] == 0
    assert result['gap_count'] == 1 and result['maximum_gap_seconds'] == 32000
    assert result['irradiance_wh_m2'] is None
