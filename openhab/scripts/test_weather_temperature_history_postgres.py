"""Explicit disposable PostgreSQL qualification; never accepts a live DSN.

Supply Solar_PV's advisory test-fixture and source directories on PYTHONPATH.
The fixture creates its own loopback postgres:16 container and roles. Without
that explicit harness this module skips rather than falling back to production.
"""
from contextlib import closing
from datetime import timedelta
import time

import pytest

fixture_module = pytest.importorskip('advisory_db_fixture', reason='explicit disposable PostgreSQL harness required')
advisory_db = fixture_module.advisory_db

from test_weather_temperature_reader import AT, POLICY, raw
from weather_temperature_history import EVIDENCE_ITEM, TemperatureHistoryUnavailable, fetch_temperature_target


def test_actual_postgres_mapping_raw_barriers_bounds_permissions_and_timeout(advisory_db):
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            cursor.execute('CREATE TABLE public.item0700 (time timestamptz PRIMARY KEY, value text)')
            cursor.execute('INSERT INTO public.items VALUES (700, %s)', (EVIDENCE_ITEM,))
            cursor.execute('GRANT SELECT ON public.items, public.item0700 TO advisory_assessor')
            cursor.executemany('INSERT INTO public.item0700 VALUES (%s,%s)', [
                (AT - timedelta(seconds=90), raw(-90)), (AT, raw()),
                (AT + timedelta(seconds=61), raw(61, '99'))])
    opened = []
    def connect():
        connection = advisory_db.connect_assessor(); opened.append(connection); return connection
    def fetch():
        return fetch_temperature_target(connect, target=AT + timedelta(seconds=60),
            assessed_at=AT + timedelta(minutes=5), stream='indoor', policy=POLICY)
    def insert(offset, state):
        with closing(advisory_db.connect_owner()) as connection, connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO public.item0700 VALUES (%s,%s)', (AT + timedelta(seconds=offset), state))
    assert fetch()['temperatureF'] == 70  # 61-second post-target snapshot is not chosen
    assert opened[-1].closed
    insert(30, raw(30, 'invalid'))
    assert fetch() is None
    insert(40, raw(40, '75'))
    assert fetch()['temperatureF'] == 75
    insert(50, 'x' * 9000)
    assert fetch() is None  # SQL size cap preserves a NULL barrier, not an omitted row
    with closing(advisory_db.connect_owner()) as locker:
        with locker.cursor() as cursor: cursor.execute('LOCK TABLE public.item0700 IN ACCESS EXCLUSIVE MODE')
        began = time.monotonic()
        with pytest.raises(TemperatureHistoryUnavailable): fetch()
        assert time.monotonic() - began < 4
        locker.rollback()
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor: cursor.execute('REVOKE SELECT ON public.item0700 FROM advisory_assessor')
    with pytest.raises(TemperatureHistoryUnavailable) as error: fetch()
    assert str(error.value) == 'temperature evidence history unavailable'
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor: cursor.execute('INSERT INTO public.items VALUES (701,%s)', (EVIDENCE_ITEM,))
    with pytest.raises(TemperatureHistoryUnavailable): fetch()
    assert all(connection.closed for connection in opened)
