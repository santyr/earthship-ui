#!/usr/bin/env python3
"""Rehearse Astro icon Item/link ownership in a disposable networkless OpenHAB.

Only definitions, provider withdrawal and managed rollback are checked. Natural
Astro updates and JDBC history still require separate live cutover evidence.
"""
import importlib.util
import json
from pathlib import Path
import secrets
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'aqi_provider_rehearsal', ROOT / 'scripts/qualify-openmeteo-aqi-item.py')
aqi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aqi)

SOURCE = ROOT / 'openhab/file-config/items/astro-icons.items'
MAP = ROOT / 'openhab/transform/astro.map'
LABEL = 'hex.astro.icons.qualification'
CHANNELS = {
    'SunPhaseIcon': 'astro:sun:local:phase#name',
    'MoonPhaseicon': 'astro:moon:local:phase#name',
}
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')
PROFILE = {'profile': 'transform:MAP', 'function': 'astro.map'}


def exact(container, header, originals, *, file_owned):
    code, links = aqi.isolated_get(container, '/links', header)
    if code != 200:
        return False
    for name, expected in originals.items():
        code, item = aqi.isolated_get(container, '/items/' + name + '?metadata=.*', header)
        matches = [row for row in links if row.get('itemName') == name]
        if code != 200 or not isinstance(item, dict) or len(matches) != 1:
            return False
        if item.get('editable') is not (not file_owned):
            return False
        if any(item.get(key) != expected.get(key) for key in FIELDS):
            return False
        link = matches[0]
        if (link.get('editable') is not (not file_owned)
                or link.get('channelUID') != CHANNELS[name]
                or link.get('configuration') != PROFILE):
            return False
    return True


def wait_exact(container, header, originals, *, file_owned, seconds=240):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if exact(container, header, originals, file_owned=file_owned):
            return True
        time.sleep(3)
    return False


def absent(container, header):
    code, links = aqi.isolated_get(container, '/links', header)
    return (code == 200
            and not any(row.get('itemName') in CHANNELS for row in links)
            and all(aqi.isolated_get(container, '/items/' + name, header)[0] == 404
                    for name in CHANNELS))


def put(container, path, payload):
    aqi.install_bytes(container, '/tmp', 'astro-payload.json',
                      json.dumps(payload).encode(), mode=0o600)
    response = aqi.run(['docker', 'exec', container, 'curl', '-sS',
        '--max-time', '8', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT',
        '-H', '@/tmp/astro-auth-header', '-H', 'Content-Type: application/json',
        '--data-binary', '@/tmp/astro-payload.json',
        'http://127.0.0.1:8080/rest' + path], timeout=12)
    if response.stdout.decode().strip() not in ('200', '201', '202', '204'):
        raise RuntimeError('isolated managed rollback refused: ' + path)


def main():
    source = SOURCE.read_bytes()
    if source.count(b'\nString ') != 2:
        raise RuntimeError('unexpected Astro Item source cardinality')
    for name, channel in CHANNELS.items():
        if source.count(('String ' + name + ' ').encode()) != 1 or source.count(channel.encode()) != 1:
            raise RuntimeError('Astro Item source identity mismatch: ' + name)
    originals = {}
    live_links = aqi.oh.get('/links')
    for name, channel in CHANNELS.items():
        item = aqi.oh.get('/items/' + name + '?metadata=.*')
        matches = [row for row in live_links if row.get('itemName') == name]
        if (item.get('editable') is not True or item.get('type') != 'String'
                or len(matches) != 1 or matches[0].get('editable') is not True
                or matches[0].get('channelUID') != channel
                or matches[0].get('configuration') != PROFILE):
            raise RuntimeError('live Astro Item/link preflight changed: ' + name)
        originals[name] = item
    marker = secrets.token_hex(8)
    container = None
    try:
        container = aqi.run(['docker', 'run', '-d', '--label', LABEL + '=' + marker,
            '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
            '--pids-limit', '384', '--memory', '4g',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
            'while [ ! -f /openhab/conf/items/' + SOURCE.name + ' ]; do sleep 1; done; '
            'exec /openhab/start.sh server']).stdout.decode().strip()
        owner = aqi.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "' + LABEL + '"}}', container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')
        for scope in ('conf', 'userdata'):
            aqi.restore(container, scope)
        items = aqi.snapshot_registry('org.openhab.core.items.Item.json')
        links = aqi.snapshot_registry('org.openhab.core.thing.link.ItemChannelLink.json')
        for name, channel in CHANNELS.items():
            link_id = name + ' -> ' + channel
            if name not in items or link_id not in links:
                raise RuntimeError('restored registry lacks managed Astro original')
            del items[name]
            del links[link_id]
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
                          'org.openhab.core.items.Item.json',
                          json.dumps(items, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
                          'org.openhab.core.thing.link.ItemChannelLink.json',
                          json.dumps(links, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/conf/transform', MAP.name, MAP.read_bytes())
        header = ('Authorization: Bearer ' + aqi.oh.token() + '\n').encode()
        aqi.install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait_exact(container, header, originals, file_owned=True):
            raise RuntimeError('isolated file Item/link mismatch')
        print('first_boot_exact_file_items_and_links=2', flush=True)
        aqi.run(['docker', 'restart', container], timeout=90)
        if not wait_exact(container, header, originals, file_owned=True):
            raise RuntimeError('isolated restart Item/link mismatch')
        print('full_restart_exact_file_items_and_links=2', flush=True)
        aqi.run(['docker', 'exec', container, 'rm',
                 '/openhab/conf/items/' + SOURCE.name])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if absent(container, header):
                break
            time.sleep(3)
        else:
            raise RuntimeError('isolated file Items/links did not withdraw')
        aqi.install_bytes(container, '/tmp', 'astro-auth-header', header, mode=0o600)
        for name, channel in CHANNELS.items():
            put(container, '/items/' + name, aqi.managed_item_dto(originals[name]))
            put(container, '/links/' + name + '/' + quote(channel, safe=''),
                {'itemName': name, 'channelUID': channel, 'configuration': PROFILE})
        if not wait_exact(container, header, originals, file_owned=False, seconds=90):
            raise RuntimeError('isolated managed rollback mismatch')
        print('managed_rollback_exact_items_and_links=2', flush=True)
    finally:
        if container is not None:
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container],
                check=False).stdout.decode().strip()
            if owner == marker:
                aqi.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_container_removed=true', flush=True)
    print('status=passed; production_writes=0; natural_updates_and_jdbc=not_tested')


if __name__ == '__main__':
    main()
