#!/usr/bin/env python3
"""Networkless restore-based AQI Item/link provider rehearsal; no live writes.

The restored snapshot contains private host data. It stays inside a disposable
networkless container and is never printed or copied into Git.
"""
import io
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

SNAPSHOT = Path('/home/sat/backups/earthship-energy/runtime-recovery-1x76m17d')
IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'
BINDING = Path('/var/lib/openhab/marketplace/bundles/165191/com.obones.binding.openmeteo-0.5.0.jar')
SOURCE = ROOT / 'openhab/file-config/items/openmeteo-current-aqi.items'
ITEM = 'Current_US_AQI'
CHANNEL = 'openmeteo:air-quality:local:aq:current#us-aqi'
LINK = ITEM + ' -> ' + CHANNEL


def run(args, data=None, *, check=True, timeout=45):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('isolated command failed: ' + args[0] + ' ' + args[1])
    return result


def install_bytes(container, directory, name, body, *, mode=0o644):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        member = tarfile.TarInfo(name)
        member.size = len(body)
        member.mode = mode
        archive.addfile(member, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '--no-same-owner',
         '--no-same-permissions', '-xf', '-', '-C', directory], output.getvalue())


def restore(container, scope):
    with (SNAPSHOT / (scope + '.tar')).open('rb') as archive:
        result = subprocess.run(['docker', 'exec', '-i', container, 'tar',
                                 '--no-same-owner', '--no-same-permissions', '-xf',
                                 '-', '-C', '/openhab/' + scope], stdin=archive,
                                capture_output=True, timeout=110)
    if result.returncode:
        raise RuntimeError('isolated restore failed: ' + scope)


def snapshot_registry(name):
    with tarfile.open(SNAPSHOT / 'userdata.tar') as archive:
        member = archive.extractfile('./jsondb/' + name)
        if member is None:
            raise RuntimeError('snapshot registry missing')
        return json.loads(member.read())


def isolated_get(container, path, header):
    result = run(['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '7',
                  '-w', '\nCODE:%{http_code}', '-H', '@-',
                  'http://127.0.0.1:8080/rest' + path], header,
                 check=False, timeout=11)
    body = result.stdout.decode(errors='replace')
    if '\nCODE:' not in body:
        return None, None
    body, code = body.rsplit('\nCODE:', 1)
    if code.strip() == '404':
        return 404, None
    if code.strip() != '200':
        return code.strip(), None
    try:
        return 200, json.loads(body)
    except ValueError:
        return None, None


def readback(container, header):
    item_code, item = isolated_get(container, '/items/' + ITEM + '?metadata=.*', header)
    link_code, links = isolated_get(container, '/links', header)
    if link_code != 200:
        return None
    matches = [link for link in links if link.get('itemName') == ITEM]
    return {'item_code': item_code, 'item': item, 'links': matches}


def wait_state(container, header, original, *, file_owned, seconds=240):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = readback(container, header)
        if state is not None:
            item = state['item']
            links = state['links']
            if item and item.get('editable') is (not file_owned) and len(links) == 1:
                link = links[0]
                if link.get('editable') is (not file_owned) and link.get('channelUID') == CHANNEL:
                    fields = ('name', 'type', 'label', 'category', 'tags', 'groupNames')
                    if all(item.get(field) == original.get(field) for field in fields):
                        return True
        time.sleep(3)
    return False


