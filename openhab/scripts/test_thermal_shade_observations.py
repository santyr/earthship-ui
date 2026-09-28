from datetime import datetime, timedelta, timezone
import json

import pytest

from thermal_model.shade_observations import (MAX_ROWS, join_change_only_shade_rows,
                                              qualified_shade_intervals)


T = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)


def row(stored, position=0, *, received=None, available=True, source='motor_report',
        stale=False, scalar=None):
    report = dict(schema_version=1, reported_position=position,
                  report_received_at=(received or stored).timestamp(),
                  stale=stale, source=source, report={}, cache={})
    return dict(stored_at=stored, diagnostic_state=json.dumps(report),
                availability=available,
                scalar_position=str(position) if scalar is None else scalar)


def change(stored, state):
    return dict(stored_at=stored, state=state)


def diagnostic(stored, position, *, received=None):
    return change(stored, row(stored, position, received=received)['diagnostic_state'])


def test_percent_open_intervals_follow_motor_receipts_and_offline_barriers():
    rows = [
        row(T + timedelta(minutes=1), 0, received=T),
        row(T + timedelta(minutes=10), 0, received=T),  # same receipt, not a refresh
        row(T + timedelta(minutes=16), 25, received=T + timedelta(minutes=15)),
        row(T + timedelta(minutes=30), 25, received=T + timedelta(minutes=15)),
        row(T + timedelta(minutes=40), 25, available=False),
        row(T + timedelta(minutes=41), 25, received=T + timedelta(minutes=15)),
    ]
    intervals = qualified_shade_intervals(rows, start=T, end=T + timedelta(minutes=50))
    assert [(part.start, part.end, part.percent_closed, part.percent_open) for part in intervals] == [
        (T + timedelta(minutes=1), T + timedelta(minutes=16), 0, 100),
        (T + timedelta(minutes=16), T + timedelta(minutes=40), 25, 75),
    ]


def test_old_report_expires_without_new_motor_report():
    rows = [row(T + timedelta(minutes=1), 100, received=T),
            row(T + timedelta(minutes=20), 100, received=T)]
    intervals = qualified_shade_intervals(rows, start=T, end=T + timedelta(hours=1))
    assert len(intervals) == 1
    assert intervals[0].end == T + timedelta(minutes=30)
    assert intervals[0].percent_open == 0


def test_pre_window_carry_is_bounded_and_future_rows_do_not_rewrite_origin():
    rows = [row(T + timedelta(minutes=1), 0, received=T),
            row(T + timedelta(minutes=20), 100, received=T + timedelta(minutes=20))]
    intervals = qualified_shade_intervals(rows, start=T + timedelta(minutes=10),
                                          end=T + timedelta(minutes=15))
    assert len(intervals) == 1
    assert (intervals[0].start, intervals[0].end, intervals[0].percent_open) == (
        T + timedelta(minutes=10), T + timedelta(minutes=15), 100)


@pytest.mark.parametrize('change', [
    {'source': 'bridge_cache'}, {'stale': True}, {'available': False},
    {'available': None}, {'scalar': '100'},
])
def test_cache_stale_offline_unknown_and_scalar_disagreement_are_barriers(change):
    valid = row(T + timedelta(minutes=1), 0, received=T)
    invalid = row(T + timedelta(minutes=5), 0, received=T + timedelta(minutes=5), **change)
    intervals = qualified_shade_intervals([valid, invalid], start=T,
                                          end=T + timedelta(minutes=20))
    assert len(intervals) == 1
    assert intervals[0].end == T + timedelta(minutes=5)


def test_future_source_clock_skew_cannot_create_pre_report_interval():
    rows = [row(T + timedelta(minutes=1), 0, received=T + timedelta(minutes=1, seconds=30))]
    intervals = qualified_shade_intervals(rows, start=T, end=T + timedelta(minutes=5))
    assert intervals[0].start == T + timedelta(minutes=1, seconds=30)


def test_older_motor_timestamp_does_not_resurrect_position():
    rows = [row(T + timedelta(minutes=5), 0, received=T + timedelta(minutes=5)),
            row(T + timedelta(minutes=10), 100, received=T + timedelta(minutes=4))]
    intervals = qualified_shade_intervals(rows, start=T, end=T + timedelta(minutes=20))
    assert len(intervals) == 1
    assert intervals[0].end == T + timedelta(minutes=10)


def test_malformed_and_out_of_order_rows_fail_closed():
    malformed = row(T + timedelta(minutes=1))
    malformed['diagnostic_state'] = '{'
    assert qualified_shade_intervals([malformed], start=T, end=T + timedelta(minutes=5)) == ()
    with pytest.raises(ValueError, match='strictly ordered'):
        qualified_shade_intervals([row(T + timedelta(minutes=2)), row(T + timedelta(minutes=1))],
                                  start=T, end=T + timedelta(minutes=5))
    with pytest.raises(ValueError, match='row bound'):
        qualified_shade_intervals([row(T + timedelta(minutes=1))] * (MAX_ROWS + 1),
                                  start=T, end=T + timedelta(minutes=5))


