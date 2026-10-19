#!/usr/bin/env python3
"""Cold Group/JDBC round trip in disconnected owned containers; live GET/SQL-read only.

This qualifier has no production apply path. It copies the current managed
Group/member records, their metadata and private API users.
Current file-owned age members retain their exact file and two inert channels.
No rules, hardware endpoints, exec scripts or production database credentials enter it.
"""
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import gzip
import io
import tarfile
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import weather_health_group as g
import file_migration_batch as b

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/file)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

h = load('weather_group_history', 'migrate-moon-weather-batch.py')
p = load('weather_group_jdbc_helpers', 'openhab_qualification_jdbc.py')
f = load('weather_group_file_helpers', 'openhab_qualification_fixture.py')
protected = load('weather_group_protected', 'migrate-battery-charging-status-item.py')
SOURCE = ROOT/'openhab/file-config/items/weather-health-group.items'
SOURCE_SHA = 'b2eae0fe035a099fa079d0854cd866ecf9986836a2ff7a1b5d5ecfb043dd762f'
LABEL = 'hex.weather.health.group.qualification'
REGISTRY = '/openhab/userdata/jsondb/org.openhab.core.items.Item.json'
TARGET = '/openhab/conf/items/'+SOURCE.name
VALUE_TYPES = {541:'varchar',540:'timestamptz',535:'varchar',
               532:'double precision',534:'double precision',533:'double precision'}


def save(directory, name, value):
    b.private_file(directory, name, value if isinstance(value, bytes) else b.encoded(value))


def live_guard():
    selected=b.oh.get('/items/BatteryChargingStatus?metadata=.*')
    return {'registry_sources_jvm':protected.protected_signature(),
            'additional_item':{**b.item_definition(selected),'editable':selected.get('editable')}}


def connect():
    settings = h.parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    db = h.psycopg2.connect(**settings.connect_kwargs, connect_timeout=3)
    db.set_session(readonly=True, isolation_level='REPEATABLE READ')
    return db


def native_history(db, name, identity, *, cutoff=None, output=None):
    with db.cursor() as c:
        c.execute("SET LOCAL TIME ZONE 'UTC'"); c.execute("SET LOCAL statement_timeout='60s'")
        c.execute('SELECT itemid FROM public.items WHERE itemname=%s', (name,))
        g.require(c.fetchall()==[(identity,)], 'member JDBC identity drift')
        table=h.sql.Identifier('item'+str(identity).zfill(4))
        query=h.sql.SQL('SELECT count(*),max(time) FROM public.{}').format(table)
        if cutoff is not None: query+=h.sql.SQL(' WHERE time<=%s')
        c.execute(query, () if cutoff is None else (cutoff,)); count,end=c.fetchone()
        g.require(count>0 and end is not None, 'member history missing')
        digest=h.DigestWriter(output)
        c.copy_expert(h.sql.SQL('COPY (SELECT time,value FROM public.{} WHERE time<={} '
            'ORDER BY time,value) TO STDOUT WITH CSV').format(table,h.sql.Literal(end)).as_string(db),digest)
        return {'id':identity,'count':count,'cutoff':end.isoformat(),
                'sha256':digest.digest.hexdigest(),'bytes':digest.size}


