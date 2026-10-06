#!/usr/bin/env python3
"""Closed Sun calendar provider/restart/rollback fixture; production GET-only.

Only eight display Items/links, the Sun Group/Thing and private API users enter
one owned networkless JVM. No rules, device endpoints, states or commands.
"""
import argparse,importlib.util,json,secrets,time,sys
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import sun_calendar_items as d
ROOT=d.ROOT

def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
q=load('sun_existing_native_binding','qualify-moon-phase-provider.py');aqi=q.aqi
LABEL='hex.sun.calendar.provider.qualification'
TARGET='/openhab/conf/items/'+d.SOURCE.name


def wait(predicate,seconds=240):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  try:
   if predicate():return
  except (RuntimeError,ValueError,KeyError,TypeError):pass
  time.sleep(2)
 raise RuntimeError('owned Sun calendar provider condition timed out')


def exact(container,header,managed):
 code,items=aqi.isolated_get(container,'/items?metadata=.*',header)
 linkcode,links=aqi.isolated_get(container,'/links',header)
 rulecode,rules=aqi.isolated_get(container,'/rules',header)
 if code!=200 or linkcode!=200 or rulecode!=200:return False
 d.require({x['name'] for x in items}==set(d.IDS)|{'Sun'} and rules==[] and len(links)==8,'fixture scope drift')
 for x in items:
  if x['name'] in d.IDS:d.validate_item(x,x['name'],managed=managed);d.validate_links(links,x['name'],managed=managed)
 return True


def absent(container,header):
 code,items=aqi.isolated_get(container,'/items',header);lc,links=aqi.isolated_get(container,'/links',header)
 return code==200 and lc==200 and not {x['name'] for x in items}.intersection(d.IDS) and links==[]


def mutation(container,header,method,path,body=None):
 d.allowed_mutation(method,path,body)
 aqi.install_bytes(container,'/tmp','calendar-auth-header',header,mode=0o600)
 aqi.install_bytes(container,'/tmp','calendar-payload.json',b'' if body is None else d.batch.encoded(body),mode=0o600)
 args=['docker','exec',container,'curl','-sS','--max-time','10','-o','/dev/null','-w','%{http_code}','-X',method,'-H','@/tmp/calendar-auth-header','-H','Content-Type: application/json']
 if body is not None:args+=['--data-binary','@/tmp/calendar-payload.json']
 status=aqi.run(args+['http://127.0.0.1:8080/rest'+path],timeout=15).stdout.decode().strip()
 d.require(status in ('200','201','202','204'),'owned definition mutation refused: '+method+' '+path)


