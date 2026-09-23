"""The isolated AQI JDBC recovery harness supports only exact resources."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('qualify_openmeteo_aqi_jdbc',
    Path(__file__).with_name('qualify-openmeteo-aqi-jdbc.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_closed_aqi_jdbc_candidates_preserve_the_default():
    assert set(module.CANDIDATES) == {'current', 'forecast'}
    assert module.CANDIDATES['current'] == (
        'Current_US_AQI', module.ROOT / 'openhab/file-config/items/openmeteo-current-aqi.items')
    assert module.CANDIDATES['forecast'] == (
        'Forecast_AQI', module.ROOT / 'openhab/file-config/items/openmeteo-forecast-aqi.items')
    assert module.ITEM == module.CANDIDATES['current'][0]
