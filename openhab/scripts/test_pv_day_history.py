from datetime import timedelta

import pytest

from pv_day_history import ITEM, PVDayHistoryUnavailable, fetch_qualified_pv_day
from test_pv_day_evidence import DAY, bounds, rows


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.query = ''

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.connection.queries.append((query, params))
        if self.connection.fail_query and 'SELECT time' in query:
            raise RuntimeError('permission denied')

    def fetchone(self):
        if self.query == 'SHOW transaction_read_only':
            return ('on' if self.connection.readonly else 'off',)
        if self.query == 'SHOW transaction_isolation':
            return ('repeatable read' if self.connection.repeatable else 'read committed',)
        raise AssertionError('unexpected fetchone')

    def fetchall(self):
        if 'SELECT itemid' in self.query:
            return self.connection.matches
        if 'SELECT time' in self.query:
            return self.connection.observations
        raise AssertionError('unexpected fetchall')


class Connection:
    def __init__(self, *, observations=None, matches=None, readonly=True,
                 repeatable=True, fail_query=False, status=0):
        self.observations = rows() if observations is None else observations
        self.matches = [(777,)] if matches is None else matches
        self.readonly = readonly
        self.repeatable = repeatable
        self.fail_query = fail_query
        self.status = status
        self.queries = []
        self.session = None
        self.closed = False

    def get_transaction_status(self):
        return self.status

    def set_session(self, **kwargs):
        self.session = kwargs

    def cursor(self):
        return Cursor(self)

    def close(self):
        self.closed = True


def read(connection, *, cutover=None, as_of=None):
    start, end = bounds()
    return fetch_qualified_pv_day(
        lambda: connection, local_date=DAY,
        cutover=start if cutover is None else cutover,
        as_of=end + timedelta(seconds=1) if as_of is None else as_of)


def test_exact_item_and_table_one_snapshot_without_write_or_commit():
    connection = Connection()
    result = read(connection)
    assert result['pv_kwh'] == 8.298
    assert result['source_item'] == ITEM
    assert connection.session == {'readonly': True, 'autocommit': False,
                                  'isolation_level': 'REPEATABLE READ'}
    assert connection.closed
    assert ('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (ITEM,)) in connection.queries
    day_query, params = next((query, params) for query, params in connection.queries
                             if 'SELECT time' in query)
    assert 'FROM public.item0777' in day_query
    assert 'octet_length(value::text) <= 4096' in day_query
    assert 'LIMIT 5001' in day_query
    assert params == bounds()
    assert not any('INSERT' in query or 'UPDATE' in query or 'DELETE' in query
                   for query, _ in connection.queries)


@pytest.mark.parametrize('matches', [[], [(777,), (778,)], [('777',)], [(-1,)], [(True,)]])
def test_missing_or_ambiguous_item_identity_refuses_and_closes(matches):
    connection = Connection(matches=matches)
    with pytest.raises(PVDayHistoryUnavailable):
        read(connection)
    assert connection.closed
    assert not any('SELECT time' in query for query, _ in connection.queries)


@pytest.mark.parametrize('settings', [
    {'readonly': False}, {'repeatable': False}, {'fail_query': True}, {'status': 2},
])
def test_transaction_or_privilege_failure_refuses(settings):
    connection = Connection(**settings)
    with pytest.raises(PVDayHistoryUnavailable):
        read(connection)
    assert connection.closed


def test_cutover_or_incomplete_day_refuses_before_connection():
    calls = []
    factory = lambda: calls.append(True)  # noqa: E731
    start, end = bounds()
    for cutover, as_of in ((start + timedelta(seconds=1), end + timedelta(seconds=1)),
                           (start, end - timedelta(seconds=1))):
        with pytest.raises(PVDayHistoryUnavailable):
            fetch_qualified_pv_day(factory, local_date=DAY,
                                   cutover=cutover, as_of=as_of)
    assert calls == []


def test_null_oversize_barrier_duplicate_row_and_over_budget_refuse():
    original = rows()
    for altered in (
        [*original[:500], (original[500][0], None), *original[501:]],
        [*original[:500], original[499], *original[501:]],
        original + [original[-1]] * (5001 - len(original)),
    ):
        connection = Connection(observations=altered)
        with pytest.raises(PVDayHistoryUnavailable):
            read(connection)
        assert connection.closed
