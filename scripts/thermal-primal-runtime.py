#!/usr/bin/env python3
"""Stage/verify a frozen, inactive Primal code closure, never shared model code.

CLI modes perform no secret, dependency, journal, signer, network or service access.
The separately called private environment writer accepts only the seven reviewed
runtime fields; it never prints or returns their values.
Dependency/identity/configuration and full recovery checks are separate gates.
"""
import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

FILES = (
    'thermal_confirmation.py', 'thermal_messaging.py', 'thermal_nip04.py',
    'thermal_state_backup.py', 'thermal_primal.py', 'thermal_model/__init__.py',
    'thermal_model/schema.py', 'thermal_model/journal.py',
    'thermal_model/airflow_migration.py',
)
GATES = {
    'thermal_confirmation.py': ('POSITION_INGRESS_RELEASE_READY',),
    'thermal_messaging.py': ('POSITION_DELIVERY_RELEASE_READY', 'POLL_RELEASE_READY'),
    'thermal_nip04.py': ('PRIMAL_RELEASE_READY',),
    'thermal_model/journal.py': ('V2_WRITE_RELEASE_READY',),
    'thermal_model/airflow_migration.py': ('RELEASE_READY',),
}
SCHEMA = 'earthship-primal-inactive-code/v1'
MAX_FILE = 256 * 1024
ENVIRONMENT_KEYS = frozenset({
    'NOSTR_SECRET_KEY', 'THERMAL_DATABASE_URL', 'THERMAL_DATABASE_RUNTIME_ROLE',
    'THERMAL_DATABASE_EXPECTED_OWNER', 'EARTHSHIP_PRIMAL_NAK',
    'EARTHSHIP_PRIMAL_NAK_SHA256', 'EARTHSHIP_PRIMAL_NAK_VERSION',
})


def private_directory(path):
    info = path.lstat()
    if (not path.is_absolute() or path.resolve() != path
            or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError('owned non-symlink mode-0700 directory required')


def read(path, *, private=False):
    info = path.lstat()
    if (not path.is_absolute() or path.resolve() != path
            or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o002 or info.st_size > MAX_FILE
            or (private and stat.S_IMODE(info.st_mode) != 0o600)):
        raise ValueError('unsafe runtime file or size')
    value = path.read_bytes()
    if len(value) != info.st_size:
        raise ValueError('runtime source changed while reading')
    return value


def check_source(name, value):
    try:
        tree = ast.parse(value, filename=name)
        compile(tree, name, 'exec')
        for gate in GATES.get(name, ()):
            assignments = [node.value for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == gate for target in node.targets)]
            if len(assignments) != 1 or ast.literal_eval(assignments[0]) is not False:
                raise ValueError('inactive runtime release gate must be exactly false')
    except (SyntaxError, TypeError, UnicodeError) as error:
        raise ValueError('runtime syntax or gate declaration refused') from error


def write_new(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())


def write_environment(path, values):
    """New private systemd environment file; no shell execution or overwrite."""
    path = Path(path)
    private_directory(path.parent)
    if (not isinstance(values, dict) or set(values) != ENVIRONMENT_KEYS
            or any(not isinstance(value, str) or not 0 < len(value) <= 4096
                   or any(ord(char) < 32 or ord(char) == 127 for char in value)
                   for value in values.values())):
        raise ValueError('exact bounded private runtime environment required')
    def quote(value):
        return '"'+value.replace('\\', '\\\\').replace('"', '\\"')+'"'
    raw = ''.join(name+'='+quote(values[name])+'\n' for name in sorted(values)).encode('utf-8')
    write_new(path, raw)
    fd = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage(source, destination):
    source, destination = Path(source), Path(destination)
    private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise ValueError('existing runtime must not be overwritten')
    if not destination.is_absolute() or destination.parent.resolve()/destination.name != destination:
        raise ValueError('absolute non-symlink runtime destination required')
    contents = {name: read(source/name) for name in FILES}
    for name, value in contents.items():
        check_source(name, value)
    destination.mkdir(mode=0o700)
    (destination/'code').mkdir(mode=0o700)
    (destination/'code/thermal_model').mkdir(mode=0o700)
    for name, value in contents.items():
        write_new(destination/'code'/name, value)
    manifest = {'schema': SCHEMA, 'release_enabled': False,
                'files_sha256': {name: sha256(value).hexdigest() for name, value in contents.items()}}
    raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()+b'\n'
    write_new(destination/'code-manifest.json', raw)
    for directory in (destination/'code/thermal_model', destination/'code', destination):
        fd = os.open(directory, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    pin = sha256(raw).hexdigest()
    result = verify(destination, pin)
    result['status'] = 'inactive_code_staged'
    return result


def verify(directory, expected_manifest_sha256):
    directory = Path(directory)
    if (not isinstance(expected_manifest_sha256, str)
            or re.fullmatch('[0-9a-f]{64}', expected_manifest_sha256) is None):
        raise ValueError('independently selected manifest SHA-256 required')
    for parent in (directory, directory/'code', directory/'code/thermal_model'):
        private_directory(parent)
    raw = read(directory/'code-manifest.json', private=True)
    if sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError('runtime manifest byte pin differs')
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'release_enabled', 'files_sha256'}
            or manifest['schema'] != SCHEMA or manifest['release_enabled'] is not False
            or not isinstance(manifest['files_sha256'], dict)
            or set(manifest['files_sha256']) != set(FILES)):
        raise ValueError('unexpected inactive runtime manifest')
    actual = set()
    for path in (directory/'code').rglob('*'):
        name = path.relative_to(directory/'code').as_posix()
        if name == 'thermal_model' and path.is_dir() and not path.is_symlink():
            continue
        actual.add(name)
    if actual != set(FILES):
        raise ValueError('unexpected runtime code inventory')
    for name, expected in manifest['files_sha256'].items():
        value = read(directory/'code'/name, private=True)
        if sha256(value).hexdigest() != expected:
            raise ValueError('frozen runtime code differs')
        check_source(name, value)
    return {'status': 'inactive_code_verified', 'scope': 'code-only-no-dependency-or-secret-qualification',
            'release_enabled': False, 'files': len(FILES),
            'manifest_sha256': expected_manifest_sha256, 'collector_activated': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--manifest-sha256')
    args = parser.parse_args(argv)
    try:
        if args.verify:
            result = verify(args.destination, args.manifest_sha256)
        elif args.source is not None and args.manifest_sha256 is None:
            result = stage(args.source, args.destination)
        else:
            raise ValueError('explicit source or independent verification pin required')
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError):
        print('inactive Primal runtime refused; source, permissions or pin invalid')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
