"""The isolated AQI provider rehearsal uses only closed, exact candidates."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('qualify_openmeteo_aqi_item',
    Path(__file__).with_name('qualify-openmeteo-aqi-item.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_current_candidate_remains_the_default_verified_resource():
    assert module.CANDIDATES['current'] == (
        module.ROOT / 'openhab/file-config/items/openmeteo-current-aqi.items',
        'Current_US_AQI', 'openmeteo:air-quality:local:aq:current#us-aqi')
    assert (module.SOURCE, module.ITEM, module.CHANNEL) == module.CANDIDATES['current']


def test_forecast_candidate_is_exact_and_not_live_owned():
    assert set(module.CANDIDATES) == {'current', 'forecast'}
    assert module.CANDIDATES['forecast'] == (
        module.ROOT / 'openhab/file-config/items/openmeteo-forecast-aqi.items',
        'Forecast_AQI',
        'openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string')


def test_managed_rollback_omits_absent_category_but_preserves_present_metadata():
    original = {'name': 'Forecast_AQI', 'type': 'String',
                'label': 'US Air Quality Index', 'tags': ['forecast'],
                'groupNames': []}
    assert module.managed_item_dto(original) == original
    with_category = {**original, 'category': 'airquality'}
    assert module.managed_item_dto(with_category) == with_category
