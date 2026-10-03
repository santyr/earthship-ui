from datetime import timedelta
import random

import pytest

import weather_radiation_reader as reader
from test_weather_radiation_reader import AT, EPOCH, POLICY, raw


def grid(rows, seconds=(0, 30, 60, 120), **overrides):
    kwargs = dict(targets=[AT + timedelta(seconds=x) for x in seconds],
                  assessed_at=AT + timedelta(hours=25),
                  history_start=AT - timedelta(seconds=120),
                  cutover=AT - timedelta(hours=1), policy=POLICY)
    return reader.select_radiation_grid(rows, **{**kwargs, **overrides})


def test_grid_uses_native_receipts_and_preserves_original_expiry_and_hash():
    rows = [(AT, raw(value=0)), (AT + timedelta(seconds=60), raw(60, sequence=2))]
    result = grid(rows)
    assert [None if value is None else value['irradianceWm2'] for _, value in result] == [0, 0, 100, 100]
    assert result[1][1]['receivedAt'] == AT
    assert result[1][1]['validUntil'] == AT + timedelta(seconds=120)
    assert result[1][1]['snapshotSha256'] == result[0][1]['snapshotSha256']
    assert grid(rows, seconds=(180,))[0][1] is None


def test_future_native_values_are_not_backdated_and_legacy_is_not_qualified():
    rows = [(AT + timedelta(seconds=10), raw()),
            (AT + timedelta(seconds=61), raw(61, sequence=2, value=500))]
    assert [None if value is None else value['irradianceWm2']
            for _, value in grid(rows, seconds=(0, 10, 60, 61))] == [None, 100, 100, 500]
    assert all(value is None for _, value in grid([(AT, raw(version=1))]))


def test_malformed_barrier_and_restored_original_cannot_recover():
    rows = [(AT, raw()), (AT + timedelta(seconds=20), '{'),
            (AT + timedelta(seconds=30), raw()),
            (AT + timedelta(seconds=60), raw(60, sequence=2))]
    values = [value for _, value in grid(rows)]
    assert values[0] is not None and values[1] is None
    assert values[2]['radioDecodedAt'] == AT + timedelta(seconds=60)


def test_legacy_snapshot_is_a_grid_barrier_until_a_genuinely_new_v2_receipt():
    rows = [(AT, raw()), (AT + timedelta(seconds=20), raw(20, sequence=2, version=1)),
            (AT + timedelta(seconds=30), raw(20, sequence=2)),
            (AT + timedelta(seconds=60), raw(60, sequence=3))]
    values = [value for _, value in grid(rows, seconds=(0, 20, 30, 60))]
    assert values[0] is not None and values[1:3] == [None, None]
    assert values[3]['radioDecodedAt'] == AT + timedelta(seconds=60)


def test_hidden_faults_do_not_rewrite_as_of_points_or_prove_a_clean_day():
    rows = [(AT, raw()), (AT + timedelta(seconds=30), raw(30, sequence=3, faults=1))]
    assert all(value is not None for _, value in grid(rows, seconds=(0, 20, 30)))
    window = reader.select_radiation_window(rows, start=AT, end=AT + timedelta(seconds=30),
        assessed_at=AT + timedelta(seconds=30), history_start=AT - timedelta(seconds=120),
        cutover=AT - timedelta(hours=1), policy=POLICY)
    assert window['status'] == 'partial' and window['irradiance_wh_m2'] is None


def test_closed_epoch_and_counter_regression_remain_barriers():
    other = '00000000-0000-4000-8000-000000000002'
    rows = [(AT, raw()), (AT + timedelta(seconds=20), raw(20, epoch=other)),
            (AT + timedelta(seconds=30), raw(30, sequence=2, epoch=EPOCH))]
    assert grid(rows, seconds=(30,))[0][1] is None
    rows = [(AT, raw(sequence=2, faults=1)),
            (AT + timedelta(seconds=30), raw(30, sequence=3, faults=0))]
    assert grid(rows, seconds=(30,))[0][1] is None


def test_cutover_applies_to_persisted_receiver_and_decoder_clocks():
    rows = [(AT, raw())]
    assert grid(rows, seconds=(1,), cutover=AT + timedelta(seconds=1))[0][1] is None


@pytest.mark.parametrize('targets', [[], [AT, AT], [AT, AT - timedelta(seconds=1)],
    [AT.replace(tzinfo=None)], [AT + timedelta(hours=26)], [AT] * 302])
def test_bad_target_grid_refuses(targets):
    with pytest.raises(ValueError): grid([], targets=targets)


def test_missing_original_carry_or_excess_span_refuses():
    with pytest.raises(ValueError): grid([], history_start=AT)
    with pytest.raises(ValueError): grid([], targets=[AT, AT + timedelta(hours=25, seconds=1)],
                                         assessed_at=AT + timedelta(hours=26))
    with pytest.raises(ValueError): grid([(AT, raw()), (AT, raw(value=0))])


def test_one_pass_parses_each_snapshot_once_over_a_maximum_dst_day(monkeypatch):
    rows = [(AT + timedelta(seconds=30*i), raw(30*i, sequence=i+1)) for i in range(3001)]
    original, calls = reader._snapshot, []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(reader, '_snapshot', counted)
    result = grid(rows, seconds=tuple(300*i for i in range(301)))
    assert len(result) == 301 and all(value is not None for _, value in result)
    assert len(calls) == len(rows)


def test_v2_grid_matches_unchanged_point_engine_across_deterministic_fault_histories():
    rng = random.Random(206)
    for _ in range(50):
        rows, faults = [], 0
        for index in range(24):
            choice = rng.random()
            if choice < .2:
                faults += 1
                body = rng.choice([None, '{', 'NULL'])
            elif choice < .35 and rows:
                body = rng.choice(rows)[1]
            else:
                body = raw(index*30, sequence=index+1, faults=faults,
                           value=rng.randrange(601))
            rows.append((AT + timedelta(seconds=index*30), body))
        targets = tuple(range(0, 751, 10))
        result = grid(rows, seconds=targets)
        expected = [(target, reader.select_radiation_at(rows, target=target,
            assessed_at=AT + timedelta(hours=25), history_start=AT - timedelta(seconds=120),
            cutover=AT - timedelta(hours=1), policy=POLICY)) for target, _ in result]
        assert result == expected
