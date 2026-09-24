#!/usr/bin/env python3
"""Attended three-Item forecast JSON transfer with verified live rollback.

No synthetic production updates. The publisher timer is paused only during the
brief handoff; each Item keeps its name, persisted state and JDBC history.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']
import openhab_sanity_check as oh  # noqa: E402
from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402

NAMES = ('Forecast_Hourly_JSON', 'Forecast_Daily_JSON', 'Forecast_10Day_JSON')
ITEM_TYPE = 'String'
SOURCE = ROOT / 'openhab/file-config/items/forecast-json.items'
TARGET = Path('/etc/openhab/items/forecast-json.items')
ITEM_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
BACKUP_PREFIX = 'forecast-json'
TIMER = 'forecast-json.timer'
SERVICE = 'forecast-json.service'
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def command(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=20).stdout.decode().strip()


def unit_state(unit):
    return command('systemctl', '--user', 'show', unit, '-p', 'ActiveState', '--value')


def item(name):
    try:
        return oh.get('/items/' + name + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def request(method, name, body=None):
    headers = {'Authorization': 'Bearer ' + oh.token()}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(oh.BASE + '/items/' + name, method=method,
                             data=json.dumps(body).encode() if body is not None else None,
                             headers=headers), timeout=15) as response:
            require(response.status in (200, 201, 202, 204), 'Item REST mutation refused')
    except HTTPError as error:
        raise RuntimeError('Item REST mutation HTTP ' + str(error.code)) from None


def definition(actual, original, provider):
    if actual is None or actual.get('editable') is not provider:
        return False
    for field in (*FIELDS, 'metadata', 'stateDescription'):
        a, b = actual.get(field), original.get(field)
        if field in ('tags', 'groupNames'):
            a, b = sorted(a or []), sorted(b or [])
        if field == 'category':
            a, b = a or None, b or None
        if a != b:
            return False
    return True


def same_state(actual, expected):
    if ITEM_TYPE != 'Number':
        return actual == expected
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    try:
        left, right = Decimal(actual), Decimal(expected)
        return left.is_finite() and right.is_finite() and left == right
    except InvalidOperation:
        return False


def wait(name, original, provider, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = item(name)
        if provider is None and current is None:
            return
        if provider is not None and definition(current, original, provider):
            if same_state(current.get('state'), original.get('state')):
                return
        time.sleep(1)
    raise RuntimeError('provider, definition or state recovery failed: ' + name)


def history(db, name):
    digest = sha256()
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='10s'")
        cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (name,))
        found = cursor.fetchall()
        require(len(found) == 1 and type(found[0][0]) is int,
                'JDBC identity missing or ambiguous: ' + name)
        ident = found[0][0]
        cursor.execute(sql.SQL('SELECT time,value FROM public.{} ORDER BY time,value').format(
            sql.Identifier('item' + str(ident).zfill(4))))
        rows = cursor.fetchall()
    require(rows, 'JDBC state history empty: ' + name)
    for stamp, value in rows:
        digest.update((str(stamp) + '\t' + str(value) + '\n').encode())
    return {'id': ident, 'count': len(rows), 'last_state': str(rows[-1][1]),
            'sha256': digest.hexdigest()}


def save_private(directory, name, body):
    descriptor = os.open(directory / name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def backup(originals, histories, source_hash):
    root = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700, 'private backup root unsafe')
    directory = BACKUP_ROOT / (BACKUP_PREFIX + '-' + datetime.now(timezone.utc).strftime(
        '%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    save_private(directory, 'managed-items-and-history.json', json.dumps(
        {'items': originals, 'histories': histories, 'source_sha256': source_hash},
        sort_keys=True).encode())
    save_private(directory, 'item-jsondb.json', ITEM_DB.read_bytes())
    handle = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    return directory


def main(apply):
    require(not TARGET.exists() and not TARGET.is_symlink(), 'target already exists')
    source = SOURCE.read_bytes()
    source_hash = sha256(source).hexdigest()
    require(all(source.count((ITEM_TYPE + ' ' + name + ' ').encode()) == 1 for name in NAMES),
            'source Item set unexpected')
    originals = {name: item(name) for name in NAMES}
    require(all(entry is not None and entry.get('editable') is True
                and entry.get('type') == ITEM_TYPE and entry.get('state') not in (None, 'NULL')
                for entry in originals.values()), 'managed Item/state preflight failed')
    require(not any(link.get('itemName') in NAMES for link in oh.get('/links')),
            'forecast Item unexpectedly linked')
    require(unit_state(TIMER) == 'active',
            'forecast timer not active')
    require(unit_state(SERVICE) == 'inactive',
            'forecast publisher currently running')
    db = psycopg2.connect(**parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs,
        connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        histories = {name: history(db, name) for name in NAMES}
        require(all(same_state(histories[name]['last_state'], originals[name]['state'])
                    for name in NAMES), 'current state disagrees with persisted state')
        if not apply:
            print(json.dumps({'status': 'preflight_passed', 'items': {name: {
                'jdbc_id': row['id'], 'history_rows': row['count']}
                for name, row in histories.items()}, 'source_sha256': source_hash},
                sort_keys=True), flush=True)
            return
        directory = backup(originals, histories, source_hash)
        print('private_backup=' + str(directory), flush=True)
        paused = changed = success = recovered = False
        try:
            command('systemctl', '--user', 'stop', TIMER)
            paused = True
            require(unit_state(SERVICE) == 'inactive',
                    'publisher started during transfer')
            require({name: item(name) for name in NAMES} == originals,
                    'Item definition or state drift after timer pause')
            require(sha256(SOURCE.read_bytes()).hexdigest() == source_hash,
                    'source drift before transfer')
            for name in NAMES:
                require(definition(item(name), originals[name], True),
                        'managed definition drift: ' + name)
                changed = True
                request('DELETE', name)
                wait(name, originals[name], None)
            subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                           check=True, timeout=15)
            require(sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                    'installed source differs')
            for name in NAMES:
                wait(name, originals[name], False)
            require({name: history(db, name) for name in NAMES} == histories,
                    'JDBC history changed after file transfer')
            # Exercise actual live rollback before accepting the new provider.
            TARGET.rename(directory / 'rollback.items')
            for name in NAMES:
                wait(name, originals[name], None)
                request('PUT', name, {key: originals[name][key] for key in FIELDS
                                      if key in originals[name]})
                wait(name, originals[name], True)
            require({name: history(db, name) for name in NAMES} == histories,
                    'JDBC history changed during managed rollback')
            for name in NAMES:
                request('DELETE', name)
                wait(name, originals[name], None)
            (directory / 'rollback.items').rename(TARGET)
            for name in NAMES:
                wait(name, originals[name], False)
            require({name: history(db, name) for name in NAMES} == histories,
                    'JDBC history changed on return to file provider')
            require(not any(link.get('itemName') in NAMES for link in oh.get('/links')),
                    'unexpected link appeared')
            success = True
        finally:
            try:
                if changed and not success:
                    if TARGET.exists():
                        require(not TARGET.is_symlink()
                                and sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                                'unknown target; manual recovery required')
                        TARGET.rename(directory / 'failed.items')
                    for name in NAMES:
                        if item(name) is None:
                            request('PUT', name, {key: originals[name][key] for key in FIELDS
                                                  if key in originals[name]})
                        wait(name, originals[name], True)
                    require({name: history(db, name) for name in NAMES} == histories,
                            'JDBC history changed during failure rollback')
                    recovered = True
                    print('managed_rollback_verified=true', flush=True)
            finally:
                if paused and (success or recovered or not changed):
                    command('systemctl', '--user', 'start', TIMER)
                    require(unit_state(TIMER) == 'active',
                            'forecast timer did not recover')
                elif paused:
                    print('RECOVERY_INCOMPLETE: timer remains stopped; inspect backup',
                          flush=True)
        print(json.dumps({'status': 'file_owned_verified', 'items': list(NAMES),
                          'jdbc_histories_preserved': True, 'live_rollback_verified': True,
                          'timer_active': True, 'backup': str(directory)},
                         sort_keys=True), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-forecast-json-items.py --check|--apply')
    main(sys.argv[1:] == ['--apply'])
