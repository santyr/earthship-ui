"""Default-off Primal compatibility primitives, not a collector or live sender.

No automatic NIP17 downgrade. Keep the signed kind-4 ciphertext event intact;
its ID, not a manufactured kind-14 rumor ID, identifies an operator reply.
Outbound plaintext requires an explicitly pinned stdin-capable nak candidate.
"""
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
import json
from pathlib import Path
import re
import sqlite3
import stat
import time

import thermal_confirmation as t
import thermal_messaging as m
from thermal_messaging import require

PRIMAL_RELEASE_READY = False


def require_release():
    require(PRIMAL_RELEASE_READY is True, 'Primal compatibility release gate is closed')


def _ciphertext(value):
    require(isinstance(value, str) and 0 < len(value) <= t.MAX_SEAL,
            'NIP04 ciphertext outside bound')
    parts = value.split('?iv=')
    require(len(parts) == 2, 'invalid NIP04 ciphertext')
    try:
        ciphertext = base64.b64decode(parts[0], validate=True)
        iv = base64.b64decode(parts[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise t.Refused('invalid NIP04 ciphertext') from exc
    require(len(iv) == 16 and len(ciphertext) > 0 and len(ciphertext) % 16 == 0,
            'invalid NIP04 ciphertext dimensions')


def _plaintext(value):
    try:
        require(isinstance(value, str), 'invalid NIP04 plaintext')
        encoded = value.encode('utf-8')
    except UnicodeError as exc:
        raise t.Refused('invalid NIP04 plaintext') from exc
    require(0 < len(encoded) <= t.MAX_RUMOR, 'NIP04 plaintext outside bound')
    return encoded


@dataclass(frozen=True)
class AuthenticatedMessage:
    signed_event: bytes
    plaintext: str

    @property
    def event_id(self):
        return t.strict_json(self.signed_event)['id']


class Nip04Codec:
    def __init__(self, keyer):
        self.keyer = keyer

    def encode(self, plaintext, *, author, recipient, created_at):
        payload = _plaintext(plaintext)
        author, recipient = t.identifier(author), t.identifier(recipient)
        require(type(created_at) is int and 0 <= created_at <= 253402300799,
                'invalid NIP04 creation time')
        # The stock pinned nak lacks --stdin and safely refuses. Never fall
        # back to positional plaintext or an implicit default identity.
        raw = self.keyer.call(['encrypt', '--nip04', '--stdin', '-p', recipient],
                              payload, identity=True)
        try:
            ciphertext = raw.decode('ascii').removesuffix('\n')
        except UnicodeError as exc:
            raise t.Refused('invalid NIP04 encryption response') from exc
        _ciphertext(ciphertext)
        fields = {'kind': 4, 'pubkey': author, 'created_at': created_at,
                  'tags': [['p', recipient]], 'content': ciphertext}
        event = t.strict_json(self.keyer.call(['event'], t.canonical(fields) + b'\n',
                                             identity=True))
        self.keyer.verify(event, 4)
        require(event['pubkey'] == author, 'NIP04 signer identity mismatch')
        require(all(event.get(key) == value for key, value in fields.items()),
                'NIP04 signer changed message fields')
        return event

    def decode(self, raw, *, recipient, authors):
        recipient = t.identifier(recipient)
        require(isinstance(authors, frozenset) and 1 <= len(authors) <= 16,
                'explicit NIP04 author allowlist required')
        for author in authors:
            t.identifier(author)
        event = t.validate_event(t.strict_json(raw), kind=4, signed=True)
        require(event['pubkey'] in authors, 'NIP04 author is not authorized')
        require(t.tag_value(event, 'p') == recipient, 'NIP04 recipient mismatch')
        self.keyer.verify(event, 4)  # Verify original ciphertext BEFORE decrypting.
        _ciphertext(event['content'])
        # Only ciphertext is positional; plaintext and credentials never are.
        clear = self.keyer.call(['decrypt', '--nip04', '--sender-pubkey',
                                 event['pubkey'], '--', event['content']], identity=True)
        try:
            plaintext = clear.decode('utf-8').removesuffix('\n')
        except UnicodeError as exc:
            raise t.Refused('invalid NIP04 decryption response') from exc
        _plaintext(plaintext)
        return AuthenticatedMessage(t.canonical(event), plaintext)


def question_text(policy, prompt_id):
    prompt = next((p for p in policy.prompts if p.event_id == prompt_id), None)
    require(prompt is not None, 'unknown thermal question reference')
    event = t.prompt_event(prompt, policy.recipient)
    require(event['id'] == prompt.event_id, 'thermal question reference changed')
    lines = []
    for line in event['content'].split('\n'):
        if line.startswith('Reply yes only'):
            break
        lines.append(line)
    lines.extend(['Confirm only states/actions you personally verified, not plans.',
                  'Question reference: ' + prompt.event_id,
                  'Reply: yes ' + prompt.event_id,
                  'Earlier verified time: yes ' + prompt.event_id
                  + ' HH:MM (America/Denver today) or an offset ISO timestamp.',
                  'Otherwise: not yet ' + prompt.event_id + ' or skip ' + prompt.event_id])
    return '\n'.join(lines)


@dataclass(frozen=True)
class BoundReply:
    message: AuthenticatedMessage
    prompt: t.Prompt
    disposition: str
    effective_at: datetime | None
    received_at: datetime

    @property
    def event_id(self):
        return self.message.event_id


def bind_reply(message, policy, *, now, question_wire_ids=None):
    require(isinstance(message, AuthenticatedMessage), 'authenticated NIP04 message required')
    now = t.aware(now)
    event = t.validate_event(t.strict_json(message.signed_event), kind=4, signed=True)
    require(event['pubkey'] in policy.operators, 'NIP04 operator is not authorized')
    require(t.tag_value(event, 'p') == policy.recipient, 'NIP04 collector mismatch')
    match = re.fullmatch(r'(yes|not yet|skip) ([0-9a-f]{64})(?: ([^\n\r]+))?', message.plaintext)
    require(match is not None, 'explicit thermal question reference required')
    answer, prompt_id, when = match.groups()
    require(answer == 'yes' or when is None, 'time applies only to verified confirmations')
    prompt = next((p for p in policy.prompts if p.event_id == prompt_id), None)
    require(prompt is not None and prompt.operator == event['pubkey'],
            'NIP04 reply does not bind this operator question')
    require(t.prompt_event(prompt, policy.recipient)['id'] == prompt_id,
            'thermal question reference changed')
    if any(tag[0] == 'e' for tag in event['tags']):
        require(isinstance(question_wire_ids, dict) and prompt_id in question_wire_ids,
                'native NIP04 reply context awaits original question wire binding')
        require(t.tag_value(event, 'e') == t.identifier(question_wire_ids[prompt_id]),
                'native NIP04 reply context differs from original question')
    signed_at = datetime.fromtimestamp(event['created_at'], t.UTC)
    require(signed_at <= now and now - signed_at <= t.MAX_AGE
            and prompt.issued_at <= signed_at <= prompt.expires_at
            and now <= prompt.expires_at, 'NIP04 reply is future-dated or expired')
    disposition, effective_at = t.resolve_reply(answer + (' ' + when if when else ''), signed_at)
    return BoundReply(message, prompt, disposition, effective_at, now)


def _prompt(policy, prompt_id):
    prompt = next((p for p in policy.prompts if p.event_id == prompt_id), None)
    require(prompt is not None and prompt.operator in policy.operators
            and t.prompt_event(prompt, policy.recipient)['id'] == prompt_id,
            'unknown or changed thermal question')
    return prompt


def _records(reply, prior):
    previous = {} if prior is None else {
        r['action']: r for r in t.strict_json(prior['records_json'].encode())}
    require(prior is None or set(previous) == dict(reply.prompt.actions).keys(),
            'correction action scope differs from original confirmation')
    if reply.disposition != 'confirmed':
        return []
    key = 'nostr:' + reply.event_id
    effective = t.iso(reply.effective_at)
    return [{'event_id': sha256(f'{key}:{action}:{state}:{effective}'.encode()).hexdigest()[:24],
             'idempotency_key': key, 'received_at': t.iso(reply.received_at),
             'effective_at': effective, 'action': action, 'state': state,
             'source': 'nostr_confirmed', 'confidence': 1.0, 'interval_id': None,
             'note': 'Nostr NIP-04 question ' + reply.prompt.event_id,
             'supersedes': previous[action]['event_id'] if prior else None}
            for action, state in reply.prompt.actions]


def receipt_for(row, version):
    records = t.strict_json(row['records_json'].encode())
    return {'version': version, 'transport': 'nip04',
            'status': 'stored' if records else 'no_action_recorded',
            'disposition': row['disposition'], 'event_id': row['event_id'],
            'question_id': row['prompt_id'], 'idempotency_key': 'nostr:' + row['event_id'],
            'first_received_at': row['first_received_at'],
            'original_event_sha256': row['digest'],
            'action_event_ids': [record['event_id'] for record in records]}


class PrimalLedger:
    """Private original-cipher ledger. No relay, journal or service side effects.

    Uses a distinct database; existing NIP17 delivery/confirmation tables are
    never opened or migrated. Low-level preparation does not release ingress.
    """
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        require(directory.is_absolute() and directory.resolve() == directory
                and stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700,
                'Primal ledger directory must be private and non-symlink')
        path = directory / 'primal.sqlite3'
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600,
                    'Primal ledger database must be private')
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        if self.db.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
            self.db.close()
            raise t.Refused('unsupported Primal ledger schema')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS questions (
              prompt_id TEXT PRIMARY KEY, prompt_json TEXT NOT NULL,
              collector TEXT NOT NULL, operator TEXT NOT NULL,
              event_id TEXT NOT NULL UNIQUE, original_event BLOB NOT NULL,
              digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts (
              event_id TEXT PRIMARY KEY, transport TEXT NOT NULL CHECK(transport='nip04'),
              prompt_id TEXT NOT NULL REFERENCES questions(prompt_id),
              prompt_json TEXT NOT NULL, collector TEXT NOT NULL, operator TEXT NOT NULL,
              digest TEXT NOT NULL, original_event BLOB NOT NULL,
              first_received_at TEXT NOT NULL, disposition TEXT NOT NULL,
              records_json TEXT NOT NULL, acknowledgement TEXT);
            CREATE TABLE IF NOT EXISTS terminal_prompts (
              prompt_id TEXT PRIMARY KEY REFERENCES questions(prompt_id),
              event_id TEXT NOT NULL UNIQUE REFERENCES receipts(event_id));
            CREATE TABLE IF NOT EXISTS corrections (
              original_id TEXT PRIMARY KEY REFERENCES receipts(event_id),
              correction_id TEXT NOT NULL UNIQUE REFERENCES receipts(event_id));
            PRAGMA user_version=1;
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def _verified_question(self, event, policy, prompt_id, codec):
        prompt = _prompt(policy, prompt_id)
        codec.keyer.verify(event, 4)
        require(event['pubkey'] == policy.recipient
                and t.tag_value(event, 'p') == prompt.operator
                and event['created_at'] == int(prompt.issued_at.timestamp())
                and event['tags'] == [['p', prompt.operator]],
                'outgoing Primal question identity mismatch')
        _ciphertext(event['content'])
        # The collector can check its own outbound ECDH cipher using the
        # operator public key. This does NOT use the operator signing key.
        clear = codec.keyer.call(['decrypt', '--nip04', '--sender-pubkey',
                                  prompt.operator, '--', event['content']], identity=True)
        require(clear == question_text(policy, prompt_id).encode() + b'\n',
                'outgoing Primal question content mismatch')
        return prompt

    def queue_question(self, event, policy, prompt_id, codec):
        prompt = self._verified_question(event, policy, prompt_id, codec)
        raw = t.canonical(event)
        fields = (prompt_id, t.canonical(prompt.snapshot()).decode(), policy.recipient,
                  prompt.operator, event['id'], raw, sha256(raw).hexdigest())
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT * FROM questions WHERE prompt_id=?',
                                  (prompt_id,)).fetchone()
            if old is not None:
                require(tuple(old) == fields, 'outgoing Primal question conflicts with original')
            else:
                require(self.db.execute('SELECT count(*) FROM questions').fetchone()[0] < 4096,
                        'Primal question quota reached; reviewed retention required')
                self.db.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?)', fields)
            self.db.commit()  # Must precede any publication; no publication occurs here.
        except BaseException:
            self.db.rollback()
            raise

    def question(self, policy, prompt_id, codec):
        prompt = _prompt(policy, prompt_id)
        row = self.db.execute('SELECT * FROM questions WHERE prompt_id=?', (prompt_id,)).fetchone()
        require(row is not None, 'original outgoing Primal question is missing')
        require(row['prompt_json'] == t.canonical(prompt.snapshot()).decode()
                and row['collector'] == policy.recipient and row['operator'] == prompt.operator
                and sha256(row['original_event']).hexdigest() == row['digest'],
                'stored outgoing Primal question changed')
        event = t.strict_json(row['original_event'])
        require(t.canonical(event) == row['original_event'] and event['id'] == row['event_id'],
                'stored outgoing Primal ciphertext identity changed')
        self._verified_question(event, policy, prompt_id, codec)
        return event

    def get(self, event_id):
        row = self.db.execute('SELECT * FROM receipts WHERE event_id=?',
                              (t.identifier(event_id),)).fetchone()
        return dict(row) if row is not None else None

    def _revalidate_prior(self, row, policy, codec, now, seen=()):
        require(row is not None and len(seen) < 32 and row['event_id'] not in seen,
                'stored Primal correction chain is missing, cyclic or outside bound')
        require(row['acknowledgement'] is not None and row['disposition'] == 'confirmed'
                and row['collector'] == policy.recipient and row['operator'] in policy.operators,
                'stored Primal correction target is not a committed authorized confirmation')
        ack = t.strict_json(row['acknowledgement'].encode())
        require(type(ack.get('version')) is int and ack['version'] in (1, 2),
                'stored Primal acknowledgement vocabulary changed')
        original = t.Policy.load(t.canonical({
            'version': ack['version'], 'recipient': policy.recipient,
            'operators': sorted(policy.operators),
            'prompts': [t.strict_json(row['prompt_json'].encode())]}))
        question = self.question(original, row['prompt_id'], codec)
        message = codec.decode(row['original_event'], recipient=original.recipient,
                               authors=original.operators)
        first = t.aware(row['first_received_at'])
        require(first <= now and message.event_id == row['event_id']
                and message.signed_event == row['original_event']
                and sha256(message.signed_event).hexdigest() == row['digest'],
                'stored Primal original ciphertext or timing changed')
        reply = bind_reply(message, original, now=first,
                           question_wire_ids={row['prompt_id']: question['id']})
        require(reply.prompt.event_id == row['prompt_id'], 'stored Primal question binding changed')
        prior = None
        if reply.prompt.correction_of:
            prior = self.get(reply.prompt.correction_of)
            self._revalidate_prior(prior, policy, codec, now, (*seen, row['event_id']))
        require(row['transport'] == 'nip04' and row['disposition'] == reply.disposition
                and row['records_json'] == t.canonical(_records(reply, prior)).decode()
                and row['acknowledgement'] == t.canonical(receipt_for(row, original.version)).decode(),
                'stored Primal correction target differs from authenticated original')

    def receive(self, raw, policy, codec, *, now):
        now = t.aware(now)  # Fixed before cryptographic processing and storage.
        message = codec.decode(raw, recipient=policy.recipient, authors=policy.operators)
        match = re.fullmatch(r'(yes|not yet|skip) ([0-9a-f]{64})(?: ([^\n\r]+))?',
                             message.plaintext)
        require(match is not None, 'explicit thermal question reference required')
        prompt_id = match[2]
        question = self.question(policy, prompt_id, codec)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.get(message.event_id)
            first = now if old is None else t.aware(old['first_received_at'])
            require(first <= now, 'stored receipt precedes current clock')
            reply = bind_reply(message, policy, now=first,
                               question_wire_ids={prompt_id: question['id']})
            prior = self.get(reply.prompt.correction_of) if reply.prompt.correction_of else None
            if reply.prompt.correction_of:
                require(prior is not None and prior['acknowledgement'] is not None
                        and prior['disposition'] == 'confirmed'
                        and prior['operator'] == reply.prompt.operator
                        and prior['collector'] == policy.recipient,
                        'correction requires a committed confirmation by the same operator')
                self._revalidate_prior(prior, policy, codec, now)
            records = _records(reply, prior)
            fields = {'event_id': message.event_id, 'transport': 'nip04',
                      'prompt_id': prompt_id, 'prompt_json': t.canonical(reply.prompt.snapshot()).decode(),
                      'collector': policy.recipient, 'operator': reply.prompt.operator,
                      'digest': sha256(message.signed_event).hexdigest(),
                      'original_event': message.signed_event, 'first_received_at': t.iso(first),
                      'disposition': reply.disposition, 'records_json': t.canonical(records).decode()}
            if old is not None:
                require(all(old[key] == value for key, value in fields.items()),
                        'stored Primal receipt differs from authenticated original')
            else:
                require(not self.db.execute('SELECT 1 FROM terminal_prompts WHERE prompt_id=?',
                                            (prompt_id,)).fetchone(),
                        'question already has a terminal reply; use an explicit correction')
                if prior is not None and reply.disposition == 'confirmed':
                    require(not self.db.execute('SELECT 1 FROM corrections WHERE original_id=?',
                                                (reply.prompt.correction_of,)).fetchone(),
                            'correct the latest confirmation, not a superseded ancestor')
                require(self.db.execute('SELECT count(*) FROM receipts').fetchone()[0] < 4096,
                        'Primal receipt quota reached; reviewed retention required')
                self.db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)',
                                tuple(fields.values()))
                if reply.disposition in {'confirmed', 'skipped'}:
                    self.db.execute('INSERT INTO terminal_prompts VALUES (?,?)',
                                    (prompt_id, message.event_id))
                if prior is not None and reply.disposition == 'confirmed':
                    self.db.execute('INSERT INTO corrections VALUES (?,?)',
                                    (reply.prompt.correction_of, message.event_id))
            self.db.commit()  # Before the external journal write, even on recovery.
            return self.get(message.event_id)
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise t.Refused('Primal receipt identity or terminal question conflict') from exc
        except BaseException:
            self.db.rollback()
            raise

    def acknowledge(self, row, receipt):
        encoded = t.canonical(receipt).decode()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            current = self.get(row['event_id'])
            require(current is not None
                    and all(current[key] == value for key, value in row.items()
                            if key != 'acknowledgement'),
                    'Primal receipt changed before acknowledgement')
            require(current['acknowledgement'] in (None, encoded),
                    'stored Primal acknowledgement conflicts with receipt')
            self.db.execute('UPDATE receipts SET acknowledgement=? WHERE event_id=?',
                            (encoded, row['event_id']))
            self.db.commit()
            return receipt
        except BaseException:
            self.db.rollback()
            raise


