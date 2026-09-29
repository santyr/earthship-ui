#!/usr/bin/env python3
"""Networkless BatteryIcon file withdrawal and managed-metadata rollback.

This never writes to production. The established private recovery snapshot
stays inside an owned, networkless container without host mounts or volumes.
"""
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    'file_qualifier', ROOT / 'scripts/qualify-forecast-json-file-provider.py')
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)
spec = importlib.util.spec_from_file_location(
    'aqi_rehearsal', ROOT / 'scripts/qualify-openmeteo-aqi-item.py')
aqi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aqi)

ITEM = 'BatteryIcon'
SOURCE = ROOT / 'openhab/file-config/items/battery-icon.items'
LABEL = 'hex.battery-icon.rollback'
FIELDS = ('name', 'type', 'label', 'category', 'tags', 'groupNames')


def request(container, method, path, payload=None):
    args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
            '-w', '\nCODE:%{http_code}', '-H', '@/tmp/battery-auth-header',
            '-X', method]
    body = None
    if payload is not None:
        args += ['-H', 'Content-Type: application/json', '--data-binary', '@-']
        body = json.dumps(payload).encode()
    args.append('http://127.0.0.1:8080/rest' + path)
    result = qualifier.run(args, body, timeout=12).decode()
    if '\nCODE:' not in result:
        raise RuntimeError('isolated REST response missing status')
    text, status = result.rsplit('\nCODE:', 1)
    return int(status.strip()), json.loads(text) if text.strip().startswith('{') else None


def wait(container, original, *, file_owned=None, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            status, item = request(container, 'GET', '/items/' + ITEM + '?metadata=.*')
        except RuntimeError:  # OpenHAB's REST listener is not ready at first boot.
            time.sleep(2)
            continue
        if file_owned is None and status == 404:
            return True
        if status == 200 and item and item.get('editable') is (not file_owned):
            expected_metadata = json.loads(json.dumps(original['metadata']))
            if file_owned:
                expected_metadata['stateDescription']['editable'] = False
            fields_match = all((item.get(field) or None) == (original.get(field) or None)
                               if field == 'category' else item.get(field) == original.get(field)
                               for field in FIELDS)
            if (fields_match
                    and item.get('metadata') == expected_metadata
                    and item.get('stateDescription') == original.get('stateDescription')):
                return True
        time.sleep(2)
    return False


def main():
    live = oh.get('/items/' + ITEM + '?metadata=.*')
    expected = {'stateDescription': {'value': ' ',
                                     'config': {'pattern': '"Battery Icon [%s]" <iconify>'},
                                     'editable': live.get('editable')}}
    if (live.get('editable') not in (True, False) or live.get('type') != 'String'
            or live.get('metadata') != expected):
        raise RuntimeError('live BatteryIcon definition changed')
    original = json.loads(json.dumps(live))
    original['metadata'] = {
                'stateDescription': {'value': ' ',
                                     'config': {'pattern': '"Battery Icon [%s]" <iconify>'},
                                     'editable': True}}
    if any(link.get('itemName') == ITEM for link in oh.get('/links')):
        raise RuntimeError('live BatteryIcon unexpectedly linked')
    source = SOURCE.read_bytes()
    if source.count(b'String BatteryIcon ') != 1:
        raise RuntimeError('staged BatteryIcon source changed')
    marker = uuid.uuid4().hex
    container = qualifier.run([
        'docker', 'run', '-d', '--label', LABEL + '=' + marker,
        '--network', 'none', '--hostname', 'localhost', '--cap-drop', 'ALL',
        '--memory', '4g', '--pids-limit', '384',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
        '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
        '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
        'while [ ! -f /openhab/conf/items/' + SOURCE.name + ' ]; do sleep 1; done; '
        'exec /openhab/start.sh server']).decode().strip()
    try:
        info = json.loads(qualifier.run(['docker', 'inspect', container]))[0]
        host = info['HostConfig']
        if (host['NetworkMode'] != 'none' or host['Privileged']
                or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
                or info['AppArmorProfile'] != 'docker-default'):
            raise RuntimeError('disposable isolation mismatch')
        for scope in ('conf', 'userdata'):
            aqi.restore(container, scope)
        items = aqi.snapshot_registry('org.openhab.core.items.Item.json')
        metadata = aqi.snapshot_registry('org.openhab.core.items.Metadata.json')
        metadata_key = 'stateDescription:' + ITEM
        if ITEM not in items or metadata_key not in metadata:
            raise RuntimeError('private recovery snapshot lacks BatteryIcon')
        del items[ITEM]
        del metadata[metadata_key]
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
                          'org.openhab.core.items.Item.json',
                          json.dumps(items, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/openhab/userdata/jsondb',
                          'org.openhab.core.items.Metadata.json',
                          json.dumps(metadata, separators=(',', ':')).encode())
        aqi.install_bytes(container, '/tmp', 'battery-auth-header',
                          ('Authorization: Bearer ' + oh.token() + '\n').encode(), mode=0o600)
        aqi.install_bytes(container, '/openhab/conf/items', SOURCE.name, source)
        if not wait(container, original, file_owned=True, seconds=240):
            raise RuntimeError('isolated file provider mismatch')
        print('file_provider_metadata_exact=true', flush=True)
        qualifier.run(['docker', 'exec', container, 'rm',
                       '/openhab/conf/items/' + SOURCE.name])
        if not wait(container, original, file_owned=None):
            raise RuntimeError('isolated file Item did not withdraw')
        payload = {field: original[field] for field in FIELDS if field in original}
        status, _ = request(container, 'PUT', '/items/' + ITEM, payload)
        if status not in (200, 201, 202, 204):
            raise RuntimeError('isolated managed Item restore refused: HTTP ' + str(status))
        status, _ = request(container, 'PUT', '/items/' + ITEM + '/metadata/stateDescription',
                            {'value': ' ', 'config': original['metadata']['stateDescription']['config']})
        if status not in (200, 201, 202, 204):
            raise RuntimeError('isolated managed metadata restore refused: HTTP ' + str(status))
        if not wait(container, original, file_owned=False):
            raise RuntimeError('isolated managed metadata rollback mismatch')
        print('managed_metadata_rollback_exact=true', flush=True)
    finally:
        owner = qualifier.run(['docker', 'inspect', '--format',
                               '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership changed')
        qualifier.run(['docker', 'rm', '-f', '-v', container])
        print('owned_container_and_tmpfs_removed=true', flush=True)
    print('production_writes=0; jdbc_and_live_transfer=not_tested')


if __name__ == '__main__':
    main()
