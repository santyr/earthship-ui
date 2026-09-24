#!/usr/bin/env python3
"""Attended Forecast_AQI Item/link transfer; --check is strictly read-only.

The binding publishes a 48-value time series, not a numeric current AQI.
REFRESH is a special Item state. No synthetic state or REFRESH command is sent.
The immediate provider transfer is provisional until a natural binding series
event is observed after the cutover.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']
import openhab_sanity_check as oh  # noqa: E402
from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402

NAME = 'Forecast_AQI'
CHANNEL = 'openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string'
THING = 'openmeteo:air-quality:local:aq'
SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-aqi.items'
SOURCE_SHA256 = '5d9517fc7c68d22df252ed43c5dc551782438cf00cca81088c626f2a66914590'
TARGET = Path('/etc/openhab/items/openmeteo-forecast-aqi.items')
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
ITEM_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')
EXPECTED = {'name': NAME, 'type': 'String', 'label': 'US Air Quality Index',
            'category': None, 'tags': ['forecast'], 'groupNames': []}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def item():
    try:
        return oh.get('/items/' + NAME + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def links():
    return [row for row in oh.get('/links') if row.get('itemName') == NAME]


def exact_item(row, provider):
    return (row is not None and row.get('editable') is provider
            and all(row.get(key) == value for key, value in EXPECTED.items()
                    if key != 'category')
            and (row.get('category') or None) is None
            and not row.get('metadata'))


def exact_link(row, provider):
    return (row.get('editable') is provider and row.get('itemName') == NAME
            and row.get('channelUID') == CHANNEL and not row.get('configuration'))


def allowed_state(value):
    # The exact special state recovered through isolated file reload and JVM
    # restart. A transient NULL must not be accepted as completed recovery.
    return value == 'REFRESH'


def ready(provider):
    current = item()
    found = links()
    return (exact_item(current, provider) and len(found) == 1
            and exact_link(found[0], provider) and allowed_state(current.get('state')))


def absent():
    return item() is None and not links()


def wait_for(predicate, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (OSError, RuntimeError, ValueError, KeyError):
            pass
        time.sleep(1)
    return False


def healthy_thing():
    thing = oh.get('/things/' + THING + '?summary=false')
    return (thing.get('UID') == THING and thing.get('editable') is False
            and thing.get('statusInfo', {}).get('status') == 'ONLINE'
            and any(row.get('uid') == CHANNEL for row in thing.get('channels', [])))


def request(method, path, body=None):
    headers = {'Authorization': 'Bearer ' + oh.token()}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(oh.BASE + path, method=method,
                             data=json.dumps(body).encode() if body is not None else None,
                             headers=headers), timeout=15) as response:
            require(response.status in (200, 201, 202, 204), 'REST mutation refused')
    except HTTPError as error:
        raise RuntimeError('Forecast_AQI ' + method + ' HTTP ' + str(error.code)) from None


def history(db, ident, cutoff=None):
    digest = sha256()
    count = 0
    last = None
    query = sql.SQL('SELECT time,value FROM public.{}').format(
        sql.Identifier('item' + str(ident).zfill(4)))
    if cutoff is not None:
        query += sql.SQL(' WHERE time<=%s')
    query += sql.SQL(' ORDER BY time,value')
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='10s'")
        cursor.execute(query, (cutoff,) if cutoff is not None else ())
        for stamp, value in cursor:
            digest.update((str(stamp) + '\t' + str(value) + '\n').encode())
            count += 1
            last = stamp
    return {'count': count, 'max_time': last, 'sha256': digest.hexdigest()}


def private_file(directory, name, body):
    descriptor = os.open(directory / name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def backup(original, original_link, source_hash, item_id, before):
    root = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700, 'private backup root unsafe')
    directory = BACKUP_ROOT / ('forecast-aqi-' + datetime.now(timezone.utc).strftime(
        '%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    private_file(directory, 'managed-and-history.json', json.dumps({
        'item': original, 'link': original_link, 'source_sha256': source_hash,
        'jdbc_item_id': item_id, 'history_before': before}, default=str,
        sort_keys=True).encode())
    private_file(directory, 'item-jsondb.json', ITEM_DB.read_bytes())
    private_file(directory, 'link-jsondb.json', LINK_DB.read_bytes())
    handle = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    return directory


def restore_managed(directory, original, original_link, source_hash):
    removed_file = False
    if TARGET.exists():
        require(not TARGET.is_symlink()
                and sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                'target drift; manual recovery required')
        TARGET.rename(directory / 'failed-file.items')
        removed_file = True
    if removed_file:
        require(wait_for(absent, 60), 'file Item/link did not withdraw')
    current = item()
    if current is None:
        request('PUT', '/items/' + NAME,
                {key: original[key] for key in FIELDS if key in original})
    else:
        require(exact_item(current, True), 'unexpected Item during rollback')
    current_links = links()
    if not current_links:
        request('PUT', '/links/' + NAME + '/' + quote(CHANNEL, safe=''),
                {key: original_link[key] for key in ('itemName', 'channelUID', 'configuration')})
    else:
        require(len(current_links) == 1 and exact_link(current_links[0], True),
                'unexpected link during rollback')
    require(wait_for(lambda: ready(True), 90), 'managed rollback did not recover')


def main(apply):
    require(not TARGET.exists() and not TARGET.is_symlink(), 'target already exists')
    source = SOURCE.read_bytes()
    source_hash = sha256(source).hexdigest()
    require(source_hash == SOURCE_SHA256, 'prepared source changed')
    original = item()
    original_links = links()
    require(exact_item(original, True) and original.get('state') == 'REFRESH'
            and len(original_links) == 1 and exact_link(original_links[0], True)
            and healthy_thing(), 'managed Item/link/Thing preflight failed')
    db = psycopg2.connect(**parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs,
        connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (NAME,))
            found = cursor.fetchall()
        require(len(found) == 1 and type(found[0][0]) is int,
                'JDBC Item identity missing or ambiguous')
        item_id = found[0][0]
        before = history(db, item_id)
        require(before['count'] >= 2, 'legacy JDBC prefix unexpectedly missing')
        if not apply:
            print(json.dumps({'status': 'preflight_passed', 'item': NAME,
                              'jdbc_item_id': item_id, 'history_rows': before['count'],
                              'source_sha256': source_hash}, sort_keys=True), flush=True)
            return
        directory = backup(original, original_links[0], source_hash, item_id, before)
        print('private_backup=' + str(directory), flush=True)
        changed = False
        try:
            require(item() == original and links() == original_links,
                    'managed source drift before transfer')
            require(history(db, item_id) == before,
                    'JDBC history drift before transfer')
            changed = True
            request('DELETE', '/links/' + NAME + '/' + quote(CHANNEL, safe=''))
            require(wait_for(lambda: not links(), 45), 'managed link did not withdraw')
            request('DELETE', '/items/' + NAME)
            require(wait_for(absent, 45), 'managed Item did not withdraw')
            require(sha256(SOURCE.read_bytes()).hexdigest() == source_hash,
                    'source drift during transfer')
            subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                           check=True, timeout=15)
            require(sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                    'installed source differs')
            require(wait_for(lambda: ready(False), 90),
                    'file Item/link/state readback failed')
            require(history(db, item_id, before['max_time']) == before,
                    'JDBC historical prefix changed')
            require(healthy_thing(), 'AQI binding Thing degraded')
        except BaseException:
            if changed:
                restore_managed(directory, original, original_links[0], source_hash)
                require(history(db, item_id, before['max_time']) == before,
                        'JDBC prefix changed during rollback')
                print('managed_rollback_verified=true', flush=True)
            raise
        print(json.dumps({'status': 'file_provider_provisional', 'item': NAME,
                          'link': CHANNEL, 'jdbc_item_id': item_id,
                          'history_rows_preserved': before['count'],
                          'state': item().get('state'), 'source_sha256': source_hash,
                          'backup': str(directory), 'natural_series_pending': True},
                         sort_keys=True), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-openmeteo-forecast-aqi-item.py --check|--apply')
    main(apply=sys.argv[1:] == ['--apply'])