def ingest_primal(raw, policy, ledger, codec, sink, *, now=None):
    """Gated original-cipher ingress. No acknowledgement publication or polling."""
    require_release()  # Refuse before touching any dependency in production.
    now = t.aware(now or datetime.now(timezone.utc))
    require(policy.version in (1, 2), 'unsupported Primal policy vocabulary')
    if policy.version == 2:
        sink.require_v2_storage()  # Also guards skips/not-yet before any receipt.
    row = ledger.receive(raw, policy, codec, now=now)
    records = t.strict_json(row['records_json'].encode())
    if row['disposition'] == 'confirmed':
        # Existing append/readback path is idempotent. Payload is the actual
        # signed kind-4 cipher, not a manufactured cleartext rumor.
        sink.store(records, row['original_event'], vocabulary_version=policy.version)
    return ledger.acknowledge(row, receipt_for(row, policy.version))


class PrimalRelay(m.Relay):
    """Explicit gated kind-4 transport; NIP17 Relay defaults remain unchanged."""
    def __init__(self, keyer, collector, operators, **kwargs):
        collector = t.identifier(collector)
        require(isinstance(operators, frozenset) and 1 <= len(operators) <= 16
                and collector not in operators, 'explicit Primal relay operator allowlist required')
        for operator in operators:
            t.identifier(operator)
        self.operators = operators
        super().__init__(keyer, collector, **kwargs)

    def _outgoing_event(self, event):
        require_release()
        self.keyer.verify(event, 4)
        require(event['pubkey'] == self.collector
                and t.tag_value(event, 'p') in self.operators,
                'outgoing Primal relay identity mismatch')
        _ciphertext(event['content'])
        return event


    def _inbox_filter(self, since, until):
        require_release()
        return {'kinds': [4], 'authors': sorted(self.operators), '#p': [self.collector],
                'since': since, 'until': until, 'limit': m.MAX_INBOX_EVENTS}

    def _incoming_event(self, event, since, until):
        require_release()
        event = self.keyer.verify(event, 4)
        require(event['pubkey'] in self.operators
                and t.tag_value(event, 'p') == self.collector,
                'incoming Primal relay identity mismatch')
        require(since <= event['created_at'] <= until,
                'Primal relay event outside requested window')
        _ciphertext(event['content'])
        return event


