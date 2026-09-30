"""Locked source-to-outbox integration; fake keyer is not identity evidence."""
from datetime import timedelta
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import pre_dusk_notification as notification
from pre_dusk_notification_worker import run
from thermal_messaging import Outbox
from thermal_state_backup import state_lock
import thermal_confirmation as t
from test_pre_dusk_notification import Keyer, Routes, Relay, NOW, SENDER, OPERATOR
from test_pre_dusk_notification_source import history_fixture, DAY


class CheckedKeyer(Keyer):
    def __init__(self, fail=False):
        super().__init__()
        self.checked = []
        self.fail = fail

    def check_identity(self, identity):
        self.checked.append(identity)
        if self.fail:
            raise t.Refused('configured identity unavailable')


def invoke(path, get, connect, keyer, relay, **changes):
    args = dict(day=DAY, state_dir=path, routes=Routes(), keyer=keyer, relay=relay,
                sender=SENDER, operator=OPERATOR, now=NOW + timedelta(seconds=1))
    args.update(changes)
    return run(get, connect, **args)


def test_default_off_refuses_before_state_io_keyer_or_history(tmp_path):
    _, gets, connections, get, connect = history_fixture()
    keyer, relay = CheckedKeyer(), Relay()
    path = tmp_path / 'private'
    with pytest.raises(t.Refused, match='release is off'):
        invoke(path, get, connect, keyer, relay)
    assert not path.exists()
    assert gets == connections == keyer.checked == relay.sent == []


def test_overlapping_worker_refuses_before_history_or_signer(tmp_path, monkeypatch):
    monkeypatch.setattr(notification, 'RELEASE_READY', True)
    _, gets, connections, get, connect = history_fixture()
    keyer, relay = CheckedKeyer(), Relay()
    path = tmp_path / 'private'
    with state_lock(path):
        with pytest.raises(ValueError, match='busy'):
            invoke(path, get, connect, keyer, relay)
    assert gets == connections == keyer.checked == relay.sent == []
    assert not (path / 'delivery.sqlite3').exists()


def test_non_low_forecast_skips_signer_and_delivery_database(tmp_path, monkeypatch):
    monkeypatch.setattr(notification, 'RELEASE_READY', True)
    _, _, _, get, connect = history_fixture(soc=99)
    keyer, relay = CheckedKeyer(), Relay()
    path = tmp_path / 'private'
    assert invoke(path, get, connect, keyer, relay) == {
        'status': 'not_eligible', 'relay_acceptances': 0,
        'retryable': 0, 'deferred': 0, 'operator_read_verified': False}
    assert keyer.checked == relay.sent == []
    assert not (path / 'delivery.sqlite3').exists()


def test_signer_failure_does_not_create_an_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(notification, 'RELEASE_READY', True)
    _, _, _, get, connect = history_fixture()
    path, keyer, relay = tmp_path / 'private', CheckedKeyer(fail=True), Relay()
    with pytest.raises(t.Refused):
        invoke(path, get, connect, keyer, relay)
    assert keyer.checked == [SENDER] and relay.sent == []
    assert not (path / 'delivery.sqlite3').exists()


def test_worker_restart_retains_exact_ciphertexts_and_rereads_original_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(notification, 'RELEASE_READY', True)
    _, gets, connections, get, connect = history_fixture()
    path, keyer, relay = tmp_path / 'private', CheckedKeyer(), Relay(ambiguous=True)
    assert invoke(path, get, connect, keyer, relay)['retryable'] == 2
    first_events = [event for _, event in relay.sent]
    relay.ambiguous = False
    result = invoke(path, get, connect, keyer, relay, now=NOW + timedelta(minutes=1))
    assert result == {'status': 'delivery_checked', 'relay_acceptances': 4,
                     'retryable': 0, 'deferred': 0, 'operator_read_verified': False}
    assert relay.sent[2][1] == first_events[0]
    assert relay.sent[4][1] == first_events[1]
    assert len(keyer.wraps) == 2
    assert len(gets) == 4 and len(connections) == 2
    assert all(connection.closed for connection in connections)
    box = Outbox(path)
    try:
        assert len(box.rows()) == 2
    finally:
        box.close()
    with state_lock(path):
        pass  # Worker released its lock on return.
