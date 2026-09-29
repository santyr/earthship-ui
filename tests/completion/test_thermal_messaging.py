"""Real SQLite and loopback WebSocket tests; FakeKeyer is NOT crypto evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_messaging as m
import thermal_confirmation as t

C, O = 'b' * 64, 'a' * 64
NOW = datetime(2026, 9, 22, 16, tzinfo=timezone.utc)


def event(kind=14, pubkey=O, tags=None, content='yes', stamp=None):
    obj = dict(kind=kind, pubkey=pubkey, created_at=int((stamp or NOW).timestamp()),
               tags=tags if tags is not None else [['p', C]], content=content)
    obj['id'] = t.event_id(obj)
    obj['sig'] = '0' * 128
    return obj


def policy():
    draft = dict(version=1, recipient=C, operators=[O], prompts=[dict(operator=O,
        issued_at=(NOW - timedelta(minutes=5)).isoformat(), expires_at=(NOW + timedelta(minutes=5)).isoformat(),
        actions={'vent': 'closed'})])
    return t.Policy.load(t.canonical(draft), assign_ids=True)


class FakeKeyer:
    def __init__(self):
        self.wraps = []
        self.signs = []
    def verify(self, obj, kind):
        return t.validate_event(obj, kind=kind, signed=True)
    def wrap(self, rumor, target):
        self.wraps.append((deepcopy(rumor), target))
        # The varying wrapper identity exercises persistence of randomized envelopes.
        return event(1059, str(len(self.wraps) % 10) * 64, [['p', target]], t.canonical(rumor).decode())
    def decode(self, raw, recipient):
        return m.rumor_fields(t.strict_json(raw))  # unsigned-rumor test double, not crypto
    def sign(self, obj, expected):
        self.signs.append(deepcopy(obj))
        return event(obj['kind'], expected, obj['tags'], obj['content'],
                     datetime.fromtimestamp(obj['created_at'], timezone.utc))


class Sink:
    def __init__(self):
        self.stores = []
        self.fail = False
    def store(self, records, payload):
        if self.fail:
            raise t.Retryable('journal unavailable')
        self.stores.append(deepcopy(records))


class FakeRelay:
    def __init__(self):
        self.sent = []
        self.fail = False
    def publish(self, url, obj):
        self.sent.append((url, deepcopy(obj)))
        if self.fail:
            raise t.Retryable('relay unavailable')


def announcements():
    return dict(version=1, announcements=[event(10050, pk, [['relay', 'wss://relay.example']], '', datetime(2020, 1, 1, tzinfo=timezone.utc))
                                          for pk in (C, O)])


@pytest.fixture
def delivery(tmp_path):
    keyer, sink, relay = FakeKeyer(), Sink(), FakeRelay()
    p = policy()
    routes = m.Routes(t.canonical(announcements()), p, keyer)
    spool, outbox = t.Spool(tmp_path / 'private'), m.Outbox(tmp_path / 'private')
    obj = m.Delivery(p, routes, spool, outbox, keyer, relay, sink)
    yield obj
    outbox.close()
    spool.close()


def reply(d, content='yes'):
    return t.canonical(event(tags=[['p', C], ['e', d.policy.prompts[0].event_id]], content=content))


def test_prompt_is_queued_for_recipient_and_sender_once(delivery):
    d = delivery
    d.queue_prompts(NOW)
    d.queue_prompts(NOW)
    assert len(d.outbox.rows()) == 2
    assert {r['target'] for r in d.outbox.rows()} == {C, O}
    assert d.keyer.wraps == [] and d.relay.sent == []
    assert d.flush(NOW)['relay_acceptances'] == 2
    assert len(d.relay.sent) == 2
    assert d.flush(NOW)['relay_acceptances'] == 0


def test_retry_after_restart_reuses_exact_encrypted_envelope(delivery, tmp_path):
    d = delivery
    d.queue_prompts(NOW)
    d.relay.fail = True
    assert d.flush(NOW)['retryable'] == 2
    envelopes = [obj for _, obj in d.relay.sent]
    d.outbox.close()
    d.outbox = m.Outbox(tmp_path / 'private')
    d.relay.fail = False
    assert d.flush(NOW)['deferred'] == 2
    assert d.flush(NOW + timedelta(seconds=60))['relay_acceptances'] == 2
    assert [obj for _, obj in d.relay.sent[2:]] == envelopes
    assert len(d.keyer.wraps) == 2
    # Restore fixture cleanup handle to the reopened connection.
    # sqlite close is idempotent; close the live connection explicitly here.
    d.outbox.close()


def test_ambiguous_publish_crash_retries_identical_wrap(delivery):
    d = delivery
    d.queue_prompts(NOW)
    real = d.outbox.accepted
    d.outbox.accepted = lambda *args: (_ for _ in ()).throw(t.Retryable('receipt write failed'))
    assert d.flush(NOW)['retryable'] == 2
    first = [obj for _, obj in d.relay.sent]
    d.outbox.accepted = real
    assert d.flush(NOW + timedelta(seconds=60))['relay_acceptances'] == 2
    assert [obj for _, obj in d.relay.sent[2:]] == first


@pytest.mark.parametrize('content', ['yes', 'not yet', 'skip'])
def test_acknowledgement_follows_ingress_and_is_encrypted(delivery, content):
    d = delivery
    receipt = d.receive(reply(d, content), NOW)
    assert receipt['status'] == ('stored' if content == 'yes' else 'no_action_recorded')
    assert len(d.sink.stores) == (1 if content == 'yes' else 0)
    assert len(d.outbox.rows()) == 2 and d.relay.sent == []
    d.flush(NOW)
    assert len(d.relay.sent) == 2
    assert all(obj['kind'] == 1059 for _, obj in d.relay.sent)
    assert len(d.sink.stores) == (5 if content == 'yes' else 0)


def test_journal_failure_never_queues_success_ack(delivery):
    d = delivery
    d.sink.fail = True
    with pytest.raises(t.Retryable):
        d.receive(reply(d), NOW)
    assert d.outbox.rows() == [] and d.relay.sent == []
    d.sink.fail = False
    receipt = d.receive(reply(d), NOW + timedelta(seconds=30))
    assert receipt['first_received_at'] == NOW.isoformat()
    assert len(d.outbox.rows()) == 2


def test_later_readback_failure_withholds_pending_ack(delivery):
    d = delivery
    d.receive(reply(d), NOW)
    d.sink.fail = True
    assert d.flush(NOW)['retryable'] == 2
    assert d.relay.sent == []


def test_receipt_queue_crash_can_be_recovered(delivery, monkeypatch):
    d = delivery
    original = d.outbox.queue
    monkeypatch.setattr(d.outbox, 'queue', lambda *a: (_ for _ in ()).throw(t.Retryable('queue unavailable')))
    with pytest.raises(t.Retryable):
        d.receive(reply(d), NOW)
    assert d.spool.db.execute('SELECT count(*) FROM receipts WHERE acknowledgement IS NOT NULL').fetchone()[0] == 1
    monkeypatch.setattr(d.outbox, 'queue', original)
    # Recover using a fixed clock after the original receipt, without real network.
    d.recover_acks(NOW + timedelta(seconds=30))
    assert len(d.outbox.rows()) == 2


def test_expired_prompts_are_not_sent(delivery):
    d = delivery
    d.queue_prompts(NOW)
    assert d.flush(NOW + timedelta(hours=1))['withheld'] == 2
    assert d.relay.sent == []


def test_revoked_operator_pending_ack_is_not_sent(delivery):
    d = delivery
    d.receive(reply(d), NOW)
    d.policy = t.Policy(C, frozenset(), ())
    assert d.flush(NOW)['withheld'] == 2
    assert d.relay.sent == []


def test_mutated_message_fails_prompt_binding(delivery):
    d = delivery
    d.queue_prompts(NOW)
    with d.outbox.db:
        d.outbox.db.execute("UPDATE delivery SET body='{}'")
    assert d.flush(NOW)['withheld'] == 2
    assert d.relay.sent == []


def test_conflicting_outbox_intent_is_not_overwritten(delivery):
    d = delivery
    d.queue_prompts(NOW)
    rumor = t.prompt_event(d.policy.prompts[0], C)
    rumor['content'] = 'different question'
    rumor['id'] = t.event_id(rumor)
    with pytest.raises(t.Refused, match='conflicts'):
        d.outbox.queue('prompt:' + d.policy.prompts[0].event_id, rumor, C, O)


def test_quota_is_atomic_for_both_copies(delivery, monkeypatch):
    monkeypatch.setattr(m, 'MAX_ROWS', 1)
    with pytest.raises(t.Refused, match='quota'):
        delivery.queue_prompts(NOW)
    assert delivery.outbox.rows() == []


@pytest.mark.parametrize('url', ['http://relay.example', 'ws://relay.example', 'ws://127.0.0.1:1',
    'wss://user:secret@relay.example', 'wss://relay.example?secret=x', 'wss://relay.example/#bad',
    'wss://relay.example:0', 'wss://relay.example:99999', 'wss://', 'wss://bad\nhost', None])
def test_unsafe_relay_urls_are_refused(url):
    with pytest.raises(t.Refused):
        m.relay_url(url)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unexpected', 'wrong_kind', 'no_relays', 'too_many'])
def test_invalid_recipient_relay_inventory_is_refused(change):
    data = announcements()
    if change == 'missing': data['announcements'].pop()
    if change == 'duplicate': data['announcements'][1] = data['announcements'][0]
    if change == 'unexpected': data['announcements'][0] = event(10050, 'c' * 64, [['relay', 'wss://x']], '')
    if change == 'wrong_kind': data['announcements'][0] = event(1, C, [['relay', 'wss://x']], '')
    if change == 'no_relays': data['announcements'][0] = event(10050, C, [], '')
    if change == 'too_many': data['announcements'][0] = event(10050, C, [['relay', f'wss://x{i}'] for i in range(4)], '')
    with pytest.raises(t.Refused):
        m.Routes(t.canonical(data), policy(), FakeKeyer())


@pytest.mark.parametrize('mode', [0o755, 0o775, 0o777])
def test_public_outbox_directory_refused(tmp_path, mode):
    private = tmp_path / 'state'
    private.mkdir(mode=mode)
    private.chmod(mode)
    with pytest.raises(t.Refused, match='private'):
        m.Outbox(private)


def test_existing_world_readable_outbox_database_refused(tmp_path):
    tmp_path.chmod(0o700)
    f = tmp_path / 'delivery.sqlite3'
    f.write_text('')
    f.chmod(0o644)
    with pytest.raises(t.Refused, match='private'):
        m.Outbox(tmp_path)


def test_v1_outbox_migrates_without_losing_queued_delivery(tmp_path):
    private = tmp_path / 'private'
    outbox = m.Outbox(private)
    outbox.queue('prompt:old', t.prompt_event(policy().prompts[0], C), C, O)
    before = outbox.rows()
    outbox.db.execute('DROP TABLE inbox_ingested')
    outbox.db.execute('PRAGMA user_version=1')
    outbox.db.commit()
    outbox.close()

    migrated = m.Outbox(private)
    try:
        assert migrated.rows() == before
        assert migrated.db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert migrated.db.execute('SELECT count(*) FROM inbox_ingested').fetchone()[0] == 0
        assert migrated.db.execute('SELECT count(*) FROM inbox_refused').fetchone()[0] == 0
    finally:
        migrated.close()


def test_v2_outbox_migrates_without_losing_ingested_envelopes(tmp_path):
    private = tmp_path / 'private'
    outbox = m.Outbox(private)
    envelope = event(1059, 'c' * 64, [['p', C]], 'stored')
    outbox.record_ingress(envelope)
    outbox.db.execute('DROP TABLE inbox_refused')
    outbox.db.execute('PRAGMA user_version=2')
    outbox.db.commit()
    outbox.close()

    migrated = m.Outbox(private)
    try:
        assert migrated.db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert migrated.ingress_recorded(envelope)
        assert migrated.db.execute('SELECT count(*) FROM inbox_refused').fetchone()[0] == 0
    finally:
        migrated.close()


class Socket:
    def __init__(self, responses): self.responses, self.sent = iter(responses), []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def send(self, value): self.sent.append(json.loads(value))
    def recv(self, timeout=None):
        try: return next(self.responses)
        except StopIteration: raise TimeoutError('no matching OK')


def publisher(responses, *, auth=False):
    sock = Socket([json.dumps(x) if not isinstance(x, Exception) else x for x in responses])
    return m.Relay(FakeKeyer(), C, auth=auth, connect=lambda *a, **kw: sock), sock


@pytest.mark.parametrize('response', [['OK', 'wrong-id', True, ''], ['OK', 'id', False, 'no'],
    ['OK', 'id', 1, ''], ['NOTICE', 'hello'], ['EOSE', 'id'], ['OK', 'id', True]])
def test_wrong_or_nonpositive_relay_response_never_means_delivered(response):
    obj = event(1059, C)
    response = [obj['id'] if x == 'id' else x for x in response]
    relay, _ = publisher([response])
    with pytest.raises((t.Refused, t.Retryable)):
        relay.publish('wss://relay.example', obj)


def test_only_exact_positive_ok_means_relay_acceptance():
    obj = event(1059, C)
    relay, sock = publisher([['OK', obj['id'], True, 'duplicate: already stored']])
    assert relay.publish('wss://relay.example', obj) is None
    assert sock.sent == [['EVENT', obj]]


def test_unapproved_auth_does_not_sign():
    relay, sock = publisher([['AUTH', 'challenge']])
    with pytest.raises(t.Refused, match='explicit'):
        relay.publish('wss://relay.example', event(1059, C))
    assert relay.keyer.signs == []


def test_keyer_environment_separates_verifier_and_signer(tmp_path, monkeypatch):
    f = tmp_path / 'nak'
    f.write_bytes(b'test executable double')
    f.chmod(0o755)
    calls = []
    def runner(argv, data, env, **kwargs):
        calls.append((argv, data, env))
        return b''
    monkeypatch.setenv('NOSTR_SECRET_KEY', 'bunker://private')
    monkeypatch.setenv('NOSTR_CLIENT_KEY', 'private-client')
    monkeypatch.setenv('THERMAL_DATABASE_URL', 'PRIVATE-DB')
    monkeypatch.setenv('OPENHAB_TOKEN', 'PRIVATE-OH')
    k = m.Keyer(f, sha256(f.read_bytes()).hexdigest(), runner=runner)
    k.call(['verify'], b'{}')
    k.call(['gift', 'wrap'], b'{}', identity=True)
    assert 'NOSTR_SECRET_KEY' not in calls[0][2] and 'NOSTR_CLIENT_KEY' not in calls[0][2]
    assert calls[1][2]['NOSTR_CLIENT_KEY'] == 'private-client'
    for argv, _, env in calls:
        assert 'PRIVATE-DB' not in str(env) and 'PRIVATE-OH' not in str(env)
        assert 'private' not in str(argv)


def test_plaintext_is_stdin_not_command_argument(monkeypatch, tmp_path):
    k = m.Keyer(tmp_path / 'nak', 'a' * 64)
    seen = []
    r = event()
    del r['sig']
    wrapped = event(1059, C, [['p', O]])
    monkeypatch.setattr(k, 'call', lambda a, p=b'', **kw: seen.append((a, p)) or t.canonical(wrapped))
    monkeypatch.setattr(k, 'verify', lambda *a: None)
    k.wrap(r, O)
    assert r['content'] not in str(seen[0][0])
    assert r['content'] in seen[0][1].decode()
    assert '--use-our-identity-key' in seen[0][0] and '--use-their-identity-key' in seen[0][0]


def test_real_loopback_websocket_acceptance():
    from websockets.sync.server import serve
    got = []
    def handler(ws):
        data = json.loads(ws.recv(timeout=2))
        got.append(data)
        ws.send(json.dumps(['OK', data[1]['id'], True, '']))
    with serve(handler, '127.0.0.1', 0, compression=None) as server:
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        port = server.socket.getsockname()[1]
        obj = event(1059, C)
        m.Relay(FakeKeyer(), C, local_test=True).publish(f'ws://127.0.0.1:{port}', obj)
        server.shutdown()
        th.join(timeout=3)
    assert got == [['EVENT', obj]]


def test_real_loopback_nip42_handshake_retries_exact_event():
    from websockets.sync.server import serve
    seen = []
    def handler(ws):
        first = json.loads(ws.recv(timeout=2))
        seen.append(first)
        ws.send(json.dumps(['AUTH', 'fixed-loopback-challenge']))
        ws.send(json.dumps(['OK', first[1]['id'], False, 'auth-required: sign first']))
        auth = json.loads(ws.recv(timeout=2))
        seen.append(auth)
        assert auth[0] == 'AUTH' and auth[1]['pubkey'] == C
        assert auth[1]['kind'] == 22242
        ws.send(json.dumps(['OK', auth[1]['id'], True, '']))
        retry = json.loads(ws.recv(timeout=2))
        seen.append(retry)
        ws.send(json.dumps(['OK', retry[1]['id'], True, '']))
    with serve(handler, '127.0.0.1', 0, compression=None) as server:
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        url = f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        obj = event(1059, C)
        m.Relay(FakeKeyer(), C, auth=True, local_test=True).publish(url, obj)
        server.shutdown()
        th.join(timeout=3)
    assert seen[0] == seen[2] == ['EVENT', obj]
    assert ['relay', url] in seen[1][1]['tags']


def test_bounded_inbox_fetch_accepts_only_verified_matching_events(monkeypatch):
    monkeypatch.setattr(m.secrets, 'token_hex', lambda _: 'fixed-subscription')
    wrapped = event(1059, 'c' * 64, [['p', C]], 'encrypted',
                    datetime.now(timezone.utc))
    responses = [['EVENT', 'fixed-subscription', wrapped],
                 ['EOSE', 'fixed-subscription']]
    relay, sock = publisher(responses)
    since = int(datetime.now(timezone.utc).timestamp()) - 60
    assert relay.fetch('wss://relay.example', since=since) == [wrapped]
    assert len(sock.sent) == 1
    assert sock.sent[0][:2] == ['REQ', 'fixed-subscription']
    assert sock.sent[0][2] == {'kinds': [1059], '#p': [C], 'since': since,
                                'until': sock.sent[0][2]['until'],
                                'limit': m.MAX_INBOX_EVENTS}
    assert sock.sent[0][2]['until'] >= wrapped['created_at']


@pytest.mark.parametrize('responses', [
    [['EVENT', 'wrong-subscription', event(1059, 'c' * 64, [['p', C]], 'encrypted')]],
    [['EVENT', 'fixed-subscription', event(1059, 'c' * 64, [['p', O]], 'encrypted')]],
    [['CLOSED', 'fixed-subscription', 'restricted: no access']],
    [['NOTICE', 'PRIVATE_RELAY_MESSAGE']],
])
def test_inbox_fetch_refuses_wrong_scope_or_incomplete_reply(monkeypatch, responses):
    monkeypatch.setattr(m.secrets, 'token_hex', lambda _: 'fixed-subscription')
    relay, _ = publisher(responses)
    with pytest.raises((t.Refused, t.Retryable)) as raised:
        relay.fetch('wss://relay.example', since=int(datetime.now(timezone.utc).timestamp()) - 86400)
    assert 'PRIVATE_RELAY_MESSAGE' not in str(raised.value)


def test_inbox_fetch_does_not_sign_unapproved_auth(monkeypatch):
    monkeypatch.setattr(m.secrets, 'token_hex', lambda _: 'fixed-subscription')
    relay, _ = publisher([['AUTH', 'challenge']])
    with pytest.raises(t.Refused, match='explicit'):
        relay.fetch('wss://relay.example', since=int(datetime.now(timezone.utc).timestamp()) - 86400)
    assert relay.keyer.signs == []


def test_real_loopback_inbox_fetch_and_eose():
    from websockets.sync.server import serve
    seen = []
    wrapped = event(1059, 'c' * 64, [['p', C]], 'encrypted',
                    datetime.now(timezone.utc))
    def handler(ws):
        request = json.loads(ws.recv(timeout=2))
        seen.append(request)
        ws.send(json.dumps(['EVENT', request[1], wrapped]))
        ws.send(json.dumps(['EOSE', request[1]]))
    with serve(handler, '127.0.0.1', 0, compression=None) as server:
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        url = f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        result = m.Relay(FakeKeyer(), C, local_test=True).fetch(
            url, since=int(datetime.now(timezone.utc).timestamp()) - 60)
        server.shutdown()
        th.join(timeout=3)
    assert result == [wrapped]
    assert seen[0][0] == 'REQ' and seen[0][2]['#p'] == [C]


def test_real_loopback_inbox_auth_retries_same_query():
    from websockets.sync.server import serve
    seen = []
    wrapped = event(1059, 'c' * 64, [['p', C]], 'encrypted',
                    datetime.now(timezone.utc))
    def handler(ws):
        first = json.loads(ws.recv(timeout=2))
        seen.append(first)
        ws.send(json.dumps(['AUTH', 'fixed-inbox-challenge']))
        ws.send(json.dumps(['CLOSED', first[1], 'auth-required: sign first']))
        auth = json.loads(ws.recv(timeout=2))
        seen.append(auth)
        ws.send(json.dumps(['OK', auth[1]['id'], True, '']))
        retry = json.loads(ws.recv(timeout=2))
        seen.append(retry)
        ws.send(json.dumps(['EVENT', retry[1], wrapped]))
        ws.send(json.dumps(['EOSE', retry[1]]))
    with serve(handler, '127.0.0.1', 0, compression=None) as server:
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        url = f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        result = m.Relay(FakeKeyer(), C, auth=True, local_test=True).fetch(
            url, since=int(datetime.now(timezone.utc).timestamp()) - 60)
        server.shutdown()
        th.join(timeout=3)
    assert result == [wrapped]
    assert seen[0] == seen[2]
    assert seen[1][0] == 'AUTH' and ['relay', url] in seen[1][1]['tags']


def test_real_loopback_inbox_closed_before_auth_challenge():
    from websockets.sync.server import serve
    seen = []
    def handler(ws):
        first = json.loads(ws.recv(timeout=2))
        seen.append(first)
        ws.send(json.dumps(['CLOSED', first[1], 'auth-required: sign first']))
        ws.send(json.dumps(['AUTH', 'late-challenge']))
        auth = json.loads(ws.recv(timeout=2))
        seen.append(auth)
        ws.send(json.dumps(['OK', auth[1]['id'], True, '']))
        retry = json.loads(ws.recv(timeout=2))
        seen.append(retry)
        ws.send(json.dumps(['EOSE', retry[1]]))
    with serve(handler, '127.0.0.1', 0, compression=None) as server:
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        url = f'ws://127.0.0.1:{server.socket.getsockname()[1]}'
        assert m.Relay(FakeKeyer(), C, auth=True, local_test=True).fetch(
            url, since=int(datetime.now(timezone.utc).timestamp()) - 60) == []
        server.shutdown()
        th.join(timeout=3)
    assert seen[0] == seen[2]
    assert seen[1][0] == 'AUTH' and ['challenge', 'late-challenge'] in seen[1][1]['tags']


def test_saturated_inbox_page_is_not_claimed_complete(monkeypatch):
    monkeypatch.setattr(m.secrets, 'token_hex', lambda _: 'fixed-subscription')
    monkeypatch.setattr(m, 'MAX_INBOX_EVENTS', 1)
    fixed_now = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(m.time, 'time', lambda: fixed_now)
    wrapped = event(1059, 'c' * 64, [['p', C]], 'encrypted',
                    datetime.fromtimestamp(fixed_now, timezone.utc))
    relay, _ = publisher([['EVENT', 'fixed-subscription', wrapped],
                          ['EOSE', 'fixed-subscription']])
    with pytest.raises(t.Retryable, match='second saturated'):
        relay.fetch('wss://relay.example', since=fixed_now)


def test_saturated_inbox_windows_split_with_bounded_complete_pages(monkeypatch):
    monkeypatch.setattr(m, 'MAX_INBOX_EVENTS', 2)
    fixed_now = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(m.time, 'time', lambda: fixed_now)
    envelopes = [event(1059, 'c' * 64, [['p', C]], str(offset),
                       datetime.fromtimestamp(fixed_now - offset, timezone.utc))
                 for offset in (11, 6, 1)]
    requests = []

    class WindowSocket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send(self, value):
            request = json.loads(value)
            requests.append(request)
            lower, upper = request[2]['since'], request[2]['until']
            matching = [wrapped for wrapped in envelopes
                        if lower <= wrapped['created_at'] <= upper]
            matching.sort(key=lambda wrapped: (-wrapped['created_at'], wrapped['id']))
            self.responses = iter([['EVENT', request[1], wrapped]
                                   for wrapped in matching[:m.MAX_INBOX_EVENTS]]
                                  + [['EOSE', request[1]]])
        def recv(self, timeout=None):
            return json.dumps(next(self.responses))

    relay = m.Relay(FakeKeyer(), C, connect=lambda *args, **kwargs: WindowSocket())
    result = relay.fetch('wss://relay.example', since=fixed_now - 12)
    assert result == sorted(envelopes, key=lambda wrapped: (-wrapped['created_at'], wrapped['id']))
    assert len(requests) == 5
    assert requests[0][2]['until'] == fixed_now
    assert all(request[2]['limit'] == 2 for request in requests)

    requests.clear()
    monkeypatch.setattr(m, 'MAX_INBOX_PAGES', 2)
    with pytest.raises(t.Refused, match='page budget'):
        relay.fetch('wss://relay.example', since=fixed_now - 12)


def test_poll_replies_deduplicates_across_reviewed_routes(tmp_path):
    class InboundKeyer(FakeKeyer):
        def decode(self, raw, recipient):
            assert recipient == C
            return t.strict_json(t.strict_json(raw)['content'].encode())
    class InboxRelay(FakeRelay):
        def __init__(self, envelope):
            super().__init__()
            self.envelope = envelope
            self.queries = []
        def fetch(self, url, *, since):
            self.queries.append((url, since))
            return [self.envelope]
    p, keyer, sink = policy(), InboundKeyer(), Sink()
    route_list = announcements()
    route_list['announcements'][0] = event(10050, C,
        [['relay', 'wss://relay.example'], ['relay', 'wss://second.example']], '',
        datetime(2020, 1, 1, tzinfo=timezone.utc))
    routes = m.Routes(t.canonical(route_list), p, keyer)
    rumor = event(tags=[['p', C], ['e', p.prompts[0].event_id]])
    del rumor['sig']
    wrapped = event(1059, 'c' * 64, [['p', C]], t.canonical(rumor).decode())
    relay = InboxRelay(wrapped)
    spool, outbox = t.Spool(tmp_path / 'private'), m.Outbox(tmp_path / 'private')
    try:
        delivery = m.Delivery(p, routes, spool, outbox, keyer, relay, sink)
        result = delivery.poll_replies(NOW)
        assert result == dict(accepted=1, retryable=0, withheld=0,
                              deferred=0, refusal_backoff=0, relay_failures=0)
        assert len(relay.queries) == 2
        assert len(sink.stores) == 1
        assert len(outbox.rows()) == 2
        assert spool.get(rumor['id'])['first_received_at'] == NOW.isoformat()
    finally:
        outbox.close()
        spool.close()


def test_poll_replies_advances_past_accepted_batch_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'MAX_BATCH', 2)

    class InboundKeyer(FakeKeyer):
        def decode(self, raw, recipient):
            assert recipient == C
            return t.strict_json(t.strict_json(raw)['content'].encode())

    class InboxRelay(FakeRelay):
        def __init__(self, envelopes):
            super().__init__()
            self.envelopes = envelopes
        def fetch(self, url, *, since):
            assert url == 'wss://relay.example'
            return self.envelopes

    p, keyer, sink = policy(), InboundKeyer(), Sink()
    routes = m.Routes(t.canonical(announcements()), p, keyer)
    envelopes = []
    for seconds in (3, 2, 1):
        stamp = NOW - timedelta(seconds=seconds)
        rumor = event(tags=[['p', C], ['e', p.prompts[0].event_id]],
                      content='not yet', stamp=stamp)
        del rumor['sig']
        envelopes.append(event(1059, 'c' * 64, [['p', C]],
                               t.canonical(rumor).decode(), stamp))
    relay = InboxRelay(envelopes)
    private = tmp_path / 'private'
    spool, outbox = t.Spool(private), m.Outbox(private)
    try:
        first = m.Delivery(p, routes, spool, outbox, keyer, relay, sink).poll_replies(NOW)
        assert first == dict(accepted=2, retryable=0, withheld=0,
                             deferred=1, refusal_backoff=0, relay_failures=0)
    finally:
        outbox.close()
        spool.close()

    spool, outbox = t.Spool(private), m.Outbox(private)
    try:
        second = m.Delivery(p, routes, spool, outbox, keyer, relay, sink).poll_replies(NOW)
        assert second == dict(accepted=1, retryable=0, withheld=0,
                              deferred=0, refusal_backoff=0, relay_failures=0)
        assert outbox.db.execute('SELECT count(*) FROM inbox_ingested').fetchone()[0] == 3
        assert spool.db.execute('SELECT count(*) FROM receipts').fetchone()[0] == 3
        assert len(outbox.rows()) == 6
    finally:
        outbox.close()
        spool.close()


def test_refused_envelopes_back_off_and_do_not_starve_older_valid_reply(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'MAX_BATCH', 2)

    class InboundKeyer(FakeKeyer):
        def decode(self, raw, recipient):
            assert recipient == C
            return t.strict_json(t.strict_json(raw)['content'].encode())

    class InboxRelay(FakeRelay):
        def fetch(self, url, *, since):
            return envelopes

    p, keyer, sink = policy(), InboundKeyer(), Sink()
    routes = m.Routes(t.canonical(announcements()), p, keyer)
    bad = [event(1059, 'c' * 64, [['p', C]], 'not-json',
                 NOW - timedelta(seconds=seconds)) for seconds in (1, 2)]
    rumor = event(tags=[['p', C], ['e', p.prompts[0].event_id]])
    del rumor['sig']
    valid = event(1059, 'c' * 64, [['p', C]], t.canonical(rumor).decode(),
                  NOW - timedelta(seconds=3))
    envelopes = bad + [valid]
    private = tmp_path / 'private'
    spool, outbox = t.Spool(private), m.Outbox(private)
    try:
        first = m.Delivery(p, routes, spool, outbox, keyer, InboxRelay(), sink).poll_replies(NOW)
        assert first == dict(accepted=1, retryable=0, withheld=1, deferred=1,
                             refusal_backoff=0, relay_failures=0)
        assert outbox.db.execute('SELECT count(*) FROM inbox_refused').fetchone()[0] == 1
        assert outbox.db.execute('SELECT count(*) FROM inbox_ingested').fetchone()[0] == 1
    finally:
        outbox.close()
        spool.close()

    spool, outbox = t.Spool(private), m.Outbox(private)
    try:
        second = m.Delivery(p, routes, spool, outbox, keyer, InboxRelay(), sink).poll_replies(NOW)
        assert second == dict(accepted=0, retryable=0, withheld=1, deferred=1,
                              refusal_backoff=1, relay_failures=0)
        assert outbox.db.execute('SELECT count(*) FROM inbox_refused').fetchone()[0] == 2
        assert outbox.db.execute('SELECT count(*) FROM inbox_ingested').fetchone()[0] == 1
        assert len(sink.stores) == 1
    finally:
        outbox.close()
        spool.close()


def test_new_invalid_id_burst_cannot_hide_oldest_valid_reply(tmp_path):
    class InboundKeyer(FakeKeyer):
        def decode(self, raw, recipient):
            assert recipient == C
            return t.strict_json(t.strict_json(raw)['content'].encode())

    class InboxRelay(FakeRelay):
        def fetch(self, url, *, since):
            return envelopes

    p, keyer, sink = policy(), InboundKeyer(), Sink()
    routes = m.Routes(t.canonical(announcements()), p, keyer)
    bad = [event(1059, 'c' * 64, [['p', C]], 'not-json',
                 NOW - timedelta(seconds=seconds)) for seconds in range(1, 21)]
    rumor = event(tags=[['p', C], ['e', p.prompts[0].event_id]])
    del rumor['sig']
    valid = event(1059, 'c' * 64, [['p', C]], t.canonical(rumor).decode(),
                  NOW - timedelta(seconds=21))
    envelopes = bad + [valid]  # Real relay.fetch returns newest first.
    private = tmp_path / 'private'
    spool, outbox = t.Spool(private), m.Outbox(private)
    try:
        result = m.Delivery(p, routes, spool, outbox, keyer, InboxRelay(), sink).poll_replies(NOW)
        assert result == dict(accepted=1, retryable=0, withheld=15, deferred=5,
                              refusal_backoff=0, relay_failures=0)
        assert outbox.ingress_recorded(valid)
        assert len(sink.stores) == 1
    finally:
        outbox.close()
        spool.close()


def test_noisy_first_relay_cannot_starve_second_reviewed_route(tmp_path):
    class InboundKeyer(FakeKeyer):
        def decode(self, raw, recipient):
            assert recipient == C
            return t.strict_json(t.strict_json(raw)['content'].encode())

    class InboxRelay(FakeRelay):
        def fetch(self, url, *, since):
            return bad if url == 'wss://relay.example' else [valid]

    p, keyer, sink = policy(), InboundKeyer(), Sink()
    route_list = announcements()
    route_list['announcements'][0] = event(10050, C,
        [['relay', 'wss://relay.example'], ['relay', 'wss://second.example']], '',
        datetime(2020, 1, 1, tzinfo=timezone.utc))
    routes = m.Routes(t.canonical(route_list), p, keyer)
    bad = [event(1059, 'c' * 64, [['p', C]], 'not-json',
                 NOW - timedelta(seconds=seconds)) for seconds in range(1, 21)]
    rumor = event(tags=[['p', C], ['e', p.prompts[0].event_id]])
    del rumor['sig']
    valid = event(1059, 'c' * 64, [['p', C]], t.canonical(rumor).decode(),
                  NOW - timedelta(seconds=21))
    spool, outbox = t.Spool(tmp_path / 'private'), m.Outbox(tmp_path / 'private')
    try:
        result = m.Delivery(p, routes, spool, outbox, keyer, InboxRelay(), sink).poll_replies(NOW)
        assert result == dict(accepted=1, retryable=0, withheld=15, deferred=5,
                              refusal_backoff=0, relay_failures=0)
        assert outbox.ingress_recorded(valid)
        assert len(sink.stores) == 1
    finally:
        outbox.close()
        spool.close()


def test_refusal_backoff_is_bounded_retryable_and_quota_limited(tmp_path, monkeypatch):
    outbox = m.Outbox(tmp_path / 'private')
    first = event(1059, 'c' * 64, [['p', C]], 'bad-one')
    second = event(1059, 'c' * 64, [['p', C]], 'bad-two')
    try:
        now = int(NOW.timestamp())
        outbox.record_refusal(first, now)
        assert outbox.refusal_deferred(first, now + 299)
        assert not outbox.refusal_deferred(first, now + 300)
        outbox.record_refusal(first, now + 300)
        assert outbox.refusal_deferred(first, now + 899)
        assert not outbox.refusal_deferred(first, now + 900)
        monkeypatch.setattr(m, 'MAX_ROWS', 1)
        with pytest.raises(t.Refused, match='refusal quota'):
            outbox.record_refusal(second, now)
        assert not outbox.ingress_recorded(first)
        outbox.record_ingress(first)
        assert outbox.ingress_recorded(first)
        assert outbox.db.execute('SELECT count(*) FROM inbox_refused').fetchone()[0] == 0
    finally:
        outbox.close()


def test_refusal_status_is_aggregate_and_tracks_due_retry(tmp_path):
    outbox = m.Outbox(tmp_path / 'private')
    first = event(1059, 'c' * 64, [['p', C]], 'bad-one')
    second = event(1059, 'c' * 64, [['p', C]], 'bad-two')
    now = int(NOW.timestamp())
    try:
        assert outbox.refusal_status(now) == dict(pending=0, due=0, next_retry_at=None)
        outbox.record_refusal(first, now)
        outbox.record_refusal(second, now + 60)
        status = outbox.refusal_status(now + 299)
        assert status == dict(pending=2, due=0,
                              next_retry_at=datetime.fromtimestamp(now + 300, timezone.utc).isoformat())
        assert first['id'] not in str(status) and second['id'] not in str(status)
        assert outbox.refusal_status(now + 300) == dict(
            pending=2, due=1,
            next_retry_at=datetime.fromtimestamp(now + 360, timezone.utc).isoformat())
        assert outbox.refusal_status(now + 360) == dict(pending=2, due=2, next_retry_at=None)
        outbox.record_ingress(first)
        assert outbox.refusal_status(now + 360) == dict(pending=1, due=1, next_retry_at=None)
    finally:
        outbox.close()


def test_poll_replies_does_not_skip_retryable_ingress(tmp_path):
    class InboundKeyer(FakeKeyer):
        def decode(self, raw, recipient):
            return t.strict_json(t.strict_json(raw)['content'].encode())
    class InboxRelay(FakeRelay):
        def fetch(self, url, *, since):
            return [envelope]

    p, keyer, sink = policy(), InboundKeyer(), Sink()
    routes = m.Routes(t.canonical(announcements()), p, keyer)
    rumor = event(tags=[['p', C], ['e', p.prompts[0].event_id]])
    del rumor['sig']
    envelope = event(1059, 'c' * 64, [['p', C]], t.canonical(rumor).decode())
    spool, outbox = t.Spool(tmp_path / 'private'), m.Outbox(tmp_path / 'private')
    try:
        delivery = m.Delivery(p, routes, spool, outbox, keyer, InboxRelay(), sink)
        sink.fail = True
        assert delivery.poll_replies(NOW)['retryable'] == 1
        assert outbox.db.execute('SELECT count(*) FROM inbox_ingested').fetchone()[0] == 0
        sink.fail = False
        assert delivery.poll_replies(NOW)['accepted'] == 1
        assert outbox.db.execute('SELECT count(*) FROM inbox_ingested').fetchone()[0] == 1
        assert len(sink.stores) == 1
    finally:
        outbox.close()
        spool.close()


def test_poll_cli_remains_release_gated(capsys):
    assert m.POLL_RELEASE_READY is False
    assert m.main(['--poll-replies']) == 2
    assert 'not release-qualified' in capsys.readouterr().err


def test_recover_pending_receipt_after_journal_failure(delivery):
    d = delivery
    d.sink.fail = True
    with pytest.raises(t.Retryable): d.receive(reply(d), NOW)
    d.sink.fail = False
    assert d.recover_acks(NOW + timedelta(seconds=30)) == dict(retryable=0, withheld=0, deferred=0)
    assert len(d.outbox.rows()) == 2
    assert d.spool.db.execute('SELECT first_received_at FROM receipts').fetchone()[0] == NOW.isoformat()


def test_revoked_recovery_does_not_abort_other_work(delivery):
    d = delivery
    d.sink.fail = True
    with pytest.raises(t.Retryable): d.receive(reply(d), NOW)
    d.policy = t.Policy(C, frozenset(), ())
    assert d.recover_acks(NOW)['withheld'] == 1
    assert d.outbox.rows() == []


def test_expired_entries_do_not_exhaust_delivery_budget(delivery, monkeypatch):
    d = delivery
    d.queue_prompts(NOW)
    d.receive(reply(d), NOW)
    monkeypatch.setattr(m, 'MAX_BATCH', 2)
    # The two expired prompt copies precede the two valid acknowledgement copies.
    result = d.flush(NOW + timedelta(hours=1))
    assert result['withheld'] == 2
    assert result['relay_acceptances'] == 2 and result['deferred'] == 0


def test_route_removal_is_obeyed_for_pending_delivery(delivery):
    d = delivery
    d.queue_prompts(NOW)
    d.routes.routes = {C: ('wss://new-relay.example',), O: ('wss://new-relay.example',)}
    assert d.flush(NOW)['relay_acceptances'] == 2
    assert {url for url, _ in d.relay.sent} == {'wss://new-relay.example'}


def test_arbitrary_receipt_cannot_be_turned_into_success_ack(delivery):
    d = delivery
    receipt = d.receive(reply(d), NOW)
    altered = dict(receipt, status='anything')
    with pytest.raises(t.Refused, match='committed'):
        m.acknowledgement(d.spool.get(receipt['rumor_id']), altered, C)


def test_keyer_missing_identity_does_not_fall_back(tmp_path, monkeypatch):
    f = tmp_path / 'nak'
    f.write_bytes(b'never execute')
    f.chmod(0o755)
    monkeypatch.delenv('NOSTR_SECRET_KEY', raising=False)
    def forbidden(*a, **kw): pytest.fail('must not execute default-key path')
    k = m.Keyer(f, sha256(f.read_bytes()).hexdigest(), runner=forbidden)
    with pytest.raises(t.Refused, match='explicit'):
        k.call(['event'], b'{}', identity=True)


def test_keyer_does_not_sign_arbitrary_event_kind(tmp_path):
    k = m.Keyer(tmp_path / 'nak', 'a' * 64)
    with pytest.raises(t.Refused, match='outside scope'):
        k.sign({'kind': 1, 'content': 'never publish this'}, C)


def test_local_test_transport_cannot_target_nonlocal_cleartext():
    with pytest.raises(t.Refused):
        m.relay_url('ws://other-host.example', local_test=True)


def test_future_relay_inventory_is_refused():
    data = announcements()
    data['announcements'][0] = event(10050, C, [['relay', 'wss://x']], '',
                                      datetime.now(timezone.utc) + timedelta(days=1))
    with pytest.raises(t.Refused, match='future'):
        m.Routes(t.canonical(data), policy(), FakeKeyer())
