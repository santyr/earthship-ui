"""Default-off Primal compatibility primitives, not a collector or live sender.

No automatic NIP17 downgrade. Keep the signed kind-4 ciphertext event intact;
its ID, not a manufactured kind-14 rumor ID, identifies an operator reply.
Outbound plaintext requires an explicitly pinned stdin-capable nak candidate.
"""
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
import re

import thermal_confirmation as t
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


def bind_reply(message, policy, *, now):
    require(isinstance(message, AuthenticatedMessage), 'authenticated NIP04 message required')
    now = t.aware(now)
    event = t.validate_event(t.strict_json(message.signed_event), kind=4, signed=True)
    require(event['pubkey'] in policy.operators, 'NIP04 operator is not authorized')
    require(t.tag_value(event, 'p') == policy.recipient, 'NIP04 collector mismatch')
    require(not any(tag[0] == 'e' for tag in event['tags']),
            'native NIP04 reply context awaits original question wire binding')
    match = re.fullmatch(r'(yes|not yet|skip) ([0-9a-f]{64})(?: ([^\n\r]+))?', message.plaintext)
    require(match is not None, 'explicit thermal question reference required')
    answer, prompt_id, when = match.groups()
    require(answer == 'yes' or when is None, 'time applies only to verified confirmations')
    prompt = next((p for p in policy.prompts if p.event_id == prompt_id), None)
    require(prompt is not None and prompt.operator == event['pubkey'],
            'NIP04 reply does not bind this operator question')
    require(t.prompt_event(prompt, policy.recipient)['id'] == prompt_id,
            'thermal question reference changed')
    signed_at = datetime.fromtimestamp(event['created_at'], t.UTC)
    require(signed_at <= now and now - signed_at <= t.MAX_AGE
            and prompt.issued_at <= signed_at <= prompt.expires_at
            and now <= prompt.expires_at, 'NIP04 reply is future-dated or expired')
    disposition, effective_at = t.resolve_reply(answer + (' ' + when if when else ''), signed_at)
    return BoundReply(message, prompt, disposition, effective_at, now)
