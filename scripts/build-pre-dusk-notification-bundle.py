#!/usr/bin/env python3
"""Build/verify an inactive code-only bundle in an existing empty private dir.

No installation, symlink switch, credentials, outbox, service or network access.
The verifier requires the expected manifest digest from the build receipt.
"""
import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'advisory_windows.py', 'openhab_sanity_check.py', 'pre_dusk_issue_source.py',
    'pre_dusk_notification.py', 'pre_dusk_notification_cli.py',
    'pre_dusk_notification_source.py', 'pre_dusk_notification_worker.py',
    'pre_dusk_tuning.py', 'pre_dusk_tuning_history.py',
    'thermal_confirmation.py', 'thermal_messaging.py', 'thermal_state_backup.py',
)
GATES = {'pre_dusk_notification.py': ('RELEASE_READY',),
         'thermal_messaging.py': ('POLL_RELEASE_READY', 'POSITION_DELIVERY_RELEASE_READY')}
MAX_BYTES = 256 * 1024


def private(path, directory=False):
    info = path.lstat()
    wanted = stat.S_ISDIR if directory else stat.S_ISREG
    if not wanted(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('owned private bundle path required')


def checked_source(name, raw):
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('bounded source required')
    tree = ast.parse(raw, filename=name)
    compile(tree, name, 'exec')  # Compile only; never import or execute the bundle.
    for gate in GATES.get(name, ()):
        assignments = [node.value for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == gate for target in node.targets)]
        if len(assignments) != 1 or not isinstance(assignments[0], ast.Constant) or assignments[0].value is not False:
            raise ValueError('inactive release gates required')


def digest(raw):
    return sha256(raw).hexdigest()


def bounded_bytes(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('bounded bundle file required')
    return raw


def build(output, source=ROOT / 'openhab/scripts'):
    output = Path(output)
    private(output, directory=True)
    if any(output.iterdir()):
        raise ValueError('empty dedicated bundle directory required')
    payloads = {}
    for name in FILES:
        path = Path(source) / name
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('regular source required')
        raw = bounded_bytes(path)
        checked_source(name, raw)
        payloads[name] = raw
    manifest = {'version': 1, 'scope': 'inactive_pre_dusk_notification_code_only',
                'files': {name: digest(raw) for name, raw in payloads.items()}}
    encoded = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
    # All source/gate checks precede output writes. Never replace an existing file.
    for name, raw in {**payloads, 'manifest.json': encoded}.items():
        fd = os.open(output / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    directory_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return verify(output, digest(encoded))


def verify(output, expected_digest):
    output = Path(output)
    private(output, directory=True)
    if set(path.name for path in output.iterdir()) != set(FILES) | {'manifest.json'}:
        raise ValueError('exact bundle membership required')
    private(output / 'manifest.json')
    encoded = bounded_bytes(output / 'manifest.json')
    if len(encoded) > MAX_BYTES or digest(encoded) != expected_digest:
        raise ValueError('manifest digest mismatch')
    manifest = json.loads(encoded)
    if (set(manifest) != {'version', 'scope', 'files'} or type(manifest['version']) is not int
            or manifest['version'] != 1 or manifest['scope'] != 'inactive_pre_dusk_notification_code_only'
            or set(manifest['files']) != set(FILES)):
        raise ValueError('manifest scope mismatch')
    for name in FILES:
        path = output / name
        private(path)
        raw = bounded_bytes(path)
        if digest(raw) != manifest['files'][name]:
            raise ValueError('source digest mismatch')
        checked_source(name, raw)
    return {'status': 'verified_inactive_code_bundle', 'manifest_sha256': expected_digest,
            'files': len(FILES), 'units_installed': 0, 'messages_published': 0,
            'credentials_included': False, 'production_installed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-manifest-sha256')
    args = parser.parse_args(argv)
    try:
        result = (verify(args.output, args.verify_manifest_sha256)
                  if args.verify_manifest_sha256 else build(args.output))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('{"status":"refused","reason":"inactive code bundle verification failed"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
