"""Artifact/permission guards; signature verifier is explicitly a fixture double."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_routes', ROOT/'scripts/prepare-thermal-route-snapshot.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class Keyer:
    def __init__(self, events, *, fail_first=False, bad_signature=False):
        self.events, self.calls = events, []
        self.fail_first, self.bad_signature = fail_first, bad_signature
    def check_binary(self):
        pass
    def call(self, args):
        self.calls.append(args)
        if self.fail_first and len(self.calls) == 1:
            raise p.t.Retryable('fixture unavailable')
        return b'\n'.join(p.t.canonical(event) for event in self.events)
    def verify(self, event, kind):
        if self.bad_signature: raise p.t.Refused('fixture signature refusal')
        return p.t.validate_event(event, kind=kind, signed=True)


@pytest.fixture
def events(monkeypatch):
    result = []
    for author in (p.COLLECTOR, p.OPERATOR):
        event = {'pubkey': author, 'created_at': int(time.time())-10, 'kind': 10050,
            'tags': [['relay', url] for url in p.RELAYS], 'content': '', 'sig': '0'*128}
        event['id'] = p.t.event_id(event)
        result.append(event)
    monkeypatch.setattr(p, 'APPROVED', {event['pubkey']: event['id'] for event in result})
    return result


def test_private_save_is_exact_non_actuating_and_never_overwrites(tmp_path, events):
    keyer = Keyer(events)
    path = tmp_path/'routes.json'
    result = p.prepare(path, keyer)
    assert result['status'] == 'saved' and result['identities'] == 2
    assert result['publication'] is result['signing_key_used'] is result['collector_activated'] is False
    assert path.stat().st_mode & 0o077 == 0
    original = path.read_bytes()
    with pytest.raises(p.t.Refused, match='overwritten'):
        p.prepare(path, keyer)
    assert path.read_bytes() == original and len(keyer.calls) == 1


def test_unavailable_relay_falls_back_without_changing_routes(events):
    keyer = Keyer(events, fail_first=True)
    result = p.prepare(keyer=keyer)
    assert result['status'] == 'verified' and result['source_relay'] == p.SOURCES[1]
    assert len(keyer.calls) == 2


@pytest.mark.parametrize('damage', ['missing', 'author', 'endpoint', 'signature'])
def test_unsupported_or_unverified_inventory_never_creates_file(tmp_path, events, damage):
    changed = deepcopy(events)
    if damage == 'missing': changed.pop()
    elif damage == 'author': changed[0]['pubkey'] = '1'*64
    elif damage == 'endpoint': changed[0]['tags'][0] = ['relay', 'wss://unapproved.invalid']
    keyer = Keyer(changed, bad_signature=damage == 'signature')
    with pytest.raises(p.t.Retryable, match='unavailable'):
        p.prepare(tmp_path/'routes.json', keyer)
    assert list(tmp_path.iterdir()) == []


def test_public_parent_refuses_before_network(tmp_path, events):
    public = tmp_path/'public'
    public.mkdir(mode=0o755)
    keyer = Keyer(events)
    with pytest.raises(ValueError, match='private'):
        p.prepare(public/'routes.json', keyer)
    assert not keyer.calls and list(public.iterdir()) == []
