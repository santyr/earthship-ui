#!/usr/bin/env python3
"""Guarded observational Number Item transfer; default is read-only preflight."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

migration.NAMES = ('Forecast_Trough_Error_7d',)
migration.ITEM_TYPE = 'Number'
migration.SOURCE = ROOT / 'openhab/file-config/items/forecast-trough-error.items'
migration.TARGET = Path('/etc/openhab/items/forecast-trough-error.items')
migration.TIMER = 'forecast-intel.timer'
migration.SERVICE = 'forecast-intel.service'
migration.BACKUP_PREFIX = 'forecast-trough-error'
RELEASE_READY = False

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-forecast-trough-error-item.py --check|--apply')
    if sys.argv[1:] == ['--apply'] and not RELEASE_READY:
        raise SystemExit('live cutover withheld until post-06:40 forecast verification')
    migration.main(apply=sys.argv[1:] == ['--apply'])
