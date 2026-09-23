#!/usr/bin/env python3
"""Attended exact-target AQI Item/link transfer; no synthetic live telemetry."""
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
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']
import openhab_sanity_check as oh  # noqa: E402
from earthship_energy.db import parse_openhab_jdbc_config  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2 import sql  # noqa: E402

NAME = 'Current_US_AQI'
CHANNEL = 'openmeteo:air-quality:local:aq:current#us-aqi'
THING = 'openmeteo:air-quality:local:aq'
SOURCE = ROOT / 'openhab/file-config/items/openmeteo-current-aqi.items'
SOURCE_SHA256 = '82b92ebe0d10f439d067fa309f8ee28b1fa5fd693e0abd8c2e1b0caa9241e530'
TARGET = Path('/etc/openhab/items/openmeteo-current-aqi.items')
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
ITEM_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')
EXPECTED = {'name': NAME, 'type': 'Number', 'label': 'Current US AQI',
            'category': 'airquality', 'tags': ['Measurement'], 'groupNames': []}
EXPECTED_METADATA = {'semantics': {'value': 'Point_Measurement', 'editable': False}}


def get_item():
    try:
        return oh.get('/items/' + NAME + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def links():
    return [entry for entry in oh.get('/links') if entry.get('itemName') == NAME]


def exact_item(entry, provider):
    return (entry is not None and entry.get('editable') is provider and
            all(entry.get(key) == value for key, value in EXPECTED.items()) and
            entry.get('metadata') == EXPECTED_METADATA)


def exact_link(entry, provider):
    return (entry.get('editable') is provider and entry.get('itemName') == NAME
            and entry.get('channelUID') == CHANNEL and not entry.get('configuration'))


def same_number(left, right):
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except (InvalidOperation, TypeError, ValueError):
        return False


def healthy_thing():
    thing = oh.get('/things/' + THING + '?summary=false')
    return (thing.get('UID') == THING and thing.get('editable') is False
            and thing.get('statusInfo', {}).get('status') == 'ONLINE'
            and any(channel.get('uid') == CHANNEL for channel in thing.get('channels', [])))


def history(db, item_id, cutoff=None):
    table = sql.Identifier('item' + str(item_id).zfill(4))
    query = sql.SQL('SELECT time,value FROM public.{}').format(table)
    args = ()
    if cutoff is not None:
        query += sql.SQL(' WHERE time<=%s')
        args = (cutoff,)
    query += sql.SQL(' ORDER BY time,value')
    digest = sha256()
    count = 0
    latest_time = latest_value = None
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='10s'")
        cursor.execute(query, args)
        for stamp, value in cursor:
            digest.update((str(stamp) + '\t' + str(value) + '\n').encode())
            count += 1
            latest_time, latest_value = stamp, value
    return {'count': count, 'max_time': latest_time, 'latest_value': latest_value,
            'sha256': digest.hexdigest()}


def private_file(directory, name, body):
    descriptor = os.open(directory / name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def backup(original, original_link, source_hash, item_id, before):
    root = BACKUP_ROOT.lstat()
    if (not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid()
            or stat.S_IMODE(root.st_mode) != 0o700):
        raise RuntimeError('private backup root ownership or mode is unsafe')
    directory = BACKUP_ROOT / ('openmeteo-aqi-' + datetime.now(timezone.utc).strftime(
        '%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    snapshot = {'item': original, 'link': original_link, 'source_sha256': source_hash,
                'jdbc_item_id': item_id, 'history_before': before}
    private_file(directory, 'rest-and-history.json',
                 json.dumps(snapshot, default=str, sort_keys=True).encode())
    private_file(directory, 'item-jsondb.json', ITEM_DB.read_bytes())
    private_file(directory, 'link-jsondb.json', LINK_DB.read_bytes())
    handle = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    return directory


def request(method, path, body=None):
    headers = {'Authorization': 'Bearer ' + oh.token()}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    query = Request(oh.BASE + path, method=method, data=body, headers=headers)
    try:
        with urlopen(query, timeout=15) as response:
            return response.status
    except HTTPError as error:
        raise RuntimeError('AQI ' + method + ' returned HTTP ' + str(error.code)) from None


def wait_for(predicate, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (OSError, RuntimeError, ValueError, KeyError):
            pass
        time.sleep(1)
    return False


def absent():
    return get_item() is None and not links()


def file_ready(state):
    entry = get_item()
    current_links = links()
    return (exact_item(entry, False) and len(current_links) == 1
            and exact_link(current_links[0], False)
            and same_number(entry.get('state'), state))


def managed_ready(state):
    entry = get_item()
    current_links = links()
    return (exact_item(entry, True) and len(current_links) == 1
            and exact_link(current_links[0], True)
            and same_number(entry.get('state'), state))


def rollback(directory, original, original_link, source_hash, state):
    file_removed = False
    if TARGET.exists():
        if TARGET.is_symlink() or sha256(TARGET.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError('AQI target changed; manual rollback review required')
        TARGET.rename(directory / 'failed-file.items')
        file_removed = True
    if file_removed and not wait_for(absent, 45):
        raise RuntimeError('AQI file Item/link did not withdraw during rollback')
    if get_item() is None:
        body = {key: original[key] for key in EXPECTED}
        if request('PUT', '/items/' + NAME, json.dumps(body).encode()) not in (200, 201, 202):
            raise RuntimeError('managed AQI Item restore refused')
    if not links():
        body = {key: original_link[key] for key in ('itemName', 'channelUID')}
        body['configuration'] = original_link.get('configuration', {})
        if request('PUT', '/links/' + NAME + '/' + quote(CHANNEL, safe=''),
                   json.dumps(body).encode()) not in (200, 201, 202, 204):
            raise RuntimeError('managed AQI link restore refused')
    if not wait_for(lambda: managed_ready(state), 90):
        raise RuntimeError('managed AQI rollback state or definition failed')


def main():
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-openmeteo-aqi-item.py --check|--apply')
    apply = sys.argv[1:] == ['--apply']
    if TARGET.exists() or TARGET.is_symlink():
        raise RuntimeError('AQI file target already exists')
    source = SOURCE.read_bytes()
    source_hash = sha256(source).hexdigest()
    if source_hash != SOURCE_SHA256:
        raise RuntimeError('AQI prepared source drifted')
    original = get_item()
    original_links = links()
    if (not exact_item(original, True) or len(original_links) != 1
            or not exact_link(original_links[0], True) or not healthy_thing()):
        raise RuntimeError('AQI managed Item/link/Thing preflight failed')
    state = original.get('state')
    if not same_number(state, state):
        raise RuntimeError('AQI live state is not numeric')
    connection = parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    db = psycopg2.connect(**connection.connect_kwargs, connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (NAME,))
            mapping = cursor.fetchall()
        if len(mapping) != 1 or type(mapping[0][0]) is not int:
            raise RuntimeError('AQI JDBC identity is not unique')
        item_id = mapping[0][0]
        before = history(db, item_id)
        if before['count'] == 0 or not same_number(before['latest_value'], state):
            raise RuntimeError('AQI live state and latest JDBC history disagree')
        if not apply:
            print(json.dumps({'status': 'preflight_passed', 'item': NAME,
                              'jdbc_item_id': item_id, 'history_rows': before['count'],
                              'source_sha256': source_hash}, sort_keys=True), flush=True)
            return
        directory = backup(original, original_links[0], source_hash, item_id, before)
        print('private_backup=' + str(directory), flush=True)
        changed = False
        try:
            changed = True
            code = request('DELETE', '/links/' + NAME + '/' + quote(CHANNEL, safe=''))
            if code not in (200, 202, 204):
                raise RuntimeError('managed AQI link deletion refused')
            if not wait_for(lambda: not links(), 30):
                raise RuntimeError('managed AQI link did not withdraw')
            code = request('DELETE', '/items/' + NAME)
            if code not in (200, 202, 204):
                raise RuntimeError('managed AQI Item deletion refused')
            if not wait_for(absent, 30):
                raise RuntimeError('managed AQI Item did not withdraw')
            if sha256(SOURCE.read_bytes()).hexdigest() != source_hash:
                raise RuntimeError('AQI source changed during transfer')
            subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                           check=True, timeout=15)
            if sha256(TARGET.read_bytes()).hexdigest() != source_hash:
                raise RuntimeError('installed AQI Item file differs from source')
            if not wait_for(lambda: file_ready(state), 90):
                raise RuntimeError('AQI file Item/link/state readback failed')
            if history(db, item_id, before['max_time']) != before:
                raise RuntimeError('AQI JDBC historical prefix changed')
            if not healthy_thing():
                raise RuntimeError('AQI Thing degraded during transfer')
        except BaseException:
            if changed:
                rollback(directory, original, original_links[0], source_hash, state)
                if history(db, item_id, before['max_time']) != before:
                    raise RuntimeError('AQI JDBC historical prefix changed during rollback')
                print('managed_rollback_verified=true', flush=True)
            raise
        print(json.dumps({'status': 'file_owned_verified', 'item': NAME,
                          'link': CHANNEL, 'jdbc_item_id': item_id,
                          'history_rows_preserved': before['count'],
                          'source_sha256': source_hash, 'backup': str(directory)},
                         sort_keys=True), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    main()
