"""Private thermal confirmation snapshot for the disabled collector.

The same advisory lock must cover every CLI state mutation and this snapshot.
Optional policy and route bytes can be captured with the SQLite pair. This
also supports an explicit stopped-writer PostgreSQL archive exporter. Scopes
remain distinct; verification does not qualify live or off-host recovery.
"""

import argparse
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess


DATABASES = ('confirmations.sqlite3', 'delivery.sqlite3')
PRIMAL_DATABASES = ('primal.sqlite3', 'primal-delivery.sqlite3')
CONFIG_FILES = ('policy.json', 'routes.json')
JOURNAL_FILE = 'journal.dump'
MAX_CONFIG_BYTES = 128 * 1024
MAX_JOURNAL_BYTES = 128 * 1024 * 1024
SQLITE_SCOPE = 'thermal_sqlite_pair_only_no_postgresql_journal'
CONFIG_SCOPE = 'thermal_sqlite_pair_and_config_no_postgresql_journal'
JOURNAL_SCOPE = 'thermal_stopped_writer_journal_sqlite_config_bundle'
PRIMAL_SQLITE_SCOPE = 'thermal_primal_sqlite_pair_only_no_postgresql_journal'
PRIMAL_CONFIG_SCOPE = 'thermal_primal_sqlite_pair_and_config_no_postgresql_journal'
PRIMAL_JOURNAL_SCOPE = 'thermal_primal_stopped_writer_journal_sqlite_config_bundle'
SNAPSHOT_LAYOUTS = {
    1: (SQLITE_SCOPE, DATABASES),
    2: (CONFIG_SCOPE, DATABASES + CONFIG_FILES),
    3: (JOURNAL_SCOPE, DATABASES + CONFIG_FILES + (JOURNAL_FILE,)),
    4: (PRIMAL_SQLITE_SCOPE, PRIMAL_DATABASES),
    5: (PRIMAL_CONFIG_SCOPE, PRIMAL_DATABASES + CONFIG_FILES),
    6: (PRIMAL_JOURNAL_SCOPE, PRIMAL_DATABASES + CONFIG_FILES + (JOURNAL_FILE,)),
}


def _transport(value):
    if value not in ('nip17', 'nip04'):
        raise ValueError('explicit nip17 or nip04 snapshot transport required')
    return value


def _primal_database(path, name):
    """Refuse unrecognized application state, even if its file digest matches."""
    _private_file(path)
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as check:
        expected = 1 if name == 'primal.sqlite3' else 3
        if check.execute('PRAGMA user_version').fetchone() != (expected,):
            raise ValueError('Primal snapshot database schema version differs')


def _primal_directory(path):
    _private_directory(path)
    if (not path.is_absolute() or path.resolve() != path
            or stat.S_IMODE(path.lstat().st_mode) != 0o700):
        raise ValueError('Primal snapshot requires owned mode-0700 non-symlink directories')


