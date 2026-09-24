"""Pure exact-definition and mixed-unit guards for daily forecast transfer."""
from datetime import datetime, timezone
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_daily_transfer',
    Path(__file__).with_name('migrate-openmeteo-forecast-daily-items.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)
t = module.transfer


def test_closed_source_and_precipitation_state_unit():
    assert sha256(t.SOURCE.read_bytes()).hexdigest() == t.SOURCE_SHA256
    assert set(t.CHANNELS) == set(t.TYPES) == set(t.LABELS)
    assert module.valid_state('Forecast_Daily_PrecipSum', '0.5 in')
    assert module.valid_state('Forecast_Daily_PrecipSum', '12.7 mm')
    assert not module.valid_state('Forecast_Daily_PrecipSum', '0.5')
    assert not module.valid_state('Forecast_Daily_UVIndex', '2 in')
    assert module.valid_state('Forecast_Daily_WeatherCode', '65.0')
    assert t.same_state('12.7 mm', '0.5 in')
    assert not t.same_state('12.7 mm', '0.5')


def test_history_restore_formats_only_precipitation_with_length_unit():
    now = datetime(2026, 9, 23, 20, tzinfo=timezone.utc)
    rows = [(now.replace(hour=0), 0.5),
            (now.replace(hour=19), 0.9),
            (now.replace(day=24, hour=0), 9.9)]
    assert t.restore_state_from_history(rows, now, 'Forecast_Daily_PrecipSum') == '0.9 in'
    assert t.restore_state_from_history(rows, now, 'Forecast_Daily_PrecipProbMax') == '0.9'
