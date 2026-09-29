"""Disposable PostgreSQL-only rain day transport check; no production DSN."""
from contextlib import closing
from datetime import timedelta

import pytest


fixture_module = pytest.importorskip(
    'advisory_db_fixture', reason='explicit disposable PostgreSQL harness required',
)
advisory_db = fixture_module.advisory_db

from test_weather_rain_day import DAY, POLICY, bounds, day_rows
from test_weather_rain_day_recovery import latch, mutate, reject, rows_for_day
from weather_rain_history import (RainDayHistoryUnavailable,
                                  fetch_candidate_recovered_rain_day,
                                  fetch_qualified_rain_day)


def test_real_sql_exact_item_restricted_role_and_oversize_barrier(advisory_db):
    start, end = bounds()
    rows = day_rows()
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            cursor.execute('INSERT INTO public.items VALUES (%s, %s)',
                           (802, 'Weather_Rain_Evidence_JSON'))
            cursor.execute('CREATE TABLE public.item0802 '
                           '(time timestamptz PRIMARY KEY, value text)')
            cursor.executemany('INSERT INTO public.item0802 VALUES (%s, %s)', rows)
            cursor.execute('GRANT SELECT ON public.items, public.item0802 '
                           'TO advisory_assessor')

    opened = []

    def connect():
        connection = advisory_db.connect_assessor()
        opened.append(connection)
        return connection

    def fetch():
        return fetch_qualified_rain_day(
            connect, local_date=DAY, cutover=start, policy=POLICY,
            as_of=end + timedelta(seconds=120))

    result = fetch()
    assert result['rain_in'] == 0.1
    assert result['receipt_count'] == len(rows)
    assert result['source_item'] == 'Weather_Rain_Evidence_JSON'
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('REVOKE SELECT ON public.item0802 FROM advisory_assessor')
    with pytest.raises(RainDayHistoryUnavailable,
                       match='^rain day history unavailable$'):
        fetch()
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('GRANT SELECT ON public.item0802 TO advisory_assessor')
            cursor.execute('INSERT INTO public.item0802 VALUES (%s, %s)',
                           (start + timedelta(hours=12, seconds=45), 'x' * 5000))
    with pytest.raises(RainDayHistoryUnavailable,
                       match='^rain day history unavailable$'):
        fetch()
    assert all(connection.closed for connection in opened)

    # Exercise the separate candidate over the same restricted SQL transport.
    # The strict production reader must still refuse the natural quarantine.
    candidate_rows, _ = rows_for_day()
    candidate_rows = mutate(latch(candidate_rows, 100), 100, reject)
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.item0802')
            cursor.executemany('INSERT INTO public.item0802 VALUES (%s, %s)',
                               candidate_rows)
    with pytest.raises(RainDayHistoryUnavailable):
        fetch()
    result = fetch_candidate_recovered_rain_day(
        connect, local_date=DAY, cutover=start, policy=POLICY,
        as_of=end + timedelta(seconds=120))
    assert result['rain_in'] == 0.1
    assert result['quarantined_jumps'] == 1
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('REVOKE SELECT ON public.item0802 FROM advisory_assessor')
    with pytest.raises(RainDayHistoryUnavailable):
        fetch_candidate_recovered_rain_day(
            connect, local_date=DAY, cutover=start, policy=POLICY,
            as_of=end + timedelta(seconds=120))
    assert all(connection.closed for connection in opened)