def _private_directory(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError('private state directory required')


def _private_file(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError('private regular state file required')


@contextmanager
def state_lock(directory):
    """Refuse overlapping CLI or backup work before opening state databases."""
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    _private_directory(directory)
    fd = os.open(directory / 'state.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError('private regular state lock required')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('thermal confirmation state is busy') from exc
        yield
    finally:
        os.close(fd)


def _digest(path):
    digest = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _private_config_source(path):
    path = Path(path)
    _private_directory(path.parent)
    _private_file(path)
    if not 0 < path.stat().st_size <= MAX_CONFIG_BYTES:
        raise ValueError('private config size outside bound')
    return path


def _copy_private_config(source, target):
    """Copy a private regular file without following a replaced source link."""
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(source_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or not 0 < info.st_size <= MAX_CONFIG_BYTES):
            raise ValueError('private config source invalid')
        copied = bytearray()
        while len(copied) <= MAX_CONFIG_BYTES:
            block = os.read(source_fd, min(65536, MAX_CONFIG_BYTES + 1 - len(copied)))
            if not block:
                break
            copied.extend(block)
        if not copied or len(copied) > MAX_CONFIG_BYTES or len(copied) != info.st_size:
            raise ValueError('private config changed or exceeds bound')
        os.lseek(source_fd, 0, os.SEEK_SET)
        if os.read(source_fd, len(copied) + 1) != copied:
            raise ValueError('private config changed during snapshot')
        target_fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(target_fd, 'wb') as stream:
            stream.write(copied)
            stream.flush()
            os.fsync(stream.fileno())
        return sha256(copied).hexdigest()
    finally:
        os.close(source_fd)


def _check_journal_archive(target):
    _private_file(target)
    if not 0 < target.stat().st_size <= MAX_JOURNAL_BYTES:
        raise ValueError('journal archive size outside bound')
    checked = subprocess.run(['pg_restore', '--list', str(target)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=30, check=False)
    if checked.returncode != 0 or len(checked.stdout) > 65536:
        raise ValueError('journal archive structure invalid')
    schemas = set()
    tables = set()
    for line in checked.stdout.splitlines():
        if not re.match(rb'^\d+;', line):
            continue
        schema = re.search(rb'\bSCHEMA - ([a-z_][a-z_0-9]*)\b', line)
        data = re.search(rb'\bTABLE DATA ([a-z_][a-z_0-9]*) ([a-z_][a-z_0-9]*)\b', line)
        if schema:
            schemas.add(schema.group(1))
        if data:
            tables.add((data.group(1), data.group(2)))
    expected = {(b'thermal_intel', table.encode()) for table in
                ('action_events', 'message_receipts', 'mode_events')}
    if schemas != {b'thermal_intel'} or tables != expected:
        raise ValueError('journal archive schema inventory invalid')


def _snapshot_locked(source, destination, config_paths=None, journal_exporter=None,
                     *, transport='nip17'):
    """Snapshot both DBs under state_lock; destination must not yet exist.

    A failed snapshot leaves its private destination for attended inspection,
    not a silently reusable or automatically pruned recovery point.
    """
    source, destination = Path(source), Path(destination)
    _transport(transport)
    _private_directory(source)
    _private_directory(destination.parent)
    databases = PRIMAL_DATABASES if transport == 'nip04' else DATABASES
    if transport == 'nip04':
        _primal_directory(source)
        _primal_directory(destination.parent)
    if config_paths is not None:
        config_paths = tuple(_private_config_source(path) for path in config_paths)
    for name in databases:
        _private_file(source / name)
        if transport == 'nip04':
            _primal_database(source / name, name)
    destination.mkdir(mode=0o700)
    files = {}
    for name in databases:
        original = source / name
        _private_file(original)
        target = destination / name
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with sqlite3.connect(f'file:{original}?mode=ro', uri=True) as live:
            with sqlite3.connect(target) as backup:
                live.backup(backup)
        _private_file(target)
        with sqlite3.connect(f'file:{target}?mode=ro', uri=True) as check:
            if check.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('snapshot integrity check failed')
        files[name] = _digest(target)
    if config_paths is not None:
        for name, original in zip(CONFIG_FILES, config_paths):
            files[name] = _copy_private_config(original, destination / name)
    if journal_exporter is not None:
        target = destination / JOURNAL_FILE
        journal_exporter(target)
        _check_journal_archive(target)
        files[JOURNAL_FILE] = _digest(target)
    version = 3 if journal_exporter is not None else 2 if config_paths is not None else 1
    if transport == 'nip04':
        version += 3
    manifest = {'version': version,
                'scope': SNAPSHOT_LAYOUTS[version][0],
                'files_sha256': files}
    path = destination / 'manifest.json'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return manifest


def snapshot_state(source, destination, *, policy=None, routes=None,
                   journal_exporter=None, transport='nip17'):
    """Take an idle-state snapshot; caller must stop external journal writers.

    A journal exporter must write one private pg_dump custom archive to its
    supplied new path. Holding this lock blocks collector CLIs sharing the
    selected state directory, but cannot stop independent journal writers.
    Primal is explicit opt-in; existing NIP-17 filenames/formats stay unchanged.
    """
    _transport(transport)
    if (policy is None) != (routes is None):
        raise ValueError('policy and routes must be captured together')
    if journal_exporter is not None and (policy is None or not callable(journal_exporter)):
        raise ValueError('journal snapshot requires both config files and an exporter')
    _private_directory(Path(source))
    with state_lock(source):
        return _snapshot_locked(source, destination,
                                None if policy is None else (policy, routes),
                                journal_exporter, transport=transport)


def verify_snapshot(directory, *, transport=None):
    """Verify a paired archive without opening live state or printing contents."""
    if transport is not None:
        _transport(transport)
    directory = Path(directory)
    _private_directory(directory)
    path = directory / 'manifest.json'
    _private_file(path)
    if path.stat().st_size > 4096:
        raise ValueError('paired snapshot manifest exceeds bound')
    manifest = json.loads(path.read_bytes())
    if not isinstance(manifest, dict) or set(manifest) != {'version', 'scope', 'files_sha256'}:
        raise ValueError('invalid paired snapshot manifest')
    version, scope = manifest.get('version'), manifest.get('scope')
    layout = SNAPSHOT_LAYOUTS.get(version) if type(version) is int else None
    expected_files = layout[1] if layout and scope == layout[0] else ()
    if (not expected_files or not isinstance(manifest.get('files_sha256'), dict)
            or set(manifest['files_sha256']) != set(expected_files)):
        raise ValueError('invalid paired snapshot manifest')
    observed_transport = 'nip04' if version >= 4 else 'nip17'
    if transport is not None and transport != observed_transport:
        raise ValueError('snapshot transport differs from selected transport')
    if observed_transport == 'nip04':
        _primal_directory(directory)
        if set(child.name for child in directory.iterdir()) != set(expected_files) | {'manifest.json'}:
            raise ValueError('unexpected Primal snapshot contents')
    for name in expected_files:
        target = directory / name
        _private_file(target)
        expected = manifest['files_sha256'][name]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(char not in '0123456789abcdef' for char in expected)):
            raise ValueError('invalid paired snapshot digest')
        if _digest(target) != expected:
            raise ValueError('paired snapshot digest mismatch')
        if name in DATABASES + PRIMAL_DATABASES:
            if name in PRIMAL_DATABASES:
                _primal_database(target, name)
            with sqlite3.connect(f'file:{target}?mode=ro', uri=True) as check:
                if check.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError('paired snapshot integrity check failed')
        elif name == JOURNAL_FILE:
            _check_journal_archive(target)
        elif not 0 < target.stat().st_size <= MAX_CONFIG_BYTES:
            raise ValueError('private config snapshot size outside bound')
    return {'version': version, 'scope': scope, 'verified_files': len(expected_files)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--snapshot', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--snapshot-dir', type=Path, required=True)
    parser.add_argument('--policy', type=Path, help='private reviewed policy file to include')
    parser.add_argument('--routes', type=Path, help='private signed-route snapshot to include')
    parser.add_argument('--transport', choices=('nip17', 'nip04'),
                        help='explicit snapshot transport; defaults to nip17 when creating')
    args = parser.parse_args(argv)
    if args.snapshot:
        if args.source_dir is None:
            parser.error('--snapshot requires --source-dir')
        snapshot_state(args.source_dir, args.snapshot_dir,
                       policy=args.policy, routes=args.routes,
                       transport=args.transport or 'nip17')
    elif args.policy is not None or args.routes is not None:
        parser.error('--verify reads config from the snapshot directory')
    result = verify_snapshot(args.snapshot_dir, transport=args.transport)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
