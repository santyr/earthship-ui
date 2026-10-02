"""Real restricted/disposable PostgreSQL only; never accepts a household DSN."""
from contextlib import closing
from datetime import timedelta
import time

import pytest

fixture_module = pytest.importorskip('advisory_db_fixture', reason='explicit disposable harness required')
advisory_db = fixture_module.advisory_db

from test_weather_radiation_reader import AT, POLICY, raw
from weather_radiation_history import ITEM, RadiationHistoryUnavailable, fetch_radiation_at, fetch_radiation_window


def test_original_jdbc_read_barriers_permissions_mapping_timeout_and_closure(advisory_db):
    with closing(advisory_db.connect_owner()) as c, c:
        with c.cursor() as q:
            q.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            q.execute('CREATE TABLE public.item0664 (time timestamptz PRIMARY KEY, value text)')
            q.execute('INSERT INTO public.items VALUES (664,%s)', (ITEM,))
            q.execute('GRANT SELECT ON public.items, public.item0664 TO advisory_assessor')
            q.executemany('INSERT INTO public.item0664 VALUES (%s,%s)', [
                (AT, raw()), (AT + timedelta(seconds=61), raw(61, sequence=4, value=200)),
                (AT + timedelta(seconds=130), raw(130, sequence=9, value=1000))])
    connections = []
    def connect():
        c = advisory_db.connect_assessor(); connections.append(c); return c
    def point():
        return fetch_radiation_at(connect, target=AT + timedelta(seconds=60),
            assessed_at=AT + timedelta(seconds=240), cutover=AT - timedelta(hours=1), policy=POLICY)
    def interval():
        return fetch_radiation_window(connect, start=AT, end=AT + timedelta(seconds=120),
            assessed_at=AT + timedelta(seconds=240), cutover=AT - timedelta(hours=1), policy=POLICY)
    assert point()['irradianceWm2'] == 100  # 61-second future row is never selected.
    result = interval()
    assert result['status'] == 'ok' and result['observed_high_w_m2'] == 200
    assert result['irradiance_wh_m2'] == pytest.approx((61 * 100 + 59 * 200) / 3600)
    with closing(advisory_db.connect_owner()) as c, c:
        with c.cursor() as q:
            q.execute('INSERT INTO public.item0664 VALUES (%s,%s)', (AT + timedelta(seconds=30), None))
    assert point() is None and interval()['irradiance_wh_m2'] is None
    with closing(advisory_db.connect_owner()) as c, c:
        with c.cursor() as q:
            q.execute('INSERT INTO public.item0664 VALUES (%s,%s)', (AT + timedelta(seconds=40), raw(40, sequence=3)))
    assert point()['irradianceWm2'] == 100  # Genuine newer native receipt recovers forward.
    with closing(advisory_db.connect_owner()) as c, c:
        with c.cursor() as q:
            q.execute('INSERT INTO public.item0664 VALUES (%s,%s)', (AT + timedelta(seconds=50), 'x' * 9000))
    assert point() is None  # SQL NULL size barrier is retained, not dropped.
    with closing(advisory_db.connect_owner()) as locker:
        with locker.cursor() as q:
            q.execute('LOCK TABLE public.item0664 IN ACCESS EXCLUSIVE MODE')
        began = time.monotonic()
        with pytest.raises(RadiationHistoryUnavailable): point()
        assert time.monotonic() - began < 4
        locker.rollback()
    with closing(advisory_db.connect_owner()) as c, c:
        with c.cursor() as q:
            q.execute('REVOKE SELECT ON public.item0664 FROM advisory_assessor')
    with pytest.raises(RadiationHistoryUnavailable, match='^radiation history unavailable$'): point()
    with closing(advisory_db.connect_owner()) as c, c:
        with c.cursor() as q:
            q.execute('GRANT SELECT ON public.item0664 TO advisory_assessor')
            q.execute('INSERT INTO public.items VALUES (665,%s)', (ITEM,))
    with pytest.raises(RadiationHistoryUnavailable): point()
    assert all(c.closed for c in connections)
