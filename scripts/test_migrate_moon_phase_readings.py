from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = spec_from_file_location('moon_handoff', Path(__file__).with_name('migrate-moon-phase-readings.py'))
m = module_from_spec(spec)
spec.loader.exec_module(m)


def originals():
    return {name: {'name': name, 'type': reading['type'], 'label': reading['label'],
                  'category': '', 'tags': ['Point'], 'groupNames': ['Moon'],
                  'metadata': deepcopy(m.definition.SEMANTICS), 'unitSymbol': reading['unit'],
                  'stateDescription': {'readOnly': True}, 'editable': True,
                  'state': 'WANING_GIBBOUS' if name.endswith('PhaseName') else '0.75'}
            for name, reading in m.definition.READINGS.items()}


def links():
    return {name: [{'itemName': name, 'channelUID': reading['channel'],
                   'configuration': deepcopy(reading['profile']), 'editable': True}]
            for name, reading in m.definition.READINGS.items()}


def histories():
    return {name: {'id': identity, 'count': 2, 'cutoff': datetime(2026, 9, 30, tzinfo=timezone.utc),
                  'sha256': 'a' * 64, 'bytes': 100,
                  'latest': 'WANING_GIBBOUS' if name.endswith('PhaseName') else 0.75}
            for name, identity in m.IDS.items()}


def test_closed_apply_gate_refuses_before_rest_or_database(monkeypatch):
    monkeypatch.setattr(m, 'RELEASE_READY', False)
    monkeypatch.setattr(m.transport.oh, 'get', lambda *_: pytest.fail('REST access'))
    monkeypatch.setattr(m.transport.psycopg2, 'connect', lambda **_: pytest.fail('database access'))
    with pytest.raises(SystemExit, match='not release-qualified'): m.main(['--apply'])


@pytest.mark.parametrize('args', [[], ['--check', '--apply'], ['--apply', 'another'], ['--target', 'BMS_SOC']])
def test_no_arbitrary_target_or_command_interface(args):
    with pytest.raises(SystemExit, match='usage'): m.main(args)


def test_state_validation_preserves_phase_and_fraction_contract():
    assert m.same_state('Moon_MoonPhaseName', 'NEW', 'NEW')
    assert not m.same_state('Moon_MoonPhaseName', 'new', 'new')
    assert m.same_state('Moon_MoonIllumination', '0.7500', 0.75)
    for value in ('75', '75 %', 'UNDEF', 'NaN', 'Infinity', '-0.1', '1.1'):
        assert not m.same_state('Moon_MoonIllumination', value, value)
    assert not m.same_state('BMS_SOC', '0.75', '0.75')


def test_history_digest_is_streamed_and_size_bounded(monkeypatch):
    writer = m.DigestWriter()
    writer.write('first\n'); writer.write(b'second\n')
    assert writer.digest.hexdigest() == sha256(b'first\nsecond\n').hexdigest()
    monkeypatch.setattr(m, 'MAX_HISTORY_BYTES', 13)
    with pytest.raises(RuntimeError, match='backup bound'): writer.write('!')


def test_history_prefix_requires_exact_count_cutoff_and_digest(monkeypatch):
    before = histories()
    calls = []
    def history(_, name, *, cutoff=None):
        calls.append((name, cutoff))
        return deepcopy(before[name])
    monkeypatch.setattr(m, 'history', history)
    m.prefix_preserved(object(), before)
    assert calls == [(name, row['cutoff']) for name, row in before.items()]
    monkeypatch.setattr(m, 'history', lambda _, name, **__: {**before[name], 'sha256': 'b' * 64})
    with pytest.raises(RuntimeError, match='prefix changed'): m.prefix_preserved(object(), before)


def test_atomic_install_has_exact_bytes_permissions_and_no_pending_file(monkeypatch, tmp_path):
    target = tmp_path / 'live.items'
    monkeypatch.setattr(m, 'TARGET', target)
    m.install_source()
    assert target.read_bytes() == m.SOURCE.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o644
    assert not list(tmp_path.glob('*.pending'))


@pytest.mark.parametrize('symlink', [False, True])
def test_atomic_install_never_overwrites_an_existing_target(monkeypatch, tmp_path, symlink):
    target = tmp_path / 'live.items'
    other = tmp_path / 'foreign.items'
    other.write_bytes(b'unrelated user data')
    if symlink: target.symlink_to(other)
    else: target.write_bytes(b'unrelated user data')
    monkeypatch.setattr(m, 'TARGET', target)
    with pytest.raises(FileExistsError): m.install_source()
    assert target.read_bytes() == b'unrelated user data'
    assert other.read_bytes() == b'unrelated user data'
    assert not list(tmp_path.glob('*.pending'))


