"""Exact source and release guards for tomorrow's forecast values."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_tomorrow_migration', ROOT / 'scripts/migrate-forecast-tomorrow-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_staged_source_exactly_matches_batch_without_links():
    source = migration.migration.SOURCE.read_text()
    for name in migration.migration.NAMES:
        assert source.count('Number ' + name + ' ') == 1
    assert source.count('\nNumber ') == len(migration.migration.NAMES)
    assert source.count('["forecast-intel"]') == len(migration.migration.NAMES)
    assert 'channel=' not in source


def test_live_cutover_released_after_isolated_qualification():
    assert migration.RELEASE_READY is True
    assert migration.migration.ITEM_TYPE == 'Number'
    assert migration.migration.TIMER == 'forecast-intel.timer'
