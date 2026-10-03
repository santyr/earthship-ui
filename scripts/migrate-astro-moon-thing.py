#!/usr/bin/env python3
"""Default-off, receipt-backed Moon Thing handoff; no controls or restart.

--check is GET/SELECT-only. --prepare additionally retains a private original
REST/CSV recovery preimage. --apply requires BOTH explicit release decisions,
then verifies file -> original managed rollback -> final file, including new
natural Moon/Sun updates and every original JDBC prefix at each boundary.
No Item/link mutation, synthetic state, SQL write or service operation exists.
"""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q = load('moon_migration_qualification', 'qualify-astro-moon-thing-provider.py')
consumer = load('moon_migration_consumers', 'preflight-astro-moon-consumers.py')
transport = load('moon_migration_jdbc_transport', 'migrate-astro-icon-items.py')
oh = q.runtime.oh
TARGET = q.TARGET
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
EVENT_LOG = Path('/var/log/openhab/events.log')
DELETE_PATH = '/things/' + q.UID + '?force=true'
# October 3 attended handoff completed; one-shot mutation authority is re-locked.
LIVE_RELEASE_READY = False
# Accepted October 3, 2026: exactly the qualified 39 binding metadata fields.
# This decision alone does not authorize the attended production handoff.
METADATA_DEVIATION_APPROVED = True


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      default=lambda at: at.isoformat()).encode()


def private_directory(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700 and path.resolve() == path,
            'private recovery directory unsafe')


