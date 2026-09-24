"""Pure mixed-unit guards for isolated daily forecast JDBC recovery."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_daily_jdbc',
    Path(__file__).with_name('qualify-openmeteo-forecast-daily-jdbc.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_precipitation_length_conversion_and_unitless_values():
    assert module.same_scalar('12.7 mm', '0.5 in')
    assert module.stored_scalar(12.7, 'mm', '0.5 in')
    assert not module.same_scalar('0.5', '0.5 in')
    assert not module.stored_scalar(0.5, 'cm', '0.5 in')
    assert module.same_scalar('65.0', '65')
    assert not module.same_scalar('NULL', '65')
    assert module.stored_past_value('Forecast_Daily_PrecipSum', 'mm') == '22.86'


def test_four_daily_series_require_seven_matching_targets():
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert len(module.fixture.NAMES) == 4
    for name in module.fixture.NAMES:
        rows = [((first + timedelta(days=i)).isoformat(),
                 float(module.series_value(name, i).split(' ', 1)[0]))
                for i in range(7)]
        unit = 'in' if name == 'Forecast_Daily_PrecipSum' else '2.9'
        assert module.fixture.assert_series(rows, name, first, unit)
        assert not module.fixture.assert_series(rows[:-1], name, first, unit)
