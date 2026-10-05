#!/usr/bin/env python3
"""Frozen closed-batch provider/restart/rollback rehearsal, production GET-only.

Restored private data stays in one owned networkless container. No production
mounts, ports, devices, state writes, service operations or controls are used.
"""
import argparse,importlib.util,json,secrets,time
from pathlib import Path
from urllib.parse import quote
from hashlib import sha256
import file_migration_batch as batch
ROOT=batch.ROOT

def load(name,filename):
 s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
q=load('batch_moon_provider','qualify-moon-phase-provider.py')
aqi=q.aqi
LABEL='hex.moon.weather.provider.qualification'
HTTP=Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/org.openhab.binding.http/5.2.1/org.openhab.binding.http-5.2.1.jar')

def exact(container,header,*,managed):
 spec=batch.specification();code,links=aqi.isolated_get(container,'/links',header)
 if code!=200:return False
 for name,row in spec['moon'].items():
  code,item=aqi.isolated_get(container,'/items/'+name+'?metadata=.*',header)
  if code!=200 or item.get('editable') is not managed or batch.item_definition(item)!=batch.item_definition(row['item']):return False
  attached=[l for l in links if l.get('itemName')==name]
  if len(attached)!=1 or attached[0].get('editable') is not managed or {k:attached[0].get(k) for k in row['link']}!=row['link']:return False
 code,thing=aqi.isolated_get(container,'/things/'+spec['weather']['thing']['UID'],header)
 return code==200 and thing.get('editable') is managed and batch.thing_definition(thing)==batch.thing_definition(spec['weather']['thing'])

def wait(predicate,seconds=240):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if predicate():return
  time.sleep(2)
 raise RuntimeError('isolated exact provider condition timed out')

def absent(container,header):
 spec=batch.specification();code,links=aqi.isolated_get(container,'/links',header)
 if code!=200:return False
 return not any(l.get('itemName') in spec['moon'] for l in links) and all(aqi.isolated_get(container,'/items/'+n,header)[0]==404 for n in spec['moon']) and aqi.isolated_get(container,'/things/'+spec['weather']['thing']['UID'],header)[0]==404

def mutation(container,header,method,path,body=None):
 batch.allowed_request(method,path,body)
 aqi.install_bytes(container,'/tmp','batch-payload.json',b'' if body is None else batch.encoded(body),mode=0o600)
 args=['docker','exec',container,'curl','-sS','--max-time','10','-o','/dev/null','-w','%{http_code}','-X',method,'-H','@/tmp/batch-auth-header','-H','Content-Type: application/json']
 if body is not None:args+=['--data-binary','@/tmp/batch-payload.json']
 args+=['http://127.0.0.1:8080/rest'+path]
 status=aqi.run(args,timeout=15).stdout.decode().strip()
 batch.require(status in ('200','201','202','204'),'isolated original restoration refused: '+method+' '+path+' status '+status)

