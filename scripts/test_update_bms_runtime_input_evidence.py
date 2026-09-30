"""Synthetic exact-delta/rollback tests; no production connection or writes."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('runtime_update',
    Path(__file__).with_name('update-bms-runtime-input-evidence.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def baseline(monkeypatch):
    monkeypatch.setattr(m, 'OLD_SHA', sha256(b'old synthetic source').hexdigest())
    monkeypatch.setattr(m, 'NEW_SHA', sha256(b'new synthetic source').hexdigest())
    return {'uid': m.UID, 'editable': True, 'name': 'collector', 'conditions': [],
        'triggers': json.loads(m.common.DEFINITION.read_text())['rule']['triggers'],
        'actions': [{'id': 'evidence', 'inputs': {}, 'type': 'script.ScriptAction',
                    'configuration': {'type': 'application/javascript', 'script': 'old synthetic source'}}]}


def test_plan_changes_only_action_source(monkeypatch):
    original = baseline(monkeypatch)
    expected = m.common.rule_body(original)
    expected['actions'][0]['configuration']['script'] = 'new synthetic source'
    assert m.plan(original, 'new synthetic source') == expected
    assert original['actions'][0]['configuration']['script'] == 'old synthetic source'


@pytest.mark.parametrize('mutation', [
    lambda row: row.update(uid='hex_southoutlet_cycle'),
    lambda row: row.update(editable=False),
    lambda row: row.update(triggers=[]),
    lambda row: row.update(conditions=[{'id': 'foreign'}]),
    lambda row: row['actions'][0]['configuration'].update(script='foreign source'),
])
def test_preimage_drift_refused(monkeypatch, mutation):
    row = baseline(monkeypatch); mutation(row)
    with pytest.raises(RuntimeError):
        m.plan(row, 'new synthetic source')


def transaction(monkeypatch, tmp_path, failure=None):
    raw = baseline(monkeypatch)
    original = m.common.rule_body(raw)
    desired = m.plan(raw, 'new synthetic source')
    state = {'rule': deepcopy(original)}
    writes = []
    monkeypatch.setattr(m, 'RELEASE_ENABLED', True)
    monkeypatch.setattr(m, 'save_backup', lambda *_: tmp_path)
    monkeypatch.setattr(m, 'inspect', lambda: (deepcopy(state['rule']), desired, 'guard'))
    monkeypatch.setattr(m, 'guard_digest', lambda: 'guard')
    monkeypatch.setattr(m, 'read_definition', lambda: deepcopy(state['rule']))
    monkeypatch.setattr(m, 'verify_ready', lambda expected: None)
    def put(body):
        writes.append(deepcopy(body)); state['rule'] = deepcopy(body)
        if len(writes) == 1 and failure:
            if failure == 'concurrent': state['rule']['name'] = 'foreign edit'
            raise OSError('ambiguous update')
    monkeypatch.setattr(m, 'put_definition', put)
    return original, desired, state, writes


def test_release_gate_blocks_before_backup_or_write(monkeypatch, tmp_path):
    original, desired, state, writes = transaction(monkeypatch, tmp_path)
    monkeypatch.setattr(m, 'RELEASE_ENABLED', False)
    monkeypatch.setattr(m, 'save_backup', lambda *_: pytest.fail('backup before gate'))
    with pytest.raises(RuntimeError, match='gate is off'):
        m.apply(original, desired, 'guard')
    assert writes == [] and state['rule'] == original


def test_success_is_definition_only_not_natural_qualification(monkeypatch, tmp_path):
    original, desired, state, writes = transaction(monkeypatch, tmp_path)
    assert m.apply(original, desired, 'guard')['status'] == 'definition_updated_natural_evidence_pending'
    assert writes == [desired] and state['rule'] == desired


def test_ambiguous_failure_rolls_back_exact_owned_definition(monkeypatch, tmp_path):
    original, desired, state, writes = transaction(monkeypatch, tmp_path, 'ambiguous')
    with pytest.raises(RuntimeError, match='rollback verified'):
        m.apply(original, desired, 'guard')
    assert writes == [desired, original] and state['rule'] == original


def test_failure_does_not_overwrite_concurrent_edit(monkeypatch, tmp_path):
    original, desired, state, writes = transaction(monkeypatch, tmp_path, 'concurrent')
    with pytest.raises(RuntimeError, match='rollback unverified'):
        m.apply(original, desired, 'guard')
    assert len(writes) == 1 and state['rule']['name'] == 'foreign edit'


def test_recheck_refuses_changed_baseline_before_write(monkeypatch, tmp_path):
    original, desired, state, writes = transaction(monkeypatch, tmp_path)
    state['rule']['name'] = 'foreign edit'
    with pytest.raises(RuntimeError, match='preimage changed'):
        m.apply(original, desired, 'guard')
    assert writes == []


def test_unrelated_configuration_drift_rolls_back_only_our_collector(monkeypatch, tmp_path):
    original, desired, state, writes = transaction(monkeypatch, tmp_path)
    monkeypatch.setattr(m, 'guard_digest', lambda: 'changed control definition')
    with pytest.raises(RuntimeError, match='rollback verified'):
        m.apply(original, desired, 'guard')
    assert writes == [desired, original]
    assert state['rule'] == original


def test_candidate_hash_drift_refused(monkeypatch):
    row = baseline(monkeypatch)
    with pytest.raises(RuntimeError, match='candidate source drift'):
        m.plan(row, 'unreviewed source')


def test_put_scope_cannot_target_a_control_rule(monkeypatch):
    monkeypatch.setattr(m.common, 'request', lambda *_: pytest.fail('foreign write'))
    with pytest.raises(RuntimeError, match='outside collector scope'):
        m.put_definition({'uid': 'hex_southoutlet_cycle'})


def test_private_backup_is_exclusive_and_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(m.common, 'PRIVATE_ROOT', tmp_path / 'private')
    directory = m.save_backup({'uid': m.UID}, 'guard')
    assert directory.stat().st_mode & 0o077 == 0
    path = directory / 'preimage.json'
    assert path.stat().st_mode & 0o077 == 0
    assert json.loads(path.read_text())['original'] == {'uid': m.UID}
