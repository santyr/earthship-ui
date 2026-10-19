#!/usr/bin/env python3
"""Attended closed Sun calendar handoff; default is a read-only check.

Prepare precedes explicit one-shot apply. Only eight exact Item/link definitions
can change. No production states, commands, rules, Things or service operations.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request,urlopen
import argparse,fcntl,gzip,importlib.util,json,os,secrets,stat,subprocess,time
import sun_calendar_items as d
b=d.batch
ROOT=d.ROOT
TARGET=Path('/etc/openhab/items/sun-calendar.items')
BACKUP_ROOT=Path('/home/sat/.local/state/openhab-config-migration')
s=importlib.util.spec_from_file_location('sun_history_reader',ROOT/'scripts/qualify-sky-diagnostic-items.py');q=importlib.util.module_from_spec(s);s.loader.exec_module(q);h=q.q


def sync(path):
 fd=os.open(path,os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)


def save(directory,name,value):b.private_file(directory,name,value if isinstance(value,bytes) else b.encoded(value))


def get(path):
 try:return b.oh.get(path)
 except HTTPError as e:
  if e.code==404:return None
  raise


def snapshot():
 result={'at':datetime.now(timezone.utc).isoformat(),'pid':subprocess.check_output(['systemctl','show','openhab.service','-p','MainPID','--value'],text=True).strip(),**{k:get('/'+k+('?metadata=.*' if k=='items' else '')) for k in ('items','links','things','rules')}}
 group=get('/items/Sun?metadata=.*')
 result['items']=[group if x['name']=='Sun' else x for x in result['items']]
 return result


def normalized(snap):
 items={i['name']:{**b.item_definition(i),'editable':i.get('editable'),'groupType':i.get('groupType'),'function':i.get('function'),**({'members':sorted(x['name'] for x in i['members'])} if 'members' in i else {})} for i in snap['items']}
 if 'Sun' in items:
  group=items['Sun'];members={n for n,i in items.items() if 'Sun' in i['groupNames']}
  d.require(set(group.get('members',[]))==members and len(group.get('members',[]))==len(members),'Sun membership drift')
  points={n for n in members if 'Point' in items[n]['tags']}
  for n in points:d.require(items[n]['metadata'].get('semantics',{}).get('config',{}).get('isPointOf')=='Sun','Sun semantic parent drift')
  semantics=group['metadata'].get('semantics',{})
  d.require(semantics.get('value')=='Equipment' and semantics.get('editable') is False and semantics.get('config',{}).get('hasPoint') in points,'Sun semantic representative invalid')
  # The native provider chooses one hasPoint representative by iteration order.
  # Verify it belongs to the exact graph, then compare the complete Point edges.
  group['metadata']['semantics']['config']['hasPoint']=sorted(points)
 return {'items':items,'links':{x['itemName']+' -> '+x['channelUID']:deepcopy(x) for x in snap['links']},'things':{x['UID']:{**b.thing_definition(x),'editable':x.get('editable')} for x in snap['things']},'rules':{x['uid']:{**{k:x.get(k) for k in ('uid','name','description','visibility','configuration','triggers','conditions','actions','editable')},'tags':sorted(x.get('tags',[]))} for x in snap['rules']}}


def compare(expected,actual):
 d.require(expected==actual,'unapproved definition/provider drift')
 return []


def sources():
 result={}
 for r in json.loads((ROOT/'openhab/file-config/ownership.json').read_text())['resources']:
  if r.get('provider')!='file' or not r.get('destination'):continue
  source=ROOT/r['source'] if r['source'].startswith('openhab/') else ROOT/'openhab/file-config'/r['source'];target=Path(r['destination'])
  d.require(not source.is_symlink() and not target.is_symlink() and source.read_bytes()==target.read_bytes(),'installed source drift');result[str(target)]=sha256(target.read_bytes()).hexdigest()
 return result


class SourceStore:
 def __init__(self,target=TARGET):self.target=target;self.owned=None;self.withdrawal_pending=False
 def absent(self):d.require(not self.target.exists() and not self.target.is_symlink(),'foreign watched candidate present')
 def install(self):
  self.absent();self.withdrawal_pending=False;body=d.checked_source();pending=self.target.parent/('.sun-calendar-'+secrets.token_hex(12)+'.pending')
  fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);inode=os.fstat(fd);self.owned=(inode.st_dev,inode.st_ino)
  try:
   with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
   os.link(pending,self.target,follow_symlinks=False);sync(self.target.parent)
  finally:
   if pending.exists():pending.unlink();sync(pending.parent)
 def verify(self):
  d.require(self.owned is not None and not self.target.is_symlink(),'source is not owned')
  inode=self.target.lstat();d.require((inode.st_dev,inode.st_ino)==self.owned and sha256(self.target.read_bytes()).hexdigest()==d.SOURCE_SHA,'owned source drift')
 def withdraw(self):
  self.verify();self.target.unlink();self.withdrawal_pending=True;sync(self.target.parent)


def wait(predicate,seconds=180):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  try:
   if predicate():return
  except (RuntimeError,ValueError):pass
  time.sleep(1)
 raise RuntimeError('selected provider/state recovery did not settle')


class Operations:
 def __init__(self,directory,db):
  self.directory=directory;self.db=db;self.store=SourceStore();self.changed=False;self.phase=0;self.get=get
  self.before=json.loads((directory/'before-registry.json').read_text());self.prefixes=json.loads((directory/'history-prefixes.json').read_text());self.pins=json.loads((directory/'before-sources.json').read_text())
  d.require({n:r['id'] for n,r in self.prefixes.items()}==d.IDS,'recovery history scope/identity drift')
 def mutate(self,method,path,body=None):
  d.allowed_mutation(method,path,body)
  data=None if body is None else b.encoded(body)
  with urlopen(Request(b.oh.BASE+path,method=method,data=data,headers={'Authorization':'Bearer '+b.oh.token(),'Content-Type':'application/json'}),timeout=15) as response:
   d.require(response.status in (200,201,202,204),'definition mutation refused');response.read()
  with (self.directory/'mutation-events.jsonl').open('a') as f:f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'method':method,'path':path,'status':response.status})+'\n');f.flush();os.fsync(f.fileno())
 def ready(self,managed):
  links=self.get('/links')
  try:
   for n in d.IDS:d.validate_item(self.get('/items/'+n+'?metadata=.*'),n,managed=managed);d.validate_links(links,n,managed=managed)
   return True
  except (RuntimeError,ValueError,TypeError):return False
 def absent(self):return not any(x['itemName'] in d.IDS for x in self.get('/links')) and all(self.get('/items/'+n) is None for n in d.IDS)
 def preserved(self,managed=True):
  current=snapshot();d.require(current['pid']==self.before['pid'] and int(current['pid'])>0,'production JVM changed')
  disabled=lambda rows:{r['uid'] for r in rows if r.get('status',{}).get('statusDetail')=='DISABLED'}
  originally_disabled=disabled(self.before['rules']);d.require(disabled(current['rules'])==originally_disabled,'disabled-rule set changed')
  d.require(all(r.get('status',{}).get('status') in ('IDLE','RUNNING') for r in current['rules'] if r['uid'] not in originally_disabled),'enabled rule unhealthy')
  expected=normalized(self.before)
  for n,r in d.specification().items():expected['items'][n]['editable']=managed;expected['links'][n+' -> '+r['link']['channelUID']]['editable']=managed
  advances=compare(expected,normalized(current));d.require(sources()==self.pins,'prior source pins changed')
  with self.db:
   for n,r in self.prefixes.items():d.require(h.native_history(self.db,n,r['id'],cutoff=datetime.fromisoformat(r['cutoff']))==r,'original history changed')
  return current,advances
 def withdraw_managed(self):
  self.store.absent();d.require(self.ready(True),'managed provider drift');self.preserved();self.changed=True
  for n,r in d.specification().items():self.mutate('DELETE','/links/'+n+'/'+quote(r['link']['channelUID'],safe=''))
  for n in d.IDS:self.mutate('DELETE','/items/'+n)
  wait(self.absent)
 def install_file(self):d.require(self.absent(),'managed resources not absent');self.store.install()
 def verify_file(self):
  wait(lambda:self.ready(False));self.store.verify();current,advances=self.preserved(False);self.phase+=1
  save(self.directory,'file-phase-'+str(self.phase)+'.json',{'at':current['at'],'registry':current,'original_history_prefixes_preserved':8,'binding_freshness_advances':advances,'source_sha256':d.SOURCE_SHA});print('file_phase='+str(self.phase)+' verified=true',flush=True)
 def settle_withdrawal(self):
  if self.store.withdrawal_pending:
   sync(self.store.target.parent);wait(self.absent);self.store.withdrawal_pending=False
 def withdraw_file(self):self.store.withdraw();self.settle_withdrawal()
 def restore_managed(self):
  self.settle_withdrawal()
  for n,r in d.specification().items():
   item=self.get('/items/'+n+'?metadata=.*')
   if item is None:self.mutate('PUT','/items/'+n,d.managed_item(n))
   else:
    actual=b.item_definition(item);expected=r['item']
    d.require(item.get('editable') is True and all(actual[k]==expected[k] for k in (*b.ITEM_WRITABLE,'metadata')),'foreign Item during restoration')
  links=self.get('/links')
  for n,r in d.specification().items():
   selected=[x for x in links if x['itemName']==n]
   if not selected:self.mutate('PUT','/links/'+n+'/'+quote(r['link']['channelUID'],safe=''),r['link'])
   else:d.validate_links(selected,n,managed=True)
 def verify_managed(self):
  wait(lambda:self.ready(True));current,advances=self.preserved()
  save(self.directory,'original-managed-rollback.json',{'at':current['at'],'registry':current,'original_history_prefixes_preserved':8,'binding_freshness_advances':advances});print('original_managed_rollback=verified',flush=True)
 def recover_managed(self):
  if not self.changed:return
  if self.store.target.exists() or self.store.target.is_symlink():self.withdraw_file()
  self.settle_withdrawal()
  self.restore_managed();wait(lambda:self.ready(True));self.preserved()
  save(self.directory,'failure-managed-recovery.json',{'at':datetime.now(timezone.utc).isoformat(),'original_managed_restored':True})


def handoff(ops):
 try:
  ops.withdraw_managed();ops.install_file();ops.verify_file();ops.withdraw_file();ops.restore_managed();ops.verify_managed();ops.withdraw_managed();ops.install_file();ops.verify_file()
 except BaseException:
  ops.recover_managed();raise


def qualification(directory):
 d.require(isinstance(directory,Path) and directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,'private proof directory required')
 manifest=json.loads((directory/'manifest.json').read_text())
 for n,row in manifest.items():
  d.require('/' not in n and n not in ('.','..'),'unsafe proof name');path=directory/n
  d.require(not path.is_symlink() and path.stat().st_mode&0o777==0o600 and sha256(path.read_bytes()).hexdigest()==row['sha256'],'sealed proof changed')
 return directory


def validate_transport(proof):
 d.require(proof.get('transport_sha256')==sha256(Path(__file__).read_bytes()).hexdigest()
           and proof.get('source_sha256')==d.SOURCE_SHA and proof.get('specification_sha256')==d.SPEC_SHA
           and proof.get('items')==8 and proof.get('links')==8 and proof.get('production_writes')==0
           and proof.get('file_phases')==2
           and all(proof.get(k) is True for k in ('exact_transport_native_round_trip','original_managed_rollback','full_jvm_restart','owned_fixture_removed')),'exact current transport qualification required')


def prepare(provider,jdbc,transport):
 store=SourceStore();store.absent();d.checked_source()
 provider=json.loads((qualification(provider)/'provider-proof.json').read_text());jdbc=json.loads((qualification(jdbc)/'jdbc-proof.json').read_text());transport=json.loads((qualification(transport)/'transport-proof.json').read_text());validate_transport(transport)
 for proof in (provider,jdbc):d.require(proof['source_sha256']==d.SOURCE_SHA and proof['specification_sha256']==d.SPEC_SHA and proof['items']==8 and proof['production_writes']==0,'qualification scope drift')
 d.require(provider['full_jvm_restart'] and provider['original_managed_rollback'] and provider['owned_container_removed'] and len(provider['phases'])==5,'provider qualification incomplete')
 d.require(jdbc['full_jvm_restart_state_history'] and jdbc['original_managed_state_history'] and jdbc['owned_containers_removed'],'JDBC qualification incomplete')
 before=snapshot();d.require(before['pid'].isdigit() and int(before['pid'])>0,'JVM unavailable')
 for n in d.IDS:d.validate_item(next(x for x in before['items'] if x['name']==n),n,managed=True);d.validate_links(before['links'],n,managed=True)
 normalized(before);directory=Path(__import__('tempfile').mkdtemp(prefix='sun-calendar-handoff-20261006-',dir=BACKUP_ROOT));directory.chmod(0o700)
 save(directory,'before-registry.json',before);save(directory,'before-sources.json',sources());save(directory,'source.items',d.checked_source());save(directory,'adapter.py',Path(__file__).read_bytes());save(directory,'qualification-references.json',{'provider':provider,'jdbc':jdbc,'transport':transport})
 save(directory,'mutation-events.jsonl',b'');prefixes={};db=h.connect()
 try:
  with db:
   for n,identity in d.IDS.items():
    row=h.native_history(db,n,identity);fd=os.open(directory/(n+'.csv.gz'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
     with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0,compresslevel=1) as z:copied=h.native_history(db,n,identity,cutoff=datetime.fromisoformat(row['cutoff']),output=z)
     f.flush();os.fsync(f.fileno())
    d.require(copied==row,'recoverable history mismatch');prefixes[n]=row
 finally:db.close()
 save(directory,'history-prefixes.json',prefixes)
 for filename in ['org.openhab.core.items.Item.json','org.openhab.core.thing.link.ItemChannelLink.json','users.json']:save(directory,filename,Path('/var/lib/openhab/jsondb',filename).read_bytes())
 fd=os.open(directory/'conf.tar',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:
  r=subprocess.run(['sudo','-n','tar','--sparse','--hole-detection=seek','-cf','-','-C','/etc/openhab','.'],stdout=f,stderr=subprocess.PIPE);d.require(r.returncode==0,'configuration backup failed');f.flush();os.fsync(f.fileno())
 sync(directory);sync(BACKUP_ROOT);print('prepared_directory='+str(directory),flush=True)
 return directory


def apply(directory):
 d.require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,'private recovery directory required')
 d.require((directory/'adapter.py').read_bytes()==Path(__file__).read_bytes(),'adapter changed after preparation');validate_transport(json.loads((directory/'qualification-references.json').read_text())['transport']);d.checked_source();SourceStore().absent()
 db=h.connect()
 try:
  ops=Operations(directory,db);d.require(ops.ready(True),'managed provider changed');ops.preserved()
  save(directory,'apply-started.json',{'at':datetime.now(timezone.utc).isoformat()});sync(directory);sync(BACKUP_ROOT)
  handoff(ops)
  save(directory,'live-proof.json',{'at':datetime.now(timezone.utc).isoformat(),'items':8,'links':8,'file_phases':2,'actual_original_managed_rollback':True,'original_history_rows':sum(x['count'] for x in ops.prefixes.values()),'production_pid':ops.before['pid'],'source_sha256':d.SOURCE_SHA,'production_restart_qualified':False,'production_state_command_or_rule_writes':0})
  sync(directory)
 finally:db.close()


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--apply',type=Path);p.add_argument('--provider',type=Path);p.add_argument('--jdbc',type=Path);p.add_argument('--transport',type=Path);args=p.parse_args()
 d.require(not(args.prepare and args.apply),'choose one phase')
 fd=os.open(BACKUP_ROOT/'sun-calendar-handoff.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 try:
  d.require(stat.S_ISREG(os.fstat(fd).st_mode),'unsafe lock');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if args.prepare:prepare(args.provider,args.jdbc,args.transport)
  elif args.apply:apply(args.apply)
  else:
   before=snapshot();normalized(before);SourceStore().absent()
   for n in d.IDS:d.validate_item(next(x for x in before['items'] if x['name']==n),n,managed=True);d.validate_links(before['links'],n,managed=True)
   print('read_only_preflight=passed items=8 links=8 production_writes=0')
 finally:os.close(fd)
if __name__=='__main__':main()
