"""Pure source and provider guards for the hourly meteorology group."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_meteorology_provider',
    Path(__file__).with_name('qualify-openmeteo-forecast-meteorology-provider.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_prepared_source_has_exact_hourly_items_types_and_channels():
    source = module.provider.SOURCE.read_text()
    assert set(module.provider.CHANNELS) == set(module.provider.TYPES) == {
        'Forecast_Cloudiness', 'Forecast_Radiation', 'Forecast_PrecipProb'}
    assert source.count('(gForecast) ["forecast"] { channel="') == 3
    for name, channel in module.provider.CHANNELS.items():
        declaration = module.provider.TYPES[name] + ' ' + name + ' '
        assert source.count(declaration) == 1
        assert source.count('channel="' + channel + '"') == 1
