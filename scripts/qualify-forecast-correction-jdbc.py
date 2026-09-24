#!/usr/bin/env python3
"""Disconnected JDBC/state/rollback qualification for correction Items."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    from_script = ROOT / 'scripts/migrate-forecast-correction-items.py'
    migration_spec = importlib.util.spec_from_file_location('forecast_correction_migration', from_script)
    migration = importlib.util.module_from_spec(migration_spec)
    migration_spec.loader.exec_module(migration)
    names = migration.migration.NAMES
    qualifier.main(items={names[0]: '3.3', names[1]: '-7.2'},
                   source_path=migration.migration.SOURCE,
                   types={name: 'Number' for name in names})
