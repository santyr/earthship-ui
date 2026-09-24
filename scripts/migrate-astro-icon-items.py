#!/usr/bin/env python3
"""Attended, reversible transfer of the two observational Astro icon Items.

--check is read-only. --apply privately saves managed definitions and JDBC
history, then transfers only the two Items/links to their prepared file source.
Natural Astro publication remains a separate post-cutover gate.
"""
from collections import Counter
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

SOURCE = ROOT / 'openhab/file-config/items/astro-icons.items'
SOURCE_SHA256 = 'e4ac1e2f889b5ba6be4e770ca76aeb324e0b38fac7e81ac39e05f1f2847e134b'
MAP_SOURCE = ROOT / 'openhab/transform/astro.map'
MAP_TARGET = Path('/etc/openhab/transform/astro.map')
MAP_SHA256 = '25f76f802ab403d97bcf4608ffce41529455a1de79a7964fd805ba7d8f8dc7ad'
TARGET = Path('/etc/openhab/items/astro-icons.items')
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
ITEM_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')
CHANNELS = {
    'SunPhaseIcon': 'astro:sun:local:phase#name',
    'MoonPhaseicon': 'astro:moon:local:phase#name',
}
EXPECTED = {
    'SunPhaseIcon': ('Sun Phase Icon', 'sun', ['Sun']),
    'MoonPhaseicon': ('Moon Phase Icon', 'moon', ['Moon']),
}
PROFILE = {'profile': 'transform:MAP', 'function': 'astro.map'}
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def item(name):
    try:
        return oh.get('/items/' + name + '?metadata=.*')
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def links():
    all_links = oh.get('/links')
    return {name: [row for row in all_links if row.get('itemName') == name]
            for name in CHANNELS}


def exact_item(row, name, managed, states=None):
    label, category, groups = EXPECTED[name]
    return (isinstance(row, dict) and row.get('editable') is managed
            and row.get('name') == name and row.get('type') == 'String'
            and row.get('label') == label and row.get('category') == category
            and row.get('tags') == [] and row.get('groupNames') == groups
            and not row.get('metadata') and isinstance(row.get('state'), str)
            and row['state'].startswith('iconify:mdi:')
            and (states is None or row['state'] in states[name]))


def exact_link(row, name, managed):
    return (row.get('editable') is managed and row.get('itemName') == name
            and row.get('channelUID') == CHANNELS[name]
            and row.get('configuration') == PROFILE)


