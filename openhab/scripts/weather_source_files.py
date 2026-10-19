"""Neutral private file primitives for qualified local measurement evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import tempfile

MAX_BYTES = 128 * 1024


def _instant(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError('invalid capture timestamp')
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.utcoffset() is None:
        raise ValueError('capture timestamp must be aware')
    return at.astimezone(timezone.utc)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _directory(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or path.resolve(strict=True) != path):
        raise ValueError('capture directory must be owned private and non-symlink')
    return path


def _read(path, maximum=MAX_BYTES, *, source=False):
    path = Path(path)
    before = path.lstat()
    allowed = (0, os.getuid()) if source else (os.getuid(),)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid not in allowed
            or before.st_mode & 0o022 or before.st_size > maximum
            or path.resolve(strict=True) != path
            or (not source and (stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1))):
        raise ValueError('owned bounded immutable source required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
    if (len(raw) != before.st_size or len(raw) > maximum
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) !=
               (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError('source changed during read')
    return raw


def _write(root, name, raw, *, before_publish=None):
    if before_publish is not None and not callable(before_publish):raise ValueError('callable original retention guard required')
    root = _directory(root)
    target = root / name
    fd, temporary = tempfile.mkstemp(prefix='.temperature-origin-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        if before_publish is not None:before_publish()
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if _read(target, max(MAX_BYTES, len(raw))) != raw:
                raise ValueError('immutable origin collision')
        directory_fd = os.open(root, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)
    return target
