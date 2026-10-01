#!/usr/bin/env python3
"""Exact Moon display Item/link rehearsal; production access is GET-only.

Reuses the existing private, networkless OpenHAB restoration harness. All
provider withdrawal, restart and managed rollback happen in the owned container.
Does not prove production JDBC/state recovery or authorize a live handoff.
"""
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import secrets
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'moon_aqi_rehearsal', ROOT / 'scripts/qualify-openmeteo-aqi-item.py')
aqi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aqi)

SOURCE = ROOT / 'openhab/file-config/items/moon-phase-readings.items'
SOURCE_SHA256 = 'fc96f70a65e8de45479cda6b8c2c97840ae78eaedc5334111036013143e3941e'
ASTRO = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/'
             'org.openhab.binding.astro/5.2.1/org.openhab.binding.astro-5.2.1.jar')
ASTRO_SHA256 = '1a3b8207ec49834022706359bff60ff2f4eaa1354d392c48850cb418de63e7db'
LABEL = 'hex.moon.phase.qualification'
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames', 'metadata',
          'unitSymbol', 'stateDescription')
READINGS = {
    'Moon_MoonPhaseName': {
        'type': 'String', 'label': 'Moon Phase Name',
        'channel': 'astro:moon:local:phase#name',
        'unit': None,
        'profile': {'profile': 'system:default', 'function': 'astro.map'},
    },
    'Moon_MoonIllumination': {
        'type': 'Number:Dimensionless', 'label': 'Moon Illumination',
        'channel': 'astro:moon:local:phase#illumination', 'profile': {},
        'unit': 'one',
    },
}
SEMANTICS = {'semantics': {'value': 'Point', 'config': {'isPointOf': 'Moon'},
                           'editable': False}}


def exact_definition(item, name, *, managed):
    expected = READINGS[name]
    return (item.get('editable') is managed and item.get('name') == name
            and item.get('type') == expected['type']
            and item.get('label') == expected['label']
            and item.get('category') in ('', None)
            and item.get('unitSymbol') == expected['unit']
            and item.get('tags') == ['Point'] and item.get('groupNames') == ['Moon']
            and item.get('metadata') == SEMANTICS)


def exact_link(link, name, *, managed):
    expected = READINGS[name]
    return (link.get('editable') is managed and link.get('itemName') == name
            and link.get('channelUID') == expected['channel']
            and link.get('configuration') == expected['profile'])


def preflight(items, links):
    """No identity/provider/profile/semantic normalization beyond empty category."""
    originals = {}
    for name in READINGS:
        matches = [row for row in items if row.get('name') == name]
        attached = [row for row in links if row.get('itemName') == name]
        if (len(matches) != 1 or not exact_definition(matches[0], name, managed=True)
                or len(attached) != 1 or not exact_link(attached[0], name, managed=True)):
            raise ValueError('Moon reading definition or link changed')
        originals[name] = matches[0]
    return originals


def checked_source():
    source = SOURCE.read_bytes()
    if sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('staged Moon source changed')
    return source


def checked_astro():
    body = ASTRO.read_bytes()
    if sha256(body).hexdigest() != ASTRO_SHA256:
        raise ValueError('cached Astro bundle changed')
    return body


def exact(container, header, originals, *, file_owned):
    code, links = aqi.isolated_get(container, '/links', header)
    if code != 200:
        return False
    for name, original in originals.items():
        code, item = aqi.isolated_get(container, '/items/' + name + '?metadata=.*', header)
        attached = [row for row in links if row.get('itemName') == name]
        if (code != 200 or not isinstance(item, dict)
                or not exact_definition(item, name, managed=not file_owned)
                or len(attached) != 1 or not exact_link(attached[0], name, managed=not file_owned)):
            return False
        # Empty managed categories are normalized to null by some file providers.
        if any(item.get(field) != original.get(field) for field in FIELDS if field != 'category'):
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
    return (code == 200 and not any(row.get('itemName') in READINGS for row in links)
            and all(aqi.isolated_get(container, '/items/' + name, header)[0] == 404
                    for name in READINGS))


