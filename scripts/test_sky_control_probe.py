"""No hardware: guards and synthetic native-input contracts for sky recovery."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

import sky_control_probe as probe


def baseline(script='fixture'):
    return {'uid': probe.UID, 'editable': True, 'name': 'fixture', 'conditions': [],
            'status': {'status': 'IDLE', 'statusDetail': 'NONE'},
            'triggers': [{'type': kind, 'configuration': dict(fields)}
                         for kind, fields in probe.TRIGGERS],
            'actions': [{'type': 'script.ScriptAction',
                         'configuration': {'type': 'application/javascript', 'script': script}}]}


def test_exact_live_and_canonical_action_required(monkeypatch):
    monkeypatch.setattr(probe, 'ACTION_SHA', sha256(b'fixture').hexdigest())
    rule = baseline()
    assert probe.control_payload(rule, b'fixture') == {
        key: value for key, value in rule.items() if key not in ('editable', 'status')}
    with pytest.raises(RuntimeError):
        probe.control_payload(rule, b'other')


def test_durable_consumer_requires_explicit_revision_and_exact_canonical_source():
    source = (Path(__file__).resolve().parents[1]
              / 'openhab/rules/southoutlet-cycle-current.js').read_bytes()
    rule = baseline(source.decode())
    assert sha256(source).hexdigest() == probe.DURABLE_ACTION_SHA
    assert probe.control_payload(rule, source, consumer_revision='durable-recovery') == {
        key: value for key, value in rule.items() if key not in ('editable', 'status')}
    # The original release adapter's default stays pinned to its old baseline.
    with pytest.raises(RuntimeError):
        probe.control_payload(rule, source)
    with pytest.raises(RuntimeError):
        probe.control_payload(rule, source + b'\n', consumer_revision='durable-recovery')
    rule['actions'][0]['configuration']['script'] += '\n'
    with pytest.raises(RuntimeError):
        probe.control_payload(rule, source, consumer_revision='durable-recovery')


@pytest.mark.parametrize('revision', ['', None, True, 'latest', '0'*64])
def test_unreviewed_consumer_revision_refused(revision):
    with pytest.raises(RuntimeError, match='consumer revision'):
        probe.control_payload(baseline(), b'fixture', consumer_revision=revision)


@pytest.mark.parametrize('damage', ['uid', 'provider', 'trigger', 'action', 'condition', 'status'])
@pytest.mark.parametrize('revision', ['original', 'durable-recovery'])
def test_control_drift_refused(monkeypatch, damage, revision):
    monkeypatch.setattr(probe, 'ACTION_SHA', sha256(b'fixture').hexdigest())
    monkeypatch.setattr(probe, 'DURABLE_ACTION_SHA', sha256(b'fixture').hexdigest())
    rule = baseline()
    if damage == 'uid': rule['uid'] = 'another'
    elif damage == 'provider': rule['editable'] = False
    elif damage == 'trigger': rule['triggers'] = []
    elif damage == 'action': rule['actions'][0]['configuration']['script'] = 'changed'
    elif damage == 'condition': rule['conditions'] = [{'type': 'unexpected'}]
    else: rule['status'] = {'status': 'UNINITIALIZED', 'statusDetail': 'HANDLER_MISSING_ERROR'}
    with pytest.raises(RuntimeError):
        probe.control_payload(rule, b'fixture', consumer_revision=revision)


def test_synthetic_receipts_explicitly_distinguish_fresh_and_expired():
    at = datetime(2026, 10, 3, 22, tzinfo=timezone.utc)
    fresh = probe.soc_receipt(at, expired=False)
    expired = probe.soc_receipt(at, expired=True)
    assert fresh['validUntil'] > int(at.timestamp() * 1000)
    assert expired['validUntil'] <= int(at.timestamp() * 1000)
    assert fresh['validUntil'] == min(fresh['observedAt'], fresh['scaleObservedAt']) + 120000
    assert set(fresh) == {'version', 'streamEpoch', 'recordedAt', 'status', 'reason',
                          'observedAt', 'scaleObservedAt', 'validUntil', 'soc'}


@pytest.mark.parametrize('name', probe.PUMPS)
def test_transient_on_commands_cannot_hide_behind_final_off_state(name):
    probe.require_no_on_commands("[ItemCommandEvent] - Item 'irrelevant' received command ON")
    probe.require_no_on_commands(f"[ItemCommandEvent] - Item '{name}' received command OFF")
    with pytest.raises(RuntimeError):
        probe.require_no_on_commands(f"[ItemCommandEvent] - Item '{name}' received command ON")


def test_output_contract_requires_specific_refusal_and_both_pumps_off():
    states = {name: 'OFF' for name in probe.PUMPS}
    states['SouthOutlet_AutoStatus'] = 'reason=invalid_soc_evidence,voltage=53.60'
    assert probe.refusal_matches(states, 'invalid_soc_evidence')
    assert not probe.refusal_matches(states, 'invalid_voltage')
    states[probe.PUMPS[0]] = 'ON'
    assert not probe.refusal_matches(states, 'invalid_soc_evidence')


def test_datetime_fixture_accepts_same_instant_not_another_time():
    assert probe.fixture_state_matches('SouthOutlet_LastCycleStart',
        '2026-10-03T16:00:00.000-0600', '2026-10-03T22:00:00+00:00')
    assert not probe.fixture_state_matches('SouthOutlet_LastCycleStart',
        '2026-10-03T16:01:00.000-0600', '2026-10-03T22:00:00+00:00')
    assert not probe.fixture_state_matches('SouthOutlet_LastCycleStart', 'NULL', 'bad')
    assert not probe.fixture_state_matches('BMS_SOC', '99', '100')
