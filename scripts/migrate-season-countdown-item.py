#!/usr/bin/env python3
"""Guarded display-only countdown Item handoff; no synthetic Item updates.

--check is read-only. --apply requires a separate release decision after an
isolated rehearsal and exact live preflight. The Astro-driven writer is never
paused, and an unexpected state/history change aborts the transfer.
"""
import importlib.util
import io
import json
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

ITEM = 'DaysUntilNextSeason'
RULE = 'update_days_until_season'
WRITER_SHA256 = 'd101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36'
ITEM_ID = 176
SOURCE = ROOT / 'openhab/file-config/items/days-until-next-season.items'
TARGET = Path('/etc/openhab/items/days-until-next-season.items')
DEFINITION = 'String DaysUntilNextSeason "Days Until Next Season" <calendar>'
RELEASE_READY = False  # Attended one-shot cutover completed; no repeat transfer authorized.

migration.NAMES = (ITEM,)
migration.ITEM_TYPE = 'String'
migration.SOURCE = SOURCE
migration.TARGET = TARGET
migration.BACKUP_PREFIX = 'season-countdown-item'


def rule_idle():
    rule = migration.oh.get('/rules/' + RULE)
    migration.require(rule.get('uid') == RULE and rule.get('editable') is False
                      and rule.get('status') == {
                          'status': 'IDLE', 'statusDetail': 'NONE'},
                      'season countdown file writer unavailable')
    migration.require(
        len(rule.get('triggers', [])) == 1 and
        rule['triggers'][0].get('type') == 'core.ItemStateChangeTrigger' and
        rule['triggers'][0].get('configuration') == {'itemName': 'Sun_TimeLeft'} and
        rule.get('conditions') == [] and
        len(rule.get('actions', [])) == 1 and
        rule['actions'][0].get('type') == 'jsr223.ScriptedAction' and
        rule['actions'][0].get('configuration') == {'privId': 'i0'},
        'season countdown writer registry drift')
    installed = Path('/etc/openhab/automation/js/update_days_until_season.js')
    migration.require(installed.is_file() and not installed.is_symlink() and
                      sha256(installed.read_bytes()).hexdigest() == WRITER_SHA256,
                      'season countdown writer source drift')
    return rule


def preflight(db):
    migration.require(not TARGET.exists() and not TARGET.is_symlink(),
                      'countdown file target already exists')
    source = SOURCE.read_bytes()
    definitions = [line.strip() for line in source.decode().splitlines()
                   if line.strip() and not line.lstrip().startswith('//')]
    migration.require(definitions == [DEFINITION], 'countdown source changed')
    original = migration.item(ITEM)
    migration.require(original is not None and original.get('editable') is True
                      and original.get('name') == ITEM
                      and original.get('type') == 'String'
                      and original.get('label') == 'Days Until Next Season'
                      and original.get('category') == 'calendar'
                      and original.get('state') not in (None, 'NULL', 'UNDEF')
                      and not original.get('tags')
                      and not original.get('groupNames')
                      and not original.get('metadata'),
                      'managed countdown Item definition/state unavailable')
    migration.require(not any(link.get('itemName') == ITEM
                              for link in migration.oh.get('/links')),
                      'countdown Item unexpectedly linked')
    rule_idle()
    history = migration.history(db, ITEM)
    migration.require(history['id'] == ITEM_ID and
                      history['last_state'] == original['state'],
                      'Item 176 history/state drift')
    return original, history, sha256(source).hexdigest()


def backup_history(db, directory):
    data = io.StringIO()
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='20s'")
        cursor.copy_expert('COPY (SELECT time,value FROM public.item0176 '
                           'ORDER BY time,value) TO STDOUT WITH CSV', data)
    body = data.getvalue().encode()
    migration.save_private(directory, 'item0176.csv', body)
    migration.require(sha256((directory / 'item0176.csv').read_bytes()).digest()
                      == sha256(body).digest(), 'private history copy mismatch')
    handle = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def apply(db, original, history, source_hash):
    directory = migration.backup({ITEM: original}, {ITEM: history}, source_hash)
    backup_history(db, directory)
    print('private_backup=' + str(directory), flush=True)
    changed = success = False
    try:
        rule_idle()
        migration.require(migration.item(ITEM) == original,
                          'countdown state changed before transfer')
        migration.require(migration.history(db, ITEM) == history,
                          'countdown history changed before transfer')
        migration.require(sha256(SOURCE.read_bytes()).hexdigest() == source_hash,
                          'countdown source changed before transfer')
        changed = True
        migration.request('DELETE', ITEM)
        migration.wait(ITEM, original, None)
        subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                       check=True, timeout=15)
        migration.require(sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                          'installed countdown source differs')
        migration.wait(ITEM, original, False)
        migration.require(migration.history(db, ITEM) == history,
                          'Item 176 history changed during file handoff')

        # Exercise the actual managed rollback before accepting file ownership.
        TARGET.rename(directory / 'rollback.items')
        migration.wait(ITEM, original, None)
        migration.request('PUT', ITEM, {key: original[key]
                          for key in migration.FIELDS if key in original})
        migration.wait(ITEM, original, True)
        migration.require(migration.history(db, ITEM) == history,
                          'Item 176 history changed during managed rollback')
        migration.request('DELETE', ITEM)
        migration.wait(ITEM, original, None)
        (directory / 'rollback.items').rename(TARGET)
        migration.wait(ITEM, original, False)
        migration.require(migration.history(db, ITEM) == history,
                          'Item 176 history changed on return to file provider')
        rule_idle()
        migration.require(not any(link.get('itemName') == ITEM
                                  for link in migration.oh.get('/links')),
                          'unexpected countdown link appeared')
        success = True
        print(json.dumps({'status': 'file_provider_provisional', 'item': ITEM,
                          'jdbc_id': ITEM_ID, 'history_rows': history['count'],
                          'backup': str(directory), 'natural_writer_pending': True},
                         sort_keys=True), flush=True)
    finally:
        if changed and not success:
            if TARGET.exists():
                migration.require(not TARGET.is_symlink() and
                                  sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                                  'unknown countdown target; manual recovery required')
                TARGET.rename(directory / 'failed.items')
                migration.wait(ITEM, original, None)
            if migration.item(ITEM) is None:
                migration.request('PUT', ITEM, {key: original[key]
                                  for key in migration.FIELDS if key in original})
            migration.wait(ITEM, original, True)
            migration.require(migration.history(db, ITEM) == history,
                              'Item 176 history changed during failure rollback')
            print('managed_rollback_verified=true', flush=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-season-countdown-item.py --check|--apply')
    if argv == ['--apply'] and not RELEASE_READY:
        raise SystemExit('countdown Item live cutover not release-qualified')
    settings = migration.parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config')
    db = migration.psycopg2.connect(**settings.connect_kwargs, connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        original, history, source_hash = preflight(db)
        if argv == ['--check']:
            print(json.dumps({'status': 'preflight_passed', 'item': ITEM,
                              'jdbc_id': ITEM_ID, 'history_rows': history['count'],
                              'source_sha256': source_hash}, sort_keys=True))
        else:
            apply(db, original, history, source_hash)
    finally:
        db.close()


if __name__ == '__main__':
    main()
