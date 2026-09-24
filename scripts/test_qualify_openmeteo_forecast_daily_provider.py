"""Pure source guard for the four bound OpenMeteo daily forecast Items."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_daily_provider',
    Path(__file__).with_name('qualify-openmeteo-forecast-daily-provider.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_prepared_daily_source_matches_closed_item_link_group():
    source = module.provider.SOURCE.read_text()
    assert set(module.provider.CHANNELS) == set(module.provider.TYPES)
    assert len(module.provider.CHANNELS) == 4
    assert source.count('(gForecast) ["forecast"] { channel="') == 4
    for name, channel in module.provider.CHANNELS.items():
        assert source.count(module.provider.TYPES[name] + ' ' + name + ' ') == 1
        assert source.count('channel="' + channel + '"') == 1
