"""Offline exact-delta and failure-rollback tests; no production requests."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cadence', ROOT / 'scripts/bms-aux-source-cadence.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def things():
    return {uid: {'UID': uid, 'editable': True, 'thingTypeUID': 'modbus:data',
                 'bridgeUID': m.POLLER, 'channels': [],
                 'statusInfo': {'status': 'ONLINE'}, 'configuration': {
                     'readStart': start, 'readValueType': 'uint32',
                     'readTransform': 'default', 'writeTransform': 'default',
                     'writeMaxTries': 3, m.PARAM: 60000}}
            for uid, (start, _) in m.TARGETS.items()}


def test_only_suppression_interval_changes():
    for thing in things().values():
        original = deepcopy(thing)
        assert m.plan(thing) == {**thing['configuration'], m.PARAM: 0}
        assert thing == original


def test_installed_binding_transform_array_preserved():
    thing = next(iter(things().values()))
    thing['configuration']['readTransform'] = ['default']
    thing['configuration']['writeTransform'] = ['default']
    assert m.plan(thing) == {**thing['configuration'], m.PARAM: 0}


@pytest.mark.parametrize('field,value', [('writeStart', '88'), ('writeTransform', 'JSON:x'),
                                        ('readStart', '1'), (m.PARAM, 120000)])
def test_unsafe_or_unexpected_config_refused(field, value):
    thing = next(iter(things().values()))
    thing['configuration'][field] = value
    with pytest.raises(RuntimeError):
        m.plan(thing)


def transaction(monkeypatch, tmp_path, fail=False, concurrent=False):
    original = things()
    live = deepcopy(original)
    attempts = []
    guard = {'poller': 'unchanged'}
    monkeypatch.setattr(m, 'inspect', lambda: (deepcopy(live), guard))
    monkeypatch.setattr(m, 'backup', lambda *_: tmp_path)
    monkeypatch.setattr(m.oh, 'get', lambda path: deepcopy(live[path.removeprefix('/things/')]))
    monkeypatch.setattr(m, 'wait_online', lambda uid, config: live[uid])

    def put(uid, config):
        attempts.append((uid, deepcopy(config)))
        live[uid]['configuration'] = deepcopy(config)
        if fail and len(attempts) == 2:
            if concurrent:
                live[uid]['configuration']['readStart'] = '99'
            raise OSError('ambiguous HTTP failure')
    monkeypatch.setattr(m, 'put', put)
    return original, live, guard, attempts


def test_applies_exact_two_configs_and_idempotent(monkeypatch, tmp_path):
    original, live, guard, attempts = transaction(monkeypatch, tmp_path)
    assert m.apply(original, guard)['status'] == 'applied'
    assert len(attempts) == 2
    assert m.apply(deepcopy(live), guard)['status'] == 'already_configured'
    assert len(attempts) == 2


def test_ambiguous_failure_restores_both_preimages(monkeypatch, tmp_path):
    original, live, guard, attempts = transaction(monkeypatch, tmp_path, fail=True)
    with pytest.raises(RuntimeError, match='rollback verified'):
        m.apply(original, guard)
    assert live == original
    assert len(attempts) == 4


def test_rollback_does_not_clobber_concurrent_edit(monkeypatch, tmp_path):
    original, live, guard, attempts = transaction(monkeypatch, tmp_path, fail=True, concurrent=True)
    with pytest.raises(RuntimeError, match='rollback incomplete'):
        m.apply(original, guard)
    first, second = m.TARGETS
    assert live[first] == original[first]
    assert live[second]['configuration']['readStart'] == '99'
    assert len(attempts) == 3
