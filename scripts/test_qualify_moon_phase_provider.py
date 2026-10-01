from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('moon_provider', Path(__file__).with_name('qualify-moon-phase-provider.py'))
q = module_from_spec(spec)
spec.loader.exec_module(q)


def fixtures(managed=True):
    items = [{'name': name, 'type': reading['type'], 'label': reading['label'],
              'category': '', 'tags': ['Point'], 'groupNames': ['Moon'],
              'metadata': deepcopy(q.SEMANTICS), 'editable': managed}
             for name, reading in q.READINGS.items()]
    for item in items:
        item['unitSymbol'] = q.READINGS[item['name']]['unit']
    links = [{'itemName': name, 'channelUID': reading['channel'],
              'configuration': deepcopy(reading['profile']), 'editable': managed}
             for name, reading in q.READINGS.items()]
    return items, links


def test_exact_live_definitions_preserve_legacy_default_profile_without_mutation():
    items, links = fixtures()
    before = deepcopy((items, links))
    assert set(q.preflight(items, links)) == set(q.READINGS)
    assert (items, links) == before
    assert q.READINGS['Moon_MoonPhaseName']['profile'] == {
        'profile': 'system:default', 'function': 'astro.map'}


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'file_item', 'file_link',
    'type', 'label', 'category', 'unit', 'tags', 'group', 'metadata', 'channel', 'map_profile', 'extra_link'])
def test_drift_and_ambiguous_ownership_refused(damage):
    items, links = fixtures()
    if damage == 'missing': items.pop()
    elif damage == 'duplicate': items.append(deepcopy(items[0]))
    elif damage == 'file_item': items[0]['editable'] = False
    elif damage == 'file_link': links[0]['editable'] = False
    elif damage == 'type': items[1]['type'] = 'Number'
    elif damage == 'label': items[0]['label'] = 'Other'
    elif damage == 'category': items[0]['category'] = 'switch'
    elif damage == 'unit': items[1]['unitSymbol'] = '%'
    elif damage == 'tags': items[0]['tags'] = []
    elif damage == 'group': items[0]['groupNames'] = ['Sun']
    elif damage == 'metadata': items[0]['metadata'] = {}
    elif damage == 'channel': links[0]['channelUID'] = 'astro:sun:local:phase#name'
    elif damage == 'map_profile': links[0]['configuration']['profile'] = 'transform:MAP'
    else: links.append(deepcopy(links[0]))
    with pytest.raises(ValueError): q.preflight(items, links)


def test_file_readback_checks_semantics_and_per_item_profile(monkeypatch):
    originals, _ = fixtures()
    items, links = fixtures(False)
    items[0]['category'] = None
    def get(_, path, __):
        if path == '/links': return 200, links
        name = path.split('/')[2].split('?')[0]
        return 200, next(item for item in items if item['name'] == name)
    monkeypatch.setattr(q.aqi, 'isolated_get', get)
    assert q.exact('fixture', b'private', {item['name']: item for item in originals}, file_owned=True)
    links[0]['configuration'].pop('function')
    assert not q.exact('fixture', b'private', {item['name']: item for item in originals}, file_owned=True)


def test_source_contains_only_exact_display_readings_and_no_group_or_control():
    assert q.checked_source() == q.SOURCE.read_bytes()
    rows = [line for line in q.SOURCE.read_text().splitlines() if not line.startswith('//')]
    assert len(rows) == 2
    for row, (name, reading) in zip(rows, q.READINGS.items()):
        assert row.startswith(reading['type'] + ' ' + name + ' ')
        assert reading['channel'] in row and '(Moon) ["Point"]' in row
    assert 'profile="system:default", function="astro.map"' in rows[0]
    assert not any(word in '\n'.join(rows) for word in ('Group ', 'expire=', 'command=', 'autoupdate='))


def test_source_drift_is_refused_before_container_or_live_access(tmp_path, monkeypatch):
    changed = tmp_path / 'candidate.items'
    changed.write_bytes(q.SOURCE.read_bytes() + b'\n// unreviewed drift\n')
    monkeypatch.setattr(q, 'SOURCE', changed)
    monkeypatch.setattr(q.aqi.oh, 'get', lambda *_: pytest.fail('live access before source guard'))
    monkeypatch.setattr(q.aqi, 'run', lambda *_: pytest.fail('container access before source guard'))
    with pytest.raises(ValueError, match='source changed'): q.main()


def test_cached_binding_drift_refuses_before_live_or_container_access(tmp_path, monkeypatch):
    bundle = tmp_path / 'unqualified.jar'
    bundle.write_bytes(b'not the matched binding')
    monkeypatch.setattr(q, 'ASTRO', bundle)
    monkeypatch.setattr(q.aqi.oh, 'get', lambda *_: pytest.fail('live access before bundle guard'))
    monkeypatch.setattr(q.aqi, 'run', lambda *_: pytest.fail('container access before bundle guard'))
    with pytest.raises(ValueError, match='bundle changed'): q.main()
