"""Read original target evidence through a bounded read-only local transaction."""
from datetime import datetime,timezone,timedelta
import importlib
import pytest

NOW=datetime(2026,10,15,2,tzinfo=timezone.utc)

class Connection:
    def __init__(self,rows):self.rows=rows;self.closed=False;self.calls=[]
    def get_transaction_status(self):return 0
    def set_session(self,**kwargs):self.session=kwargs
    def cursor(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query,params=None):self.query=query;self.calls.append((query,params))
    def fetchone(self):return ('on',) if 'transaction_read_only' in self.query else ('repeatable read',)
    def fetchall(self):return [(613,)] if 'public.items' in self.query else self.rows
    def close(self):self.closed=True


def test_bounded_read_retains_latest_null_and_previous_row():
    api=importlib.import_module('household_battery_source');rows=[(NOW,None),(NOW-timedelta(seconds=1),'{}')];db=Connection(rows)
    packet=api.fetch_endpoint(lambda:db,target_at=NOW,remaining=lambda:10.,clock=lambda:NOW+timedelta(minutes=5))
    assert packet['rows']==[[NOW.isoformat(),None],[(NOW-timedelta(seconds=1)).isoformat(),'{}']]
    assert db.closed and db.session==dict(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
    query,params=next((q,p) for q,p in db.calls if 'FROM public.item0613 ' in q)
    assert 'ORDER BY time DESC LIMIT 2' in query and 'octet_length' in query
    assert params==(NOW-timedelta(seconds=120),NOW)
    assert next(p for q,p in db.calls if 'public.items' in q)==('BMS_SOC_Evidence_JSON',)


@pytest.mark.parametrize('damage',['tie','future','timeout','readonly'])
def test_source_closes_connection_on_invalid_original_query(damage):
    api=importlib.import_module('household_battery_source');db=Connection([(NOW,None),(NOW-timedelta(seconds=1),'{}')])
    if damage=='tie':db.rows[1]=(NOW,'{}')
    if damage=='future':db.rows[0]=(NOW+timedelta(seconds=1),None)
    if damage=='readonly':db.fetchone=lambda:('off',)
    ticks=iter([10.,10.,10.,0.]) if damage=='timeout' else None
    with pytest.raises(ValueError):api.fetch_endpoint(lambda:db,target_at=NOW,remaining=(lambda:next(ticks)) if ticks else lambda:10.,clock=lambda:NOW+timedelta(minutes=5))
    assert db.closed
