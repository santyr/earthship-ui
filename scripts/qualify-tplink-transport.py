#!/usr/bin/env python3
"""Actual HS103 binding TCP fault/native recovery in disconnected owned fixtures.

No production credentials, mounts, routes, state writes or device commands.
The original transform, event triggers, collector and JDBC policy are used.
This is transport qualification, not evidence of a household physical outage.
"""
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets
import tarfile
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'hex.tplink.transport.qualification'
ITEM = 'TPLink_Switch_Evidence_JSON'
UID = 'hex_tplink_switch_evidence'
THINGS = ('tplinksmarthome:hs103:a34b4957dc', 'tplinksmarthome:hs103:08482dd378')
FIELDS = ('load.dishwasher_state', 'load.shurflo_pump_state')
OBSERVATIONS = ('Dishwasher_Switch_Observation_JSON', 'Cistern_Pump_Switch_Observation_JSON')
SOURCE_SHA = '40b34d9b2afa3ce9451aecdf5b26aef3f46a85adda402cb6a0f7f6106f4466d9'
BINDING = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/'
    'org.openhab.binding.tplinksmarthome/5.2.1/org.openhab.binding.tplinksmarthome-5.2.1.jar')


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def check_clone(info, marker, network):
    host = info.get('HostConfig', {})
    if (info.get('Config', {}).get('Labels', {}).get(LABEL) != marker
            or host.get('NetworkMode') != network or not network.startswith('container:')
            or host.get('Privileged') or host.get('Binds') or host.get('Devices')
            or host.get('PortBindings') or host.get('ReadonlyRootfs') is not True
            or host.get('Memory') != 2147483648 or host.get('MemorySwap') != 2147483648
            or host.get('NanoCpus') != 2000000000 or host.get('CapDrop') != ['ALL']
            or host.get('PidsLimit') != 256 or info.get('AppArmorProfile') != 'docker-default'):
        raise RuntimeError('disconnected binding containment mismatch')


def check_request(method, path):
    allowed = (method == 'GET' and (
        path in {'/items/' + name for name in (ITEM, *OBSERVATIONS)}
        or path in {'/things/' + name for name in THINGS}
        or path == '/rules/' + UID
        or path == '/persistence/items/' + ITEM + '?serviceId=jdbc')
        or method == 'POST' and path == '/rules')
    if not allowed:
        raise RuntimeError('request outside disconnected observation scope')


def rule_definition():
    source = (ROOT / 'openhab/rules/tplink-switch-evidence.js').read_text()
    if sha256(source.encode()).hexdigest() != SOURCE_SHA or 'sendCommand' in source:
        raise RuntimeError('observational collector source drift')
    original = json.loads((ROOT / 'openhab/tplink-switch-evidence-resources.json').read_bytes())['rule']
    if original['uid'] != UID or original['enabled'] is not False:
        raise RuntimeError('original disabled source descriptor drift')
    return {'uid': UID, 'name': 'Disconnected actual binding observation',
            'triggers': original['triggers'], 'conditions': [],
            'actions': [{'id': 'collect', 'type': 'script.ScriptAction',
                        'configuration': {'type': 'application/javascript', 'script': source}}]}


def install_mode(runtime, container, device, mode):
    if device not in (1, 2) or mode not in ('healthy', 'fault'):
        raise RuntimeError('fixture mode outside approved read-only scope')
    body = (mode + '\n').encode()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as output:
        entry = tarfile.TarInfo('tmp/hex-tplink-mode-' + str(device))
        entry.size, entry.mode = len(body), 0o600
        output.addfile(entry, io.BytesIO(body))
    runtime.run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/'], archive.getvalue())


