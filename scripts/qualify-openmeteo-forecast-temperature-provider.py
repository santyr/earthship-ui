#!/usr/bin/env python3
"""Rehearse the three forecast-temperature Item/link providers without live writes.

The private restored registry stays in an owned networkless container, removed
on exit. This checks definitions and rollback, not JDBC or future-series data.
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

SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-temperature.items'
CHANNELS = {
    'Forecast_Temp': 'openmeteo:forecast:local:site:forecastHourly#temperature',
    'Forecast_Daily_High': 'openmeteo:forecast:local:site:forecastDaily#temperature-max',
    'Forecast_Daily_Low': 'openmeteo:forecast:local:site:forecastDaily#temperature-min',
}
TYPES = {name: 'Number:Temperature' for name in CHANNELS}
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')


def definitions_match(container, header, originals, *, file_owned):
    link_code, links = aqi.isolated_get(container, '/links', header)
    if link_code != 200:
        return False
    for name, expected in originals.items():
        code, item = aqi.isolated_get(container, '/items/' + name + '?metadata=.*', header)
        matches = [row for row in links if row.get('itemName') == name]
        if code != 200 or len(matches) != 1 or not isinstance(item, dict):
            return False
        if item.get('editable') is not (not file_owned):
            return False
        if any((item.get(key) or None) != (expected.get(key) or None)
               for key in FIELDS):
            return False
        link = matches[0]
        if (link.get('editable') is not (not file_owned)
                or link.get('channelUID') != CHANNELS[name]
                or link.get('configuration')):
            return False
    return True


def wait(container, header, originals, *, file_owned, seconds=240):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if definitions_match(container, header, originals, file_owned=file_owned):
            return True
        time.sleep(3)
    return False


def absent(container, header):
    code, links = aqi.isolated_get(container, '/links', header)
    if code != 200 or any(row.get('itemName') in CHANNELS for row in links):
        return False
    return all(aqi.isolated_get(container, '/items/' + name, header)[0] == 404
               for name in CHANNELS)


def put(container, path, header, payload):
    response = aqi.run(['docker', 'exec', '-i', container, 'curl', '-sS',
        '--max-time', '8', '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT',
        '-H', '@/tmp/forecast-auth-header', '-H', 'Content-Type: application/json',
        '--data-binary', '@-', 'http://127.0.0.1:8080/rest' + path],
        json.dumps(payload).encode(), timeout=12)
    if response.stdout.decode().strip() not in ('200', '201', '202', '204'):
        raise RuntimeError('isolated managed rollback refused: ' + path)


def main():
    source = SOURCE.read_bytes()
    for name, channel in CHANNELS.items():
        declaration = (f'{TYPES[name]} {name} ').encode()
        if source.count(declaration) != 1 or source.count(channel.encode()) != 1:
            raise RuntimeError('prepared forecast Item source is not exact')
    originals = {}
    live_links = aqi.oh.get('/links')
    for name, channel in CHANNELS.items():
        item = aqi.oh.get('/items/' + name + '?metadata=.*')
        matches = [row for row in live_links if row.get('itemName') == name]
        if (item.get('editable') is not True
                or item.get('type') != TYPES[name]
                or item.get('groupNames') != ['gForecast']
                or len(matches) != 1 or matches[0].get('editable') is not True
                or matches[0].get('channelUID') != channel
                or matches[0].get('configuration')):
            raise RuntimeError('live forecast Item/link preflight changed: ' + name)
        originals[name] = item
    marker = secrets.token_hex(8)
    container = None
    try:
        container = aqi.run(['docker', 'run', '-d',
            '--label', 'hex.forecast.temperature.qualification=' + marker,
            '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
            '--pids-limit', '384', '--memory', '4g',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
            'while [ ! -f /openhab/conf/items/' + SOURCE.name + ' ]; do sleep 1; done; '
            'exec /openhab/start.sh server']).stdout.decode().strip()
        owner = aqi.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "hex.forecast.temperature.qualification"}}',
            container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')
        for scope in ('conf', 'userdata'):
            aqi.restore(container, scope)
        items = aqi.snapshot_registry('org.openhab.core.items.Item.json')
        links = aqi.snapshot_registry('org.openhab.core.thing.link.ItemChannelLink.json')
        for name, channel in CHANNELS.items():
            link_id = name + ' -> ' + channel
            if name not in items or link_id not in links:
                raise RuntimeError('restored registry lacks managed forecast original')
            del items[name]
            del links[link_id]
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.items.Item.json',
            json.dumps(items, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.thing.link.ItemChannelLink.json',
            json.dumps(links, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/addons', 'openmeteo.jar',
                          aqi.BINDING.read_bytes())
        header = ('Authorization: Bearer ' + aqi.oh.token() + '\n').encode()
        aqi.install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait(container, header, originals, file_owned=True):
            raise RuntimeError('file provider did not match all three Items/links')
        print('first_boot_exact_file_items_and_links=3', flush=True)
        aqi.run(['docker', 'restart', container], timeout=90)
        if not wait(container, header, originals, file_owned=True):
            raise RuntimeError('full restart lost forecast Item/link definition')
        print('full_restart_exact_file_items_and_links=3', flush=True)
        aqi.run(['docker', 'exec', container, 'rm',
                 '/openhab/conf/items/' + SOURCE.name])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if absent(container, header):
                break
            time.sleep(3)
        else:
            raise RuntimeError('file provider did not withdraw before rollback')
        aqi.install_bytes(container, '/tmp', 'forecast-auth-header', header,
                          mode=0o600)
        for name, channel in CHANNELS.items():
            put(container, '/items/' + name, header,
                aqi.managed_item_dto(originals[name]))
            put(container, '/links/' + name + '/' + quote(channel, safe=''),
                header, {'itemName': name, 'channelUID': channel,
                         'configuration': {}})
        if not wait(container, header, originals, file_owned=False, seconds=90):
            raise RuntimeError('managed rollback did not match all definitions')
        print('managed_rollback_exact_items_and_links=3', flush=True)
    finally:
        if container is not None:
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "hex.forecast.temperature.qualification"}}',
                container], check=False).stdout.decode().strip()
            if owner == marker:
                aqi.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_container_removed=true', flush=True)
    print('status=passed; production_writes=0; jdbc_and_series_recovery=not_tested')


if __name__ == '__main__':
    main()
