"""Exact source and release guards for the thermal advisory Item."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'thermal_advisory_migration', ROOT / 'scripts/migrate-thermal-advisory-item.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_staged_source_matches_item_without_link():
    source = migration.migration.SOURCE.read_text()
    assert source.count('String Thermal_Advisory ') == 1
    assert source.count('~<') == 0
    assert '["forecast-intel"]' in source
    assert 'channel=' not in source


def test_live_cutover_released_after_isolated_qualification():
    assert migration.RELEASE_READY is True
    assert migration.migration.ITEM_TYPE == 'String'
    assert migration.migration.TIMER == 'forecast-intel.timer'
