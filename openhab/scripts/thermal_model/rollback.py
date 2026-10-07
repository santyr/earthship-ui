"""Retain and prepare verified shadow recovery files; never install or publish.

This does not retain an entire dependency environment or qualify a cold runtime.
Those gates remain necessary before a live release or recovery installation.
"""
import ctypes
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from uuid import uuid4

from .artifacts import _artifact_from_payload
from .forcing_capture import _canonical, _artifact_payload, _private_directory
from .graduation_policy import _sha, _utc
from .origin_capture import _source_bytes
from .policy_registration import _read_private
from .runtime_bundle import read_runtime_bundle, _write_private, _sync_directory
from .schema import validate_shadow_output

SCHEMA = 'earthship-thermal-rollback-snapshot/v1'
FIELDS = {'schema', 'captured_at', 'runtime_sha256', 'artifact_sha256',
          'output_sha256', 'snapshot_sha256'}
REASONS = {'baseline_regression', 'calibration_failure', 'sensor_epoch_changed',
           'artifact_corrupt', 'model_unstable', 'publication_invalid', 'operator_rollback'}


def _clock():
    return datetime.now(timezone.utc)


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def _copy_tree(source, destination):
    shutil.copytree(source, destination, symlinks=True)
    count = 0
    for current, directories, files in os.walk(destination, topdown=False, followlinks=False):
        _private_directory(Path(current))
        for name in directories:
            _private_directory(Path(current)/name)
        for name in files:
            count += 1
            if count > 600:
                raise ValueError('retained recovery tree exceeds bound')
            descriptor = os.open(Path(current)/name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        _sync_directory(Path(current))


def _rename_new(source, destination):
    """Linux atomic rename with no replacement of any existing target."""
    operation = ctypes.CDLL(None, use_errno=True).renameat2
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    if operation(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
        number = ctypes.get_errno()
        if number == 17:
            raise ValueError('recovery destination already exists')
        raise OSError(number, 'atomic recovery publication failed')


def _pair(artifact, output):
    validate_shadow_output(output)
    if output['confidence']['grade'] == 'unavailable':
        raise ValueError('available last-known-good shadow publication required')
    return _artifact_payload(artifact, output)


def _environment(runtime):
    executable = Path(sys.executable).resolve()
    raw = _source_bytes(executable, maximum=64000000)
    import numpy
    import scipy
    import psycopg2
    dependencies = {'numpy': numpy.__version__, 'scipy': scipy.__version__,
                    'psycopg2': psycopg2.__version__.split()[0]}
    if (sha256(raw).hexdigest() != runtime['interpreter_sha256'] or
            platform.python_version() != runtime['python_version'] or
            dependencies != runtime['dependencies']):
        raise ValueError('compatible retained interpreter and dependencies required')


def read_snapshot(directory):
    directory = _private_directory(Path(directory))
    if {entry.name for entry in directory.iterdir()} != {'manifest.json', 'artifact.json', 'last-shadow.json', 'bundles'}:
        raise ValueError('exact rollback snapshot membership required')
    record = _read_private(directory/'manifest.json')
    if not isinstance(record, dict) or set(record) != FIELDS or record['schema'] != SCHEMA:
        raise ValueError('closed rollback snapshot contract required')
    for name in ('runtime_sha256', 'artifact_sha256', 'output_sha256', 'snapshot_sha256'):
        _sha(record[name])
    if _digest({key: value for key, value in record.items() if key != 'snapshot_sha256'}) != record['snapshot_sha256']:
        raise ValueError('rollback snapshot manifest differs')
    if _utc(record['captured_at']) > _clock():
        raise ValueError('rollback snapshot capture is in the future')
    bundles = _private_directory(directory/'bundles')
    if {entry.name for entry in bundles.iterdir()} != {record['runtime_sha256']}:
        raise ValueError('exact retained rollback runtime required')
    bundle = read_runtime_bundle(bundles/record['runtime_sha256'])
    if _digest(bundle['runtime']) != record['runtime_sha256']:
        raise ValueError('rollback runtime binding differs')
    artifact = _read_private(directory/'artifact.json')
    output = _read_private(directory/'last-shadow.json')
    if _digest(artifact) != record['artifact_sha256'] or _digest(output) != record['output_sha256']:
        raise ValueError('rollback artifact or publication changed')
    _pair(_artifact_from_payload(artifact), output)
    if _utc(output['generatedAt']) > _utc(record['captured_at']):
        raise ValueError('last-known-good output was unavailable at snapshot capture')
    return record


def retain_snapshot(directory, *, runtime_bundle, artifact, output):
    """Retain immutable bytes from a previously accepted compatible shadow pair."""
    root = _private_directory(Path(directory))
    original = read_runtime_bundle(runtime_bundle)
    payload = _pair(artifact, output)
    runtime_digest = _digest(original['runtime'])
    temporary = root/('.thermal-snapshot-'+uuid4().hex)
    temporary.mkdir(mode=0o700)
    try:
        (temporary/'bundles').mkdir(mode=0o700)
        _copy_tree(Path(runtime_bundle), temporary/'bundles'/runtime_digest)
        _write_private(temporary/'artifact.json', _canonical(payload))
        _write_private(temporary/'last-shadow.json', _canonical(output))
        body = dict(schema=SCHEMA, captured_at=_clock().isoformat(), runtime_sha256=runtime_digest,
            artifact_sha256=_digest(payload), output_sha256=_digest(output))
        body['snapshot_sha256'] = _digest(body)
        _write_private(temporary/'manifest.json', _canonical(body))
        read_snapshot(temporary)
        if read_runtime_bundle(runtime_bundle) != original:
            raise ValueError('prior runtime changed while retaining recovery')
        _sync_directory(temporary)
        target = root/body['snapshot_sha256']
        _rename_new(temporary, target)
        _sync_directory(root)
        return target
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def prepare_restore(snapshot, destination, *, reason):
    """Prepare a new private recovery generation, never replacing live files.

    Preserved output is historical evidence. It must never be republished as a
    fresh prediction. The next shadow invocation must read qualified current inputs.
    """
    if reason not in REASONS:
        raise ValueError('explicit supported rollback reason required')
    snapshot = Path(snapshot)
    record = read_snapshot(snapshot)
    bundle_path = snapshot/'bundles'/record['runtime_sha256']
    bundle = read_runtime_bundle(bundle_path)
    _environment(bundle['runtime'])
    destination = Path(destination)
    if not destination.is_absolute() or destination.resolve() != destination:
        raise ValueError('absolute non-symlink private recovery target required')
    parent = _private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise ValueError('recovery destination already exists')
    temporary = parent/('.thermal-restore-'+uuid4().hex)
    temporary.mkdir(mode=0o700)
    try:
        _copy_tree(bundle_path/'sources', temporary/'runtime')
        (temporary/'models').mkdir(mode=0o700)
        _write_private(temporary/'models/accepted.json', _canonical(_read_private(snapshot/'artifact.json')))
        _write_private(temporary/'last-shadow.json', _canonical(_read_private(snapshot/'last-shadow.json')))
        receipt = dict(schema='earthship-thermal-rollback-preparation/v1',
            snapshot_sha256=record['snapshot_sha256'], runtime_sha256=record['runtime_sha256'],
            artifact_sha256=record['artifact_sha256'], reason=reason, prepared_at=_clock().isoformat(),
            installed=False, automatic_actuation=False, cold_runtime_qualified=False,
            dependency_environment_retained=False)
        _write_private(temporary/'rollback.json', _canonical(receipt))
        # The copied source closure must still match every declared retained byte.
        for name, expected in bundle['runtime']['source_manifest'].items():
            if sha256(_source_bytes(temporary/'runtime'/name, maximum=2000000)).hexdigest() != expected:
                raise ValueError('prepared recovery runtime differs')
        if read_snapshot(snapshot) != record:
            raise ValueError('rollback snapshot changed during preparation')
        _environment(bundle['runtime'])
        _sync_directory(temporary/'models'); _sync_directory(temporary)
        _rename_new(temporary, destination)
        _sync_directory(parent)
        return receipt
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
