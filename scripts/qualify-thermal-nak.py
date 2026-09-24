#!/usr/bin/env python3
"""Qualify a pinned nak with disposable keys; never use the household journal.

No installation, permission changes, message publication or service activation.
Only the explicit local executable and temporary configuration are used. nak's
unwrap may attempt read-only relay discovery for the disposable identities;
CI additionally runs in a disconnected network namespace.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_confirmation as thermal

DEFAULT_NAK = Path('/home/sat/.local/bin/nak')
VERSION = 'nak version v0.20.7'
# Upstream release asset digests, not a report of the installed host binary.
RELEASE_HASHES = {
    'x86_64': 'ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e',
    'aarch64': '917b19813f2f27ca6bc937d151652953ceeea2c18cd2610f6d1a9bf3e7161634',
}
# Public, disposable test keys. NEVER use these identities outside this test.
SENDER_KEY = format(1, '064x')
RECIPIENT_KEY = format(2, '064x')
WRAPPER_KEY = format(3, '064x')
SENDER = '79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
RECIPIENT = 'c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'


class QualificationFailed(RuntimeError):
    """Only fixed diagnostics may leave the qualification process."""


def require(condition, diagnostic):
    if not condition:
        raise QualificationFailed(diagnostic)


def release_digest():
    require(sys.platform == 'linux', 'default release pin supports Linux only')
    digest = RELEASE_HASHES.get(platform.machine())
    require(digest is not None, 'architecture needs an explicitly reviewed SHA-256')
    return digest


def inspect_binary(path: Path, digest: str):
    """Check bytes and permissions before executing even --version."""
    thermal.identifier(digest)
    require(digest not in thermal.UNQUALIFIED_NAK_SHA256, 'old nak build is not qualified')
    require(path.is_absolute(), 'nak path must be absolute')
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), 'nak must be a non-symlink regular file')
    require(info.st_uid in {0, os.getuid()} and not info.st_mode & 0o022
            and bool(info.st_mode & 0o111), 'nak ownership or executable permissions are unsafe')
    require(0 < info.st_size <= 128 * 1024 * 1024, 'nak size outside bound')
    with path.open('rb') as stream:
        hasher = sha256()
        total = 0
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            total += len(block)
            require(total <= 128 * 1024 * 1024, 'nak size outside bound')
            hasher.update(block)
    require(hasher.hexdigest() == digest, 'nak does not match the selected release pin')


def isolated_environment(home: str):
    # No inherited secrets, client key, proxy, household config or database DSN.
    return {'PATH': os.defpath, 'HOME': home, 'XDG_CONFIG_HOME': home + '/.config',
            'LANG': 'C.UTF-8', 'NOSTR_SECRET_KEY': RECIPIENT_KEY}


def expect_refused(operation, diagnostic):
    try:
        operation()
    except thermal.Refused:
        return
    # Timeouts/unavailable executables are NOT evidence of cryptographic rejection.
    raise QualificationFailed(diagnostic)


def qualify(path: Path, digest: str):
    inspect_binary(path, digest)
    checks = []
    with tempfile.TemporaryDirectory(prefix='thermal-nak-qualification-') as home:
        env = isolated_environment(home)
        with patch.dict(os.environ, env, clear=True):
            def call(args, payload=b'', key=RECIPIENT_KEY):
                return thermal.run_bounded([str(path), *args], payload,
                                           dict(env, NOSTR_SECRET_KEY=key))

            version = call(['--version']).decode('utf-8').strip()
            require(version == VERSION, 'unexpected nak version; review this candidate separately')
            now = int(datetime.now(timezone.utc).timestamp())

            def signed(kind, content, tags, key):
                event = {'created_at': now, 'kind': kind, 'tags': tags, 'content': content}
                raw = call(['event'], thermal.canonical(event) + b'\n', key)
                return thermal.validate_event(thermal.strict_json(raw), kind=kind, signed=True)

            def encrypted(value, key):
                # Only synthetic plaintext appears in these CLI arguments.
                return call(['encrypt', '-p', RECIPIENT, '--',
                             thermal.canonical(value).decode('utf-8')], key=key).decode().strip()

            rumor = {'created_at': now, 'kind': 14, 'tags': [['p', RECIPIENT], ['e', 'a' * 64]],
                     'pubkey': SENDER, 'content': 'yes'}
            rumor['id'] = thermal.event_id(rumor)

            def wrapped(value, mutate_seal=None, corrupt_ciphertext=False):
                seal = signed(13, encrypted(value, SENDER_KEY), [], SENDER_KEY)
                require(seal['pubkey'] == SENDER, 'test sender key mismatch')
                if mutate_seal is not None:
                    mutate_seal(seal)
                ciphertext = encrypted(seal, WRAPPER_KEY)
                if corrupt_ciphertext:
                    # Preserve a validly signed outer event around a broken NIP-44 payload.
                    ciphertext = ciphertext[:-4] + ('AAAA' if ciphertext[-4:] != 'AAAA' else 'BBBB')
                return signed(1059, ciphertext, [['p', RECIPIENT]], WRAPPER_KEY)

            decoder = thermal.NakDecoder(path, digest)
            def decode(value):
                return decoder.decode(thermal.canonical(value), RECIPIENT)
            def expected_fields(value):
                return {name: value[name] for name in rumor}

            valid = wrapped(rumor)
            require(expected_fields(decode(valid)) == rumor, 'valid round-trip did not preserve the rumor')
            checks.append('valid_authenticated_roundtrip')

            bad_id = deepcopy(valid)
            bad_id['id'] = '0' * 64
            expect_refused(lambda: decode(bad_id), 'tampered outer ID was accepted')
            checks.append('outer_id_tamper_rejected')

            bad_signature = deepcopy(valid)
            bad_signature['sig'] = '0' * 128
            expect_refused(lambda: decode(bad_signature), 'invalid outer signature was accepted')
            checks.append('outer_signature_tamper_rejected')

            forged_seal = wrapped(rumor, lambda seal: seal.update(sig='0' * 128))
            expect_refused(lambda: decode(forged_seal), 'forged seal signature was accepted')
            checks.append('forged_seal_signature_rejected')

            changed_seal = wrapped(rumor, lambda seal: seal.update(created_at=seal['created_at'] - 1))
            expect_refused(lambda: decode(changed_seal), 'changed seal with stale signature was accepted')
            checks.append('seal_content_signature_binding')

            forged_author = deepcopy(rumor)
            forged_author['pubkey'] = RECIPIENT
            forged_author['id'] = thermal.event_id(forged_author)
            expect_refused(lambda: decode(wrapped(forged_author)),
                           'mismatched raw rumor author was accepted')
            checks.append('mismatched_raw_rumor_author_rejected')

            corrupt = wrapped(rumor, corrupt_ciphertext=True)
            expect_refused(lambda: decode(corrupt), 'corrupt ciphertext was accepted')
            checks.append('corrupt_ciphertext_rejected')

            expect_refused(lambda: decoder.decode(thermal.canonical(valid), SENDER),
                           'wrong outer recipient was accepted')
            checks.append('wrong_outer_recipient_rejected')
            inspect_binary(path, digest)

    return {'version': 1, 'status': 'passed', 'nak_version': version, 'nak_path': str(path),
            'nak_sha256': digest, 'scope': 'disposable-local-key-authentication', 'checks': checks,
            'production_ready': False, 'household_keys_used': False, 'journal_writes': 0,
            'bunker_verified': False, 'relay_delivery_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nak', type=Path, default=DEFAULT_NAK)
    parser.add_argument('--sha256', help='explicit, independently reviewed candidate pin; never auto-trusted')
    args = parser.parse_args(argv)
    try:
        result = qualify(args.nak, args.sha256 or release_digest())
    except (QualificationFailed, thermal.Refused) as error:
        print(json.dumps({'status': 'failed', 'reason': str(error), 'production_ready': False}))
        return 1
    except (OSError, ValueError, KeyError, thermal.Retryable):
        print(json.dumps({'status': 'incomplete', 'reason': 'qualification dependency or execution failed',
                          'production_ready': False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
