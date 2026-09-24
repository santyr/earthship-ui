#!/usr/bin/env python3
"""Guarded file-provider handoff of learned forecast temperature corrections."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

migration.NAMES = ('Forecast_HighCorrection_F', 'Forecast_LowCorrection_F')
migration.ITEM_TYPE = 'Number'
migration.SOURCE = ROOT / 'openhab/file-config/items/forecast-corrections.items'
migration.TARGET = Path('/etc/openhab/items/forecast-corrections.items')
migration.TIMER = 'forecast-intel.timer'
migration.SERVICE = 'forecast-intel.service'
migration.BACKUP_PREFIX = 'forecast-corrections'
RELEASE_READY = True  # Isolated provider/JDBC/rollback/restart proof passed.

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-forecast-correction-items.py --check|--apply')
    if sys.argv[1:] == ['--apply'] and not RELEASE_READY:
        raise SystemExit('forecast correction live cutover not release-qualified')
    migration.main(apply=sys.argv[1:] == ['--apply'])
