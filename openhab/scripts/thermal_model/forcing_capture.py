"""Private, immutable capture of inputs actually used by one shadow publication.

No directory is created or state changed unless the caller explicitly supplies
an existing, private capture root. This is observational replay evidence only.
"""
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from uuid import uuid4


def _iso(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('capture timestamps must be aware')
    return value.astimezone(timezone.utc).isoformat()


def _json_default(value):
    if isinstance(value, datetime):
        return _iso(value)
    raise TypeError('unsupported forcing-capture value')


def _canonical(value):
    return json.dumps(value, default=_json_default, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def _private_directory(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o700 or path.resolve(strict=True) != path):
        raise ValueError('capture directory must be owned mode-0700 and non-symlink')
    return path


def capture_shadow_inputs(directory, *, output, snapshot, rows, current,
                          inputs_available_at, published_at):
    """Atomically preserve one successful published output and its exact inputs."""
    root = _private_directory(directory)
    issued = datetime.fromisoformat(output['generatedAt'])
    issued_utc = datetime.fromisoformat(_iso(issued))
    available = datetime.fromisoformat(_iso(inputs_available_at))
    published = datetime.fromisoformat(_iso(published_at))
    if not available <= issued_utc <= published:
        raise ValueError('forcing inputs were not available by decision time')
    if output.get('status') != 'shadow' or output.get('confidence', {}).get('grade') == 'unavailable':
        raise ValueError('only successfully available shadow output can be captured')
    values = {'output': output, 'raw_forecast': snapshot,
              'forecast_rows': rows, 'current': current}
    digests = {name: sha256(_canonical(value)).hexdigest() for name, value in values.items()}
    record = {'schema': 'earthship-thermal-shadow-forcing-capture/v1',
              'decision_at': _iso(issued), 'inputs_available_at': _iso(available),
              'published_at': _iso(published), 'sha256': digests,
              **values}
    raw = _canonical(record)
    if len(raw) > 1_000_000:
        raise ValueError('forcing capture exceeds one-megabyte bound')
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > 256_000:
        raise ValueError('compressed forcing capture exceeds bound')
    month = root / issued_utc.strftime('%Y-%m')
    try:
        month.mkdir(mode=0o700)
    except FileExistsError:
        pass
    _private_directory(month)
    name = issued_utc.strftime('%Y%m%dT%H%M%SZ') + '-' + digests['output'][:16] + '.json.gz'
    target = month / name
    temporary = month / ('.capture-' + uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(compressed)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            existing = target.lstat()
            if (not stat.S_ISREG(existing.st_mode) or existing.st_uid != os.getuid()
                    or stat.S_IMODE(existing.st_mode) != 0o600):
                raise ValueError('capture identity is not an owned private file')
            if target.read_bytes() != compressed:
                raise ValueError('capture identity already has different content')
        directory_fd = os.open(month, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def verify_capture(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size > 256_000 or
            info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
        raise ValueError('forcing capture must be an owned bounded private file')
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('forcing capture exceeds decoded bound')
    record = json.loads(raw)
    if (not isinstance(record, dict) or set(record) != {
            'schema', 'decision_at', 'inputs_available_at', 'published_at', 'sha256',
            'output', 'raw_forecast', 'forecast_rows', 'current'} or
            record['schema'] != 'earthship-thermal-shadow-forcing-capture/v1'):
        raise ValueError('invalid forcing-capture schema')
    if (not isinstance(record['sha256'], dict) or
            set(record['sha256']) != {'output', 'raw_forecast', 'forecast_rows', 'current'}):
        raise ValueError('invalid forcing-capture digest set')
    if not (datetime.fromisoformat(record['inputs_available_at']) <=
            datetime.fromisoformat(record['decision_at']) <=
            datetime.fromisoformat(record['published_at'])):
        raise ValueError('invalid forcing-capture chronology')
    for name in ('output', 'raw_forecast', 'forecast_rows', 'current'):
        if sha256(_canonical(record[name])).hexdigest() != record['sha256'].get(name):
            raise ValueError('forcing-capture digest mismatch')
    if record['decision_at'] != _iso(datetime.fromisoformat(record['output']['generatedAt'])):
        raise ValueError('forcing-capture output timestamp mismatch')
    return record