def private_file(path, body):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def exclusive():
    private_directory(BACKUP_ROOT)
    fd = os.open(BACKUP_ROOT / 'astro-moon.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                'Moon handoff lock unsafe')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def database():
    settings = transport.parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    return transport.psycopg2.connect(**settings.connect_kwargs, connect_timeout=5)


class ArchiveDigest(q.HistoryDigest):
    def __init__(self, remaining, stream):
        super().__init__(remaining)
        self.stream = stream

    def write(self, value):
        body = value.encode() if isinstance(value, str) else value
        super().write(body)  # Enforce table/total bounds before retaining bytes.
        require(self.stream.write(body) == len(body), 'incomplete original CSV write')


def original_history(db, directory=None):
    with ExitStack() as stack:
        streams = {}
        def factory(name, remaining):
            require(name in q.HISTORY_IDS and name not in streams, 'CSV archive identity changed')
            path = directory / ('item' + str(q.HISTORY_IDS[name]).zfill(4) + '.csv')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            stream = stack.enter_context(os.fdopen(fd, 'wb'))
            streams[name] = stream
            return ArchiveDigest(remaining, stream)
        prefixes = q.history_prefixes(db, writer_factory=factory if directory else None)
        if directory:
            require(set(streams) == set(q.HISTORY_IDS), 'CSV recovery scope incomplete')
            for stream in streams.values():
                stream.flush()
                os.fsync(stream.fileno())
    return prefixes


def current_dependents(get=None):
    get = get or oh.get
    links = [row for row in get('/links')
             if row.get('channelUID', '').startswith(q.UID + ':')]
    require(len(links) == len({row['itemName'] for row in links}) == 28
            and {row['itemName'] for row in links} == set(q.HISTORY_IDS),
            'Moon linked scope changed')
    items = {name: get('/items/' + name + '?metadata=.*') for name in q.HISTORY_IDS}
    items['Moon'] = get('/items/Moon?metadata=.*')
    return sorted(links, key=lambda row: row['itemName']), q.dependent_definitions(items)


def withdrawal_dependents(dependents):
    """Exact unbound-core defaults for this fixed, non-overridden Moon scope.

    ChannelStateDescriptionProvider loses its fragment while the Thing is absent.
    DefaultStateDescriptionFragmentProvider then supplies the Item-type pattern,
    with false readOnly and empty options. Never discard the descriptor wholesale.
    """
    result = deepcopy(dependents)
    patterns = {'String': '%s', 'DateTime': '%1$tY-%1$tm-%1$td %1$tH:%1$tM:%1$tS',
                'Number': '%.0f'}
    for name, row in result.items():
        if name not in q.HISTORY_IDS:
            continue  # The unlinked Moon Group keeps its complete original contract.
        old = row.get('stateDescription') or {}
        require(set(old) == {'pattern', 'readOnly', 'options'} and old['readOnly'] is True
                and isinstance(old['pattern'], str) and isinstance(old['options'], list)
                and 'stateDescription' not in (row.get('metadata') or {})
                and '[' not in (row.get('label') or '') and ']' not in (row.get('label') or ''),
                'Moon withdrawal descriptor overrides outside qualified scope')
        kind = row.get('type')
        pattern = '%.0f %unit%' if kind in (
            'Number:Angle', 'Number:Length', 'Number:Time', 'Number:Dimensionless') else patterns.get(kind)
        require(pattern is not None, 'Moon withdrawal Item type outside qualified scope')
        row['stateDescription'] = {'pattern': pattern, 'readOnly': False, 'options': []}
    return result


def verify_unchanged(snapshot, *, withdrawal=False, get=None):
    links, items = current_dependents(get) if get is not None else current_dependents()
    expected = snapshot['dependents']
    if withdrawal:
        expected = withdrawal_dependents(expected)
        require(all(items[name].get('stateDescription', {}).get('readOnly') is False
                    for name in q.HISTORY_IDS if name in expected),
                'Moon withdrawal readOnly contract changed')
    require(links == snapshot['links'] and items == expected,
            'Moon dependent definition drift')


def capture(directory=None):
    source_ready()
    original, links, raw_items = q.preflight()
    require({row['itemName'] for row in links} == set(q.HISTORY_IDS), 'original history scope changed')
    guard = consumer.check()
    snapshot = {'thing': original, 'links': sorted(links, key=lambda row: row['itemName']),
                'items': raw_items, 'dependents': q.dependent_definitions(raw_items),
                'consumer_guard': guard}
    withdrawal_dependents(snapshot['dependents'])  # Refuse unsupported overrides before withdrawal.
    intended = q.binding_metadata_candidate(original, q.binding_channel_metadata())
    require(sha256(encoded(q.definition(intended))).hexdigest()
            == '3c4b60e6d22f3e8b452b1e2834d02d6cf5f1b12bcd3745563d330209adf90595',
            'qualified alternative descriptor changed')
    db = database()
    try:
        prefixes = original_history(db, directory)
        require(q.history_prefixes(db, before=prefixes) == prefixes, 'original JDBC prefix changed')
    finally:
        db.close()
    verify_unchanged(snapshot)
    again = oh.get('/things/' + q.UID)
    require(again.get('editable') is True
            and again.get('statusInfo') == {'status': 'ONLINE', 'statusDetail': 'NONE'}
            and q.definition(again) == q.definition(original),
            'original Moon provider changed during capture')
    require(consumer.check() == guard, 'consumer definitions changed during capture')
    source_ready()
    return {'snapshot': snapshot, 'history': prefixes, 'intended': intended,
            'source_sha256': q.SOURCE_SHA, 'captured_at': datetime.now(timezone.utc)}


def file_proof(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and info.st_size <= q.MAX_TABLE_HISTORY_BYTES,
            'private recovery file unsafe')
    digest = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return {'bytes': info.st_size, 'sha256': digest.hexdigest()}


def verify_backup(directory, verified):
    private_directory(directory)
    preimage = directory / 'preimage'
    private_directory(preimage)
    names = {'snapshot.json', 'source.things',
             *('item' + str(identity).zfill(4) + '.csv' for identity in q.HISTORY_IDS.values())}
    require({path.name for path in preimage.iterdir()} == names, 'recovery file scope changed')
    proofs = {name: file_proof(preimage / name) for name in sorted(names)}
    require((preimage / 'snapshot.json').read_bytes() == encoded(verified)
            and (preimage / 'source.things').read_bytes() == source_ready(),
            'original definition/source preimage changed')
    for name, row in verified['history'].items():
        proof = proofs['item' + str(row['id']).zfill(4) + '.csv']
        require(proof == {'bytes': row['bytes'], 'sha256': row['sha256']},
                'original CSV prefix preimage changed')
    manifest = {'version': 1, 'uid': q.UID, 'files': proofs}
    path = directory / 'manifest.json'
    if path.exists() or path.is_symlink():
        file_proof(path)
        require(path.read_bytes() == encoded(manifest), 'private recovery manifest changed')
    return manifest


def prepare():
    private_directory(BACKUP_ROOT)
    directory = Path(tempfile.mkdtemp(prefix='astro-moon-', dir=BACKUP_ROOT))
    try:
        preimage = directory / 'preimage'
        preimage.mkdir(mode=0o700)
        verified = capture(preimage)
        private_file(preimage / 'snapshot.json', encoded(verified))
        private_file(preimage / 'source.things', source_ready())
        manifest = verify_backup(directory, verified)
        private_file(directory / 'manifest.json', encoded(manifest))
        sync_directory(preimage)
        sync_directory(directory)
        sync_directory(BACKUP_ROOT)
        require(verify_backup(directory, verified) == manifest, 'durable backup differs')
    except BaseException:
        # Only this just-created incomplete recovery point, before ANY write
        # to production. Never prune an older/completed backup or lock file.
        shutil.rmtree(directory)
        raise
    return directory, verified


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(method, path, original, body=None):
    require(LIVE_RELEASE_READY and METADATA_DEVIATION_APPROVED, 'Moon live release gates are off')
    require(original.get('editable') is True and original.get('thingTypeUID') == 'astro:moon',
            'managed recovery preimage invalid')
    full = q.managed_thing(original)
    initial = {key: value for key, value in full.items() if key != 'channels'}
    allowed = (method == 'DELETE' and path == DELETE_PATH and body is None
               or method == 'POST' and path == '/things' and body == initial
               or method == 'PUT' and path == '/things/' + q.UID and body == full)
    require(allowed, 'Moon REST mutation outside exact recovery scope')
    headers = {'Authorization': 'Bearer ' + oh.token(), 'Content-Type': 'application/json'}
    opener = build_opener(ProxyHandler({}), NoRedirects())
    with opener.open(Request(oh.BASE + path, method=method,
                            data=encoded(body) if body is not None else None,
                            headers=headers), timeout=15) as response:
        require(response.status in (200, 201, 202, 204), 'Moon REST mutation refused')


def get_thing():
    try:
        return oh.get('/things/' + q.UID)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def wait(predicate, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(2)
    raise RuntimeError('Moon bounded qualification timeout')


def source_ready():
    require(not q.SOURCE.is_symlink(), 'Moon declaration symlink')
    body = q.SOURCE.read_bytes()
    require(sha256(body).hexdigest() == q.SOURCE_SHA,
            'Moon declaration changed')
    return body


def install_source(on_install=None):
    body = source_ready()
    fd, name = tempfile.mkstemp(prefix='.astro-moon-', suffix='.tmp', dir=TARGET.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            os.fchmod(stream.fileno(), 0o644)
            stream.flush()
            os.fsync(stream.fileno())
        info = temporary.lstat()
        identity = (info.st_dev, info.st_ino)
        os.link(temporary, TARGET, follow_symlinks=False)  # Exclusive, never overwrites.
        if on_install is not None:
            on_install(identity)  # Retain ownership even if subsequent fsync fails.
        sync_directory(TARGET.parent)
        return identity
    finally:
        temporary.unlink(missing_ok=True)


def remove_owned_file(identity):
    info = TARGET.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and identity == (info.st_dev, info.st_ino)
            and sha256(TARGET.read_bytes()).hexdigest() == q.SOURCE_SHA,
            'Moon file drift; manual recovery required')
    TARGET.unlink()  # Exact owned bytes remain in canonical Git/private preimage.
    sync_directory(TARGET.parent)


def provider_ready(verified, file_owned, getter=None):
    current = (getter or get_thing)()
    expected = verified['intended'] if file_owned else verified['snapshot']['thing']
    return (isinstance(current, dict) and current.get('editable') is (not file_owned)
            and current.get('statusInfo') == {'status': 'ONLINE', 'statusDetail': 'NONE'}
            and q.definition(current) == q.definition(expected))


def history_unchanged(verified, factory=None):
    db = (factory or database)()
    try:
        require(q.history_prefixes(db, before=verified['history']) == verified['history'],
                'Moon original history changed; manual recovery required')
    finally:
        db.close()


def guard_unchanged(verified):
    source_ready()
    require(consumer.check() == verified['snapshot']['consumer_guard'],
            'consumer or shared Sun definition drift')


def pumps_off():
    for name in ('SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power'):
        require(oh.get('/items/' + name).get('state') == 'OFF',
                'both greywater outputs must report OFF for planned handoff')


def natural_updates_after(after):
    # Bounded read, no whole log export. Old/held/unattributed states never pass.
    with EVENT_LOG.open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        stream.seek(max(0, size - 4 * 1024**2))
        log = stream.read(4 * 1024**2).decode(errors='replace')
    return native_events(log, after)


def native_events(log, after):
    now = datetime.now(timezone.utc)
    return (q.native_update_after(log, after, now)
            and q.native_update_after(log, after, now, item='Sun_Position_Elevation',
                                      channel='astro:sun:local:position#elevation'))


def qualify_phase(directory, verified, file_owned, after, name, operations=None):
    ops = operations or ProductionOperations()
    ops.wait(lambda: ops.provider_ready(verified, file_owned))
    ops.verify_unchanged(verified['snapshot'])
    ops.guard_unchanged(verified)
    ops.wait(lambda: ops.natural_updates_after(after), seconds=360)
    require(ops.provider_ready(verified, file_owned), 'Moon provider changed after native witness')
    ops.verify_unchanged(verified['snapshot'])
    ops.guard_unchanged(verified)
    ops.history_unchanged(verified)
    private_file(directory / (name + '.json'), encoded({'status': 'verified', 'file_owned': file_owned,
                 'native_moon_and_sun_after': after, 'history_prefixes_unchanged': 28}))
    sync_directory(directory)


def rollback(directory, verified, identity, operations=None):
    ops = operations or ProductionOperations()
    original = verified['snapshot']['thing']
    if ops.target_exists():
        current = ops.get_thing()
        require(current is None or (current.get('editable') is False
                and q.definition(current) == q.definition(verified['intended'])),
                'unexpected provider during rollback; manual recovery required')
        ops.remove_owned_file(identity)
        ops.wait(lambda: ops.get_thing() is None, seconds=60)
    current = ops.get_thing()
    if current is None:
        ops.verify_unchanged(verified['snapshot'], withdrawal=True)
        full = q.managed_thing(original)
        ops.request('POST', '/things', original, {key: value for key, value in full.items() if key != 'channels'})
        # Acknowledge loss/races conservatively: never PUT over an unexpected
        # managed definition. New factory metadata must match the tested one.
        ops.wait(lambda: ops.get_thing() is not None, seconds=30)
        current = ops.get_thing()
        require(current.get('editable') is True
                and q.definition(current) in (q.definition(original), q.definition(verified['intended'])),
                'managed recreation descriptor drift; manual recovery required')
        ops.request('PUT', '/things/' + q.UID, original, full)
    else:
        require(current.get('editable') is True and q.definition(current) == q.definition(original),
                'unexpected managed provider; manual recovery required')
    ops.wait(lambda: ops.provider_ready(verified, False))


class ProductionOperations:
    """Production mutations always retain their independent live gate checks."""
    def target_exists(self): return TARGET.exists() or TARGET.is_symlink()
    def get_thing(self): return get_thing()
    def wait(self, *a, **k): return wait(*a, **k)
    def request(self, *a, **k): return request(*a, **k)
    def install_source(self, *a, **k): return install_source(*a, **k)
    def remove_owned_file(self, *a, **k): return remove_owned_file(*a, **k)
    def provider_ready(self, *a, **k): return provider_ready(*a, **k)
    def verify_unchanged(self, *a, **k): return verify_unchanged(*a, **k)
    def guard_unchanged(self, *a, **k): return guard_unchanged(*a, **k)
    def history_unchanged(self, *a, **k): return history_unchanged(*a, **k)
    def pumps_off(self): return pumps_off()
    def natural_updates_after(self, *a, **k): return natural_updates_after(*a, **k)
    def qualify_phase(self, *a, **k): return qualify_phase(*a, **k)
    def rollback(self, *a, **k): return rollback(*a, **k)


def apply(directory, verified):
    require(LIVE_RELEASE_READY and METADATA_DEVIATION_APPROVED, 'Moon live release gates are off')
    verify_backup(directory, verified)
    return round_trip(directory, verified, ProductionOperations())


def round_trip(directory, verified, ops):
    # No default backend: a fixture must supply its contained capabilities.
    # Production REST remains gated inside request as well as apply itself.
    ownership, changed = {'identity': None}, False
    try:
        for index in (1, 2):
            require(not ops.target_exists() and ops.provider_ready(verified, False),
                    'managed handoff preimage drift')
            ops.verify_unchanged(verified['snapshot'])
            ops.guard_unchanged(verified)
            ops.history_unchanged(verified)
            ops.pumps_off()
            changed = True  # Lost DELETE response may still have removed it.
            ops.request('DELETE', DELETE_PATH, verified['snapshot']['thing'])
            ops.wait(lambda: ops.get_thing() is None, seconds=60)
            ops.verify_unchanged(verified['snapshot'], withdrawal=True)
            ops.guard_unchanged(verified)
            after = datetime.now(timezone.utc)
            ops.install_source(lambda identity: ownership.update(identity=identity))
            ops.qualify_phase(directory, verified, True, after, 'file-' + str(index))
            if index == 1:
                ops.pumps_off()
                after = datetime.now(timezone.utc)
                ops.rollback(directory, verified, ownership['identity'])
                ownership['identity'] = None
                ops.qualify_phase(directory, verified, False, after, 'managed-rollback')
        return {'status': 'provisional_file_provider_verified', 'private_backup': str(directory),
                'original_history_items': 28, 'managed_rollback_exercised': True,
                'production_restart': False, 'production_restart_recovery': 'not_tested'}
    except BaseException:
        if changed:
            after = datetime.now(timezone.utc)
            ops.rollback(directory, verified, ownership['identity'])
            ops.qualify_phase(directory, verified, False, after, 'failure-recovery')
        raise


def command(args):
    require(args in (['--check'], ['--prepare'], ['--apply']), 'unsupported Moon handoff interface')
    if args == ['--apply']:
        require(LIVE_RELEASE_READY and METADATA_DEVIATION_APPROVED, 'Moon live release gates are off')
    if args == ['--check']:
        verified = capture()
        return {'status': 'read_only_preflight_passed', 'original_history_items': len(verified['history']),
                'original_rows': sum(row['count'] for row in verified['history'].values()),
                'original_bytes': sum(row['bytes'] for row in verified['history'].values()),
                'original_prefix_sha256': sha256(encoded(verified['history'])).hexdigest(),
                'production_writes': 0, 'live_release_ready': LIVE_RELEASE_READY,
                'metadata_deviation_approved': METADATA_DEVIATION_APPROVED}
    with exclusive():
        directory, verified = prepare()
        if args == ['--prepare']:
            return {'status': 'original_private_preimage_verified', 'private_backup': str(directory),
                    'original_history_items': len(verified['history']), 'production_writes': 0,
                    'original_rows': sum(row['count'] for row in verified['history'].values()),
                    'original_bytes': sum(row['bytes'] for row in verified['history'].values()),
                    'live_release_ready': LIVE_RELEASE_READY,
                    'metadata_deviation_approved': METADATA_DEVIATION_APPROVED}
        print('private_backup=' + str(directory), flush=True)
        return apply(directory, verified)


if __name__ == '__main__':
    try:
        print(json.dumps(command(sys.argv[1:]), sort_keys=True))
    except (Exception, KeyboardInterrupt):
        raise SystemExit('Moon handoff refused; inspect retained private recovery point; private diagnostics withheld') from None
