"""Pure fail-closed guards for the attended three-Item provider transfer."""
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('forecast_temperature_transfer',
    Path(__file__).with_name('migrate-openmeteo-forecast-temperature-items.py'))
m = module_from_spec(spec)
spec.loader.exec_module(m)


def managed(name, state='68.2574 °F'):
    return {'name': name, 'type': 'Number:Temperature', 'label': m.LABELS[name],
            'category': None, 'tags': ['forecast'], 'groupNames': ['gForecast'],
            'state': state, 'editable': True, 'metadata': None}


def link(name):
    return {'itemName': name, 'channelUID': m.CHANNELS[name],
            'configuration': {}, 'editable': True}


def test_exact_group_item_link_and_temperature_state():
    assert set(m.CHANNELS) == set(m.LABELS)
    for name in m.CHANNELS:
        assert m.exact_item(managed(name), name, True)
        assert m.exact_item(managed(name, '68.25740000001 °F'), name, True,
                            '68.2574 °F')
        assert not m.exact_item(managed(name, '68.3 °F'), name, True,
                                '68.2574 °F')
        assert not m.exact_item({**managed(name), 'groupNames': []}, name, True)
        assert not m.exact_item({**managed(name), 'metadata': {'x': 'y'}}, name, True)
        assert not m.exact_item({**managed(name), 'editable': False}, name, True)
        assert m.exact_link(link(name), name, True)
        assert not m.exact_link({**link(name), 'configuration': {'profile': 'offset'}},
                                name, True)
        assert not m.exact_link({**link(name), 'channelUID': 'other'}, name, True)
    assert not m.same_state('NULL', '68 °F')
    assert not m.same_state('68 °C', '68 °F')


def test_preserved_requires_every_historical_row_including_duplicates():
    stamp = datetime(2026, 9, 23, tzinfo=timezone.utc)
    row = (stamp, 68.0)
    assert m.preserved([row, row], [row, row, (stamp, 69.0)])
    assert not m.preserved([row, row], [row])
    assert not m.preserved([row], [(stamp, 69.0)])


def test_state_restore_accepts_only_original_or_latest_past_jdbc_value():
    name = 'Forecast_Daily_High'
    now = datetime(2026, 9, 23, 19, tzinfo=timezone.utc)
    rows = [(now.replace(hour=0), 72.3074),
            (now.replace(hour=18), 68.3473982),
            (now.replace(day=24, hour=0), 66.0)]
    restored = m.restore_state_from_history(rows, now)
    assert restored == '68.3473982 °F'
    candidates = ('68.2574 °F', restored)
    assert m.exact_item(managed(name, candidates[0]), name, True, candidates)
    assert m.exact_item(managed(name, candidates[1]), name, True, candidates)
    assert not m.exact_item(managed(name, '66 °F'), name, True, candidates)
    assert not m.exact_item(managed(name, 'NULL'), name, True, candidates)
    with pytest.raises(RuntimeError, match='no past JDBC'):
        m.restore_state_from_history(rows[2:], now)


def test_history_guard_waits_through_transient_jdbc_series_replacement(monkeypatch):
    stamp = datetime(2026, 9, 23, tzinfo=timezone.utc)
    before = {name: [(stamp, 68.0)] for name in m.CHANNELS}
    identities = {name: index for index, name in enumerate(m.CHANNELS)}
    attempts = {'count': 0}

    def transient(_, identity):
        name = list(m.CHANNELS)[identity]
        if name == 'Forecast_Temp':
            attempts['count'] += 1
            if attempts['count'] <= 2:
                return []
        return before[name]

    monkeypatch.setattr(m, 'history', transient)
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    assert m.settled_history_preserved(None, identities, before)
    assert attempts['count'] == 6


def test_rollback_refuses_unknown_file_without_moving_it(tmp_path, monkeypatch):
    target = tmp_path / 'unknown.items'
    target.write_text('unknown source')
    monkeypatch.setattr(m, 'TARGET', target)
    with pytest.raises(RuntimeError, match='target drift'):
        m.restore_managed(tmp_path, {}, {}, m.SOURCE_SHA256, {})
    assert target.read_text() == 'unknown source'


def test_rollback_is_idempotent_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'TARGET', tmp_path / 'absent.items')
    originals = {name: managed(name) for name in m.CHANNELS}
    originals_links = {name: link(name) for name in m.CHANNELS}
    monkeypatch.setattr(m, 'item', lambda name: originals[name])
    monkeypatch.setattr(m, 'links', lambda: {
        name: [originals_links[name]] for name in m.CHANNELS})
    monkeypatch.setattr(m, 'wait_for', lambda predicate, seconds=90: predicate())
    monkeypatch.setattr(m, 'request', lambda *args: pytest.fail('unexpected mutation'))
    m.restore_managed(tmp_path, originals, originals_links,
                      m.SOURCE_SHA256,
                      {name: originals[name]['state'] for name in m.CHANNELS})
