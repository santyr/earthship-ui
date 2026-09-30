"""Real private SQLite tests; fake wrapping/publishing is NOT crypto evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import pre_dusk_notification as n
import thermal_confirmation as t
from thermal_messaging import Outbox

SENDER, OPERATOR = 'b' * 64, 'a' * 64
NOW = datetime(2026, 9, 29, 23, 33, 23, tzinfo=timezone.utc)


def inputs(soc=40, drop=20):
    at = NOW - timedelta(seconds=20)
    ms = int(at.timestamp() * 1000)
    raw = json.dumps({'version': 1, 'streamEpoch': str(UUID(int=1)),
        'recordedAt': ms, 'status': 'valid', 'reason': 'ok', 'observedAt': ms,
        'scaleObservedAt': ms, 'validUntil': ms + 120000, 'soc': soc})
    issue = {'version': 1, 'basis': 'atomic_soc_pre_dusk_v1',
        'predictionDay': '2026-09-29', 'issuedAt': NOW.isoformat(),
        'sunsetAt': '2026-09-30T00:48:23+00:00',
        'morningIssuedAt': '2026-09-29T12:40:17+00:00',
        'socRecordedAt': at.isoformat(), 'socStreamEpoch': str(UUID(int=1)),
        'socEvidenceSha256': sha256(raw.encode()).hexdigest(),
        'socAtIssuePct': soc, 'overnightDropPct': drop,
        'overnightTroughSocPct': max(12, min(99, soc - drop))}
    return issue, raw, at.isoformat()


class Keyer:
    def __init__(self):
        self.wraps = []

    def wrap(self, rumor, target):
        event = {'kind': 1059, 'pubkey': str(len(self.wraps) + 1) * 64,
            'created_at': int(NOW.timestamp()), 'tags': [['p', target]],
            'content': t.canonical(rumor).decode()}
        event['id'] = t.event_id(event)
        event['sig'] = '0' * 128
        self.wraps.append(deepcopy(event))
        return event

    def verify(self, event, kind):
        t.validate_event(event, kind=kind, signed=True)


class Routes:
    def for_recipient(self, target):
        assert target in (SENDER, OPERATOR)
        return ('wss://one.example', 'wss://two.example')


class Relay:
    def __init__(self, ambiguous=False):
        self.sent = []
        self.ambiguous = ambiguous

    def publish(self, url, event):
        self.sent.append((url, deepcopy(event)))
        if self.ambiguous:
            raise t.Retryable('acceptance uncertain')


def test_default_off_never_queues_or_publishes(tmp_path):
    issue, raw, stored = inputs()
    box = Outbox(tmp_path / 'private')
    try:
        with pytest.raises(t.Refused, match='release is off'):
            n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        with pytest.raises(t.Refused, match='release is off'):
            n.flush(box, Routes(), Keyer(), Relay(), issue, raw, stored, NOW, SENDER, OPERATOR)
        assert box.rows() == []
    finally:
        box.close()


@pytest.mark.parametrize('soc,expected', [(49, True), (50, False), (51, False)])
def test_existing_strict_threshold_and_deterministic_identity(soc, expected):
    issue, raw, stored = inputs(soc=soc)
    first = n.notice(issue, raw, stored, NOW, SENDER, OPERATOR)
    second = n.notice(issue, raw, stored, NOW + timedelta(minutes=1), SENDER, OPERATOR)
    assert first == second
    assert (first is not None) == expected
    if first:
        t.validate_event(first['rumor'], kind=14, signed=False)
        assert 'Forecast only' in first['rumor']['content']


@pytest.mark.parametrize('change', [
    {'basis': 'morning'}, {'version': True}, {'overnightTroughSocPct': 19},
    {'overnightDropPct': float('nan')}, {'issuedAt': '2026-09-29T23:33:23'},
    {'predictionDay': '2026-09-28'}, {'socEvidenceSha256': '0' * 64},
    {'morningIssuedAt': NOW.isoformat()}, {'unexpected': 'value'},
])
def test_invalid_or_unbound_issue_is_refused(change):
    issue, raw, stored = inputs()
    issue.update(change)
    with pytest.raises(t.Refused):
        n.notice(issue, raw, stored, NOW, SENDER, OPERATOR)


def test_future_and_expired_issue_never_notifies():
    issue, raw, stored = inputs()
    for now in (NOW - timedelta(seconds=1), datetime(2026, 9, 30, 17, tzinfo=timezone.utc)):
        with pytest.raises(t.Refused):
            n.notice(issue, raw, stored, now, SENDER, OPERATOR)


def test_uncertain_publish_restart_reuses_exact_ciphertext(tmp_path, monkeypatch):
    monkeypatch.setattr(n, 'RELEASE_READY', True)
    issue, raw, stored = inputs()
    path = tmp_path / 'private'
    box, keyer, relay = Outbox(path), Keyer(), Relay(ambiguous=True)
    try:
        assert n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        assert n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        assert len(box.rows()) == 2
        result = n.flush(box, Routes(), keyer, relay, issue, raw, stored, NOW, SENDER, OPERATOR)
        assert result == {'relay_acceptances': 0, 'retryable': 2, 'deferred': 0}
        first = deepcopy(relay.sent)
        assert len(keyer.wraps) == 2
    finally:
        box.close()
    box = Outbox(path)
    try:
        relay.ambiguous = False
        result = n.flush(box, Routes(), keyer, relay, issue, raw, stored,
                         NOW + timedelta(minutes=1), SENDER, OPERATOR)
        assert result == {'relay_acceptances': 4, 'retryable': 0, 'deferred': 0}
        assert len(keyer.wraps) == 2
        assert relay.sent[2] == first[0]
        assert relay.sent[4] == first[1]
        sent = len(relay.sent)
        assert n.flush(box, Routes(), keyer, relay, issue, raw, stored,
                       NOW + timedelta(minutes=2), SENDER, OPERATOR)['relay_acceptances'] == 0
        assert len(relay.sent) == sent
    finally:
        box.close()


def test_conflicting_same_day_issue_cannot_replace_original(tmp_path, monkeypatch):
    monkeypatch.setattr(n, 'RELEASE_READY', True)
    box = Outbox(tmp_path / 'private')
    try:
        issue, raw, stored = inputs()
        n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        original = deepcopy(box.rows())
        changed, raw2, stored2 = inputs(soc=41)
        with pytest.raises(t.Refused, match='conflicts'):
            n.queue(box, changed, raw2, stored2, NOW, SENDER, OPERATOR)
        assert box.rows() == original
    finally:
        box.close()


def test_changed_provenance_with_same_display_value_is_a_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr(n, 'RELEASE_READY', True)
    box = Outbox(tmp_path / 'private')
    try:
        issue, raw, stored = inputs()
        n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        changed = {**issue, 'morningIssuedAt': '2026-09-29T12:41:17+00:00'}
        with pytest.raises(t.Refused, match='conflicts'):
            n.queue(box, changed, raw, stored, NOW, SENDER, OPERATOR)
    finally:
        box.close()


def test_partial_ack_retries_only_remaining_relays_and_honors_backoff(tmp_path, monkeypatch):
    monkeypatch.setattr(n, 'RELEASE_READY', True)
    box, keyer = Outbox(tmp_path / 'private'), Keyer()
    relay = Relay()
    original_publish = relay.publish

    def partial(url, event):
        original_publish(url, event)
        if url == 'wss://two.example':
            raise t.Retryable('acceptance uncertain')

    relay.publish = partial
    issue, raw, stored = inputs()
    try:
        n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        result = n.flush(box, Routes(), keyer, relay, issue, raw, stored, NOW, SENDER, OPERATOR)
        assert result == {'relay_acceptances': 2, 'retryable': 2, 'deferred': 0}
        before = len(relay.sent)
        assert n.flush(box, Routes(), keyer, relay, issue, raw, stored,
                       NOW + timedelta(seconds=1), SENDER, OPERATOR)['deferred'] == 2
        assert len(relay.sent) == before
        relay.publish = original_publish
        assert n.flush(box, Routes(), keyer, relay, issue, raw, stored,
                       NOW + timedelta(minutes=1), SENDER, OPERATOR)['relay_acceptances'] == 2
        assert all(url == 'wss://two.example' for url, _ in relay.sent[before:])
        assert len(keyer.wraps) == 2
    finally:
        box.close()


def test_mutated_outbox_or_expired_issue_never_reaches_relay(tmp_path, monkeypatch):
    monkeypatch.setattr(n, 'RELEASE_READY', True)
    issue, raw, stored = inputs()
    box, relay = Outbox(tmp_path / 'private'), Relay()
    try:
        n.queue(box, issue, raw, stored, NOW, SENDER, OPERATOR)
        with box.db:
            box.db.execute("UPDATE delivery SET body='{}' WHERE target=?", (OPERATOR,))
        with pytest.raises(t.Refused, match='issue changed'):
            n.flush(box, Routes(), Keyer(), relay, issue, raw, stored, NOW, SENDER, OPERATOR)
        assert relay.sent == []
        with pytest.raises(t.Refused):
            n.flush(box, Routes(), Keyer(), relay, issue, raw, stored,
                    datetime(2026, 9, 30, 17, tzinfo=timezone.utc), SENDER, OPERATOR)
        assert relay.sent == []
    finally:
        box.close()


def test_slow_signing_crossing_expiry_does_not_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(n, 'RELEASE_READY', True)
    issue, raw, stored = inputs()
    box, relay = Outbox(tmp_path / 'private'), Relay()
    elapsed = iter((0.0, 2.0))
    monkeypatch.setattr(n.time, 'monotonic', lambda: next(elapsed))
    before_expiry = datetime(2026, 9, 30, 16, 59, 59, tzinfo=timezone.utc)
    try:
        n.queue(box, issue, raw, stored, before_expiry, SENDER, OPERATOR)
        with pytest.raises(t.Refused):
            n.flush(box, Routes(), Keyer(), relay, issue, raw, stored,
                    before_expiry, SENDER, OPERATOR)
        assert relay.sent == []
    finally:
        box.close()
