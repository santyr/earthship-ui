"""No-network transaction checks for the season display-rule handoff."""

import importlib.util
from pathlib import Path

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
FILE_RULE = {**ORIGINAL, 'editable': False}


@pytest.mark.parametrize('install_fails', [False, True])
def test_handoff_never_leaves_two_providers_and_restores_managed_on_failure(
        monkeypatch, install_fails):
    state = {'rule': ORIGINAL}
    calls = []
    monkeypatch.setattr(migration, 'backup', lambda original: Path('/tmp'))
    monkeypatch.setattr(migration, 'TARGET', Path('/tmp/nonexistent-season-rule-test.js'))
    monkeypatch.setattr(migration, 'rule_or_none', lambda: state['rule'])

    def request(method, path, body=None):
        expected_path = '/rules/' + migration.RULE if method == 'DELETE' else '/rules'
        assert path == expected_path
        if method == 'DELETE':
            assert state['rule'] == ORIGINAL
            state['rule'] = None
            calls.append('withdraw')
            return 204
        assert method == 'POST' and state['rule'] is None
        state['rule'] = ORIGINAL
        calls.append('restore')
        return 201

    def install():
        assert state['rule'] is None
        calls.append('install')
        if install_fails:
            raise RuntimeError('isolated install failure')
        state['rule'] = FILE_RULE

    def get(path):
        if path == '/rules':
            return [] if state['rule'] is None else [state['rule']]
        assert path == '/items/DaysUntilNextSeason'
        return {'state': '83 days until Winter ❄️'}

    monkeypatch.setattr(migration, 'request', request)
    monkeypatch.setattr(migration, 'install', install)
    monkeypatch.setattr(migration.oh, 'get', get)
    if install_fails:
        with pytest.raises(RuntimeError, match='isolated install failure'):
            migration.apply(ORIGINAL, '83 days until Winter ❄️')
        assert state['rule'] == ORIGINAL
        assert calls == ['withdraw', 'install', 'restore']
    else:
        migration.apply(ORIGINAL, '83 days until Winter ❄️')
        assert state['rule'] == FILE_RULE
        assert calls == ['withdraw', 'install']
