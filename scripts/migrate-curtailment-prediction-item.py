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

migration.NAMES = ('Predicted_Curtailment_Hours',)
migration.ITEM_TYPE = 'Number'
migration.SOURCE = ROOT / 'openhab/file-config/items/predicted-curtailment.items'
migration.TARGET = Path('/etc/openhab/items/predicted-curtailment.items')
migration.TIMER = 'forecast-intel.timer'
migration.SERVICE = 'forecast-intel.service'
migration.BACKUP_PREFIX = 'predicted-curtailment'
RELEASE_READY = False

if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-curtailment-prediction-item.py --check|--apply')
    if sys.argv[1:] == ['--apply'] and not RELEASE_READY:
        raise SystemExit('live cutover withheld until post-06:40 forecast verification')
    migration.main(apply=sys.argv[1:] == ['--apply'])
