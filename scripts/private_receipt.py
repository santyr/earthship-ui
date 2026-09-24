"""Exclusive, private JSON receipts for attended backup/recovery tools."""

import json
import os
from pathlib import Path
import re
import stat


def save_private_json(directory: Path, name: str, value: object) -> Path:
    """Create one mode-0600 receipt inside an owned mode-0700 directory.

    Refuse an existing name instead of overwriting an earlier recovery result.
    This deliberately has no dependency on a Codex session's temporary tools.
    """
    if not re.fullmatch(r'[a-z][a-z0-9-]*\.json', name):
        raise ValueError('unsupported private receipt name')
    body = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    root = Path(directory)
    dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(dir_fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError('private receipt directory is not owned mode-0700')
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(dir_fd)
        except BaseException:
            os.unlink(name, dir_fd=dir_fd)
            raise
    finally:
        os.close(dir_fd)
    return root / name
