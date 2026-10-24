"""Real v2 SQL against the explicit disposable-only PostgreSQL fixture."""
from contextlib import closing
from datetime import timedelta
import json

import pytest

fixture_module = pytest.importorskip('advisory_db_fixture',
    reason='explicit disposable PostgreSQL harness required; no household DSN fallback')
advisory_db = fixture_module.advisory_db

from thermal_model.shade_history_v2 import ShadeHistoryV2Unavailable, fetch_shade_intervals_v2
from test_thermal_shade_history_v2 import ITEMS, IDS
from test_thermal_shade_observations_v2 import T, PROFILE, state, service, bridge


def test_disposable_eight_role_snapshot_identity_partial_positions_and_refusals(advisory_db):
    tables = [f'public.item{number:04d}' for number in IDS.values()]
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            for name,number in IDS.items():
                cursor.execute('INSERT INTO public.items VALUES (%s,%s)',(number,name))
                cursor.execute(f'CREATE TABLE public.item{number:04d} (time timestamptz PRIMARY KEY,value text)')
            cursor.execute('GRANT SELECT ON public.items, '+', '.join(tables)+' TO advisory_assessor')
            for role,value in (('availability','ON'),('service_availability','ON'),
                ('bridge_availability','ON'),('provider_status','ONLINE'),
                ('service_state',json.dumps(service())),('bridge_state',json.dumps(bridge()))):
                cursor.execute(f'INSERT INTO public.item{IDS[ITEMS[role]]:04d} VALUES (%s,%s)',
                               (T-timedelta(seconds=1),value))
            cursor.executemany(f'INSERT INTO public.item{IDS[ITEMS["diagnostic_state"]]:04d} VALUES (%s,%s)',[
                (T+timedelta(seconds=2),json.dumps(state(T+timedelta(seconds=2),25,'20261024180002000'))),
                (T+timedelta(seconds=4),json.dumps(state(T+timedelta(seconds=4),50,'20261024180004000'))),
                (T+timedelta(seconds=11),json.dumps(state(T+timedelta(seconds=11),75,'20261024180011000')))])
            cursor.executemany(f'INSERT INTO public.item{IDS[ITEMS["scalar_position"]]:04d} VALUES (%s,%s)',[
                (T+timedelta(seconds=1),'25'),(T+timedelta(seconds=5),'50')])
    opened=[]
    def connect():
        connection=advisory_db.connect_assessor()
        opened.append(connection)
        return connection
    def fetch(factory=connect, profile=PROFILE):
        return fetch_shade_intervals_v2(factory,items=ITEMS,profile=profile,start=T,
            end=T+timedelta(seconds=10),as_of=T+timedelta(seconds=10))
    expected=[(T+timedelta(seconds=2),T+timedelta(seconds=4),75),
              (T+timedelta(seconds=5),T+timedelta(seconds=10),50)]
    parts=lambda history:[(part.start,part.end,part.percent_open) for part in history.intervals]
    history=fetch()
    assert parts(history)==expected
    assert [part.percent_closed for part in history.observations]==[25,50]
    assert not history.action_qualified and not history.preference_qualified
    assert opened[-1].closed
    other_epoch={**PROFILE,'commissioned_epoch':'22222222-2222-4222-8222-222222222222'}
    with pytest.raises(ShadeHistoryV2Unavailable): fetch(profile=other_epoch)

    # Commit a synthetic provider change between role queries. REPEATABLE READ
    # must retain the already-established snapshot; the next read sees OFFLINE.
    provider=f'public.item{IDS[ITEMS["provider_status"]]:04d}'
    triggered=[]
    class CursorProxy:
        def __init__(self,cursor): self.cursor=cursor
        def __enter__(self): self.cursor.__enter__(); return self
        def __exit__(self,*args): return self.cursor.__exit__(*args)
        def __getattr__(self,name): return getattr(self.cursor,name)
        def execute(self,query,params=None):
            result=self.cursor.execute(query,params)
            if not triggered and f'FROM public.item{IDS[ITEMS["diagnostic_state"]]:04d}' in query:
                triggered.append(True)
                with closing(advisory_db.connect_owner()) as writer,writer:
                    with writer.cursor() as cursor:
                        cursor.execute(f'UPDATE {provider} SET value=%s',('OFFLINE',))
            return result
    class ConnectionProxy:
        def __init__(self,connection): self.connection=connection
        def __getattr__(self,name): return getattr(self.connection,name)
        def cursor(self): return CursorProxy(self.connection.cursor())
    assert parts(fetch(lambda:ConnectionProxy(connect())))==expected
    assert triggered and not fetch().intervals
    with closing(advisory_db.connect_owner()) as connection,connection:
        with connection.cursor() as cursor:
            cursor.execute(f'UPDATE {provider} SET value=%s',('ONLINE',))
            cursor.execute(f'INSERT INTO public.item{IDS[ITEMS["diagnostic_state"]]:04d} VALUES (%s,%s)',
                           (T+timedelta(seconds=6),'x'*9000))
    assert parts(fetch())==[expected[0],(T+timedelta(seconds=5),T+timedelta(seconds=6),50)]
    with closing(advisory_db.connect_owner()) as connection,connection:
        with connection.cursor() as cursor:
            cursor.execute(f'REVOKE SELECT ON {provider} FROM advisory_assessor')
    with pytest.raises(ShadeHistoryV2Unavailable,match='^v2 shade history unavailable$'): fetch()
    assert all(connection.closed for connection in opened)