def test_unbounded_input_is_stopped_after_one_over_limit_row():
    seen = []
    def stream():
        for index in range(MAX_ROWS + 100):
            seen.append(index)
            yield row(T + timedelta(minutes=1))
    with pytest.raises(ValueError, match='row bound'):
        qualified_shade_intervals(stream(), start=T, end=T + timedelta(minutes=5))
    assert len(seen) == MAX_ROWS + 1


def test_change_only_join_waits_for_all_three_persisted_values_and_never_backdates():
    joined = join_change_only_shade_rows(
        [diagnostic(T + timedelta(seconds=2), 25),
         diagnostic(T + timedelta(seconds=4), 50)],
        [change(T, 'ON')],
        [change(T + timedelta(seconds=1), '25'),
         change(T + timedelta(seconds=5), '50')],
        start=T, end=T + timedelta(seconds=10),
    )
    intervals = qualified_shade_intervals(joined, start=T, end=T + timedelta(seconds=10))
    assert [(part.start, part.end, part.percent_open) for part in intervals] == [
        (T + timedelta(seconds=2), T + timedelta(seconds=4), 75),
        (T + timedelta(seconds=5), T + timedelta(seconds=10), 50),
    ]


def test_change_only_join_offline_and_return_to_on_require_a_later_diagnostic():
    joined = join_change_only_shade_rows(
        [diagnostic(T + timedelta(seconds=2), 25),
         diagnostic(T + timedelta(seconds=5), 25, received=T + timedelta(seconds=2)),
         diagnostic(T + timedelta(seconds=6), 0)],
        [change(T, 'ON'), change(T + timedelta(seconds=3), 'OFF'),
         change(T + timedelta(seconds=4), 'ON')],
        [change(T + timedelta(seconds=1), '25'), change(T + timedelta(seconds=6, milliseconds=500), '0')],
        start=T, end=T + timedelta(seconds=10),
    )
    intervals = qualified_shade_intervals(joined, start=T, end=T + timedelta(seconds=10))
    assert [(part.start, part.end, part.percent_open) for part in intervals] == [
        (T + timedelta(seconds=2), T + timedelta(seconds=3), 75),
        (T + timedelta(seconds=6, milliseconds=500), T + timedelta(seconds=10), 100),
    ]


def test_cross_item_timestamp_tie_is_a_barrier_until_a_later_diagnostic():
    joined = join_change_only_shade_rows(
        [diagnostic(T, 25), diagnostic(T + timedelta(seconds=2), 25)],
        [change(T, 'ON')],
        [change(T, '25'), change(T + timedelta(seconds=1), '25')],
        start=T, end=T + timedelta(seconds=5),
    )
    assert joined[0]['availability'] is False
    assert joined[1]['availability'] is False
    intervals = qualified_shade_intervals(joined, start=T, end=T + timedelta(seconds=5))
    assert [(part.start, part.percent_open) for part in intervals] == [
        (T + timedelta(seconds=2), 75),
    ]


def test_change_only_join_preserves_one_pre_window_carry_per_item():
    joined = join_change_only_shade_rows(
        [diagnostic(T - timedelta(seconds=10), 25)],
        [change(T - timedelta(seconds=30), 'ON')],
        [change(T - timedelta(seconds=20), '25')],
        start=T, end=T + timedelta(seconds=10),
    )
    intervals = qualified_shade_intervals(joined, start=T, end=T + timedelta(seconds=10))
    assert len(intervals) == 1
    assert (intervals[0].start, intervals[0].end, intervals[0].percent_open) == (
        T, T + timedelta(seconds=10), 75)


def test_change_only_join_refuses_future_duplicates_excess_carry_and_unbounded_input():
    with pytest.raises(ValueError, match='future'):
        join_change_only_shade_rows([diagnostic(T + timedelta(seconds=10), 25)], [], [],
                                    start=T, end=T + timedelta(seconds=10))
    with pytest.raises(ValueError, match='strictly ordered'):
        join_change_only_shade_rows([diagnostic(T, 25), diagnostic(T, 25)], [], [],
                                    start=T, end=T + timedelta(seconds=10))
    with pytest.raises(ValueError, match='pre-window carry'):
        join_change_only_shade_rows([diagnostic(T - timedelta(seconds=2), 25),
                                     diagnostic(T - timedelta(seconds=1), 25)], [], [],
                                    start=T, end=T + timedelta(seconds=10))
    seen = []
    def stream():
        for index in range(MAX_ROWS + 100):
            seen.append(index)
            yield change(T + timedelta(microseconds=index), 'ON')
    with pytest.raises(ValueError, match='row bound'):
        join_change_only_shade_rows([], stream(), [], start=T, end=T + timedelta(seconds=10))
    assert len(seen) == MAX_ROWS + 1
