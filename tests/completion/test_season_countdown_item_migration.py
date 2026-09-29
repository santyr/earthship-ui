"""Offline provider/rollback transaction tests; never contact production."""
import importlib.util
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'season_countdown_item_migration',
    ROOT / 'scripts/migrate-season-countdown-item.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def setup_transfer(monkeypatch, tmp_path, *, fail_file_load=False):
    original = {
        'name': module.ITEM, 'editable': True, 'type': 'String',
        'label': 'Days Until Next Season', 'category': 'calendar',
        'state': '82 days until Winter ❄️', 'tags': [], 'groupNames': [],
    }
    history = {'id': 176, 'count': 217, 'last_state': original['state'],
               'sha256': 'a' * 64}
    source = tmp_path / 'source.items'
    source.write_text(module.DEFINITION + '\n')
    target = tmp_path / 'target.items'
    backup = tmp_path / 'private-backup'
    backup.mkdir()
    state = {'item': dict(original), 'file_failed': False, 'requests': []}

    monkeypatch.setattr(module, 'SOURCE', source)
    monkeypatch.setattr(module, 'TARGET', target)
    monkeypatch.setattr(module, 'rule_idle', lambda: None)
    monkeypatch.setattr(module, 'backup_history', lambda *_: None)
    monkeypatch.setattr(module.migration, 'backup', lambda *_: backup)
    monkeypatch.setattr(module.migration, 'item', lambda _: state['item'])
    monkeypatch.setattr(module.migration, 'history', lambda *_: history)
    monkeypatch.setattr(module.migration.oh, 'get', lambda path: [] if path == '/links' else None)

    def request(method, name, body=None):
        assert name == module.ITEM
        state['requests'].append(method)
        if method == 'DELETE':
            state['item'] = None
        else:
            assert method == 'PUT' and body['name'] == module.ITEM
            state['item'] = dict(original)

    def wait(name, expected, provider, seconds=90):
        assert name == module.ITEM and expected == original
        if provider is None:
            assert not target.exists()
            state['item'] = None
        elif provider is False:
            assert target.exists()
            if fail_file_load and not state['file_failed']:
                state['file_failed'] = True
                raise RuntimeError('file provider did not load')
            state['item'] = {**original, 'editable': False}
        else:
            assert provider is True and not target.exists()
            assert state['item'] == original

    def install(args, **_kwargs):
        assert args[:3] == ['install', '-m', '0644']
        shutil.copyfile(args[3], args[4])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.migration, 'request', request)
    monkeypatch.setattr(module.migration, 'wait', wait)
    monkeypatch.setattr(module.subprocess, 'run', install)
    return original, history, source, target, backup, state


def test_countdown_item_exercises_managed_rollback_then_file_provider(monkeypatch, tmp_path):
    original, history, source, target, backup, state = setup_transfer(monkeypatch, tmp_path)
    module.apply(None, original, history, module.sha256(source.read_bytes()).hexdigest())
    assert target.read_bytes() == source.read_bytes()
    assert state['item']['editable'] is False
    assert state['requests'] == ['DELETE', 'PUT', 'DELETE']
    assert not (backup / 'rollback.items').exists()


def test_countdown_item_restores_managed_provider_on_file_load_failure(monkeypatch, tmp_path):
    original, history, source, target, backup, state = setup_transfer(
        monkeypatch, tmp_path, fail_file_load=True)
    with pytest.raises(RuntimeError, match='file provider did not load'):
        module.apply(None, original, history, module.sha256(source.read_bytes()).hexdigest())
    assert not target.exists()
    assert (backup / 'failed.items').read_bytes() == source.read_bytes()
    assert state['item'] == original
    assert state['requests'] == ['DELETE', 'PUT']