def fault_observation(held, fault):
    # Some bindings actively update their channel to UNDEF on failure. That
    # transform invocation has a new host timestamp but is not a valid switch
    # receipt. Other handlers retain the last OFF value and its original clock.
    if held.get('version') != 1 or not isinstance(held.get('observedAt'), int):
        raise RuntimeError('unexpected acquisition observation shape')
    if held.get('value') == 'OFF' and held['observedAt'] <= fault['recordedAt']:
        return 'held_original_off'
    if held.get('value') in ('UNDEF', 'NULL'):
        return 'explicit_unavailable_channel_update'
    raise RuntimeError('fault acquisition observation unexpected: ' + str(held.get('value')))


def validate_history(rows, first, repeated, fault, recovery, *, fault_field=FIELDS[0]):
    if fault_field not in FIELDS: raise RuntimeError('unknown fault field')
    decoded = []
    previous = -1
    for row in rows:
        if row['time'] <= previous:
            raise RuntimeError('JDBC ordered prefix changed')
        previous = row['time']
        decoded.append(json.loads(row['state']))
    anchors = (first, repeated, fault, recovery)
    try:
        positions = [decoded.index(value) for value in anchors]
    except ValueError:
        raise RuntimeError('original checkpoint missing from JDBC') from None
    if positions != sorted(set(positions)):
        raise RuntimeError('fault/recovery durable ordering differs')
    if repeated['recordedAt'] - first['recordedAt'] < 60000:
        raise RuntimeError('periodic unchanged report publication not exercised')
    epoch = first['streamEpoch']
    previous_sequence = 0
    for value in decoded:
        if (value.get('version') != 2 or value.get('basis') != 'tplink_hs103_switch_report_v1'
                or value.get('streamEpoch') != epoch or value.get('sequence') != previous_sequence + 1):
            raise RuntimeError('collector stream identity or sequence changed')
        for field in value['fields'].values():
            if field['status'] == 'valid' and (
                field['reason'] != 'ok' or field['value'] != 'OFF'
                or not field['observedAt'] <= value['recordedAt'] < field['validUntil']
                or field['validUntil'] != field['observedAt'] + 95000):
                raise RuntimeError('native field acquisition/expiry contract differs')
        previous_sequence = value['sequence']
    for name in FIELDS:
        a, b = first['fields'][name], repeated['fields'][name]
        if (a['status'] != 'valid' or b['status'] != 'valid' or a['value'] != 'OFF'
                or b['value'] != a['value'] or b['observedAt'] <= a['observedAt']
                or b['validUntil'] != b['observedAt'] + 95000):
            raise RuntimeError('unchanged native value did not renew original receipt')
    unavailable = fault['fields'][fault_field]
    recovered = recovery['fields'][fault_field]
    unaffected = next(name for name in FIELDS if name != fault_field)
    if (unavailable['status'] != 'unavailable' or unavailable['reason'] != 'source_unavailable'
            or any(unavailable[key] is not None for key in ('value', 'observedAt', 'validUntil'))
            or recovered['status'] != 'valid' or recovered['value'] != 'OFF'
            or recovered['observedAt'] <= fault['recordedAt']
            or recovered['validUntil'] != recovered['observedAt'] + 95000
            or fault['fields'][unaffected]['status'] != 'valid'
            or any(recovery['fields'][name]['status'] != 'valid' for name in FIELDS)):
        raise RuntimeError('fault barrier or new native recovery missing')
    return {'status': 'qualified_disconnected_actual_binding_transport',
            'unchanged_native_reports': True, 'source_fault_and_native_recovery': True,
            'durable_receipts': len(rows), 'source_sha256': SOURCE_SHA,
            'fault_field': fault_field,
            'original_rows_sha256': sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'checkpoint_times_ms': [value['recordedAt'] for value in anchors],
            'household_physical_sources_tested': False, 'production_writes': 0}


