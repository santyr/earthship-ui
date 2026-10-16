from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import json
import pytest
s=spec_from_file_location('file_batch',Path(__file__).with_name('file_migration_batch.py'))
m=module_from_spec(s);s.loader.exec_module(m)

def item(name='Moon_Azimuth',editable=True):
 return {'name':name,'type':'Number:Angle','label':'Azimuth','category':'','groupNames':['Moon'],'tags':['Point'],'metadata':{'semantics':{'value':'Point','config':{'isPointOf':'Moon'},'editable':False}},'unitSymbol':'°','stateDescription':{'pattern':'%.2f °','readOnly':True},'editable':editable,'state':'100 °'}

def test_definition_preserves_unit_semantics_and_ignores_only_empty_category_provider_and_state():
 a=item();b=item(editable=False);b['category']=None;b['state']='101 °'
 assert m.item_definition(a)==m.item_definition(b)
 for key,value in [('unitSymbol','rad'),('tags',[]),('groupNames',[]),('stateDescription',{}),('metadata',{})]:
  c=deepcopy(b);c[key]=value
  assert m.item_definition(a)!=m.item_definition(c)

@pytest.mark.parametrize('method,path',[('POST','/items/Moon_Azimuth'),('PUT','/items/BMS_SOC'),('DELETE','/things/astro:moon:local?force=true'),('POST','/rules/hex_southoutlet_cycle/runnow'),('PUT','/items/Moon_Azimuth/state'),('DELETE','/links/Sun_Position_Elevation/astro%3Asun%3Alocal%3Aposition%23elevation')])
def test_mutations_outside_exact_scope_refused_before_auth(monkeypatch,method,path):
 monkeypatch.setattr(m,'read_token',lambda:pytest.fail('auth requested'))
 with pytest.raises(RuntimeError):m.request(method,path)

def test_wrong_item_link_target_refuses():
 with pytest.raises(RuntimeError):m.allowed_request('PUT','/links/Moon_Azimuth/astro%3Asun%3Alocal%3Aposition%23azimuth',{})

def test_correct_scope_includes_only_original_configuration_restoration():
 spec=m.specification();n='Moon_Azimuth';row=spec['moon'][n];channel=row['link']['channelUID']
 assert m.allowed_request('DELETE','/items/'+n,None)
 assert m.allowed_request('PUT','/items/'+n,{k:row['item'][k] for k in m.ITEM_WRITABLE if k in row['item']})
 with pytest.raises(RuntimeError):m.allowed_request('PUT','/items/'+n,{'name':n,'type':'Switch'})
 assert m.allowed_request('DELETE','/things/http:url:weatherTemperatureEvidence?force=true',None)

@pytest.mark.parametrize('suffix',['items/moon-display-readings.items','things/weather-temperature-evidence.things'])
def test_missing_or_drifting_source_fails_before_network(tmp_path,monkeypatch,suffix):
 monkeypatch.setattr(m,'ROOT',tmp_path)
 with pytest.raises((RuntimeError,FileNotFoundError)):m.checked_source('moon' if suffix.startswith('items') else 'weather')

def test_thing_signature_preserves_channel_fields_and_all_configuration():
 t={'UID':'http:url:weatherTemperatureEvidence','thingTypeUID':'http:url','configuration':{'refresh':30},'label':'Temperature','properties':{'thingTypeVersion':'2'},'channels':[{'id':'snapshot','uid':'http:url:weatherTemperatureEvidence:snapshot','label':'Snapshot','defaultTags':[],'configuration':{'mode':'READONLY'},'linkedItems':['Weather_Temperature_Evidence_JSON']}],'editable':True,'statusInfo':{'status':'ONLINE'}}
 c=deepcopy(t);c['editable']=False;c['statusInfo']['status']='UNKNOWN'
 assert m.thing_definition(t)==m.thing_definition(c)
 for key,value in [('label','Changed'),('configuration',{'refresh':1})]:
  c=deepcopy(t);c[key]=value;assert m.thing_definition(t)!=m.thing_definition(c)
 c=deepcopy(t);c['channels'][0]['defaultTags']=['Measurement'];assert m.thing_definition(t)!=m.thing_definition(c)

def test_specification_has_exact_frozen_scope_and_no_states_or_credentials():
 spec=m.specification();assert len(spec['moon'])==25
 for name,row in spec['moon'].items():
  assert name.startswith('Moon_') and row['link']['channelUID'].startswith('astro:moon:local:')
  assert 'state' not in row['item'] and type(row['jdbc_id']) is int
 assert spec['weather']['jdbc_id']==646
 raw=json.dumps(spec).lower()
 assert 'password' not in raw and 'openhab_token' not in raw

