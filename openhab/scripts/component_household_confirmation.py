"""Only exact confirmed component household publications are score origins."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import os
from household.codec import loads,canonical,identity
from household.control_contracts import instant
from household_observation import _private_file
from component_household_receipt import validate,SUFFIX,MAX_BYTES
from component_household_worker import EMISSION_SUFFIX,curated

def read_emission(path):
 path=Path(path);raw=_private_file(path,32768)[0];emission=loads(raw)
 fields={'schema','issued','issued_at','published_at','receipt_sha256','receipt_file_sha256','owner_profile_sha256','view_bytes_sha256','view','automatic_actuation','emission_sha256'}
 if (not isinstance(emission,dict) or set(emission)!=fields or emission['schema']!='earthship-confirmed-component-household-emission/v1' or
  emission['issued'] is not True or emission['automatic_actuation'] is not False or path.name!=sha256(raw).hexdigest()+EMISSION_SUFFIX or
  emission['emission_sha256']!=identity({k:v for k,v in emission.items() if k!='emission_sha256'})):
  raise ValueError('unchanged confirmed original household emission required')
 pin=emission['receipt_file_sha256']
 from weather_learning.contracts import digest
 digest(pin)
 receipt_path=path.parent/(pin+SUFFIX);receipt_raw=_private_file(receipt_path,MAX_BYTES)[0];receipt=validate(loads(receipt_raw))
 if sha256(receipt_raw).hexdigest()!=pin or receipt['receipt_sha256']!=emission['receipt_sha256']:raise ValueError('confirmed original household receipt differs')
 origin=instant(receipt['output']['issued_at']);published=instant(emission['published_at']);view=emission['view'];inputs=receipt['inputs']
 if (instant(emission['issued_at'])!=origin or not origin<=instant(inputs['assessed_at'])<=instant(view['generated_at'])<=published<=origin+timedelta(seconds=85) or
  inputs['owner_profile']['bytes_sha256']!=emission['owner_profile_sha256'] or
  sha256(canonical(view)).hexdigest()!=emission['view_bytes_sha256'] or
  canonical(curated(receipt,inputs['context']['prepared'],generated=instant(view['generated_at'])))!=canonical(view)):
  raise ValueError('confirmed original household view/clock/profile differs')
 return receipt_path,receipt,emission

def _emission_paths(store,guard):
 rows=[]
 with os.scandir(store) as entries:
  for i,entry in enumerate(entries):
   if i>=10000:raise ValueError('bounded original component emission inventory required')
   if i%100==0:guard()
   if not entry.name.endswith(EMISSION_SUFFIX):continue
   if not entry.is_file(follow_symlinks=False):raise ValueError('regular original component emission required')
   rows.append((entry.stat(follow_symlinks=False).st_mtime_ns,Path(entry.path)))
 return [path for _,path in sorted(rows,reverse=True)]

def confirmed_inventory(store,*,now,guard):
 result=[];seen=set()
 for path in _emission_paths(store,guard)[:512]:
  guard();receipt_path,receipt,emission=read_emission(path);origin=instant(receipt['output']['issued_at'])
  if not now-timedelta(hours=36)<=origin<=instant(emission['published_at'])<=now:continue
  if receipt['receipt_sha256'] in seen:raise ValueError('one confirmed component household origin required')
  seen.add(receipt['receipt_sha256']);result.append((origin,receipt_path,receipt))
 return result

def read_confirmed_forecast(path,*,guard=lambda:None):
 path=Path(path)
 for emission in _emission_paths(path.parent,guard):
  guard();receipt_path,receipt,_=read_emission(emission)
  if receipt_path==path:return receipt
 raise ValueError('confirmed original component household publication required')
