"""Exact interval evidence, not regularly sampled daily extrema."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from test_weather_temperature_reader import AT, POLICY, raw
from weather_temperature_reader import select_temperature_window


def window(rows, seconds=300, **overrides):
    kwargs = dict(start=AT, end=AT + timedelta(seconds=seconds),
                  assessed_at=AT + timedelta(days=2),
                  history_start=AT - timedelta(seconds=120),
                  stream='indoor', policy=POLICY)
    kwargs.update(overrides)
    return select_temperature_window(
        [(AT + timedelta(seconds=offset), value) for offset, value in rows], **kwargs)


def test_short_lived_extreme_between_grid_points_is_not_lost():
    rows = [(0, raw()), (30, raw(30, '95')), (31, raw(31, '65')),
            (120, raw(120)), (230, raw(230))]
    result = window(rows)
    assert result == dict(observed_high_f=95, observed_low_f=65,
                         covered_seconds=300, total_seconds=300,
                         maximum_gap_seconds=0, fully_covered=True)


def test_expiry_is_exact_and_unchanged_numeric_value_cannot_renew_it():
    result = window([(0, raw()), (110, raw()), (250, raw(250))])
    assert result['covered_seconds'] == 170
    assert result['maximum_gap_seconds'] == 130
    assert not result['fully_covered']


def test_invalid_barriers_and_restored_old_receipts_extend_one_gap():
    result = window([(0, raw()), (20, 'bad JSON'), (30, raw()),
                     (40, raw(25)), (90, raw(90, '75'))], seconds=120)
    assert result['covered_seconds'] == 50
    assert result['maximum_gap_seconds'] == 70
    assert result['observed_high_f'] == 75


def test_half_open_end_does_not_include_next_days_extreme():
    result = window([(-10, raw(-10, '60')), (110, raw(110)),
                     (120, raw(120, '100'))], seconds=120)
    assert result['observed_low_f'] == 60
    assert result['observed_high_f'] == 70
    assert result['fully_covered']


def test_persistence_delay_does_not_backdate_coverage():
    result = window([(40, raw(0))], seconds=150)
    assert result['covered_seconds'] == 80
    assert result['maximum_gap_seconds'] == 40


def test_empty_or_expired_history_has_no_observed_extrema():
    for rows in ([], [(-120, raw(-120))]):
        result = window(rows)
        assert result['observed_high_f'] is None
        assert result['observed_low_f'] is None
        assert result['covered_seconds'] == 0
        assert result['maximum_gap_seconds'] == 300


def test_conflicting_same_timestamp_rejects_entire_window():
    with pytest.raises(ValueError):
        window([(0, raw()), (0, raw(value='71'))])


@pytest.mark.parametrize('hours', [23, 24, 25])
def test_elapsed_days_include_dst_lengths_and_parse_each_row_once(hours, monkeypatch):
    import weather_temperature_reader as reader
    original = reader._snapshot
    calls = []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(reader, '_snapshot', counted)
    rows = [(s, raw(s)) for s in range(0, hours * 3600, 30)]
    result = window(rows, seconds=hours * 3600)
    assert result['fully_covered']
    assert result['total_seconds'] == hours * 3600
    assert len(calls) == len(rows)


@pytest.mark.parametrize('month,day,hours', [(3, 8, 23), (11, 1, 25)])
def test_local_day_boundaries_are_converted_before_duration(month, day, hours):
    zone = ZoneInfo('America/Denver')
    start = datetime(2026, month, day, tzinfo=zone)
    end = datetime(2026, month, day + 1, tzinfo=zone)
    result = window([], start=start, end=end, assessed_at=end,
                    history_start=start - timedelta(minutes=2))
    assert result['total_seconds'] == hours * 3600


@pytest.mark.parametrize('overrides', [
    {'end': AT}, {'end': AT - timedelta(seconds=1)},
    {'end': AT + timedelta(hours=25, seconds=1)},
    {'assessed_at': AT}, {'history_start': AT},
    {'start': AT.replace(tzinfo=None)},
])
def test_invalid_window_contract_is_rejected(overrides):
    with pytest.raises(ValueError):
        window([], **overrides)


def test_new_epoch_cannot_restore_an_old_receipt():
    epoch = '631b737c-ab25-48d7-9a90-889746e56410'
    result = window([(0, raw()), (30, raw(0, '100', epoch)),
                     (60, raw(60, '75', epoch))], seconds=100)
    assert result['covered_seconds'] == 70
    assert result['maximum_gap_seconds'] == 30
    assert result['observed_high_f'] == 75


def test_bounds_and_unsorted_rows_refuse_partial_result():
    for rows in ([(1, raw(1)), (0, raw())], [(0, raw())] * 10001):
        with pytest.raises(ValueError):
            window(rows)


def test_window_fetch_is_one_stable_read_only_snapshot():
    from test_weather_temperature_history import Connection
    from weather_temperature_history import fetch_temperature_window
    connection = Connection(carry=(AT - timedelta(seconds=130), raw(-130)),
                            rows=[(AT, raw()), (AT + timedelta(seconds=30), raw(30, '90'))])
    result = fetch_temperature_window(lambda: connection, start=AT,
        end=AT + timedelta(seconds=60), assessed_at=AT + timedelta(seconds=60),
        stream='indoor', policy=POLICY)
    assert result['fully_covered'] and result['observed_high_f'] == 90
    assert connection.closed
    assert connection.session == dict(readonly=True, autocommit=False,
                                     isolation_level='REPEATABLE READ')
    assert connection.calls[-1][1] == (AT - timedelta(seconds=120), AT + timedelta(seconds=60))
    assert sum('time >=' in query for query, _ in connection.calls) == 1
    assert all(q.startswith(('SET LOCAL', 'SHOW ', 'SELECT ')) for q, _ in connection.calls)


def test_window_fetch_failure_has_no_partial_extrema_or_secret():
    from test_weather_temperature_history import Connection
    from weather_temperature_history import fetch_temperature_window, TemperatureHistoryUnavailable
    for connection in (Connection(fail='time >='), Connection(rows=[(AT, raw())] * 10001),
                       Connection(read_only='off')):
        with pytest.raises(TemperatureHistoryUnavailable,
                           match='^temperature evidence history unavailable$'):
            fetch_temperature_window(lambda: connection, start=AT,
                end=AT + timedelta(seconds=60), assessed_at=AT + timedelta(seconds=60),
                stream='indoor', policy=POLICY)
        assert connection.closed


def test_window_future_end_never_opens_connection():
    from weather_temperature_history import fetch_temperature_window, TemperatureHistoryUnavailable
    def forbidden(): pytest.fail('invalid window opened a connection')
    with pytest.raises(TemperatureHistoryUnavailable):
        fetch_temperature_window(forbidden, start=AT, end=AT + timedelta(seconds=1),
                                 assessed_at=AT, stream='indoor', policy=POLICY)
