"""Pure guards for the attended Forecast_AQI transfer; no live writes."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


spec = spec_from_file_location('forecast_aqi_migration',
    Path(__file__).with_name('migrate-openmeteo-forecast-aqi-item.py'))
m = module_from_spec(spec)
spec.loader.exec_module(m)


def managed():
    return {**m.EXPECTED, 'editable': True, 'metadata': None, 'state': 'REFRESH'}


def link():
    return {'itemName': m.NAME, 'channelUID': m.CHANNEL, 'editable': True,
            'configuration': {}}


def test_exact_item_and_link_fail_closed():
    assert m.exact_item(managed(), True)
    assert m.exact_item({**managed(), 'category': ''}, True)
    assert not m.exact_item({**managed(), 'editable': False}, True)
    assert not m.exact_item({**managed(), 'tags': []}, True)
    assert not m.exact_item({**managed(), 'metadata': {'semantics': {}}}, True)
    assert m.exact_link(link(), True)
    assert not m.exact_link({**link(), 'channelUID': m.CHANNEL + '-other'}, True)
    assert not m.exact_link({**link(), 'configuration': {'profile': 'offset'}}, True)


def test_special_state_is_not_a_measured_aqi():
    assert m.allowed_state('REFRESH')
    for value in ('', 'NULL', 'UNDEF', '42', 'MODERATE', None):
        assert not m.allowed_state(value)


def test_rollback_is_idempotent_before_first_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'TARGET', tmp_path / 'not-installed.items')
    monkeypatch.setattr(m, 'item', managed)
    monkeypatch.setattr(m, 'links', lambda: [link()])
    monkeypatch.setattr(m, 'wait_for', lambda predicate, seconds=90: predicate())
    calls = []
    monkeypatch.setattr(m, 'request', lambda *args: calls.append(args))
    m.restore_managed(tmp_path, managed(), link(), m.SOURCE_SHA256)
    assert calls == []


def test_rollback_restores_only_missing_link(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'TARGET', tmp_path / 'not-installed.items')
    monkeypatch.setattr(m, 'item', managed)
    current_links = []
    monkeypatch.setattr(m, 'links', lambda: current_links)
    monkeypatch.setattr(m, 'wait_for', lambda predicate, seconds=90: predicate())
    def request(method, path, body=None):
        assert method == 'PUT' and path.startswith('/links/')
        current_links.append(link())
    monkeypatch.setattr(m, 'request', request)
    m.restore_managed(tmp_path, managed(), link(), m.SOURCE_SHA256)
    assert current_links == [link()]


def test_rollback_refuses_unknown_target_without_moving_it(tmp_path, monkeypatch):
    target = tmp_path / 'unknown.items'
    target.write_text('unknown file')
    monkeypatch.setattr(m, 'TARGET', target)
    with pytest.raises(RuntimeError, match='target drift'):
        m.restore_managed(tmp_path, managed(), link(), m.SOURCE_SHA256)
    assert target.read_text() == 'unknown file'


def test_rollback_with_owned_file_withdraws_then_restores_both(tmp_path, monkeypatch):
    target = tmp_path / 'installed.items'
    target.write_bytes(m.SOURCE.read_bytes())
    monkeypatch.setattr(m, 'TARGET', target)
    state = {'item': None, 'links': []}
    monkeypatch.setattr(m, 'item', lambda: state['item'])
    monkeypatch.setattr(m, 'links', lambda: state['links'])
    monkeypatch.setattr(m, 'wait_for', lambda predicate, seconds=90: predicate())
    def request(method, path, body=None):
        assert method == 'PUT'
        if path.startswith('/items/'):
            state['item'] = managed()
        else:
            state['links'] = [link()]
    monkeypatch.setattr(m, 'request', request)
    m.restore_managed(tmp_path, managed(), link(), m.SOURCE_SHA256)
    assert not target.exists()
    assert (tmp_path / 'failed-file.items').read_bytes() == m.SOURCE.read_bytes()
    assert state == {'item': managed(), 'links': [link()]}
