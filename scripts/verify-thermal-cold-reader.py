#!/usr/bin/env python3
"""Verify an approved retained artifact reader in a fresh offline process.

Executes pinned reader imports and validation only. It never invokes training,
publication, journal commands or a recovered application entrypoint. The receipt
is not a complete environment, journal or production qualification.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import sys

FIELDS = {'schema', 'runtime', 'sources', 'artifact_schema', 'interpreter_sha256', 'artifact', 'output'}
REQUIRED = {'thermal_model/__init__.py', 'thermal_model/artifacts.py', 'thermal_model/schema.py', 'thermal_model/forcing_capture.py'}


def require(value):
    if not value: raise ValueError('cold reader refused')


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None)
    return value


def directory(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
    return path


def read(path, maximum, *, executable=False):
    path = Path(path); require(path.is_absolute() and path.resolve() == path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= maximum)
    if executable:
        require(info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022)
    else:
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600)
        directory(path.parent)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        require((before.st_dev, before.st_ino) == (info.st_dev, info.st_ino))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream: raw = stream.read(maximum+1)
        after = os.fstat(descriptor)
        require(len(raw) == info.st_size and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        return raw
    finally: os.close(descriptor)


def document(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result); result[key] = value
        return result
    def constant(_): raise ValueError('nonfinite document')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def inspect_profile(path):
    raw = read(path, 128000); profile = document(raw)
    require(isinstance(profile, dict) and set(profile) == FIELDS and profile['schema'] == 'earthship-thermal-cold-reader/v1')
    root = directory(profile['runtime']); sources = profile['sources']
    require(isinstance(sources, dict) and 4 <= len(sources) <= 128 and REQUIRED <= set(sources))
    found = set(); pending = [root]; total = 0; members = 0
    while pending:
        current = pending.pop(); directory(current)
        for entry in current.iterdir():
            members += 1; require(members <= 256)
            if stat.S_ISDIR(entry.lstat().st_mode): pending.append(entry)
            else: found.add(str(entry.relative_to(root)))
    require(found == set(sources))
    for name, expected in sources.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and str(relative) == name and '..' not in relative.parts and name.endswith('.py'))
        content = read(root/name, 2000000); total += len(content); require(total <= 16000000)
        require(sha256(content).hexdigest() == digest(expected))
    require(profile['artifact_schema'] in {'earthship-thermal-model/v4', 'earthship-thermal-model/v5'})
    require(sha256(read(Path(sys.executable).resolve(), 64000000, executable=True)).hexdigest() == digest(profile['interpreter_sha256']))
    documents = {}
    for field in ('artifact', 'output'):
        entry = profile[field]; require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'})
        content = read(entry['path'], 4000000 if field == 'artifact' else 16384)
        require(sha256(content).hexdigest() == digest(entry['sha256']))
        documents[field] = document(content)
    return profile, documents, sha256(raw).hexdigest()


def verify(path):
    require(not any(name == 'thermal_model' or name.startswith('thermal_model.') for name in sys.modules))
    require(sys.dont_write_bytecode)
    profile, documents, pin = inspect_profile(path)
    def denied(*_args, **_kwargs): raise PermissionError('offline cold-reader operation')
    socket.socket.connect = denied; socket.socket.connect_ex = denied; socket.create_connection = denied
    import psycopg2
    psycopg2.connect = denied
    sys.path.insert(0, profile['runtime'])
    artifacts = importlib.import_module('thermal_model.artifacts')
    schema = importlib.import_module('thermal_model.schema')
    forcing = importlib.import_module('thermal_model.forcing_capture')
    for module in (artifacts, schema, forcing):
        require(Path(module.__file__).resolve().is_relative_to(Path(profile['runtime'])))
    require(artifacts.MODEL_SCHEMA == profile['artifact_schema'] == documents['artifact']['schema'])
    artifact = artifacts._artifact_from_payload(documents['artifact'])
    artifacts.validate_artifact(artifact, require_eligible=True)
    schema.validate_shadow_output(documents['output'])
    require(documents['output']['confidence']['grade'] != 'unavailable')
    forcing._artifact_payload(artifact, documents['output'])
    require(inspect_profile(path)[2] == pin)
    import numpy
    import scipy
    return dict(schema='earthship-thermal-cold-reader-receipt/v1', checked_at=datetime.now(timezone.utc).isoformat(),
        profile_sha256=pin, artifact_schema=artifact.schema, artifact_sha256=profile['artifact']['sha256'],
        output_sha256=profile['output']['sha256'], interpreter_sha256=profile['interpreter_sha256'],
        source_manifest_sha256=sha256(json.dumps(profile['sources'], sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        dependencies=dict(numpy=numpy.__version__, scipy=scipy.__version__, psycopg2=psycopg2.__version__.split()[0]),
        cold_artifact_reader_verified=True, journal_qualified=False, dependency_environment_retained=False,
        production_qualified=False, automatic_actuation=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    args = parser.parse_args(argv)
    try: receipt = verify(args.profile)
    except Exception:
        print('thermal cold reader refused; validate retained bytes, schema and offline environment', file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__': raise SystemExit(main())
