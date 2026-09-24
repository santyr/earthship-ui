#!/usr/bin/env python3
"""Attended three-Item OpenMeteo forecast provider transfer.

--check is read-only. --apply privately backs up exact managed definitions and
all three JDBC row sets, transfers only these Items/links, and verifies file
ownership and preservation. A natural binding fetch remains a separate gate.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
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

SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-temperature.items'
SOURCE_SHA256 = '10d702cba64f1bca213f4db9229107ed04bd12db5d28448026fe9200f118e9fc'
TARGET = Path('/etc/openhab/items/openmeteo-forecast-temperature.items')
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
ITEM_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')
THING = 'openmeteo:forecast:local:site'
CHANNELS = {
    'Forecast_Temp': 'openmeteo:forecast:local:site:forecastHourly#temperature',
    'Forecast_Daily_High': 'openmeteo:forecast:local:site:forecastDaily#temperature-max',
    'Forecast_Daily_Low': 'openmeteo:forecast:local:site:forecastDaily#temperature-min',
}
LABELS = {'Forecast_Temp': 'Forecast Temperature',
          'Forecast_Daily_High': 'Forecast Daily High',
          'Forecast_Daily_Low': 'Forecast Daily Low'}
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')
STATE = re.compile(r'^-?(?:\d+(?:\.\d*)?|\.\d+) °F$')


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def item(name):
    try:
        return oh.get('/items/' + name + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def links():
    return {name: [row for row in oh.get('/links') if row.get('itemName') == name]
            for name in CHANNELS}


def same_state(actual, expected):
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    if STATE.fullmatch(actual) is None or STATE.fullmatch(expected) is None:
        return False
    try:
        return abs(Decimal(actual[:-3]) - Decimal(expected[:-3])) <= Decimal('0.000001')
    except InvalidOperation:
        return False


def state_matches(actual, expected):
    candidates = (expected,) if isinstance(expected, str) else expected
    return any(same_state(actual, candidate) for candidate in candidates)


def restore_state_from_history(rows, at):
    past = [(stamp, value) for stamp, value in rows if stamp <= at]
    require(bool(past), 'no past JDBC forecast value available for state restore')
    _, value = max(past, key=lambda row: row[0])
    require(type(value) in (float, int, Decimal), 'non-numeric JDBC forecast state')
    return str(value) + ' °F'


def exact_item(row, name, managed, original_state=None):
    return (isinstance(row, dict) and row.get('editable') is managed
            and row.get('name') == name
            and row.get('type') == 'Number:Temperature'
            and row.get('label') == LABELS[name]
            and (row.get('category') or None) is None
            and row.get('tags') == ['forecast']
            and row.get('groupNames') == ['gForecast']
            and not row.get('metadata')
            and isinstance(row.get('state'), str)
            and STATE.fullmatch(row['state']) is not None
            and (original_state is None or state_matches(row['state'], original_state)))


def exact_link(row, name, managed):
    return (row.get('editable') is managed
            and row.get('itemName') == name
            and row.get('channelUID') == CHANNELS[name]
            and not row.get('configuration'))


def ready(managed, original_states):
    found = links()
    return all(exact_item(item(name), name, managed, original_states[name])
               and len(found[name]) == 1 and exact_link(found[name][0], name, managed)
               for name in CHANNELS)


def absent():
    found = links()
    return all(item(name) is None and not found[name] for name in CHANNELS)


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
    channels = {row.get('uid') for row in thing.get('channels', [])}
    return (thing.get('UID') == THING and thing.get('editable') is False
            and thing.get('statusInfo', {}).get('status') == 'ONLINE'
            and set(CHANNELS.values()).issubset(channels))


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
        raise RuntimeError('forecast group ' + method + ' HTTP ' + str(error.code)) from None


def history(db, identity):
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='10s'")
        cursor.execute(sql.SQL('SELECT time,value FROM public.{} ORDER BY time,value').format(
            sql.Identifier('item' + str(identity).zfill(4))))
        return cursor.fetchall()


def preserved(before, after):
    return not (Counter(before) - Counter(after))


def settled_history_preserved(db, identities, before, seconds=90):
    """Allow asynchronous JDBC series replacement to finish before judging rows."""
    deadline = time.monotonic() + seconds
    consecutive = 0
    while time.monotonic() < deadline:
        if all(preserved(before[name], history(db, identities[name]))
               for name in CHANNELS):
            consecutive += 1
            if consecutive == 4:
                return True
        else:
            consecutive = 0
        time.sleep(2)
    return False


def private_file(directory, name, body):
    descriptor = os.open(directory / name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def backup(originals, original_links, identities, before, source_hash):
    root = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700, 'private backup root unsafe')
    directory = BACKUP_ROOT / ('forecast-temperature-'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    private_file(directory, 'managed-and-history.json', json.dumps({
        'items': originals, 'links': original_links, 'source_sha256': source_hash,
        'jdbc_item_ids': identities,
        'jdbc_rows': {name: [[stamp.isoformat(), value] for stamp, value in rows]
                      for name, rows in before.items()},
    }, sort_keys=True, allow_nan=False).encode())
    private_file(directory, 'item-jsondb.json', ITEM_DB.read_bytes())
    private_file(directory, 'link-jsondb.json', LINK_DB.read_bytes())
    handle = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)
    return directory


def restore_managed(directory, originals, original_links, source_hash, states):
    if TARGET.exists():
        require(not TARGET.is_symlink()
                and sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                'target drift; manual recovery required')
        TARGET.rename(directory / 'failed-file.items')
        require(wait_for(absent, 60), 'file group did not withdraw before rollback')
    for name in CHANNELS:
        current = item(name)
        if current is None:
            request('PUT', '/items/' + name,
                    {field: originals[name][field] for field in FIELDS
                     if field in originals[name]})
        else:
            require(exact_item(current, name, True),
                    'unexpected Item during managed rollback: ' + name)
    found = links()
    for name, channel in CHANNELS.items():
        if not found[name]:
            request('PUT', '/links/' + name + '/' + quote(channel, safe=''),
                    {key: original_links[name][key]
                     for key in ('itemName', 'channelUID', 'configuration')})
        else:
            require(len(found[name]) == 1 and exact_link(found[name][0], name, True),
                    'unexpected link during managed rollback: ' + name)
    require(wait_for(lambda: ready(True, states), 90),
            'managed rollback Item/link/database-backed state did not recover')


def main(apply):
    require(not TARGET.exists() and not TARGET.is_symlink(), 'target already exists')
    source_hash = sha256(SOURCE.read_bytes()).hexdigest()
    require(source_hash == SOURCE_SHA256, 'prepared source changed')
    originals = {name: item(name) for name in CHANNELS}
    original_links = links()
    states = {name: originals[name].get('state') if originals[name] else None
              for name in CHANNELS}
    require(all(exact_item(originals[name], name, True)
                and len(original_links[name]) == 1
                and exact_link(original_links[name][0], name, True)
                for name in CHANNELS) and healthy_thing(),
            'managed group/link/Thing preflight failed')
    original_links = {name: original_links[name][0] for name in CHANNELS}
    db = psycopg2.connect(**parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs,
        connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        identities = {}
        before = {}
        with db.cursor() as cursor:
            for name in CHANNELS:
                cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (name,))
                found = cursor.fetchall()
                require(len(found) == 1 and type(found[0][0]) is int,
                        'JDBC Item identity missing: ' + name)
                identities[name] = found[0][0]
                before[name] = history(db, identities[name])
                require(len(before[name]) >= 7, 'forecast JDBC history missing: ' + name)
        if not apply:
            print(json.dumps({'status': 'preflight_passed',
                'jdbc_item_ids': identities,
                'jdbc_rows': {name: len(rows) for name, rows in before.items()},
                'source_sha256': source_hash}, sort_keys=True), flush=True)
            return
        cutover_at = datetime.now(timezone.utc)
        accepted_states = {name: (states[name], restore_state_from_history(before[name], cutover_at))
                           for name in CHANNELS}
        directory = backup(originals, original_links, identities, before, source_hash)
        print('private_backup=' + str(directory), flush=True)
        changed = False
        try:
            current_links = links()
            require(all(item(name) == originals[name] for name in CHANNELS)
                    and all(len(current_links[name]) == 1
                            and current_links[name][0] == original_links[name]
                            for name in CHANNELS),
                    'managed source drift before transfer')
            require(all(history(db, identities[name]) == before[name]
                        for name in CHANNELS), 'JDBC history drift before transfer')
            changed = True
            for name, channel in CHANNELS.items():
                request('DELETE', '/links/' + name + '/' + quote(channel, safe=''))
            require(wait_for(lambda: all(not rows for rows in links().values()), 45),
                    'managed links did not withdraw')
            for name in CHANNELS:
                request('DELETE', '/items/' + name)
            require(wait_for(absent, 45), 'managed Items did not withdraw')
            require(sha256(SOURCE.read_bytes()).hexdigest() == source_hash,
                    'source drift during transfer')
            subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                           check=True, timeout=15)
            require(sha256(TARGET.read_bytes()).hexdigest() == source_hash,
                    'installed source differs')
            require(wait_for(lambda: ready(False, accepted_states), 90),
                    'file Item/link/database-backed state readback failed')
            require(settled_history_preserved(db, identities, before),
                    'historical JDBC rows changed after settling')
            require(healthy_thing(), 'OpenMeteo forecast Thing degraded')
        except BaseException:
            if changed:
                restore_managed(directory, originals, original_links, source_hash,
                                accepted_states)
                require(settled_history_preserved(db, identities, before),
                        'JDBC rows changed during rollback')
                print('managed_rollback_metadata_history_and_database_backed_state_verified=true',
                      flush=True)
            raise
        print(json.dumps({'status': 'file_provider_provisional',
            'items': list(CHANNELS), 'jdbc_item_ids': identities,
            'jdbc_rows_preserved': {name: len(rows) for name, rows in before.items()},
            'state_readback': {name: item(name)['state'] for name in CHANNELS},
            'original_states': states,
            'database_restore_states': {name: accepted_states[name][1] for name in CHANNELS},
            'source_sha256': source_hash, 'backup': str(directory),
            'natural_series_pending': True}, sort_keys=True), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-openmeteo-forecast-temperature-items.py --check|--apply')
    main(apply=sys.argv[1:] == ['--apply'])
