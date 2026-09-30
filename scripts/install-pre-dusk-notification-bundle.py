#!/usr/bin/env python3
"""Guarded inactive code deployment only; no units, credentials or messages."""
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import argparse

SPEC = importlib.util.spec_from_file_location('bundle_builder', Path(__file__).with_name('build-pre-dusk-notification-bundle.py'))
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)
RUNTIME = Path('/home/sat/.local/lib/earthship-pre-dusk-notification')
HEX = re.compile('[0-9a-f]{64}\\Z')


def raw_current(root):
    try:
        root.lstat()
    except FileNotFoundError:
        return None
    bundle.private(root, directory=True)
    link = root / 'current'
    try:
        info = link.lstat()
    except FileNotFoundError:
        return None
    if not link.is_symlink() or info.st_uid != os.getuid():
        raise ValueError('owned runtime symlink required')
    target = os.readlink(link)
    if not target.startswith('releases/') or not HEX.fullmatch(target[9:]):
        raise ValueError('runtime pointer outside exact release scope')
    bundle.private(root / 'releases', directory=True)
    return target[9:]


def current(root):
    value = raw_current(root)
    if value is not None:
        bundle.verify(root / 'releases' / value, value)
    return value


@contextmanager
def lock(root):
    root.mkdir(mode=0o700, exist_ok=True)
    bundle.private(root, directory=True)
    if set(p.name for p in root.iterdir()) - {'releases', 'current', 'install.lock'}:
        raise ValueError('runtime namespace contains unknown files')
    fd = os.open(root / 'install.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        bundle.private(root / 'install.lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def sync_directory(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def switch(root, expected, replacement):
    if raw_current(root) != expected:
        raise ValueError('concurrent runtime pointer change')
    if replacement is None:
        if expected is not None:
            (root / 'current').unlink()
    else:
        if not isinstance(replacement, str) or not HEX.fullmatch(replacement):
            raise ValueError('exact replacement digest required')
        bundle.verify(root / 'releases' / replacement, replacement)
        temporary = root / ('.pointer-' + secrets.token_hex(12))
        try:
            temporary.symlink_to('releases/' + replacement)
            if raw_current(root) != expected:
                raise ValueError('concurrent runtime pointer change')
            os.replace(temporary, root / 'current')
        finally:
            if temporary.is_symlink():
                temporary.unlink()
    sync_directory(root)


def install(source, expected_digest, expected_current=None, *, root=RUNTIME, probe=None):
    source, root = Path(source), Path(root)
    bundle.verify(source, expected_digest)
    with lock(root):
        if current(root) != expected_current:
            raise ValueError('runtime preimage changed')
        releases = root / 'releases'
        releases.mkdir(mode=0o700, exist_ok=True)
        bundle.private(releases, directory=True)
        target = releases / expected_digest
        if target.exists() or target.is_symlink():
            bundle.verify(target, expected_digest)
        else:
            stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=releases))
            try:
                for name in (*bundle.FILES, 'manifest.json'):
                    raw = bundle.bounded_bytes(source / name)
                    fd = os.open(stage / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                bundle.verify(stage, expected_digest)
                sync_directory(stage)
                os.rename(stage, target)
                sync_directory(releases)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)  # Exact newly-created owned stage only.
        try:
            switch(root, expected_current, expected_digest)
            (probe or bundle.verify)(target, expected_digest)
            if current(root) != expected_digest:
                raise ValueError('runtime readback changed')
        except Exception:
            # Ownership/preimage check does not trust a broken candidate's
            # contents. Verify the original release before restoring it, and
            # never overwrite a subsequent/concurrent pointer.
            if raw_current(root) == expected_digest:
                switch(root, expected_digest, expected_current)
            raise
        return {'status': 'installed_inactive_code', 'manifest_sha256': expected_digest,
                'previous_manifest_sha256': expected_current, 'units_installed': 0,
                'messages_published': 0, 'credentials_changed': False}


def rollback(expected_current, restore, *, root=RUNTIME):
    root = Path(root)
    with lock(root):
        switch(root, expected_current, restore)
        if current(root) != restore:
            raise ValueError('rollback readback mismatch')
    return {'status': 'inactive_pointer_restored', 'manifest_sha256': restore}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--expected-current')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        bundle.verify(args.bundle, args.manifest_sha256)
        if args.apply:
            result = install(args.bundle, args.manifest_sha256, args.expected_current)
        else:
            existing = current(RUNTIME) if RUNTIME.exists() else None
            if existing != args.expected_current:
                raise ValueError('runtime preimage changed')
            result = {'status': 'inactive_install_preflight', 'writes': 0,
                      'manifest_sha256': args.manifest_sha256,
                      'previous_manifest_sha256': existing}
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('{"status":"refused","reason":"inactive bundle deployment failed"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
