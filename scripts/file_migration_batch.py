"""Closed Moon-display and temperature-evidence specification and guarded transport.

No Item states, commands, rule execution, SQL writes or service operations.
Live mutations require the caller's attended release gate after qualification.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,os,secrets,stat,sys
from urllib.parse import quote
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'openhab/scripts'))
import openhab_sanity_check as oh
ITEM_WRITABLE=('name','type','label','category','groupNames','tags')
ITEM_FIELDS=(*ITEM_WRITABLE,'metadata','unitSymbol','stateDescription')
THING_FIELDS=('UID','thingTypeUID','label','bridgeUID','configuration','channels','location','properties')
LIVE_RELEASE_READY=False
DESTINATION_ROOT=Path('/etc/openhab')
SOURCE_FILES={'moon':'items/moon-display-readings.items','weather':'things/weather-temperature-evidence.things'}
SPEC_SHA256='3d1397e8ea4f90cd4072ed1c5de52da951d10e85ca1bd1630d7e5b7257d4f59d'
SOURCE_HASHES={'moon': 'b6fa17b86928912e20c693859621438fc0198042efc7eb70d5ffbcf9e42c03bc', 'weather': 'b6291324a043559e6d47896ca240f62fdf30e3252c4102a9b9da8aa48b847806'}

def require(ok,reason):
 if not ok:raise RuntimeError(reason)

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),default=lambda x:x.isoformat()).encode()

def specification():
 path=ROOT/'openhab/file-config/moon-weather-migration.json'
 require(not path.is_symlink(),'specification symlink')
 body=path.read_bytes();require(sha256(body).hexdigest()==SPEC_SHA256,'specification changed')
 return json.loads(body)

def item_definition(item):
 result={k:deepcopy(item.get(k)) for k in ITEM_FIELDS}
 result['category']=result['category'] or None
 for k in ('tags','groupNames'):result[k]=sorted(result[k] or [])
 return result

def thing_definition(thing):
 result={k:deepcopy(thing.get(k)) for k in THING_FIELDS}
 result['channels']=sorted(result['channels'] or [],key=lambda c:c['uid'])
 for c in result['channels']:
  c['linkedItems']=sorted(c.get('linkedItems',[]));c['defaultTags']=sorted(c.get('defaultTags',[]))
 return result

def checked_source(kind):
 require(kind in SOURCE_FILES,'unknown batch')
 path=ROOT/'openhab/file-config'/SOURCE_FILES[kind]
 require(not path.is_symlink(),'source symlink')
 body=path.read_bytes();require(sha256(body).hexdigest()==SOURCE_HASHES[kind],'source changed')
 return body

def read_token():return oh.token()

def allowed_request(method,path,body):
 spec=specification()
 for name,row in spec['moon'].items():
  if path=='/items/'+name:
   if method=='DELETE':require(body is None,'delete body');return True
   if method=='PUT':
    expected={k:row['item'][k] for k in ITEM_WRITABLE if k in row['item']}
    require(body==expected,'original Item definition required');return True
  link=row['link'];target='/links/'+name+'/'+quote(link['channelUID'],safe='')
  if path==target:
   require(method in ('DELETE','PUT'),'link method')
   require(body is None if method=='DELETE' else body==link,'original link required');return True
 uid=spec['weather']['thing']['UID']
 if method=='DELETE' and path=='/things/'+uid+'?force=true':
  require(body is None,'delete body');return True
 if method=='POST' and path=='/things':
  require(body==managed_thing_dto(spec['weather']['thing']),'original Thing required');return True
 raise RuntimeError('REST mutation outside exact migration scope')

def managed_thing_dto(thing):
 result={k:deepcopy(thing[k]) for k in THING_FIELDS if k in thing and thing[k] is not None}
 result['channels']=[c for c in result.get('channels',[]) if c.get('id') not in ('last-success','last-failure')]
 for c in result.get('channels',[]):c.pop('linkedItems',None)
 return result

def request(method,path,body=None):
 allowed_request(method,path,body)
 require(LIVE_RELEASE_READY,'attended release gate closed')
 data=None if body is None else encoded(body)
 with urlopen(Request(oh.BASE+path,method=method,data=data,headers={'Authorization':'Bearer '+read_token(),'Content-Type':'application/json'}),timeout=15) as response:
  require(response.status in (200,201,202,204),'REST migration refused')

def private_file(directory,name,body):
 require('/' not in name and name not in ('.','..'),'unsafe private name')
 fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())

def install_exclusive(kind):
 require(LIVE_RELEASE_READY,'attended release gate closed')
 body=checked_source(kind);target=DESTINATION_ROOT/SOURCE_FILES[kind]
 pending=target.parent/('.batch-'+secrets.token_hex(12)+'.pending')
 fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 created=os.fstat(fd)
 try:
  with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
  os.link(pending,target,follow_symlinks=False)
  directory_fd=os.open(target.parent,os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(directory_fd)
  finally:os.close(directory_fd)
 finally:
  if pending.exists():
   current=pending.lstat();require((current.st_dev,current.st_ino)==(created.st_dev,created.st_ino),'pending file drift')
   pending.unlink()
 require(sha256(target.read_bytes()).hexdigest()==SOURCE_HASHES[kind],'installed source mismatch')
 return target

def withdraw_owned(kind,directory):
 require(LIVE_RELEASE_READY,'attended release gate closed')
 target=DESTINATION_ROOT/SOURCE_FILES[kind]
 require(not target.is_symlink() and sha256(target.read_bytes()).hexdigest()==SOURCE_HASHES[kind],'target drift refuses withdrawal')
 saved=directory/(kind+'-rollback-'+secrets.token_hex(8)+'-'+target.name)
 require(not saved.exists(),'rollback target exists');target.rename(saved);saved.chmod(0o600)
 for parent in (directory,target.parent):
  fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(fd)
  finally:os.close(fd)
 return saved


def handoff(ops):
 """Verify file, original managed rollback, then final file; recover on failure."""
 ops.backup()
 try:
  ops.withdraw_managed();ops.install_file();ops.verify_file()
  ops.withdraw_file();ops.restore_managed();ops.verify_managed()
  ops.withdraw_managed();ops.install_file();ops.verify_file()
 except BaseException:
  ops.recover_managed()
  raise
