"""Disposable PostgreSQL-only PV day transport check; no production DSN."""

from contextlib import closing
from datetime import timedelta

import pytest

fixture_module = pytest.importorskip(
    'advisory_db_fixture', reason='explicit disposable PostgreSQL harness required',
)
advisory_db = fixture_module.advisory_db

from pv_day_history import PVDayHistoryUnavailable, fetch_qualified_pv_day
from test_pv_day_evidence import DAY, bounds, rows


def test_real_sql_exact_item_restricted_role_and_oversize_barrier(advisory_db):
    start, end = bounds()
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            cursor.execute('INSERT INTO public.items VALUES (%s, %s)',
                           (777, 'MPPT60_PV_Day_Evidence_JSON'))
            cursor.execute('CREATE TABLE public.item0777 '
                           '(time timestamptz PRIMARY KEY, value text)')
            cursor.executemany('INSERT INTO public.item0777 VALUES (%s, %s)', rows())
            cursor.execute('GRANT SELECT ON public.items, public.item0777 '
                           'TO advisory_assessor')

    opened = []

    def connect():
        connection = advisory_db.connect_assessor()
        opened.append(connection)
        return connection

    def fetch():
        return fetch_qualified_pv_day(
            connect, local_date=DAY, cutover=start,
            as_of=end + timedelta(seconds=1))

    result = fetch()
    assert result['pv_kwh'] == 8.298
    assert result['receipt_count'] == 1440
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('REVOKE SELECT ON public.item0777 FROM advisory_assessor')
    with pytest.raises(PVDayHistoryUnavailable, match='^PV day history unavailable$'):
        fetch()
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('GRANT SELECT ON public.item0777 TO advisory_assessor')
            cursor.execute('INSERT INTO public.item0777 VALUES (%s, %s)',
                           (start + timedelta(hours=12, seconds=45), 'x' * 5000))
    with pytest.raises(PVDayHistoryUnavailable, match='^PV day history unavailable$'):
        fetch()
    assert all(connection.closed for connection in opened)
