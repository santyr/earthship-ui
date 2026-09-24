#!/usr/bin/env python3
"""Guarded file-provider handoff of the forecast thermal advisory Item."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

migration.NAMES = ('Thermal_Advisory',)
migration.ITEM_TYPE = 'String'
migration.SOURCE = ROOT / 'openhab/file-config/items/thermal-advisory.items'
migration.TARGET = Path('/etc/openhab/items/thermal-advisory.items')
migration.TIMER = 'forecast-intel.timer'
migration.SERVICE = 'forecast-intel.service'
migration.BACKUP_PREFIX = 'thermal-advisory'
RELEASE_READY = True  # Isolated provider/JDBC/rollback/restart proof passed.

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-thermal-advisory-item.py --check|--apply')
    if sys.argv[1:] == ['--apply'] and not RELEASE_READY:
        raise SystemExit('thermal advisory live cutover not release-qualified')
    migration.main(apply=sys.argv[1:] == ['--apply'])
