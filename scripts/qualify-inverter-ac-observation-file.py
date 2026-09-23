#!/usr/bin/env python3
"""Networkless provider check for the prepared read-only inverter AC link."""
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tarfile
import time
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

ITEM = 'Inverter_AC_Output_Observation_JSON'
ORIGINAL = 'ConextGateway_ACPowerValue'
CHANNEL = 'modbus:inverter-split-phase:1ed74db72c:e853aec444:acGeneral#ac-power'
SOURCE = ROOT / 'openhab/file-config/items/inverter-ac-output-observation.items'
TRANSFORM = ROOT / 'openhab/transform/inverter_ac_output_observation.js'
IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'


def run(args, data=None, *, timeout=45):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError('isolated command failed: ' + args[0])
    return result.stdout


def install(container, name, body):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as output:
        entry = tarfile.TarInfo(name)
        entry.size, entry.mode = len(body), 0o644
        output.addfile(entry, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/openhab/conf'],
        archive.getvalue())


def main():
    source = SOURCE.read_bytes()
    transform = TRANSFORM.read_bytes()
    try:
        live_item = oh.get('/items/' + ITEM)
    except HTTPError as error:
        if error.code != 404:
            raise
        live_item = None
    links = oh.get('/links')
    original = [entry for entry in links if entry.get('itemName') == ORIGINAL]
    if len(original) != 1 or original[0].get('channelUID') != CHANNEL:
        raise RuntimeError('original inverter link changed')
    candidate = [entry for entry in links if entry.get('itemName') == ITEM]
    if live_item is None:
        if candidate:
            raise RuntimeError('proposed Item absent but link exists on production host')
    else:
        if (live_item.get('editable') is not False or live_item.get('type') != 'String'
                or len(candidate) != 1 or candidate[0].get('editable') is not False
                or candidate[0].get('channelUID') != CHANNEL
                or candidate[0].get('configuration') != {
                    'profile': 'transform:JS',
                    'toItemScript': 'inverter_ac_output_observation.js'}):
            raise RuntimeError('live observation provider differs from source intent')
        if (Path('/etc/openhab/items/inverter-ac-output-observation.items').read_bytes() != source
                or Path('/etc/openhab/transform/inverter_ac_output_observation.js').read_bytes() != transform):
            raise RuntimeError('live observation file bytes differ from source')
    marker = secrets.token_hex(8)
    container = run(['docker', 'run', '-d', '--label', 'hex.ac.profile=' + marker,
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
        info = json.loads(run(['docker', 'inspect', container]))[0]
        host = info['HostConfig']
        if (host['NetworkMode'] != 'none' or host['Privileged'] or host.get('Binds')
                or host.get('Devices') or host.get('PortBindings')
                or info['AppArmorProfile'] != 'docker-default'):
            raise RuntimeError('isolated container policy mismatch')
        install(container, 'items/inverter-ac-output-observation.items', source)
        install(container, 'transform/inverter_ac_output_observation.js', transform)
        run(['docker', 'exec', container, 'touch', '/tmp/ready'])
        for _ in range(80):
            try:
                run(['docker', 'exec', container, 'curl', '-fsS', '--max-time', '3',
                     'http://127.0.0.1:8080/rest/items/' + ITEM])
                break
            except RuntimeError:
                time.sleep(3)
        else:
            raise RuntimeError('isolated Item provider startup timeout')
        time.sleep(20)
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                      + ' administrator'], b'\n')
        output = run(client + ["openhab:users addApiToken qualification qualification ''"],
                     b'\n').decode()
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
        if len(tokens) != 1:
            raise RuntimeError('isolated API token unavailable; output withheld')
        header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                item = json.loads(run(['docker', 'exec', '-i', container, 'curl', '-fsS',
                    '--max-time', '3', '-H', '@-',
                    'http://127.0.0.1:8080/rest/items/' + ITEM], header))
                links = json.loads(run(['docker', 'exec', '-i', container, 'curl', '-fsS',
                    '--max-time', '3', '-H', '@-',
                    'http://127.0.0.1:8080/rest/links'], header))
                matches = [entry for entry in links if entry.get('itemName') == ITEM]
                if item.get('editable') is False and len(matches) == 1:
                    break
            except (RuntimeError, ValueError):
                pass
            time.sleep(3)
        else:
            raise RuntimeError('isolated profile Item/link provider timeout')
        if (item.get('name') != ITEM or item.get('type') != 'String'
                or item.get('state') != 'NULL' or matches[0].get('editable') is not False
                or matches[0].get('channelUID') != CHANNEL
                or matches[0].get('configuration') != {
                    'profile': 'transform:JS',
                    'toItemScript': 'inverter_ac_output_observation.js'}):
            raise RuntimeError('isolated Item/link profile mismatch')
        if run(['docker', 'exec', container, 'cat',
                '/openhab/conf/transform/inverter_ac_output_observation.js']) != transform:
            raise RuntimeError('isolated transform source differs')
        print('isolated_file_item_and_profile_link_exact=true', flush=True)
        print('live_acquisition_and_persistence=not_tested', flush=True)
    finally:
        owner = run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "hex.ac.profile"}}', container]).decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')
        run(['docker', 'rm', '-f', '-v', container])
        print('owned_container_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    main()
