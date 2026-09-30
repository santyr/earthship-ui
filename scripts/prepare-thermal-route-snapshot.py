#!/usr/bin/env python3
"""Read/save ONLY the two operator-approved signed inbox announcements.

No signing credential, publication, listener or journal mutation. This frozen
inventory is not a claim of relay completeness or future route discovery.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'openhab/scripts'))
import thermal_confirmation as t
import thermal_messaging as m
from thermal_state_backup import _private_directory

COLLECTOR = m.collector_public_key('npub1qkjnsgk6zrszkmk2c7ywycvh46ylp3kw4kud8y8a20m93y5synvqewl0sq')
OPERATOR = m.collector_public_key('npub1v60thnx0gz0wq3n6xdnq46y069l9x70xgmjp6lprdl6fv0eux6mqgjj4rp')
APPROVED = {
    COLLECTOR: 'f75b3a5fd8fc5a6734af6cee3a4c5a64009e86bc0efd57e6926b9ec434a16c84',
    OPERATOR: 'defe6a8571ae87261278bcae968f88d821e304930e7fad5e7e486f46e1fb20d2'}
RELAYS = ('wss://nos.lol', 'wss://relay.primal.net', 'wss://relay.damus.io')
SOURCES = (RELAYS[0], RELAYS[2], RELAYS[1])


def prepare(output=None, keyer=None):
    if output is not None:
        output = Path(output)
        _private_directory(output.parent)
        if output.exists() or output.is_symlink():
            raise t.Refused('existing route snapshot will not be overwritten')
    keyer = keyer or m.Keyer(m.DEFAULT_NAK, m.DEFAULT_SHA256)
    keyer.check_binary()
    policy = t.Policy(COLLECTOR, frozenset({OPERATOR}), (), version=2)
    args = ['req', '-k', '10050', '-l', '2']
    for author, identifier in APPROVED.items():
        args.extend(['-a', author, '-i', identifier])
    payload = None
    for relay in SOURCES:
        try:
            raw = keyer.call(args+[relay])  # Identity=False: no signing key.
            events = [t.strict_json(line) for line in raw.splitlines() if line.strip()]
            if len(events) != 2 or {e['pubkey']: e['id'] for e in events} != APPROVED:
                raise t.Refused('approved route identities differ')
            for event in events:
                if (event['content'] != '' or len(event['tags']) != len(RELAYS)
                        or set(tuple(tag) for tag in event['tags']) !=
                           {('relay', url) for url in RELAYS}):
                    raise t.Refused('approved route endpoints differ')
            payload = t.canonical({'version': 1, 'announcements': sorted(events, key=lambda e: e['pubkey'])})
            m.Routes(payload, policy, keyer)
            break
        except (t.Refused, t.Retryable, ValueError, TypeError, KeyError):
            payload = None
    if payload is None:
        raise t.Retryable('approved route snapshot unavailable')
    if output is not None:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload+b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        saved = m.read_private(output)
        if saved != payload+b'\n':
            raise t.Refused('saved route snapshot differs')
        m.Routes(saved, policy, keyer)
        fd = os.open(output.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {'status': 'saved' if output is not None else 'verified',
        'scope': 'approved_frozen_signed_route_snapshot', 'source_relay': relay,
        'identities': len(APPROVED), 'route_count_per_identity': len(RELAYS),
        'snapshot_sha256': sha256(payload+b'\n').hexdigest(),
        'output': None if output is None else str(output), 'publication': False,
        'signing_key_used': False, 'collector_activated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='NEW file in an existing private directory')
    args = parser.parse_args()
    try:
        result = prepare(args.output)
    except Exception as error:
        print(json.dumps({'status': 'withheld', 'error_type': type(error).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
