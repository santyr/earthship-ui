"""Pure exact-Group and member-reference guards for isolated rehearsal."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json

spec = spec_from_file_location('forecast_group_provider',
    Path(__file__).with_name('qualify-forecast-group-provider.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_source_has_one_exact_group_declaration():
    source = module.SOURCE.read_text()
    assert source.count('Group gForecast "Forecast Items" ["forecast"]') == 1
    root = module.ROOT / 'openhab/file-config'
    managed = json.loads((root / 'managed-exceptions/gForecast.json').read_text())
    assert managed == {'name': 'gForecast', 'type': 'Group',
                       'label': 'Forecast Items', 'category': None,
                       'tags': ['forecast'], 'groupNames': []}
    ownership = json.loads((root / 'ownership.json').read_text())
    assert [row for row in ownership['resources']
            if row['kind'] == 'item' and row['id'] == 'gForecast'] == [{
                'kind': 'item', 'id': 'gForecast', 'provider': 'file',
                'migration': 'verified',
                'source': 'items/forecast-group.items',
                'destination': '/etc/openhab/items/forecast-group.items'}]


def test_group_match_requires_provider_fields_and_all_members(monkeypatch):
    original = {'name': 'gForecast', 'type': 'Group', 'label': 'Forecast Items',
                'category': None, 'tags': ['forecast'], 'groupNames': []}
    members = {'Forecast_Temp', 'Forecast_Radiation'}
    group = {**original, 'editable': False}
    rows = [{'name': name, 'groupNames': ['gForecast']} for name in members]

    def get(_, path, __):
        return (200, group) if path.startswith('/items/gForecast') else (200, rows)

    monkeypatch.setattr(module.aqi, 'isolated_get', get)
    assert module.matches('container', b'', original, members, file_owned=True)
    rows.pop()
    assert not module.matches('container', b'', original, members, file_owned=True)
    rows[:] = [{'name': name, 'groupNames': ['gForecast']} for name in members]
    group['editable'] = True
    assert not module.matches('container', b'', original, members, file_owned=True)
