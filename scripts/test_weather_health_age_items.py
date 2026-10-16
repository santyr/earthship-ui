from copy import deepcopy
import importlib
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def guard():
    try:
        return importlib.import_module('weather_health_age_items')
    except ModuleNotFoundError:
        pytest.fail('weather-health age guards are not implemented')


def item(name, managed=True):
    g = guard()
    return {'name': name, 'type': 'Number', 'label': g.ITEMS[name]['label'],
            'category': '', 'tags': [], 'groupNames': ['gWeatherHealth'],
            'editable': managed, 'state': '7',
            'metadata': {'stateDescription': {'value': ' ',
                'config': {'pattern': '%.0f s'}, 'editable': managed}},
            'stateDescription': {'pattern': '%.0f s', 'readOnly': False, 'options': []}}


@pytest.mark.parametrize('managed', [True, False])
def test_exact_descriptor_and_metadata_ownership(managed):
    g = guard()
    for name in g.ITEMS:
        row = item(name, managed)
        g.validate_item(row, name, managed=managed)
        row['category'] = None
        g.validate_item(row, name, managed=managed)


@pytest.mark.parametrize('field,value', [
    ('name', 'WeatherData_WH65B_AgeSeconds'), ('type', 'Number:Time'),
    ('label', 'changed'), ('category', 'clock'), ('tags', ['sensor']),
    ('groupNames', []), ('unitSymbol', 's'), ('state', 'UNDEF'),
    ('state', '-1'), ('state', 'NaN'), ('state', '7 s'),
])
def test_changed_descriptor_or_invalid_state_is_refused(field, value):
    g = guard()
    name = next(iter(g.ITEMS)); row = item(name)
    row[field] = value
    with pytest.raises(ValueError):
        g.validate_item(row, name, managed=True)


@pytest.mark.parametrize('damage', ['provider', 'metadata-owner', 'pattern', 'metadata-value', 'extra-metadata'])
def test_metadata_semantics_and_single_owner_are_required(damage):
    g = guard(); name = next(iter(g.ITEMS)); row = item(name)
    if damage == 'provider': row['editable'] = False
    elif damage == 'metadata-owner': row['metadata']['stateDescription']['editable'] = False
    elif damage == 'pattern': row['stateDescription']['pattern'] = '%.1f s'
    elif damage == 'metadata-value': row['metadata']['stateDescription']['value'] = ''
    else: row['metadata']['other'] = {'value': 'x'}
    with pytest.raises(ValueError):
        g.validate_item(row, name, managed=True)


def test_exact_two_link_contracts_and_scoped_mutations():
    g = guard()
    for name, spec in g.ITEMS.items():
        link = {'itemName': name, 'channelUID': spec['channel'], 'configuration': {}, 'editable': True}
        g.validate_links([link], name, managed=True)
        wrong = deepcopy(link); wrong['channelUID'] += ':changed'
        with pytest.raises(ValueError): g.validate_links([wrong], name, managed=True)
        with pytest.raises(ValueError): g.validate_links([link, link], name, managed=True)
        g.allowed_mutation('DELETE', '/items/'+name, None)
        g.allowed_mutation('PUT', '/items/'+name, g.original_item(name))
        payload = {k: link[k] for k in ('itemName', 'channelUID', 'configuration')}
        g.allowed_mutation('PUT', g.link_path(name), payload)
        with pytest.raises(ValueError): g.allowed_mutation('PUT', g.link_path(name), {})
        g.allowed_mutation('DELETE', g.link_path(name), None)
        g.allowed_mutation('PUT', '/items/'+name+'/metadata/stateDescription', g.METADATA)


@pytest.mark.parametrize('method,path,body', [
    ('POST', '/items/WeatherData_WH31E_AgeSeconds', '7'),
    ('PUT', '/items/WeatherData_WH31E_AgeSeconds/state', '7'),
    ('DELETE', '/items/WeatherData_WH65B_AgeSeconds', None),
    ('DELETE', '/items/gWeatherHealth', None),
    ('POST', '/rules/sky-condition-calculator/runnow', None),
])
def test_mutations_outside_selected_definitions_are_refused(method, path, body):
    with pytest.raises(ValueError): guard().allowed_mutation(method, path, body)


