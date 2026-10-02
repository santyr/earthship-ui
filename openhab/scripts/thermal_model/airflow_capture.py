"""Explicit private storage of split-airflow candidates, not live publications.

No import-time I/O, default destination, pruning, accepted pointer or publisher.
A retained capture proves exact replay, not when a forecast reached an operator
or that held origin states describe future actions. Publication/outcome evidence
and household-source qualification remain separate release requirements.
"""
import gzip
from hashlib import sha256
import io
import json
import os
import re
import stat
from uuid import uuid4

from .airflow_artifact import canonical, utc, validate_artifact
from .airflow_forecast import replay_capture
from .forcing_capture import _private_directory

REFERENCE_SCHEMA = 'earthship-split-airflow-archive-reference/v1'
SCOPE = 'candidate_replay_not_publication_or_action_evidence'
MAX_DECODED_BYTES = 1_000_000
MAX_COMPRESSED_BYTES = 256_000
REFERENCE_KEYS = {'schema', 'scope', 'origin', 'capture_sha256', 'archive_sha256', 'relative_path'}


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def relative_path(origin, digest):
    at = utc(origin)
    if not _digest(digest):
        raise ValueError('full capture digest required')
    return at.strftime('%Y-%m/%Y%m%dT%H%M%SZ-') + digest + '.json.gz'


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > MAX_COMPRESSED_BYTES):
            raise ValueError('archive must be an owned private bounded single-link file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            content = stream.read(MAX_COMPRESSED_BYTES + 1)
        if len(content) > MAX_COMPRESSED_BYTES:
            raise ValueError('archive exceeds compressed bound')
        return content
    finally:
        os.close(fd)


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def archive_capture(directory, capture, *, runtime_root=None):
    """Validate/replay first, then atomically retain immutable canonical bytes."""
    root = _private_directory(directory)
    raw = canonical(capture)
    if len(raw) > MAX_DECODED_BYTES:
        raise ValueError('archive exceeds decoded bound')
    # Serialize once, then replay only that detached snapshot, not caller aliases.
    capture = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    output = replay_capture(capture, runtime_root=runtime_root)
    validate_artifact(capture['artifact'], runtime_root=runtime_root)
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError('archive exceeds compressed bound')
    relative = relative_path(output['origin'], capture['sha256'])
    target = root / relative
    try:
        target.parent.mkdir(mode=0o700)
    except FileExistsError:
        pass
    _private_directory(target.parent)
    # An earlier failed flush may have left the month present but not durable.
    _sync_directory(root)
    temporary = target.parent / ('.capture-' + uuid4().hex + '.tmp')
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
                raise ValueError('archive identity already has different content')
        _sync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
        # Persist link removal too: a restart must not leave a second link that
        # the strict reader would correctly refuse as ambiguous ownership.
        _sync_directory(target.parent)
    return {'schema': REFERENCE_SCHEMA, 'scope': SCOPE, 'origin': output['origin'],
            'capture_sha256': capture['sha256'], 'archive_sha256': sha256(compressed).hexdigest(),
            'relative_path': relative}


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError('duplicate archive JSON key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('nonfinite archive JSON value')


def read_capture(directory, reference, *, runtime_root=None):
    """Read bounded original bytes and require their exact code-bound replay."""
    root = _private_directory(directory)
    if (not isinstance(reference, dict) or set(reference) != REFERENCE_KEYS
            or reference['schema'] != REFERENCE_SCHEMA or reference['scope'] != SCOPE
            or not isinstance(reference['origin'], str)
            or reference['origin'] != utc(reference['origin']).isoformat()
            or not _digest(reference['capture_sha256']) or not _digest(reference['archive_sha256'])
            or reference['relative_path'] != relative_path(reference['origin'], reference['capture_sha256'])):
        raise ValueError('invalid closed archive reference')
    path = root / reference['relative_path']
    _private_directory(path.parent)
    compressed = _read(path)
    if sha256(compressed).hexdigest() != reference['archive_sha256']:
        raise ValueError('archive byte digest mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_DECODED_BYTES + 1)
    if len(raw) > MAX_DECODED_BYTES:
        raise ValueError('archive exceeds decoded bound')
    capture = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if (not isinstance(capture, dict) or capture.get('sha256') != reference['capture_sha256']
            or raw != canonical(capture)):
        raise ValueError('archive identity or canonical bytes mismatch')
    output = replay_capture(capture, runtime_root=runtime_root)
    validate_artifact(capture['artifact'], runtime_root=runtime_root)
    if output['origin'] != reference['origin']:
        raise ValueError('archive origin mismatch')
    return capture
