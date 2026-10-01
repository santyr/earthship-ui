#!/usr/bin/env python3
"""Guarded exact Moon display handoff; no restart, commands or SQL writes.

--check is read-only. The live apply gate starts closed. All failures after
withdrawal attempt managed rollback; unknown target/provider drift refuses
overwrite and requires manual recovery. Never use this for another Item.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
for label, filename in [('transport', 'migrate-astro-icon-items.py'),
                        ('definition', 'qualify-moon-phase-provider.py')]:
    spec = importlib.util.spec_from_file_location('moon_' + label, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    globals()[label] = module

RELEASE_READY = False
SOURCE = definition.SOURCE
SOURCE_SHA256 = definition.SOURCE_SHA256
TARGET = Path('/etc/openhab/items/moon-phase-readings.items')
IDS = {'Moon_MoonPhaseName': 59, 'Moon_MoonIllumination': 41}
PHASES = frozenset({'NEW', 'WAXING_CRESCENT', 'FIRST_QUARTER', 'WAXING_GIBBOUS',
                   'FULL', 'WANING_GIBBOUS', 'THIRD_QUARTER', 'WANING_CRESCENT'})
CONTROLS = frozenset({'hex_southoutlet_cycle', 'hex_schneider_safety',
                     'hex_bms_soc_scale', 'hex_bms_comms_watchdog', 'hex_bms_ttd_smooth'})
MAX_HISTORY_BYTES = 32 * 1024 * 1024


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


@contextmanager
def apply_lock():
    """Process-owned lock; an existing empty lock file is not a running job."""
    root = transport.BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700, 'private lock root unsafe')
    fd = os.open(transport.BACKUP_ROOT / 'moon-readings.lock',
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600, 'private Moon lock unsafe')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('another Moon handoff owns the lock') from None
        yield
    finally:
        os.close(fd)


def same_state(name, left, right):
    if name == 'Moon_MoonPhaseName':
        return left == right and left in PHASES
    if name != 'Moon_MoonIllumination':
        return False
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and 0 <= a <= 1 and 0 <= b <= 1 and a == b
    except (InvalidOperation, TypeError, ValueError):
        return False


def attached():
    links = transport.oh.get('/links')
    return {name: [row for row in links if row.get('itemName') == name] for name in IDS}


def source_checked():
    source = SOURCE.read_bytes()
    require(sha256(source).hexdigest() == SOURCE_SHA256, 'Moon source changed')
    return source


def protected_proof():
    group = transport.oh.get('/items/Moon?metadata=.*')
    require(group.get('type') == 'Group', 'Moon parent is not a Group')
    group = {key: group.get(key) for key in ('name', 'type', 'groupType', 'function',
             'label', 'category', 'tags', 'groupNames', 'metadata', 'editable')}
    thing = transport.oh.get('/things/astro:moon:local')
    require(thing.get('UID') == 'astro:moon:local'
            and thing.get('statusInfo', {}).get('status') == 'ONLINE', 'Moon Thing is not online')
    require(set(reading['channel'] for reading in definition.READINGS.values())
            <= {channel['uid'] for channel in thing.get('channels', [])}, 'Moon channels missing')
    thing = {key: thing.get(key) for key in ('UID', 'thingTypeUID', 'bridgeUID', 'label',
             'configuration', 'channels', 'properties', 'location', 'editable')}
    rules = transport.oh.get('/rules')
    by_id = {rule['uid']: rule for rule in rules}
    require(CONTROLS <= by_id.keys(), 'protected rule inventory incomplete')
    require(all(by_id[uid].get('status', {}).get('status') in ('IDLE', 'RUNNING')
                for uid in CONTROLS), 'protected rules are not healthy')
    values = {'group': group, 'thing': thing, 'controls': {
        uid: {key: by_id[uid].get(key) for key in ('uid', 'name', 'description', 'tags',
             'triggers', 'conditions', 'actions', 'configuration', 'editable')}
        for uid in sorted(CONTROLS)}}
    # Raw private rule bodies/configurations stay in memory, never diagnostics.
    return sha256(json.dumps(values, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


class DigestWriter:
    def __init__(self, output=None):
        self.output = output
        self.digest = sha256()
        self.size = 0

    def write(self, value):
        body = value.encode() if isinstance(value, str) else value
        self.size += len(body)
        require(self.size <= MAX_HISTORY_BYTES, 'Moon history exceeds backup bound')
        self.digest.update(body)
        if self.output is not None:
            self.output.write(body)


def history(db, name, *, cutoff=None, output=None):
    """One bounded, consistent read-only snapshot; COPY streams without row lists."""
    require(name in IDS, 'unexpected Moon history target')
    with db:
        with db.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='20s'")
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (name,))
            require(cursor.fetchall() == [(IDS[name],)], 'Moon JDBC identity changed')
            table = transport.sql.Identifier('item' + str(IDS[name]).zfill(4))
            where = transport.sql.SQL('') if cutoff is None else transport.sql.SQL(' WHERE time<=%s')
            args = () if cutoff is None else (cutoff,)
            cursor.execute(transport.sql.SQL('SELECT count(*),max(time) FROM public.{}').format(table)
                           + where, args)
            count, maximum = cursor.fetchone()
            require(count > 0 and maximum is not None, 'Moon history is empty')
            command = transport.sql.SQL('COPY (SELECT time,value FROM public.{}').format(table)
            command += transport.sql.SQL(' WHERE time<={}').format(transport.sql.Literal(maximum))
            command += transport.sql.SQL(' ORDER BY time,value) TO STDOUT WITH CSV')
            writer = DigestWriter(output)
            cursor.copy_expert(command.as_string(db), writer)
            cursor.execute(transport.sql.SQL('SELECT value FROM public.{} WHERE time=%s ORDER BY value').format(table),
                           (maximum,))
            latest = cursor.fetchall()
            require(len(latest) == 1, 'Moon latest history is ambiguous')
    return {'id': IDS[name], 'count': count, 'cutoff': maximum,
            'sha256': writer.digest.hexdigest(), 'bytes': writer.size, 'latest': latest[0][0]}


def prefix_preserved(db, before):
    for name, expected in before.items():
        require(history(db, name, cutoff=expected['cutoff']) == expected,
                'Moon history prefix changed')


def ready(db, originals, before, *, managed):
    links = attached()
    for name in IDS:
        item = transport.item(name)
        if (not isinstance(item, dict) or not definition.exact_definition(item, name, managed=managed)
                or any(item.get(key) != originals[name].get(key)
                       for key in definition.FIELDS if key != 'category')
                or len(links[name]) != 1 or not definition.exact_link(links[name][0], name, managed=managed)):
            return False
        current = history(db, name)
        if not same_state(name, item.get('state'), current['latest']):
            return False
    prefix_preserved(db, before)
    return True


def absent():
    links = attached()
    return all(transport.item(name) is None and not links[name] for name in IDS)


def backup(db, originals, links, before, protection):
    root = transport.BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700, 'private backup root unsafe')
    directory = transport.BACKUP_ROOT / ('moon-readings-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    transport.private_file(directory, 'managed-and-prefix.json', json.dumps({
        'items': originals, 'links': links, 'history': before,
        'protected_sha256': protection, 'source_sha256': SOURCE_SHA256,
    }, default=str, sort_keys=True, allow_nan=False).encode())
    for name in IDS:
        path = directory / ('item' + str(IDS[name]).zfill(4) + '.csv')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            copied = history(db, name, cutoff=before[name]['cutoff'], output=output)
            output.flush()
            os.fsync(output.fileno())
        require(copied == before[name] and sha256(path.read_bytes()).hexdigest() == copied['sha256'],
                'private Moon history copy differs')
    # Private recovery preimages, never written into the running JSONDB.
    transport.private_file(directory, 'item-jsondb.json', transport.ITEM_DB.read_bytes())
    transport.private_file(directory, 'link-jsondb.json', transport.LINK_DB.read_bytes())
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return directory


def restore_managed(db, directory, originals, links, before):
    if TARGET.exists() or TARGET.is_symlink():
        require(not TARGET.is_symlink() and sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                'unknown Moon target; manual recovery required')
        body = TARGET.read_bytes()
        saved = directory / 'withdrawn.items'
        if saved.exists() or saved.is_symlink():
            require(not saved.is_symlink() and sha256(saved.read_bytes()).hexdigest() == SOURCE_SHA256,
                    'saved Moon rollback source changed')
        else:
            transport.private_file(directory, 'withdrawn.items', body)
        require(sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                'Moon target changed before withdrawal')
        TARGET.unlink()
        require(transport.wait_for(absent, 60), 'Moon file provider did not withdraw')
    for name in IDS:
        current = transport.item(name)
        if current is None:
            transport.request('PUT', '/items/' + name,
                {key: originals[name][key] for key in transport.FIELDS if key in originals[name]})
        else:
            require(definition.exact_definition(current, name, managed=True),
                    'unexpected Moon provider during rollback')
    found = attached()
    for name, rows in links.items():
        if not found[name]:
            channel = rows[0]['channelUID']
            transport.request('PUT', '/links/' + name + '/' + quote(channel, safe=''),
                              {key: rows[0][key] for key in ('itemName', 'channelUID', 'configuration')})
        else:
            require(len(found[name]) == 1 and definition.exact_link(found[name][0], name, managed=True),
                    'unexpected Moon link during rollback')
    require(transport.wait_for(lambda: ready(db, originals, before, managed=True), 90),
            'Moon managed rollback readback failed')


def install_source():
    """Atomic, exclusive watched-file creation: never expose a partial Item file."""
    source = source_checked()
    pending = TARGET.parent / ('.moon-readings-' + secrets.token_hex(8) + '.pending')
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(source)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        # Hard-link creation is atomic and refuses an existing target/symlink.
        os.link(pending, TARGET, follow_symlinks=False)
        directory_fd = os.open(TARGET.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if pending.exists() or pending.is_symlink():
            current = pending.lstat()
            require(stat.S_ISREG(current.st_mode) and current.st_uid == os.getuid()
                    and (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino)
                    and source.startswith(pending.read_bytes()),
                    'pending Moon source drift; manual cleanup required')
            pending.unlink()


def withdraw_managed(db, originals, links, before):
    require(ready(db, originals, before, managed=True), 'Moon managed pre-withdrawal drift')
    for name, rows in links.items():
        transport.request('DELETE', '/links/' + name + '/' + quote(rows[0]['channelUID'], safe=''))
    require(transport.wait_for(lambda: all(not rows for rows in attached().values()), 45),
            'Moon managed links did not withdraw')
    for name in IDS:
        transport.request('DELETE', '/items/' + name)
    require(transport.wait_for(absent, 45), 'Moon managed Items did not withdraw')


def apply(db, originals, links, before, protection):
    directory = backup(db, originals, links, before, protection)
    print('private_backup=' + str(directory), flush=True)
    changed = False
    try:
        require(protected_proof() == protection, 'protected configuration changed')
        source_checked()
        require(not TARGET.exists() and not TARGET.is_symlink(), 'Moon file target appeared')
        require(ready(db, originals, before, managed=True), 'Moon pre-transfer readback drift')
        changed = True
        withdraw_managed(db, originals, links, before)
        source_checked()
        install_source()
        require(sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256, 'installed Moon source changed')
        require(transport.wait_for(lambda: ready(db, originals, before, managed=False), 90),
                'Moon file provider/state/history did not recover')
        require(protected_proof() == protection, 'protected configuration changed after transfer')
        # The required attended round trip exercises the actual managed restore,
        # not just a successful file-provider handoff or mocked failure path.
        restore_managed(db, directory, originals, links, before)
        require(protected_proof() == protection, 'protected configuration changed during rollback')
        print('managed_rollback_exercised=true', flush=True)
        withdraw_managed(db, originals, links, before)
        install_source()
        require(transport.wait_for(lambda: ready(db, originals, before, managed=False), 90),
                'Moon return to file provider failed')
        require(protected_proof() == protection, 'protected configuration changed on file return')
    except BaseException:
        if changed:
            restore_managed(db, directory, originals, links, before)
            prefix_preserved(db, before)
            print('managed_rollback_verified=true', flush=True)
        raise
    return directory


def execute(argv):
    """Caller holds the apply lock, or has selected the read-only check path."""
    source_checked()
    require(not TARGET.exists() and not TARGET.is_symlink(), 'Moon target already exists')
    originals = {name: transport.item(name) for name in IDS}
    require(all(isinstance(row, dict) for row in originals.values()), 'Moon Item missing')
    links = attached()
    definition.preflight(list(originals.values()), [row for rows in links.values() for row in rows])
    protection = protected_proof()
    settings = transport.parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    db = transport.psycopg2.connect(**settings.connect_kwargs, connect_timeout=3)
    db.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
    try:
        before = {name: history(db, name) for name in IDS}
        require(ready(db, originals, before, managed=True), 'Moon current state/history drift')
        if argv == ['--check']:
            print(json.dumps({'status': 'preflight_passed', 'source_sha256': SOURCE_SHA256,
                              'jdbc_ids': IDS, 'history_rows': {name: value['count'] for name, value in before.items()}},
                             sort_keys=True), flush=True)
            return
        directory = apply(db, originals, links, before, protection)
        print(json.dumps({'status': 'file_provider_provisional', 'items': list(IDS),
                          'jdbc_ids': IDS, 'backup': str(directory),
                          'natural_astro_update_pending': True}, sort_keys=True), flush=True)
    finally:
        db.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-moon-phase-readings.py --check|--apply')
    if argv == ['--apply'] and not RELEASE_READY:
        raise SystemExit('Moon live handoff is not release-qualified')
    if argv == ['--check']:
        return execute(argv)
    with apply_lock():
        return execute(argv)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Moon handoff refused: ' + type(error).__name__) from None
