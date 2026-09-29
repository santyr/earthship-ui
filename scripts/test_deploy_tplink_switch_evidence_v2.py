"""Offline exact-baseline and rollback tests for the observational rule guard."""

import copy
import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).with_name('deploy-tplink-switch-evidence-v2.py')
spec = importlib.util.spec_from_file_location('tplink_evidence_v2_release', PATH)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def old_rule():
    return {'uid': release.UID, 'name': 'Switch evidence',
            'triggers': [{'id': str(i)} for i in range(6)], 'conditions': [],
            'actions': [{'id': 'script', 'type': 'script.ScriptAction',
                         'configuration': {'script': 'old'}}],
            'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}


def test_candidate_is_pinned_and_observational():
    source = release.SOURCE.read_text()
    assert release.digest(source) == release.NEW_SHA
    assert 'sendCommand' not in source


def test_preflight_checks_old_hash_and_both_things(monkeypatch):
    original = old_rule()
    monkeypatch.setattr(release, 'OLD_SHA', release.digest('old'))
    def get(path):
        if path == '/rules/' + release.UID:
            return copy.deepcopy(original)
        if path.startswith('/things/'):
            return {'statusInfo': {'status': 'ONLINE', 'statusDetail': 'NONE'}}
        raise AssertionError(path)
    monkeypatch.setattr(release.oh, 'get', get)
    assert release.preflight() == (original, release.SOURCE.read_text())
    original['actions'][0]['configuration']['script'] = 'drift'
    with pytest.raises(RuntimeError, match='baseline'):
        release.preflight()


@pytest.mark.parametrize('fail_candidate', [False, True])
def test_apply_exact_readback_or_verified_rollback(monkeypatch, tmp_path, fail_candidate):
    original = old_rule()
    current = copy.deepcopy(original)
    candidate = release.SOURCE.read_text()
    calls = []
    monkeypatch.setattr(release, 'backup', lambda row: tmp_path)
    def enable(flag):
        current['status'] = {'status': 'IDLE', 'statusDetail': 'NONE'} if flag else {
            'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}
        calls.append(('enable', flag))
    def put(row):
        if fail_candidate and row['actions'][0]['configuration']['script'] == candidate:
            raise RuntimeError('injected candidate PUT failure')
        current.update(copy.deepcopy(release.dto(row)))
        calls.append(('put', row['actions'][0]['configuration']['script']))
    monkeypatch.setattr(release, 'enable', enable)
    monkeypatch.setattr(release, 'put', put)
    monkeypatch.setattr(release.oh, 'get', lambda path: copy.deepcopy(current))
    if fail_candidate:
        with pytest.raises(RuntimeError, match='injected'):
            release.apply(original, candidate)
        assert release.dto(current) == release.dto(original)
        assert calls == [('enable', False), ('enable', False), ('put', 'old'), ('enable', True)]
    else:
        release.apply(original, candidate)
        assert current['actions'][0]['configuration']['script'] == candidate
        assert calls == [('enable', False), ('put', candidate), ('enable', True)]
    assert current['status'] == {'status': 'IDLE', 'statusDetail': 'NONE'}