def test_candidate_source_preserves_patterns_groups_and_channel_identity():
    g = guard(); text = g.SOURCE.read_text()
    assert set(g.ITEMS) == {'WeatherData_WH31E_AgeSeconds', 'WeatherData_WH32B_AgeSeconds'}
    for name, spec in g.ITEMS.items():
        assert f'Number {name} "{spec["label"]}" (gWeatherHealth)' in text
        assert 'channel="'+spec['channel']+'"' in text
    assert text.count('stateDescription=" " [ pattern="%.0f s" ]') == 2


def test_link_mutations_wait_for_all_native_rest_catalogs(monkeypatch):
    path = Path(__file__).with_name('qualify-weather-health-age-items.py')
    spec = importlib.util.spec_from_file_location('age_catalog_test', path)
    driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
    calls = []
    class StartingFixture(driver.Fixture):
        def rest(self, path):
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError('REST links HTTP 404 during registration')
            return []
    monkeypatch.setattr(driver.time, 'sleep', lambda _: None)
    StartingFixture().wait_catalogs()
    assert calls.count('/links') == 2
    assert '/things' in calls and '/rules' in calls


def test_inert_channel_registry_retains_identity_and_removes_endpoints():
    g = guard()
    channels = [{'uid': row['channel'], 'id': row['channel'].rsplit(':', 1)[-1],
                 'kind': 'STATE', 'itemType': 'Number', 'configuration': {'stateTransformation': 'private'},
                 'properties': {'private': 'value'}} for row in g.ITEMS.values()]
    channels.append({'uid': 'http:url:weatherHealth:healthStatus', 'kind': 'STATE', 'itemType': 'String'})
    original = {'class': 'org.openhab.core.thing.internal.ThingStorageEntity', 'value': {
        'UID': 'http:url:weatherHealth', 'thingTypeUID': 'http:url', 'isBridge': False,
        'channels': channels, 'configuration': {'baseURL': 'private endpoint'},
        'properties': {'private': 'value'}, 'label': 'original'}}
    frozen = deepcopy(original)
    inert = g.inert_fixture_thing(original)
    assert original == frozen
    assert inert['value']['configuration'] == {} and inert['value']['properties'] == {}
    assert len(inert['value']['channels']) == 2
    assert {c['uid'] for c in inert['value']['channels']} == {row['channel'] for row in g.ITEMS.values()}
    assert all(c['configuration'] == {} and c['properties'] == {} for c in inert['value']['channels'])
    dto = {**inert['value'], 'channels': [dict(c, linkedItems=[next(name for name, row in g.ITEMS.items()
            if row['channel'] == c['uid'])]) for c in inert['value']['channels']]}
    g.validate_fixture_thing(dto)
    with pytest.raises(ValueError): g.validate_fixture_thing({**dto, 'configuration': {'baseURL': 'endpoint'}})
    with pytest.raises(ValueError): g.inert_fixture_thing({**original, 'value': {**original['value'], 'UID': 'other'}})
    with pytest.raises(ValueError): g.inert_fixture_thing({**original, 'value': {**original['value'], 'channels': []}})


def test_channel_seed_rechecks_all_catalogs_after_its_restart(monkeypatch):
    path = Path(__file__).with_name('qualify-weather-health-age-items.py')
    spec = importlib.util.spec_from_file_location('age_seed_catalog_test', path)
    driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
    calls = []; thing_reads = 0; link_reads = 0
    thing = {'UID': 'http:url:weatherHealth', 'channels': [{'uid': row['channel']} for row in guard().ITEMS.values()]}
    class RestartingFixture(driver.Fixture):
        def info(self, cid): return {'State': {'Running': False}}
        def wait_group(self, managed): return None
        def rest(self, path):
            nonlocal thing_reads, link_reads
            calls.append(path)
            if path == '/things':
                thing_reads += 1
                return [] if thing_reads == 1 else [thing]
            if path == '/links':
                link_reads += 1
                if link_reads == 1: raise RuntimeError('post-restart links HTTP 404')
            return []
    monkeypatch.setattr(driver.q.f, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(driver.q.p, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(driver.time, 'sleep', lambda _: None)
    fixture = RestartingFixture(); fixture.oh = 'owned-fixture'
    fixture.seed_fixture_channels({'class': 'org.openhab.core.thing.internal.ThingStorageEntity', 'value': {}})
    assert calls.count('/links') == 2 and '/rules' in calls
