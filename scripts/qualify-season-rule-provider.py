#!/usr/bin/env python3
"""Rehearse the season display rule managed/file/managed handoff offline.

The disposable OpenHAB 5.2.1 container has no network or production mounts.
It is removed on success or failure. No live rule or Item is modified.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'isolated_jss_runtime', ROOT / 'scripts/qualify-inverter-ac-evidence-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

SOURCE = ROOT / 'openhab/file-config/automation/js/update_days_until_season.js'
RULE = 'update_days_until_season'
BASELINE = 'd43b3f993991966ade5d428bc4ff6af603a253a06f336ff93221cc22cc332311'
LABEL = 'hex.season.rule.qualification'
ITEMS = b'''Number:Time Sun_TimeLeft "Sun time left"
String Sun_NextSeason "Next season"
String DaysUntilNextSeason "Days until next season"
'''


def wait_for(check, *, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(2)
    raise RuntimeError('isolated season rule state timeout')


def main():
    live = runtime.oh.get('/rules/' + RULE)
    if (live.get('uid') != RULE or live.get('editable') is not True
            or len(live.get('triggers', [])) != 1
            or len(live.get('actions', [])) != 1
            or live.get('conditions')):
        raise RuntimeError('live season rule definition changed')
    script = live['actions'][0]['configuration']['script']
    if hashlib.sha256(script.encode()).hexdigest() != BASELINE:
        raise RuntimeError('live season rule script baseline changed')
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file() or not SOURCE.is_file():
        raise RuntimeError('isolated JavaScript resources unavailable')
    marker = secrets.token_hex(8)
    container = None
    try:
        container = runtime.run(['docker', 'run', '-d', '--label', LABEL + '=' + marker,
            '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
            '--memory', '2048m', '--cpus', '2', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
            '--entrypoint', '/bin/sh', runtime.IMAGE, '-c',
            'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
            'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']).decode().strip()
        info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
        host = info['HostConfig']
        if (info['Config']['Labels'].get(LABEL) != marker
                or host['NetworkMode'] != 'none' or host['Privileged']
                or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
                or info['AppArmorProfile'] != 'docker-default'):
            raise RuntimeError('isolated container policy mismatch')
        runtime.install(container, 'conf/items/season-rehearsal.items', ITEMS)
        runtime.install_bundles(container, bundles)
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/ready'])
        wait_for(lambda: _startup_item(container), seconds=240)
        time.sleep(20)
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        wait_for(lambda: _active_bundle(client, 'org.graalvm.js.js-language'), seconds=90)
        runtime.install_bundles(container, [runtime.ADDON])
        wait_for(lambda: _active_bundle(client, 'org.openhab.automation.jsscripting'), seconds=90)
        runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                              + ' administrator'], b'\n')
        output = runtime.run(client + ["openhab:users addApiToken qualification qualification ''"],
                             b'\n').decode()
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
        if len(tokens) != 1:
            raise RuntimeError('isolated API token unavailable; output withheld')
        token = tokens[0]

        def rest(method, path, body=None):
            args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method,
                    '-H', 'Authorization: Bearer ' + token,
                    '-H', 'Content-Type: application/json']
            if body is not None:
                args += ['--data-binary', '@-']
            args += ['http://127.0.0.1:8080/rest' + path]
            raw = runtime.run(args, json.dumps(body).encode() if body is not None else None)
            payload, status = raw.rsplit(b'\n', 1)
            try:
                decoded = json.loads(payload) if payload else None
            except ValueError:
                decoded = payload.decode(errors='replace')[:80]
            return int(status), decoded

        managed = {key: live[key] for key in (
            'uid', 'name', 'description', 'tags', 'triggers', 'conditions', 'actions')}
        status, _ = rest('POST', '/rules', managed)
        if status != 201:
            raise RuntimeError('isolated managed rule creation failed')
        if rest('GET', '/rules/' + RULE)[1].get('editable') is not True:
            raise RuntimeError('isolated managed baseline missing')
        if rest('DELETE', '/rules/' + RULE)[0] not in (200, 204):
            raise RuntimeError('isolated managed withdrawal failed')
        wait_for(lambda: rest('GET', '/rules/' + RULE)[0] == 404)

        runtime.run(['docker', 'exec', container, 'mkdir', '-p', '/openhab/conf/automation/js'])
        runtime.install(container, 'conf/automation/js/' + SOURCE.name, SOURCE.read_bytes())
        file_rule = wait_for(lambda: _file_rule(rest), seconds=120)
        print('isolated_file_rule_uid=' + file_rule['uid'], flush=True)
        print('isolated_file_rule_editable=' + str(file_rule.get('editable')).lower(), flush=True)
        if (len(file_rule.get('triggers', [])) != 1
                or file_rule['triggers'][0].get('type') != 'core.ItemStateChangeTrigger'
                or file_rule['triggers'][0].get('configuration', {}).get('itemName') != 'Sun_TimeLeft'):
            raise RuntimeError('isolated file rule trigger mismatch')
        runtime.run(['docker', 'exec', container, 'rm',
                     '/openhab/conf/automation/js/' + SOURCE.name])
        wait_for(lambda: rest('GET', '/rules/' + RULE)[0] == 404)
        if rest('POST', '/rules', managed)[0] != 201:
            raise RuntimeError('isolated managed rollback failed')
        restored = wait_for(lambda: _managed_rule(rest))
        if restored.get('triggers') != managed['triggers']:
            raise RuntimeError('isolated managed rollback trigger mismatch')
        print('isolated_managed_rollback=true', flush=True)
    finally:
        if container is not None:
            result = runtime.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container])
            if result.decode().strip() == marker:
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_container_removed=true', flush=True)
    print('status=passed; production_writes=0; natural_updates=not_tested')


def _startup_item(container):
    try:
        runtime.run(['docker', 'exec', container, 'curl', '-fsS', '--max-time', '3',
                     'http://127.0.0.1:8080/rest/items/Sun_TimeLeft'])
        return True
    except RuntimeError:
        return False


def _active_bundle(client, name):
    listing = runtime.run(client + ['bundle:list -s'], b'\n').decode(errors='replace')
    return any(name in line and 'Active' in line for line in listing.splitlines())


def _file_rule(rest):
    status, rule = rest('GET', '/rules/' + RULE)
    return rule if status == 200 and isinstance(rule, dict) and rule.get('uid') == RULE else None


def _managed_rule(rest):
    status, rule = rest('GET', '/rules/' + RULE)
    return rule if status == 200 and isinstance(rule, dict) and rule.get('editable') is True else None


if __name__ == '__main__':
    main()
