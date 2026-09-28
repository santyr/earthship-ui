"""Disposable PostgreSQL-only shade history qualification; no live DSN."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json

import pytest

fixture_module = pytest.importorskip(
    'advisory_db_fixture', reason='explicit disposable PostgreSQL harness required',
)
advisory_db = fixture_module.advisory_db

from thermal_model.shade_history import ShadeHistoryUnavailable, fetch_shade_intervals


T = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
ITEMS = {
    'diagnostic_state': 'Kitchen_Shade_01_State',
    'availability': 'Kitchen_Shade_01_Availability',
    'scalar_position': 'Kitchen_Shade_01_Position',
}


def report(at, position):
    return json.dumps({
        'schema_version': 1, 'source': 'motor_report', 'stale': False,
        'reported_position': position, 'report_received_at': at.timestamp(),
    })


def test_real_sql_partial_position_barrier_and_restricted_grant(advisory_db):
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            for number, name in zip((701, 702, 703), ITEMS.values(), strict=True):
                cursor.execute('INSERT INTO public.items VALUES (%s, %s)', (number, name))
                cursor.execute(f'CREATE TABLE public.item{number:04d} '
                               '(time timestamptz PRIMARY KEY, value text)')
            cursor.execute('GRANT SELECT ON public.items, public.item0701, '
                           'public.item0702, public.item0703 TO advisory_assessor')
            cursor.executemany('INSERT INTO public.item0701 VALUES (%s, %s)', [
                (T + timedelta(seconds=2), report(T + timedelta(seconds=2), 25)),
                (T + timedelta(seconds=4), report(T + timedelta(seconds=4), 50)),
            ])
            cursor.execute('INSERT INTO public.item0702 VALUES (%s, %s)',
                           (T - timedelta(seconds=1), 'ON'))
            cursor.executemany('INSERT INTO public.item0703 VALUES (%s, %s)', [
                (T + timedelta(seconds=1), '25'),
                (T + timedelta(seconds=5), '50'),
            ])

    opened = []

    def connect():
        connection = advisory_db.connect_assessor()
        opened.append(connection)
        return connection

    def fetch():
        return fetch_shade_intervals(
            connect, items=ITEMS, start=T, end=T + timedelta(seconds=10),
            as_of=T + timedelta(seconds=10),
        )

    assert [(part.start, part.end, part.percent_open) for part in fetch()] == [
        (T + timedelta(seconds=2), T + timedelta(seconds=4), 75),
        (T + timedelta(seconds=5), T + timedelta(seconds=10), 50),
    ]
    assert opened[-1].closed

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO public.item0701 VALUES (%s, %s)',
                           (T + timedelta(seconds=6), 'x' * 9000))
    assert [(part.start, part.end, part.percent_open) for part in fetch()] == [
        (T + timedelta(seconds=2), T + timedelta(seconds=4), 75),
        (T + timedelta(seconds=5), T + timedelta(seconds=6), 50),
    ]

    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('REVOKE SELECT ON public.item0702 FROM advisory_assessor')
    with pytest.raises(ShadeHistoryUnavailable, match='^shade history unavailable$'):
        fetch()
    assert all(connection.closed for connection in opened)
