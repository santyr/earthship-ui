"""Offline Moon handoff guards; no household mutation or synthetic live state."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path

import pytest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('moon_handoff_tests', 'migrate-astro-moon-thing.py')
fixtures = load('moon_history_fixtures', 'test_qualify_astro_moon_thing_provider.py')


def original():
    return {'UID': m.q.UID, 'thingTypeUID': 'astro:moon', 'label': 'Moon', 'editable': True,
            'configuration': {'interval': 300},
            'statusInfo': {'status': 'ONLINE', 'statusDetail': 'NONE'},
            'channels': [{'id': 'phase#name', 'uid': m.q.UID + ':phase#name',
                          'linkedItems': ['Moon_MoonPhaseName'], 'defaultTags': []}]}


def verified():
    thing = original()
    intended = deepcopy(thing); intended['channels'][0]['defaultTags'] = ['Info']
    return {'snapshot': {'thing': thing, 'links': [], 'dependents': {}, 'consumer_guard': {}},
            'history': {}, 'intended': intended}


@pytest.mark.parametrize('mode', [['--apply'], ['--target', '/other'], []])
def test_closed_gate_or_unsupported_mode_refuses_before_preflight(monkeypatch, mode):
    monkeypatch.setattr(m, 'capture', lambda *_: pytest.fail('production preflight'))
    monkeypatch.setattr(m, 'prepare', lambda: pytest.fail('backup'))
    with pytest.raises(RuntimeError): m.command(mode)


@pytest.mark.parametrize('gate', ['LIVE_RELEASE_READY', 'METADATA_DEVIATION_APPROVED'])
def test_each_live_gate_is_independently_required(monkeypatch, gate):
    monkeypatch.setattr(m, 'LIVE_RELEASE_READY', True)
    monkeypatch.setattr(m, 'METADATA_DEVIATION_APPROVED', True)
    monkeypatch.setattr(m, gate, False)
    monkeypatch.setattr(m, 'prepare', lambda: pytest.fail('backup'))
    with pytest.raises(RuntimeError): m.command(['--apply'])


def test_read_only_check_does_not_create_backup_or_lock(monkeypatch):
    monkeypatch.setattr(m, 'capture', lambda: verified())
    monkeypatch.setattr(m, 'exclusive', lambda: pytest.fail('lock'))
    monkeypatch.setattr(m, 'prepare', lambda: pytest.fail('backup'))
    result = m.command(['--check'])
    assert result['production_writes'] == 0 and result['live_release_ready'] is False


@pytest.mark.parametrize('call', [('DELETE', '/items/Moon'), ('DELETE', '/things/other?force=true'),
                                  ('PUT', '/items/Moon'), ('POST', '/things'), ('PUT', '/things/'+m.q.UID)])
def test_mutations_outside_exact_scope_refuse_before_auth(monkeypatch, call):
    monkeypatch.setattr(m, 'LIVE_RELEASE_READY', True)
    monkeypatch.setattr(m, 'METADATA_DEVIATION_APPROVED', True)
    monkeypatch.setattr(m.oh, 'token', lambda: pytest.fail('auth'))
    with pytest.raises(RuntimeError): m.request(*call, original(), body={'unapproved': 1})


def test_request_itself_checks_release_gates(monkeypatch):
    monkeypatch.setattr(m.oh, 'token', lambda: pytest.fail('auth'))
    with pytest.raises(RuntimeError): m.request('DELETE', m.DELETE_PATH, original())


def test_read_only_archive_keeps_exact_28_original_copy_streams(tmp_path):
    db = fixtures.HistoryDB()
    result = m.original_history(db, tmp_path)
    assert len(result) == len(list(tmp_path.iterdir())) == 28
    for name, row in result.items():
        path = tmp_path / ('item' + str(row['id']).zfill(4) + '.csv')
        assert path.read_bytes() == db.body
        assert path.stat().st_mode & 0o777 == 0o600
        assert row['sha256'] == m.sha256(path.read_bytes()).hexdigest()
    assert db.calls[0][1]['readonly'] is True
    assert all(not any(word in call[1].upper().split() for word in ('INSERT', 'UPDATE', 'DELETE', 'DROP'))
               for call in db.calls if call[0] in ('execute', 'copy'))


def test_archive_bound_refuses_before_retaining_overflow(tmp_path):
    path = tmp_path / 'archive'
    with path.open('wb') as stream:
        writer = m.ArchiveDigest(3, stream)
        with pytest.raises(RuntimeError): writer.write(b'too large')
    assert path.read_bytes() == b''


def test_overlap_lock_is_retained_but_second_owner_refuses(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(m, 'BACKUP_ROOT', tmp_path)
    with m.exclusive():
        with pytest.raises(BlockingIOError):
            with m.exclusive(): pytest.fail('overlapping owner')
    with m.exclusive(): pass
    assert (tmp_path / 'astro-moon.lock').stat().st_mode & 0o777 == 0o600


def test_lock_symlink_refuses(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(m, 'BACKUP_ROOT', tmp_path)
    target = tmp_path / 'unrelated'; target.write_bytes(b'preserve')
    (tmp_path / 'astro-moon.lock').symlink_to(target)
    with pytest.raises(OSError):
        with m.exclusive(): pytest.fail('unsafe lock')
    assert target.read_bytes() == b'preserve'


@pytest.mark.parametrize('existing', ['file', 'dangling_symlink'])
def test_file_install_never_overwrites_existing(tmp_path, monkeypatch, existing):
    target = tmp_path / 'astro-moon.things'
    if existing == 'file': target.write_bytes(b'user source')
    else: target.symlink_to(tmp_path / 'missing')
    monkeypatch.setattr(m, 'TARGET', target)
    with pytest.raises(FileExistsError): m.install_source()
    assert target.read_bytes() == b'user source' if existing == 'file' else target.is_symlink()
    assert len(list(tmp_path.iterdir())) == 1


def test_install_reports_owned_inode_even_when_directory_sync_fails(tmp_path, monkeypatch):
    target = tmp_path / 'astro-moon.things'
    monkeypatch.setattr(m, 'TARGET', target)
    def fail(_): raise OSError('test sync fault')
    monkeypatch.setattr(m, 'sync_directory', fail)
    identities = []
    with pytest.raises(OSError): m.install_source(identities.append)
    info = target.stat()
    assert identities == [(info.st_dev, info.st_ino)]
    assert target.read_bytes() == m.q.SOURCE.read_bytes()
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('fault', ['inode', 'bytes', 'symlink'])
def test_owned_file_withdrawal_refuses_any_drift(tmp_path, monkeypatch, fault):
    target = tmp_path / 'astro-moon.things'
    monkeypatch.setattr(m, 'TARGET', target)
    identity = m.install_source()
    if fault == 'inode': identity = (identity[0], identity[1]+1)
    elif fault == 'bytes': target.write_bytes(b'unexpected')
    else:
        target.unlink(); target.symlink_to(m.q.SOURCE)
    with pytest.raises(RuntimeError): m.remove_owned_file(identity)
    assert target.exists() or target.is_symlink()


def test_owned_file_removed_without_touching_unrelated_files(tmp_path, monkeypatch):
    target = tmp_path / 'astro-moon.things'
    unrelated = tmp_path / 'user.things'; unrelated.write_bytes(b'preserve')
    monkeypatch.setattr(m, 'TARGET', target)
    identity = m.install_source()
    m.remove_owned_file(identity)
    assert not target.exists() and unrelated.read_bytes() == b'preserve'


@pytest.mark.parametrize('fault', [None, 'provider', 'description', 'offline'])
def test_provider_check_keeps_full_named_alternative_and_provider(monkeypatch, fault):
    evidence = verified()
    current = deepcopy(evidence['intended']); current['editable'] = False
    if fault == 'provider': current['editable'] = True
    elif fault == 'description': current['channels'][0]['description'] = 'unexpected'
    elif fault == 'offline': current['statusInfo']['status'] = 'OFFLINE'
    monkeypatch.setattr(m, 'get_thing', lambda: current)
    assert m.provider_ready(evidence, True) is (fault is None)


@pytest.mark.parametrize('fault', [None, 'metadata', 'pattern', 'missing_readonly', 'bool_type'])
def test_withdrawal_exception_is_only_true_to_false_readonly(monkeypatch, fault):
    before = {'Moon': {'metadata': {}, 'stateDescription': {'readOnly': True, 'pattern': 'kept'}}}
    after = deepcopy(before); after['Moon']['stateDescription']['readOnly'] = False
    if fault == 'metadata': after['Moon']['metadata']['extra'] = 'unexpected'
    elif fault == 'pattern': after['Moon']['stateDescription']['pattern'] = 'unexpected'
    elif fault == 'missing_readonly': after['Moon']['stateDescription'].pop('readOnly')
    elif fault == 'bool_type': after['Moon']['stateDescription']['readOnly'] = 0
    monkeypatch.setattr(m, 'current_dependents', lambda: ([], after))
    if fault:
        with pytest.raises(RuntimeError): m.verify_unchanged({'links': [], 'dependents': before}, withdrawal=True)
    else: m.verify_unchanged({'links': [], 'dependents': before}, withdrawal=True)


def native_line(item, channel, at):
    return at + " [INFO] Item '" + item + "' changed from 1 to 2 (source: org.openhab.core.thing$" + channel + ')'


@pytest.mark.parametrize('fault', [None, 'missing_sun', 'missing_moon', 'old', 'synthetic', 'updated'])
def test_native_gate_requires_distinct_new_moon_and_sun_events(tmp_path, monkeypatch, fault):
    after = datetime.now(timezone.utc) - timedelta(seconds=30)
    local = datetime.now(m.q.ZoneInfo('America/Denver')) - timedelta(seconds=5)
    if fault == 'old': local -= timedelta(hours=1)
    at = local.strftime('%Y-%m-%d %H:%M:%S.%f')[:23]
    moon = native_line('Moon_MoonIllumination', 'astro:moon:local:phase#illumination', at)
    sun = native_line('Sun_Position_Elevation', 'astro:sun:local:position#elevation', at)
    body = moon + '\n' + sun
    if fault == 'missing_sun': body = moon
    elif fault == 'missing_moon': body = sun
    elif fault == 'synthetic': body = body.replace('org.openhab.core.thing$', 'automation$')
    elif fault == 'updated': body = body.replace('changed from', 'updated from')
    path = tmp_path / 'events.log'; path.write_text(body)
    monkeypatch.setattr(m, 'EVENT_LOG', path)
    assert m.natural_updates_after(after) is (fault is None)


def flow(monkeypatch, tmp_path):
    evidence = verified()
    monkeypatch.setattr(m, 'LIVE_RELEASE_READY', True)
    monkeypatch.setattr(m, 'METADATA_DEVIATION_APPROVED', True)
    target = tmp_path / 'target'; monkeypatch.setattr(m, 'TARGET', target)
    calls = []
    monkeypatch.setattr(m, 'verify_backup', lambda *_: {})
    monkeypatch.setattr(m, 'provider_ready', lambda *_: True)
    monkeypatch.setattr(m, 'get_thing', lambda: None)
    monkeypatch.setattr(m, 'verify_unchanged', lambda *a, **k: calls.append('dependents'))
    monkeypatch.setattr(m, 'guard_unchanged', lambda *_: calls.append('guard'))
    monkeypatch.setattr(m, 'history_unchanged', lambda *_: calls.append('history'))
    monkeypatch.setattr(m, 'pumps_off', lambda: calls.append('pumps_off'))
    monkeypatch.setattr(m, 'request', lambda method, *a, **k: calls.append(method))
    def install(callback): calls.append('install'); callback((1, 2))
    monkeypatch.setattr(m, 'install_source', install)
    monkeypatch.setattr(m, 'rollback', lambda *_: calls.append('rollback'))
    monkeypatch.setattr(m, 'qualify_phase', lambda *args: calls.append(args[-1]))
    return evidence, calls


def test_actual_flow_exercises_managed_rollback_before_final_file(monkeypatch, tmp_path):
    evidence, calls = flow(monkeypatch, tmp_path)
    result = m.apply(tmp_path, evidence)
    assert [c for c in calls if c in ('DELETE','install','file-1','rollback','managed-rollback','file-2')] == [
        'DELETE','install','file-1','rollback','managed-rollback','DELETE','install','file-2']
    assert result['managed_rollback_exercised'] is True
    assert result['production_restart_recovery'] == 'not_tested'


def test_lost_delete_ack_still_runs_scoped_failure_recovery(monkeypatch, tmp_path):
    evidence, calls = flow(monkeypatch, tmp_path)
    def fail(*_): calls.append('DELETE'); raise OSError('lost response')
    monkeypatch.setattr(m, 'request', fail)
    with pytest.raises(OSError): m.apply(tmp_path, evidence)
    assert calls[-2:] == ['rollback', 'failure-recovery']


def test_late_install_failure_retains_inode_for_rollback(monkeypatch, tmp_path):
    evidence, calls = flow(monkeypatch, tmp_path)
    def install(callback): callback((99, 22)); raise OSError('late sync')
    monkeypatch.setattr(m, 'install_source', install)
    ownership = []
    monkeypatch.setattr(m, 'rollback', lambda directory, verified, identity: ownership.append(identity))
    with pytest.raises(OSError): m.apply(tmp_path, evidence)
    assert ownership == [(99, 22)]


def test_recovery_never_replaces_unexpected_managed_definition(monkeypatch, tmp_path):
    evidence = verified()
    monkeypatch.setattr(m, 'TARGET', tmp_path / 'absent')
    current = original(); current['label'] = 'changed elsewhere'
    monkeypatch.setattr(m, 'get_thing', lambda: current)
    monkeypatch.setattr(m, 'request', lambda *_: pytest.fail('overwrite'))
    with pytest.raises(RuntimeError): m.rollback(tmp_path, evidence, None)


def test_prepare_failure_only_removes_its_new_incomplete_directory(tmp_path, monkeypatch):
    tmp_path.chmod(0o700); monkeypatch.setattr(m, 'BACKUP_ROOT', tmp_path)
    old = tmp_path / 'older-recovery'; old.mkdir(); (old / 'keep').write_bytes(b'preserve')
    def fail(_): raise RuntimeError('capture refused')
    monkeypatch.setattr(m, 'capture', fail)
    with pytest.raises(RuntimeError): m.prepare()
    assert list(tmp_path.iterdir()) == [old] and (old / 'keep').read_bytes() == b'preserve'


def backup_fixture(monkeypatch, tmp_path):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(m, 'BACKUP_ROOT', tmp_path)
    def capture(directory):
        proof = verified()
        proof['history'] = m.original_history(fixtures.HistoryDB(), directory)
        return proof
    monkeypatch.setattr(m, 'capture', capture)
    return m.prepare()


def test_complete_private_original_backup_reopens_all_30_exact_files(monkeypatch, tmp_path):
    directory, evidence = backup_fixture(monkeypatch, tmp_path)
    manifest = m.verify_backup(directory, evidence)
    assert len(manifest['files']) == 30
    assert (directory / 'manifest.json').read_bytes() == m.encoded(manifest)
    assert directory.stat().st_mode & 0o777 == 0o700
    assert len(list(directory.iterdir())) == 2  # Original preimage + manifest only.


@pytest.mark.parametrize('fault', ['csv', 'definition', 'manifest', 'missing', 'extra', 'symlink', 'mode'])
def test_private_recovery_reopening_refuses_any_scope_or_digest_drift(monkeypatch, tmp_path, fault):
    directory, evidence = backup_fixture(monkeypatch, tmp_path)
    preimage = directory / 'preimage'
    path = preimage / 'item0039.csv'
    if fault == 'csv': path.write_bytes(b'unexpected')
    elif fault == 'definition': (preimage / 'snapshot.json').write_bytes(b'{}')
    elif fault == 'manifest': (directory / 'manifest.json').write_bytes(b'{}')
    elif fault == 'missing': path.unlink()
    elif fault == 'extra': (preimage / 'extra').write_bytes(b'preserve')
    elif fault == 'symlink': path.unlink(); path.symlink_to(preimage / 'item0040.csv')
    else: path.chmod(0o644)
    with pytest.raises(RuntimeError): m.verify_backup(directory, evidence)
    assert directory.exists()  # A completed backup is never pruned by verification.


@pytest.mark.parametrize('state', ['ON', 'NULL', 'UNDEF', None])
def test_planned_handoff_requires_both_pump_outputs_off(monkeypatch, state):
    monkeypatch.setattr(m.oh, 'get', lambda path: {'state': 'OFF' if 'SouthOutlet_' in path else state})
    with pytest.raises(RuntimeError): m.pumps_off()


def test_both_outputs_off_is_only_a_read_only_preflight(monkeypatch):
    calls = []
    def get(path): calls.append(path); return {'state': 'OFF'}
    monkeypatch.setattr(m.oh, 'get', get)
    m.pumps_off()
    assert calls == ['/items/SouthOutlet_Outlet2_Switch', '/items/East_Bed_Socket_Outlet_2_Power']


def test_scoped_recovery_creates_then_restores_exact_original_descriptor(monkeypatch, tmp_path):
    evidence = verified()
    monkeypatch.setattr(m, 'TARGET', tmp_path / 'absent')
    state = {'current': None}
    monkeypatch.setattr(m, 'get_thing', lambda: state['current'])
    monkeypatch.setattr(m, 'verify_unchanged', lambda *a, **k: None)
    calls = []
    def request(method, path, original, body=None):
        calls.append((method, path, body))
        state['current'] = deepcopy(evidence['intended'] if method == 'POST' else original)
    monkeypatch.setattr(m, 'request', request)
    m.rollback(tmp_path, evidence, None)
    full = m.q.managed_thing(evidence['snapshot']['thing'])
    assert calls == [('POST', '/things', {key: value for key, value in full.items() if key != 'channels'}),
                     ('PUT', '/things/'+m.q.UID, full)]
    assert 'linkedItems' not in calls[1][2]['channels'][0]


def test_failed_baseline_recheck_never_withdraws_or_rolls_back(monkeypatch, tmp_path):
    evidence, calls = flow(monkeypatch, tmp_path)
    def fail(_): raise RuntimeError('source changed')
    monkeypatch.setattr(m, 'guard_unchanged', fail)
    with pytest.raises(RuntimeError): m.apply(tmp_path, evidence)
    assert 'DELETE' not in calls and 'rollback' not in calls
