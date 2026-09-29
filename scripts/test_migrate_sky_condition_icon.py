import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    'sky_icon_migration', Path(__file__).with_name('migrate-sky-condition-icon.py'))
sky = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sky)


def test_apply_is_closed_before_live_preflight(monkeypatch):
    monkeypatch.setattr(sky, 'RELEASE_READY', False)
    monkeypatch.setattr(sky.migration.psycopg2, 'connect',
                        lambda **_kwargs: pytest.fail('database must not open'))
    with pytest.raises(SystemExit, match='not release-qualified'):
        sky.main(['--apply'])


def test_preflight_requires_exact_passive_item_and_history(monkeypatch, tmp_path):
    source = tmp_path / 'sky.items'
    source.write_text(sky.DEFINITION + '\n')
    monkeypatch.setattr(sky, 'SOURCE', source)
    monkeypatch.setattr(sky, 'TARGET', tmp_path / 'absent.items')
    original = {'name': sky.ITEM, 'type': 'String', 'editable': True,
                'state': 'iconify:mdi:moon-waning-gibbous'}
    history = {'id': sky.ITEM_ID, 'count': 21, 'last_state': original['state']}
    monkeypatch.setattr(sky.migration, 'item', lambda _name: original)
    monkeypatch.setattr(sky.migration, 'history', lambda _db, _name: history)
    monkeypatch.setattr(sky, 'WRITER_SHA256', sky.sha256(b'writer').hexdigest())
    monkeypatch.setattr(sky.migration.oh, 'get', lambda path: [] if path == '/links'
                        else {'uid': sky.RULE, 'status': {
                            'status': 'IDLE', 'statusDetail': 'NONE'},
                            'actions': [{'configuration': {'script': 'writer'}}]})
    assert sky.preflight(object()) == (original, history,
                                       sky.sha256(source.read_bytes()).hexdigest())
    history['id'] = 174
    with pytest.raises(RuntimeError, match='Item 173'):
        sky.preflight(object())
    history['id'] = sky.ITEM_ID
    monkeypatch.setattr(sky, 'WRITER_SHA256', '0' * 64)
    with pytest.raises(RuntimeError, match='writer source drift'):
        sky.preflight(object())


def _apply_fixture(monkeypatch, tmp_path, *, fail_file_wait=False):
    source = tmp_path / 'sky.items'
    source.write_text(sky.DEFINITION + '\n')
    target = tmp_path / 'installed.items'
    backup = tmp_path / 'backup'
    backup.mkdir()
    monkeypatch.setattr(sky, 'SOURCE', source)
    monkeypatch.setattr(sky, 'TARGET', target)
    monkeypatch.setattr(sky, 'rule_idle', lambda: None)
    original = {'name': sky.ITEM, 'state': 'iconify:mdi:moon-waning-gibbous',
                'type': 'String', 'editable': True}
    history = {'id': sky.ITEM_ID, 'count': 21, 'last_state': original['state']}
    seen = []
    monkeypatch.setattr(sky.migration, 'backup', lambda *_args: backup)
    monkeypatch.setattr(sky, 'backup_history', lambda *_args: None)
    monkeypatch.setattr(sky.migration, 'history', lambda *_args: history)
    monkeypatch.setattr(sky.migration.oh, 'get', lambda _path: [])
    item_calls = iter([original, None])
    monkeypatch.setattr(sky.migration, 'item', lambda _name: next(item_calls))
    monkeypatch.setattr(sky.migration, 'request',
                        lambda method, name, body=None: seen.append((method, name, body)))

    def wait(_name, _original, provider):
        seen.append(('wait', provider))
        if provider is False and fail_file_wait:
            raise RuntimeError('file state did not restore')
    monkeypatch.setattr(sky.migration, 'wait', wait)
    monkeypatch.setattr(sky.subprocess, 'run',
                        lambda args, **_kwargs: (shutil.copy2(args[-2], args[-1]),
                                                 SimpleNamespace(returncode=0))[1])
    return source, target, backup, original, history, seen


def test_apply_preserves_history_and_reports_provisional(monkeypatch, tmp_path, capsys):
    source, target, _backup, original, history, seen = _apply_fixture(
        monkeypatch, tmp_path)
    sky.apply(object(), original, history, sky.sha256(source.read_bytes()).hexdigest())
    assert target.read_bytes() == source.read_bytes()
    assert ('DELETE', sky.ITEM, None) in seen
    assert ('wait', False) in seen
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['status'] == \
        'file_provider_provisional'


def test_failed_file_state_restores_managed_provider(monkeypatch, tmp_path, capsys):
    source, target, backup, original, history, seen = _apply_fixture(
        monkeypatch, tmp_path, fail_file_wait=True)
    with pytest.raises(RuntimeError, match='file state did not restore'):
        sky.apply(object(), original, history, sky.sha256(source.read_bytes()).hexdigest())
    assert not target.exists()
    assert (backup / 'failed.items').read_bytes() == source.read_bytes()
    assert ('PUT', sky.ITEM, {'name': sky.ITEM, 'type': 'String'}) in seen
    assert seen[-1] == ('wait', True)
    assert 'managed_rollback_verified=true' in capsys.readouterr().out
