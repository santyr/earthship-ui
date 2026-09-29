#!/usr/bin/env python3
"""Guarded, attended file handoff for the passive SkyConditionIcon Item.

The sky-condition rule is never paused: it also writes the control-relevant
SkyCondition Item. An icon/state/history drift aborts the handoff. No synthetic
production update or rule invocation is permitted here.
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

ITEM = 'SkyConditionIcon'
RULE = 'sky-condition-calculator'
WRITER_SHA256 = 'd99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c'
ITEM_ID = 173
SOURCE = ROOT / 'openhab/file-config/items/sky-condition-icon.items'
TARGET = Path('/etc/openhab/items/sky-condition-icon.items')
DEFINITION = 'String SkyConditionIcon "Sky Condition Icon" <sun_clouds> ["Status"]'
RELEASE_READY = True  # Isolated provider/JDBC/rollback, focused tests and exact live preflight passed.

migration.NAMES = (ITEM,)
migration.ITEM_TYPE = 'String'
migration.SOURCE = SOURCE
migration.TARGET = TARGET
migration.BACKUP_PREFIX = 'sky-condition-icon'


def rule_idle():
    rule = migration.oh.get('/rules/' + RULE)
    migration.require(rule.get('uid') == RULE and rule.get('status') == {
        'status': 'IDLE', 'statusDetail': 'NONE'}, 'sky-condition writer not idle')
    scripts = [action.get('configuration', {}).get('script')
               for action in rule.get('actions', [])
               if action.get('configuration', {}).get('script')]
    migration.require(len(scripts) == 1 and
                      sha256(scripts[0].encode()).hexdigest() == WRITER_SHA256,
                      'sky-condition writer source drift')
    return rule


def preflight(db):
    migration.require(not TARGET.exists() and not TARGET.is_symlink(),
                      'sky-icon file target already exists')
    source = SOURCE.read_bytes()
    definitions = [line.strip() for line in source.decode().splitlines()
                   if line.strip() and not line.lstrip().startswith('//')]
    migration.require(definitions == [DEFINITION], 'sky-icon source changed')
    original = migration.item(ITEM)
    migration.require(original is not None and original.get('editable') is True
                      and original.get('type') == 'String'
                      and original.get('state') not in (None, 'NULL', 'UNDEF'),
                      'managed sky-icon Item/state unavailable')
    migration.require(not any(link.get('itemName') == ITEM
                              for link in migration.oh.get('/links')),
                      'sky-icon Item unexpectedly linked')
    rule_idle()
    history = migration.history(db, ITEM)
    migration.require(history['id'] == ITEM_ID and
                      history['last_state'] == original['state'],
                      'Item 173 history/state drift')
    return original, history, sha256(source).hexdigest()


def backup_history(db, directory):
    """Keep a private exact-data copy in addition to the registry receipt."""
    data = io.StringIO()
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='20s'")
        cursor.copy_expert('COPY (SELECT time,value FROM public.item0173 '
                           'ORDER BY time,value) TO STDOUT WITH CSV', data)
    body = data.getvalue().encode()
    migration.save_private(directory, 'item0173.csv', body)
    migration.require(sha256((directory / 'item0173.csv').read_bytes()).digest()
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
                          'sky-icon state changed before transfer')
        migration.require(migration.history(db, ITEM) == history,
                          'sky-icon history changed before transfer')
        migration.require(sha256(SOURCE.read_bytes()).hexdigest() == source_hash,
                          'sky-icon source changed before transfer')
        changed = True
        migration.request('DELETE', ITEM)
        migration.wait(ITEM, original, None)
        subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                       check=True, timeout=15)
        migration.require(sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                          'installed sky-icon source differs')
        migration.wait(ITEM, original, False)
        migration.require(migration.history(db, ITEM) == history,
                          'Item 173 history changed during transfer')
        migration.require(not any(link.get('itemName') == ITEM
                                  for link in migration.oh.get('/links')),
                          'unexpected sky-icon link appeared')
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
                                  'unknown sky-icon target; manual recovery required')
                TARGET.rename(directory / 'failed.items')
                migration.wait(ITEM, original, None)
            if migration.item(ITEM) is None:
                migration.request('PUT', ITEM, {key: original[key]
                                  for key in migration.FIELDS if key in original})
            migration.wait(ITEM, original, True)
            migration.require(migration.history(db, ITEM) == history,
                              'Item 173 history changed during rollback')
            print('managed_rollback_verified=true', flush=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-sky-condition-icon.py --check|--apply')
    if argv == ['--apply'] and not RELEASE_READY:
        raise SystemExit('sky-icon live cutover not release-qualified')
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
