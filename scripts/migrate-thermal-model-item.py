#!/usr/bin/env python3
"""Attended observational thermal Item transfer; default is read-only preflight."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

migration.NAMES = ('Thermal_Model_JSON',)
migration.SOURCE = ROOT / 'openhab/file-config/items/thermal-model-shadow.items'
migration.TARGET = Path('/etc/openhab/items/thermal-model-shadow.items')
migration.TIMER = 'thermal-model-shadow.timer'
migration.SERVICE = 'thermal-model-shadow.service'
migration.BACKUP_PREFIX = 'thermal-model-shadow'

if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--apply']):
        raise SystemExit('usage: migrate-thermal-model-item.py [--apply]')
    migration.main(apply=sys.argv[1:] == ['--apply'])
