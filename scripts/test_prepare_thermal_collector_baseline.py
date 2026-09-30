"""Local private state only; public signature verification is a fixture double."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_baseline', ROOT/'scripts/prepare-thermal-collector-baseline.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
NOW = datetime(2026, 9, 29, 20, tzinfo=timezone.utc)


@pytest.fixture
def inputs(tmp_path):
    routes = tmp_path/'routes.json'
    events = []
    for pubkey in (p.C, p.O):
        event = {'pubkey': pubkey, 'kind': 10050, 'created_at': int(NOW.timestamp()),
            'content': '', 'tags': [['relay', 'wss://nos.lol']], 'sig': '0'*128}
        event['id'] = p.t.event_id(event)
        events.append(event)
    routes.write_bytes(p.t.canonical({'version': 1, 'announcements': events}))
    routes.chmod(0o600)
    return tmp_path/'state', tmp_path/'policy.proposed.json', routes


class Keyer:
    def verify(self, event, kind):
        return p.t.validate_event(event, kind=kind, signed=True)


def test_proposal_and_empty_baseline_create_no_labels_or_delivery(inputs):
    state, policy, routes = inputs
    result = p.prepare(state, policy, routes, window='open', skylight='closed', now=NOW, keyer=Keyer())
    assert result['status'] == 'inactive_proposal_prepared'
    assert result['operator_confirmation'] is result['publication'] is result['collector_activated'] is False
    assert result['policy_review_required'] is True and result['journal_writes'] == 0
    configured = p.t.Policy.load(policy.read_bytes())
    assert configured.version == 2 and configured.operators == frozenset({p.O})
    assert configured.recipient == p.C
    assert dict(configured.prompts[0].actions) == {'window': 'open', 'skylight': 'closed'}
    assert configured.prompts[0].event_id == result['question_id']
    assert state.stat().st_mode & 0o077 == policy.stat().st_mode & 0o077 == 0
    for name, tables in [('confirmations.sqlite3', ('receipts', 'terminal_prompts', 'corrections')),
                         ('delivery.sqlite3', ('delivery', 'inbox_ingested', 'inbox_refused'))]:
        with sqlite3.connect('file:'+str(state/name)+'?mode=ro', uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert all(db.execute('SELECT count(*) FROM '+table).fetchone() == (0,) for table in tables)
    raw = policy.read_bytes()
    with pytest.raises(p.t.Refused, match='new baseline'):
        p.prepare(state, policy, routes, window='closed', skylight='open', now=NOW, keyer=Keyer())
    assert policy.read_bytes() == raw


@pytest.mark.parametrize('damage', ['active_gate', 'sending_policy_name', 'signature', 'public_routes'])
def test_refusal_creates_no_state_or_proposal(inputs, monkeypatch, damage):
    state, policy, routes = inputs
    keyer = Keyer()
    if damage == 'active_gate': monkeypatch.setattr(p.m, 'POLL_RELEASE_READY', True)
    elif damage == 'sending_policy_name': policy = policy.with_name('policy.json')
    elif damage == 'public_routes': routes.chmod(0o644)
    else:
        def bad(*_): raise p.t.Refused('fixture signature refusal')
        keyer.verify = bad
    with pytest.raises((p.t.Refused, ValueError)):
        p.prepare(state, policy, routes, window='open', skylight='closed', now=NOW, keyer=keyer)
    assert not state.exists() and not policy.exists()
