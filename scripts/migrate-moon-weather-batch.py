#!/usr/bin/env python3
"""Attended closed Moon/HTTP file handoff; default check and release gate off.

No arbitrary targets, state writes, commands, SQL writes, rule calls or restarts.
Each handoff exercises original managed rollback before final file ownership.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
import argparse,fcntl,gzip,json,os,stat,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
import file_migration_batch as b
sys.path.insert(0,'/home/sat/Solar_PV/analytics/src')
from earthship_energy.db import parse_openhab_jdbc_config
import psycopg2
from psycopg2 import sql
BACKUP_ROOT=Path('/home/sat/.local/state/openhab-config-migration')
MAX_HISTORY_BYTES=512*1024*1024

class DigestWriter:
 def __init__(self,output=None):self.output=output;self.digest=sha256();self.size=0
 def write(self,value):
  body=value.encode() if isinstance(value,str) else value;self.size+=len(body)
  b.require(self.size<=MAX_HISTORY_BYTES,'history exceeds backup bound')
  self.digest.update(body)
  if self.output is not None:self.output.write(body)


def history(db,name,identity,cutoff=None,output=None):
 expected={n:r['jdbc_id'] for n,r in b.specification()['moon'].items()};expected['Weather_Temperature_Evidence_JSON']=646
 b.require(expected.get(name)==identity,'history outside exact scope')
 with db,db.cursor() as c:
  c.execute("SET LOCAL statement_timeout='60s'");c.execute("SET LOCAL TIME ZONE 'UTC'")
  c.execute('SELECT itemid FROM public.items WHERE itemname=%s',(name,));b.require(c.fetchall()==[(identity,)],'JDBC identity drift')
  table=sql.Identifier('item'+str(identity).zfill(4));where=sql.SQL('') if cutoff is None else sql.SQL(' WHERE time<=%s')
  c.execute(sql.SQL('SELECT count(*),max(time) FROM public.{}').format(table)+where,() if cutoff is None else (cutoff,));count,maximum=c.fetchone()
  b.require(count>0 and maximum is not None,'original history missing')
  command=sql.SQL('COPY (SELECT time,value FROM public.{} WHERE time<={} ORDER BY time,value) TO STDOUT WITH CSV').format(table,sql.Literal(maximum))
  writer=DigestWriter(output);c.copy_expert(command.as_string(db),writer)
 return {'id':identity,'count':count,'cutoff':maximum.isoformat(),'sha256':writer.digest.hexdigest(),'bytes':writer.size}


def item(name):
 try:return b.oh.get('/items/'+name+'?metadata=.*')
 except HTTPError as e:
  if e.code==404:return None
  raise


def thing():
 try:return b.oh.get('/things/http:url:weatherTemperatureEvidence')
 except HTTPError as e:
  if e.code==404:return None
  raise


def protected_signature():
 spec=b.specification();moon=set(spec['moon']);items=b.oh.get('/items?metadata=.*');things=b.oh.get('/things');rules=b.oh.get('/rules');links=b.oh.get('/links')
 # linkedItems is derived registry membership. Omit only this derived field
 # when hashing Things; ready() separately proves every selected exact link.
 frozen_things=[]
 for t in things:
  if t['UID']==spec['weather']['thing']['UID']:continue
  row=b.thing_definition(t)
  for c in row['channels']:c.pop('linkedItems',None)
  row['editable']=t.get('editable');frozen_things.append(row)
 rule_defs=[]
 for r in rules:
  row={k:r.get(k) for k in ('uid','name','description','tags','visibility','configuration','triggers','conditions','actions','editable')}
  row['tags']=sorted(row['tags'] or []);rule_defs.append(row)
 return {'items':sha256(b.encoded(sorted([{**b.item_definition(i),'editable':i.get('editable')} for i in items if i['name'] not in moon],key=lambda r:r['name']))).hexdigest(),'things':sha256(b.encoded(sorted(frozen_things,key=lambda r:r['UID']))).hexdigest(),'rules':sha256(b.encoded(sorted(rule_defs,key=lambda r:r['uid']))).hexdigest(),'links':sha256(b.encoded(sorted([{k:l.get(k) for k in ('itemName','channelUID','configuration','editable')} for l in links if l['itemName'] not in moon],key=lambda r:(r['itemName'],r['channelUID'])))).hexdigest(),'openhab_pid':subprocess.check_output(['systemctl','show','openhab.service','-p','MainPID','--value'],text=True,timeout=5).strip()}


def sync_directory(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)


def wait(predicate,seconds=100):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if predicate():return
  time.sleep(1)
 raise RuntimeError('live exact condition timed out')


@contextmanager
def exclusive():
 info=BACKUP_ROOT.lstat();b.require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'private backup root unsafe')
 fd=os.open(BACKUP_ROOT/'moon-weather-migration.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 try:
  b.require(stat.S_ISREG(os.fstat(fd).st_mode),'lock unsafe');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
 finally:os.close(fd)


class Operations:
 def __init__(self,kind,db):
  self.kind=kind;self.db=db;self.spec=b.specification();b.checked_source(kind)
  target=b.DESTINATION_ROOT/b.SOURCE_FILES[kind];b.require(not target.exists() and not target.is_symlink(),'file target already exists')
  self.originals={n:item(n) for n in self.spec['moon']} if kind=='moon' else {'Weather_Temperature_Evidence_JSON':item('Weather_Temperature_Evidence_JSON')}
  self.original_thing=thing();self.original_links=b.oh.get('/links');self.guard=protected_signature();self.directory=None;self.phase=0;self.changed=False
  self.identities={n:r['jdbc_id'] for n,r in self.spec['moon'].items()} if kind=='moon' else {'Weather_Temperature_Evidence_JSON':646}
  self.before={n:history(db,n,i) for n,i in self.identities.items()}
  b.require(self.ready(True),'preflight definition/state/provider drift')
 def ready(self,managed):
  links=b.oh.get('/links')
  if self.kind=='weather':
   t=thing()
   return t is not None and t.get('editable') is managed and t.get('statusInfo',{}).get('status')=='ONLINE' and b.thing_definition(t)==b.thing_definition(self.spec['weather']['thing']) and item('Weather_Temperature_Evidence_JSON')['state'] not in ('NULL','UNDEF')
  for n,row in self.spec['moon'].items():
   a=item(n);ls=[l for l in links if l['itemName']==n]
   if a is None or a.get('editable') is not managed or b.item_definition(a)!=b.item_definition(row['item']) or a.get('state') in ('NULL','UNDEF') or len(ls)!=1 or ls[0].get('editable') is not managed or {k:ls[0].get(k) for k in row['link']}!=row['link']:return False
  return True
 def absent(self):
  if self.kind=='weather':return thing() is None
  links=b.oh.get('/links');return all(item(n) is None for n in self.identities) and not any(l['itemName'] in self.identities for l in links)
 def preserved(self):
  for n,r in self.before.items():b.require(history(self.db,n,r['id'],datetime.fromisoformat(r['cutoff']))==r,'original history prefix changed: '+n)
  b.require(self.guard['openhab_pid'].isdigit() and int(self.guard['openhab_pid'])>0,'OpenHAB process unavailable')
  b.require(protected_signature()==self.guard,'unrelated configuration or OpenHAB process changed')
 def backup(self):
  self.directory=Path(tempfile.mkdtemp(prefix=self.kind+'-file-20261005-',dir=BACKUP_ROOT));self.directory.chmod(0o700)
  b.private_file(self.directory,'preimages.json',b.encoded({'kind':self.kind,'items':self.originals,'links':self.original_links,'thing':self.original_thing,'before_history':self.before,'protected':self.guard,'specification_sha256':b.SPEC_SHA256,'source_sha256':b.SOURCE_HASHES[self.kind]}))
  for n,r in self.before.items():
   fd=os.open(self.directory/(n+'.csv.gz'),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'wb') as raw:
    with gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=1,mtime=0) as zipped:export=history(self.db,n,r['id'],datetime.fromisoformat(r['cutoff']),zipped)
    raw.flush();os.fsync(raw.fileno())
   b.require(export==r,'backup does not match original history')
  b.private_file(self.directory,'source.before',b.checked_source(self.kind))
  sync_directory(self.directory);sync_directory(BACKUP_ROOT);self.preserved()
  print('private_backup='+str(self.directory),flush=True)
 def withdraw_managed(self):
  b.require(self.ready(True),'managed provider drift before withdrawal');self.preserved();self.changed=True
  if self.kind=='weather':b.request('DELETE','/things/'+self.spec['weather']['thing']['UID']+'?force=true')
  else:
   for n,row in self.spec['moon'].items():b.request('DELETE','/links/'+n+'/'+quote(row['link']['channelUID'],safe=''))
   for n in self.identities:b.request('DELETE','/items/'+n)
  wait(self.absent)
 def install_file(self):
  b.require(self.absent(),'managed resources not absent');b.install_exclusive(self.kind)
 def verify_file(self):
  wait(lambda:self.ready(False));self.preserved();self.phase+=1
  b.private_file(self.directory,'file-phase-'+str(self.phase)+'.json',b.encoded({'at':datetime.now(timezone.utc),'kind':self.kind,'source_sha256':b.SOURCE_HASHES[self.kind],'original_prefixes_preserved':True,'protected_unchanged':True,'state_populated':True}))
  print('verified_file_phase='+str(self.phase)+' kind='+self.kind,flush=True)
 def withdraw_file(self):
  b.withdraw_owned(self.kind,self.directory);wait(self.absent)
 def restore_managed(self):
  if self.kind=='weather':
   existing=thing()
   if existing is None:b.request('POST','/things',b.managed_thing_dto(self.spec['weather']['thing']))
   else:b.require(existing.get('editable') is True and b.thing_definition(existing)==b.thing_definition(self.spec['weather']['thing']),'unexpected Thing during rollback')
  else:
   for n,row in self.spec['moon'].items():
    a=item(n)
    if a is None:b.request('PUT','/items/'+n,{k:row['item'][k] for k in b.ITEM_WRITABLE if k in row['item']})
    else:
     # Unit/stateDescription can disappear when the original link is removed.
     # Check intrinsic identity/semantics now; ready() requires the full
     # original derived definition after all exact links are repaired.
     actual=b.item_definition(a);expected=b.item_definition(row['item'])
     b.require(a.get('editable') is True and all(actual[k]==expected[k] for k in (*b.ITEM_WRITABLE,'metadata')),'unexpected Item during rollback')
   links=b.oh.get('/links')
   for n,row in self.spec['moon'].items():
    ls=[l for l in links if l['itemName']==n]
    if not ls:b.request('PUT','/links/'+n+'/'+quote(row['link']['channelUID'],safe=''),row['link'])
    else:b.require(len(ls)==1 and ls[0].get('editable') is True and {k:ls[0].get(k) for k in row['link']}==row['link'],'unexpected link during rollback')
 def verify_managed(self):
  wait(lambda:self.ready(True));self.preserved()
  b.private_file(self.directory,'managed-rollback.json',b.encoded({'at':datetime.now(timezone.utc),'kind':self.kind,'exact_managed_provider':True,'original_prefixes_preserved':True,'protected_unchanged':True}));print('verified_original_managed_rollback='+self.kind,flush=True)
 def recover_managed(self):
  if not self.changed:return
  target=b.DESTINATION_ROOT/b.SOURCE_FILES[self.kind]
  if target.exists() or target.is_symlink():self.withdraw_file()
  self.restore_managed();wait(lambda:self.ready(True));self.preserved()
  b.private_file(self.directory,'failure-managed-recovery.json',b.encoded({'at':datetime.now(timezone.utc),'kind':self.kind,'original_managed_restored':True}));print('failure_original_managed_recovered='+self.kind,flush=True)


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=('moon','weather'),required=True);p.add_argument('--apply',action='store_true');p.add_argument('--provider-proof',type=Path);p.add_argument('--jdbc-proof',type=Path);args=p.parse_args(argv)
 if args.apply:
  b.require(b.LIVE_RELEASE_READY,'attended release gate closed')
  for path in (args.provider_proof,args.jdbc_proof):
   b.require(path is not None and not path.is_symlink(),'qualification proof missing')
   info=path.stat();b.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600,'qualification proof unsafe')
  provider=json.loads(args.provider_proof.read_text());jdbc=json.loads(args.jdbc_proof.read_text())
  b.require(provider.get('specification_sha256')==b.SPEC_SHA256 and provider.get('source_sha256')==b.SOURCE_HASHES and provider.get('full_jvm_restart') is True and provider.get('original_managed_rollback') is True and provider.get('owned_container_and_volumes_removed') is True,'provider qualification invalid')
  b.require(jdbc.get('specification_sha256')==b.SPEC_SHA256 and jdbc.get('source_sha256')==b.SOURCE_HASHES['moon'] and jdbc.get('items')==25 and jdbc.get('full_jvm_restart_state_history') is True and jdbc.get('original_managed_state_history') is True and jdbc.get('owned_containers_removed') is True,'JDBC qualification invalid')
 settings=parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config');db=psycopg2.connect(**settings.connect_kwargs,connect_timeout=3);db.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
 try:
  if args.apply:
   with exclusive():
    ops=Operations(args.kind,db);b.handoff(ops);print(json.dumps({'status':'file_provider_provisional','kind':args.kind,'backup':str(ops.directory),'history_rows':{n:r['count'] for n,r in ops.before.items()},'production_restart':False},sort_keys=True),flush=True)
  else:
   ops=Operations(args.kind,db);ops.preserved();print(json.dumps({'status':'preflight_passed','kind':args.kind,'source_sha256':b.SOURCE_HASHES[args.kind],'history_rows':{n:r['count'] for n,r in ops.before.items()},'live_writes':0},sort_keys=True))
 finally:db.close()

if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('closed migration failed: '+type(e).__name__+': '+str(e)) from None
