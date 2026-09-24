#!/usr/bin/env python3
"""Disconnected JDBC/state/rollback qualification for forecast diagnostics."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    from_script = ROOT / 'scripts/migrate-forecast-quality-items.py'
    migration_spec = importlib.util.spec_from_file_location('forecast_quality_migration', from_script)
    migration = importlib.util.module_from_spec(migration_spec)
    migration_spec.loader.exec_module(migration)
    names = migration.migration.NAMES
    qualifier.main(items={name: str(index + 0.25) for index, name in enumerate(names)},
                   source_path=migration.migration.SOURCE,
                   types={name: 'Number' for name in names})
