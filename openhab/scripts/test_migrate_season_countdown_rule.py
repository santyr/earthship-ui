"""No-network transaction checks for the season display-rule handoff."""

import importlib.util
from dataclasses import replace
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/migrate-season-countdown-rule.py'
spec = importlib.util.spec_from_file_location('season_rule_migration', SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

ORIGINAL = {
    'uid': migration.RULE, 'name': 'Update Days Until Next Season',
    'description': 'Updates the season countdown display', 'tags': [],
    'triggers': [{'type': 'core.ItemStateChangeTrigger',
                  'configuration': {'itemName': 'Sun_TimeLeft'}}],
    'conditions': [], 'actions': [], 'editable': True,
    'status': {'status': 'IDLE', 'statusDetail': 'NONE'},
}
@pytest.mark.parametrize('kind', ['season', 'sky', 'extrema', 'bitcoin', 'battery-icon'])
@pytest.mark.parametrize('install_fails', [False, True])
def test_handoff_never_leaves_two_providers_and_restores_managed_on_failure(
        monkeypatch, kind, install_fails):
    config = replace(migration.RULES[kind],
                     target=Path('/tmp/nonexistent-season-rule-test.js'))
    original = {**ORIGINAL, 'uid': config.uid,
                'triggers': [{'type': type_name, 'configuration': dict(fields)}
                             for type_name, fields in config.triggers]}
    file_rule = {**original, 'editable': False}
    expected_states = {name: 'held' for name in config.outputs}
    state = {'rule': original}
    calls = []
    monkeypatch.setattr(migration, 'backup', lambda original, config: Path('/tmp'))
    monkeypatch.setattr(migration, 'rule_or_none', lambda config: state['rule'])
    monkeypatch.setattr(migration, 'output_states',
                        lambda config: expected_states)

    def request(method, path, body=None):
        expected_path = '/rules/' + config.uid if method == 'DELETE' else '/rules'
        assert path == expected_path
        if method == 'DELETE':
            assert state['rule'] == original
            state['rule'] = None
            calls.append('withdraw')
            return 204
        assert method == 'POST' and state['rule'] is None
        state['rule'] = original
        calls.append('restore')
        return 201

    def install(config):
        assert state['rule'] is None
        calls.append('install')
        if install_fails:
            raise RuntimeError('isolated install failure')
        state['rule'] = file_rule

    def get(path):
        if path == '/rules':
            return [] if state['rule'] is None else [state['rule']]
        raise AssertionError('unexpected Item fetch')

    monkeypatch.setattr(migration, 'request', request)
    monkeypatch.setattr(migration, 'install', install)
    monkeypatch.setattr(migration.oh, 'get', get)
    if install_fails:
        with pytest.raises(RuntimeError, match='isolated install failure'):
            migration.apply(original, expected_states, config)
        assert state['rule'] == original
        assert calls == ['withdraw', 'install', 'restore']
    else:
        migration.apply(original, expected_states, config)
        assert state['rule'] == file_rule
        assert calls == ['withdraw', 'install']


@pytest.mark.parametrize('kind', ['season', 'sky', 'extrema', 'bitcoin', 'battery-icon'])
def test_held_apply_refuses_before_live_preflight_or_backup(monkeypatch, kind):
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--kind', kind, '--apply'])
    monkeypatch.setattr(migration, 'preflight',
                        lambda *_: (_ for _ in ()).throw(AssertionError('preflight called')))
    monkeypatch.setattr(migration, 'backup',
                        lambda *_: (_ for _ in ()).throw(AssertionError('backup called')))
    with pytest.raises(SystemExit, match='not release-qualified'):
        migration.main()


def test_bitcoin_handoff_tolerates_natural_price_update(monkeypatch):
    config = replace(migration.RULES['bitcoin'],
                     target=Path('/tmp/nonexistent-bitcoin-rule-test.js'))
    original = {**ORIGINAL, 'uid': config.uid,
                'triggers': [{'type': kind, 'configuration': dict(fields)}
                             for kind, fields in config.triggers]}
    state = {'rule': original, 'output': '2.0'}
    monkeypatch.setattr(migration, 'backup', lambda *_: Path('/tmp'))
    monkeypatch.setattr(migration, 'rule_or_none', lambda *_: state['rule'])
    monkeypatch.setattr(migration, 'output_states', lambda *_: {'BTC_Price_24h_PercentChange': state['output']})
    monkeypatch.setattr(migration.oh, 'get', lambda path: [state['rule']] if path == '/rules' else None)
    monkeypatch.setattr(migration, 'request', lambda method, *_: state.update(rule=None) or 204)

    def install(_):
        state['rule'] = {**original, 'editable': False}
        state['output'] = '2.1'  # A natural update is not a rollback condition.

    monkeypatch.setattr(migration, 'install', install)
    migration.apply(original, {'BTC_Price_24h_PercentChange': '2.0'}, config)
    assert state['output'] == '2.1'
    assert state['rule']['editable'] is False