def capture(directory):
    original=b.oh.get('/items/'+g.GROUP+'?metadata=.*'); g.validate_group(original, managed=True)
    g.require(not any(link.get('itemName')==g.GROUP for link in b.oh.get('/links')),
              'weather-health Group unexpectedly linked')
    g.require(not Path('/etc/openhab/items/'+SOURCE.name).exists(),'candidate already installed')
    g.require(sha256(SOURCE.read_bytes()).hexdigest()==SOURCE_SHA,'candidate source drift')
    guard=live_guard()
    registry=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json').read_text())
    file_members=g.file_member_scope(registry,original)
    g.cold_edit(b.encoded(registry),remove=True,original=g.GROUP_RECORD,file_members=file_members)
    selected={n:registry[n] for n in sorted((g.MEMBERS-file_members)|{g.GROUP})}
    sources=[]
    if file_members:
        import weather_health_age_items as age
        validators=[(age,'c1cba28d41c685d40eb61628d866b488365543d7f7bbff45a139a81aad3768e4','dependency-age-source.items')]
        if file_members==g.OBSERVER_FILE_MEMBERS:
            import sky_diagnostic_items as diag
            validators.append((diag,'3c6e43fbb3d6d03723341efa425c4dfb5143722fb2cdbcd0fe42ba43561ebca3','dependency-diagnostic-source.items'))
        links=b.oh.get('/links')
        for validator,digest,backup in validators:
            source=validator.SOURCE;target=Path('/etc/openhab/items/'+source.name)
            g.require(not source.is_symlink() and not target.is_symlink() and source.read_bytes()==target.read_bytes()
                      and sha256(source.read_bytes()).hexdigest()==digest,'file member source drift')
            for name in validator.ITEMS:validator.validate_item(b.oh.get('/items/'+name+'?metadata=.*'),name,managed=False)
            if validator is age:
                for name in age.ITEMS:age.validate_links([link for link in links if link['itemName']==name],name,managed=False)
            else:validator.validate_links(links)
            save(directory,backup,source.read_bytes());sources.append({'filename':source.name,'sha256':digest,'backup':backup})
        native=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.thing.Thing.json').read_text())
        save(directory,'dependency-inert-thing.json',{'http:url:weatherHealth':age.inert_fixture_thing(native['http:url:weatherHealth'])})
    save(directory,'file-member-context.json',{'names':sorted(file_members),'sources':sources})
    metadata=json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.items.Metadata.json').read_text())
    metadata={k:v for k,v in metadata.items() if
              v.get('value',{}).get('key',{}).get('segments',[None,None])[-1] in selected}
    users=Path('/var/lib/openhab/jsondb/users.json').read_bytes()
    histories={}; db=connect()
    try:
        with db,db.cursor() as c:
            c.execute('SELECT itemid FROM public.items WHERE itemname=%s',(g.GROUP,))
            g.require(c.fetchall()==[],'plain Group unexpectedly has a JDBC identity')
            for name,identity in sorted(g.ITEM_IDS.items()):
                fd=os.open(directory/('item'+str(identity).zfill(4)+'.csv.gz'),
                           os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as out:
                    with gzip.GzipFile(filename='',fileobj=out,mode='wb',mtime=0,compresslevel=1) as z:
                        histories[name]=native_history(db,name,identity,output=z)
                    out.flush();os.fsync(out.fileno())
    finally: db.close()
    save(directory,'original-group.json',original); save(directory,'selected-items.json',selected)
    save(directory,'selected-metadata.json',metadata); save(directory,'private-users.json',users)
    save(directory,'history-prefixes.json',histories); save(directory,'before-protected.json',guard)
    save(directory,'qualified-source.items',SOURCE.read_bytes())
    return original,selected,metadata,users,histories,guard


class Fixture:
    def __init__(self):
        self.marker=secrets.token_hex(16); self.pg=None; self.oh=None
        self.auth_wait_started={}; self.auth_events=[]; self.rest_events=[]; self.file_members=frozenset()

    def info(self, cid):
        value=json.loads(p.run(['docker','inspect',cid]))[0]
        g.require(value['Config']['Labels'].get(LABEL)==self.marker,'foreign fixture')
        return value

    def sql(self, query, data=None):
        self.info(self.pg)
        return p.run(['docker','exec','-i',self.pg,'psql','-q','-v','ON_ERROR_STOP=1',
                      '-U','postgres','-d','postgres','-Atc',query],data)

    def start(self, selected, metadata, users, histories, directory):
        password=secrets.token_hex(24)
        save(directory,'fixture-identity.json',{'marker':self.marker,'label':LABEL})
        self.pg=p.run(['docker','run','-d','--network','none','--label',LABEL+'='+self.marker,
            '--memory','768m','--memory-swap','768m','--cpus','2',
            '--tmpfs','/var/lib/postgresql/data:rw,size=768m',
            '-e','POSTGRES_PASSWORD='+password,'postgres:16']).decode().strip()
        save(directory,'postgres-handle.json',{'cid':self.pg,'marker':self.marker})
        info=self.info(self.pg); host=info['HostConfig']
        g.require(host['NetworkMode']=='none' and not host['Privileged']
                  and not host.get('Binds') and not host.get('PortBindings')
                  and not host.get('Devices'),'database isolation drift')
        for _ in range(60):
            try: self.sql('SELECT 1'); break
            except RuntimeError: time.sleep(1)
        else: raise RuntimeError('owned PostgreSQL startup timed out')
        self.sql('CREATE TABLE public.items (itemid serial PRIMARY KEY,itemname varchar(255));')
        for name,row in sorted(histories.items()):
            identity=row['id']; table='item'+str(identity).zfill(4)
            self.sql("INSERT INTO public.items(itemid,itemname) VALUES ("+str(identity)+",'"+name+"');"
                     'CREATE TABLE public.'+table+' (time timestamptz,value '+VALUE_TYPES[identity]+');')
            with gzip.open(directory/(table+'.csv.gz'),'rb') as z:
                self.sql('COPY public.'+table+' FROM STDIN WITH CSV;',z.read())
            self.sql('CREATE INDEX ON public.'+table+' (time);')
        self.sql("SELECT setval('items_itemid_seq',(SELECT max(itemid) FROM public.items));")
        self.oh=p.run(['docker','run','-d','--label',LABEL+'='+self.marker,
            '--network','container:'+self.pg,'--cap-drop','ALL',
            '--pids-limit','384','--memory','2g','--memory-swap','2g',
            '--tmpfs','/tmp:rw,nosuid,nodev,size=128m',
            '-e','EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint','/bin/sh',p.IMAGE,'-c',
            'cp -a /openhab/dist/conf/. /openhab/conf/; '
            'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
            'touch /tmp/weather-bootstrap; '
            'while [ ! -f /openhab/conf/.weather-ready ]; do sleep 1; done; '
            'exec /openhab/start.sh server']).decode().strip()
        save(directory,'openhab-handle.json',{'cid':self.oh,'marker':self.marker})
        info=self.info(self.oh); host=info['HostConfig']
        g.require(host['NetworkMode']=='container:'+self.pg and not host['Privileged']
                  and not host.get('Binds') and not host.get('PortBindings')
                  and not host.get('Devices'),'OpenHAB isolation drift')
        p.run(['docker','exec',self.oh,'sh','-c',
               'while [ ! -f /tmp/weather-bootstrap ]; do sleep 1; done'])
        p.run(['docker','exec',self.oh,'mkdir','-p','/openhab/userdata/jsondb'])
        for path,body in [('org.openhab.core.items.Item.json',b.encoded(selected)),
                          ('org.openhab.core.items.Metadata.json',b.encoded(metadata)),('users.json',users)]:
            f.install_bytes(self.oh,'/openhab/userdata/jsondb',path,body,mode=0o600)
        context=directory/'file-member-context.json'
        if context.exists():
            context=json.loads(context.read_text());self.file_members=frozenset(context['names'])
        if self.file_members:
            g.require(self.file_members in g.FILE_MEMBER_SCOPES,'unsupported fixture file members')
            expected={'weather-health-ages.items':'c1cba28d41c685d40eb61628d866b488365543d7f7bbff45a139a81aad3768e4'}
            if self.file_members==g.OBSERVER_FILE_MEMBERS:expected['sky-diagnostics.items']='3c6e43fbb3d6d03723341efa425c4dfb5143722fb2cdbcd0fe42ba43561ebca3'
            source_rows=context.get('sources',[{'filename':'weather-health-ages.items','sha256':expected['weather-health-ages.items'],'backup':'dependency-age-source.items'}])
            g.require({row['filename']:row['sha256'] for row in source_rows}==expected and len(source_rows)==len(expected),'fixture dependency list drift')
            for row in source_rows:
                g.require(row['backup'] in ('dependency-age-source.items','dependency-diagnostic-source.items'),'unexpected private source path')
                source=(directory/row['backup']).read_bytes();g.require(sha256(source).hexdigest()==row['sha256'],'fixture file dependency drift')
                f.install_bytes(self.oh,'/openhab/conf/items',row['filename'],source)
            f.install_bytes(self.oh,'/openhab/userdata/jsondb','org.openhab.core.thing.Thing.json',
                            (directory/'dependency-inert-thing.json').read_bytes(),mode=0o600)
        for relative in p.isolated.BUNDLES:
            source=p.isolated.CACHE/relative
            f.install_bytes(self.oh,'/openhab/addons',source.name,source.read_bytes())
        f.install_bytes(self.oh,'/openhab/conf/services','jdbc.cfg',('url=jdbc:postgresql://127.0.0.1:5432/postgres\n'
            'user=postgres\npassword='+password+'\n').encode(),mode=0o600)
        p.install(self.oh,'persistence/jdbc.persist',
                  (ROOT/'openhab/file-config/persistence/jdbc.persist').read_bytes())
        p.run(['docker','exec',self.oh,'touch','/openhab/conf/.weather-ready'])
        save(directory,'fixture-handles.json',{'marker':self.marker,'pg':self.pg,'openhab':self.oh})

    def rest(self, path):
        info=self.info(self.oh); pid=info['State']['Pid']
        for attempt in range(4):
            try:
                code,body=p.request(self.oh,('Authorization: Bearer '+b.oh.token()+'\n').encode(),path)
                self.rest_events.append({'at':datetime.now(timezone.utc).isoformat(),
                    'path':path,'code':code,'container_host_pid':pid})
                if (code>=500 or (code==404 and path.startswith('/items?'))) and attempt<3:
                    time.sleep(2); continue
                break
            except RuntimeError:
                if attempt==3: raise
                time.sleep(2)
        if code in (401,403):
            start=self.auth_wait_started.setdefault(pid,time.monotonic())
            self.auth_events.append({'at':datetime.now(timezone.utc).isoformat(),
                                     'container_host_pid':pid,'http_status':code})
            if time.monotonic()-start>60:
                raise PermissionError('owned REST auth did not recover within startup budget')
            raise RuntimeError('owned REST auth registry still initializing')
        g.require(code==200,'owned REST read unavailable HTTP '+str(code))
        return json.loads(body)

    def wait_group(self, managed, seconds=240):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                group=self.rest('/items/'+g.GROUP+'?metadata=.*'); g.validate_group(group,managed=managed)
                return group
            except (RuntimeError,ValueError): time.sleep(2)
        raise RuntimeError('owned Group/provider/members did not recover')

    def ready_items(self):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            try:return self.rest('/items?metadata=.*')
            except RuntimeError:time.sleep(2)
        raise RuntimeError('owned Item census did not recover after REST startup transition')

    def checkpoint(self, directory, phase, histories, baseline=None, managed=True):
        group=self.wait_group(managed)
        items=self.ready_items()
        g.require({i['name'] for i in items}==g.MEMBERS|{g.GROUP},'unexpected fixture Item')
        members={i['name']:i for i in items if i['name']!=g.GROUP}
        deadline=time.monotonic()+120
        while any(i['state'] in ('NULL','UNDEF') for i in members.values()):
            g.require(time.monotonic()<deadline,'member states not restored by JDBC')
            time.sleep(2); members={i['name']:i for i in self.ready_items() if i['name']!=g.GROUP}
        if baseline is not None: g.require(members==baseline,'member definitions/state/provider drift')
        g.require(all(i.get('editable') is (name not in self.file_members) and i['groupNames']==[g.GROUP]
                      for name,i in members.items()),'member providers or references changed')
        g.require(self.sql("SELECT count(*) FROM public.items WHERE itemname='gWeatherHealth';").strip()==b'0',
                  'Group unexpectedly acquired JDBC identity')
        for name,row in histories.items():
            table='item'+str(row['id']).zfill(4)
            found=self.sql("SET TIME ZONE 'UTC'; COPY (SELECT time,value FROM public."+table+
                " WHERE time<='"+row['cutoff']+"' ORDER BY time,value) TO STDOUT WITH CSV;")
            g.require(sha256(found).hexdigest()==row['sha256'] and len(found)==row['bytes'],
                      'original member history prefix changed: '+name)
            g.require(self.sql("SELECT itemid FROM public.items WHERE itemname='"+name+"';").strip()
                      ==str(row['id']).encode(),'member identity drift')
        g.require(self.rest('/rules')==[],'fixture contains executable rules')
        links=self.rest('/links');things=self.rest('/things')
        if self.file_members:
            import weather_health_age_items as age
            g.require(len(links)==2 and len(things)==1,'fixture dependency scope drift')
            age.validate_fixture_thing(things[0])
            for name in age.ITEMS:
                age.validate_item(members[name],name,managed=False)
                age.validate_links([link for link in links if link['itemName']==name],name,managed=False)
            if self.file_members==g.OBSERVER_FILE_MEMBERS:
                import sky_diagnostic_items as diag
                diag.validate_links(links)
                for name in diag.ITEMS:diag.validate_item(members[name],name,managed=False)
        else:g.require(things==[] and links==[],'unexpected fixture Things or links')
        info=self.info(self.oh)
        value={'at':datetime.now(timezone.utc).isoformat(),'phase':phase,'group':group,'members':members,
               'all_original_history_prefixes':True,'group_jdbc_identity_absent':True,
               'file_member_names':sorted(self.file_members),'links':links,'things':things,
               'container_host_pid':info['State']['Pid'],'isolated_only':True,
               'startup_auth_events':list(self.auth_events),'rest_events':list(self.rest_events)}
        save(directory,phase+'.json',value); print(json.dumps({'phase':phase,'history_prefixes':6,
              'members':6,'managed_group':managed,'container_host_pid':info['State']['Pid']}),flush=True)
        return members

    def stopped_edit(self, temporary, *, remove):
        self.info(self.oh); f.run(['docker','stop','-t','30',self.oh],timeout=60)
        g.require(not self.info(self.oh)['State']['Running'],'owned JVM still running')
        output=p.run(['docker','cp',self.oh+':'+REGISTRY,'-'])
        with tarfile.open(fileobj=io.BytesIO(output),mode='r:') as archive:
            entry=next(member for member in archive if member.isfile())
            body=archive.extractfile(entry).read()
        changed=g.cold_edit(body,remove=remove,original=g.GROUP_RECORD,file_members=self.file_members)
        def cold_copy(directory,name,data):
            output=io.BytesIO()
            with tarfile.open(fileobj=output,mode='w') as archive:
                member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644
                archive.addfile(member,io.BytesIO(data))
            p.run(['docker','cp','-',self.oh+':'+directory],output.getvalue())
        cold_copy('/openhab/userdata/jsondb','org.openhab.core.items.Item.json',changed)
        cold_copy('/openhab/conf/items',SOURCE.name,SOURCE.read_bytes() if remove else b'')
        p.run(['docker','start',self.oh])

    def cleanup(self):
        errors=[]
        for cid in (self.oh,self.pg):
            if cid is not None:
                try:
                    self.info(cid); f.run(['docker','rm','-f','-v',cid],timeout=90)
                    found=subprocess.run(['docker','inspect',cid],capture_output=True,timeout=10)
                    g.require(found.returncode!=0,'owned container remains after removal')
                except Exception:
                    errors.append(cid)
        g.require(not errors,'owned fixture cleanup incomplete; retained private handles')
        print('owned_fixture_containers_removed=true',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-directory',required=True,type=Path)
    args=parser.parse_args(); directory=args.report_directory
    g.require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,
              'private report directory required')
    original,selected,metadata,users,histories,guard=capture(directory)
    fixture=Fixture()
    try:
        fixture.start(selected,metadata,users,histories,directory)
        baseline=fixture.checkpoint(directory,'managed-baseline',histories)
        with tempfile.TemporaryDirectory(prefix='weather-group-offline-',dir=ROOT) as temp:
            temporary=Path(temp);temporary.chmod(0o700)
            fixture.stopped_edit(temporary,remove=True)
            fixture.checkpoint(directory,'file-handoff',histories,baseline,managed=False)
            before=fixture.info(fixture.oh)['State']['Pid']
            f.run(['docker','restart',fixture.oh],timeout=90)
            fixture.checkpoint(directory,'file-cold-restart',histories,baseline,managed=False)
            g.require(fixture.info(fixture.oh)['State']['Pid']!=before,'cold restart process unchanged')
            fixture.stopped_edit(temporary,remove=False)
            fixture.checkpoint(directory,'original-managed-rollback',histories,baseline)
            fixture.stopped_edit(temporary,remove=True)
            fixture.checkpoint(directory,'final-file-handoff',histories,baseline,managed=False)
    except BaseException:
        if fixture.oh is not None:
            try:
                save(directory,'failed-fixture-openhab.log',
                     f.run(['docker','logs',fixture.oh],check=False).stdout)
                save(directory,'failed-auth-events.json',fixture.auth_events)
                save(directory,'failed-rest-events.json',fixture.rest_events)
                log=f.run(['docker','exec',fixture.oh,'cat','/openhab/userdata/logs/openhab.log'],check=False)
                save(directory,'failed-application.log',log.stdout+log.stderr)
            except Exception:
                pass
        raise
    finally: fixture.cleanup()
    g.require(live_guard()==guard,'production definitions/sources/JVM changed')
    db=connect()
    try:
        with db,db.cursor() as c:
            c.execute('SELECT itemid FROM public.items WHERE itemname=%s',(g.GROUP,))
            g.require(c.fetchall()==[],'production Group identity changed')
            for name,row in histories.items():
                g.require(native_history(db,name,row['id'],cutoff=datetime.fromisoformat(row['cutoff']))==row,
                          'production history prefix drift')
    finally: db.close()
    g.validate_group(b.oh.get('/items/'+g.GROUP+'?metadata=.*'),managed=True)
    save(directory,'qualification-proof.json',{'at':datetime.now(timezone.utc).isoformat(),
         'source_sha256':SOURCE_SHA,'member_histories':histories,'production_guard':guard,
         'native_cold_round_trip':True,'native_file_restart':True,'production_writes':0,
         'production_group_still_managed':True,'production_restart_qualified':False,
         'owned_fixture_removed':True,'file_member_names':sorted(fixture.file_members),'binding_fetch_qualified':False})
    print('qualification=passed production_writes=0 live_group_provider=managed',flush=True)


if __name__=='__main__': main()
