from datetime import datetime, timedelta, timezone
import json

import pytest

from thermal_model.shade_observations import MAX_ROWS, qualified_shade_intervals


T = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)


def row(stored, position=0, *, received=None, available=True, source='motor_report',
        stale=False, scalar=None):
    report = dict(schema_version=1, reported_position=position,
                  report_received_at=(received or stored).timestamp(),
                  stale=stale, source=source, report={}, cache={})
    return dict(stored_at=stored, diagnostic_state=json.dumps(report),
                availability=available,
                scalar_position=str(position) if scalar is None else scalar)


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
