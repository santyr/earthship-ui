"""Read-only JDBC acquisition for future commissioned shade motor reports."""
from datetime import datetime, timedelta, timezone
import json
import re

import pytest

from thermal_model.shade_history import ShadeHistoryUnavailable, fetch_shade_intervals


T = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
ITEMS = {
    'diagnostic_state': 'Kitchen_Shade_01_State',
    'availability': 'Kitchen_Shade_01_Availability',
    'scalar_position': 'Kitchen_Shade_01_Position',
}
IDS = {ITEMS['diagnostic_state']: 600, ITEMS['availability']: 601,
       ITEMS['scalar_position']: 602}


def report(at, percent_closed):
    return json.dumps({
        'schema_version': 1, 'source': 'motor_report', 'stale': False,
        'reported_position': percent_closed, 'report_received_at': at.timestamp(),
    })


class Connection:
    def __init__(self, *, mappings=None, carries=None, rows=None,
                 read_only='on', isolation='repeatable read', fail=None):
        self.mappings = IDS if mappings is None else mappings
        self.carries = {601: (T - timedelta(seconds=1), 'ON')} if carries is None else carries
        self.rows = ({
            600: [(T + timedelta(seconds=2), report(T + timedelta(seconds=2), 25)),
                  (T + timedelta(seconds=4), report(T + timedelta(seconds=4), 50))],
            602: [(T + timedelta(seconds=1), '25'),
                  (T + timedelta(seconds=5), '50')],
        } if rows is None else rows)
        self.read_only = read_only
        self.isolation = isolation
        self.fail = fail
        self.calls = []
        self.session = None
        self.closed = False

    def get_transaction_status(self): return 0
    def set_session(self, **kwargs): self.session = kwargs
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if self.fail and self.fail in query:
            raise RuntimeError('SECRET database details')

    def fetchone(self):
        query = self.calls[-1][0]
        if query == 'SHOW transaction_read_only': return (self.read_only,)
        if query == 'SHOW transaction_isolation': return (self.isolation,)
        table = re.search(r'FROM public\.item(\d+)', query)
        return self.carries.get(int(table.group(1))) if table else None

    def fetchall(self):
        query, params = self.calls[-1]
        if 'public.items' in query:
            value = self.mappings.get(params[0])
            return [] if value is None else value if isinstance(value, list) else [(value,)]
        table = re.search(r'FROM public\.item(\d+)', query)
        return self.rows.get(int(table.group(1)), [])

    def close(self): self.closed = True


def fetch(connection, **kwargs):
    return fetch_shade_intervals(
        lambda: connection, items=ITEMS, start=T, end=T + timedelta(seconds=10),
        as_of=T + timedelta(seconds=10), **kwargs,
    )


def test_exact_three_item_read_only_snapshot_and_partial_positions():
    connection = Connection()
    intervals = fetch(connection)
    assert [(part.start, part.end, part.percent_closed, part.percent_open)
            for part in intervals] == [
        (T + timedelta(seconds=2), T + timedelta(seconds=4), 25, 75),
        (T + timedelta(seconds=5), T + timedelta(seconds=10), 50, 50),
    ]
    assert connection.session == {
        'readonly': True, 'autocommit': False, 'isolation_level': 'REPEATABLE READ',
    }
    assert connection.closed
    assert [params[0] for query, params in connection.calls if 'public.items' in query] == [
        ITEMS['diagnostic_state'], ITEMS['availability'], ITEMS['scalar_position'],
    ]
    queries = [query for query, _ in connection.calls]
    assert all(query.startswith(('SET LOCAL', 'SHOW ', 'SELECT ')) for query in queries)
    assert sum('LIMIT 10001' in query for query in queries) == 3
    assert sum('octet_length(value::text) <= 8192' in query for query in queries) == 6
    assert all(params == (T, T + timedelta(seconds=10))
               for query, params in connection.calls if 'LIMIT 10001' in query)


@pytest.mark.parametrize('mappings', [
    {**IDS, ITEMS['diagnostic_state']: None},
    {**IDS, ITEMS['diagnostic_state']: [(600,), (603,)]},
    {**IDS, ITEMS['diagnostic_state']: '600'},
    {**IDS, ITEMS['availability']: 600},
])
def test_missing_ambiguous_or_shared_item_id_refuses_all_history(mappings):
    connection = Connection(mappings=mappings)
    with pytest.raises(ShadeHistoryUnavailable, match='^shade history unavailable$'):
        fetch(connection)
    assert connection.closed
    assert not any('FROM public.item0' in query for query, _ in connection.calls)


@pytest.mark.parametrize('kwargs', [
    {'read_only': 'off'}, {'isolation': 'read committed'},
    {'fail': 'public.items'}, {'fail': 'LIMIT 10001'},
    {'rows': {600: [(T + timedelta(seconds=2), report(T, 25))] * 10001}},
    {'rows': {600: [(T + timedelta(seconds=10), report(T, 25))]}},
    {'rows': {600: [(T + timedelta(seconds=2), report(T, 25))] * 2}},
])
def test_unqualified_transport_limit_or_duplicate_never_returns_partial(kwargs):
    connection = Connection(**kwargs)
    with pytest.raises(ShadeHistoryUnavailable, match='^shade history unavailable$'):
        fetch(connection)
    assert connection.closed


def test_null_diagnostic_is_a_barrier_not_a_skipped_row():
    rows = {600: [(T + timedelta(seconds=2), report(T + timedelta(seconds=2), 25)),
                  (T + timedelta(seconds=3), None)],
            602: [(T + timedelta(seconds=1), '25')]}
    intervals = fetch(Connection(rows=rows))
    assert [(part.start, part.end) for part in intervals] == [
        (T + timedelta(seconds=2), T + timedelta(seconds=3)),
    ]


def test_future_origin_and_unconfigured_items_fail_before_connecting():
    def forbidden():
        pytest.fail('invalid shade request opened the database')
    for options in (
        {'as_of': T + timedelta(seconds=9), 'items': ITEMS},
        {'as_of': T + timedelta(seconds=10), 'items': {**ITEMS, 'scalar_position': ''}},
        {'as_of': T + timedelta(seconds=10), 'items': {**ITEMS, 'scalar_position': 'Bad;SQL'}},
    ):
        with pytest.raises(ShadeHistoryUnavailable):
            fetch_shade_intervals(forbidden, start=T, end=T + timedelta(seconds=10),
                                  **options)
