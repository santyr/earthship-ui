"""Bounded private archives of raw weather inputs, not corrected UI forecasts.

The daily worker must finish capture before assigning its prediction origin.
No backfill, forecast publication, model training or control lives here.
"""
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from uuid import uuid4


MAX_RAW_BYTES = 256 * 1024
MAX_COMPRESSED_BYTES = 64 * 1024
SCHEMA = 'earthship-forecast-input/v1'
REFERENCE_KEYS = {'version', 'sha256', 'capturedAt', 'path'}
PATH_PATTERN = re.compile(r'[0-9]{4}-[0-9]{2}/([0-9a-f]{64})\.json\.gz')


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


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > MAX_COMPRESSED_BYTES):
            raise ValueError('capture file must be owned private and bounded')
        compressed = stream.read(MAX_COMPRESSED_BYTES + 1)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError('compressed capture exceeds bound')
    from thermal_model.replay_budget import observe_source_bytes
    observe_source_bytes(path,compressed)
    return compressed


def _validate_record(record):
    if (not isinstance(record, dict)
            or set(record) != {'schema', 'capturedAt', 'requestUrl', 'snapshot'}
            or record['schema'] != SCHEMA):
        raise ValueError('invalid forecast capture schema')
    _instant(record['capturedAt'])
    url = record['requestUrl']
    if not isinstance(url, str) or len(url) > 4096:
        raise ValueError('invalid forecast request identity')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'api.open-meteo.com'
            or parsed.path != '/v1/forecast' or not parsed.query or parsed.fragment
            or any(ord(char) < 32 for char in url)):
        raise ValueError('invalid forecast request identity')
    snapshot = record['snapshot']
    if (not isinstance(snapshot, dict)
            or not isinstance(snapshot.get('daily'), dict)
            or not isinstance(snapshot.get('hourly'), dict)):
        raise ValueError('forecast capture requires raw daily and hourly data')
    # A finite archive is not evidence that every meteorological value is valid;
    # outcome/feature readers must still qualify dates, units and coverage.
    raw = _canonical(record)
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError('forecast capture exceeds decoded bound')
    return raw


def capture(directory, *, snapshot, request_url, captured_at):
    """Durably preserve the exact parsed fetch result; return its immutable ID."""
    root = _directory(directory)
    if not isinstance(captured_at, datetime) or captured_at.utcoffset() is None:
        raise ValueError('capture timestamp must be aware')
    at = captured_at.astimezone(timezone.utc)
    record = {'schema': SCHEMA, 'capturedAt': at.isoformat(),
              'requestUrl': request_url, 'snapshot': snapshot}
    raw = _validate_record(record)
    digest = sha256(raw).hexdigest()
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError('compressed capture exceeds bound')
    month = root / at.strftime('%Y-%m')
    month.mkdir(mode=0o700, exist_ok=True)
    _directory(month)
    root_fd = os.open(root, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    target = month / (digest + '.json.gz')
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
            if _read(target) != compressed:
                raise ValueError('immutable capture identity has different content')
        directory_fd = os.open(month, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return {'version': 1, 'sha256': digest, 'capturedAt': record['capturedAt'],
            'path': str(target.relative_to(root))}


def read_as_of(directory, reference, *, origin):
    """Read only the exact bound input identity available at the given origin."""
    root = _directory(directory)
    if (not isinstance(reference, dict) or set(reference) != REFERENCE_KEYS
            or type(reference['version']) is not int or reference['version'] != 1
            or not isinstance(reference['path'], str)):
        raise ValueError('invalid forecast capture reference')
    match = PATH_PATTERN.fullmatch(reference['path'])
    if match is None or match[1] != reference['sha256']:
        raise ValueError('invalid forecast capture identity')
    if not isinstance(origin, datetime) or origin.utcoffset() is None:
        raise ValueError('prediction origin must be aware')
    captured = _instant(reference['capturedAt'])
    if captured > origin.astimezone(timezone.utc):
        raise ValueError('weather capture unavailable at prediction origin')
    if reference['path'].split('/')[0] != captured.strftime('%Y-%m'):
        raise ValueError('capture month disagrees with timestamp')
    _directory(root / captured.strftime('%Y-%m'))
    compressed = _read(root / reference['path'])
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    if len(raw) > MAX_RAW_BYTES or sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('forecast capture digest or size mismatch')
    record = json.loads(raw)
    if _validate_record(record) != raw or record['capturedAt'] != reference['capturedAt']:
        raise ValueError('forecast capture reference mismatch')
    return record