class PrimalOutbox(m.Outbox):
    """Separate cipher-only delivery file; reuse bounded retry/ingress bookkeeping."""
    def __init__(self, directory):
        super().__init__(directory, filename='primal-delivery.sqlite3')

    def queue(self, *args, **kwargs):
        raise t.Refused('Primal delivery requires original signed kind4 ciphertext')

    def queue_cipher(self, purpose, reference, event, codec, collector, operator):
        require(purpose in {'prompt', 'ack'}, 'unknown Primal delivery intent')
        reference = t.identifier(reference)
        collector, operator = t.identifier(collector), t.identifier(operator)
        require(collector != operator, 'Primal collector and operator must differ')
        codec.keyer.verify(event, 4)
        require(event['pubkey'] == collector and event['tags'] == [['p', operator]],
                'Primal delivery cipher identity mismatch')
        _ciphertext(event['content'])
        raw = t.canonical(event).decode()
        body = t.canonical({'transport': 'nip04', 'purpose': purpose, 'reference': reference,
                            'cipherSha256': sha256(raw.encode()).hexdigest()}).decode()
        intent = purpose + ':' + reference
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT body,wrapped FROM delivery WHERE intent=? AND target=?',
                                  (intent, operator)).fetchone()
            if old is not None:
                require(old['body'] == body and old['wrapped'] == raw,
                        'Primal outgoing intent conflicts with original cipher')
            else:
                require(self.db.execute('SELECT count(*) FROM delivery').fetchone()[0] < m.MAX_ROWS,
                        'Primal delivery quota reached; reviewed retention required')
                self.db.execute('INSERT INTO delivery(intent,target,body,wrapped) VALUES (?,?,?,?)',
                                (intent, operator, body, raw))
            self.db.commit()  # Cipher before publication; no plaintext at rest here.
        except BaseException:
            self.db.rollback()
            raise

    def ciphertext(self, row, keyer):
        require(isinstance(row['wrapped'], str), 'Primal original cipher is missing')
        meta = t.strict_json(row['body'].encode())
        require(set(meta) == {'transport', 'purpose', 'reference', 'cipherSha256'}
                and meta['transport'] == 'nip04' and meta['purpose'] in {'prompt', 'ack'}
                and row['intent'] == meta['purpose'] + ':' + t.identifier(meta['reference'])
                and sha256(row['wrapped'].encode()).hexdigest() == meta['cipherSha256'],
                'Primal delivery metadata changed')
        event = t.strict_json(row['wrapped'].encode())
        keyer.verify(event, 4)
        require(t.canonical(event).decode() == row['wrapped']
                and t.tag_value(event, 'p') == row['target'], 'Primal retained cipher scope changed')
        _ciphertext(event['content'])
        return event

    def for_intent(self, intent, operator):
        row = self.db.execute('SELECT * FROM delivery WHERE intent=? AND target=?',
                              (intent, operator)).fetchone()
        return dict(row) if row is not None else None


