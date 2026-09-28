"""Private, immutable capture of inputs actually used by one shadow publication.

No directory is created or state changed unless the caller explicitly supplies
an existing, private capture root. This is observational replay evidence only.
"""
from dataclasses import asdict
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


def _artifact_payload(artifact, output):
    from .artifacts import validate_artifact

    def published_second(value, *, output_field=False):
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None or (output_field and parsed.microsecond):
            raise ValueError('published model timestamp must be aware and whole-second')
        return parsed.astimezone(timezone.utc).replace(microsecond=0)

    validate_artifact(artifact, require_eligible=True)
    model = output.get('model')
    if (not isinstance(model, dict) or any(type(model.get(key)) is not str
            for key in ('codeRevision', 'createdAt', 'trainedThrough'))):
        raise ValueError('captured artifact does not match published model')
    if (model['codeRevision'] != artifact.code_revision
            or published_second(model['createdAt'], output_field=True) !=
               published_second(artifact.created_at)
            or published_second(model['trainedThrough'], output_field=True) !=
               published_second(artifact.trained_through)
            or datetime.fromisoformat(artifact.created_at).astimezone(timezone.utc) >
               datetime.fromisoformat(output['generatedAt']).astimezone(timezone.utc)):
        raise ValueError('captured artifact does not match published model')
    return asdict(artifact)


def capture_shadow_inputs(directory, *, output, snapshot, rows, current,
                          inputs_available_at, published_at, artifact=None):
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
    if artifact is not None:
        values['artifact'] = _artifact_payload(artifact, output)
    digests = {name: sha256(_canonical(value)).hexdigest() for name, value in values.items()}
    version = 2 if artifact is not None else 1
    record = {'schema': f'earthship-thermal-shadow-forcing-capture/v{version}',
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
    if not isinstance(record, dict):
        raise ValueError('invalid forcing-capture schema')
    base = {'output', 'raw_forecast', 'forecast_rows', 'current'}
    version = record.get('schema')
    if version == 'earthship-thermal-shadow-forcing-capture/v2':
        values = base | {'artifact'}
    elif version == 'earthship-thermal-shadow-forcing-capture/v1':
        values = base
    else:
        raise ValueError('invalid forcing-capture schema')
    if set(record) != values | {
            'schema', 'decision_at', 'inputs_available_at', 'published_at', 'sha256'}:
        raise ValueError('invalid forcing-capture schema')
    if not isinstance(record['sha256'], dict) or set(record['sha256']) != values:
        raise ValueError('invalid forcing-capture digest set')
    if not (datetime.fromisoformat(record['inputs_available_at']) <=
            datetime.fromisoformat(record['decision_at']) <=
            datetime.fromisoformat(record['published_at'])):
        raise ValueError('invalid forcing-capture chronology')
    for name in values:
        if sha256(_canonical(record[name])).hexdigest() != record['sha256'].get(name):
            raise ValueError('forcing-capture digest mismatch')
    if record['decision_at'] != _iso(datetime.fromisoformat(record['output']['generatedAt'])):
        raise ValueError('forcing-capture output timestamp mismatch')
    if 'artifact' in values:
        from .artifacts import _artifact_from_payload
        _artifact_payload(_artifact_from_payload(record['artifact']), record['output'])
    return record
