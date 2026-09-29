#!/usr/bin/env python3
"""Guarded BatteryIcon file handoff; the dual-output rule is never paused."""
from dataclasses import asdict
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'attended_item_migration', ROOT / 'scripts/migrate-forecast-json-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
sys.path.insert(0, str(ROOT / 'scripts'))
from battery_icon_history import ITEM, ITEM_ID, Snapshot, baseline, verify_prefix  # noqa: E402

RULE = 'UpdateBatteryIcon'
WRITER_SHA256 = '834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f'
SOURCE = ROOT / 'openhab/file-config/items/battery-icon.items'
TARGET = Path('/etc/openhab/items/battery-icon.items')
SOURCE_SHA256 = 'c130f3be1e04dcf05eb8920b8d9e4acebfbd8dfd33963135aa14985535ed491d'
EXPECTED_METADATA = {'stateDescription': {'value': ' ',
                     'config': {'pattern': '"Battery Icon [%s]" <iconify>'},
                     'editable': True}}
RELEASE_READY = True  # Isolated JDBC/metadata rollback, focused tests and live preflight passed.

migration.NAMES = (ITEM,)
migration.ITEM_TYPE = 'String'
migration.SOURCE = SOURCE
migration.TARGET = TARGET
migration.BACKUP_PREFIX = 'battery-icon'


def rule_healthy(*, allow_running=False):
    rule = migration.oh.get('/rules/' + RULE)
    allowed = [{'status': 'IDLE', 'statusDetail': 'NONE'}]
    if allow_running:
        allowed.append({'status': 'RUNNING', 'statusDetail': 'NONE'})
    migration.require(rule.get('uid') == RULE and rule.get('status') in allowed,
                      'BatteryIcon writer not healthy')
    scripts = [action.get('configuration', {}).get('script')
               for action in rule.get('actions', [])
               if action.get('configuration', {}).get('script')]
    migration.require(len(scripts) == 1 and
                      sha256(scripts[0].encode()).hexdigest() == WRITER_SHA256,
                      'BatteryIcon writer source drift')
    migration.require(len(rule.get('triggers', [])) == 1 and
                      rule['triggers'][0].get('configuration', {}).get('cronExpression')
                      == '0/30 * * * * ?', 'BatteryIcon writer schedule drift')


def definition(item, original, *, file_owned):
    if item is None or item.get('editable') is not (not file_owned):
        return False
    for field in migration.FIELDS:
        actual, expected = item.get(field), original.get(field)
        if field in ('tags', 'groupNames'):
            actual, expected = sorted(actual or []), sorted(expected or [])
        if field == 'category':
            actual, expected = actual or None, expected or None
        if actual != expected:
            return False
    wanted = json.loads(json.dumps(original.get('metadata')))
    if file_owned:
        wanted['stateDescription']['editable'] = False
    return (item.get('metadata') == wanted and
            item.get('stateDescription') == original.get('stateDescription'))


