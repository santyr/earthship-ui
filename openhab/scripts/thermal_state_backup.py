"""Private, paired SQLite snapshot for the disabled thermal confirmation CLI.

The same advisory lock must cover every CLI state mutation and this snapshot.
This does not back up the PostgreSQL action journal or qualify off-host restore.
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


def _snapshot_locked(source, destination):
    """Snapshot both DBs under state_lock; destination must not yet exist.

    A failed snapshot leaves its private destination for attended inspection,
    not a silently reusable or automatically pruned recovery point.
    """
    source, destination = Path(source), Path(destination)
    _private_directory(source)
    _private_directory(destination.parent)
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
    manifest = {'version': 1, 'scope': 'thermal_sqlite_pair_only_no_postgresql_journal',
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


def snapshot_state(source, destination):
    """Take one idle-state pair snapshot, coordinated with CLI state use."""
    _private_directory(Path(source))
    with state_lock(source):
        return _snapshot_locked(source, destination)


def verify_snapshot(directory):
    """Verify a paired archive without opening live state or printing contents."""
    directory = Path(directory)
    _private_directory(directory)
    path = directory / 'manifest.json'
    _private_file(path)
    if path.stat().st_size > 4096:
        raise ValueError('paired snapshot manifest exceeds bound')
    manifest = json.loads(path.read_bytes())
    if (not isinstance(manifest, dict) or manifest.get('version') != 1
            or manifest.get('scope') != 'thermal_sqlite_pair_only_no_postgresql_journal'
            or not isinstance(manifest.get('files_sha256'), dict)
            or set(manifest['files_sha256']) != set(DATABASES)):
        raise ValueError('invalid paired snapshot manifest')
    for name in DATABASES:
        target = directory / name
        _private_file(target)
        expected = manifest['files_sha256'][name]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(char not in '0123456789abcdef' for char in expected)):
            raise ValueError('invalid paired snapshot digest')
        if _digest(target) != expected:
            raise ValueError('paired snapshot digest mismatch')
        with sqlite3.connect(f'file:{target}?mode=ro', uri=True) as check:
            if check.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('paired snapshot integrity check failed')
    return {'version': 1, 'scope': manifest['scope'], 'verified_files': len(DATABASES)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--snapshot', action='store_true')
    mode.add_argument('--verify', action='store_true')
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--snapshot-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.snapshot:
        if args.source_dir is None:
            parser.error('--snapshot requires --source-dir')
        snapshot_state(args.source_dir, args.snapshot_dir)
    result = verify_snapshot(args.snapshot_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
