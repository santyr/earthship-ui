import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_energy_migration', ROOT / 'scripts/migrate-forecast-energy-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_staged_forecast_energy_items_are_exact_and_unlinked():
    source = (ROOT / 'openhab/file-config/items/forecast-energy.items').read_text()
    assert source.count('Number Predicted_PV_Today_kWh ') == 1
    assert source.count('Number Predicted_SoC_Trough_Tomorrow ') == 1
    assert source.count('["forecast-intel"]') == 2
    assert 'channel=' not in source


def test_live_adapter_is_guarded_and_preserves_numeric_state():
    assert migration.RELEASE_READY is True
    assert migration.migration.ITEM_TYPE == 'Number'
    assert migration.migration.NAMES == (
        'Predicted_PV_Today_kWh', 'Predicted_SoC_Trough_Tomorrow')
    assert migration.migration.same_state('59', '59.0')
    assert not migration.migration.same_state('NaN', '59.0')
