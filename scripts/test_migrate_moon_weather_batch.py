from pathlib import Path
import importlib.util
import pytest
s=importlib.util.spec_from_file_location('moon_weather_live_tests',Path(__file__).with_name('migrate-moon-weather-batch.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_default_apply_gate_refuses_before_credentials_db_or_live_reads(monkeypatch):
 monkeypatch.setattr(m.b,'LIVE_RELEASE_READY',False)
 monkeypatch.setattr(m,'parse_openhab_jdbc_config',lambda *_:pytest.fail('private credentials'))
 monkeypatch.setattr(m.b.oh,'get',lambda *_:pytest.fail('REST'))
 with pytest.raises(RuntimeError,match='release gate'):m.main(['--kind','moon','--apply'])

@pytest.mark.parametrize('name,identity',[('BMS_SOC',646),('Moon_Azimuth',646),('Weather_Temperature_Evidence_JSON',44)])
def test_history_refuses_wrong_identity_before_database(name,identity):
 with pytest.raises(RuntimeError,match='history outside exact scope'):m.history(None,name,identity)

def test_streamed_backup_digest_is_bounded_and_preserves_exact_csv(monkeypatch):
 import io
 from hashlib import sha256
 output=io.BytesIO();writer=m.DigestWriter(output)
 writer.write('time,value\n');writer.write(b'original\n')
 assert writer.digest.hexdigest()==sha256(output.getvalue()).hexdigest()
 monkeypatch.setattr(m,'MAX_HISTORY_BYTES',writer.size)
 with pytest.raises(RuntimeError,match='bound'):writer.write(b'not silently truncated')

def test_ready_checks_all_items_and_each_original_link(monkeypatch):
 from copy import deepcopy
 spec=m.b.specification();ops=object.__new__(m.Operations);ops.kind='moon';ops.spec=spec
 originals={n:{**deepcopy(r['item']),'editable':False,'state':'native-populated'} for n,r in spec['moon'].items()}
 links=[{**deepcopy(r['link']),'editable':False} for r in spec['moon'].values()]
 monkeypatch.setattr(m,'item',lambda n:originals[n]);monkeypatch.setattr(m.b.oh,'get',lambda _:links)
 assert ops.ready(False)
 links[0]['channelUID']='astro:moon:local:unapproved'
 assert not ops.ready(False)

def test_recovery_never_removes_unknown_source_or_calls_other_resources(monkeypatch,tmp_path):
 ops=object.__new__(m.Operations);ops.kind='moon';ops.changed=True;ops.directory=tmp_path
 monkeypatch.setattr(m.b,'DESTINATION_ROOT',tmp_path);(tmp_path/'items').mkdir();(tmp_path/'items/moon-display-readings.items').write_text('unexpected source')
 monkeypatch.setattr(m.b,'LIVE_RELEASE_READY',True)
 monkeypatch.setattr(ops,'restore_managed',lambda:pytest.fail('unsafe restoration'))
 with pytest.raises(RuntimeError,match='target drift'):ops.recover_managed()

def test_partial_link_withdrawal_repairs_original_links_before_derived_metadata_check(monkeypatch):
 from copy import deepcopy
 spec=m.b.specification();ops=object.__new__(m.Operations);ops.kind='moon';ops.spec=spec
 originals={n:{**deepcopy(r['item']),'editable':True,'state':'native-populated'} for n,r in spec['moon'].items()}
 first=next(iter(originals));originals[first]['stateDescription']=None;originals[first]['unitSymbol']=None
 links=[{**deepcopy(r['link']),'editable':True} for n,r in spec['moon'].items() if n!=first];calls=[]
 monkeypatch.setattr(m,'item',lambda n:originals[n]);monkeypatch.setattr(m.b.oh,'get',lambda _:links)
 def restore(method,path,body=None):
  calls.append((method,path,body))
  if method=='PUT' and path.startswith('/links/'):
   links.append({**body,'editable':True})
 monkeypatch.setattr(m.b,'request',restore)
 ops.restore_managed()
 assert len(calls)==1 and calls[0][2]==spec['moon'][first]['link']
 assert len(links)==25

def test_backup_directory_entries_are_durable_before_handoff_can_withdraw(monkeypatch,tmp_path):
 ops=object.__new__(m.Operations);ops.kind='moon';ops.originals={};ops.original_links=[];ops.original_thing={};ops.before={};ops.guard={}
 events=[]
 monkeypatch.setattr(m,'BACKUP_ROOT',tmp_path)
 monkeypatch.setattr(m,'sync_directory',lambda path:events.append(('sync',path)))
 monkeypatch.setattr(ops,'preserved',lambda:events.append(('verified',None)))
 ops.backup()
 assert events==[('sync',ops.directory),('sync',tmp_path),('verified',None)]
 assert (ops.directory/'preimages.json').exists() and (ops.directory/'source.before').exists()
