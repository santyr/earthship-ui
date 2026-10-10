"""Collector behavior against real immutable origins and native raw fixtures."""
from datetime import timedelta
import importlib,importlib.util,json
import pytest
from test_forecast_temperature_origin import setup
from test_forecast_temperature_score import case
from forecast_input_capture import _instant
from forecast_temperature_score import read_sources


def module():
    assert importlib.util.find_spec('forecast_temperature_collection') is not None, 'missing original outcome collector'
    return importlib.import_module('forecast_temperature_collection')


class Sources:
    def __init__(self,packet):self.packet=packet;self.reads=0
    def publication(self,origin):
        self.reads+=1;return self.packet['publication_receipt']
    def native(self,*,start,end,assessed_at):
        self.reads+=1;return self.packet['native_rows']
    def verify_unchanged(self):pass


def run(case,tmp_path,backend=None,assessed=None):
    root,p=case;out=tmp_path/'packets';out.mkdir(mode=0o700,exist_ok=True)
    return module().collect_target(origin_directory=root,origin_sha256=p['origin_sha256'],target=p['target'],
        assessed_at=assessed or p['assessed_at'],output_directory=out,backend=backend or Sources(p))


def test_retains_raw_sources_and_first_qualified_packet(case,tmp_path):
    root,p=case;backend=Sources(p);result=run(case,tmp_path,backend)
    assert result['status']=='qualified' and result['release_authority'] is False
    path=tmp_path/'packets'/result['source_packet'];retained=read_sources(path.parent,path)
    assert retained['native_rows']==p['native_rows'] and retained['publication_receipt']==p['publication_receipt']
    later=(_instant(p['assessed_at'])+timedelta(hours=1)).isoformat()
    repeated=run(case,tmp_path,backend,assessed=later)
    assert repeated['source_packet']==result['source_packet'] and repeated['status']=='already_qualified'
    assert backend.reads==2


def test_pending_never_reads_or_writes_source_packet(case,tmp_path):
    _,p=case;backend=Sources(p)
    result=run(case,tmp_path,backend,assessed=(_instant(p['target'])+timedelta(minutes=4)).isoformat())
    assert result['status']=='pending' and backend.reads==0
    assert not list((tmp_path/'packets').glob('*.json'))


def test_withheld_retained_without_becoming_qualified(case,tmp_path):
    _,p=case;backend=Sources(p);backend.packet={**p,'native_rows':[]}
    result=run(case,tmp_path,backend)
    assert result['status']=='withheld' and result['release_authority'] is False
    assert read_sources(tmp_path/'packets',tmp_path/'packets'/result['source_packet'])['native_rows']==[]
    good=run(case,tmp_path,Sources(p))
    assert good['status']=='qualified' and good['source_packet']!=result['source_packet']


def test_mismatched_receipt_is_not_retained(case,tmp_path):
    _,p=case;backend=Sources({**p,'publication_receipt':{**p['publication_receipt'],'state':p['publication_receipt']['state']+' '}})
    with pytest.raises(ValueError):run(case,tmp_path,backend)
    assert not list((tmp_path/'packets').glob('*.json'))


def test_overlapping_collection_skips_reads(case,tmp_path):
    import fcntl
    out=tmp_path/'packets';out.mkdir(mode=0o700)
    with (out/'collection.lock').open('w') as lock:
        import os;os.chmod(lock.name,0o600)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        _,p=case;backend=Sources(p);result=run(case,tmp_path,backend)
    assert result['status']=='busy' and backend.reads==0
