#!/usr/bin/env python3
"""Restore the original managed sky rule after an unqualified control-input cutover.

Only the exact sky file and backed-up rule are touched. Pumps are checked OFF
before the brief provider gap. No Item update, pump command or restart occurs.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'display_migration', ROOT / 'scripts/migrate-season-countdown-rule.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

CONFIG = migration.RULES['sky']
BACKUP = Path('/home/sat/.local/state/sky-rule-vxz_cwr2/managed-rule.json')
WITHDRAWN = BACKUP.parent / 'withdrawn-file.js'
PUMPS = ('SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power')


def main():
    migration.require(BACKUP.is_file() and not BACKUP.is_symlink()
                      and BACKUP.stat().st_mode & 0o777 == 0o600,
                      'private managed rollback missing or exposed')
    original = json.loads(BACKUP.read_text())
    migration.require(original.get('uid') == CONFIG.uid
                      and original.get('editable') is True
                      and migration.trigger_contract(original) == CONFIG.triggers
                      and migration.digest(original['actions'][0]['configuration']['script'].encode())
                      == CONFIG.script_sha, 'managed rollback definition changed')
    migration.require(not WITHDRAWN.exists() and not WITHDRAWN.is_symlink(),
                      'withdrawn backup target already exists')
    migration.require(CONFIG.target.is_file() and not CONFIG.target.is_symlink()
                      and migration.digest(CONFIG.target.read_bytes()) == CONFIG.source_sha,
                      'live sky file changed')
    migration.require(migration.file_rule_ok(migration.rule_or_none(CONFIG), CONFIG),
                      'live sky file rule not healthy')
    migration.require(all(migration.oh.get('/items/' + name).get('state') == 'OFF'
                          for name in PUMPS), 'greywater pump is not OFF')
    before = migration.output_states(CONFIG)
    migration.require(before['SkyCondition'] != 'CLEAR',
                      'sky control input currently allows pump eligibility')
    CONFIG.target.rename(WITHDRAWN)
    restored = False
    try:
        migration.wait_rule(lambda row: row is None, CONFIG)
        payload = {field: original[field] for field in migration.FIELDS if field in original}
        migration.require(migration.request('POST', '/rules', payload) == 201,
                          'managed sky rule recreation refused')
        migration.wait_rule(lambda row: migration.managed_rule_ok(row, original), CONFIG)
        restored = True
    finally:
        if not restored and migration.rule_or_none(CONFIG) is None and WITHDRAWN.exists():
            WITHDRAWN.rename(CONFIG.target)
            migration.wait_rule(lambda row: migration.file_rule_ok(row, CONFIG), CONFIG)
            print('file_rule_restored_after_failed_managed_rollback=true', flush=True)
    migration.require(migration.output_states(CONFIG) == before,
                      'sky output changed during rollback; inspect current inputs')
    migration.require(sum(rule.get('uid') == CONFIG.uid
                          for rule in migration.oh.get('/rules')) == 1,
                      'sky rule identity duplicated after rollback')
    migration.require(all(migration.oh.get('/items/' + name).get('state') == 'OFF'
                          for name in PUMPS), 'pump state changed during rollback')
    print('managed_sky_rule_restored=true; file_withdrawn=' + str(WITHDRAWN), flush=True)


if __name__ == '__main__':
    main()
