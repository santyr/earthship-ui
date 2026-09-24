#!/usr/bin/env python3
"""Disposable, networkless provider qualification for tomorrow Items."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_provider_qualifier', ROOT / 'scripts/qualify-forecast-json-file-provider.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    from_script = ROOT / 'scripts/migrate-forecast-tomorrow-items.py'
    migration_spec = importlib.util.spec_from_file_location('forecast_tomorrow_migration', from_script)
    migration = importlib.util.module_from_spec(migration_spec)
    migration_spec.loader.exec_module(migration)
    qualifier.main(names=migration.migration.NAMES,
                   source_path=migration.migration.SOURCE, item_type='Number')
