"""Offline transaction/receipt guards; no household API or database writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pytest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


m = load('bitcoin_exec_migration', 'migrate-bitcoin-exec-thing.py')
fixtures = load('bitcoin_exec_contract_fixtures', 'test_preflight_bitcoin_exec_thing.py')


def test_scoped_rest_mutations_refuse_other_resources_before_auth(monkeypatch):
    monkeypatch.setattr(m.p.oh, 'token', lambda: pytest.fail('no credentials needed'))
    for method, path, body in [
        ('DELETE', '/things/other:thing:id?force=true', None),
        ('PUT', '/items/BTC_USD_Price', b'{}'),
        ('POST', '/things', b'{"UID":"other:thing:id"}'),
    ]:
        with pytest.raises(RuntimeError):
            m.request(method, path, body)


@pytest.mark.parametrize('damage', ['old', 'future', 'null', 'wrong_price', 'extra', 'bool', 'field'])
def test_receipt_requires_new_finite_exact_success(damage):
    now = datetime(2026, 9, 30, 10, tzinfo=timezone.utc)
    after = now - timedelta(seconds=30)
    payload = {'version': 1, 'field': 'bitcoin.usd',
               'receivedAt': int(now.timestamp() * 1000) - 1, 'price': 84242}
    assert m.valid_receipt(json.dumps(payload), '84242', after=after, now=now)
    if damage == 'old': payload['receivedAt'] = int(after.timestamp() * 1000)
    elif damage == 'future': payload['receivedAt'] = int(now.timestamp() * 1000) + 1
    elif damage == 'null': payload['price'] = None
    elif damage == 'wrong_price': payload['price'] = 84243
    elif damage == 'extra': payload['unreviewed'] = 1
    elif damage == 'bool': payload['price'] = True
    else: payload['field'] = 'other'
    assert not m.valid_receipt(json.dumps(payload), '84242', after=after, now=now)


def test_fixed_definition_ignores_state_not_identity_or_metadata():
    first = {'name': 'BTC_USD_Price', 'type': 'Number', 'editable': False,
             'state': '84242', 'lastState': '84241', 'lastStateChange': 100,
             'lastStateUpdate': 101, 'label': 'Bitcoin Price', 'metadata': {}}
    assert m.item_definition(first) == m.item_definition({**first, 'state': '84243',
        'lastState': '84242', 'lastStateChange': 200, 'lastStateUpdate': 201})
    assert m.item_definition(first) != m.item_definition({**first, 'label': 'Changed'})


@pytest.mark.parametrize('damage', [None, 'label', 'metadata', 'pattern', 'missing', 'bool_type', 'group'])
def test_withdrawal_exception_is_only_derived_true_to_false_readonly(damage):
    original = {'items': {name: {'name': name, 'editable': False, 'label': 'kept',
        'metadata': {}, 'stateDescription': {'readOnly': True, 'pattern': 'kept'}}
        for name in m.p.LINKS}, 'group': {'name': 'BTC_Price'}, 'members': ['member']}
    current = deepcopy(original)
    for item in current['items'].values():
        item['stateDescription']['readOnly'] = False
    item = current['items']['BTC_USD_Price']
    if damage == 'label': item['label'] = 'changed'
    elif damage == 'metadata': item['metadata'] = {'other': 'changed'}
    elif damage == 'pattern': item['stateDescription']['pattern'] = 'changed'
    elif damage == 'missing': del item['stateDescription']['readOnly']
    elif damage == 'bool_type': item['stateDescription']['readOnly'] = 0
    elif damage == 'group': current['group']['name'] = 'other'
    assert m.withdrawal_items_equal(current, original) is (damage is None)
    assert current['items']['BTC_Output_Receipt_JSON']['stateDescription']['readOnly'] is False
    assert m.withdrawal_items_equal(original, original)
    assert not m.withdrawal_items_equal(original, current)


def test_withdrawal_requires_absent_provider_and_exact_links(monkeypatch):
    original = {'links': fixtures.links(), 'items': {}, 'group': {}, 'members': []}
    monkeypatch.setattr(m, 'dependents', lambda: {'items': {}, 'group': {}, 'members': []})
    monkeypatch.setattr(m, 'get_thing', lambda: fixtures.thing())
    monkeypatch.setattr(m.p.oh, 'get', lambda *_: pytest.fail('present provider refuses'))
    assert not m.withdrawal_dependents(original)
    monkeypatch.setattr(m, 'get_thing', lambda: None)
    monkeypatch.setattr(m.p.oh, 'get', lambda *_: fixtures.links())
    assert m.withdrawal_dependents(original)
    changed = fixtures.links(); changed[0]['configuration'] = {'other': 'changed'}
    monkeypatch.setattr(m.p.oh, 'get', lambda *_: changed)
    assert not m.withdrawal_dependents(original)


@pytest.mark.parametrize('file_owned', [False, True])
def test_actual_provider_predicate_preserves_both_editability_states(monkeypatch, file_owned):
    original = fixtures.thing()
    current = {**original, 'editable': not file_owned}
    monkeypatch.setattr(m, 'get_thing', lambda: current)
    monkeypatch.setattr(m.p.oh, 'get', lambda _path: fixtures.links())
    assert m.provider_ready(original, file_owned=file_owned)
    assert not m.provider_ready(original, file_owned=not file_owned)
    current['channels'] = deepcopy(original['channels'])
    current['channels'][0]['label'] = 'Unreviewed label'
    assert not m.provider_ready(original, file_owned=file_owned)


def test_atomic_install_never_overwrites_existing_destination(tmp_path, monkeypatch):
    target = tmp_path / 'bitcoin-price.things'
    target.write_bytes(b'user-owned file')
    monkeypatch.setattr(m, 'TARGET', target)
    with pytest.raises(FileExistsError):
        m.install_source()
    assert target.read_bytes() == b'user-owned file'
    assert sorted(x.name for x in tmp_path.iterdir()) == ['bitcoin-price.things']


def test_atomic_install_returns_owned_inode_and_exact_bytes(tmp_path, monkeypatch):
    target = tmp_path / 'bitcoin-price.things'
    monkeypatch.setattr(m, 'TARGET', target)
    identity = m.install_source()
    assert target.read_bytes() == m.p.SOURCE_BYTES
    assert identity == (target.stat().st_dev, target.stat().st_ino)
    assert target.stat().st_mode & 0o777 == 0o644
    assert sorted(x.name for x in tmp_path.iterdir()) == ['bitcoin-price.things']


@pytest.mark.parametrize('damage', ['foreign', 'changed', 'symlink'])
def test_rollback_never_withdraws_unowned_or_changed_file(tmp_path, monkeypatch, damage):
    target = tmp_path / 'bitcoin-price.things'
    monkeypatch.setattr(m, 'TARGET', target)
    identity = m.install_source()
    if damage == 'foreign': identity = None
    elif damage == 'changed': target.write_bytes(b'changed by another owner')
    else:
        target.unlink(); target.symlink_to(m.p.SOURCE)
    monkeypatch.setattr(m, 'get_thing', lambda: pytest.fail('no API action expected'))
    with pytest.raises(RuntimeError, match='manual rollback'):
        m.rollback(tmp_path, {}, identity)
    assert target.exists()


def test_live_apply_gate_precedes_backup_and_mutation(monkeypatch):
    monkeypatch.setattr(m, 'RELEASE_READY', False)
    monkeypatch.setattr(m, 'check', lambda: {'ready': True})
    monkeypatch.setattr(m, 'backup', lambda *_: pytest.fail('no backup expected'))
    monkeypatch.setattr(m, 'request', lambda *_: pytest.fail('no mutation expected'))
    with pytest.raises(RuntimeError, match='release gate'):
        m.main(apply=True)


@pytest.mark.parametrize('failed', [False, True])
def test_backup_is_private_and_failed_preparation_cleans_only_its_directory(monkeypatch, tmp_path, failed):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    earlier = root / 'earlier-complete'; earlier.mkdir()
    thing_db = tmp_path / 'thing.json'; thing_db.write_text('{}')
    link_db = tmp_path / 'link.json'; link_db.write_text('not JSON' if failed else '{}')
    monkeypatch.setattr(m, 'BACKUP_ROOT', root)
    monkeypatch.setattr(m.backup_tools, 'THING_DB', thing_db)
    monkeypatch.setattr(m.backup_tools, 'LINK_DB', link_db)
    if failed:
        with pytest.raises(ValueError):
            m.backup({'scope': 'fixture'})
        assert list(root.iterdir()) == [earlier]
    else:
        directory = m.backup({'scope': 'fixture'})
        assert directory.stat().st_mode & 0o777 == 0o700
        assert sorted(x.name for x in directory.iterdir()) == [
            'link-jsondb.json', 'rest-and-prefix.json', 'thing-jsondb.json']
        assert all(x.stat().st_mode & 0o777 == 0o600 for x in directory.iterdir())
        assert earlier.exists()


@pytest.fixture
def transaction(monkeypatch, tmp_path):
    after = datetime.now(timezone.utc) - timedelta(minutes=2)
    original = fixtures.thing()
    snapshot = {'thing': original, 'links': fixtures.links(),
                'items': {}, 'group': {}, 'members': []}
    prefix = {'before_utc': after.isoformat(), 'rows': 17, 'sha256': 'fixed-prefix'}
    verified = {'snapshot': snapshot, 'history_prefix': prefix,
                'source_sha256': m.SOURCE_SHA256}
    target = tmp_path / 'bitcoin-price.things'
    directory = tmp_path / 'backup'; directory.mkdir()
    current = {'thing': deepcopy(original), 'mutations': [], 'rollback': [],
               'durable': [], 'prefix_calls': 0}
    monkeypatch.setattr(m, 'RELEASE_READY', True)
    monkeypatch.setattr(m, 'TARGET', target)
    monkeypatch.setattr(m, 'check', lambda: verified)
    monkeypatch.setattr(m, 'backup', lambda *_: directory)
    monkeypatch.setattr(m, 'unchanged_dependents', lambda *_: True)
    monkeypatch.setattr(m, 'withdrawal_dependents', lambda *_: True)
    monkeypatch.setattr(m, 'runtime_sources', lambda: {'source': 'unchanged'})
    snapshot['runtime_sources'] = {'source': 'unchanged'}
    monkeypatch.setattr(m, 'get_thing', lambda: current['thing'])
    monkeypatch.setattr(m, 'wait', lambda predicate, seconds=90: predicate())
    monkeypatch.setattr(m, 'provider_ready', lambda original, *, file_owned:
                        current['thing'] is not None and
                        current['thing']['editable'] is (not file_owned))
    def request(method, path, body=None):
        current['mutations'].append((method, path))
        if method == 'DELETE': current['thing'] = None
        elif method == 'POST': current['thing'] = deepcopy(original)
    monkeypatch.setattr(m, 'request', request)
    real_install = m.install_source
    def install():
        identity = real_install()
        current['thing'] = {**original, 'editable': False}
        return identity
    monkeypatch.setattr(m, 'install_source', install)
    def digest(_cutoff):
        current['prefix_calls'] += 1
        return prefix
    monkeypatch.setattr(m.history, 'digest_history', digest)
    monkeypatch.setattr(m, 'natural_receipt_after', lambda *_: True)
    monkeypatch.setattr(m, 'durable_receipt_after', lambda *_: current['durable'].append(True) or True)
    real_rollback = m.rollback
    def rollback(*args):
        current['rollback'].append(True)
        current['thing'] = None  # Simulate asynchronous watched-file withdrawal.
        return real_rollback(*args)
    monkeypatch.setattr(m, 'rollback', rollback)
    return current, target, directory


def test_scoped_transaction_requires_history_and_durable_natural_receipt(transaction):
    current, target, _ = transaction
    report = m.main(apply=True)
    assert report['status'] == 'file_provider_verified'
    assert current['mutations'] == [('DELETE', m.DELETE_PATH)]
    assert current['prefix_calls'] == 2
    assert current['durable'] == [True]
    assert not current['rollback']
    assert target.read_bytes() == m.p.SOURCE_BYTES


@pytest.mark.parametrize('failure', ['boundary', 'install', 'provider', 'history', 'receipt', 'durable'])
def test_failed_transfer_restores_only_managed_thing(transaction, monkeypatch, failure):
    current, target, directory = transaction
    if failure == 'boundary':
        monkeypatch.setattr(m, 'withdrawal_dependents', lambda *_: False)
    elif failure == 'install':
        monkeypatch.setattr(m, 'install_source', lambda: (_ for _ in ()).throw(RuntimeError('failed install')))
    elif failure == 'provider':
        monkeypatch.setattr(m, 'provider_ready', lambda *_a, **kwargs: not kwargs['file_owned'])
    elif failure == 'history':
        count = [0]
        checked = m.check()['history_prefix']
        def changed(_cutoff):
            count[0] += 1
            return {'wrong': True} if count[0] == 2 else checked
        monkeypatch.setattr(m.history, 'digest_history', changed)
    elif failure == 'receipt': monkeypatch.setattr(m, 'natural_receipt_after', lambda *_: False)
    else: monkeypatch.setattr(m, 'durable_receipt_after', lambda *_: False)
    monkeypatch.setattr(m, 'rollback_receipt_after', lambda *_: True)
    with pytest.raises(RuntimeError):
        m.main(apply=True)
    assert current['rollback'] == [True]
    assert current['mutations'] == [('DELETE', m.DELETE_PATH), ('POST', '/things')]
    assert not target.exists()
    if failure not in ('boundary', 'install'):
        assert (directory / 'withdrawn-file.things').read_bytes() == m.p.SOURCE_BYTES


def test_final_definition_still_requires_derived_readonly_restored(monkeypatch):
    original = {'items': {'BTC_USD_Price': {'stateDescription': {'readOnly': True}}},
                'group': {}, 'members': []}
    current = deepcopy(original)
    current['items']['BTC_USD_Price']['stateDescription']['readOnly'] = False
    monkeypatch.setattr(m, 'dependents', lambda: current)
    assert not m.unchanged_dependents(original)
