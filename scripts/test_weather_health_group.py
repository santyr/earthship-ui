"""Cold edits must preserve member references and refuse a changed Group."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest

GROUP_RECORD = {
    'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
    'value': {'groupNames': [], 'itemType': 'Group', 'tags': [],
              'label': 'Weather Health', 'category': ''},
}
MEMBERS = ('SkyCondition_Diagnostic', 'SkyCondition_LastEval',
           'WeatherData_HealthStatus', 'WeatherData_WH31E_AgeSeconds',
           'WeatherData_WH32B_AgeSeconds', 'WeatherData_WH65B_AgeSeconds')


def tools():
    path = Path(__file__).with_name('weather_health_group.py')
    try:
        spec = importlib.util.spec_from_file_location('weather_health_group_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except FileNotFoundError:
        pytest.fail('weather-health cold transformer is not implemented')


def registry():
    result = {'gWeatherHealth': deepcopy(GROUP_RECORD), 'Unrelated': {
        'class': 'untouched', 'value': {'itemType': 'Switch', 'tags': ['keep']}}}
    for name in MEMBERS:
        result[name] = {'class': 'member', 'value': {'groupNames': ['gWeatherHealth'],
            'itemType': 'String', 'label': name}}
    return result


def test_cold_round_trip_preserves_every_other_record_and_reference():
    module = tools(); original = registry()
    removed = json.loads(module.cold_edit(json.dumps(original).encode(),
                                         remove=True, original=GROUP_RECORD))
    assert set(removed) == {'Unrelated', *MEMBERS}
    assert all(removed[name] == original[name] for name in removed)
    restored = json.loads(module.cold_edit(json.dumps(removed).encode(),
                                         remove=False, original=GROUP_RECORD))
    assert restored == original


@pytest.mark.parametrize('change', ['label', 'function', 'extra_member', 'missing_member'])
def test_changed_group_or_membership_refuses_cold_transfer(change):
    module = tools(); rows = registry()
    if change == 'label': rows['gWeatherHealth']['value']['label'] = 'Changed'
    if change == 'function': rows['gWeatherHealth']['value']['function'] = 'SUM'
    if change == 'extra_member': rows['Other'] = {'value': {'groupNames': ['gWeatherHealth']}}
    if change == 'missing_member': rows[MEMBERS[0]]['value']['groupNames'] = []
    with pytest.raises(RuntimeError):
        module.cold_edit(json.dumps(rows).encode(), remove=True, original=GROUP_RECORD)


def test_restore_refuses_an_existing_provider_record():
    module = tools()
    with pytest.raises(RuntimeError):
        module.cold_edit(json.dumps(registry()).encode(), remove=False,
                         original=GROUP_RECORD)


@pytest.mark.parametrize('remove', [None, 1, 'false'])
def test_non_boolean_operation_cannot_select_a_cold_edit(remove):
    module = tools()
    with pytest.raises(RuntimeError):
        module.cold_edit(json.dumps(registry()).encode(), remove=remove,
                         original=GROUP_RECORD)


def group_item():
    return {'name': 'gWeatherHealth', 'type': 'Group', 'label': 'Weather Health',
            'category': '', 'tags': [], 'groupNames': [], 'state': 'NULL',
            'editable': True, 'members': [{'name': name} for name in MEMBERS]}


def test_plain_group_descriptor_and_exact_six_members_are_accepted():
    module = tools(); module.validate_group(group_item(), managed=True)


@pytest.mark.parametrize('change', ['stateDescription', 'unitSymbol', 'duplicate_member'])
def test_group_behavior_or_duplicate_members_cannot_be_hidden(change):
    module = tools(); item = group_item()
    if change == 'stateDescription': item['stateDescription'] = {'pattern': '%s'}
    if change == 'unitSymbol': item['unitSymbol'] = 's'
    if change == 'duplicate_member': item['members'].append({'name': MEMBERS[0]})
    with pytest.raises(RuntimeError): module.validate_group(item, managed=True)


def test_group_link_is_rejected_before_backups_or_broader_preflight(tmp_path, monkeypatch):
    path = Path(__file__).with_name('qualify-weather-health-group.py')
    spec = importlib.util.spec_from_file_location('weather_qualifier_scope_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def get(path):
        if path == '/items/gWeatherHealth?metadata=.*': return group_item()
        if path == '/links': return [{'itemName': 'gWeatherHealth', 'channelUID': 'unexpected:input'}]
        raise AssertionError('linked Group reached broader production preflight')
    monkeypatch.setattr(module.b.oh, 'get', get)
    with pytest.raises(RuntimeError, match='linked'):
        module.capture(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_file_provider_null_category_preserves_the_original_absent_icon():
    module = tools(); item = group_item(); item['category'] = None
    module.validate_group(item, managed=True)


def test_nonempty_category_cannot_be_accepted_as_the_original_absent_icon():
    module = tools(); item = group_item(); item['category'] = 'pump'
    with pytest.raises(RuntimeError): module.validate_group(item, managed=True)
