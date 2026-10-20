#!/usr/bin/env python3
"""Retain bounded local wind/rain originals; no forecast or actuator writes."""
from pathlib import Path
from datetime import datetime,date,time,timedelta,timezone
from urllib.request import Request,build_opener,ProxyHandler
from urllib.parse import urlencode
from io import BytesIO
import json,gzip,os,argparse
from weather_learning.openhab import auth_token
from openhab_runtime_io import _NoRedirect,ReadBudget
from thermal_model.capture_readers import _pacer
from household_native_training import directory,save
from weather_learning.contracts import identity,canonical
from weather_source_files import _read
from weather_rain_day import qualify_rain_day
from weather_rain_evidence import RainPolicy
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--start',required=True);parser.add_argument('--days',type=int,required=True);parser.add_argument('--state',type=Path,default=Path.home()/'.local/state/earthship-weather/historical-weather-inventory');args=parser.parse_args();os.umask(0o077)
    if not 1<=args.days<=90:raise ValueError('bounded retained weather days required')
    first=date.fromisoformat(args.start)
    if datetime.combine(first+timedelta(days=args.days),time.min,timezone.utc)>datetime.now(timezone.utc)-timedelta(minutes=5):raise ValueError('completed mature weather dates required')
    root=directory(args.state);budget=ReadBudget(90,max_requests=args.days*2);pace=_pacer(1048576);opener=build_opener(ProxyHandler({}),_NoRedirect()).open
    policy_doc=json.loads((Path.home()/'.config/hex/weather-rain-policy.json').read_bytes());policy=RainPolicy(**{k:v for k,v in policy_doc.items() if k!='version'});days=[]
    for i in range(args.days):
     day=first+timedelta(days=i);start=datetime.combine(day,time.min,timezone.utc);end=start+timedelta(days=1);sources={};manifest={}
     for name in ('AmbientWeatherWS2902A_WindSpeed','Weather_Rain_Evidence_JSON'):
      budget.remaining();p=root/(day.isoformat()+'.'+name+'.json.gz')
      if p.exists():
       with gzip.GzipFile(fileobj=BytesIO(_read(p,8*1024**2))) as f:raw=f.read(8*1024**2+1)
       if len(raw)>8*1024**2:raise ValueError('retained source byte bound')
       value=json.loads(raw)
      else:
       fmt='%Y-%m-%dT%H:%M:%SZ';left=start-timedelta(seconds=120);right=end+timedelta(seconds=120)
       url='http://127.0.0.1:8080/rest/persistence/items/'+name+'?'+urlencode(dict(serviceId='jdbc',starttime=left.strftime(fmt),endtime=right.strftime(fmt)));request=Request(url,headers={'Authorization':'Bearer '+auth_token()},method='GET');requested=datetime.now(timezone.utc);parts=[];count=0
       with opener(request,timeout=budget.begin()) as response:
        if response.geturl()!=url:raise ValueError('redirect refused')
        while True:
         budget.remaining();pace.reserve(65536);part=response.read(65536)
         if not part:break
         count+=len(part)
         if count>4*1024**2:raise ValueError('weather inventory byte bound')
         parts.append(part)
       value=dict(schema='earthship-historical-weather-inventory-source/v1',item=name,requested_at=requested.isoformat(),received_at=datetime.now(timezone.utc).isoformat(),raw=b''.join(parts).decode(),automatic_actuation=False);value['source_sha256']=identity(value)
       fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
       with os.fdopen(fd,'wb') as f:f.write(gzip.compress(canonical(value),mtime=0))
      if value['source_sha256']!=identity({k:v for k,v in value.items() if k!='source_sha256'}) or value['item']!=name or value['automatic_actuation'] is not False:raise ValueError('original source identity differs')
      payload=json.loads(value['raw'])
      if payload.get('name')!=name or not isinstance(payload.get('data'),list) or len(payload['data'])>10000:raise ValueError('bounded exact original Item required')
      if name=='AmbientWeatherWS2902A_WindSpeed' and payload.get('unit')!='mph':raise ValueError('original wind history unit differs')
      sources[name]=payload;manifest[name]=dict(source_sha256=value['source_sha256'],file_sha256=__import__('hashlib').sha256(_read(p,8*1024**2)).hexdigest(),rows=len(payload['data']))
     rows=[(datetime.fromtimestamp(r['time']/1000,timezone.utc),r['state']) for r in sources['Weather_Rain_Evidence_JSON']['data']];carry=[r for r in rows if r[0]<start];rows=carry[-1:]+[r for r in rows if start<=r[0]<=end+timedelta(seconds=policy.validity_seconds)]
     try:rain=qualify_rain_day(day,as_of=datetime.now(timezone.utc),observations=rows,policy=policy,site_timezone='UTC');rain=dict(status='qualified',**rain)
     except Exception as e:rain=dict(status='unqualified',reason=type(e).__name__,detail=str(e))
     row=dict(date=day.isoformat(),query_start=(start-timedelta(seconds=120)).isoformat(),query_end=(end+timedelta(seconds=120)).isoformat(),sources=manifest,rain=rain);days.append(row)
     index=dict(schema='earthship-historical-weather-inventory/v1',days=days,wind_unit_basis='original_HTTP_history_response_unit_mph',wind_sensor_health_qualified=False,rain_policy_raw=json.dumps(policy_doc,sort_keys=True,separators=(',',':')),automatic_actuation=False);index['index_sha256']=identity(index);save(root/'weather-index.json',index)
     print(json.dumps({'date':day.isoformat(),'wind_rows':manifest['AmbientWeatherWS2902A_WindSpeed']['rows'],'rain_status':rain['status'],'rain_in':rain.get('rain_in')}),flush=True)
    print(json.dumps({'status':'wind_rain_history_retained','days':len(days),'qualified_rain_days':sum(r['rain']['status']=='qualified' for r in days),'wet_days':sum(r['rain'].get('rain_in',0)>0 for r in days),'requests':budget.requests if hasattr(budget,'requests') else None}),flush=True)

if __name__=='__main__':main()
