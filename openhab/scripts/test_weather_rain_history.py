from datetime import timedelta

import pytest

from test_weather_rain_day import DAY, POLICY, bounds, day_rows
from test_weather_rain_day_recovery import latch, mutate, reject, rows_for_day
from weather_rain_history import (ITEM, RainDayHistoryUnavailable,
                                  fetch_candidate_recovered_rain_day,
                                  fetch_qualified_rain_day)


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
        if self.connection.fail_source and 'SELECT time' in query:
            raise RuntimeError('permission denied')

    def fetchone(self):
        if self.query == 'SHOW transaction_read_only':
            return ('on' if self.connection.readonly else 'off',)
        if self.query == 'SHOW transaction_isolation':
            return ('repeatable read' if self.connection.repeatable else 'read committed',)
        if 'SELECT time' in self.query:
            return self.connection.carry
        raise AssertionError('unexpected fetchone')

    def fetchall(self):
        if 'SELECT itemid' in self.query:
            return self.connection.matches
        if 'SELECT time' in self.query:
            return self.connection.rows
        raise AssertionError('unexpected fetchall')


class Connection:
    def __init__(self, *, carry=None, rows=None, matches=None,
                 readonly=True, repeatable=True, status=0, fail_source=False,
                 missing_carry=False):
        observations = day_rows()
        self.carry = None if missing_carry else (observations[0] if carry is None else carry)
        self.rows = observations[1:] if rows is None else rows
        self.matches = [(802,)] if matches is None else matches
        self.readonly = readonly
        self.repeatable = repeatable
        self.status = status
        self.fail_source = fail_source
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
    return fetch_qualified_rain_day(
        lambda: connection, local_date=DAY, policy=POLICY,
        cutover=start if cutover is None else cutover,
        as_of=end + timedelta(seconds=120) if as_of is None else as_of)


def test_exact_item_one_snapshot_and_no_write_or_commit():
    connection = Connection()
    result = read(connection)
    assert result['rain_in'] == 0.1
    assert result['source_item'] == ITEM
    assert connection.session == {'readonly': True, 'autocommit': False,
                                  'isolation_level': 'REPEATABLE READ'}
    assert connection.closed
    assert ('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',
            (ITEM,)) in connection.queries
    selects = [(query, params) for query, params in connection.queries
               if 'SELECT time' in query]
    assert len(selects) == 2
    assert all('FROM public.item0802' in query and
               'octet_length(value::text) <= 4096' in query
               for query, _ in selects)
    assert selects[0][1] == (bounds()[0],)
    assert selects[1][1] == (bounds()[0], bounds()[1] + timedelta(seconds=120))
    assert 'LIMIT 4001' in selects[1][0]
    assert not any(word in query for query, _ in connection.queries
                   for word in ('INSERT', 'UPDATE', 'DELETE', 'COMMIT'))


@pytest.mark.parametrize('matches', [[], [(802,), (803,)], [('802',)], [(-1,)], [(True,)]])
def test_missing_or_ambiguous_mapping_refuses(matches):
    connection = Connection(matches=matches)
    with pytest.raises(RainDayHistoryUnavailable):
        read(connection)
    assert connection.closed
    assert not any('SELECT time' in query for query, _ in connection.queries)


@pytest.mark.parametrize('settings', [
    {'readonly': False}, {'repeatable': False}, {'status': 2},
    {'fail_source': True},
])
def test_transaction_and_privilege_fail_closed(settings):
    connection = Connection(**settings)
    with pytest.raises(RainDayHistoryUnavailable):
        read(connection)
    assert connection.closed


def test_cutover_and_partial_day_refuse_before_database_connection():
    start, end = bounds()
    calls = []
    factory = lambda: calls.append(True)
    for cutover, as_of in ((start + timedelta(seconds=1), end + timedelta(seconds=120)),
                           (start, end - timedelta(seconds=1))):
        with pytest.raises(RainDayHistoryUnavailable):
            fetch_qualified_rain_day(factory, local_date=DAY, policy=POLICY,
                                     cutover=cutover, as_of=as_of)
    assert calls == []


def test_null_oversize_duplicate_and_missing_carry_refuse():
    original = day_rows()
    for connection in (
        Connection(missing_carry=True, rows=original[1:]),
        Connection(rows=[*original[1:200], (original[200][0], None),
                         *original[201:]]),
        Connection(rows=[*original[1:200],
                         (original[200][0], original[200][1] + ' ' * 4096),
                         *original[201:]]),
        Connection(rows=[*original[1:200], original[199], *original[201:]]),
        Connection(rows=original[1:] + [original[-1]] * 4000),
    ):
        with pytest.raises(RainDayHistoryUnavailable):
            read(connection)
        assert connection.closed


def test_default_off_candidate_uses_same_restricted_snapshot_without_changing_strict_reader():
    rows, end = rows_for_day()
    rows = mutate(latch(rows, 100), 100, reject)
    start, _ = bounds()
    strict = Connection(carry=rows[0], rows=rows[1:])
    with pytest.raises(RainDayHistoryUnavailable):
        fetch_qualified_rain_day(lambda: strict, local_date=DAY, cutover=start,
                                 as_of=end + timedelta(seconds=120), policy=POLICY)
    assert strict.closed

    candidate = Connection(carry=rows[0], rows=rows[1:])
    result = fetch_candidate_recovered_rain_day(
        lambda: candidate, local_date=DAY, cutover=start,
        as_of=end + timedelta(seconds=120), policy=POLICY)
    assert result['rain_in'] == 0.1
    assert result['quarantined_jumps'] == 1
    assert result['source_item'] == ITEM
    assert result['source_cutover'] == start.isoformat()
    assert candidate.closed
    assert candidate.session == {'readonly': True, 'autocommit': False,
                                 'isolation_level': 'REPEATABLE READ'}

    denied = Connection(carry=rows[0], rows=rows[1:], fail_source=True)
    with pytest.raises(RainDayHistoryUnavailable):
        fetch_candidate_recovered_rain_day(
            lambda: denied, local_date=DAY, cutover=start,
            as_of=end + timedelta(seconds=120), policy=POLICY)
    assert denied.closed
