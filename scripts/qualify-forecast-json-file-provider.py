#!/usr/bin/env python3
"""Qualify prepared forecast JSON Items in an isolated OpenHAB 5.2.1 provider.

Read-only against production. The disposable container has no network, host
mounts, production credentials, or persisted data; it is removed on exit.
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

NAMES = ('Forecast_Hourly_JSON', 'Forecast_Daily_JSON', 'Forecast_10Day_JSON')
SOURCE = ROOT / 'openhab/file-config/items/forecast-json.items'
IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'


def run(args, data=None, timeout=45):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError('isolated operation failed: ' + args[0])
    return result.stdout


def main(names=NAMES, source_path=SOURCE, item_type='String'):
    source = source_path.read_bytes()
    if any(source.count((item_type + ' ' + name + ' ').encode()) != 1 for name in names):
        raise ValueError('prepared file does not define exactly the expected Items')
    originals = {name: oh.get('/items/' + name + '?metadata=.*') for name in names}
    if any(item.get('editable') not in (True, False) or item.get('type') != item_type
           for item in originals.values()):
        raise ValueError('live forecast Item preflight failed')
    if any(link.get('itemName') in names for link in oh.get('/links')):
        raise ValueError('prepared Item has an unexpected channel link')
    marker = uuid4().hex
    cid = run(['docker', 'run', '-d', '--label', 'hex.forecast.qualifier=' + marker,
        '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
        '--memory', '1536m', '--cpus', '1', '--pids-limit', '256',
        '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
        '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
        '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
        '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=32m,uid=9001,gid=9001',
        '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
        '--entrypoint', '/bin/sh', IMAGE, '-c',
        'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
        'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']).decode().strip()
    try:
        info = json.loads(run(['docker', 'inspect', cid]))[0]
        host = info['HostConfig']
        if (host['NetworkMode'] != 'none' or host['Privileged']
                or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
                or info['AppArmorProfile'] != 'docker-default'):
            raise RuntimeError('disposable isolation mismatch')
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            entry = tarfile.TarInfo('items/' + source_path.name)
            entry.size, entry.mode = len(source), 0o644
            tar.addfile(entry, io.BytesIO(source))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/openhab/conf'],
            archive.getvalue())
        run(['docker', 'exec', cid, 'touch', '/tmp/ready'])
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                rows = json.loads(run(['docker', 'exec', cid, 'curl', '-fsS',
                    '--max-time', '3', 'http://127.0.0.1:8080/rest/items?metadata=.*']))
                if all(name in {item['name'] for item in rows} for name in names):
                    time.sleep(20)  # reject a transient first-ready provider
                    break
            except (RuntimeError, ValueError):
                pass
            time.sleep(3)
        else:
            raise RuntimeError('isolated Item provider startup timeout')
        for name, expected in originals.items():
            actual = json.loads(run(['docker', 'exec', cid, 'curl', '-fsS',
                '--max-time', '3', '--retry', '5', '--retry-all-errors',
                '--retry-delay', '2',
                'http://127.0.0.1:8080/rest/items/' + name + '?metadata=.*']))
            if actual.get('editable') is not False or actual.get('state') != 'NULL':
                raise RuntimeError('file provider did not own the prepared Item')
            for field in ('name', 'type', 'label', 'category', 'groupNames',
                          'metadata', 'stateDescription'):
                left, right = actual.get(field), expected.get(field)
                # REST-managed resources may encode no icon as an empty string;
                # the file provider returns null for the same absent category.
                if field == 'category':
                    left, right = left or None, right or None
                if left != right:
                    raise RuntimeError('prepared provider DTO mismatch: ' + name + ':' + field)
            if sorted(actual.get('tags', [])) != sorted(expected.get('tags', [])):
                raise RuntimeError('prepared Item tags differ: ' + name)
        if run(['docker', 'exec', cid, 'cat', '/openhab/conf/items/' + source_path.name]) != source:
            raise RuntimeError('isolated file differs from source')
        print('file_provider_definitions_exact=' + str(len(names)))
        print('state_restore_and_live_transfer=not_tested')
    finally:
        label = run(['docker', 'inspect', '--format',
                     '{{index .Config.Labels "hex.forecast.qualifier"}}', cid]).decode().strip()
        if label != marker:
            raise RuntimeError('disposable ownership label mismatch')
        run(['docker', 'rm', '-f', '-v', cid])
        print('owned_container_and_tmpfs_removed=true')


if __name__ == '__main__':
    main()
