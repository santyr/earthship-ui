import importlib.util
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    'battery_icon_migration', Path(__file__).with_name('migrate-battery-icon.py'))
battery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(battery)


def original():
    return {'name': battery.ITEM, 'type': 'String', 'label': 'BatteryIcon',
            'category': '', 'tags': [], 'groupNames': [], 'editable': True,
            'state': 'iconify:mdi:battery-70',
            'metadata': battery.EXPECTED_METADATA,
            'stateDescription': {'pattern': '"Battery Icon [%s]" <iconify>',
                                 'options': [], 'readOnly': False}}


def snapshot():
    return battery.Snapshot(
        31, 2, datetime(2026, 9, 29, tzinfo=timezone.utc),
        'iconify:mdi:battery-70', 'a' * 64)


def test_apply_gate_is_closed_before_database_open(monkeypatch):
    monkeypatch.setattr(battery, 'RELEASE_READY', False)
    monkeypatch.setattr(battery.migration.psycopg2, 'connect',
                        lambda **_kwargs: pytest.fail('database must not open'))
    with pytest.raises(SystemExit, match='not release-qualified'):
        battery.main(['--apply'])


def test_definition_changes_only_metadata_provider_flag():
    managed = original()
    file_item = {**managed, 'editable': False,
                 'metadata': json.loads(json.dumps(managed['metadata']))}
    file_item['metadata']['stateDescription']['editable'] = False
    assert battery.definition(managed, managed, file_owned=False)
    assert battery.definition(file_item, managed, file_owned=True)
    file_item['metadata']['stateDescription']['config']['pattern'] = '%s'
    assert not battery.definition(file_item, managed, file_owned=True)


def _fixture(monkeypatch, tmp_path, *, fail_file_wait=False):
    source = tmp_path / 'source.items'
    source.write_text('String BatteryIcon "BatteryIcon"\n')
    target = tmp_path / 'target.items'
    backup = tmp_path / 'receipt'
    backup.mkdir()
    monkeypatch.setattr(battery, 'SOURCE', source)
    monkeypatch.setattr(battery, 'TARGET', target)
    digest = sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(battery, 'SOURCE_SHA256', digest)
    monkeypatch.setattr(battery, 'rule_healthy', lambda **_kwargs: None)
    monkeypatch.setattr(battery.migration, 'backup', lambda *_args: backup)
    monkeypatch.setattr(battery, 'backup_history', lambda *_args: None)
    monkeypatch.setattr(battery, 'verify_prefix',
                        lambda *_args: {'added': 0, 'last_state': original()['state']})
    monkeypatch.setattr(battery.migration.oh, 'get', lambda _path: [])
    current = original()
    states = iter([current, None])
    monkeypatch.setattr(battery.migration, 'item', lambda _name: next(states))
    seen = []
    monkeypatch.setattr(battery.migration, 'request',
                        lambda method, name, body=None: seen.append((method, name, body)))
    monkeypatch.setattr(battery.migration, 'wait',
                        lambda _name, _original, provider: seen.append(('wait', provider)))
    monkeypatch.setattr(battery, 'restore_metadata',
                        lambda: seen.append(('restore_metadata',)))

    def wait_item(_db, _original, _before, *, file_owned):
        seen.append(('wait_item', file_owned))
        if file_owned and fail_file_wait:
            raise RuntimeError('file state did not restore')
        return {'added': 0}

    monkeypatch.setattr(battery, 'wait_item', wait_item)
    monkeypatch.setattr(battery.subprocess, 'run',
                        lambda args, **_kwargs: (shutil.copy2(args[-2], args[-1]),
                                                 SimpleNamespace(returncode=0))[1])
    return source, target, backup, current, seen


def test_provisional_transfer_keeps_writer_running(monkeypatch, tmp_path, capsys):
    source, target, _backup, current, seen = _fixture(monkeypatch, tmp_path)
    battery.apply(object(), current, snapshot())
    assert target.read_bytes() == source.read_bytes()
    assert ('DELETE', battery.ITEM, None) in seen
    assert ('wait_item', True) in seen
    assert 'file_provider_provisional' in capsys.readouterr().out


def test_failed_file_restore_recovers_managed_metadata(monkeypatch, tmp_path):
    source, target, backup, current, seen = _fixture(
        monkeypatch, tmp_path, fail_file_wait=True)
    with pytest.raises(RuntimeError, match='file state did not restore'):
        battery.apply(object(), current, snapshot())
    assert not target.exists()
    assert (backup / 'failed.items').read_bytes() == source.read_bytes()
    assert ('PUT', battery.ITEM, {field: current[field]
                                  for field in battery.migration.FIELDS}) in seen
    assert ('restore_metadata',) in seen
    assert seen[-1] == ('wait_item', False)
