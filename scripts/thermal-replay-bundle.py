#!/usr/bin/env python3
"""Create or verify a private, source-bound thermal replay recovery bundle.

This copies evidence only. It does not train, publish, restore, or authorize
thermal actions. Legacy bundles bind the included runtime to artifact training;
an explicit v2 publication pin preserves a separately qualified runtime without
relabeling training or claiming every capture replays under that runtime.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from uuid import uuid4


SCHEMA = 'earthship-thermal-replay-evidence/v1'
PUBLICATION_SCHEMA = 'earthship-thermal-replay-evidence/v2'
MAX_FILE = 2_000_000
MAX_FILES = 10_000
MAX_TOTAL = 100_000_000
MODEL_NAMES = ('accepted.json', 'candidate.json', 'previous.json', 'backtest-report.json')
LEGACY_RUNTIME_PATHS = (
    'thermal_intel.py', 'forecast_intel.py', 'thermal_temperature_runtime.py',
    'hourly_temperature_runtime.py', 'daily_temperature_runtime.py',
    'weather_temperature_reader.py', 'weather_temperature_history.py',
    'weather_temperature_evidence.py', 'weather_temperature_config.py',
    'thermal_model/temperature_history.py', 'thermal_model/__init__.py',
    'thermal_model/actions.py', 'thermal_model/artifacts.py', 'thermal_model/behavior.py',
    'thermal_model/dataset.py', 'thermal_model/dynamics.py', 'thermal_model/evaluation.py',
    'thermal_model/journal.py', 'thermal_model/pipeline.py', 'thermal_model/schema.py',
    'thermal_model/solar.py',
)
RADIATION_RUNTIME_PATHS = (
    *LEGACY_RUNTIME_PATHS[:3], 'thermal_radiation_runtime.py',
    'weather_radiation_reader.py', 'weather_radiation_history.py',
    'weather_radiation_evidence.py', 'weather_radiation_config.py',
    *LEGACY_RUNTIME_PATHS[3:],
)
CAPTURE_NAME = re.compile(r'^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}\.json\.gz$')


def _private_directory(path):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or path.resolve(strict=True) != path):
        raise ValueError(f'private mode-0700 directory required: {path}')
    return path


def _read(path, *, private=False, max_size=MAX_FILE):
    path = Path(path)
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_size > max_size or info.st_nlink != 1
            or (private and stat.S_IMODE(info.st_mode) != 0o600)):
        raise ValueError(f'unexpected source file: {path}')
    data = path.read_bytes()
    if len(data) != info.st_size:
        raise ValueError(f'source changed while reading: {path}')
    return data


def _paths(source):
    tree = ast.parse(source.decode('utf-8'))
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'RUNTIME_REVISION_PATHS'
                      for target in node.targets)]
    if len(values) != 1:
        raise ValueError('exactly one runtime revision path list required')
    paths = ast.literal_eval(values[0])
    if (not isinstance(paths, tuple) or paths not in (LEGACY_RUNTIME_PATHS, RADIATION_RUNTIME_PATHS)
            or len(set(paths)) != len(paths)
            or any(not isinstance(name, str) or not _safe_name(name) for name in paths)
            or paths[0] != 'thermal_intel.py'):
        raise ValueError('unexpected runtime revision manifest')
    return paths


def _safe_name(name):
    path = PurePosixPath(name)
    return (name and not path.is_absolute() and str(path) == name
            and all(part not in ('.', '..') for part in path.parts))


def _revision(paths, entries):
    digest = hashlib.sha256()
    for name in paths:
        data = entries['code/' + name]
        encoded = name.encode('utf-8')
        digest.update(len(encoded).to_bytes(4, 'big'))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _is_revision(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _manifest(entries, paths, accepted, publication_runtime_revision=None):
    result = {
        'schema': SCHEMA,
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'accepted_code_revision': accepted,
        'code_revision_paths': list(paths),
        'entries': {name: hashlib.sha256(data).hexdigest()
                    for name, data in sorted(entries.items())},
    }
    if publication_runtime_revision is not None:
        result.update(schema=PUBLICATION_SCHEMA,
                      included_runtime_revision=publication_runtime_revision,
                      runtime_binding='explicit_publication_revision')
    return result


def create(output, *, runtime_root, state_root, source_bundle=None,
           publication_runtime_revision=None):
    if publication_runtime_revision is not None and not _is_revision(publication_runtime_revision):
        raise ValueError('full lowercase publication runtime SHA-256 required')
    output = Path(output)
    _private_directory(output.parent)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    runtime_root = Path(runtime_root)
    models = _private_directory(Path(state_root) / 'models')
    captures = _private_directory(Path(state_root) / 'forcing-captures')
    entries = {}
    if source_bundle is None:
        main = _read(runtime_root / 'thermal_intel.py')
        paths = _paths(main)
        for name in paths:
            entries['code/' + name] = main if name == 'thermal_intel.py' else _read(runtime_root / name)
        entries['code/thermal_model/forcing_capture.py'] = _read(
            runtime_root / 'thermal_model/forcing_capture.py')
    else:
        source_data = _read(source_bundle, private=True, max_size=MAX_TOTAL)
        _, verified_source = _verify_archive_data(source_data)
        paths = _paths(verified_source['code/thermal_intel.py'])
        for name in paths:
            entries['code/' + name] = verified_source['code/' + name]
        entries['code/thermal_model/forcing_capture.py'] = verified_source[
            'code/thermal_model/forcing_capture.py']
    for name in MODEL_NAMES:
        path = models / name
        if path.exists():
            entries['state/models/' + name] = _read(path, private=True)
    accepted_data = entries.get('state/models/accepted.json')
    if accepted_data is None:
        raise ValueError('accepted thermal artifact missing')
    accepted = json.loads(accepted_data)['code_revision']
    if not _is_revision(accepted):
        raise ValueError('accepted training revision must be a full lowercase SHA-256')
    included_revision = _revision(paths, entries)
    if publication_runtime_revision is not None:
        if included_revision != publication_runtime_revision:
            raise ValueError('included code does not match explicit publication runtime')
    elif accepted != included_revision:
        runtime_label = 'included' if source_bundle is not None else 'installed'
        raise ValueError(f'accepted artifact does not match {runtime_label} runtime')
    for month in sorted(captures.iterdir()):
        _private_directory(month)
        if len(month.name) != 7 or month.name[4] != '-' or not month.name.replace('-', '').isdigit():
            raise ValueError('unexpected capture month')
        for capture in sorted(month.iterdir()):
            if not CAPTURE_NAME.fullmatch(capture.name):
                raise ValueError(f'unexpected capture file: {capture}')
            entries[f'state/forcing-captures/{month.name}/{capture.name}'] = _read(
                capture, private=True)
    if len(entries) > MAX_FILES or sum(map(len, entries.values())) > MAX_TOTAL:
        raise ValueError('replay evidence budget exceeded')
    if _read(models / 'accepted.json', private=True) != accepted_data:
        raise ValueError('accepted artifact changed during snapshot')
    if source_bundle is None:
        for name in (*paths, 'thermal_model/forcing_capture.py'):
            if _read(runtime_root / name) != entries['code/' + name]:
                raise ValueError('runtime changed during snapshot; retry when quiescent')
    elif _read(source_bundle, private=True, max_size=MAX_TOTAL) != source_data:
        raise ValueError('source-bundle runtime changed during snapshot')
    if not any(name.startswith('state/forcing-captures/') for name in entries):
        raise ValueError('at least one forcing capture required')
    manifest = _manifest(entries, paths, accepted, publication_runtime_revision)
    entries['manifest.json'] = _canonical(manifest) + b'\n'
    temporary = output.parent / ('.thermal-replay-' + uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with tarfile.open(fileobj=raw, mode='w:gz') as archive:
                for name, data in sorted(entries.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o600
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(data))
            raw.flush()
            os.fsync(raw.fileno())
        verified = verify(temporary)
        os.link(temporary, output, follow_symlinks=False)
        parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return verified


def _verify_archive_data(data):
    entries = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive:
            if (not member.isfile() or not _safe_name(member.name)
                    or member.name in entries or not 0 <= member.size <= MAX_FILE):
                raise ValueError('unexpected replay archive member')
            total += member.size
            if len(entries) >= MAX_FILES or total > MAX_TOTAL:
                raise ValueError('replay archive budget exceeded')
            entries[member.name] = archive.extractfile(member).read()
    raw = entries.pop('manifest.json', None)
    if raw is None:
        raise ValueError('replay manifest missing')
    manifest = json.loads(raw)
    fields = {'schema', 'captured_at', 'accepted_code_revision',
              'code_revision_paths', 'entries'}
    publication_binding = manifest.get('schema') == PUBLICATION_SCHEMA
    if publication_binding:
        fields |= {'included_runtime_revision', 'runtime_binding'}
    if (set(manifest) != fields or manifest.get('schema') not in (SCHEMA, PUBLICATION_SCHEMA)
            or set(manifest['entries']) != set(entries)):
        raise ValueError('replay manifest mismatch')
    for name, member_data in entries.items():
        if hashlib.sha256(member_data).hexdigest() != manifest['entries'][name]:
            raise ValueError(f'replay member digest mismatch: {name}')
    paths = _paths(entries['code/thermal_intel.py'])
    if list(paths) != manifest['code_revision_paths']:
        raise ValueError('replay source path list mismatch')
    expected_code = {'code/' + name for name in paths}
    allowed_models = {'state/models/' + name for name in MODEL_NAMES}
    captures = [name for name in entries if name.startswith('state/forcing-captures/')]
    if (not captures or any(not re.fullmatch(
            r'state/forcing-captures/[0-9]{4}-[0-9]{2}/' + CAPTURE_NAME.pattern[1:-1],
            name) for name in captures)
            or set(entries) != expected_code | {'code/thermal_model/forcing_capture.py'}
            | (set(entries) & allowed_models) | set(captures)):
        raise ValueError('unexpected replay member inventory')
    accepted = json.loads(entries['state/models/accepted.json'])['code_revision']
    if not _is_revision(accepted):
        raise ValueError('accepted training revision must be a full lowercase SHA-256')
    revision = _revision(paths, entries)
    if accepted != manifest['accepted_code_revision']:
        raise ValueError('replay training revision does not match accepted artifact')
    if publication_binding:
        if (manifest['runtime_binding'] != 'explicit_publication_revision'
                or manifest['included_runtime_revision'] != revision):
            raise ValueError('replay source does not match explicit publication runtime')
    elif accepted != revision:
        raise ValueError('replay source does not match accepted artifact')
    result = {'members': len(entries), 'accepted_code_revision': accepted,
              'captures': len(captures), 'sha256': hashlib.sha256(data).hexdigest()}
    if publication_binding:
        result.update(included_runtime_revision=revision,
                      runtime_binding=manifest['runtime_binding'])
    return result, entries


def verify(archive_path):
    archive_path = Path(archive_path)
    info = archive_path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TOTAL:
        raise ValueError(f'unexpected replay archive file: {archive_path}')
    data = archive_path.read_bytes()
    if len(data) != info.st_size:
        raise ValueError(f'archive changed while reading: {archive_path}')
    result, _ = _verify_archive_data(data)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--runtime-root', type=Path, default=Path('/home/sat/openhab/scripts'))
    parser.add_argument('--state-root', type=Path,
                        default=Path('/home/sat/.local/state/thermal-intel'))
    parser.add_argument('--source-bundle', type=Path,
                        help='private verified prior bundle containing accepted code')
    parser.add_argument('--publication-runtime-revision',
                        help='explicit full publication-runtime SHA-256; creates v2 with distinct training/runtime bindings')
    args = parser.parse_args()
    if args.action != 'create' and args.source_bundle is not None:
        parser.error('--source-bundle is only valid with create')
    if args.action != 'create' and args.publication_runtime_revision is not None:
        parser.error('--publication-runtime-revision is only valid with create')
    if args.action == 'create':
        result = create(args.archive, runtime_root=args.runtime_root,
                        state_root=args.state_root, source_bundle=args.source_bundle,
                        publication_runtime_revision=args.publication_runtime_revision)
    else:
        result = verify(args.archive)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