def put(container, path, payload):
    aqi.install_bytes(container, '/tmp', 'moon-payload.json', json.dumps(payload).encode(), mode=0o600)
    response = aqi.run(['docker', 'exec', container, 'curl', '-sS', '--max-time', '8',
        '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT',
        '-H', '@/tmp/moon-auth-header', '-H', 'Content-Type: application/json',
        '--data-binary', '@/tmp/moon-payload.json', 'http://127.0.0.1:8080/rest' + path], timeout=12)
    if response.stdout.decode().strip() not in ('200', '201', '202', '204'):
        raise RuntimeError('isolated Moon managed rollback refused')


def main():
    # These are public display definitions. Never export general live DTOs to Git.
    source = checked_source()
    astro = checked_astro()
    live_links = aqi.oh.get('/links')
    originals = preflight([aqi.oh.get('/items/' + name + '?metadata=.*')
                           for name in READINGS], live_links)
    marker = secrets.token_hex(8)
    container = None
    try:
        container = aqi.run(['docker', 'run', '-d', '--label', LABEL + '=' + marker,
            '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
            '--pids-limit', '384', '--memory', '2g', '--memory-swap', '2g',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
            '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
            'while [ ! -f /openhab/conf/items/' + SOURCE.name + ' ]; do sleep 1; done; '
            'exec /openhab/start.sh server']).stdout.decode().strip()
        owner = aqi.run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "' + LABEL + '"}}', container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated Moon container ownership mismatch')
        for scope in ('conf', 'userdata'):
            aqi.restore(container, scope)
        # Offline feature resolution cannot download the configured binding.
        # Its exact types are required for read-only state descriptions/options.
        aqi.install_bytes(container, '/openhab/addons', ASTRO.name, astro)
        items = aqi.snapshot_registry('org.openhab.core.items.Item.json')
        links = aqi.snapshot_registry('org.openhab.core.thing.link.ItemChannelLink.json')
        for name, reading in READINGS.items():
            link_id = name + ' -> ' + reading['channel']
            if name not in items or link_id not in links:
                raise RuntimeError('snapshot lacks original Moon Item/link')
            del items[name]
            del links[link_id]
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.items.Item.json', json.dumps(items, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
            'org.openhab.core.thing.link.ItemChannelLink.json', json.dumps(links, separators=(',', ':')).encode())
        header = ('Authorization: Bearer ' + aqi.oh.token() + '\n').encode()
        aqi.install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait_exact(container, header, originals, file_owned=True):
            raise RuntimeError('isolated Moon file Item/link mismatch')
        print('first_boot_exact_file_items_and_links=2', flush=True)
        aqi.run(['docker', 'restart', container], timeout=90)
        if not wait_exact(container, header, originals, file_owned=True):
            raise RuntimeError('isolated Moon restart Item/link mismatch')
        print('full_restart_exact_file_items_and_links=2', flush=True)
        aqi.run(['docker', 'exec', container, 'rm', '/openhab/conf/items/' + SOURCE.name])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if absent(container, header):
                break
            time.sleep(3)
        else:
            raise RuntimeError('isolated Moon file Items/links did not withdraw')
        aqi.install_bytes(container, '/tmp', 'moon-auth-header', header, mode=0o600)
        for name, reading in READINGS.items():
            put(container, '/items/' + name, aqi.managed_item_dto(originals[name]))
            put(container, '/links/' + name + '/' + quote(reading['channel'], safe=''),
                {'itemName': name, 'channelUID': reading['channel'],
                 'configuration': reading['profile']})
        if not wait_exact(container, header, originals, file_owned=False, seconds=90):
            raise RuntimeError('isolated Moon managed rollback mismatch')
        print('managed_rollback_exact_items_and_links=2', flush=True)
    finally:
        if container:
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container], check=False).stdout.decode().strip()
            if owner != marker:
                raise RuntimeError('Moon cleanup ownership mismatch; manual review required')
            aqi.run(['docker', 'rm', '-f', '-v', container], timeout=60)
            print('owned_container_and_volumes_removed=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Private snapshot contents and HTTP/crypto diagnostics must not escape.
        raise SystemExit('Moon provider rehearsal failed: ' + type(error).__name__) from None
