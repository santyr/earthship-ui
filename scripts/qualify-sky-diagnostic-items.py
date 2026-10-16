#!/usr/bin/env python3
"""Owned offline diagnostic Item and resulting mixed-Group rehearsal; live reads only."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import argparse,importlib.util,json,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import sky_diagnostic_items as diag
import weather_health_age_items as age
spec=importlib.util.spec_from_file_location('diagnostic_group_fixture',ROOT/'scripts/qualify-weather-health-group.py');q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
q.LABEL='hex.sky.diagnostic.qualification'
SOURCE_SHA='3c6e43fbb3d6d03723341efa425c4dfb5143722fb2cdbcd0fe42ba43561ebca3'
TARGET='/openhab/conf/items/'+diag.SOURCE.name


class Fixture(q.Fixture):
 def mutation(self,method,path,body=None):
  diag.allowed_mutation(method,path,body);self.info(self.oh)
  code,response=q.p.request(self.oh,('Authorization: Bearer '+q.b.oh.token()+'\n').encode(),path,method,None if body is None else json.dumps(body),'application/json')
  self.rest_events.append({'at':datetime.now(timezone.utc).isoformat(),'method':method,'path':path,'code':code,'response':response})
  diag.require(code in (200,201,202,204),'owned definition mutation refused: '+str(code))
 def wait_absent(self):
  deadline=time.monotonic()+120
  while time.monotonic()<deadline:
   if not {row['name'] for row in self.rest('/items?metadata=.*')}.intersection(diag.ITEMS):return
   time.sleep(1)
  raise RuntimeError('diagnostic withdrawal did not settle')
 def withdraw_managed(self):
  for name in diag.ITEMS:
   self.mutation('DELETE','/items/'+name+'/metadata/stateDescription');self.mutation('DELETE','/items/'+name)
  self.wait_absent()
 def install_file(self):
  self.info(self.oh);diag.require(sha256(diag.SOURCE.read_bytes()).hexdigest()==SOURCE_SHA,'source drift')
  q.f.install_bytes(self.oh,'/openhab/conf/items',diag.SOURCE.name,diag.SOURCE.read_bytes())
 def restore_managed(self):
  self.info(self.oh);diag.require(q.p.run(['docker','exec',self.oh,'sha256sum',TARGET]).decode().split()[0]==SOURCE_SHA,'owned source drift')
  q.p.run(['docker','exec',self.oh,'rm',TARGET]);self.wait_absent()
  for name in diag.ITEMS:
   self.mutation('PUT','/items/'+name,diag.original_item(name));self.mutation('PUT','/items/'+name+'/metadata/stateDescription',diag.metadata(name))
 def checkpoint(self,directory,phase,histories,baseline=None,*,diagnostics_managed=True,group_managed=True):
  deadline=time.monotonic()+240
  while time.monotonic()<deadline:
   try:
    group=self.rest('/items/'+q.g.GROUP+'?metadata=.*');q.g.validate_group(group,managed=group_managed)
    rows=self.rest('/items?metadata=.*');diag.require({r['name'] for r in rows}==q.g.MEMBERS|{q.g.GROUP},'fixture Item scope drift')
    members={r['name']:r for r in rows if r['name']!=q.g.GROUP}
    for name in diag.ITEMS:diag.validate_item(members[name],name,managed=diagnostics_managed)
    for name in age.ITEMS:age.validate_item(members[name],name,managed=False)
    for name in ('WeatherData_HealthStatus','WeatherData_WH65B_AgeSeconds'):
     diag.require(members[name]['editable'] is True and members[name]['groupNames']==[q.g.GROUP] and members[name]['state'] not in ('NULL','UNDEF'),'protected member restoration drift')
    links=self.rest('/links');things=self.rest('/things')
    diag.require(len(links)==2 and len(things)==1 and self.rest('/rules')==[],'fixture dependency scope drift');diag.validate_links(links);age.validate_fixture_thing(things[0])
    for name in age.ITEMS:age.validate_links([link for link in links if link['itemName']==name],name,managed=False)
    if baseline is not None:
     for name in members:
      left=q.b.item_definition(members[name]);right=q.b.item_definition(baseline[name])
      if name in diag.ITEMS:right['metadata']['stateDescription']['editable']=diagnostics_managed
      diag.require(left==right and members[name]['state']==baseline[name]['state'],'member definition/state drift')
    break
   except (RuntimeError,ValueError,KeyError):time.sleep(2)
  else:raise RuntimeError('diagnostic/provider/history recovery timed out')
  diag.require(self.sql("SELECT count(*) FROM public.items WHERE itemname='gWeatherHealth';").strip()==b'0','Group JDBC identity appeared')
  for name,row in histories.items():
   table='item'+str(row['id']).zfill(4);data=self.sql("SET TIME ZONE 'UTC'; COPY (SELECT time,value FROM public."+table+" WHERE time<='"+row['cutoff']+"' ORDER BY time,value) TO STDOUT WITH CSV;")
   diag.require(len(data)==row['bytes'] and sha256(data).hexdigest()==row['sha256'],'original history prefix changed')
   diag.require(self.sql("SELECT itemid FROM public.items WHERE itemname='"+name+"';").strip()==str(row['id']).encode(),'JDBC identity changed')
  proof={'at':datetime.now(timezone.utc).isoformat(),'phase':phase,'members':members,'group':group,'links':links,'things':things,'diagnostics_managed':diagnostics_managed,'group_managed':group_managed,'all_six_history_prefixes_preserved':True,'container_host_pid':self.info(self.oh)['State']['Pid'],'production_writes':0}
  q.save(directory,phase+'.json',proof);print(json.dumps({key:proof[key] for key in ('phase','diagnostics_managed','group_managed','container_host_pid')}),flush=True)
  return members


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report-directory',required=True,type=Path);directory=parser.parse_args().report_directory
 diag.require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,'private report directory required')
 diag.require(not Path('/etc/openhab/items/'+diag.SOURCE.name).exists(),'candidate already installed')
 diag.require(sha256(diag.SOURCE.read_bytes()).hexdigest()==SOURCE_SHA,'source drift')
 for name in diag.ITEMS:diag.validate_item(q.b.oh.get('/items/'+name+'?metadata=.*'),name,managed=True)
 diag.validate_links(q.b.oh.get('/links'))
 _,selected,metadata,users,histories,guard=q.capture(directory);q.save(directory,'diagnostic-source.items',diag.SOURCE.read_bytes())
 fixture=Fixture()
 try:
  fixture.start(selected,metadata,users,histories,directory)
  baseline=fixture.checkpoint(directory,'managed-baseline',histories)
  fixture.withdraw_managed();fixture.install_file();fixture.checkpoint(directory,'file-handoff',histories,baseline,diagnostics_managed=False)
  before=fixture.info(fixture.oh)['State']['Pid'];q.f.run(['docker','restart',fixture.oh],timeout=90)
  fixture.checkpoint(directory,'file-cold-restart',histories,baseline,diagnostics_managed=False);diag.require(fixture.info(fixture.oh)['State']['Pid']!=before,'cold process unchanged')
  fixture.restore_managed();fixture.checkpoint(directory,'original-managed-rollback',histories,baseline)
  fixture.withdraw_managed();fixture.install_file();fixture.checkpoint(directory,'final-file-handoff',histories,baseline,diagnostics_managed=False)
  fixture.file_members=q.g.OBSERVER_FILE_MEMBERS
  fixture.stopped_edit(directory,remove=True);fixture.checkpoint(directory,'group-file-handoff',histories,baseline,diagnostics_managed=False,group_managed=False)
  before=fixture.info(fixture.oh)['State']['Pid'];q.f.run(['docker','restart',fixture.oh],timeout=90)
  fixture.checkpoint(directory,'group-file-cold-restart',histories,baseline,diagnostics_managed=False,group_managed=False);diag.require(fixture.info(fixture.oh)['State']['Pid']!=before,'Group cold process unchanged')
  fixture.stopped_edit(directory,remove=False);fixture.checkpoint(directory,'group-managed-rollback',histories,baseline,diagnostics_managed=False)
  fixture.stopped_edit(directory,remove=True);fixture.checkpoint(directory,'group-final-file-handoff',histories,baseline,diagnostics_managed=False,group_managed=False)
 except BaseException:
  if fixture.oh is not None:
   try:q.save(directory,'failed-docker.log',q.f.run(['docker','logs',fixture.oh],check=False).stdout);q.save(directory,'failed-rest-events.json',fixture.rest_events)
   except Exception:pass
  raise
 finally:fixture.cleanup()
 diag.require(q.live_guard()==guard,'production definitions/sources/JVM changed')
 db=q.connect()
 try:
  with db:
   for name,row in histories.items():diag.require(q.native_history(db,name,row['id'],cutoff=datetime.fromisoformat(row['cutoff']))==row,'production prefix changed')
 finally:db.close()
 q.save(directory,'qualification-proof.json',{'at':datetime.now(timezone.utc).isoformat(),'source_sha256':SOURCE_SHA,'member_histories':histories,'production_guard':guard,'native_diagnostic_round_trip':True,'native_four_file_member_group_round_trip':True,'production_writes':0,'production_diagnostics_still_managed':True,'production_group_still_managed':True,'production_restart_qualified':False,'owned_fixtures_removed':True,'binding_fetch_qualified':False})
 print('qualification=passed production_writes=0 diagnostic_and_group_production_providers=managed',flush=True)
if __name__=='__main__':main()
