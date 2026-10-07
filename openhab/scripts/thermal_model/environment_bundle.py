"""Stream an explicit dependency-file inventory into immutable private blobs.

Retaining declared bytes does not attest inventory completeness, relocation,
cold execution, restored journal compatibility or production readiness.
"""
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from uuid import uuid4

from .forcing_capture import _canonical, _private_directory
from .origin_capture import _object
from .runtime_bundle import _write_private, _sync_directory
from .rollback import _rename_new

SCHEMA = 'earthship-thermal-environment-files/v1'
FIELDS = {'schema', 'files', 'total_bytes', 'cold_environment_qualified', 'production_qualified', 'bundle_sha256'}
MAX_FILES = 20000
MAX_FILE_BYTES = 256000000
MAX_TOTAL_BYTES = 1000000000
MAX_MANIFEST_BYTES = 8000000
CHUNK = 262144


def _name(value):
    if not isinstance(value, str): raise ValueError('absolute dependency path required')
    path = PurePosixPath(value)
    if not path.is_absolute() or str(path) != value or '..' in path.parts or len(value.encode()) > 1024:
        raise ValueError('normalized bounded dependency path required')
    return value


def _file_pin(path, *, private=False, destination=None):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path: raise ValueError('resolved dependency source required')
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES or
            info.st_uid not in ((os.getuid(),) if private else (0, os.getuid())) or
            info.st_mode & 0o022 or private and (stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1)):
        raise ValueError('bounded safe dependency file required')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    output = None
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino): raise ValueError('dependency changed before read')
        if destination is not None:
            output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        digest = sha256(); size = 0
        while True:
            chunk = os.read(descriptor, CHUNK)
            if not chunk: break
            size += len(chunk)
            if size > MAX_FILE_BYTES: raise ValueError('dependency exceeds file bound')
            digest.update(chunk)
            if output is not None:
                view = memoryview(chunk)
                while view:
                    wrote = os.write(output, view)
                    if wrote <= 0: raise OSError('dependency copy stalled')
                    view = view[wrote:]
        after = os.fstat(descriptor)
        if (size != info.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('dependency changed during read')
        if output is not None: os.fsync(output)
        return dict(sha256=digest.hexdigest(), bytes=size)
    finally:
        os.close(descriptor)
        if output is not None: os.close(output)


def _copy_file(source, destination):
    return _file_pin(source, destination=destination)


def _read(directory, *, addressed):
    root = _private_directory(Path(directory))
    if {entry.name for entry in root.iterdir()} != {'manifest.json', 'blobs'}:
        raise ValueError('exact environment bundle membership required')
    manifest = root/'manifest.json'
    if manifest.stat().st_size > MAX_MANIFEST_BYTES: raise ValueError('environment manifest exceeds bound')
    _file_pin(manifest, private=True)
    def constant(_): raise ValueError('nonfinite environment manifest')
    descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        with os.fdopen(descriptor, 'rb', closefd=False) as stream: raw = stream.read(MAX_MANIFEST_BYTES+1)
    finally: os.close(descriptor)
    if len(raw) > MAX_MANIFEST_BYTES: raise ValueError('environment manifest exceeds bound')
    value = json.loads(raw, object_pairs_hook=_object, parse_constant=constant)
    if (not isinstance(value, dict) or set(value) != FIELDS or value['schema'] != SCHEMA or
            value['cold_environment_qualified'] is not False or value['production_qualified'] is not False):
        raise ValueError('closed dependency retention manifest required')
    digest = sha256(_canonical({key: item for key, item in value.items() if key != 'bundle_sha256'})).hexdigest()
    if value['bundle_sha256'] != digest or addressed and root.name != digest:
        raise ValueError('environment manifest identity differs')
    files = value['files']; total = 0; expected = set()
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES: raise ValueError('bounded dependency inventory required')
    for name, entry in files.items():
        _name(name)
        if (not isinstance(entry, dict) or set(entry) != {'sha256', 'bytes'} or
                type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= MAX_FILE_BYTES or
                not isinstance(entry['sha256'], str) or len(entry['sha256']) != 64 or
                any(character not in '0123456789abcdef' for character in entry['sha256'])):
            raise ValueError('exact dependency file identity required')
        total += entry['bytes']; expected.add(entry['sha256'])
    if total > MAX_TOTAL_BYTES or type(value['total_bytes']) is not int or value['total_bytes'] != total:
        raise ValueError('environment inventory size differs or exceeds bound')
    blobs = _private_directory(root/'blobs')
    if {entry.name for entry in blobs.iterdir()} != expected: raise ValueError('environment blobs missing or extra')
    verified = {}
    for name in expected: verified[name] = _file_pin(blobs/name, private=True)
    if any(verified[entry['sha256']] != entry for entry in files.values()):
        raise ValueError('retained dependency bytes differ')
    return value


def read_environment_bundle(directory):
    return _read(directory, addressed=True)


def capture_environment_files(directory, files):
    """Retain exactly specified resolved files; no traversal, execution or install."""
    root = _private_directory(Path(directory))
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES: raise ValueError('explicit bounded dependency map required')
    pins = {}; total = 0
    for name, source in files.items():
        _name(name); pin = _file_pin(Path(source)); total += pin['bytes']
        if total > MAX_TOTAL_BYTES: raise ValueError('environment inventory exceeds total bound')
        pins[name] = pin
    body = dict(schema=SCHEMA, files=pins, total_bytes=total, cold_environment_qualified=False, production_qualified=False)
    body['bundle_sha256'] = sha256(_canonical(body)).hexdigest()
    raw = _canonical(body)
    if len(raw) > MAX_MANIFEST_BYTES: raise ValueError('environment manifest exceeds bound')
    stage = root/('.environment-'+uuid4().hex); stage.mkdir(mode=0o700)
    try:
        (stage/'blobs').mkdir(mode=0o700)
        copied = set()
        for name, source in files.items():
            expected = pins[name]
            if expected['sha256'] not in copied:
                if _copy_file(Path(source), stage/'blobs'/expected['sha256']) != expected:
                    raise ValueError('dependency changed during capture')
                copied.add(expected['sha256'])
        for name, source in files.items():
            if _file_pin(Path(source)) != pins[name]: raise ValueError('dependency changed across capture')
        _write_private(stage/'manifest.json', raw)
        _read(stage, addressed=False)
        _sync_directory(stage/'blobs'); _sync_directory(stage)
        target = root/body['bundle_sha256']
        try: _rename_new(stage, target)
        except ValueError:
            if not target.exists() or read_environment_bundle(target) != body: raise
        _sync_directory(root)
        return target
    finally:
        if stage.exists(): shutil.rmtree(stage)