def ready(managed, states):
    found = links()
    return all(exact_item(item(name), name, managed, states)
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


def healthy_things():
    for kind in ('sun', 'moon'):
        uid = 'astro:' + kind + ':local'
        thing = oh.get('/things/' + uid + '?summary=false')
        channels = {row.get('uid') for row in thing.get('channels', [])}
        if (thing.get('UID') != uid or thing.get('statusInfo', {}).get('status') != 'ONLINE'):
            return False
        if ('astro:' + kind + ':local:phase#name') not in channels:
            return False
    return True


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
        raise RuntimeError('Astro ' + method + ' HTTP ' + str(error.code)) from None


def history(db, identity):
    with db.cursor() as cursor:
        cursor.execute("SET statement_timeout='10s'")
        cursor.execute(sql.SQL('SELECT time,value FROM public.{} ORDER BY time,value').format(
            sql.Identifier('item' + str(identity).zfill(4))))
        return cursor.fetchall()


def history_preserved(db, identities, before):
    return all(not (Counter(before[name]) - Counter(history(db, identities[name])))
               for name in CHANNELS)


def private_file(directory, name, body):
    descriptor = os.open(directory / name,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def backup(originals, original_links, identities, before):
    info = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'private backup root unsafe')
    directory = BACKUP_ROOT / ('astro-icons-'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    private_file(directory, 'managed-and-history.json', json.dumps({
        'items': originals, 'links': original_links,
        'source_sha256': SOURCE_SHA256, 'map_sha256': MAP_SHA256,
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


def restore_managed(directory, originals, original_links, states):
    if TARGET.exists():
        require(not TARGET.is_symlink()
                and sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                'file target drift; manual recovery required')
        TARGET.rename(directory / 'failed-file.items')
        require(wait_for(absent, 60), 'file Items/links did not withdraw')
    for name in CHANNELS:
        current = item(name)
        if current is None:
            request('PUT', '/items/' + name,
                    {field: originals[name][field] for field in FIELDS
                     if field in originals[name]})
        else:
            require(exact_item(current, name, True),
                    'unexpected managed Item during rollback: ' + name)
    found = links()
    for name, channel in CHANNELS.items():
        if not found[name]:
            request('PUT', '/links/' + name + '/' + quote(channel, safe=''),
                    {key: original_links[name][key]
                     for key in ('itemName', 'channelUID', 'configuration')})
        else:
            require(len(found[name]) == 1 and exact_link(found[name][0], name, True),
                    'unexpected link during rollback: ' + name)
    require(wait_for(lambda: ready(True, states), 90),
            'managed rollback Item/link/state did not recover')


def main(apply):
    require(not TARGET.exists() and not TARGET.is_symlink(), 'target already exists')
    require(sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256,
            'prepared Astro Item source changed')
    require(sha256(MAP_SOURCE.read_bytes()).hexdigest() == MAP_SHA256
            and sha256(MAP_TARGET.read_bytes()).hexdigest() == MAP_SHA256,
            'canonical/live Astro MAP drift')
    originals = {name: item(name) for name in CHANNELS}
    found = links()
    states = {name: {originals[name]['state']} if originals[name] else set()
              for name in CHANNELS}
    require(all(exact_item(originals[name], name, True)
                and len(found[name]) == 1 and exact_link(found[name][0], name, True)
                for name in CHANNELS) and healthy_things(),
            'managed Astro Item/link/Thing preflight failed')
    original_links = {name: found[name][0] for name in CHANNELS}
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
                rows = cursor.fetchall()
                require(len(rows) == 1 and type(rows[0][0]) is int,
                        'JDBC Item identity missing: ' + name)
                identities[name] = rows[0][0]
                before[name] = history(db, identities[name])
                require(len(before[name]) >= 1 and before[name][-1][1] in states[name],
                        'JDBC state/history mismatch: ' + name)
        if not apply:
            print(json.dumps({'status': 'preflight_passed',
                'jdbc_item_ids': identities,
                'jdbc_rows': {name: len(rows) for name, rows in before.items()},
                'source_sha256': SOURCE_SHA256}, sort_keys=True), flush=True)
            return
        directory = backup(originals, original_links, identities, before)
        print('private_backup=' + str(directory), flush=True)
        changed = False
        try:
            current_links = links()
            require(all(item(name) == originals[name]
                        and len(current_links[name]) == 1
                        and current_links[name][0] == original_links[name]
                        for name in CHANNELS), 'managed Astro source drift')
            require(all(history(db, identities[name]) == before[name]
                        for name in CHANNELS), 'JDBC history drift before transfer')
            changed = True
            for name, channel in CHANNELS.items():
                request('DELETE', '/links/' + name + '/' + quote(channel, safe=''))
            require(wait_for(lambda: all(not rows for rows in links().values()), 45),
                    'managed Astro links did not withdraw')
            for name in CHANNELS:
                request('DELETE', '/items/' + name)
            require(wait_for(absent, 45), 'managed Astro Items did not withdraw')
            require(sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA256,
                    'Astro source drift during transfer')
            subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                           check=True, timeout=15)
            require(sha256(TARGET.read_bytes()).hexdigest() == SOURCE_SHA256,
                    'installed Astro source differs')
            require(wait_for(lambda: ready(False, states), 90),
                    'file Astro Item/link/state readback failed')
            require(history_preserved(db, identities, before),
                    'historical Astro JDBC rows changed')
            require(healthy_things(), 'Astro Thing degraded')
        except BaseException:
            if changed:
                restore_managed(directory, originals, original_links, states)
                require(history_preserved(db, identities, before),
                        'JDBC rows changed during rollback')
                print('managed_rollback_history_and_state_verified=true', flush=True)
            raise
        print(json.dumps({'status': 'file_provider_provisional',
            'items': list(CHANNELS), 'jdbc_item_ids': identities,
            'jdbc_rows_preserved': {name: len(rows) for name, rows in before.items()},
            'state_readback': {name: item(name)['state'] for name in CHANNELS},
            'source_sha256': SOURCE_SHA256, 'backup': str(directory),
            'natural_astro_updates_pending': True}, sort_keys=True), flush=True)
    finally:
        db.close()


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-astro-icon-items.py --check|--apply')
    main(apply=sys.argv[1:] == ['--apply'])