def main():
    jdbc = module('tplink_jdbc_fixture', 'qualify-persistence-jdbc.py')
    fixture = module('tplink_runtime_fixture', 'qualify-bms-runtime-estimator.py').fixture
    runtime = fixture.runtime
    rule = rule_definition()
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file() or not BINDING.is_file():
        raise RuntimeError('version-pinned isolated dependencies unavailable')
    peer = jdbc.compile_probe('HexTplinkLoopbackProbe', ['org.osgi.framework'])
    # Test frame implementation against the actual binding before allocating.
    with tempfile.TemporaryDirectory(prefix='earthship-tplink-wire-') as directory:
        with zipfile.ZipFile(io.BytesIO(peer)) as bundle:
            bundle.extract('HexTplinkLoopbackProbe.class', directory)
        framework = Path('/usr/share/openhab/runtime/system/org/apache/felix/'
                         'org.apache.felix.framework/7.0.5/org.apache.felix.framework-7.0.5.jar')
        if not framework.is_file(): raise RuntimeError('pinned OSGi framework missing')
        classpath = os.pathsep.join(map(str, [Path(directory), BINDING, framework]))
        print(runtime.run(['java', '-cp', classpath, 'HexTplinkLoopbackProbe', '--self-test']).decode().strip(), flush=True)
    marker = secrets.token_hex(8)
    with jdbc.Database() as database:
        runtime.run(['docker', 'update', '--memory-swap', '384m', database.cid])
        container = None
        try:
            container = runtime.run(['docker', 'run', '-d', '--init', '--label', LABEL + '=' + marker,
                '--network', database.network, '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
                '--memory', '2048m', '--memory-swap', '2048m', '--cpus', '2', '--pids-limit', '256',
                '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
                '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
                '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
                '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
                '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
                '-e', 'HEX_TPLINK_ISOLATED=1', '--entrypoint', '/bin/sh', runtime.IMAGE, '-c',
                'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']).decode().strip()
            check_clone(json.loads(runtime.run(['docker', 'inspect', container]))[0], marker, database.network)
            db = json.loads(runtime.run(['docker', 'inspect', database.cid]))[0]
            host = db['HostConfig']
            if (db['Config']['Labels'].get('hex.jdbc.qualification') != database.marker
                    or host['NetworkMode'] != 'none' or host['Privileged'] or host.get('Binds')
                    or host.get('Devices') or host.get('PortBindings')
                    or host['Memory'] != 402653184 or host['MemorySwap'] != 402653184):
                raise RuntimeError('disconnected database containment mismatch')
            print('owned_disconnected_tplink_fixture=' + container, flush=True)
            database.stage(container)
            for destination, source in (
                ('conf/persistence/jdbc.persist', 'openhab/file-config/persistence/jdbc.persist'),
                ('conf/items/switch-evidence.items', 'openhab/file-config/items/tplink-switch-evidence.items'),
                ('conf/items/switch-observation.items', 'openhab/file-config/items/tplink-switch-observation.items'),
                ('conf/transform/tplink_switch_observation.js', 'openhab/transform/tplink_switch_observation.js')):
                runtime.install(container, destination, (ROOT / source).read_bytes())
            things = ''.join(f'Thing {uid} [ipAddress="127.0.0.{i}", refresh=1]\n'
                             for i, uid in enumerate(THINGS, 1))
            runtime.install(container, 'conf/things/disconnected-plugs.things', things.encode())
            runtime.install(container, 'addons/hex-tplink-peer.jar', peer)
            for device in (1, 2):
                install_mode(runtime, container, device, 'healthy')
            runtime.install_bundles(container, [*bundles, BINDING])
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/ready'])
            fixture.wait_for(lambda: fixture._startup_item(container, ITEM), seconds=240)
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.graalvm.js.js-language'))
            runtime.install_bundles(container, [runtime.ADDON])
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.automation.jsscripting'))
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.binding.tplinksmarthome'))
            runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20) + ' administrator'], b'\n')
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', runtime.run(client +
                ["openhab:users addApiToken qualification qualification ''"], b'\n').decode())
            if len(tokens) != 1:
                raise RuntimeError('fixture credential creation failed; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()

            def rest(method, path, body=None):
                check_request(method, path)
                if method == 'POST' and body != rule:
                    raise RuntimeError('only exact original observational rule allowed')
                command = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method, '-H', '@-', '-H', 'Content-Type: application/json']
                if body is not None:
                    command += ['--data-binary', json.dumps(body)]
                payload, status = runtime.run(command + ['http://127.0.0.1:8080/rest' + path], header).rsplit(b'\n', 1)
                return int(status), json.loads(payload) if payload else None

            def state():
                status, item = rest('GET', '/items/' + ITEM)
                if status != 200: raise RuntimeError('fixture Item read failed')
                try: return json.loads(item['state'])
                except ValueError: return None

            def valid():
                value = state()
                return value if value and all(value['fields'][name]['status'] == 'valid' for name in FIELDS) else False

            if rest('POST', '/rules', rule)[0] != 201:
                raise RuntimeError('exact observational rule creation failed')
            fixture.wait_for(lambda: rest('GET', '/rules/' + UID)[1]['status']['status'] == 'IDLE')
            first = fixture.wait_for(valid, seconds=90)
            print('actual_native_binding_reports=valid', flush=True)
            def renewed():
                value = valid()
                return value if value and value['sequence'] > first['sequence'] else False
            repeated = fixture.wait_for(renewed, seconds=90)
            print('unchanged_off_native_report_renewal=verified', flush=True)
            results = []
            for device in (1, 2):
                fault_field = FIELDS[device - 1]
                install_mode(runtime, container, device, 'fault')
                def failed():
                    value = state()
                    return value if value and value['fields'][fault_field]['reason'] == 'source_unavailable' else False
                fault = fixture.wait_for(failed, seconds=40)
                wire = json.loads(runtime.run(['docker', 'exec', container, 'cat', '/tmp/hex-tplink-wire-' + str(device)]))
                if wire['faults'] < 1 or wire['rejected'] != 0:
                    raise RuntimeError('real transport fault marker missing or action attempted')
                if rest('GET', '/things/' + THINGS[device - 1])[1]['statusInfo']['status'] != 'OFFLINE':
                    raise RuntimeError('actual binding fault not reflected in Thing')
                held = json.loads(rest('GET', '/items/' + OBSERVATIONS[device - 1])[1]['state'])
                observation = fault_observation(held, fault)
                print('device_' + str(device) + '_tcp_failure_offline_and_receipt_barrier=verified:' + observation, flush=True)
                install_mode(runtime, container, device, 'healthy')
                recovery = fixture.wait_for(valid, seconds=40)
                def persisted():
                    status, payload = rest('GET', '/persistence/items/' + ITEM + '?serviceId=jdbc')
                    rows = payload.get('data', []) if status == 200 and isinstance(payload, dict) else []
                    return rows if any(json.loads(row['state']) == recovery for row in rows) else False
                rows = fixture.wait_for(persisted, seconds=40)
                result = validate_history(rows, first, repeated, fault, recovery, fault_field=fault_field)
                result['fault_acquisition_state'] = observation
                results.append(result)
            for device in (1, 2):
                wire = json.loads(runtime.run(['docker', 'exec', container, 'cat', '/tmp/hex-tplink-wire-' + str(device)]))
                if wire['rejected'] != 0: raise RuntimeError('non-read-only device command attempted')
            print(json.dumps({'results': results, 'binding_sha256': sha256(BINDING.read_bytes()).hexdigest(),
                'fixture_refresh_seconds': 1, 'production_refresh_seconds': 30}, sort_keys=True), flush=True)
        finally:
            if container is not None:
                owner = runtime.run(['docker', 'inspect', '--format',
                    '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
                if owner != marker: raise RuntimeError('fixture cleanup ownership mismatch')
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_tplink_fixture_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'reason': str(error)}))
        raise SystemExit(1) from None
