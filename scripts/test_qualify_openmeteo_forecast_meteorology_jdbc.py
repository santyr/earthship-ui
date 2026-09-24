"""Pure mixed-unit guards for isolated hourly forecast JDBC recovery."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_meteorology_jdbc',
    Path(__file__).with_name('qualify-openmeteo-forecast-meteorology-jdbc.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_mixed_units_and_closed_group():
    assert set(module.fixture.NAMES) == set(module.fixture.TYPES) == set(module.fixture.SERIES)
    assert module.same_scalar('0.50000001', '0.5')
    assert module.same_scalar('100.00000001 W/m²', '100 W/m²')
    assert not module.same_scalar('100 W/m²', '100')
    assert not module.same_scalar('1', '0.5')
    assert module.stored_scalar(100, 'W/m²', '100 W/m²')
    assert not module.stored_scalar(100, 'kW/m²', '100 W/m²')
    assert not module.stored_scalar(1, '0.5', '0.5')


def test_all_future_series_values_are_checked():
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for name in module.fixture.NAMES:
        rows = [((first + timedelta(hours=i)).isoformat(),
                 float(module.series_value(name, i).split(' ', 1)[0])) for i in range(48)]
        observed_unit = 'W/m²' if name == 'Forecast_Radiation' else '0.5'
        assert module.fixture.assert_series(rows, name, first, observed_unit)
        wrong = rows.copy()
        wrong[-1] = (wrong[-1][0], 999.0)
        assert not module.fixture.assert_series(wrong, name, first, observed_unit)
