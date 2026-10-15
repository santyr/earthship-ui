"""The daily learner acquires bounded, original AC rows through a reader only."""
from datetime import timedelta
from test_household_ac_load_sources import START,raw
import importlib
import pytest


class Cursor:
    def __init__(self,owner):self.owner=owner;self.last=''
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query,args=None):self.last=query;self.owner.calls.append((query,args))
    def fetchone(self):return ('on',) if self.owner.readonly else ('off',)
    def fetchall(self):
        if 'public.items' in self.last:return self.owner.mapping
        return self.owner.rows


class Connection:
    def __init__(self):self.calls=[];self.rows=[(START,raw(START))];self.mapping=[(613,)];self.readonly=True;self.closed=False
    def set_session(self,**kw):self.session=kw
    def cursor(self):return Cursor(self)
    def close(self):self.closed=True


def capture(conn,*,clocks=None):
    api=importlib.import_module('household_ac_load_transport');end=START+timedelta(days=1)
    clocks=iter(clocks or [end+timedelta(seconds=1),end+timedelta(seconds=2)])
    def connect(*,remaining):assert remaining()==10.;return conn
    return api.capture_day(connect=connect,start=START,end=end,clock=lambda:next(clocks),remaining=lambda:10.)


def test_bounded_readonly_original_capture_and_connection_close():
    conn=Connection();source=capture(conn)
    assert conn.closed and conn.session==dict(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
    assert source['rows']==[[START.isoformat(),raw(START)]] and source['item_id']==613
    query,args=next((q,a) for q,a in conn.calls if 'FROM public.item0613' in q)
    assert 'LIMIT 20001' in query and 'octet_length' in query and 'ELSE NULL' in query
    assert args==(START-timedelta(seconds=120),START+timedelta(days=1))
    assert any('statement_timeout' in q and '2000ms' in q for q,_ in conn.calls)
    assert any('lock_timeout' in q and '1000ms' in q for q,_ in conn.calls)
    assert any('idle_in_transaction_session_timeout' in q and '5000ms' in q for q,_ in conn.calls)
    assert all(q.split()[0] in {'SET','SHOW','SELECT'} for q,_ in conn.calls)


@pytest.mark.parametrize('damage',['mapping_missing','mapping_duplicate','mapping_text','mapping_negative','writeable','too_many','future','late','bad_row'])
def test_capture_refuses_ambiguous_unbounded_or_late_original_and_always_closes(damage):
    conn=Connection();end=START+timedelta(days=1);clocks=None
    if damage=='mapping_missing':conn.mapping=[]
    elif damage=='mapping_duplicate':conn.mapping=[(613,),(614,)]
    elif damage=='mapping_text':conn.mapping=[('613',)]
    elif damage=='mapping_negative':conn.mapping=[(-1,)]
    elif damage=='writeable':conn.readonly=False
    elif damage=='too_many':conn.rows=[(START,raw(START))]*20001
    elif damage=='future':clocks=[end-timedelta(seconds=1),end]
    elif damage=='late':clocks=[end,end+timedelta(seconds=16)]
    else:conn.rows=[(START,'x'*4097)]
    with pytest.raises(ValueError):capture(conn,clocks=clocks)
    assert conn.closed
