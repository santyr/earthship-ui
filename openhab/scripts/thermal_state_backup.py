"""Private thermal confirmation snapshot for the disabled collector.

The same advisory lock must cover every CLI state mutation and this snapshot.
Optional policy and route bytes can be captured with the SQLite pair. This
does not back up the PostgreSQL action journal or qualify off-host restore.
"""

import argparse
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat


DATABASES = ('confirmations.sqlite3', 'delivery.sqlite3')
CONFIG_FILES = ('policy.json', 'routes.json')
MAX_CONFIG_BYTES = 128 * 1024
SQLITE_SCOPE = 'thermal_sqlite_pair_only_no_postgresql_journal'
CONFIG_SCOPE = 'thermal_sqlite_pair_and_config_no_postgresql_journal'


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


def _snapshot_locked(source, destination, config_paths=None):
    """Snapshot both DBs under state_lock; destination must not yet exist.

    A failed snapshot leaves its private destination for attended inspection,
    not a silently reusable or automatically pruned recovery point.
    """
    source, destination = Path(source), Path(destination)
    _private_directory(source)
    _private_directory(destination.parent)
    if config_paths is not None:
        config_paths = tuple(_private_config_source(path) for path in config_paths)
    for name in DATABASES:
        _private_file(source / name)
    destination.mkdir(mode=0o700)
    files = {}
    for name in DATABASES:
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
    manifest = {'version': 2 if config_paths is not None else 1,
                'scope': CONFIG_SCOPE if config_paths is not None else SQLITE_SCOPE,
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


def snapshot_state(source, destination, *, policy=None, routes=None):
    """Take an idle-state snapshot, optionally binding exact config bytes."""
    if (policy is None) != (routes is None):
        raise ValueError('policy and routes must be captured together')
    _private_directory(Path(source))
    with state_lock(source):
        return _snapshot_locked(source, destination,
                                None if policy is None else (policy, routes))


def verify_snapshot(directory):
    """Verify a paired archive without opening live state or printing contents."""
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
    expected_files = DATABASES if type(version) is int and version == 1 and scope == SQLITE_SCOPE else (
        DATABASES + CONFIG_FILES if version == 2 and scope == CONFIG_SCOPE else ())
    if (not expected_files or not isinstance(manifest.get('files_sha256'), dict)
            or set(manifest['files_sha256']) != set(expected_files)):
        raise ValueError('invalid paired snapshot manifest')
    for name in expected_files:
        target = directory / name
        _private_file(target)
        expected = manifest['files_sha256'][name]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(char not in '0123456789abcdef' for char in expected)):
            raise ValueError('invalid paired snapshot digest')
        if _digest(target) != expected:
            raise ValueError('paired snapshot digest mismatch')
        if name in DATABASES:
            with sqlite3.connect(f'file:{target}?mode=ro', uri=True) as check:
                if check.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise ValueError('paired snapshot integrity check failed')
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
    args = parser.parse_args(argv)
    if args.snapshot:
        if args.source_dir is None:
            parser.error('--snapshot requires --source-dir')
        snapshot_state(args.source_dir, args.snapshot_dir,
                       policy=args.policy, routes=args.routes)
    elif args.policy is not None or args.routes is not None:
        parser.error('--verify reads config from the snapshot directory')
    result = verify_snapshot(args.snapshot_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