def wait_item(db, original, before, *, file_owned, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = migration.item(ITEM)
        if definition(current, original, file_owned=file_owned):
            tail = verify_prefix(db, before)
            if current.get('state') == tail['last_state']:
                return tail
        time.sleep(1)
    raise RuntimeError('BatteryIcon provider, metadata or persisted state recovery failed')


def preflight(db):
    migration.require(not TARGET.exists() and not TARGET.is_symlink(),
                      'BatteryIcon file target already exists')
    migration.require(sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256,
                      'BatteryIcon staged source changed')
    original = migration.item(ITEM)
    migration.require(original is not None and original.get('editable') is True
                      and original.get('type') == 'String'
                      and original.get('metadata') == EXPECTED_METADATA
                      and original.get('state') not in (None, 'NULL', 'UNDEF'),
                      'managed BatteryIcon definition/state unavailable')
    migration.require(not original.get('groupNames') and
                      not any(link.get('itemName') == ITEM
                              for link in migration.oh.get('/links')),
                      'BatteryIcon unexpectedly grouped or linked')
    rule_healthy()
    before = baseline(db)
    migration.require(before.item_id == ITEM_ID and
                      before.last_state == original['state'],
                      'BatteryIcon JDBC state/identity drift')
    return original, before


def backup_history(db, directory):
    data = io.StringIO()
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='20s'")
        cursor.copy_expert('COPY (SELECT time,value FROM public.item0031 '
                           'ORDER BY time,value) TO STDOUT WITH CSV', data)
    body = data.getvalue().encode()
    migration.save_private(directory, 'item0031.csv', body)
    migration.require(sha256((directory / 'item0031.csv').read_bytes()).digest()
                      == sha256(body).digest(), 'private Item 31 history copy mismatch')
    handle = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def restore_metadata():
    payload = {key: EXPECTED_METADATA['stateDescription'][key]
               for key in ('value', 'config')}
    request = Request(migration.oh.BASE + '/items/' + ITEM + '/metadata/stateDescription',
                      method='PUT', data=json.dumps(payload).encode(),
                      headers={'Authorization': 'Bearer ' + migration.oh.token(),
                               'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=15) as response:
            migration.require(response.status in (200, 201, 202, 204),
                              'BatteryIcon metadata rollback refused')
    except HTTPError as error:
        raise RuntimeError('BatteryIcon metadata rollback HTTP ' + str(error.code)) from None


def apply(db, original, before):
    receipt = asdict(before)
    receipt['last_time'] = before.last_time.isoformat()
    directory = migration.backup({ITEM: original}, {ITEM: receipt}, SOURCE_SHA256)
    backup_history(db, directory)
    print('private_backup=' + str(directory), flush=True)
    changed = success = False
    try:
        rule_healthy()
        migration.require(migration.item(ITEM) == original and
                          verify_prefix(db, before)['added'] == 0,
                          'BatteryIcon changed during backup; retry later')
        changed = True
        migration.request('DELETE', ITEM)
        migration.wait(ITEM, original, None)
        subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                       check=True, timeout=15)
        migration.require(sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                          'installed BatteryIcon source differs')
        tail = wait_item(db, original, before, file_owned=True)
        rule_healthy(allow_running=True)
        migration.require(not any(link.get('itemName') == ITEM
                                  for link in migration.oh.get('/links')),
                          'BatteryIcon gained unexpected link')
        success = True
        print(json.dumps({'status': 'file_provider_provisional', 'item': ITEM,
                          'jdbc_id': ITEM_ID, 'original_rows': before.count,
                          'later_rows': tail['added'], 'backup': str(directory),
                          'natural_writer_pending': True}, sort_keys=True), flush=True)
    finally:
        if changed and not success:
            if TARGET.exists():
                migration.require(not TARGET.is_symlink() and
                                  sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                                  'unknown BatteryIcon file target; manual recovery required')
                TARGET.rename(directory / 'failed.items')
                migration.wait(ITEM, original, None)
            current = migration.item(ITEM)
            if current is None:
                migration.request('PUT', ITEM, {field: original[field]
                                  for field in migration.FIELDS if field in original})
                restore_metadata()
            elif current.get('editable') is True and not definition(
                    current, original, file_owned=False):
                restore_metadata()
            elif current.get('editable') is not True:
                raise RuntimeError('unknown BatteryIcon provider during rollback')
            wait_item(db, original, before, file_owned=False)
            print('managed_metadata_rollback_verified=true', flush=True)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-battery-icon.py --check|--apply')
    if argv == ['--apply'] and not RELEASE_READY:
        raise SystemExit('BatteryIcon live cutover not release-qualified')
    settings = migration.parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config')
    db = migration.psycopg2.connect(**settings.connect_kwargs, connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        original, before = preflight(db)
        if argv == ['--check']:
            print(json.dumps({'status': 'preflight_passed', 'item': ITEM,
                              'jdbc_id': ITEM_ID, 'history_rows': before.count,
                              'source_sha256': SOURCE_SHA256}, sort_keys=True))
        else:
            apply(db, original, before)
    finally:
        db.close()


if __name__ == '__main__':
    main()
