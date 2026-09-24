"""Pure guards for isolated forecast temperature JDBC/time-series recovery."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_temperature_jdbc',
    Path(__file__).with_name('qualify-openmeteo-forecast-temperature-jdbc.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_closed_group_and_future_series_counts():
    assert set(module.SCALARS) == set(module.NAMES) == set(module.SERIES)
    assert module.SERIES == {
        'Forecast_Temp': (48, 3600, 40),
        'Forecast_Daily_High': (7, 86400, 70),
        'Forecast_Daily_Low': (7, 86400, 30),
    }


def test_temperature_state_accepts_canonical_decimal_variants_only():
    assert module.same_temperature('68 °F', '68.0 °F')
    assert module.same_temperature('20.00000000000000000000000000000002 °C', '68 °F')
    assert not module.same_temperature('19 °C', '68 °F')
    assert not module.same_temperature('NULL', '68 °F')
    assert module.stored_temperature(68.0, '°F', '68 °F')
    assert module.stored_temperature(20.0, '°C', '68 °F')
    assert not module.stored_temperature(19.0, '°C', '68 °F')


def test_future_series_requires_every_timestamp_value_and_unit():
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for name, (count, step, base) in module.SERIES.items():
        rows = [((first + timedelta(seconds=index * step)).isoformat(),
                 str(base + index) + ' °F') for index in range(count)]
        assert module.assert_series(rows, name, first)
        assert not module.assert_series(rows[:-1], name, first)
        wrong = rows.copy()
        wrong[0] = (wrong[0][0], wrong[0][1].replace('°F', '°C'))
        assert not module.assert_series(wrong, name, first)
