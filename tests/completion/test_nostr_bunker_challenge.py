"""The attended signer check must fail closed before any public test note."""

import importlib.machinery
import importlib.util
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[2] / 'deploy/nostr-bunker/challenge-earthship-operator'


def module():
    loader = importlib.machinery.SourceFileLoader('earthship_bunker_challenge', str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    value = importlib.util.module_from_spec(spec)
    loader.exec_module(value)
    return value


def ready(monkeypatch, challenge):
    class Nak:
        def lstat(self):
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o755, st_uid=0)

        def read_bytes(self):
            return b'test pinned binary'

        def __str__(self):
            return '/test/nak'

    import hashlib
    monkeypatch.setattr(challenge, 'NAK', Nak())
    monkeypatch.setattr(challenge, 'NAK_SHA256', hashlib.sha256(b'test pinned binary').hexdigest())
    monkeypatch.setattr(challenge.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(challenge.sys, 'stderr', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(challenge.getpass, 'getpass', lambda _: 'test-client-secret')


def test_wrong_client_never_contacts_bunker_or_publishes(monkeypatch):
    challenge = module()
    ready(monkeypatch, challenge)
    calls = []

    def fake_call(args, **kwargs):
        calls.append(args)
        if args[0] == 'systemctl':
            return 'ActiveState=active\nSubState=running\nUnitFileState=enabled'
        return 'wrong-client-public-key'

    monkeypatch.setattr(challenge, 'call', fake_call)
    with pytest.raises(challenge.ChallengeError, match='allowlist'):
        challenge.main()
    assert len(calls) == 2
    assert not any('event' in args for args in calls)


def test_remote_signature_and_exact_relay_readback_required(monkeypatch, capsys):
    challenge = module()
    ready(monkeypatch, challenge)
    event = {'id': 'a' * 64, 'pubkey': challenge.OPERATOR, 'kind': 1,
             'content': 'placeholder'}
    calls = []

    def fake_call(args, **kwargs):
        calls.append(args)
        if args[0] == 'systemctl':
            return 'ActiveState=active\nSubState=running\nUnitFileState=enabled'
        if args[1:3] == ['key', 'public']:
            return challenge.OPERATOR if kwargs['env']['NOSTR_SECRET_KEY'].startswith('bunker://') else challenge.CLIENT
        if args[1] == 'verify':
            return ''
        if args[1] == 'event' and '--content' in args:
            event['content'] = args[args.index('--content') + 1]
            return json.dumps(event)
        if args[1] == 'event':
            return ''
        if args[1] == 'req':
            return json.dumps(event) if args[-1] == challenge.RELAYS[0] else ''
        raise AssertionError(args)

    monkeypatch.setattr(challenge, 'call', fake_call)
    challenge.main()
    assert 'read back on 1/3 relays' in capsys.readouterr().out
    assert sum(args[1] == 'event' and '--content' not in args for args in calls if args[0] != 'systemctl') == 3
    assert os.environ.get('NOSTR_SECRET_KEY') != 'test-client-secret'