def acknowledgement_text(row, receipt):
    require(row['acknowledgement'] == t.canonical(receipt).decode()
            and receipt == receipt_for(row, receipt['version']),
            'Primal acknowledgement is not a committed receipt')
    return 'THERMAL STATE RECEIPT\n' + t.canonical(receipt).decode()


class PrimalDelivery:
    """Bounded explicitly selected transport. No CLI, daemon or automatic activation."""
    def __init__(self, policy, routes, ledger, outbox, codec, relay, sink):
        require_release()
        require(isinstance(routes, m.Routes)
                and set(routes.routes) == {policy.recipient, *policy.operators},
                'Primal delivery requires the exact signed route inventory')
        require(isinstance(relay, PrimalRelay) and relay.collector == policy.recipient
                and relay.operators == policy.operators, 'Primal relay authority mismatch')
        if policy.version == 2:
            sink.require_v2_storage()
        self.policy, self.routes, self.ledger = policy, routes, ledger
        self.outbox, self.codec, self.relay, self.sink = outbox, codec, relay, sink

    def queue_prompts(self, now):
        require_release()
        now = t.aware(now)
        if self.policy.version == 2:
            self.sink.require_v2_storage()
        for prompt in self.policy.prompts:
            if not prompt.issued_at <= now <= prompt.expires_at:
                continue
            exists = self.ledger.db.execute('SELECT 1 FROM questions WHERE prompt_id=?',
                                           (prompt.event_id,)).fetchone()
            if exists is None:
                event = self.codec.encode(question_text(self.policy, prompt.event_id),
                    author=self.policy.recipient, recipient=prompt.operator,
                    created_at=int(prompt.issued_at.timestamp()))
                self.ledger.queue_question(event, self.policy, prompt.event_id, self.codec)
            event = self.ledger.question(self.policy, prompt.event_id, self.codec)
            self.outbox.queue_cipher('prompt', prompt.event_id, event, self.codec,
                                      self.policy.recipient, prompt.operator)

    def _queue_ack(self, row, receipt):
        text = acknowledgement_text(row, receipt)
        existing = self.outbox.for_intent('ack:' + row['event_id'], row['operator'])
        if existing is not None:
            event = self.outbox.ciphertext(existing, self.codec.keyer)
        else:
            event = self.codec.encode(text, author=self.policy.recipient, recipient=row['operator'],
                                      created_at=int(t.aware(row['first_received_at']).timestamp()))
        self._verify_ack(event, row, receipt)
        self.outbox.queue_cipher('ack', row['event_id'], event, self.codec,
                                  self.policy.recipient, row['operator'])

    def _verify_ack(self, event, row, receipt):
        self.codec.keyer.verify(event, 4)
        require(event['pubkey'] == self.policy.recipient and event['tags'] == [['p', row['operator']]]
                and event['created_at'] == int(t.aware(row['first_received_at']).timestamp()),
                'Primal acknowledgement identity changed')
        clear = self.codec.keyer.call(['decrypt', '--nip04', '--sender-pubkey', row['operator'],
                                       '--', event['content']], identity=True)
        require(clear == acknowledgement_text(row, receipt).encode() + b'\n',
                'Primal acknowledgement cleartext changed')

    def receive(self, raw, now=None):
        require_release()
        receipt = ingest_primal(raw, self.policy, self.ledger, self.codec, self.sink, now=now)
        self._queue_ack(self.ledger.get(receipt['event_id']), receipt)
        return receipt

    def authorize(self, row, now):
        require_release()
        event = self.outbox.ciphertext(row, self.codec.keyer)
        require(event['pubkey'] == self.policy.recipient and row['target'] in self.policy.operators,
                'Primal outgoing authority was revoked')
        purpose, reference = row['intent'].split(':', 1)
        if purpose == 'prompt':
            prompt = _prompt(self.policy, reference)
            require(prompt.issued_at <= now <= prompt.expires_at, 'Primal question expired')
            if self.policy.version == 2:
                self.sink.require_v2_storage()
            require(event == self.ledger.question(self.policy, reference, self.codec),
                    'Primal outgoing question changed')
        else:
            require(purpose == 'ack', 'unknown Primal delivery purpose')
            original = self.ledger.get(reference)
            require(original is not None, 'Primal acknowledgement original is missing')
            # Reauthenticate and repeat exact journal readback before EVERY send.
            receipt = ingest_primal(original['original_event'], self.policy, self.ledger,
                                     self.codec, self.sink, now=now)
            self._verify_ack(event, self.ledger.get(reference), receipt)
        return event

    def flush(self, now=None):
        require_release()
        fixed_now = now
        deadline = time.monotonic() + 90
        counts = dict(relay_acceptances=0, retryable=0, withheld=0, deferred=0)
        attempted = 0
        for row in self.outbox.rows():
            current = t.aware(fixed_now or datetime.now(timezone.utc))
            routes = self.routes.for_recipient(row['target']) if row['target'] in self.routes.routes else ()
            pending = set(routes) - set(json.loads(row['accepted']))
            if not pending:
                if not routes: counts['withheld'] += 1
                continue
            if attempted >= m.MAX_BATCH or row['next_attempt'] > current.timestamp() or time.monotonic() >= deadline:
                counts['deferred'] += 1
                continue
            attempted += 1
            try:
                for url in sorted(pending):
                    event = self.authorize(row, t.aware(fixed_now or datetime.now(timezone.utc)))
                    self.relay.publish(url, event, deadline=deadline)
                    self.outbox.accepted(row, url)
                    counts['relay_acceptances'] += 1
            except t.Refused:
                # Retained expired/revoked evidence must not consume the send
                # budget forever and starve newer authorized messages.
                attempted -= 1
                counts['withheld'] += 1
            except t.Retryable:
                counts['retryable'] += 1
                self.outbox.retry(row, current.timestamp())
        return counts

    def recover_acks(self, now=None):
        require_release()
        counts = dict(retryable=0, withheld=0, deferred=0)
        existing = {row['intent'] for row in self.outbox.rows()}
        deadline, attempted = time.monotonic() + 90, 0
        for record in self.ledger.db.execute('SELECT event_id FROM receipts ORDER BY rowid').fetchall():
            if 'ack:' + record['event_id'] in existing:
                continue
            if attempted >= m.MAX_BATCH or time.monotonic() >= deadline:
                counts['deferred'] += 1
                continue
            attempted += 1
            try:
                self.receive(self.ledger.get(record['event_id'])['original_event'], now)
            except t.Refused:
                counts['withheld'] += 1
            except t.Retryable:
                counts['retryable'] += 1
        return counts

    def poll_replies(self, now=None):
        require_release()
        fixed_now = now
        current = t.aware(now or datetime.now(timezone.utc))
        active = [p for p in self.policy.prompts if p.issued_at <= current <= p.expires_at]
        counts = dict(accepted=0, retryable=0, withheld=0, deferred=0, relay_failures=0)
        if not active:
            return counts
        since = int(min(p.issued_at for p in active).timestamp())
        deadline = time.monotonic() + 90
        streams = []
        for url in self.routes.for_recipient(self.policy.recipient):
            if time.monotonic() >= deadline:
                counts['relay_failures'] += 1
                continue
            try:
                events = self.relay.fetch(url, since=since, deadline=deadline)
            except (t.Refused, t.Retryable):
                counts['relay_failures'] += 1
                continue
            streams.append(iter(m.balanced_inbox_order(events)))
        seen, attempted = set(), 0
        while streams:
            remaining = []
            for stream in streams:
                try:
                    event = next(stream)
                except StopIteration:
                    continue
                remaining.append(stream)
                if event['id'] in seen:
                    continue
                seen.add(event['id'])
                if self.outbox.ingress_recorded(event):
                    continue
                if (self.outbox.refusal_deferred(event, current.timestamp())
                        or attempted >= m.MAX_BATCH or time.monotonic() >= deadline):
                    counts['deferred'] += 1
                    continue
                attempted += 1
                try:
                    self.receive(t.canonical(event), fixed_now)
                except t.Refused:
                    self.outbox.record_refusal(event, current.timestamp())
                    counts['withheld'] += 1
                except t.Retryable:
                    counts['retryable'] += 1
                else:
                    self.outbox.record_ingress(event)
                    counts['accepted'] += 1
            streams = remaining
        return counts