def main():
    original = oh.get('/items/' + ITEM + '?metadata=.*')
    links = [link for link in oh.get('/links') if link.get('itemName') == ITEM]
    if original.get('editable') is not True or len(links) != 1 or links[0].get('channelUID') != CHANNEL:
        raise RuntimeError('live AQI source or link changed; requalify first')
    if any(link.get('configuration') for link in links):
        raise RuntimeError('live AQI link configuration is not empty')
    source = SOURCE.read_bytes()
    marker = secrets.token_hex(8)
    container = None
    passed = False
    try:
        container = run(['docker', 'run', '-d', '--label', 'hex.aqi.qualification=' + marker,
                         '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
                         '--pids-limit', '384', '--memory', '4g',
                         '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                         '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
                         '--entrypoint', '/bin/sh', IMAGE, '-c',
                         'while [ ! -f /openhab/conf/items/openmeteo-current-aqi.items ]; do sleep 1; done; '
                         'exec /openhab/start.sh server'], timeout=45).stdout.decode().strip()
        owner = run(['docker', 'inspect', '--format',
                     '{{index .Config.Labels "hex.aqi.qualification"}}', container]).stdout.decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')
        for scope in ('conf', 'userdata'):
            restore(container, scope)
        items = snapshot_registry('org.openhab.core.items.Item.json')
        registered_links = snapshot_registry('org.openhab.core.thing.link.ItemChannelLink.json')
        if ITEM not in items or LINK not in registered_links:
            raise RuntimeError('snapshot lacks AQI managed originals')
        del items[ITEM]
        del registered_links[LINK]
        install_bytes(container, '/openhab/userdata/jsondb', 'org.openhab.core.items.Item.json',
                      json.dumps(items, separators=(',', ':')).encode())
        install_bytes(container, '/openhab/userdata/jsondb',
                      'org.openhab.core.thing.link.ItemChannelLink.json',
                      json.dumps(registered_links, separators=(',', ':')).encode())
        install_bytes(container, '/openhab/addons', 'openmeteo.jar', BINDING.read_bytes())
        header = ('Authorization: Bearer ' + oh.token() + '\n').encode()
        install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait_state(container, header, original, file_owned=True):
            raise RuntimeError('isolated file provider/link did not match live definition')
        print(json.dumps({'phase': 'first_boot', 'file_item_and_link_match': True}), flush=True)
        run(['docker', 'restart', container], timeout=90)
        if not wait_state(container, header, original, file_owned=True):
            raise RuntimeError('isolated restart did not restore file Item/link')
        print(json.dumps({'phase': 'full_restart', 'file_item_and_link_match': True}), flush=True)
        run(['docker', 'exec', container, 'rm', '/openhab/conf/items/' + SOURCE.name])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = readback(container, header)
            if state and state['item_code'] == 404 and not state['links']:
                break
            time.sleep(3)
        else:
            raise RuntimeError('file provider/link did not disappear before rollback')
        install_bytes(container, '/tmp', 'auth-header', header, mode=0o600)
        dto = {field: original[field] for field in ('name', 'type', 'label', 'category',
                                                    'tags', 'groupNames')}
        install_bytes(container, '/tmp', 'item.json', json.dumps(dto).encode(), mode=0o600)
        link_dto = {field: links[0][field] for field in ('itemName', 'channelUID')}
        link_dto['configuration'] = links[0].get('configuration', {})
        install_bytes(container, '/tmp', 'link.json', json.dumps(link_dto).encode(), mode=0o600)
        for path, payload in (('/items/' + ITEM, 'item.json'),
                              ('/links/' + ITEM + '/' + quote(CHANNEL, safe=''), 'link.json')):
            response = run(['docker', 'exec', container, 'curl', '-sS', '--max-time', '8',
                            '-o', '/dev/null', '-w', '%{http_code}', '-X', 'PUT',
                            '-H', '@/tmp/auth-header', '-H', 'Content-Type: application/json',
                            '--data-binary', '@/tmp/' + payload,
                            'http://127.0.0.1:8080/rest' + path], timeout=12)
            if response.stdout.decode().strip() not in {'200', '201', '202', '204'}:
                raise RuntimeError('isolated managed restoration failed')
        if not wait_state(container, header, original, file_owned=False, seconds=90):
            raise RuntimeError('managed rollback Item/link did not match')
        print(json.dumps({'phase': 'managed_rollback', 'managed_item_and_link_match': True}), flush=True)
        passed = True
    finally:
        if container is not None:
            owner = run(['docker', 'inspect', '--format',
                         '{{index .Config.Labels "hex.aqi.qualification"}}', container],
                        check=False).stdout.decode().strip()
            if owner == marker:
                run(['docker', 'rm', '-f', '-v', container], timeout=90)
    if passed:
        print(json.dumps({'status': 'passed', 'live_writes': 0,
                          'isolated_snapshot_removed': True,
                          'state_and_jdbc_recovery_verified': False}), flush=True)


if __name__ == '__main__':
    main()
