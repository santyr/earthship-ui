#!/usr/bin/env python3
"""Attended, receipt-bound managed-to-file OpenMeteo Thing transfer."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import forecast_intel as forecast  # noqa: E402
from openmeteo_config import mismatch_keys  # noqa: E402

SOURCE = ROOT / 'openhab/file-config/things/openmeteo.things'
TARGET = Path('/etc/openhab/things/openmeteo.things')
SOURCE_SHA256 = '2d0f1fc402a23115a54bc0e3ce110eacc4424581903fcaed77f4923535d6b585'
BINDING = Path('/var/lib/openhab/marketplace/bundles/165191/com.obones.binding.openmeteo-0.5.0.jar')
BINDING_SHA256 = '47b4682de46ce1c340861c555fba9615b5331bb4db6bc615e7dacf4001ba4f8f'
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
THING_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.Thing.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')
UIDS = ('openmeteo:openmeteo:local', 'openmeteo:forecast:local:site',
        'openmeteo:air-quality:local:aq')
DELETE_ORDER = (UIDS[1], UIDS[2], UIDS[0])
ITEMS = ('Forecast_Temp', 'Current_US_AQI', 'Forecast_Daily_High', 'Forecast_Daily_Low')


def request(method, path, *, body=None):
    headers = {'Authorization': 'Bearer ' + forecast.auth_token()}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(forecast.BASE + path, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=12) as response:
            return response.status
    except HTTPError as exc:
        raise RuntimeError(f'OpenHAB {method} returned HTTP {exc.code}') from None


def things():
    return {entry['UID']: entry for entry in forecast.oh_get('/things?summary=false')
            if entry.get('UID') in UIDS}


def links():
    return {(entry['itemName'], entry['channelUID']) for entry in forecast.oh_get('/links')
            if any(entry.get('channelUID', '').startswith(uid + ':') for uid in UIDS)}


def link_configuration_empty():
    return all(not entry.get('configuration') for entry in forecast.oh_get('/links')
               if any(entry.get('channelUID', '').startswith(uid + ':') for uid in UIDS))


def supported_configuration_matches(current, original):
    for uid in UIDS:
        description = forecast.oh_get('/thing-types/' + original[uid]['thingTypeUID'])
        if mismatch_keys(current[uid], original[uid], description):
            return False
    return True


def states_valid():
    return all(forecast.oh_get('/items/' + item)['state']
               not in (None, 'NULL', 'UNDEF', 'REFRESH') for item in ITEMS)


def same_definitions(current, original, *, file_owned):
    if set(current) != set(UIDS):
        return False
    return all(
        entry.get('editable') is (not file_owned)
        and entry.get('thingTypeUID') == original[uid].get('thingTypeUID')
        and entry.get('bridgeUID') == original[uid].get('bridgeUID')
        and entry.get('label') == original[uid].get('label')
        and {channel['uid'] for channel in entry.get('channels', [])}
        == {channel['uid'] for channel in original[uid].get('channels', [])}
        for uid, entry in current.items()
    )


def wait_for(predicate, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (OSError, RuntimeError, KeyError, ValueError):
            pass
        time.sleep(2)
    return False


def private_file(directory, name, body):
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())
    return path


def backup(original, original_links, source_hash):
    BACKUP_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = BACKUP_ROOT.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError('private backup root ownership or mode is unsafe')
    directory = BACKUP_ROOT / ('openmeteo-' + datetime.now(timezone.utc).strftime(
        '%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    payload = json.dumps({'things': original,
                          'links': sorted([list(pair) for pair in original_links]),
                          'source_sha256': source_hash}, sort_keys=True).encode()
    private_file(directory, 'rest-snapshot.json', payload)
    private_file(directory, 'thing-jsondb.json', THING_DB.read_bytes())
    private_file(directory, 'link-jsondb.json', LINK_DB.read_bytes())
    directory_fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return directory


def recreate(original):
    for uid in UIDS:
        if uid in things():
            continue
        entry = original[uid]
        body = {key: entry[key] for key in ('UID', 'thingTypeUID', 'label',
                                            'configuration')}
        if entry.get('bridgeUID'):
            body['bridgeUID'] = entry['bridgeUID']
        code = request('POST', '/things', body=json.dumps(body).encode())
        if code not in (200, 201, 202):
            raise RuntimeError('managed Thing recreation was not accepted')


def rollback(original, original_links):
    if TARGET.exists():
        TARGET.unlink()
    if not wait_for(lambda: not any(not entry.get('editable')
                                    for entry in things().values()), seconds=45):
        raise RuntimeError('file-owned Things did not unload during rollback')
    recreate(original)
    if not wait_for(lambda: same_definitions(things(), original, file_owned=False)
                    and links() == original_links, seconds=60):
        raise RuntimeError('managed Thing rollback readback failed')


def main():
    if sys.argv[1:] != ['--apply']:
        raise SystemExit('usage: migrate-openmeteo-things.py --apply')
    if TARGET.exists() or TARGET.is_symlink():
        raise RuntimeError('target Thing file already exists')
    source_bytes = SOURCE.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    if source_hash != SOURCE_SHA256 or sha256(BINDING.read_bytes()).hexdigest() != BINDING_SHA256:
        raise RuntimeError('prepared source or installed binding hash drifted')
    original = things()
    if set(original) != set(UIDS) or any(
            entry.get('editable') is not True or
            entry.get('statusInfo', {}).get('status') != 'ONLINE'
            for entry in original.values()):
        raise RuntimeError('managed Thing preflight failed')
    original_links = links()
    bridge_config = original[UIDS[0]].get('configuration', {})
    if any(bridge_config.get(name) for name in
           ('APIKey', 'proxyHost', 'proxyUser', 'proxyPassword')):
        raise RuntimeError('OpenMeteo bridge gained private credentials or a proxy')
    if len(original_links) != 12 or not link_configuration_empty() or not states_valid():
        raise RuntimeError('link or Item-state preflight failed')
    directory = backup(original, original_links, source_hash)
    print('private_backup=' + str(directory), flush=True)
    changed = False
    try:
        for uid in DELETE_ORDER:
            changed = True
            code = request('DELETE', '/things/' + quote(uid, safe='') + '?force=true')
            if code not in (200, 202, 204):
                raise RuntimeError('managed Thing removal was not accepted')
        if not wait_for(lambda: not things() and links() == original_links, seconds=20):
            raise RuntimeError('managed Things or links did not reach transfer boundary')
        if sha256(SOURCE.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError('source changed during transfer')
        subprocess.run(['install', '-m', '0644', str(SOURCE), str(TARGET)],
                       check=True, timeout=15)
        if sha256(TARGET.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError('installed Thing file mismatch')
        if not wait_for(lambda: same_definitions(things(), original, file_owned=True)
                        and links() == original_links, seconds=90):
            raise RuntimeError('file-owned Thing/channel/link readback failed')
        if not supported_configuration_matches(things(), original):
            raise RuntimeError('file-owned Thing configuration drifted')
        if not wait_for(lambda: all(entry.get('statusInfo', {}).get('status') == 'ONLINE'
                                    for entry in things().values()) and states_valid(),
                        seconds=120):
            raise RuntimeError('online or consumed Item readback failed')
    except BaseException:
        if changed:
            rollback(original, original_links)
            print('managed_rollback_verified=true', flush=True)
        raise
    print(json.dumps({'status': 'file_owned_verified', 'things': len(UIDS),
                      'links': len(original_links), 'all_online': True,
                      'source_sha256': source_hash, 'backup': str(directory)},
                     sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
