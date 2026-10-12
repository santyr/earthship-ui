"""Capture integration exercises the unchanged actual provisional publisher."""
from copy import deepcopy
from datetime import datetime,timedelta
import importlib,json
from pathlib import Path
import pytest
from test_provisional_thermal_live import fixture,module as live
from test_provisional_thermal_forecast import ISSUE

def api():return importlib.import_module('household_cycle')

def test_collection_follows_parent_inputs_and_keeps_original_numeric_output(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    direct=live().publish_cycle(settings,backend=parent,guard=lambda:None)
    capture=json.loads(Path(direct['origin_path']).read_bytes());original=capture['output']
    issued=datetime.fromisoformat(capture['issued_at'])
    clock[0]=ISSUE-timedelta(seconds=30);calls=[]
    original_collect=parent.collect
    def collect_parent(**kw):
        value=original_collect(**kw);calls.append('parent');clock[0]+=timedelta(seconds=10);return value
    parent.collect=collect_parent
    def collect_household(*,issue,remaining,guard):
        calls.append('household');assert issue==issued
        assert 0 < remaining() <= 6
        guard();clock[0]+=timedelta(seconds=1)
        return {'original_collection_finished':clock[0].isoformat()}
    adapter=api().ObservingBackend(parent,collector=collect_household,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert calls==['parent','household']
    assert result['delivery_verified'] is True
    wrapped=json.loads(Path(result['origin_path']).read_bytes())['output']
    assert wrapped==original
    assert adapter.collection['status']=='collected'
    assert adapter.collection['originals']['original_collection_finished']==(issued-timedelta(seconds=9)).isoformat()

def test_collector_failure_does_not_withdraw_or_break_original_delivery(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    def broken(**kwargs):raise ValueError('operator-only diagnostic payload')
    adapter=api().ObservingBackend(parent,collector=broken,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'
    assert 'operator-only' not in json.dumps(adapter.collection)

def test_late_window_skips_observation_and_keeps_forecast_delivery(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    original=parent.collect
    def late(**kwargs):
        value=original(**kwargs);clock[0]=kwargs['issue']-timedelta(seconds=2);return value
    parent.collect=late
    def forbidden(**kwargs):pytest.fail('late collector started')
    adapter=api().ObservingBackend(parent,collector=forbidden,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['reason']=='insufficient_preissue_budget'

def test_parent_collection_failure_is_not_hidden(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    def broken(**kwargs):raise ValueError('original collection failed')
    parent.collect=broken
    adapter=api().ObservingBackend(parent,collector=lambda **kw:{},guard=lambda:None,clock=lambda:clock[0])
    with pytest.raises(ValueError,match='original collection failed'):
        live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert parent.puts==[]

def test_collection_cannot_renew_the_total_preissue_budget(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch);ticks=[0.]
    def overrun(**kwargs):
        ticks[0]+=7;clock[0]+=timedelta(seconds=7)
        return {'originals':'not accepted after budget'}
    adapter=api().ObservingBackend(parent,collector=overrun,guard=lambda:None,clock=lambda:clock[0],monotonic=lambda:ticks[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'
    assert 'originals' not in adapter.collection

def test_backward_collection_clock_refuses_household_originals(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch);offset=[0]
    def backward(**kwargs):
        offset[0]=1
        return {'captured_at':clock[0].isoformat()}
    adapter=api().ObservingBackend(parent,collector=backward,guard=lambda:None,clock=lambda:clock[0]-timedelta(seconds=offset[0]))
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'