def test_specification_drift_refuses_arbitrary_added_target(tmp_path,monkeypatch):
 base=tmp_path/'openhab/file-config';base.mkdir(parents=True)
 (base/'moon-weather-migration.json').write_text('{"moon":{"BMS_SOC":{}},"weather":{}}')
 monkeypatch.setattr(m,'ROOT',tmp_path)
 with pytest.raises(RuntimeError,match='specification changed'):m.specification()

def test_closed_gate_refuses_install_before_source_or_filesystem(monkeypatch):
 monkeypatch.setattr(m,'LIVE_RELEASE_READY',False)
 monkeypatch.setattr(m,'checked_source',lambda *_:pytest.fail('source access'))
 with pytest.raises(RuntimeError,match='release gate'):m.install_exclusive('moon')

def test_closed_gate_refuses_withdrawal_before_filesystem(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'LIVE_RELEASE_READY',False)
 with pytest.raises(RuntimeError,match='release gate'):m.withdraw_owned('moon',tmp_path)

def test_original_thing_recreation_uses_collection_post_with_exact_uid_and_body():
 spec=m.specification();body=m.managed_thing_dto(spec['weather']['thing'])
 assert m.allowed_request('POST','/things',body)
 bad=deepcopy(body);bad['UID']='http:url:unapproved'
 with pytest.raises(RuntimeError):m.allowed_request('POST','/things',bad)
 with pytest.raises(RuntimeError):m.allowed_request('PUT','/things/'+body['UID'],body)

def test_thing_restoration_omits_binding_generated_channels_and_linked_item_readback():
 body=m.managed_thing_dto(m.specification()['weather']['thing'])
 assert [c['id'] for c in body['channels']]==['snapshot']
 assert 'linkedItems' not in body['channels'][0]
 assert body['channels'][0]['defaultTags']==[] and body['channels'][0]['properties']=={}

def test_atomic_install_is_complete_exclusive_and_cleans_pending(tmp_path,monkeypatch):
 monkeypatch.setattr(m,'LIVE_RELEASE_READY',True);monkeypatch.setattr(m,'DESTINATION_ROOT',tmp_path)
 monkeypatch.setattr(m,'checked_source',lambda kind:b'complete definition\n')
 from hashlib import sha256
 monkeypatch.setitem(m.SOURCE_HASHES,'moon',sha256(b'complete definition\n').hexdigest())
 (tmp_path/'items').mkdir();target=m.install_exclusive('moon')
 assert target.read_bytes()==b'complete definition\n' and target.stat().st_mode&0o777==0o644
 with pytest.raises(FileExistsError):m.install_exclusive('moon')
 assert target.read_bytes()==b'complete definition\n' and list((tmp_path/'items').iterdir())==[target]

class Operations:
 def __init__(self,fail=0):self.events=[];self.verified=0;self.fail=fail
 def backup(self):self.events.append('backup')
 def withdraw_managed(self):self.events.append('withdraw_managed')
 def install_file(self):self.events.append('install_file')
 def verify_file(self):
  self.events.append('verify_file');self.verified+=1
  if self.verified==self.fail:raise RuntimeError('injected provider failure')
 def withdraw_file(self):self.events.append('withdraw_file')
 def restore_managed(self):self.events.append('restore_managed')
 def verify_managed(self):self.events.append('verify_managed')
 def recover_managed(self):self.events.append('recover_managed')

def test_handoff_exercises_actual_managed_rollback_before_final_file():
 ops=Operations();m.handoff(ops)
 assert ops.events==['backup','withdraw_managed','install_file','verify_file','withdraw_file','restore_managed','verify_managed','withdraw_managed','install_file','verify_file']

@pytest.mark.parametrize('failure',[1,2])
def test_each_file_verification_failure_attempts_original_managed_recovery(failure):
 ops=Operations(failure)
 with pytest.raises(RuntimeError,match='provider failure'):m.handoff(ops)
 assert ops.events[-1]=='recover_managed'

def test_second_failure_recovery_can_withdraw_source_after_prior_rollback(tmp_path,monkeypatch):
 from hashlib import sha256
 monkeypatch.setattr(m,'LIVE_RELEASE_READY',True);monkeypatch.setattr(m,'DESTINATION_ROOT',tmp_path)
 body=b'complete definition\n';monkeypatch.setitem(m.SOURCE_HASHES,'moon',sha256(body).hexdigest())
 (tmp_path/'items').mkdir();backup=tmp_path/'private';backup.mkdir()
 target=tmp_path/'items/moon-display-readings.items';target.write_bytes(body)
 first=m.withdraw_owned('moon',backup);target.write_bytes(body)
 second=m.withdraw_owned('moon',backup)
 assert first!=second and first.read_bytes()==second.read_bytes()==body and not target.exists()
