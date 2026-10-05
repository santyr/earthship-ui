#!/usr/bin/env python3
"""Closed one-Switch handoff; check is read-only and live release defaults off."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import fcntl
import gzip
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import file_migration_batch as b
oh = b.oh
spec = importlib.util.spec_from_file_location('charging_history_tools',
    ROOT/'scripts/migrate-moon-weather-batch.py')
history_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history_tools)

ITEM = 'BatteryChargingStatus'
RULE = 'UpdateBatteryIcon'
ITEM_ID = 154
SOURCE = ROOT/'openhab/file-config/items/battery-charging-status.items'
TARGET = Path('/etc/openhab/items/battery-charging-status.items')
SOURCE_SHA256 = '546d5498d3392b6ea041850d7a869783b7a3f29a56a49e5cfdbdb97a6200802a'
WRITER_SOURCE = ROOT/'openhab/file-config/automation/js/battery-icon.js'
WRITER_TARGET = Path('/etc/openhab/automation/js/battery-icon.js')
WRITER_SHA256 = 'bc6c0954b232902d4b5af444b6381cf5c8ea4af062aa5a12b8195de364729b45'
BACKUP_ROOT = history_tools.BACKUP_ROOT
RELEASE_READY = False
ORIGINAL_DTO = {'name': ITEM, 'type': 'Switch', 'label': ITEM,
                'category': '', 'tags': [], 'groupNames': []}


def allowed_mutation(method, path, body):
    if path == '/items/'+ITEM:
        if method == 'DELETE' and body is None:
            return
        if method == 'PUT' and body == ORIGINAL_DTO:
            return
    if (method == 'POST' and path == '/rules/'+RULE+'/enable'
            and type(body) is bool):
        return
    raise RuntimeError('mutation outside exact charging-status scope')


def request(method, path, body=None):
    b.require(RELEASE_READY, 'attended release gate closed')
    allowed_mutation(method, path, body)
    content = 'application/json'
    data = None
    if type(body) is bool:
        data, content = (b'true' if body else b'false'), 'text/plain'
    elif body is not None:
        data = b.encoded(body)
    with urlopen(Request(oh.BASE+path, method=method, data=data,
            headers={'Authorization': 'Bearer '+oh.token(), 'Content-Type': content}),
            timeout=15) as response:
        b.require(response.status in (200, 201, 202, 204), 'exact mutation refused')


def validate_descriptor(item, *, managed):
    b.require(type(managed) is bool and item is not None and item.get('editable') is managed,
              'Item provider drift')
    for name, expected in ORIGINAL_DTO.items():
        actual = item.get(name)
        if name == 'category':
            actual = actual or ''
        b.require(actual == expected, 'Item descriptor drift: '+name)
    b.require(not item.get('metadata') and not item.get('stateDescription')
              and not item.get('unitSymbol'), 'Item metadata or unit drift')


def validate_item(item, *, managed, state=None):
    validate_descriptor(item, managed=managed)
    b.require(item.get('state') in ('ON', 'OFF') and
              (state is None or item['state'] == state), 'Item state unrestored')


def validate_writer(rule, *, disabled):
    b.require(rule.get('uid') == RULE and rule.get('editable') is False,
              'writer ownership drift')
    triggers = rule.get('triggers', [])
    actions = rule.get('actions', [])
    b.require(len(triggers) == 1 and
        triggers[0].get('type') == 'timer.GenericCronTrigger' and
        triggers[0].get('configuration') == {'cronExpression': '0/30 * * * * ?'}
        and not rule.get('conditions') and len(actions) == 1 and
        actions[0].get('type') == 'jsr223.ScriptedAction', 'writer contract drift')
    config = actions[0].get('configuration', {})
    b.require(set(config) == {'privId'} and type(config['privId']) is str and
              re.fullmatch(r'i[0-9]{1,9}', config['privId']) is not None,
              'writer registration drift')
    expected = ({'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'} if disabled
                else {'status': 'IDLE', 'statusDetail': 'NONE'})
    b.require(rule.get('status') == expected, 'writer status drift')


def file_identity(target, digest):
    info = target.lstat()
    b.require(stat.S_ISREG(info.st_mode) and not target.is_symlink() and
              sha256(target.read_bytes()).hexdigest() == digest,
              'watched file source drift')
    return info.st_dev, info.st_ino


def withdraw_owned(target, directory, digest, identity, number):
    b.require(file_identity(target, digest) == identity, 'watched file ownership drift')
    saved = directory/('withdrawal-'+str(number)+'.items')
    b.require(not saved.exists() and not saved.is_symlink(), 'recovery entry exists')
    # Hard-link the verified inode exclusively before removing its watched name.
    os.link(target, saved, follow_symlinks=False)
    b.require(file_identity(target, digest) == identity and
              file_identity(saved, digest) == identity, 'watched file ownership drift')
    target.unlink()
    saved.chmod(0o600)
    history_tools.sync_directory(target.parent)
    history_tools.sync_directory(directory)
    return saved


def preflight(db):
    b.require(not TARGET.exists() and not TARGET.is_symlink(), 'file target already exists')
    file_identity(SOURCE, SOURCE_SHA256)
    original = item()
    validate_item(original, managed=True)
    b.require(not any(x['itemName'] == ITEM for x in oh.get('/links')),
              'charging-status Item unexpectedly linked')
    writer(disabled=False)
    before = history(db)
    b.require(before['last_state'] == original['state'], 'JDBC state not caught up')
    return original, before, protected_signature()


def item():
    try:
        return oh.get('/items/'+ITEM+'?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def writer(*, disabled):
    file_identity(WRITER_SOURCE, WRITER_SHA256)
    file_identity(WRITER_TARGET, WRITER_SHA256)
    rule = oh.get('/rules/'+RULE)
    validate_writer(rule, disabled=disabled)
    return rule


def protected_signature():
    items = oh.get('/items?metadata=.*')
    rules = oh.get('/rules')
    links = oh.get('/links')
    things = oh.get('/things')
    declarations = json.loads((ROOT/'openhab/file-config/ownership.json').read_text())
    files = {}
    for row in declarations['resources']:
        if row.get('provider') != 'file' or not row.get('destination'):
            continue
        source = ROOT/row['source'] if row['source'].startswith('openhab/') else ROOT/'openhab/file-config'/row['source']
        target = Path(row['destination'])
        b.require(not source.is_symlink() and not target.is_symlink()
                  and source.read_bytes() == target.read_bytes(), 'installed source drift')
        files[str(target)] = sha256(source.read_bytes()).hexdigest()
    normalized_things = []
    for thing in things:
        row = b.thing_definition(thing)
        for channel in row['channels']:
            channel.pop('linkedItems', None)  # Derived membership; links compared independently.
        row['editable'] = thing.get('editable')
        normalized_things.append(row)
    rule_fields = ('uid','name','description','visibility','configuration','triggers',
                   'conditions','actions','editable')
    signature = {
        'items': sorted([{**b.item_definition(x), 'editable': x.get('editable'),
            'groupType':x.get('groupType'), 'function':x.get('function')}
            for x in items if x['name'] != ITEM], key=lambda x:x['name']),
        'rules': sorted([{**{k:x.get(k) for k in rule_fields},
            'tags': sorted(x.get('tags',[]))} for x in rules], key=lambda x:x['uid']),
        'links': sorted(links, key=lambda x:(x['itemName'],x['channelUID'])),
        'things': sorted(normalized_things,key=lambda x:x['UID']),
        'files': files,
    }
    pid = subprocess.check_output(['systemctl','show','openhab.service','-p',
                                  'MainPID','--value'],text=True,timeout=5).strip()
    b.require(pid.isdigit() and int(pid) > 0, 'OpenHAB JVM unavailable')
    return {'pid': pid, 'sha256': sha256(b.encoded(signature)).hexdigest()}


def history(db, cutoff=None, output=None):
    with db, db.cursor() as cur:
        cur.execute("SET LOCAL TIME ZONE 'UTC'")
        cur.execute("SET LOCAL statement_timeout='20s'")
        cur.execute('SELECT itemid FROM public.items WHERE itemname=%s',(ITEM,))
        b.require(cur.fetchall() == [(154,)], 'JDBC identity drift')
        cur.execute('SELECT count(*),max(time) FROM public.item0154'+
                    (' WHERE time<=%s' if cutoff is not None else ''),
                    (cutoff,) if cutoff is not None else ())
        count, end = cur.fetchone()
        b.require(count > 0 and end is not None, 'original history missing')
        cur.execute('SELECT value::text FROM public.item0154 WHERE time<=%s '
                    'ORDER BY time DESC,value DESC LIMIT 1',(end,))
        last = cur.fetchone()[0]
        b.require(last in ('ON','OFF'), 'latest JDBC Switch value invalid')
        digest = history_tools.DigestWriter(output)
        cur.copy_expert(history_tools.sql.SQL('COPY (SELECT time,value FROM '
            'public.item0154 WHERE time<={} ORDER BY time,value) TO STDOUT WITH CSV')
            .format(history_tools.sql.Literal(end)).as_string(db), digest)
    return {'id':154,'count':count,'cutoff':end.isoformat(),'last_state':last,
            'sha256':digest.digest.hexdigest(),'bytes':digest.size}


def backup_history(db, directory, name, before):
    fd = os.open(directory/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
            copied = history(db, datetime.fromisoformat(before['cutoff']), compressed)
        raw.flush()
        os.fsync(raw.fileno())
    b.require(copied == before, 'recoverable history backup mismatch')
    history_tools.sync_directory(directory)


def wait_for(predicate, seconds=90):
    deadline = time.monotonic()+seconds
    while True:
        if predicate():
            return
        b.require(time.monotonic() < deadline, 'provider or writer recovery timeout')
        time.sleep(.5)


class Operations:
    def __init__(self, db):
        self.db = db
        self.original, self.before, self.guard = preflight(db)
        self.directory = None
        self.owned_identity = None
        self.withdrawals = 0
        self.pause_attempted = False
        self.item_change_attempted = False
        self.frozen = False
        self.recovered = False
        self.safe_to_resume = False

    def backup(self):
        root = BACKUP_ROOT.lstat()
        b.require(stat.S_ISDIR(root.st_mode) and not BACKUP_ROOT.is_symlink()
            and root.st_uid == os.getuid() and stat.S_IMODE(root.st_mode) == 0o700,
            'private backup root unsafe')
        self.directory = Path(tempfile.mkdtemp(prefix='charging-status-file-',dir=BACKUP_ROOT))
        self.directory.chmod(0o700)
        b.private_file(self.directory,'preflight.json',b.encoded({'original':self.original,
            'history':self.before,'protected':self.guard,'source_sha256':SOURCE_SHA256,
            'original_writer':writer(disabled=False),'original_writer_enabled':True}))
        b.private_file(self.directory,'qualified-source.items',SOURCE.read_bytes())
        backup_history(self.db,self.directory,'original-item0154.csv.gz',self.before)
        history_tools.sync_directory(self.directory)
        history_tools.sync_directory(BACKUP_ROOT)

    def preserved(self):
        b.require(history(self.db,datetime.fromisoformat(self.before['cutoff'])) == self.before,
                  'original JDBC history prefix changed')
        b.require(protected_signature() == self.guard, 'unrelated definition/source/JVM drift')
        file_identity(SOURCE,SOURCE_SHA256)

    def paused_writer(self):
        return self.writer_ready(disabled=True)

    def writer_ready(self, *, disabled):
        try:
            writer(disabled=disabled)
            return True
        except RuntimeError as error:
            if str(error) == 'writer status drift':
                return False
            raise

    def wait_item(self, managed):
        def ready():
            current = item()
            if managed is None:
                return current is None
            if current is None or current.get('editable') is not managed:
                return False
            if current.get('state') in (None,'NULL','UNDEF'):
                return False
            validate_item(current,managed=managed,
                          state=self.original['state'] if self.frozen else None)
            return True
        wait_for(ready)

    def withdraw_managed(self):
        if not self.pause_attempted:
            self.preserved()
            writer(disabled=False)
            self.pause_attempted = True  # Timeout may follow an accepted enable write.
            request('POST','/rules/'+RULE+'/enable',False)
            wait_for(self.paused_writer)
            current = item()
            validate_item(current,managed=True)
            self.preserved()
            fresh = history(self.db)
            b.require(fresh['last_state'] == current['state'],'paused JDBC state unrestored')
            self.original,self.before = current,fresh
            backup_history(self.db,self.directory,'paused-item0154.csv.gz',self.before)
            b.private_file(self.directory,'paused.json',b.encoded({'original':current,'history':fresh}))
            history_tools.sync_directory(self.directory)
            self.frozen = True
        self.preserved()
        writer(disabled=True)
        validate_item(item(),managed=True,state=self.original['state'])
        b.require(not TARGET.exists() and not TARGET.is_symlink(),'file/managed overlap refused')
        self.item_change_attempted = True
        request('DELETE','/items/'+ITEM)
        self.wait_item(None)

    def install_file(self):
        self.preserved()
        b.require(item() is None,'managed provider still present')
        file_identity(SOURCE,SOURCE_SHA256)
        body = SOURCE.read_bytes()
        b.require(sha256(body).hexdigest() == SOURCE_SHA256,'qualified source drift')
        pending = TARGET.parent/('.charging-'+os.urandom(8).hex()+'.pending')
        fd = os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        created = os.fstat(fd)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(body);stream.flush()
                os.fchmod(stream.fileno(),0o644);os.fsync(stream.fileno())
            os.link(pending,TARGET,follow_symlinks=False)
            self.owned_identity = created.st_dev,created.st_ino
            b.require(file_identity(TARGET,SOURCE_SHA256) == self.owned_identity,
                      'installed file ownership drift')
            history_tools.sync_directory(TARGET.parent)
        finally:
            pending_info = pending.lstat()
            b.require(stat.S_ISREG(pending_info.st_mode) and
                      (pending_info.st_dev,pending_info.st_ino) == (created.st_dev,created.st_ino),
                      'pending file ownership drift')
            pending.unlink()
            history_tools.sync_directory(TARGET.parent)

    def verify_file(self):
        b.require(file_identity(TARGET,SOURCE_SHA256) == self.owned_identity,'file ownership drift')
        self.wait_item(False)
        self.preserved()

    def withdraw_file(self):
        self.withdrawals += 1
        withdraw_owned(TARGET,self.directory,SOURCE_SHA256,self.owned_identity,self.withdrawals)
        self.owned_identity = None
        self.wait_item(None)

    def restore_managed(self):
        b.require(not TARGET.exists() and not TARGET.is_symlink() and item() is None,
                  'managed restore would overlap another provider')
        request('PUT','/items/'+ITEM,deepcopy(ORIGINAL_DTO))

    def verify_managed(self):
        self.wait_item(True)
        self.preserved()

    def recover_managed(self):
        if self.item_change_attempted:
            # A final enable timeout may follow an accepted resume. Re-pause
            # the exact known writer before any provider recovery operation.
            if not self.paused_writer():
                writer(disabled=False)
                request('POST','/rules/'+RULE+'/enable',False)
                wait_for(self.paused_writer)
            b.require(history(self.db,datetime.fromisoformat(self.before['cutoff'])) == self.before,
                      'original JDBC history prefix changed before rollback')
            current = item()
            if current is not None:
                validate_descriptor(current,managed=current.get('editable'))
                native_state = current.get('state')
                if native_state in ('ON','OFF'):
                    def caught_up():
                        observed = item()
                        validate_item(observed,managed=current['editable'],state=native_state)
                        b.require(history(self.db,datetime.fromisoformat(self.before['cutoff']))
                                  == self.before,'original JDBC history prefix changed during catch-up')
                        return history(self.db)['last_state'] == native_state
                    wait_for(caught_up)
                    # Preserve a genuine later update only after its native
                    # persisted receipt; never rebase the original prefix.
                    self.original = {**self.original,'state':native_state}
                else:
                    b.require(current.get('editable') is False and native_state in ('NULL','UNDEF'),
                              'unexpected recovery state')
                    b.require(history(self.db)['last_state'] == self.original['state'],
                              'unrestored provider has unexpected persisted state')
        if TARGET.exists() or TARGET.is_symlink():
            self.withdraw_file()  # Refuses unknown inode/source; never adopts a foreign file.
        if self.item_change_attempted and item() is None:
            self.restore_managed()
        self.wait_item(True)
        b.require(history(self.db,datetime.fromisoformat(self.before['cutoff'])) == self.before,
                  'original JDBC history prefix changed during rollback')
        self.recovered = self.safe_to_resume = True

    def resume_writer(self):
        if not self.pause_attempted:
            return
        b.require(self.safe_to_resume,'writer resume requires verified Item recovery')
        try:
            writer(disabled=False)
            return  # Accepted enable response may have been lost.
        except RuntimeError:
            writer(disabled=True)
        request('POST','/rules/'+RULE+'/enable',True)
        wait_for(lambda: self.writer_ready(disabled=False))

    def run(self):
        try:
            b.handoff(self)
            self.safe_to_resume = True
            self.resume_writer()
            self.preserved()
            b.private_file(self.directory,'file-proof.json',b.encoded({
                'at':datetime.now(timezone.utc),'item':ITEM,'jdbc_id':154,
                'source_sha256':SOURCE_SHA256,'original_history':self.before,
                'owned_identity':self.owned_identity,'withdrawals':self.withdrawals,
                'actual_managed_rollback':True,'writer_reenabled':True,
                'natural_writer_pending':True,'production_restart_qualified':False}))
            history_tools.sync_directory(self.directory)
        except BaseException:
            if self.directory is not None and not self.recovered:
                self.recover_managed()
            if self.safe_to_resume:
                self.resume_writer()
            raise


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-battery-charging-status-item.py --check|--apply')
    if argv == ['--apply'] and not RELEASE_READY:
        raise SystemExit('charging-status live cutover release gate closed')
    settings = history_tools.parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    db = history_tools.psycopg2.connect(**settings.connect_kwargs,connect_timeout=3)
    db.set_session(readonly=True,isolation_level='REPEATABLE READ')
    lock = None
    try:
        if argv == ['--check']:
            original,before,guard = preflight(db)
            print(json.dumps({'status':'preflight_passed','item':ITEM,'jdbc_id':154,
                'original_history_rows':before['count'],'state':original['state'],
                'source_sha256':SOURCE_SHA256,'protected':guard,'production_writes':0}))
        else:
            root = BACKUP_ROOT.lstat()
            b.require(stat.S_ISDIR(root.st_mode) and not BACKUP_ROOT.is_symlink()
                and root.st_uid == os.getuid() and stat.S_IMODE(root.st_mode) == 0o700,
                'private backup root unsafe')
            lock = os.open(BACKUP_ROOT/'charging-status-migration.lock',
                os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            b.require(stat.S_ISREG(os.fstat(lock).st_mode),'migration lock unsafe')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            ops = Operations(db)
            ops.run()
            print(json.dumps({'status':'file_provider_provisional','backup':str(ops.directory),
                'natural_writer_pending':True,'production_restart_qualified':False}))
    finally:
        if lock is not None:
            os.close(lock)
        db.close()


if __name__ == '__main__':
    main()
