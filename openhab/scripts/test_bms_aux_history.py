from datetime import timedelta

import pytest

from bms_aux_evidence import ITEM
from bms_aux_history import (BmsAuxDayHistoryUnavailable,
                             BmsTemperatureParityUnavailable,
                             fetch_qualified_bms_aux_day,
                             fetch_bms_temperature_parity_day)
from test_bms_aux_evidence import DAY, bounds, day_rows


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
        self.observations = day_rows() if observations is None else observations
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


def read(connection, *, as_of=None):
    start, end = bounds()
    return fetch_qualified_bms_aux_day(
        lambda: connection, local_date=DAY, cutover=start - timedelta(days=1),
        as_of=end if as_of is None else as_of)


def test_exact_item_table_bounded_readonly_snapshot():
    connection = Connection()
    result = read(connection)
    assert result['source_item'] == ITEM
    assert result['fields']['battery.remaining_ah']['quality'] == 'ok'
    assert connection.session == {'readonly': True, 'autocommit': False,
                                  'isolation_level': 'REPEATABLE READ'}
    assert connection.closed
    assert ('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (ITEM,)) in connection.queries
    query, params = next((query, params) for query, params in connection.queries
                         if 'SELECT time' in query)
    assert 'FROM public.item0777' in query
    assert 'octet_length(value::text) <= 4096' in query
    assert 'LIMIT 5001' in query
    start, end = bounds()
    assert params == (start - timedelta(seconds=120), end)
    assert not any('INSERT' in query or 'UPDATE' in query or 'DELETE' in query
                   for query, _ in connection.queries)


@pytest.mark.parametrize('matches', [[], [(777,), (778,)], [('777',)], [(-1,)], [(True,)]])
def test_missing_ambiguous_or_invalid_mapping_refuses(matches):
    connection = Connection(matches=matches)
    with pytest.raises(BmsAuxDayHistoryUnavailable):
        read(connection)
    assert connection.closed
    assert not any('SELECT time' in query for query, _ in connection.queries)


@pytest.mark.parametrize('settings', [
    {'readonly': False}, {'repeatable': False}, {'fail_query': True}, {'status': 2},
])
def test_permission_or_session_failure_refuses(settings):
    connection = Connection(**settings)
    with pytest.raises(BmsAuxDayHistoryUnavailable):
        read(connection)
    assert connection.closed


def test_incomplete_day_refuses_without_connecting():
    connection = Connection()
    _, end = bounds()
    with pytest.raises(BmsAuxDayHistoryUnavailable):
        read(connection, as_of=end - timedelta(seconds=1))
    assert connection.session is None


class ParityCursor(Cursor):
    def execute(self, query, params=None):
        super().execute(query, params)
        self.params = params
        if self.connection.fail_query and 'FROM public.item0559' in query:
            raise RuntimeError('derived table permission denied')

    def fetchall(self):
        if 'SELECT itemid' in self.query:
            return [(658,)] if self.params == (ITEM,) else [(559,)]
        if 'FROM public.item0658' in self.query:
            return self.connection.observations
        if 'FROM public.item0559' in self.query:
            start, _ = bounds()
            return ([(start - timedelta(minutes=1), 68.0)]
                    if 'ORDER BY time DESC' in self.query else [])
        raise AssertionError('unexpected parity query')


class ParityConnection(Connection):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fail_query = False
        self.fail_derived = kwargs.get('fail_query', False)

    def cursor(self):
        outer = self
        class CursorWithGrant(ParityCursor):
            def execute(self, query, params=None):
                super().execute(query, params)
                if outer.fail_derived and 'FROM public.item0559' in query:
                    raise RuntimeError('derived table permission denied')
        return CursorWithGrant(self)


def test_parity_adapter_reads_exact_two_items_in_one_readonly_snapshot():
    connection = ParityConnection()
    _, end = bounds()
    result = fetch_bms_temperature_parity_day(
        lambda: connection, local_date=DAY, as_of=end, cutover=bounds()[0] - timedelta(days=1))
    assert result['status'] == 'insufficient_changes'
    assert result['source_temperature_quality'] == 'ok'
    assert connection.session == {'readonly': True, 'autocommit': False,
                                  'isolation_level': 'REPEATABLE READ'}
    assert connection.closed
    statements = [query for query, _ in connection.queries]
    assert any('FROM public.item0658' in query and 'LIMIT 5001' in query
               for query in statements)
    assert sum('FROM public.item0559' in query for query in statements) == 2
    assert not any('INSERT' in query or 'UPDATE' in query or 'DELETE' in query
                   for query in statements)


def test_parity_adapter_refuses_missing_derived_grant_and_partial_day():
    connection = ParityConnection(fail_query=True)
    _, end = bounds()
    with pytest.raises(BmsTemperatureParityUnavailable):
        fetch_bms_temperature_parity_day(
            lambda: connection, local_date=DAY, as_of=end,
            cutover=bounds()[0] - timedelta(days=1))
    assert connection.closed
    untouched = ParityConnection()
    with pytest.raises(BmsTemperatureParityUnavailable):
        fetch_bms_temperature_parity_day(
            lambda: untouched, local_date=DAY, as_of=end - timedelta(seconds=1),
            cutover=bounds()[0] - timedelta(days=1))
    assert untouched.session is None
