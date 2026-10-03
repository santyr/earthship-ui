#!/usr/bin/env python3
"""Exercise the same Moon transaction core using contained fixture capabilities.

OpenHAB is networkless, no host mounts/ports/devices/rules. PostgreSQL is also
networkless: its sole host mount is an owned private temporary Unix-socket
directory, never production data/configuration; no port is published.
Only an existing private Moon recovery preimage enters the disposable database.
No production apply interface, release flag, SQL write or household command.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('isolated_moon_transaction', ROOT / 'scripts/migrate-astro-moon-thing.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
q = m.q
PG_IMAGE = 'postgres@sha256:95206741a5b214807675e14165369d05b93a9cf692223b616d07cca227e74b0b'
PG_LABEL = 'hex.astro.moon.history.qualification'
RECOVERY = Path('/home/sat/.local/state/openhab-config-migration/astro-moon-y363q6hk')
RECOVERY_SHA = 'af9d6449122165ab6cbb1e1cbae929c4b11dfa4d2426b539b2d31d361b9f7091'
ALLOWED_TYPES = {'timestamp with time zone', 'character varying', 'double precision'}


def create_database_container(arguments):
    """Keep Docker diagnostics useful without exposing environment arguments."""
    result = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    if result.returncode:
        category = 'other'
        for fragment, name in ((b'bind source path does not exist', 'socket_path_not_visible'),
                               (b'permission denied', 'permission_denied'),
                               (b'invalid mount config', 'invalid_mount')):
            if fragment in result.stderr.lower():
                category = name
                break
        print('isolated_database_create_failure=' + category, flush=True)
        raise RuntimeError('disposable database creation failed')
    identity = result.stdout.decode().strip()
    require(len(identity) == 64 and all(c in '0123456789abcdef' for c in identity),
            'unexpected disposable database identity')
    return identity


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def recovered():
    m.private_directory(RECOVERY)
    m.file_proof(RECOVERY / 'manifest.json')
    require(sha256((RECOVERY / 'manifest.json').read_bytes()).hexdigest() == RECOVERY_SHA,
            'original recovery point pin changed')
    m.file_proof(RECOVERY / 'preimage/snapshot.json')
    value = json.loads((RECOVERY / 'preimage/snapshot.json').read_bytes())
    value['captured_at'] = datetime.fromisoformat(value['captured_at'])
    require(set(value['history']) == set(q.HISTORY_IDS), 'original recovery identities changed')
    for name, row in value['history'].items():
        require(row['id'] == q.HISTORY_IDS[name], 'original recovery mapping changed')
        for key in ('first', 'cutoff'):
            row[key] = datetime.fromisoformat(row[key])
            require(q.aware_time(row[key]), 'original recovery timestamp ambiguous')
    m.verify_backup(RECOVERY, value)
    return value


def source_column_types():
    # Production is SELECT-only. Identifier types are closed before any DDL.
    db = m.database()
    try:
        db.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        with db:
            with db.cursor() as cursor:
                cursor.execute('SHOW transaction_read_only')
                require(cursor.fetchone() == ('on',), 'schema read is not read-only')
                cursor.execute('''SELECT cl.relname,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod)
                    FROM pg_catalog.pg_class cl JOIN pg_catalog.pg_namespace ns ON ns.oid=cl.relnamespace
                    JOIN pg_catalog.pg_attribute a ON a.attrelid=cl.oid WHERE ns.nspname=%s
                    AND cl.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY cl.relname,a.attnum''',
                    ('public', ['item' + str(i).zfill(4) for i in q.HISTORY_IDS.values()]))
                rows = cursor.fetchall()
    finally:
        db.close()
    expected = {'item' + str(i).zfill(4) for i in q.HISTORY_IDS.values()}
    result = {}
    for table, column, kind in rows:
        require(table in expected and column in ('time', 'value') and kind in ALLOWED_TYPES,
                'history schema outside qualified fixture types')
        require((table, column) not in result, 'duplicate history column')
        result[(table, column)] = kind
    require(len(result) == 56 and all(result[(table, 'time')] == 'timestamp with time zone'
                                     for table in expected), 'history schema incomplete')
    return result


def validate_pg(info, marker, socket):
    m.private_directory(socket.parent)
    require(socket.name == 'socket' and socket.parent.name.startswith('earthship-moon-pg-socket-')
            and socket.resolve() == socket and socket.is_dir()
            and socket.stat().st_uid == m.os.getuid()
            and socket.stat().st_mode & 0o7777 == 0o1777,
            'fixture socket path ownership/shape mismatch')
    host = info['HostConfig']
    require(info['Config']['Labels'].get(PG_LABEL) == marker
            and info['Config']['Image'] == PG_IMAGE and info['Config'].get('User') == '999:999'
            and host['NetworkMode'] == 'none' and not host['Privileged']
            and host['ReadonlyRootfs'] and not host.get('Binds') and not host.get('Devices')
            and host['Memory'] == host['MemorySwap'] == 512 * 1024**2
            and host['NanoCpus'] == 1_000_000_000 and not host.get('PortBindings'),
            'disposable database containment mismatch')
    require(set(info['NetworkSettings']['Networks']) == {'none'}
            and all(not bindings for bindings in info['NetworkSettings']['Ports'].values()),
            'unexpected database network/listener')
    mounts = [row for row in info.get('Mounts', []) if row.get('Type') != 'tmpfs']
    require(len(mounts) == 1 and mounts[0].get('Type') == 'bind'
            and mounts[0].get('Source') == str(socket)
            and mounts[0].get('Destination') == '/var/run/postgresql' and mounts[0].get('RW') is True,
            'unexpected database host data mount')


class HistoryFixture:
    def __init__(self, marker, types):
        self.marker, self.types = marker, types
        self.container = None
        self.temporary = None
        self.socket = None
        self.password = secrets.token_hex(32)
        self.reader_password = secrets.token_hex(32)

    def validate(self):
        info = json.loads(q.runtime.run(['docker', 'inspect', self.container]))[0]
        validate_pg(info, self.marker, self.socket)

    def admin(self):
        self.validate()
        return m.transport.psycopg2.connect(host=str(self.socket), port=5432, dbname='postgres',
            user='postgres', password=self.password, connect_timeout=3)

    def database(self):
        self.validate()
        db = m.transport.psycopg2.connect(host=str(self.socket), port=5432, dbname='postgres',
            user='moon_fixture_reader', password=self.reader_password, connect_timeout=3)
        db.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        return db

    def start(self, archived):
        # Snap's Docker daemon has a private /tmp; the owned workspace is visible.
        self.temporary = tempfile.TemporaryDirectory(prefix='earthship-moon-pg-socket-', dir=ROOT)
        self.socket = Path(self.temporary.name) / 'socket'
        self.socket.mkdir(mode=0o700)
        self.socket.chmod(0o1777)  # Parent stays private 0700; fixture UID owns its sockets.
        self.container = create_database_container(['docker', 'create', '--label', PG_LABEL+'='+self.marker,
            '--network', 'none', '--read-only', '--user', '999:999', '--cap-drop', 'ALL',
            '--memory', '512m', '--memory-swap', '512m', '--cpus', '1', '--pids-limit', '128',
            '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,nodev,size=384m,uid=999,gid=999,mode=700',
            '--mount', 'type=bind,source='+str(self.socket)+',target=/var/run/postgresql',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=16m,uid=999,gid=999',
            '--env', 'POSTGRES_PASSWORD='+self.password,
            PG_IMAGE, '-c', 'shared_buffers=32MB', '-c', 'max_connections=10', '-c', 'work_mem=4MB'])
        q.runtime.run(['docker', 'start', self.container])
        deadline = time.monotonic()+60
        while True:
            try:
                db = self.admin(); db.close(); break
            except m.transport.psycopg2.OperationalError:
                if time.monotonic() >= deadline: raise RuntimeError('disposable database startup timeout') from None
                time.sleep(.25)
        with closing(self.admin()) as db:
            with db:
                with db.cursor() as cursor:
                    cursor.execute("SET LOCAL TIME ZONE 'UTC'")
                    cursor.execute("SET LOCAL DateStyle='ISO, YMD'")
                    cursor.execute('CREATE TABLE public.items(itemname character varying PRIMARY KEY,itemid integer UNIQUE)')
                    for name, identity in sorted(q.HISTORY_IDS.items()):
                        table = 'item' + str(identity).zfill(4)
                        # Only fixed numeric names and the three closed types reach DDL.
                        cursor.execute('CREATE TABLE public.'+table+'(time '+self.types[(table,'time')]
                                       +',value '+self.types[(table,'value')]+')')
                        cursor.execute('INSERT INTO public.items VALUES (%s,%s)', (name,identity))
                        with (RECOVERY/'preimage'/(table+'.csv')).open('rb') as stream:
                            cursor.copy_expert('COPY public.'+table+'(time,value) FROM STDIN WITH CSV', stream)
                    cursor.execute('CREATE ROLE moon_fixture_reader LOGIN PASSWORD %s', (self.reader_password,))
                    cursor.execute('GRANT SELECT ON ALL TABLES IN SCHEMA public TO moon_fixture_reader')
        with closing(self.database()) as db:
            require(q.history_prefixes(db, before=archived['history']) == archived['history'],
                    'restored original history differs')
            with db:
                with db.cursor() as cursor:
                    cursor.execute("SELECT has_table_privilege(current_user,'public.items','INSERT')")
                    require(cursor.fetchone() == (False,), 'fixture reader gained write permission')
        print('isolated_original_28_csv_histories_restored=true; restricted_reader_select_only=true', flush=True)

    def close(self):
        if self.container is not None:
            owner = q.runtime.run(['docker','inspect','--format',
                '{{index .Config.Labels "'+PG_LABEL+'"}}',self.container]).decode().strip()
            require(owner == self.marker, 'database cleanup owner mismatch')
            q.runtime.run(['docker','rm','-f','-v',self.container])
        if self.temporary is not None:
            self.temporary.cleanup()
        print('owned_history_container_socket_directory_and_tmpfs_removed=true', flush=True)


def sun_contract(thing):
    value = q.definition(thing)
    for channel in value['channels']:
        channel.pop('linkedItems',None)  # Fixture has ONE explicitly different probe link.
    return value


class FixtureOperations:
    """No production capabilities; every mutation rechecks the owned container."""
    def __init__(self, context, history):
        self.context, self.history = context, history
        self.container, self.marker = context['container'], context['marker']
        self.file = '/openhab/conf/things/astro-moon.things'

    def validate(self):
        q.validate_container(json.loads(q.runtime.run(['docker','inspect',self.container]))[0], self.marker)
        require(not m.LIVE_RELEASE_READY, 'production live gate unexpectedly open')

    def get(self,path):
        require(path.startswith(('/things','/items','/links','/rules')), 'unknown fixture resource')
        code, row = self.context['rest']('GET',path)
        require(code == 200, 'fixture read unavailable')
        return row

    def get_thing(self):
        code, row = self.context['rest']('GET','/things/'+q.UID)
        require(code in (200,404), 'fixture Thing read unavailable')
        return row if code == 200 else None

    def target_exists(self):
        return q.runtime.run(['docker','exec',self.container,'sh','-c',
            'if [ -e '+self.file+' ] || [ -L '+self.file+' ]; then echo present; else echo absent; fi']).strip() == b'present'

    def request(self,method,path,original,body=None):
        self.validate()
        full=q.managed_thing(original)
        require(method=='DELETE' and path==m.DELETE_PATH and body is None
            or method=='POST' and path=='/things' and body=={k:v for k,v in full.items() if k!='channels'}
            or method=='PUT' and path=='/things/'+q.UID and body==full, 'fixture mutation outside Moon recovery')
        require(self.context['rest'](method,path,body)[0] in (200,201,202,204), 'fixture Moon mutation refused')

    def install_source(self,callback):
        self.validate(); require(not self.target_exists(),'fixture file already exists')
        q.runtime.install(self.container,'conf/things/astro-moon.things',m.source_ready())
        info=q.runtime.run(['docker','exec',self.container,'stat','-c','%d:%i',self.file]).decode().strip()
        callback(tuple(int(x) for x in info.split(':')))

    def remove_owned_file(self,identity):
        self.validate()
        info=q.runtime.run(['docker','exec',self.container,'stat','-c','%d:%i',self.file]).decode().strip()
        digest=q.runtime.run(['docker','exec',self.container,'sha256sum',self.file]).decode().split()[0]
        require(tuple(int(x) for x in info.split(':'))==identity and digest==q.SOURCE_SHA,
                'fixture file ownership/source drift')
        q.runtime.run(['docker','exec',self.container,'rm',self.file])

    def provider_ready(self,v,file_owned): return m.provider_ready(v,file_owned,getter=self.get_thing)
    def verify_unchanged(self,snapshot,**kwargs):
        try:
            return m.verify_unchanged(snapshot,get=self.get,**kwargs)
        except RuntimeError:
            links,items=m.current_dependents(self.get)
            print(json.dumps({'isolated_dependency_check':'withdrawal' if kwargs.get('withdrawal') else 'steady',
                'link_difference_paths':q.difference_paths(snapshot['links'],links)[:60],
                'item_difference_paths':q.difference_paths(snapshot['dependents'],items)[:60]},sort_keys=True),flush=True)
            raise
    def history_unchanged(self,v): return m.history_unchanged(v,factory=self.history.database)
    def wait(self,*args,**kwargs): return m.wait(*args,**kwargs)
    def qualify_phase(self,*args,**kwargs):
        result=m.qualify_phase(*args,operations=self,**kwargs)
        print('isolated_adapter_phase='+args[-1]+'; full_dependencies_and_28_histories_and_native_sun_moon=true',flush=True)
        return result
    def rollback(self,*args,**kwargs): return m.rollback(*args,operations=self,**kwargs)

    def guard_unchanged(self,verified):
        self.validate(); m.source_ready()
        sun=self.get('/things/astro:sun:local')
        require(sun.get('editable') is True and sun.get('statusInfo')=={'status':'ONLINE','statusDetail':'NONE'}
                and sun_contract(sun)==sun_contract(self.context['sun']), 'shared Sun definition changed')
        require(self.get('/rules')==[], 'household rule entered fixture')
        links=[row for row in self.get('/links') if row.get('channelUID','').startswith('astro:sun:local:')]
        require(len(links)==1 and links[0].get('itemName')=='Sun_Position_Elevation'
                and links[0].get('channelUID')=='astro:sun:local:position#elevation'
                and links[0].get('configuration')=={}, 'isolated Sun probe links changed')

    def pumps_off(self):
        # Absence of household controls is NOT a simulated physical OFF report.
        for name in ('SouthOutlet_Outlet2_Switch','East_Bed_Socket_Outlet_2_Power'):
            require(self.context['rest']('GET','/items/'+name)[0]==404, 'household actuator entered fixture')

    def natural_updates_after(self,after):
        log=q.runtime.run(['docker','exec',self.container,'tail','-c','4194304',
                           '/openhab/userdata/logs/events.log']).decode(errors='replace')
        return m.native_events(log,after)


def main():
    require(sys.argv[1:] == [], 'no live/apply/target interface')
    require(not m.LIVE_RELEASE_READY, 'production live gate open')
    archived=recovered(); types=source_column_types()
    history=HistoryFixture(secrets.token_hex(8),types)
    try:
        history.start(archived)
        def exercise(context):
            operations=FixtureOperations(context,history)
            evidence={'snapshot':{'thing':context['original'],'links':context['links'],
                       'dependents':context['dependents']}, 'intended':context['intended'],
                       'history':archived['history']}
            m.withdrawal_dependents(evidence['snapshot']['dependents'])
            with tempfile.TemporaryDirectory(prefix='earthship-moon-runtime-receipts-') as temporary:
                result=m.round_trip(Path(temporary),evidence,operations)
                require(result['managed_rollback_exercised'] is True,'adapter rollback not exercised')
            print('isolated_actual_adapter_round_trip_passed=true; production_live_gates=false',flush=True)
        q.main(binding_metadata=True,shared_sun=True,fixture_hook=exercise)
    finally:
        history.close()
    print('status=passed; production_writes=0; natural_jdbc_writer=not_tested; production_restart=not_tested',flush=True)


if __name__ == '__main__':
    try:
        main()
    except (Exception,KeyboardInterrupt) as error:
        locations=[]
        trace=error.__traceback__
        while trace:
            if trace.tb_frame.f_code.co_filename in (__file__,m.__file__,q.__file__):
                locations.append({'file':Path(trace.tb_frame.f_code.co_filename).name,
                                  'function':trace.tb_frame.f_code.co_name,'line':trace.tb_lineno})
            trace=trace.tb_next
        print(json.dumps({'failure_type':type(error).__name__,'locations':locations}),flush=True)
        raise SystemExit('isolated Moon handoff withheld; private diagnostics not emitted') from None