def diagnose(container,header):
 spec=batch.specification();differences=[]
 for name,row in spec['moon'].items():
  code,item=aqi.isolated_get(container,'/items/'+name+'?metadata=.*',header)
  if code!=200:differences.append({'item':name,'status':code});continue
  actual=batch.item_definition(item);expected=batch.item_definition(row['item'])
  for key in actual:
   if actual[key]!=expected[key]:differences.append({'item':name,'field':key,'expected':expected[key],'actual':actual[key]})
 code,t=aqi.isolated_get(container,'/things/'+spec['weather']['thing']['UID'],header)
 if code==200:
  a=batch.thing_definition(t);b=batch.thing_definition(spec['weather']['thing'])
  for key in a:
   if a[key]!=b[key]:differences.append({'thing':spec['weather']['thing']['UID'],'field':key,'expected':b[key],'actual':a[key]})
 else:differences.append({'thing':spec['weather']['thing']['UID'],'status':code})
 return differences

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',required=True,type=Path);args=parser.parse_args(argv)
 spec=batch.specification();sources={k:batch.checked_source(k) for k in batch.SOURCE_FILES};astro=q.checked_astro();http=HTTP.read_bytes()
 # Check all production definitions without printing states or credentials.
 links=batch.oh.get('/links')
 for name,row in spec['moon'].items():
  actual=batch.oh.get('/items/'+name+'?metadata=.*')
  batch.require(actual.get('editable') is True and batch.item_definition(actual)==batch.item_definition(row['item']),'live Moon Item drift')
  attached=[l for l in links if l.get('itemName')==name]
  batch.require(len(attached)==1 and attached[0].get('editable') is True and {k:attached[0].get(k) for k in row['link']}==row['link'],'live Moon link drift')
 live=batch.oh.get('/things/'+spec['weather']['thing']['UID'])
 batch.require(live.get('editable') is True and batch.thing_definition(live)==batch.thing_definition(spec['weather']['thing']),'live HTTP Thing drift')
 marker=secrets.token_hex(12);container=None;report={'scope':'isolated_closed_moon_weather_provider','specification_sha256':batch.SPEC_SHA256,'source_sha256':batch.SOURCE_HASHES,'live_writes':0,'metadata_deviations_accepted':0}
 try:
  container=aqi.run(['docker','run','-d','--label',LABEL+'='+marker,'--network','none','--hostname','localhost','--cap-drop','ALL','--pids-limit','384','--memory','2g','--memory-swap','2g','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','-e','EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver','--entrypoint','/bin/sh',aqi.IMAGE,'-c','while [ ! -f /openhab/conf/items/moon-display-readings.items ]; do sleep 1; done; exec /openhab/start.sh server']).stdout.decode().strip()
  batch.require(aqi.run(['docker','inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',container]).stdout.decode().strip()==marker,'container ownership')
  for scope in ('conf','userdata'):aqi.restore(container,scope)
  for path,body in ((q.ASTRO,astro),(HTTP,http)):aqi.install_bytes(container,'/openhab/addons',path.name,body)
  itemdb=aqi.snapshot_registry('org.openhab.core.items.Item.json');linkdb=aqi.snapshot_registry('org.openhab.core.thing.link.ItemChannelLink.json');thingdb=aqi.snapshot_registry('org.openhab.core.thing.Thing.json')
  for name,row in spec['moon'].items():
   batch.require(name in itemdb and name+' -> '+row['link']['channelUID'] in linkdb,'restored Moon identity absent')
   del itemdb[name];del linkdb[name+' -> '+row['link']['channelUID']]
  thingdb.pop(spec['weather']['thing']['UID'],None)
  for filename,payload in [('org.openhab.core.items.Item.json',itemdb),('org.openhab.core.thing.link.ItemChannelLink.json',linkdb),('org.openhab.core.thing.Thing.json',thingdb)]:aqi.install_bytes(container,'/openhab/userdata/jsondb',filename,batch.encoded(payload))
  header=('Authorization: Bearer '+batch.oh.token()+'\n').encode()
  aqi.install_bytes(container,'/openhab/conf/things','weather-temperature-evidence.things',sources['weather'])
  aqi.install_bytes(container,'/openhab/conf/items','moon-display-readings.items',sources['moon'])
  try:wait(lambda:exact(container,header,managed=False))
  except Exception:
   batch.private_file(args.report.parent,'provider-differences.json',batch.encoded(diagnose(container,header)));raise
  report['first_boot']={'items':25,'links':25,'things':1,'exact':True};print('first_boot_exact_items=25 links=25 things=1',flush=True)
  aqi.run(['docker','restart',container],timeout=90);wait(lambda:exact(container,header,managed=False))
  report['full_jvm_restart']=True;print('full_jvm_restart_exact=true',flush=True)
  aqi.run(['docker','exec',container,'rm','/openhab/conf/items/moon-display-readings.items','/openhab/conf/things/weather-temperature-evidence.things']);wait(lambda:absent(container,header),seconds=100)
  aqi.install_bytes(container,'/tmp','batch-auth-header',header,mode=0o600)
  mutation(container,header,'POST','/things',batch.managed_thing_dto(spec['weather']['thing']))
  for name,row in spec['moon'].items():
   mutation(container,header,'PUT','/items/'+name,{k:row['item'][k] for k in batch.ITEM_WRITABLE if k in row['item']})
   mutation(container,header,'PUT','/links/'+name+'/'+quote(row['link']['channelUID'],safe=''),row['link'])
  wait(lambda:exact(container,header,managed=True),seconds=100)
  report['original_managed_rollback']=True;print('original_managed_rollback_exact=true',flush=True)
 finally:
  if container:
   owner=aqi.run(['docker','inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',container],check=False).stdout.decode().strip()
   batch.require(owner==marker,'cleanup ownership changed')
   aqi.run(['docker','rm','-f','-v',container],timeout=60);report['owned_container_and_volumes_removed']=True;print('owned_container_and_volumes_removed=true',flush=True)
 if report.get('original_managed_rollback'):
  batch.private_file(args.report.parent,args.report.name,batch.encoded(report));print('qualification_report='+str(args.report),flush=True)

if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('provider qualification failed: '+type(e).__name__+': '+str(e)) from None
