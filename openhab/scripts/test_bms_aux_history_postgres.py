"""Disposable PostgreSQL-only BMS aux reader test; no production DSN."""
from contextlib import closing
from datetime import timedelta

import pytest


fixture_module = pytest.importorskip(
    'advisory_db_fixture', reason='explicit disposable PostgreSQL harness required',
)
advisory_db = fixture_module.advisory_db

from bms_aux_history import (BmsAuxDayHistoryUnavailable,
                             fetch_qualified_bms_aux_day)
from test_bms_aux_evidence import DAY, bounds, day_rows


def test_real_sql_exact_item_restricted_role_and_oversize_barrier(advisory_db):
    start, end = bounds()
    rows = day_rows()
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            cursor.execute('INSERT INTO public.items VALUES (%s, %s)',
                           (803, 'BMS_Aux_Evidence_JSON'))
            cursor.execute('CREATE TABLE public.item0803 '
                           '(time timestamptz PRIMARY KEY, value text)')
            cursor.executemany('INSERT INTO public.item0803 VALUES (%s, %s)', rows)
            cursor.execute('GRANT SELECT ON public.items, public.item0803 '
                           'TO advisory_assessor')

    opened = []

    def connect():
        connection = advisory_db.connect_assessor()
        opened.append(connection)
        return connection

    def fetch():
        return fetch_qualified_bms_aux_day(
            connect, local_date=DAY, cutover=start, as_of=end)

    result = fetch()
    assert result['evidence_rows'] == len(rows)
    assert result['source_item'] == 'BMS_Aux_Evidence_JSON'
    assert all(field['quality'] == 'ok' for field in result['fields'].values())
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('REVOKE SELECT ON public.item0803 FROM advisory_assessor')
    with pytest.raises(BmsAuxDayHistoryUnavailable,
                       match='^BMS auxiliary day history unavailable$'):
        fetch()
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('GRANT SELECT ON public.item0803 TO advisory_assessor')
            cursor.execute('INSERT INTO public.item0803 VALUES (%s, %s)',
                           (start + timedelta(hours=12, seconds=30), 'x' * 5000))
    with pytest.raises(BmsAuxDayHistoryUnavailable,
                       match='^BMS auxiliary day history unavailable$'):
        fetch()
    assert all(connection.closed for connection in opened)
