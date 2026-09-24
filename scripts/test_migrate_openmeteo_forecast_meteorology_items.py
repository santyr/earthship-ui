"""Pure fail-closed guards for the mixed-unit hourly forecast transfer."""
from datetime import datetime, timezone
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('forecast_meteorology_transfer',
    Path(__file__).with_name('migrate-openmeteo-forecast-meteorology-items.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)
t = module.transfer


def test_closed_source_identity_and_scalar_units():
    assert sha256(t.SOURCE.read_bytes()).hexdigest() == t.SOURCE_SHA256
    assert set(t.CHANNELS) == set(t.TYPES) == set(t.LABELS)
    assert module.valid_state('Forecast_Cloudiness', '0.5')
    assert module.valid_state('Forecast_PrecipProb', '0.16')
    assert module.valid_state('Forecast_Radiation', '0 W/m²')
    assert not module.valid_state('Forecast_Radiation', '0')
    assert not module.valid_state('Forecast_Cloudiness', '0 W/m²')
    assert not module.same_state('0.5', '0.6')
    assert module.same_state('0.50000001', '0.5')
    assert not module.same_state('0 W/m²', '0')


def test_latest_past_jdbc_state_uses_item_unit_and_excludes_future():
    now = datetime(2026, 9, 23, 20, tzinfo=timezone.utc)
    rows = [(now.replace(hour=0), 100.0),
            (now.replace(hour=19), 55.0),
            (now.replace(day=24, hour=0), 999.0)]
    assert t.restore_state_from_history(rows, now, 'Forecast_Radiation') == '55.0 W/m²'
    assert t.restore_state_from_history(rows, now, 'Forecast_Cloudiness') == '55.0'
