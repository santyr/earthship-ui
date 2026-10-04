"""Guards and metadata parity for the in-container exact sky transaction."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('sky_isolated_transaction',
    Path(__file__).with_name('isolated-sky-transaction.py'))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


def test_refuses_outside_disposable_container_before_using_token(monkeypatch):
    monkeypatch.setattr(q.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(q.sys, 'stdin', None)
    with pytest.raises(RuntimeError, match='isolated container'):
        q.main('apply')


def test_unknown_phase_refused_before_any_input(monkeypatch):
    monkeypatch.setattr(q.sys, 'stdin', None)
    with pytest.raises(RuntimeError, match='transaction phase'):
        q.main('unknown')


def test_guard_refuses_changed_consumer_and_any_device_link():
    original = {'uid': q.release.sky.UID, 'actions': [{'script': 'original'}],
                'triggers': [], 'visibility': 'HIDDEN', 'configuration': {'kept': True}}
    healthy = {**original, 'editable': True,
               'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
    rows = {'/rules/' + original['uid']: healthy, '/links': [],
            **{'/items/' + name: {'state': 'OFF'} for name in q.release.sky.PUMPS}}
    q.guard(lambda path: rows[path], original)
    rows['/links'] = [{'itemName': q.release.sky.PUMPS[0], 'channelUID': 'physical'}]
    with pytest.raises(RuntimeError, match='device links'):
        q.guard(lambda path: rows[path], original)
    rows['/links'] = []
    rows['/rules/' + original['uid']] = {**healthy, 'configuration': {}}
    with pytest.raises(RuntimeError, match='consumer'):
        q.guard(lambda path: rows[path], original)
    rows['/rules/' + original['uid']] = healthy
    rows['/items/' + q.release.sky.PUMPS[0]] = {'state': 'ON'}
    with pytest.raises(RuntimeError, match='pump'):
        q.guard(lambda path: rows[path], original)
