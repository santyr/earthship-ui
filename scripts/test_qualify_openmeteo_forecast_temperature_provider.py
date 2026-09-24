"""Pure guards for the isolated forecast-temperature provider rehearsal."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_temperature_provider',
    Path(__file__).with_name('qualify-openmeteo-forecast-temperature-provider.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_prepared_source_has_only_exact_forecast_group_members_and_links():
    source = module.SOURCE.read_text()
    assert set(module.CHANNELS) == {
        'Forecast_Temp', 'Forecast_Daily_High', 'Forecast_Daily_Low'}
    assert source.count('Number:Temperature ') == 3
    for name, channel in module.CHANNELS.items():
        assert source.count('Number:Temperature ' + name + ' ') == 1
        assert source.count('(gForecast) ["forecast"] { channel="' + channel + '" }') == 1


def test_provider_match_requires_all_three_exact_links(monkeypatch):
    originals = {}
    links = []
    for name, channel in module.CHANNELS.items():
        originals[name] = {'name': name, 'type': 'Number:Temperature',
                           'label': name, 'category': None, 'tags': ['forecast'],
                           'groupNames': ['gForecast']}
        links.append({'itemName': name, 'channelUID': channel,
                      'configuration': {}, 'editable': False})

    def get(_, path, __):
        if path == '/links':
            return 200, links
        name = path.split('/')[2].split('?')[0]
        return 200, {**originals[name], 'editable': False}

    monkeypatch.setattr(module.aqi, 'isolated_get', get)
    assert module.definitions_match('isolated', b'', originals, file_owned=True)
    links[1]['channelUID'] += '-wrong'
    assert not module.definitions_match('isolated', b'', originals, file_owned=True)