def main():
 from urllib.parse import quote
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',required=True,type=Path);directory=parser.parse_args().directory
 d.require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,'private evidence directory required')
 source=d.checked_source();astro=q.checked_astro();spec=d.specification();live_links=d.batch.oh.get('/links')
 for name in d.IDS:d.validate_item(d.batch.oh.get('/items/'+name+'?metadata=.*'),name,managed=True);d.validate_links(live_links,name,managed=True)
 itemdb=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json').read_text());linkdb=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json').read_text());thingdb=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.thing.Thing.json').read_text())
 items={n:itemdb[n] for n in set(d.IDS)|{'Sun'}};links={n+' -> '+r['link']['channelUID']:linkdb[n+' -> '+r['link']['channelUID']] for n,r in spec.items()};things={'astro:sun:local':thingdb['astro:sun:local']}
 d.require(not things['astro:sun:local']['value'].get('bridgeUID'),'unexpected Sun dependency')
 users=Path('/var/lib/openhab/jsondb/users.json').read_bytes();header=('Authorization: Bearer '+d.batch.oh.token()+'\n').encode()
 for filename,body in [('managed-items.json',d.batch.encoded(items)),('managed-links.json',d.batch.encoded(links)),('managed-thing.json',d.batch.encoded(things)),('private-users.json',users),('source.items',source)]:d.batch.private_file(directory,filename,body)
 marker=secrets.token_hex(12);container=None;proof={'at':datetime.now(timezone.utc).isoformat(),'source_sha256':d.SOURCE_SHA,'specification_sha256':d.SPEC_SHA,'items':8,'links':8,'production_writes':0,'synthetic_state_writes':0,'network':'none','rules':0,'phases':[]}
 def checkpoint(phase,managed):
  wait(lambda:exact(container,header,managed))
  pid=int(aqi.run(['docker','inspect','--format','{{.State.Pid}}',container]).stdout)
  proof['phases'].append({'phase':phase,'managed':managed,'host_pid':pid})
  print(json.dumps(proof['phases'][-1]),flush=True);return pid
 try:
  container=aqi.run(['docker','run','-d','--label',LABEL+'='+marker,'--network','none','--hostname','localhost','--cap-drop','ALL','--pids-limit','384','--memory','2g','--memory-swap','2g','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','-e','EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver','--entrypoint','/bin/sh',aqi.IMAGE,'-c','cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; touch /tmp/calendar-bootstrap; while [ ! -f /openhab/conf/.calendar-ready ]; do sleep 1; done; exec /openhab/start.sh server']).stdout.decode().strip()
  d.require(aqi.run(['docker','inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',container]).stdout.decode().strip()==marker,'fixture ownership mismatch')
  aqi.run(['docker','exec',container,'sh','-c','while [ ! -f /tmp/calendar-bootstrap ]; do sleep 1; done; mkdir -p /openhab/userdata/jsondb'])
  aqi.install_bytes(container,'/openhab/addons',q.ASTRO.name,astro)
  for filename,body in [('org.openhab.core.items.Item.json',d.batch.encoded(items)),('org.openhab.core.thing.link.ItemChannelLink.json',d.batch.encoded(links)),('org.openhab.core.thing.Thing.json',d.batch.encoded(things)),('users.json',users)]:aqi.install_bytes(container,'/openhab/userdata/jsondb',filename,body,mode=0o600)
  aqi.install_bytes(container,'/openhab/conf/services','regional.cfg',b'org.openhab.i18n:language=en\norg.openhab.i18n:region=US\norg.openhab.i18n:measurementSystem=US\norg.openhab.i18n:timezone=America/Denver\n')
  aqi.install_bytes(container,'/tmp','calendar-auth-header',header,mode=0o600);aqi.run(['docker','exec',container,'touch','/openhab/conf/.calendar-ready'])
  checkpoint('original-managed',True)
  for n,r in spec.items():mutation(container,header,'DELETE','/links/'+n+'/'+quote(r['link']['channelUID'],safe=''))
  for n in d.IDS:mutation(container,header,'DELETE','/items/'+n)
  wait(lambda:absent(container,header));aqi.install_bytes(container,'/openhab/conf/items',d.SOURCE.name,source)
  old=checkpoint('file-handoff',False);aqi.run(['docker','restart',container],timeout=90);new=checkpoint('file-cold-restart',False);d.require(old!=new,'cold JVM unchanged')
  aqi.run(['docker','exec',container,'rm',TARGET]);wait(lambda:absent(container,header))
  for n,r in spec.items():mutation(container,header,'PUT','/items/'+n,d.managed_item(n));mutation(container,header,'PUT','/links/'+n+'/'+quote(r['link']['channelUID'],safe=''),r['link'])
  checkpoint('original-managed-rollback',True)
  for n,r in spec.items():mutation(container,header,'DELETE','/links/'+n+'/'+quote(r['link']['channelUID'],safe=''))
  for n in d.IDS:mutation(container,header,'DELETE','/items/'+n)
  wait(lambda:absent(container,header));aqi.install_bytes(container,'/openhab/conf/items',d.SOURCE.name,source);checkpoint('final-file-handoff',False)
 except BaseException:
  if container:
   try:d.batch.private_file(directory,'failed-runtime.log',aqi.run(['docker','logs',container],check=False).stdout)
   except Exception:pass
  raise
 finally:
  if container:
   owner=aqi.run(['docker','inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',container],check=False).stdout.decode().strip();d.require(owner==marker,'cleanup ownership mismatch');aqi.run(['docker','rm','-f','-v',container],timeout=60)
   print('owned_container_removed=true',flush=True)
 proof.update(full_jvm_restart=True,original_managed_rollback=True,owned_container_removed=True)
 d.batch.private_file(directory,'provider-proof.json',d.batch.encoded(proof))
 print('provider_qualification=passed production_writes=0',flush=True)
if __name__=='__main__':main()
