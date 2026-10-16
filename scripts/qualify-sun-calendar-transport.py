#!/usr/bin/env python3
"""Exercise the attended transport in a disconnected owned Sun fixture.

The production adapter's methods run unchanged. REST and file I/O are routed
into the owned fixture; original production histories are checked read-only.
No production definitions, states, commands or service operations can be written.
"""
import argparse,importlib.util,json,os,secrets,tempfile,time
from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
from urllib.parse import urlparse
from types import SimpleNamespace
import sun_calendar_items as d
ROOT=d.ROOT

def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=load('sun_transport_provider','qualify-sun-calendar-provider.py');m=load('sun_attended_transport','migrate-sun-calendar-items.py');a=p.aqi
LABEL='hex.sun.calendar.transport.qualification'


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',required=True,type=Path);directory=parser.parse_args().directory
 d.require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,'private report directory required')
 source=d.checked_source();prod_get=m.get;prod_snapshot=m.snapshot;before=prod_snapshot();pins=m.sources()
 for n in d.IDS:d.validate_item(prod_get('/items/'+n+'?metadata=.*'),n,managed=True);d.validate_links(before['links'],n,managed=True)
 items=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json').read_text());links=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json').read_text());things=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.thing.Thing.json').read_text())
 items={n:items[n] for n in set(d.IDS)|{'Sun'}};links={n+' -> '+r['link']['channelUID']:links[n+' -> '+r['link']['channelUID']] for n,r in d.specification().items()};things={'astro:sun:local':things['astro:sun:local']}
 users=Path('/var/lib/openhab/jsondb/users.json').read_bytes();header=('Authorization: Bearer '+d.batch.oh.token()+'\n').encode();astro=p.q.checked_astro()
 for n,body in [('native-items.json',d.batch.encoded(items)),('native-links.json',d.batch.encoded(links)),('native-thing.json',d.batch.encoded(things)),('private-users.json',users),('transport.py',Path(m.__file__).read_bytes()),('source.items',source)]:m.save(directory,n,body)
 db=m.h.connect();prefixes={}
 with db:
  for n,i in d.IDS.items():prefixes[n]=m.h.native_history(db,n,i)
 m.save(directory,'history-prefixes.json',prefixes);m.save(directory,'before-sources.json',pins);m.save(directory,'mutation-events.jsonl',b'')
 marker=secrets.token_hex(12);container=None
 try:
  container=a.run(['docker','run','-d','--label',LABEL+'='+marker,'--network','none','--hostname','localhost','--cap-drop','ALL','--pids-limit','384','--memory','2g','--memory-swap','2g','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','-e','EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver','--entrypoint','/bin/sh',a.IMAGE,'-c','cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; mkdir -p /openhab/userdata/jsondb; touch /tmp/transport-bootstrap; while [ ! -f /openhab/conf/.transport-ready ]; do sleep 1; done; exec /openhab/start.sh server']).stdout.decode().strip()
  d.require(a.run(['docker','inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',container]).stdout.decode().strip()==marker,'fixture ownership mismatch')
  a.run(['docker','exec',container,'sh','-c','while [ ! -f /tmp/transport-bootstrap ]; do sleep 1; done'])
  a.install_bytes(container,'/openhab/addons',p.q.ASTRO.name,astro)
  for n,body in [('org.openhab.core.items.Item.json',d.batch.encoded(items)),('org.openhab.core.thing.link.ItemChannelLink.json',d.batch.encoded(links)),('org.openhab.core.thing.Thing.json',d.batch.encoded(things)),('users.json',users)]:a.install_bytes(container,'/openhab/userdata/jsondb',n,body,mode=0o600)
  a.install_bytes(container,'/openhab/conf/services','regional.cfg',b'org.openhab.i18n:language=en\norg.openhab.i18n:region=US\norg.openhab.i18n:measurementSystem=US\norg.openhab.i18n:timezone=America/Denver\n');a.run(['docker','exec',container,'touch','/openhab/conf/.transport-ready'])
  p.wait(lambda:p.exact(container,header,True))
  def pid():return a.run(['docker','inspect','--format','{{.State.Pid}}',container]).stdout.decode().strip()
  def native_get(path):
   code,result=a.isolated_get(container,path,header)
   if code==404:return None
   d.require(code==200,'owned REST unavailable');return result
  def native_snapshot():
   s={'at':datetime.now(timezone.utc).isoformat(),'pid':pid(),**{k:native_get('/'+k+('?metadata=.*' if k=='items' else '')) for k in ('items','links','things','rules')}}
   group=native_get('/items/Sun?metadata=.*');s['items']=[group if x['name']=='Sun' else x for x in s['items']];return s
  def native_open(request,timeout=15):
   path=urlparse(request.full_url).path;d.require(path.startswith('/rest/'),'owned REST prefix required');path=path[5:]
   body=None if request.data is None else json.loads(request.data)
   p.mutation(container,header,request.get_method(),path,body)
   class Response:
    status=204
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return b''
   return Response()
  with tempfile.TemporaryDirectory(prefix='sun-transport-source-') as host_store:
   class Store(m.SourceStore):
    def install(self):super().install();a.install_bytes(container,'/openhab/conf/items',d.SOURCE.name,self.target.read_bytes())
    def verify(self):
     super().verify();d.require(a.run(['docker','exec',container,'sha256sum',p.TARGET]).stdout.decode().split()[0]==d.SOURCE_SHA,'owned fixture source drift')
    def withdraw(self):super().withdraw();a.run(['docker','exec',container,'rm',p.TARGET]);p.wait(lambda:p.absent(container,header))
   store=Store(Path(host_store)/d.SOURCE.name)
   m.get=native_get;m.snapshot=native_snapshot;m.urlopen=native_open
   m.save(directory,'before-registry.json',native_snapshot())
   ops=m.Operations(directory,db);ops.store=store;d.require(ops.ready(True),'native managed baseline unavailable')
   m.handoff(ops);d.require(ops.phase==2,'native transport phases incomplete')
   old=pid();a.run(['docker','restart',container],timeout=90);p.wait(lambda:p.exact(container,header,False));new=pid();d.require(old!=new,'native cold PID unchanged');store.verify()
   m.save(directory,'cold-native-registry.json',native_snapshot())
   proof={'at':datetime.now(timezone.utc).isoformat(),'transport_sha256':sha256(Path(m.__file__).read_bytes()).hexdigest(),'source_sha256':d.SOURCE_SHA,'specification_sha256':d.SPEC_SHA,'exact_transport_native_round_trip':True,'file_phases':2,'original_managed_rollback':True,'full_jvm_restart':True,'old_native_pid':old,'new_native_pid':new,'items':8,'links':8,'production_writes':0,'production_history_prefixes':8,'rules':0}
 except BaseException:
  if container:
   try:m.save(directory,'failed-native.log',a.run(['docker','logs',container],check=False).stdout)
   except Exception:pass
  raise
 finally:
  m.get=prod_get;m.snapshot=prod_snapshot
  db.close()
  if container:
   d.require(a.run(['docker','inspect','--format','{{index .Config.Labels "'+LABEL+'"}}',container],check=False).stdout.decode().strip()==marker,'cleanup ownership mismatch');a.run(['docker','rm','-f','-v',container],timeout=60);print('owned_fixture_removed=true',flush=True)
 after=prod_snapshot();proof['binding_freshness_advances']=m.compare(m.normalized(before),m.normalized(after));d.require(after['pid']==before['pid'] and m.sources()==pins,'production JVM/sources changed')
 db=m.h.connect()
 try:
  with db:
   for n,r in prefixes.items():d.require(m.h.native_history(db,n,r['id'],cutoff=datetime.fromisoformat(r['cutoff']))==r,'production history prefix changed')
 finally:db.close()
 proof.update(owned_fixture_removed=True,production_jvm_unchanged=True,production_definitions_unchanged=True)
 m.save(directory,'transport-proof.json',proof);print('exact_native_transport=passed production_writes=0',flush=True)
if __name__=='__main__':main()
