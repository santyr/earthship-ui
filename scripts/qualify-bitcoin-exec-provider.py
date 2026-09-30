#!/usr/bin/env python3
"""Networkless managed/file/restart/managed Bitcoin Exec Thing rehearsal.

Production access is GET-only. The real feed is NEVER copied or executed:
an isolated script at the same path emits a fixed synthetic price. There are
no host mounts, network, devices, secrets, database or OpenHAB control rules.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import re
import secrets
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load('bitcoin_exec_preflight', 'preflight-bitcoin-exec-thing.py')
q = load('display_rule_qualifier', 'qualify-season-rule-provider.py')
runtime = q.runtime
LABEL = 'hex.bitcoin.exec.qualification'
BINDING = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/'
               'org.openhab.binding.exec/5.2.1/org.openhab.binding.exec-5.2.1.jar')
PROBE = 'Bitcoin_Qualification_LastExecution'
ITEMS = b'''Group BTC_Price
Number BTC_USD_Price "Bitcoin Price" (BTC_Price) { channel="exec:command:BTC_Price:output" }
String BTC_Output_Receipt_JSON { channel="exec:command:BTC_Price:output" [profile="transform:JS", toItemScript="bitcoin_output_receipt.js"] }
DateTime Bitcoin_Qualification_LastExecution { channel="exec:command:BTC_Price:lastexecution" }
'''


def validate_container(info, marker):
    host = info['HostConfig']
    if (info['Config']['Labels'].get(LABEL) != marker
            or info['Config'].get('User') != '9001:9001'
            or host['NetworkMode'] != 'none' or host['Privileged']
            or not host['ReadonlyRootfs'] or host.get('Binds')
            or host.get('Devices') or host.get('PortBindings')
            or host.get('Memory') != 1536 * 1024**2
            or host.get('MemorySwap') != host.get('Memory')
            or host.get('NanoCpus') != 1_000_000_000
            or info.get('AppArmorProfile') != 'docker-default'):
        raise RuntimeError('isolated Bitcoin container policy mismatch')


def install_probe(container):
    body = (ROOT / 'tests/fixtures/bitcoin-exec-probe.sh').read_bytes()
    if body != (b'#!/bin/sh\n'
                b'# Disposable provider qualification only: no network, credentials or hardware.\n'
                b"printf '%s\\n' '12345.67'\n"):
        raise RuntimeError('isolated synthetic script changed')
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as output:
        entry = tarfile.TarInfo('bitcoin.py')
        entry.size, entry.mode = len(body), 0o755
        output.addfile(entry, io.BytesIO(body))
    runtime.run(['docker', 'exec', '-i', container, 'tar', '-xf', '-',
                 '-C', '/etc/openhab/scripts'], archive.getvalue())


def binding_identity(listing):
    rows = [line for line in listing.splitlines() if 'org.openhab.binding.exec' in line]
    if len(rows) != 1:
        return None
    match = re.match(r'\s*(\d+)\s*[|│]\s*(\w+)\s*[|│]', rows[0])
    return (int(match[1]), match[2]) if match else None


def managed_definition(original):
    # REST's read DTO includes enriched channels/properties. Let the actual
    # binding factory construct them, as the qualified OpenMeteo adapter does.
    return {key: deepcopy(original[key]) for key in (
        'UID', 'thingTypeUID', 'label', 'configuration')}


def main():
    p.check()  # live GET-only preflight; refuses an already installed target
    original = p.oh.get('/things/' + p.UID + '?summary=false')
    p.validate(original, p.oh.get('/links'))
    if not BINDING.is_file():
        raise RuntimeError('cached Exec binding unavailable')
    marker = secrets.token_hex(8)
    container = None
    try:
        supervisor = (
            'cp -a /openhab/dist/conf/. /openhab/conf/; '
            'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
            'while [ ! -f /tmp/ready ]; do sleep 1; done; '
            'while true; do while [ ! -f /tmp/boot-permit ]; do sleep 1; done; '
            'rm /tmp/boot-permit; /openhab/start.sh server & jvm_child=$!; '
            'wait "$jvm_child"; touch /tmp/jvm-stopped; done')
        container = runtime.run([
            'docker', 'run', '-d', '--init', '--label', LABEL + '=' + marker,
            '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
            '--memory', '1536m', '--memory-swap', '1536m', '--cpus', '1', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=16m,uid=9001,gid=9001',
            '--tmpfs', '/etc/openhab/scripts:rw,exec,nosuid,nodev,size=1m,uid=9001,gid=9001',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -XX:ActiveProcessorCount=1 '
                  '-Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
            '--entrypoint', '/bin/sh', runtime.IMAGE, '-c', supervisor,
        ]).decode().strip()
        validate_container(json.loads(runtime.run(['docker', 'inspect', container]))[0], marker)
        install_probe(container)
        # Create the explicit managed Thing before channel links can cause
        # any implicit Thing construction by a binding factory.
        runtime.install(container, 'conf/items/bitcoin-qualification.items',
                        b'Group BTC_Price\nNumber BTC_USD_Price\n')
        runtime.install(container, 'conf/misc/exec.whitelist', (p.CONFIG['command'] + '\n').encode())
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit', '/tmp/ready'])
        q.wait_for(lambda: q._startup_item(container, 'BTC_USD_Price'), seconds=240)
        time.sleep(20)  # Let the core's initial feature transaction settle first.
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        runtime.install_bundles(container, [BINDING])
        def binding_ready():
            try:
                listing = runtime.run(client + ['bundle:list -s'], b'\n').decode()
            except RuntimeError:
                return False  # Reobserve this JVM after a transient CLI refusal.
            identity = binding_identity(listing)
            if identity is None:
                return False
            number, state = identity
            if state == 'Resolved':
                runtime.run(client + ['bundle:start ' + str(number)], b'\n')
                return False
            return state == 'Active'
        try:
            q.wait_for(binding_ready, seconds=120)
        except RuntimeError:
            listing = runtime.run(client + ['bundle:list -s'], b'\n').decode()
            rows = [line for line in listing.splitlines() if 'org.openhab.binding.exec' in line]
            print('isolated_exec_bundle_status=' + json.dumps(rows), flush=True)
            for row in rows:
                match = re.match(r'\s*(\d+)\s*[|│]', row)
                if match:
                    diagnostic = runtime.run(client + ['bundle:diag ' + match[1]], b'\n').decode()
                    # Only public package-resolution metadata, never arbitrary log lines.
                    requirements = [line.strip() for line in diagnostic.splitlines()
                                    if 'osgi.wiring.package' in line or 'osgi.ee' in line]
                    print('isolated_exec_bundle_requirements=' + json.dumps(requirements), flush=True)
            raise
        runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                              + ' administrator'], b'\n')
        token_output = runtime.run(client + ["openhab:users addApiToken qualification qualification ''"], b'\n')
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', token_output.decode())
        if len(tokens) != 1:
            raise RuntimeError('isolated API token unavailable; output withheld')

        def rest(method, path, body=None):
            args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method,
                    '-H', 'Authorization: Bearer ' + tokens[0],
                    '-H', 'Content-Type: application/json']
            if body is not None:
                args += ['--data-binary', '@-']
            args += ['http://127.0.0.1:8080/rest' + path]
            payload, status = runtime.run(args, json.dumps(body).encode() if body is not None else None).rsplit(b'\n', 1)
            return int(status), json.loads(payload) if payload.startswith((b'{', b'[')) else None

        def linked_outputs():
            status, links = rest('GET', '/links')
            if status != 200 or not isinstance(links, list):
                raise RuntimeError('isolated link read unavailable')
            probe = [link for link in links if link.get('itemName') == PROBE]
            if (len(probe) != 1 or probe[0].get('channelUID') != p.UID + ':lastexecution'
                    or probe[0].get('editable') is not False or probe[0].get('configuration') != {}):
                raise RuntimeError('isolated poll-time probe link changed')
            return [link for link in links if link.get('itemName') != PROBE]

        def ready(editable, after):
            status, row = rest('GET', '/things/' + p.UID)
            if status != 200 or not isinstance(row, dict) or row.get('editable') is not editable:
                return False
            try:
                # Only provider editability differs from the exact managed contract.
                p.validate({**row, 'editable': True}, linked_outputs())
                # The only extra membership is the declared synthetic poll-time probe.
                comparison = deepcopy(row)
                for channel in comparison.get('channels', []):
                    if 'linkedItems' in channel:
                        channel['linkedItems'] = [name for name in channel['linkedItems']
                                                  if name != PROBE]
                if p.definition(comparison) != p.definition(original):
                    return False
            except RuntimeError:
                return False
            status, stamp = rest('GET', '/items/' + PROBE)
            try:
                at = datetime.fromisoformat(stamp['state']).astimezone(timezone.utc)
            except (KeyError, TypeError, ValueError):
                return False
            price_status, price = rest('GET', '/items/BTC_USD_Price')
            return (status == price_status == 200 and at > after
                    and price.get('state') == '12345.67')

        q.wait_for(lambda: rest('GET', '/thing-types/exec:command')[0] == 200, seconds=90)
        managed = managed_definition(original)
        phase = datetime.now(timezone.utc)
        status, _ = rest('POST', '/things', managed)
        if status not in (200, 201, 202):
            print('isolated_managed_creation_status=' + str(status), flush=True)
            raise RuntimeError('isolated managed Thing creation failed')
        runtime.install(container, 'conf/items/bitcoin-qualification.items', ITEMS)
        q.wait_for(lambda: ready(True, phase), seconds=120)
        if rest('DELETE', '/things/' + p.UID)[0] not in (200, 202, 204):
            raise RuntimeError('isolated managed Thing withdrawal failed')
        q.wait_for(lambda: rest('GET', '/things/' + p.UID)[0] == 404)
        phase = datetime.now(timezone.utc)
        runtime.install(container, 'conf/things/bitcoin-price.things', p.SOURCE.read_bytes())
        q.wait_for(lambda: ready(False, phase), seconds=120)
        print('isolated_file_thing_exact=true; linked_outputs_preserved=2; synthetic_poll=true', flush=True)
        before = q.java_pids(container)
        if len(before) != 1:
            raise RuntimeError('one isolated server JVM required')
        try:
            runtime.run(client + ['system:shutdown -f'], b'\n')
        except RuntimeError:
            pass
        q.wait_for(lambda: before[0] not in q.java_pids(container), seconds=60)
        q.wait_for(lambda: q._jvm_stopped(container), seconds=30)
        phase = datetime.now(timezone.utc)
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit'])
        q.wait_for(lambda: q._startup_item(container, 'BTC_USD_Price'), seconds=240)
        q.wait_for(lambda: ready(False, phase), seconds=120)
        after = q.java_pids(container)
        if len(after) != 1 or before == after:
            raise RuntimeError('isolated JVM did not actually restart')
        print('isolated_full_jvm_restart=true; synthetic_poll_after_restart=true', flush=True)
        runtime.run(['docker', 'exec', container, 'rm', '/openhab/conf/things/bitcoin-price.things'])
        q.wait_for(lambda: rest('GET', '/things/' + p.UID)[0] == 404)
        phase = datetime.now(timezone.utc)
        if rest('POST', '/things', managed)[0] not in (200, 201, 202):
            raise RuntimeError('isolated managed rollback failed')
        q.wait_for(lambda: ready(True, phase), seconds=120)
        print('isolated_managed_rollback_exact=true; synthetic_poll_after_rollback=true', flush=True)
    finally:
        if container is not None:
            label = runtime.run(['docker', 'inspect', '--format',
                                 '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
            if label != marker:
                raise RuntimeError('isolated cleanup ownership mismatch')
            runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
            print('owned_container_and_tmpfs_removed=true', flush=True)
    print('status=passed; production_writes=0; real_feed_and_JDBC=not_tested')


if __name__ == '__main__':
    main()
