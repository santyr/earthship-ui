"""Pure release and provider guards for the Bitcoin price transfer adapter."""
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

spec = spec_from_file_location('bitcoin_price_migration',
    Path(__file__).with_name('migrate-bitcoin-price-item.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_number_and_exact_provider_guards():
    assert module.same_number('84242.0', 84242)
    assert not module.same_number('NaN', 84242)
    managed = {'editable': True, 'name': module.ITEM, 'type': 'Number',
               'label': '[%.0f ]', 'category': '', 'groupNames': ['BTC_Price'],
               'tags': [], 'metadata': None, 'state': '84242'}
    assert module.exact_item(managed, file_owned=False)
    assert not module.exact_item(managed, file_owned=True)
    file_row = {**managed, 'editable': False, 'label': 'Bitcoin Price',
                'stateDescription': {'pattern': '%.0f USD'}}
    assert module.exact_item(file_row, file_owned=True)
    link = {'editable': False, 'itemName': module.ITEM,
            'channelUID': module.CHANNEL, 'configuration': {}}
    assert module.exact_link(link, file_owned=True)
    link['configuration'] = {'profile': 'unexpected'}
    assert not module.exact_link(link, file_owned=True)


def test_group_semantics_must_survive_item_transfer(monkeypatch):
    group = {'editable': True, 'type': 'Group', 'label': 'BTC Price',
             'metadata': {'semantics': {'value': 'Equipment', 'editable': False}}}
    monkeypatch.setattr(module.oh, 'get', lambda path: group)
    assert module.group_unchanged()
    group['metadata'] = {}
    assert not module.group_unchanged()


def test_natural_receipt_must_be_new_and_match_file_state(monkeypatch):
    at = datetime(2026, 9, 24, 4, tzinfo=timezone.utc)
    monkeypatch.setattr(module, 'get_item', lambda: {'state': '84242'})
    monkeypatch.setattr(module, 'exact_item', lambda row, *, file_owned: file_owned)
    payload = {'version': 1, 'field': 'bitcoin.usd', 'receivedAt':
               int(at.timestamp() * 1000) + 1, 'price': 84242}
    monkeypatch.setattr(module.oh, 'get', lambda path: {'state': json.dumps(payload)})
    assert module.natural_receipt_after(at)
    payload['price'] = 84243
    assert not module.natural_receipt_after(at)
    payload['price'] = 84242
    payload['receivedAt'] = int(at.timestamp() * 1000)
    assert not module.natural_receipt_after(at)


def test_apply_refuses_before_any_backup_or_mutation(monkeypatch):
    monkeypatch.setattr(module.preflight, 'check', lambda: {'status': 'preflight_passed'})
    monkeypatch.setattr(module, 'backup', lambda *args:
                        pytest.fail('backup started despite release gate'))
    monkeypatch.setattr(module, 'request', lambda *args:
                        pytest.fail('REST mutation started despite release gate'))
    with pytest.raises(RuntimeError, match='not release-qualified'):
        module.main(apply=True)


def test_private_backup_requires_readable_dump_before_release(tmp_path, monkeypatch):
    root = tmp_path / 'private'
    root.mkdir(mode=0o700)
    item_db = tmp_path / 'item.json'
    link_db = tmp_path / 'link.json'
    item_db.write_text('{"item":1}')
    link_db.write_text('{"link":1}')
    monkeypatch.setattr(module, 'BACKUP_ROOT', root)
    monkeypatch.setattr(module, 'ITEM_DB', item_db)
    monkeypatch.setattr(module, 'LINK_DB', link_db)
    calls = []

    def run(args, **kwargs):
        calls.append(args[0])
        if args[0] == 'sudo':
            kwargs['stdout'].write(b'isolated-custom-dump')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, 'run', run)
    directory = module.backup({'name': module.ITEM},
                              {'channelUID': module.CHANNEL}, {'rows': 7})
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / 'item0034.dump').read_bytes() == b'isolated-custom-dump'
    assert (directory / 'archive-proof.json').stat().st_mode & 0o777 == 0o600
    assert calls == ['sudo', 'pg_restore']


def test_failed_private_backup_removes_only_incomplete_directory(tmp_path, monkeypatch):
    root = tmp_path / 'private'
    root.mkdir(mode=0o700)
    item_db = tmp_path / 'item.json'
    link_db = tmp_path / 'link.json'
    item_db.write_text('{"item":1}')
    link_db.write_text('{"link":1}')
    root.joinpath('earlier-complete-backup').mkdir()
    monkeypatch.setattr(module, 'BACKUP_ROOT', root)
    monkeypatch.setattr(module, 'ITEM_DB', item_db)
    monkeypatch.setattr(module, 'LINK_DB', link_db)
    monkeypatch.setattr(module.subprocess, 'run',
                        lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match='table dump failed'):
        module.backup({'name': module.ITEM},
                      {'channelUID': module.CHANNEL}, {'rows': 7})
    assert sorted(path.name for path in root.iterdir()) == ['earlier-complete-backup']


def test_rollback_refuses_changed_file_source(tmp_path, monkeypatch):
    target = tmp_path / 'bitcoin-price.items'
    target.write_bytes(b'changed by another owner')
    monkeypatch.setattr(module, 'TARGET', target)
    with pytest.raises(RuntimeError, match='manual rollback needed'):
        module.rollback(tmp_path, {}, {})
    assert target.exists()


def test_rollback_restores_exact_managed_item_and_link(tmp_path, monkeypatch):
    target = tmp_path / 'bitcoin-price.items'
    target.write_bytes(module.SOURCE.read_bytes())
    monkeypatch.setattr(module, 'TARGET', target)
    item = {'editable': True, 'name': module.ITEM, 'type': 'Number',
            'label': '[%.0f ]', 'category': '', 'groupNames': ['BTC_Price'],
            'tags': [], 'metadata': None, 'state': '84242'}
    link = {'editable': True, 'itemName': module.ITEM,
            'channelUID': module.CHANNEL, 'configuration': {}}
    current = {'item': None, 'links': []}
    calls = []

    def request(method, path, body=None):
        calls.append((method, path))
        if path.startswith('/items/'):
            current['item'] = item
        else:
            current['links'] = [link]

    monkeypatch.setattr(module, 'get_item', lambda: current['item'])
    monkeypatch.setattr(module, 'links', lambda: current['links'])
    monkeypatch.setattr(module, 'members',
                        lambda: {module.ITEM, 'BTC_Price_24h_PercentChange'})
    monkeypatch.setattr(module, 'group_unchanged', lambda: True)
    monkeypatch.setattr(module, 'request', request)
    monkeypatch.setattr(module, 'wait', lambda predicate, seconds=90: predicate())
    module.rollback(tmp_path, item, link)
    assert not target.exists()
    assert (tmp_path / 'failed-file.items').read_bytes() == module.SOURCE.read_bytes()
    assert calls == [('PUT', '/items/' + module.ITEM),
                     ('PUT', '/links/' + module.ITEM + '/'
                      + 'exec%3Acommand%3ABTC_Price%3Aoutput')]
