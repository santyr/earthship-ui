"""Real pinned nak, disposable keys; no household identities, relays or journal."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n

CKEY, OKEY = format(2, '064x'), format(1, '064x')
C = 'c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'
O = '79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def policy():
    return t.Policy.load(t.canonical({
        'version': 2, 'recipient': C, 'operators': [O], 'prompts': [{
            'operator': O, 'issued_at': (NOW - timedelta(minutes=5)).isoformat(),
            'expires_at': (NOW + timedelta(minutes=30)).isoformat(),
            'actions': {'window': 'open', 'skylight': 'closed'},
        }]}), assign_ids=True)


@pytest.fixture
def codec(monkeypatch, tmp_path):
    candidate = os.environ.get('EARTHSHIP_TEST_NAK')
    digest = os.environ.get('EARTHSHIP_TEST_NAK_SHA256')
    if not candidate or not digest:
        pytest.skip('explicit isolated stdin-capable nak qualification pin required')
    binary = Path(candidate)
    assert binary.is_absolute() and t.identifier(digest)
    assert binary.is_file() and sha256(binary.read_bytes()).hexdigest() == digest
    # No inherited household key, bunker, database, relay or proxy environment.
    for key in tuple(os.environ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PATH', os.defpath)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('LANG', 'C.UTF-8')
    monkeypatch.setenv('NOSTR_SECRET_KEY', CKEY)
    return n.Nip04Codec(m.Keyer(binary, digest))


def signed_reply(codec, monkeypatch, content, *, author=O, recipient=C, at=NOW):
    monkeypatch.setenv('NOSTR_SECRET_KEY', OKEY)
    event = codec.encode(content, author=author, recipient=recipient,
                         created_at=int(at.timestamp()))
    monkeypatch.setenv('NOSTR_SECRET_KEY', CKEY)
    return event


def test_real_nip04_roundtrip_preserves_signed_identity_and_multiline_plaintext(codec, monkeypatch):
    text = 'Synthetic qualification\nWindows: open\nSkylights: closed'
    event = codec.encode(text, author=C, recipient=O, created_at=int(NOW.timestamp()))
    assert event['kind'] == 4 and event['pubkey'] == C
    assert event['tags'] == [['p', O]]
    assert text not in t.canonical(event).decode()
    monkeypatch.setenv('NOSTR_SECRET_KEY', OKEY)
    decoded = codec.decode(t.canonical(event), recipient=O, authors=frozenset({C}))
    assert decoded.plaintext == text
    assert decoded.signed_event == t.canonical(event)
    assert decoded.event_id == event['id']
    assert event['id'] == t.event_id(event)


@pytest.mark.parametrize('mutation', ['signature', 'id', 'ciphertext', 'recipient', 'author', 'kind'])
def test_signed_event_tampering_or_scope_mismatch_is_rejected(codec, monkeypatch, mutation):
    event = signed_reply(codec, monkeypatch, 'yes ' + policy().prompts[0].event_id)
    bad = deepcopy(event)
    if mutation == 'signature':
        bad['sig'] = '0' * 128
    elif mutation == 'id':
        bad['id'] = '0' * 64
    elif mutation == 'ciphertext':
        bad['content'] = bad['content'][1:]
        bad['id'] = t.event_id(bad)  # Hash alone must not replace signature verification.
    elif mutation == 'recipient':
        bad['tags'] = [['p', O]]
        bad['id'] = t.event_id(bad)
    elif mutation == 'author':
        bad['pubkey'] = C
        bad['id'] = t.event_id(bad)
    else:
        bad['kind'] = 14
        bad['id'] = t.event_id(bad)
    with pytest.raises(t.Refused):
        codec.decode(t.canonical(bad), recipient=C, authors=frozenset({O}))


def test_valid_signature_with_bad_nip04_ciphertext_is_rejected_before_decrypt(codec, monkeypatch):
    # Use an actual valid signature; this tests ciphertext-format policy, not a
    # failure caused by invalid fixture crypto.
    monkeypatch.setenv('NOSTR_SECRET_KEY', OKEY)
    event = t.strict_json(codec.keyer.call(['event'], t.canonical({
        'kind': 4, 'created_at': int(NOW.timestamp()), 'tags': [['p', C]],
        'content': 'invalid?iv=invalid'}) + b'\n', identity=True))
    monkeypatch.setenv('NOSTR_SECRET_KEY', CKEY)
    with pytest.raises(t.Refused):
        codec.decode(t.canonical(event), recipient=C, authors=frozenset({O}))


def test_wrong_configured_signer_cannot_create_a_message_under_hex_identity(codec):
    with pytest.raises(t.Refused, match='identity'):
        codec.encode('synthetic', author=O, recipient=C, created_at=int(NOW.timestamp()))


@pytest.mark.parametrize('text', ['', 'x' * (t.MAX_RUMOR + 1), '\ud800'])
def test_invalid_or_oversized_plaintext_is_refused(codec, text):
    with pytest.raises(t.Refused):
        codec.encode(text, author=C, recipient=O, created_at=int(NOW.timestamp()))


def test_question_text_binds_exact_states_and_includes_explicit_reply_reference():
    p = policy()
    prompt = p.prompts[0]
    text = n.question_text(p, prompt.event_id)
    assert 'Windows: open' in text and 'Skylights: closed' in text
    assert f'Question reference: {prompt.event_id}' in text
    assert f'yes {prompt.event_id}' in text
    assert f'not yet {prompt.event_id}' in text
    assert f'skip {prompt.event_id}' in text
    assert 'personally verified' in text
    assert 'Reply yes only' not in text  # Old unreferenced instructions are removed.
    with pytest.raises(t.Refused):
        n.question_text(p, 'f' * 64)


@pytest.mark.parametrize('prefix,disposition', [('yes', 'confirmed'),
                                             ('not yet', 'not_yet'), ('skip', 'skipped')])
def test_bound_reply_retains_original_signed_event_and_explicit_question(codec, monkeypatch, prefix, disposition):
    p = policy()
    event = signed_reply(codec, monkeypatch, prefix + ' ' + p.prompts[0].event_id)
    decoded = codec.decode(t.canonical(event), recipient=C, authors=p.operators)
    reply = n.bind_reply(decoded, p, now=NOW + timedelta(seconds=1))
    assert reply.event_id == event['id']
    assert reply.message.signed_event == t.canonical(event)
    assert reply.prompt == p.prompts[0]
    assert reply.disposition == disposition
    assert reply.effective_at == (NOW if prefix == 'yes' else None)
    assert reply.received_at == NOW + timedelta(seconds=1)


def test_prior_verified_time_is_resolved_without_using_chat_as_truth(codec, monkeypatch):
    p = policy()
    event = signed_reply(codec, monkeypatch, f'yes {p.prompts[0].event_id} 07:30')
    message = codec.decode(t.canonical(event), recipient=C, authors=p.operators)
    reply = n.bind_reply(message, p, now=NOW)
    assert reply.effective_at == datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('content', ['yes', 'not yet', 'skip', 'Yes {id}',
    'yes ' + 'f' * 64, 'yes {id} tomorrow', 'yes {id}\n', 'yes  {id}',
    'yes {id} 2099-01-01T12:00:00+00:00', 'not yet {id} 07:30'])
def test_unbound_unknown_ambiguous_or_future_reply_cannot_select_a_question(codec, monkeypatch, content):
    p = policy()
    event = signed_reply(codec, monkeypatch, content.format(id=p.prompts[0].event_id))
    message = codec.decode(t.canonical(event), recipient=C, authors=p.operators)
    with pytest.raises(t.Refused):
        n.bind_reply(message, p, now=NOW)


@pytest.mark.parametrize('offset', [-1, 1801, 49 * 3600])
def test_reply_future_receipt_expiry_and_age_boundaries_are_enforced(codec, monkeypatch, offset):
    p = policy()
    event = signed_reply(codec, monkeypatch, 'yes ' + p.prompts[0].event_id)
    message = codec.decode(t.canonical(event), recipient=C, authors=p.operators)
    with pytest.raises(t.Refused):
        n.bind_reply(message, p, now=NOW + timedelta(seconds=offset))


def test_bound_reply_does_not_write_journal_or_release_default_off_gate(codec, monkeypatch):
    p = policy()
    event = signed_reply(codec, monkeypatch, 'yes ' + p.prompts[0].event_id)
    message = codec.decode(t.canonical(event), recipient=C, authors=p.operators)
    reply = n.bind_reply(message, p, now=NOW)
    assert reply.event_id == event['id']
    with pytest.raises(t.Refused, match='release'):
        n.require_release()


def test_subprocess_boundary_keeps_plaintext_and_credentials_out_of_argv(codec, monkeypatch):
    calls = []
    runner = codec.keyer.runner
    plaintext = 'Synthetic plaintext boundary qualification'
    monkeypatch.setenv('THERMAL_DATABASE_URL', 'test-only-database-secret')
    def traced(argv, payload, env):
        assert plaintext not in argv
        assert CKEY not in argv and OKEY not in argv
        assert 'THERMAL_DATABASE_URL' not in env
        calls.append((argv[1:], payload))
        return runner(argv, payload, env)
    codec.keyer.runner = traced
    event = codec.encode(plaintext, author=C, recipient=O, created_at=int(NOW.timestamp()))
    assert calls[0] == (['encrypt', '--nip04', '--stdin', '-p', O], plaintext.encode())
    monkeypatch.setenv('NOSTR_SECRET_KEY', OKEY)
    assert codec.decode(t.canonical(event), recipient=O, authors=frozenset({C})).plaintext == plaintext


def test_stdin_backport_rejects_mixed_empty_and_oversized_input(codec):
    for args, payload in [
        (['encrypt', '--nip04', '--stdin', '-p', O, '--', 'positional'], b'synthetic'),
        (['encrypt', '--stdin', '-p', O], b'synthetic'),
        (['encrypt', '--nip04', '--stdin', '-p', O], b''),
        (['encrypt', '--nip04', '--stdin', '-p', O], b'x' * 65537),
    ]:
        with pytest.raises(t.Refused):
            codec.keyer.call(args, payload, identity=True)


def test_old_nak_refuses_stdin_outbound_without_positional_fallback(monkeypatch, tmp_path):
    binary = m.DEFAULT_NAK
    if not binary.is_file() or sha256(binary.read_bytes()).hexdigest() != m.DEFAULT_SHA256:
        pytest.skip('original pinned host binary unavailable')
    for key in tuple(os.environ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PATH', os.defpath)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('NOSTR_SECRET_KEY', CKEY)
    old = n.Nip04Codec(m.Keyer(binary, m.DEFAULT_SHA256))
    with pytest.raises(t.Refused):
        old.encode('synthetic', author=C, recipient=O, created_at=int(NOW.timestamp()))


def test_native_reply_context_is_withheld_until_original_question_wire_id_is_bound(codec, monkeypatch):
    p = policy()
    event = signed_reply(codec, monkeypatch, 'yes ' + p.prompts[0].event_id)
    # Produce an actually signed event, but with native reply context that
    # cannot yet be tied to a preserved outgoing kind-4 question envelope.
    monkeypatch.setenv('NOSTR_SECRET_KEY', OKEY)
    event = t.strict_json(codec.keyer.call(['event'], t.canonical({
        **{key: value for key, value in event.items() if key not in {'sig', 'id'}},
        'tags': [['p', C], ['e', 'f' * 64]]}) + b'\n', identity=True))
    monkeypatch.setenv('NOSTR_SECRET_KEY', CKEY)
    decoded = codec.decode(t.canonical(event), recipient=C, authors=p.operators)
    with pytest.raises(t.Refused, match='context'):
        n.bind_reply(decoded, p, now=NOW)
