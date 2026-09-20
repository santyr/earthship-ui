from datetime import timedelta

import pytest

from test_weather_temperature_reader import AT, POLICY, raw
from weather_temperature_reader import select_temperature_grid, select_temperature_at


def grid(rows, offsets=(0, 60, 120, 300), **kwargs):
    context = dict(targets=[AT + timedelta(seconds=s) for s in offsets],
                   assessed_at=AT + timedelta(days=1), history_start=AT - timedelta(minutes=2),
                   stream='indoor', policy=POLICY)
    context.update(kwargs)
    return select_temperature_grid(rows, **context)


def test_grid_unchanged_value_expiry_and_recovery_keep_original_provenance():
    rows = [(AT, raw()), (AT + timedelta(seconds=300), raw(300))]
    result = grid(rows)
    assert [None if value is None else value['temperatureF'] for _, value in result] == [70, 70, None, 70]
    assert result[1][1]['receivedAt'] == AT
    assert result[1][1]['storedAt'] == AT
    assert result[-1][1]['receivedAt'] == AT + timedelta(seconds=300)


def test_grid_preserves_barrier_chain_before_each_target_window():
    rows = [(AT, raw()), (AT + timedelta(seconds=30), 'invalid')]
    # Old receipts repeatedly restored after a barrier cannot become new evidence.
    rows.extend((AT + timedelta(seconds=s), raw(s - 25)) for s in range(40, 201, 10))
    result = grid(rows, offsets=(60, 120, 200))
    assert all(value is None for _, value in result)


@pytest.mark.parametrize('broken', ['bad JSON', None, raw(60, 'invalid')])
def test_batch_is_exactly_equivalent_to_individual_asof_selection(broken):
    rows = [(AT, raw()), (AT + timedelta(seconds=60), broken),
            (AT + timedelta(seconds=90), raw()),
            (AT + timedelta(seconds=150), raw(150)),
            (AT + timedelta(seconds=400), raw(400, '80'))]
    result = grid(rows, offsets=range(0, 421, 10))
    for at, value in result:
        assert value == select_temperature_at(rows, target=at, assessed_at=AT + timedelta(days=1),
            history_start=AT - timedelta(minutes=2), stream='indoor', policy=POLICY)


@pytest.mark.parametrize('offsets', [(), (60, 0), (0, 0), (-1,), (0, 86401), range(290)])
def test_invalid_or_unbounded_grid_is_rejected(offsets):
    with pytest.raises(ValueError): grid([(AT, raw())], offsets=offsets)


def test_unsorted_or_conflicting_history_refuses_whole_batch():
    for rows in [[(AT, raw()), (AT, raw(value='71'))],
                 [(AT + timedelta(seconds=1), raw(1)), (AT, raw())]]:
        with pytest.raises(ValueError): grid(rows)


def test_each_snapshot_is_parsed_once_for_a_full_day(monkeypatch):
    import weather_temperature_reader as reader
    original = reader._snapshot
    calls = []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(reader, '_snapshot', counted)
    rows = [(AT + timedelta(seconds=s), raw(s)) for s in range(0, 86401, 30)]
    result = grid(rows, offsets=range(0, 86401, 300))
    assert len(result) == 289 and all(value is not None for _, value in result)
    assert len(calls) == len(rows)


def test_grid_fetch_uses_one_read_only_snapshot_and_closes_it():
    from test_weather_temperature_history import Connection
    from weather_temperature_history import fetch_temperature_grid
    rows = [(AT + timedelta(seconds=s), raw(s)) for s in range(0, 601, 30)]
    connection = Connection(rows=rows)
    targets = [AT + timedelta(seconds=s) for s in (0, 300, 600)]
    result = fetch_temperature_grid(lambda: connection, targets=targets,
        assessed_at=targets[-1], stream='indoor', policy=POLICY)
    assert [at for at, _ in result] == targets
    assert all(value['temperatureF'] == 70 for _, value in result)
    assert connection.closed and connection.session['readonly']
    assert len([query for query, _ in connection.calls if 'time >=' in query]) == 1
    assert connection.calls[-1][1] == (AT - timedelta(seconds=120), targets[-1])


def test_bad_grid_never_opens_database_connection():
    from weather_temperature_history import fetch_temperature_grid, TemperatureHistoryUnavailable
    def forbidden(): pytest.fail('invalid grid opened a connection')
    for targets in ([], [AT + timedelta(seconds=1)], [AT, AT]):
        with pytest.raises(TemperatureHistoryUnavailable):
            fetch_temperature_grid(forbidden, targets=targets, assessed_at=AT,
                                   stream='indoor', policy=POLICY)


def test_failed_grid_fetch_never_returns_partial_day_or_database_details():
    from test_weather_temperature_history import Connection
    from weather_temperature_history import fetch_temperature_grid, TemperatureHistoryUnavailable
    connection = Connection(fail='time >=')
    with pytest.raises(TemperatureHistoryUnavailable, match='^temperature evidence history unavailable$'):
        fetch_temperature_grid(lambda: connection, targets=[AT, AT + timedelta(minutes=5)],
            assessed_at=AT + timedelta(days=1), stream='indoor', policy=POLICY)
    assert connection.closed
