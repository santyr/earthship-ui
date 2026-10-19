"""Foreign-source refusal and recovery of failed attended calendar handoffs."""
import importlib.util
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import pytest


def tools():
 p=Path(__file__).with_name('migrate-sun-calendar-items.py');s=importlib.util.spec_from_file_location('closed_sun_handoff',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def test_atomic_source_install_and_owned_withdrawal(tmp_path):
 m=tools();store=m.SourceStore(tmp_path/'sun-calendar.items')
 store.install();assert store.target.read_bytes()==m.d.checked_source()
 store.withdraw();assert not store.target.exists()


@pytest.mark.parametrize('symlink',[False,True])
def test_foreign_target_refuses_install_or_deletion(tmp_path,symlink):
 m=tools();target=tmp_path/'sun-calendar.items';other=tmp_path/'foreign';other.write_bytes(b'foreign')
 if symlink:target.symlink_to(other)
 else:target.write_bytes(b'foreign')
 store=m.SourceStore(target)
 with pytest.raises(RuntimeError):store.install()
 with pytest.raises(RuntimeError):store.withdraw()
 assert other.read_bytes()==b'foreign' and (target.is_symlink() if symlink else target.read_bytes()==b'foreign')


def test_identical_replacement_is_not_owned(tmp_path):
 m=tools();store=m.SourceStore(tmp_path/'sun-calendar.items');store.install()
 replacement=tmp_path/'replacement';replacement.write_bytes(m.d.checked_source());replacement.replace(store.target)
 with pytest.raises(RuntimeError):store.withdraw()
 assert store.target.read_bytes()==m.d.checked_source()


@pytest.mark.parametrize('failure',['withdraw_managed','install_file','verify_file','withdraw_file','restore_managed','verify_managed'])
def test_failed_phase_recovers_original_managed_provider(failure):
 m=tools();events=[]
 class Ops:
  def __getattr__(self,n):
   def call():
    events.append(n)
    if n==failure:raise RuntimeError('lost acknowledgement')
   return call
 with pytest.raises(RuntimeError):m.handoff(Ops())
 assert events[-1]=='recover_managed'


def test_sun_semantic_representative_can_change_but_complete_edges_must_match():
 m=tools()
 def fixture(point):
  return {'items':[{'name':'Sun','type':'Group','tags':['Equipment'],'groupNames':[],
    'members':[{'name':'A'},{'name':'B'}],'metadata':{'semantics':{'value':'Equipment','config':{'hasPoint':point},'editable':False}}},
    *[{'name':n,'type':'DateTime','tags':['Point'],'groupNames':['Sun'],
       'metadata':{'semantics':{'value':'Point','config':{'isPointOf':'Sun'},'editable':False}}} for n in ['A','B']]],'links':[],'rules':[],'things':[]}
 assert m.normalized(fixture('A'))==m.normalized(fixture('B'))
 bad=fixture('outside')
 with pytest.raises(RuntimeError):m.normalized(bad)
 changed=fixture('B');changed['items'][-1]['groupNames']=[]
 with pytest.raises(RuntimeError):m.normalized(changed)


def test_retired_binding_metadata_changes_are_definition_drift():
 m=tools();uid='openmeteo:forecast:local:site';left={'things':{uid:{'properties':{'last-updated':'2026-10-06T12:00:00Z'},'label':'same'}},'items':{},'links':{},'rules':{}}
 assert m.compare(left,deepcopy(left))==[]
 right=deepcopy(left);right['things'][uid]['properties']['last-updated']='2026-10-06T13:00:00Z'
 with pytest.raises(RuntimeError):m.compare(left,right)
 right['things'][uid]['label']='changed'
 with pytest.raises(RuntimeError):m.compare(left,right)


def test_foreign_source_before_withdrawal_performs_no_requests(tmp_path,monkeypatch):
 m=tools();target=tmp_path/'sun-calendar.items';target.write_bytes(b'foreign')
 ops=m.Operations.__new__(m.Operations);ops.store=m.SourceStore(target);ops.changed=False
 calls=[];ops.ready=lambda managed:True;ops.preserved=lambda:calls.append('preserved');ops.mutate=lambda *args:calls.append('mutation')
 with pytest.raises(RuntimeError):ops.withdraw_managed()
 assert calls==[] and ops.changed is False and target.read_bytes()==b'foreign'


def test_rollback_repairs_missing_link_before_full_derived_metadata_validation(monkeypatch):
 m=tools();ops=m.Operations.__new__(m.Operations);ops.store=SimpleNamespace(withdrawal_pending=False);row=m.d.specification();name='Sun_Spring'
 selected={n:{**deepcopy(r['item']),'editable':True,'state':'2030-01-01T00:00:00Z'} for n,r in row.items()}
 selected[name]['stateDescription']=None;selected[name]['unitSymbol']=None
 ops.get=lambda path:[] if path=='/links' else selected[path.split('/')[2].split('?')[0]]
 writes=[];ops.mutate=lambda method,path,body=None:writes.append((method,path,body))
 ops.restore_managed()
 assert len(writes)==8 and all(path.startswith('/links/') for _,path,_ in writes)


@pytest.mark.parametrize('lost',['DELETE-link','DELETE-item','PUT-item','PUT-link'])
def test_actual_restore_recovers_lost_ack_after_definition_was_applied(tmp_path,lost):
 m=tools();spec=m.d.specification();state={n:{**deepcopy(r['item']),'editable':True,'state':'2030-01-01T00:00:00Z'} for n,r in spec.items()};links=[{**deepcopy(r['link']),'editable':True} for r in spec.values()]
 for n in state:
  if n=='Sun_Eclipse_PartialElevation':state[n]['state']='1.5 °'
 class Ops(m.Operations):
  def __init__(self):self.store=m.SourceStore(tmp_path/'sun-calendar.items');self.changed=False;self.failure=False;self.phase=0
  def get(self,path):return links if path=='/links' else state.get(path.split('/')[2].split('?')[0])
  def mutate(self,method,path,body=None):
   m.d.allowed_mutation(method,path,body);kind='link' if path.startswith('/links/') else 'item';n=path.split('/')[2]
   if method=='DELETE':
    if kind=='link':links[:]=[x for x in links if x['itemName']!=n];state[n]['unitSymbol']=None;state[n]['stateDescription']=None
    else:state.pop(n,None)
   elif kind=='item':state[n]={**deepcopy(spec[n]['item']),'editable':True,'state':'2030-01-01T00:00:00Z'};state[n]['stateDescription']=None;state[n]['unitSymbol']=None
   else:
    links.append({**deepcopy(body),'editable':True});state[n].update(deepcopy(spec[n]['item']));state[n]['state']='1.5 °' if n=='Sun_Eclipse_PartialElevation' else '2030-01-01T00:00:00Z'
   if method+'-'+kind==lost and not self.failure:self.failure=True;raise RuntimeError('server applied write, response lost')
  def preserved(self,managed=True):return {'at':'now'},[]
  def install_file(self):
   super().install_file();state.update({n:{**deepcopy(r['item']),'editable':False,'state':'1.5 °' if n=='Sun_Eclipse_PartialElevation' else '2030-01-01T00:00:00Z'} for n,r in spec.items()});links.extend({**deepcopy(r['link']),'editable':False} for r in spec.values())
  def withdraw_file(self):self.store.withdraw();state.clear();links.clear()
  def verify_file(self):assert self.ready(False)
  def verify_managed(self):assert self.ready(True)
 ops=Ops()
 # Exercise real recovery methods, while keeping receipt storage disposable.
 ops.directory=tmp_path
 with pytest.raises(RuntimeError):m.handoff(ops)
 assert ops.failure and ops.ready(True) and not ops.store.target.exists()
 assert (tmp_path/'failure-managed-recovery.json').exists()


def test_snapshot_fetches_full_sun_membership_after_shallow_item_census(monkeypatch):
 m=tools();calls=[]
 def get(path):
  calls.append(path)
  if path=='/items?metadata=.*':return [{'name':'Sun','type':'Group','members':[]},{'name':'A','groupNames':['Sun']}]
  if path=='/items/Sun?metadata=.*':return {'name':'Sun','type':'Group','members':[{'name':'A'}]}
  return []
 monkeypatch.setattr(m,'get',get);monkeypatch.setattr(m.subprocess,'check_output',lambda *args,**kw:'1696\n')
 result=m.snapshot()
 assert result['items'][0]['members']==[{'name':'A'}] and '/items/Sun?metadata=.*' in calls


@pytest.mark.parametrize('failure',['sync_after_unlink','read_after_unlink'])
def test_recovery_waits_for_known_file_withdrawal_when_path_already_gone(tmp_path,monkeypatch,failure):
 m=tools();store=m.SourceStore(tmp_path/'sun-calendar.items');store.install();spec=m.d.specification()
 state={n:{**deepcopy(r['item']),'editable':False,'state':'1.5 °' if n=='Sun_Eclipse_PartialElevation' else '2030-01-01T00:00:00Z'} for n,r in spec.items()};links=[{**deepcopy(r['link']),'editable':False} for r in spec.values()]
 real_sync=m.sync
 if failure=='sync_after_unlink':
  monkeypatch.setattr(m,'sync',lambda _:(_ for _ in ()).throw(RuntimeError('directory sync failed after unlink')))
  with pytest.raises(RuntimeError):store.withdraw()
 else:store.withdraw()
 monkeypatch.setattr(m,'sync',real_sync);monkeypatch.setattr(m.time,'sleep',lambda _:None)
 assert not store.target.exists()
 class Ops(m.Operations):
  def __init__(self):self.store=store;self.changed=True;self.directory=tmp_path;self.polls=0
  def get(self,path):return links if path=='/links' else state.get(path.split('/')[2].split('?')[0])
  def absent(self):
   self.polls+=1
   if failure=='read_after_unlink' and self.polls==1:raise RuntimeError('withdrawal transport failure')
   if self.polls<3:return False
   state.clear();links.clear();return True
  def mutate(self,method,path,body=None):
   n=path.split('/')[2]
   if path.startswith('/items/'):state[n]={**deepcopy(spec[n]['item']),'editable':True,'state':'1.5 °' if n=='Sun_Eclipse_PartialElevation' else '2030-01-01T00:00:00Z'}
   else:links.append({**deepcopy(body),'editable':True})
  def preserved(self,managed=True):return {},[]
 ops=Ops();ops.recover_managed()
 assert ops.polls>=3 and ops.ready(True) and (tmp_path/'failure-managed-recovery.json').exists()


@pytest.mark.parametrize('status,detail',[('UNINITIALIZED','DISABLED'),('UNINITIALIZED','HANDLER_INITIALIZING_ERROR')])
def test_preservation_rejects_new_disabled_or_unhealthy_rules(monkeypatch,status,detail):
 m=tools();base={'items':[],'links':[],'things':[],'pid':'1696','rules':[{'uid':'protected','tags':[],'status':{'status':'IDLE','statusDetail':'NONE'}}]};current=deepcopy(base);current['rules'][0]['status']={'status':status,'statusDetail':detail}
 from contextlib import nullcontext
 ops=m.Operations.__new__(m.Operations);ops.before=base;ops.pins={};ops.prefixes={};ops.db=nullcontext()
 monkeypatch.setattr(m,'snapshot',lambda:current);monkeypatch.setattr(m,'sources',lambda:{})
 # Stub pure definition comparison: exercise the distinct runtime health gate.
 monkeypatch.setattr(m,'normalized',lambda _: {'things':{},'items':{n:{'editable':True} for n in m.d.IDS},'links':{n+' -> '+r['link']['channelUID']:{'editable':True} for n,r in m.d.specification().items()},'rules':{}})
 with pytest.raises(RuntimeError,match='rule'):ops.preserved()


@pytest.mark.parametrize('field,value',[('transport_sha256','0'*64),('full_jvm_restart',False),('owned_fixture_removed',False)])
def test_transport_release_requires_current_exact_native_proof(field,value):
 from hashlib import sha256
 m=tools();proof={'transport_sha256':sha256(Path(m.__file__).read_bytes()).hexdigest(),'source_sha256':m.d.SOURCE_SHA,'specification_sha256':m.d.SPEC_SHA,'items':8,'links':8,'production_writes':0,'exact_transport_native_round_trip':True,'file_phases':2,'original_managed_rollback':True,'full_jvm_restart':True,'owned_fixture_removed':True}
 m.validate_transport(proof);proof[field]=value
 with pytest.raises(RuntimeError):m.validate_transport(proof)


@pytest.mark.parametrize('persistent',[False,True])
def test_failed_unlink_sync_is_retried_before_any_managed_put(tmp_path,monkeypatch,persistent):
 m=tools();store=m.SourceStore(tmp_path/'sun-calendar.items');store.install();events=[];real_sync=m.sync
 def sync(path):
  events.append('sync')
  if persistent or events.count('sync')==1:raise RuntimeError('directory sync failure')
  return real_sync(path)
 monkeypatch.setattr(m,'sync',sync)
 with pytest.raises(RuntimeError):store.withdraw()
 assert not store.target.exists()
 ops=m.Operations.__new__(m.Operations);ops.store=store;ops.get=lambda path:[] if path=='/links' else None;ops.absent=lambda:True
 ops.mutate=lambda *args:events.append('PUT')
 if persistent:
  with pytest.raises(RuntimeError):ops.restore_managed()
  assert 'PUT' not in events and store.withdrawal_pending
 else:
  ops.restore_managed()
  assert events[:3]==['sync','sync','PUT'] and not store.withdrawal_pending