def fixture(monkeypatch, tmp_path, *, fail_at=None, unknown_target=False):
    origin = originals(); attached = links(); before = histories()
    current = deepcopy(origin); current_links = deepcopy(attached)
    directory = tmp_path / 'private'; directory.mkdir(mode=0o700)
    target = tmp_path / 'live.items'
    monkeypatch.setattr(m, 'TARGET', target)
    monkeypatch.setattr(m, 'backup', lambda *_: directory)
    monkeypatch.setattr(m, 'protected_proof', lambda: 'protected')
    monkeypatch.setattr(m.transport, 'item', lambda name: current.get(name))
    monkeypatch.setattr(m, 'attached', lambda: deepcopy(current_links))
    monkeypatch.setattr(m, 'history', lambda _, name, **__: deepcopy(before[name]))
    seen = []
    file_loaded = False
    file_failed = False
    def wait(predicate, seconds=60):
        nonlocal file_loaded, file_failed
        if target.exists():
            if unknown_target:
                target.write_bytes(b'concurrent unreviewed source')
            if fail_at == 'file_readback' and not file_failed:
                file_failed = True
                return False
            file_loaded = True
            for name in m.IDS:
                current[name] = {**deepcopy(origin[name]), 'editable': False}
                current_links[name] = [{**deepcopy(attached[name][0]), 'editable': False}]
        elif file_loaded:
            file_loaded = False
            current.clear()
            current_links.update({name: [] for name in m.IDS})
        return predicate()
    monkeypatch.setattr(m.transport, 'wait_for', wait)
    def request(method, path, body=None):
        seen.append((method, path, body))
        if fail_at == 'link_delete' and len(seen) == 2:
            raise RuntimeError('partial link failure')
        name = path.split('/')[2]
        if path.startswith('/links/'):
            if method == 'DELETE': current_links[name] = []
            else: current_links[name] = [{**body, 'editable': True}]
        elif method == 'DELETE':
            if fail_at == 'item_delete' and sum(p.startswith('/items/') for _, p, _ in seen) == 2:
                raise RuntimeError('partial Item failure')
            current.pop(name, None)
        else: current[name] = deepcopy(origin[name])
    monkeypatch.setattr(m.transport, 'request', request)
    return SimpleNamespace(originals=origin, links=attached, before=before, directory=directory,
                           target=target, current=current, current_links=current_links, seen=seen)


def test_successful_transfer_only_mutates_exact_two_items_and_links(monkeypatch, tmp_path, capsys):
    f = fixture(monkeypatch, tmp_path)
    assert m.apply(object(), f.originals, f.links, f.before, 'protected') == f.directory
    assert all(row['editable'] is False for row in f.current.values())
    assert {method for method, _, _ in f.seen} == {'DELETE', 'PUT'}
    assert {path.split('/')[2] for _, path, _ in f.seen} == set(m.IDS)
    assert f.target.read_bytes() == m.SOURCE.read_bytes()
    output = capsys.readouterr().out
    assert 'managed_rollback_exercised=true' in output
    assert 'managed_rollback_verified' not in output


@pytest.mark.parametrize('failure', ['link_delete', 'item_delete', 'file_readback'])
def test_partial_failures_restore_exact_managed_providers(monkeypatch, tmp_path, failure, capsys):
    f = fixture(monkeypatch, tmp_path, fail_at=failure)
    with pytest.raises(RuntimeError): m.apply(object(), f.originals, f.links, f.before, 'protected')
    assert not f.target.exists()
    assert f.current == f.originals
    assert f.current_links == f.links
    assert 'managed_rollback_verified=true' in capsys.readouterr().out


def test_unknown_target_is_preserved_instead_of_unsafe_rollback(monkeypatch, tmp_path):
    f = fixture(monkeypatch, tmp_path, fail_at='file_readback', unknown_target=True)
    with pytest.raises(RuntimeError, match='unknown Moon target'):
        m.apply(object(), f.originals, f.links, f.before, 'protected')
    assert f.target.read_bytes() == b'concurrent unreviewed source'
    assert not any(method == 'PUT' for method, _, _ in f.seen)


def test_protected_configuration_drift_aborts_before_any_mutation(monkeypatch, tmp_path):
    f = fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(m, 'protected_proof', lambda: 'changed')
    with pytest.raises(RuntimeError, match='protected configuration changed'):
        m.apply(object(), f.originals, f.links, f.before, 'protected')
    assert not f.seen and not f.target.exists()


def test_apply_lock_prevents_overlapping_processes_and_releases_on_exit(monkeypatch, tmp_path):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    monkeypatch.setattr(m.transport, 'BACKUP_ROOT', root)
    with m.apply_lock():
        with pytest.raises(RuntimeError, match='owns the lock'):
            with m.apply_lock(): pytest.fail('overlapping apply')
    with m.apply_lock(): pass


def test_apply_lock_refuses_symlink_and_unsafe_root(monkeypatch, tmp_path):
    root = tmp_path / 'private'; root.mkdir(mode=0o700)
    monkeypatch.setattr(m.transport, 'BACKUP_ROOT', root)
    other = tmp_path / 'foreign'; other.write_text('user data')
    (root / 'moon-readings.lock').symlink_to(other)
    with pytest.raises(OSError):
        with m.apply_lock(): pytest.fail('followed symlink')
    assert other.read_text() == 'user data'
    root.chmod(0o755)
    with pytest.raises(RuntimeError, match='lock root'):
        with m.apply_lock(): pytest.fail('unsafe root')


def test_readback_uses_current_natural_history_not_the_old_state_snapshot(monkeypatch):
    origin = originals(); current = deepcopy(origin); attached = links(); before = histories()
    current['Moon_MoonIllumination']['state'] = '0.76'
    monkeypatch.setattr(m.transport, 'item', lambda name: current[name])
    monkeypatch.setattr(m, 'attached', lambda: attached)
    def history(_, name, *, cutoff=None):
        row = deepcopy(before[name])
        if cutoff is None and name == 'Moon_MoonIllumination': row['latest'] = 0.76
        return row
    monkeypatch.setattr(m, 'history', history)
    assert m.ready(object(), origin, before, managed=True)
    current['Moon_MoonIllumination']['state'] = '0.75'
    assert not m.ready(object(), origin, before, managed=True)


def test_readback_refuses_loss_of_channel_readonly_description(monkeypatch):
    origin = originals(); current = deepcopy(origin); attached = links(); before = histories()
    current['Moon_MoonPhaseName']['stateDescription']['readOnly'] = False
    monkeypatch.setattr(m.transport, 'item', lambda name: current[name])
    monkeypatch.setattr(m, 'attached', lambda: attached)
    monkeypatch.setattr(m, 'history', lambda _, name, **__: deepcopy(before[name]))
    assert not m.ready(object(), origin, before, managed=True)
