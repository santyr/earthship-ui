#!/usr/bin/env python3
"""Networkless, disposable OpenHAB provider qualification; no production writes."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
from extrema_item_source import NAMES, render
import openhab_sanity_check as oh

IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'


def run(args, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=45)
    if result.returncode:
        raise RuntimeError('isolated operation failed: ' + args[0])
    return result.stdout


def main():
    source = (ROOT / 'openhab/file-config/drafts/temperature-extrema.items').read_bytes()
    originals = [oh.get('/items/' + name + '?metadata=.*') for name in NAMES]
    assert render(originals, oh.get('/links')).encode() == source
    # Equipment ancestry generates isPointOf; plain Groups are not equivalent.
    parents = sorted({g for _, g in NAMES.values()})
    for name in parents:
        parent = oh.get('/items/' + name)
        assert parent['type'] == 'Group' and parent['tags'] == ['Equipment']
        assert not parent.get('groupNames')
    groups = '\n'.join('Group ' + group + ' ["Equipment"]' for group in parents) + '\n'
    marker = str(uuid.uuid4())
    cid = run(['docker', 'run', '-d', '--label', 'hex.extrema.qualification=' + marker,
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
    print('isolated_container=' + cid, flush=True)
    try:
        info = json.loads(run(['docker', 'inspect', cid]))[0]
        host = info['HostConfig']
        assert host['NetworkMode'] == 'none' and not host['Privileged']
        assert not host.get('Binds') and not host.get('Devices') and not host.get('PortBindings')
        assert info['AppArmorProfile'] == 'docker-default'
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            for name, data in [('items/temperature-extrema.items', source), ('items/parents.items', groups.encode())]:
                entry = tarfile.TarInfo(name); entry.size = len(data); entry.mode = 0o644
                tar.addfile(entry, io.BytesIO(data))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/openhab/conf'], archive.getvalue())
        run(['docker', 'exec', cid, 'touch', '/tmp/ready'])
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                rows = json.loads(run(['docker', 'exec', cid, 'curl', '-fsS', '--max-time', '3',
                    'http://127.0.0.1:8080/rest/items?metadata=.*']))
                by_name = {item['name']: item for item in rows}
                if all(name in by_name for name in NAMES):
                    # Feature installation can briefly withdraw REST after first readiness.
                    time.sleep(20)
                    break
            except (RuntimeError, ValueError):
                pass
            time.sleep(3)
        else:
            raise RuntimeError('isolated Item provider startup timeout')
        for original in originals:
            actual = json.loads(run(['docker', 'exec', cid, 'curl', '-fsS', '--max-time', '3',
                '--retry', '5', '--retry-all-errors', '--retry-delay', '2',
                'http://127.0.0.1:8080/rest/items/' + original['name'] + '?metadata=.*']))
            assert actual['editable'] is False and actual['state'] == 'NULL'
            for field in ['name', 'type', 'label', 'category', 'groupNames', 'metadata', 'stateDescription']:
                if actual.get(field) != original.get(field):
                    raise RuntimeError('provider mismatch: ' + original['name'] + ':' + field
                        + ' expected=' + json.dumps(original.get(field), sort_keys=True)
                        + ' actual=' + json.dumps(actual.get(field), sort_keys=True))
            assert sorted(actual['tags']) == sorted(original['tags'])
        assert run(['docker', 'exec', cid, 'cat', '/openhab/conf/items/temperature-extrema.items']) == source
        print('four_file_definitions_metadata_and_formats_match=true', flush=True)
        print('state_restore_and_production_transfer=not_tested', flush=True)
    finally:
        label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.extrema.qualification"}}', cid]).decode().strip()
        assert label == marker
        run(['docker', 'rm', '-f', '-v', cid])
        print('owned_container_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    main()
