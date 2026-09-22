#!/usr/bin/env python3
"""Attended encrypted thermal delivery. No timer, controls, or automatic activation.

Use --check-keyer first. Sending requires an explicit policy, reviewed signed
NIP-17 relay announcements, and private local state. Relay OK means accepted by
a relay, never read by the operator. Credentials are read only from environment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import sys
import time
from urllib.parse import urlsplit

import thermal_confirmation as t

DEFAULT_NAK = Path('/home/sat/.local/bin/nak')
DEFAULT_SHA256 = 'ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e'
MAX_ROWS = 4096
MAX_BATCH = 16


def require(condition, reason):
    if not condition:
        raise t.Refused(reason)


def collector_public_key(value: str) -> str:
    """Normalize CLI input only; signed events and policy files stay strict hex.

    NIP-19 npub uses BIP-173 Bech32 (not Bech32m), with a 32-byte payload.
    Validate its checksum, case and zero padding before using the public key.
    Never echo rejected input: someone may accidentally paste a private key.
    """
    reason = 'collector must be a 64-character hex public key or a valid npub'
    require(isinstance(value, str) and len(value) in {63, 64} and value.isascii(), reason)
    normalized = value.lower()
    if t.HEX64.fullmatch(normalized):
        return normalized
    require(len(value) == 63 and normalized.startswith('npub1')
            and (value == normalized or value == value.upper()), reason)
    alphabet = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    words = [alphabet.find(char) for char in normalized[5:]]
    require(all(word >= 0 for word in words), reason)
    hrp = 'npub'
    expanded = [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]
    generators = (0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)
    checksum = 1
    for word in expanded + words:
        top = checksum >> 25
        checksum = ((checksum & 0x1ffffff) << 5) ^ word
        for bit, generator in enumerate(generators):
            if (top >> bit) & 1:
                checksum ^= generator
    require(checksum == 1, reason)
    # A bare npub is exactly 52 data symbols: 256 key bits and 4 zero pad bits.
    payload = 0
    for word in words[:-6]:
        payload = (payload << 5) | word
    require(payload & 0x0f == 0, reason)
    return t.identifier((payload >> 4).to_bytes(32, 'big').hex())


def rumor_fields(event):
    return {k: v for k, v in event.items() if k != 'sig'}


class Keyer(t.NakDecoder):
    """Pinned nak signer/encryptor; plaintext travels on stdin, never argv."""
    def check_binary(self):
        require(self.executable.is_absolute(), 'nak path must be absolute')
        info = self.executable.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid in {0, os.getuid()}
                and not info.st_mode & 0o022 and bool(info.st_mode & 0o111)
                and 0 < info.st_size <= 128 * 1024 * 1024,
                'nak ownership or executable permissions are unsafe')
        with self.executable.open('rb') as stream:
            digest = sha256()
            size = 0
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(block)
                require(size <= 128 * 1024 * 1024, 'nak exceeds size bound')
                digest.update(block)
        require(digest.hexdigest() == self.digest, 'nak executable hash mismatch')

    def call(self, args, payload=b'', *, identity=False):
        self.check_binary()
        env = {k: v for k, v in os.environ.items()
               if k in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'XDG_CONFIG_HOME'}}
        if identity:
            require(bool(os.environ.get('NOSTR_SECRET_KEY')), 'explicit keyer configuration required')
            env['NOSTR_SECRET_KEY'] = os.environ['NOSTR_SECRET_KEY']
            if os.environ.get('NOSTR_CLIENT_KEY'):
                env['NOSTR_CLIENT_KEY'] = os.environ['NOSTR_CLIENT_KEY']
        return self.runner([str(self.executable), *args], payload, env)

    def verify(self, event, kind):
        t.validate_event(event, kind=kind, signed=True)
        self.call(['verify'], t.canonical(event) + b'\n')
        return event

    def sign(self, event, expected_author):
        require(event.get('kind') in {14, 22242}, 'signing kind outside scope')
        body = t.canonical(event)
        require(len(body) <= t.MAX_RUMOR, 'signing input exceeds bound')
        signed = t.strict_json(self.call(['event'], body + b'\n', identity=True))
        self.verify(signed, event['kind'])
        require(signed['pubkey'] == t.identifier(expected_author), 'keyer identity mismatch')
        require(all(signed.get(k) == v for k, v in event.items()
                    if k not in {'id', 'sig', 'pubkey'}), 'keyer changed signed fields')
        return signed

    def wrap(self, rumor, recipient):
        t.validate_event(rumor, kind=14, signed=False)
        payload = t.canonical(rumor_fields(rumor))
        require(len(payload) <= t.MAX_RUMOR, 'message exceeds bound')
        args = ['gift', 'wrap', '--use-our-identity-key', '--use-their-identity-key',
                '-p', t.identifier(recipient)]
        wrapped = t.strict_json(self.call(args, payload + b'\n', identity=True))
        self.verify(wrapped, 1059)
        require(t.tag_value(wrapped, 'p') == recipient, 'wrapped recipient mismatch')
        return wrapped

    def check_identity(self, collector):
        t.identifier(collector)
        event = {'created_at': int(time.time()), 'kind': 14, 'tags': [['p', collector]],
                 'content': 'Earthship keyer self-check ' + secrets.token_hex(16)}
        signed = self.sign(event, collector)
        rumor = rumor_fields(signed)
        wrapped = self.wrap(rumor, collector)
        decoded = self.decode(t.canonical(wrapped), collector)
        require(rumor_fields(decoded) == rumor, 'keyer self-roundtrip mismatch')
        return {'version': 1, 'status': 'passed', 'scope': 'configured-keyer-self-roundtrip',
                'signing_verified': True, 'encryption_verified': True,
                'decryption_verified': True,
                'bunker_verified': os.environ.get('NOSTR_SECRET_KEY', '').startswith('bunker://'),
                'nak_sha256': self.digest, 'journal_writes': 0,
                'message_published': False, 'relay_delivery_verified': False,
                'production_ready': False}


def relay_url(value, *, local_test=False):
    require(isinstance(value, str) and 0 < len(value) <= 512
            and all(ord(c) > 32 for c in value), 'invalid relay URL')
    try:
        parsed = urlsplit(value)
        port = parsed.port
        require(parsed.hostname is not None and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment and (port is None or port > 0),
                'invalid relay URL')
        require(parsed.scheme == 'wss' or (local_test and parsed.scheme == 'ws'
                and parsed.hostname in {'127.0.0.1', '::1'}), 'relay requires TLS')
    except ValueError as error:
        raise t.Refused('invalid relay URL') from error
    return value


class Routes:
    """Reviewed local snapshot of signed kind-10050 recipient relay lists."""
    def __init__(self, raw, policy, keyer, *, local_test=False):
        obj = t.strict_json(raw)
        require(isinstance(obj, dict) and set(obj) == {'version', 'announcements'}
                and type(obj['version']) is int and obj['version'] == 1
                and isinstance(obj['announcements'], list), 'invalid relay inventory')
        expected = policy.operators | {policy.recipient}
        require(len(obj['announcements']) == len(expected), 'relay inventory must cover each identity once')
        self.routes = {}
        for event in obj['announcements']:
            keyer.verify(event, 10050)
            author = event['pubkey']
            require(author in expected and author not in self.routes, 'unexpected relay-list author')
            require(event['created_at'] <= int(time.time()) + 60, 'future relay announcement')
            urls = [relay_url(tag[1], local_test=local_test)
                    for tag in event['tags'] if tag[0] == 'relay' and len(tag) == 2]
            require(1 <= len(urls) <= 3 and len(set(urls)) == len(urls)
                    and all(tag[0] != 'relay' or len(tag) == 2 for tag in event['tags']),
                    'relay list requires one to three unique endpoints')
            self.routes[author] = tuple(urls)

    def for_recipient(self, pubkey):
        require(pubkey in self.routes, 'recipient relay list is not approved')
        return self.routes[pubkey]


class Relay:
    """Bounded NIP-01 publication; only a matching boolean-true OK is success."""
    def __init__(self, keyer, collector, *, auth=False, connect=None, local_test=False):
        self.keyer, self.collector, self.auth = keyer, collector, auth
        self.connect = connect
        self.local_test = local_test

    def publish(self, url, event):
        relay_url(url, local_test=self.local_test)
        t.validate_event(event, kind=1059, signed=True)
        connect = self.connect
        if connect is None:
            from websockets.sync.client import connect
        try:
            with connect(url, open_timeout=10, close_timeout=2, max_size=t.MAX_INPUT,
                         max_queue=8, compression=None, proxy=None) as ws:
                deadline = time.monotonic() + 45
                auth_id = None
                challenged = False
                ws.send(t.canonical(['EVENT', event]).decode())
                for _ in range(32):
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise t.Retryable('relay acceptance timed out')
                    raw = ws.recv(timeout=left)
                    require(isinstance(raw, str), 'relay requires JSON text frames')
                    message = t.strict_json(raw.encode())
                    require(isinstance(message, list) and message and isinstance(message[0], str),
                            'malformed relay message')
                    if message[0] == 'AUTH':
                        require(self.auth and not challenged and len(message) == 2
                                and isinstance(message[1], str) and 0 < len(message[1]) <= 512,
                                'relay authentication requires explicit approval or exceeded bound')
                        challenged = True
                        signed = self.keyer.sign({'kind': 22242, 'created_at': int(time.time()),
                            'tags': [['relay', url], ['challenge', message[1]]], 'content': ''},
                            self.collector)
                        auth_id = signed['id']
                        ws.send(t.canonical(['AUTH', signed]).decode())
                    elif message[0] == 'OK':
                        require(len(message) == 4 and isinstance(message[1], str)
                                and type(message[2]) is bool and isinstance(message[3], str),
                                'malformed relay acceptance')
                        if auth_id is not None and message[1] == auth_id:
                            require(message[2], 'relay authentication refused')
                            auth_id = None
                            ws.send(t.canonical(['EVENT', event]).decode())
                        elif message[1] == event['id']:
                            if message[2]:
                                return
                            # NIP-42 relays may reject the first EVENT before AUTH finishes.
                            if self.auth and (auth_id is not None or not challenged) and message[3].startswith('auth-required:'):
                                continue
                            raise t.Retryable('relay did not accept encrypted event')
                raise t.Retryable('relay response budget exceeded')
        except (t.Refused, t.Retryable):
            raise
        except Exception as error:
            # No relay text, message plaintext, URLs or credentials in diagnostics.
            raise t.Retryable('relay delivery unavailable') from error


class Outbox:
    """Private SQLite delivery intents. Persist ciphertext BEFORE publishing it."""
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and not stat.S_IMODE(info.st_mode) & 0o077, 'outbox directory must be private')
        path = directory / 'delivery.sqlite3'
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and not stat.S_IMODE(info.st_mode) & 0o077, 'outbox file must be private')
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        require(self.db.execute('PRAGMA user_version').fetchone()[0] in (0, 1), 'unknown outbox schema')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS delivery (
              intent TEXT NOT NULL, target TEXT NOT NULL, body TEXT NOT NULL,
              wrapped TEXT, accepted TEXT NOT NULL DEFAULT '[]',
              attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
              PRIMARY KEY(intent, target));
            PRAGMA user_version=1;
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def queue(self, intent, rumor, collector, operator):
        t.validate_event(rumor, kind=14, signed=False)
        require(rumor['pubkey'] == collector and t.tag_value(rumor, 'p') == operator,
                'outgoing message identity mismatch')
        require(collector != operator, 'outgoing operator must differ from collector')
        body = t.canonical(rumor_fields(rumor)).decode()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for target in (collector, operator):
                row = self.db.execute('SELECT body FROM delivery WHERE intent=? AND target=?',
                                      (intent, target)).fetchone()
                if row:
                    require(row['body'] == body, 'outgoing intent conflicts with original message')
                else:
                    require(self.db.execute('SELECT count(*) FROM delivery').fetchone()[0] < MAX_ROWS,
                            'outbox quota reached; reviewed retention required')
                    self.db.execute('INSERT INTO delivery(intent,target,body) VALUES (?,?,?)',
                                    (intent, target, body))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def rows(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM delivery ORDER BY rowid')]

    def ciphertext(self, row, keyer):
        if row['wrapped'] is None:
            event = keyer.wrap(t.strict_json(row['body'].encode()), row['target'])
            encoded = t.canonical(event).decode()
            # Another process may have already prepared a different randomized wrap.
            with self.db:
                self.db.execute('UPDATE delivery SET wrapped=? WHERE intent=? AND target=? AND wrapped IS NULL',
                                (encoded, row['intent'], row['target']))
        saved = self.db.execute('SELECT wrapped FROM delivery WHERE intent=? AND target=?',
                                (row['intent'], row['target'])).fetchone()[0]
        event = t.strict_json(saved.encode())
        keyer.verify(event, 1059)
        require(t.tag_value(event, 'p') == row['target'], 'outbox envelope target changed')
        return event

    def accepted(self, row, url):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current = self.db.execute('SELECT accepted FROM delivery WHERE intent=? AND target=?',
                                     (row['intent'], row['target'])).fetchone()
            urls = set(json.loads(current[0])) | {url}
            self.db.execute('UPDATE delivery SET accepted=?, attempts=0, next_attempt=0 WHERE intent=? AND target=?',
                            (json.dumps(sorted(urls)), row['intent'], row['target']))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def retry(self, row, now):
        attempts = row['attempts'] + 1
        delay = min(3600, 5 * 2 ** min(attempts, 10))
        with self.db:
            self.db.execute('UPDATE delivery SET attempts=?,next_attempt=? WHERE intent=? AND target=?',
                            (attempts, now + delay, row['intent'], row['target']))


def acknowledgement(row, receipt, collector):
    require(receipt['rumor_id'] == row['rumor_id'] and row['acknowledgement'] == t.canonical(receipt).decode(),
            'acknowledgement is not a committed ingress receipt')
    event = {'pubkey': collector, 'kind': 14,
             'created_at': int(t.aware(row['first_received_at']).timestamp()),
             'tags': [['p', row['operator']], ['e', row['rumor_id']]],
             'content': 'THERMAL RECEIPT v1\n' + t.canonical(receipt).decode()}
    event['id'] = t.event_id(event)
    return event


class Delivery:
    def __init__(self, policy, routes, spool, outbox, keyer, relay, sink):
        self.policy, self.routes, self.spool = policy, routes, spool
        self.outbox, self.keyer, self.relay, self.sink = outbox, keyer, relay, sink

    def queue_prompts(self, now):
        for prompt in self.policy.prompts:
            if prompt.issued_at <= now <= prompt.expires_at:
                self.outbox.queue('prompt:' + prompt.event_id, t.prompt_event(prompt, self.policy.recipient),
                                  self.policy.recipient, prompt.operator)

    def receive(self, raw, now=None):
        receipt = t.ingest(raw, self.policy, self.spool, self.keyer, self.sink, now=now)
        row = self.spool.get(receipt['rumor_id'])
        self.outbox.queue('ack:' + receipt['rumor_id'], acknowledgement(row, receipt, self.policy.recipient),
                          self.policy.recipient, row['operator'])
        return receipt

    def recover_acks(self, now=None):
        # Recover even if the process died after journal commit but before the
        # local receipt or outbox commit. Replaying uses the preserved arrival.
        result = dict(retryable=0, withheld=0, deferred=0)
        attempted = 0
        for row in list(self.spool.db.execute('SELECT rumor_id FROM receipts')):
            intent = 'ack:' + row['rumor_id']
            if self.outbox.db.execute('SELECT count(*) FROM delivery WHERE intent=?', (intent,)).fetchone()[0] == 2:
                continue
            if attempted >= MAX_BATCH:
                result['deferred'] += 1
                continue
            attempted += 1
            try:
                self.receive(self.spool.get(row['rumor_id'])['original_wrap'], now)
            except t.Refused:
                attempted -= 1
                result['withheld'] += 1
            except t.Retryable:
                result['retryable'] += 1
        return result

    def authorize(self, row, now):
        body = t.strict_json(row['body'].encode())
        t.validate_event(body, kind=14, signed=False)
        operator = t.tag_value(body, 'p')
        require(operator in self.policy.operators and body['pubkey'] == self.policy.recipient
                and row['target'] in {operator, self.policy.recipient}, 'outgoing authority was revoked')
        purpose, identity = row['intent'].split(':', 1)
        if purpose == 'prompt':
            prompt = next((p for p in self.policy.prompts if p.event_id == identity), None)
            require(prompt is not None and prompt.issued_at <= now <= prompt.expires_at,
                    'outgoing prompt expired or was removed')
            require(body == t.prompt_event(prompt, self.policy.recipient), 'outgoing prompt changed')
        else:
            require(purpose == 'ack', 'unknown outgoing intent')
            original = self.spool.get(identity)
            require(original is not None, 'original confirmation receipt missing')
            # Re-authenticate and repeat exact PostgreSQL readback before EVERY delivery.
            receipt = t.ingest(original['original_wrap'], self.policy, self.spool,
                               self.keyer, self.sink, now=now)
            require(body == acknowledgement(self.spool.get(identity), receipt, self.policy.recipient),
                    'outgoing acknowledgement changed')
        return body

    def flush(self, now=None):
        fixed_now = now
        now = t.aware(now or datetime.now(timezone.utc))
        deadline = time.monotonic() + 90
        counts = {'relay_acceptances': 0, 'retryable': 0, 'withheld': 0, 'deferred': 0}
        attempted = 0
        for row in self.outbox.rows():
            now = t.aware(fixed_now or datetime.now(timezone.utc))
            routes = self.routes.for_recipient(row['target']) if row['target'] in self.routes.routes else ()
            remaining = set(routes) - set(json.loads(row['accepted']))
            if not remaining:
                if not routes:
                    counts['withheld'] += 1
                continue
            if row['next_attempt'] > now.timestamp() or attempted >= MAX_BATCH or time.monotonic() >= deadline:
                counts['deferred'] += 1
                continue
            attempted += 1
            try:
                self.authorize(row, now)
                event = self.outbox.ciphertext(row, self.keyer)
                for url in sorted(remaining):
                    self.authorize(row, t.aware(fixed_now or datetime.now(timezone.utc)))
                    self.relay.publish(url, event)
                    self.outbox.accepted(row, url)
                    counts['relay_acceptances'] += 1
            except t.Refused:
                attempted -= 1  # Expired/revoked entries must not starve newer active messages.
                counts['withheld'] += 1
            except t.Retryable:
                counts['retryable'] += 1
                self.outbox.retry(row, now.timestamp())
        return counts


def read_private(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and not stat.S_IMODE(info.st_mode) & 0o077, 'configuration file must be private')
    with path.open('rb') as stream:
        return stream.read(t.MAX_INPUT + 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-keyer', action='store_true')
    mode.add_argument('--send-prompts', action='store_true')
    mode.add_argument('--process-reply', action='store_true')
    mode.add_argument('--flush', action='store_true')
    parser.add_argument('--nak', type=Path, default=DEFAULT_NAK)
    parser.add_argument('--nak-sha256', default=DEFAULT_SHA256)
    parser.add_argument('--collector', help='expected collector public key (64-character hex or npub) for --check-keyer')
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--routes', type=Path, help='reviewed signed kind-10050 JSON inventory')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--event-file', type=Path)
    parser.add_argument('--relay-auth', action='store_true', help='allow identity disclosure to approved relays via NIP-42')
    args = parser.parse_args(argv)
    spool = outbox = None
    try:
        keyer = Keyer(args.nak, args.nak_sha256)
        if args.check_keyer:
            collector = args.collector
            if collector is None and args.policy is not None:
                collector = t.Policy.load(read_private(args.policy)).recipient
            require(collector is not None, '--check-keyer requires --collector or --policy')
            collector = collector_public_key(collector)
            print(t.canonical(keyer.check_identity(collector)).decode())
            return 0
        require(all(x is not None for x in (args.policy, args.routes, args.state_dir)),
                'sending requires policy, routes and private state directory')
        policy = t.Policy.load(read_private(args.policy))
        routes = Routes(read_private(args.routes), policy, keyer)
        # No production journal write or relay publication until signer identity is verified.
        keyer.check_identity(policy.recipient)
        spool = t.Spool(args.state_dir)
        outbox = Outbox(args.state_dir)
        delivery = Delivery(policy, routes, spool, outbox, keyer,
                            Relay(keyer, policy.recipient, auth=args.relay_auth), t.JournalSink())
        if args.send_prompts:
            delivery.queue_prompts(datetime.now(timezone.utc))
        if args.process_reply:
            require(args.event_file is not None, '--process-reply requires --event-file')
            delivery.receive(read_private(args.event_file))
        recovery = delivery.recover_acks()
        result = delivery.flush()
        for name, value in recovery.items():
            result[name] += value
        result.update(version=1, operator_read_verified=False, production_ready=False)
        print(t.canonical(result).decode())
        return 3 if result['retryable'] or result['deferred'] else (2 if result['withheld'] else 0)
    except t.Refused as error:
        print('thermal messaging refused: ' + str(error), file=sys.stderr)
        return 2
    except (t.Retryable, OSError, sqlite3.Error, ImportError, ValueError, KeyError):
        print('thermal messaging incomplete; retained state requires retry or repair', file=sys.stderr)
        return 3
    finally:
        if outbox is not None:
            outbox.close()
        if spool is not None:
            spool.close()


if __name__ == '__main__':
    raise SystemExit(main())
