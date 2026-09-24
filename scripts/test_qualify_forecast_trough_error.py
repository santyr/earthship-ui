import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_trough_error_migration', ROOT / 'scripts/migrate-forecast-trough-error-item.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_staged_trough_error_item_has_exact_format_and_no_link():
    source = (ROOT / 'openhab/file-config/items/forecast-trough-error.items').read_text()
    assert source.count('Number Forecast_Trough_Error_7d ') == 1
    assert '"Trough Forecast Error (7d rolling) [%.0f]"' in source
    assert '["forecast-intel"]' in source
    assert 'channel=' not in source


def test_live_adapter_remains_guarded_and_numeric():
    assert migration.RELEASE_READY is True
    assert migration.migration.ITEM_TYPE == 'Number'
    assert migration.migration.NAMES == ('Forecast_Trough_Error_7d',)
    assert migration.migration.same_state('4', '4.0')
