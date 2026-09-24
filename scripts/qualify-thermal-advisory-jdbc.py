#!/usr/bin/env python3
"""Disconnected JDBC/state/rollback qualification for Thermal_Advisory."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_json_jdbc_qualifier', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)

if __name__ == '__main__':
    from_script = ROOT / 'scripts/migrate-thermal-advisory-item.py'
    migration_spec = importlib.util.spec_from_file_location('thermal_advisory_migration', from_script)
    migration = importlib.util.module_from_spec(migration_spec)
    migration_spec.loader.exec_module(migration)
    qualifier.main(items={'Thermal_Advisory': 'none|No thermal action needed'},
                   source_path=migration.migration.SOURCE,
                   types={'Thermal_Advisory': 'String'})
