#!/usr/bin/env python3
"""Guarded file-provider handoff of seven observational forecast diagnostics."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

migration.NAMES = (
    'Forecast_PV_Error_7d', 'Forecast_Precip_Error_7d',
    'Forecast_TempHigh_Error_7d', 'Forecast_TempHigh_Bias_7d',
    'Forecast_TempLow_Error_7d', 'Forecast_Day3_High_Error_7d',
    'Forecast_Day3_Precip_Error_7d',
)
migration.ITEM_TYPE = 'Number'
migration.SOURCE = ROOT / 'openhab/file-config/items/forecast-quality.items'
migration.TARGET = Path('/etc/openhab/items/forecast-quality.items')
migration.TIMER = 'forecast-intel.timer'
migration.SERVICE = 'forecast-intel.service'
migration.BACKUP_PREFIX = 'forecast-quality'
RELEASE_READY = True  # Seven-Item provider/JDBC/rollback/restart rehearsal passed.

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-forecast-quality-items.py --check|--apply')
    if sys.argv[1:] == ['--apply'] and not RELEASE_READY:
        raise SystemExit('forecast quality live cutover not release-qualified')
    migration.main(apply=sys.argv[1:] == ['--apply'])
