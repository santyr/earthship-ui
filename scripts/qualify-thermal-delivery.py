#!/usr/bin/env python3
"""Real nak + loopback relay qualification with ONLY public disposable keys.

No household bunker, keys, database, relay endpoints or environment is used.
The journal sink is explicitly in-memory; this is not PostgreSQL qualification.
"""
from datetime import datetime, timedelta, timezone
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_confirmation as t
import thermal_messaging as m

SKEY, CKEY = format(1, '064x'), format(2, '064x')
O = '79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
C = 'c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'


class MemorySink:
    """Explicit test double; never import production database adapters."""
    def __init__(self):
        self.records = []
    def store(self, records, payload):
        self.records.append(records)


def qualify(nak):
    from websockets.sync.server import serve
    checks = []
    with tempfile.TemporaryDirectory(prefix='thermal-delivery-qualification-') as home:
        env = {'PATH': os.defpath, 'HOME': home, 'XDG_CONFIG_HOME': home + '/.config',
               'LANG': 'C.UTF-8', 'NOSTR_SECRET_KEY': CKEY}
        with patch.dict(os.environ, env, clear=True):
            keyer = m.Keyer(nak, m.DEFAULT_SHA256)
            assert keyer.call(['--version']).decode().strip() == 'nak version v0.20.7'
            assert keyer.check_identity(C)['status'] == 'passed'
            checks.append('real_signer_encrypt_decrypt_self_check')
            try:
                keyer.check_identity(O)
            except t.Refused:
                checks.append('wrong_keyer_identity_rejected')
            else:
                raise AssertionError('wrong collector identity accepted')
            seen, errors = [], []

            def handler(ws):
                try:
                    first = t.strict_json(ws.recv(timeout=10).encode())
                    assert first[0] == 'EVENT'
                    keyer.verify(first[1], 1059)
                    ws.send(t.canonical(['AUTH', 'local-delivery-check']).decode())
                    ws.send(t.canonical(['OK', first[1]['id'], False, 'auth-required: test']).decode())
                    auth = t.strict_json(ws.recv(timeout=40).encode())
                    assert auth[0] == 'AUTH'
                    keyer.verify(auth[1], 22242)
                    assert auth[1]['pubkey'] == C
                    assert ['challenge', 'local-delivery-check'] in auth[1]['tags']
                    assert ['relay', url] in auth[1]['tags']
                    ws.send(t.canonical(['OK', auth[1]['id'], True, '']).decode())
                    retried = t.strict_json(ws.recv(timeout=10).encode())
                    assert retried == first
                    seen.append(first[1])
                    ws.send(t.canonical(['OK', first[1]['id'], True, '']).decode())
                except Exception as error:
                    errors.append(type(error).__name__)

            with serve(handler, '127.0.0.1', 0, compression=None, max_size=t.MAX_INPUT) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                url = f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
                now = datetime.now(timezone.utc).replace(microsecond=0)
                policy = t.Policy.load(t.canonical(dict(version=1, recipient=C, operators=[O],
                    prompts=[dict(operator=O, actions={'vent': 'closed'},
                        issued_at=(now - timedelta(minutes=1)).isoformat(),
                        expires_at=(now + timedelta(hours=1)).isoformat())])), assign_ids=True)
                announcements = []
                for public, secret in ((C, CKEY), (O, SKEY)):
                    obj = {'kind': 10050, 'created_at': int(now.timestamp()), 'tags': [['relay', url]], 'content': ''}
                    with patch.dict(os.environ, {'NOSTR_SECRET_KEY': secret}):
                        announcements.append(t.strict_json(keyer.call(['event'], t.canonical(obj) + b'\n', identity=True)))
                routes = m.Routes(t.canonical(dict(version=1, announcements=announcements)),
                                  policy, keyer, local_test=True)
                spool = t.Spool(Path(home) / 'state')
                outbox = m.Outbox(Path(home) / 'state')
                sink = MemorySink()
                try:
                    d = m.Delivery(policy, routes, spool, outbox, keyer,
                                   m.Relay(keyer, C, auth=True, local_test=True), sink)
                    d.queue_prompts(now)
                    result = d.flush()
                    assert result == dict(relay_acceptances=2, retryable=0, withheld=0, deferred=0), result
                    assert not errors and len(seen) == 2
                    checks.extend(['signed_recipient_relay_routes', 'real_nip42_challenge',
                                   'exact_relay_acceptance_for_both_copies'])
                    prompt = t.prompt_event(policy.prompts[0], C)
                    for wrap in seen:
                        target = t.tag_value(wrap, 'p')
                        with patch.dict(os.environ, {'NOSTR_SECRET_KEY': CKEY if target == C else SKEY}):
                            decoded = keyer.decode(t.canonical(wrap), target)
                        assert m.rumor_fields(decoded) == prompt
                        assert prompt['content'] not in t.canonical(wrap).decode()
                    checks.append('operator_and_sender_copies_decrypt_to_exact_prompt')
                    response = {'kind': 14, 'pubkey': O, 'created_at': int(now.timestamp()),
                                'tags': [['p', C], ['e', prompt['id']]], 'content': 'yes'}
                    response['id'] = t.event_id(response)
                    with patch.dict(os.environ, {'NOSTR_SECRET_KEY': SKEY}):
                        wrapped = keyer.wrap(response, C)
                    receipt = d.receive(t.canonical(wrapped))
                    assert receipt['status'] == 'stored' and len(sink.records) == 1
                    assert d.flush()['relay_acceptances'] == 2
                    assert len(seen) == 4 and not errors
                    for wrap in seen[2:]:
                        target = t.tag_value(wrap, 'p')
                        with patch.dict(os.environ, {'NOSTR_SECRET_KEY': CKEY if target == C else SKEY}):
                            decoded = keyer.decode(t.canonical(wrap), target)
                        assert t.tag_value(decoded, 'e') == response['id']
                        assert json.loads(decoded['content'].split('\n', 1)[1]) == receipt
                    checks.append('authenticated_reply_and_encrypted_storage_receipt')
                    outbox.close()
                    outbox = m.Outbox(Path(home) / 'state')
                    d.outbox = outbox
                    assert d.flush()['relay_acceptances'] == 0 and len(seen) == 4
                    checks.append('restart_does_not_republish_accepted_events')
                finally:
                    outbox.close()
                    spool.close()
                    server.shutdown()
                    worker.join(timeout=5)
    return dict(version=1, status='passed', scope='real-local-key-and-loopback-relay', checks=checks,
                household_keys_used=False, household_bunker_verified=False,
                production_journal_writes=0, journal_test_double=True,
                external_relay_delivery_verified=False, production_ready=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nak', required=True, type=Path)
    args = parser.parse_args()
    try:
        if not __debug__:
            raise RuntimeError('qualification requires assertions enabled')
        print(json.dumps(qualify(args.nak), sort_keys=True))
        return 0
    except Exception:
        # Avoid plaintext or keyer data in CI or host diagnostics.
        print(json.dumps(dict(status='failed', production_ready=False,
                              reason='delivery qualification failed; no household services used')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
