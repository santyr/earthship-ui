#!/usr/bin/env python3
"""Actual BMS Modbus TCP failure/recovery in owned disconnected fixtures.

Original 30-second polls, native channels, eight triggers, collector and JDBC.
Not a physical household outage or permission to release live consumers.
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
LABEL = 'hex.bms.transport.qualification'
ITEM = 'BMS_Aux_Evidence_JSON'
UID = 'hex_bms_aux_evidence'
BRIDGE = 'modbus:tcp:discoverBms190'
POLLER = 'modbus:poller:discoverBms190:bmsMain'
THINGS = ('modbus:data:discoverBms190:bmsMain:capRemainAh',
          'modbus:data:discoverBms190:bmsMain:tempRaw')
INPUTS = ('BMS_Capacity_Remaining_Ah', 'BMS_Temperature_Raw')
VALUES = {'battery.remaining_ah': 320, 'battery.temperature_raw': 29315}
FIELDS = tuple(VALUES)
SOURCE_SHA = 'c57778dceca6f78c3db41a05605918e1bd9db3ad10aea13579ea453587391618'
BINDING = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/'
    'org.openhab.binding.modbus/5.2.1/org.openhab.binding.modbus-5.2.1.jar')
SYSTEM = Path('/usr/share/openhab/runtime/system')
TRANSPORT = SYSTEM / 'org/openhab/core/bundles/org.openhab.core.io.transport.modbus/5.2.1/org.openhab.core.io.transport.modbus-5.2.1.jar'
SERIAL = SYSTEM / 'com/neuronrobotics/nrjavaserial/5.2.1.OH1/nrjavaserial-5.2.1.OH1.jar'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def expected_sources():
    configs = {
        BRIDGE: {'rtuEncoded': False, 'connectMaxTries': 3, 'reconnectAfterMillis': 0,
            'timeBetweenTransactionsMillis': 200, 'port': 503, 'timeBetweenReconnectMillis': 100,
            'connectTimeoutMillis': 10000, 'afterConnectionDelayMillis': 0,
            'id': 190, 'enableDiscovery': False},
        POLLER: {'length': 34, 'start': 64, 'refresh': 30000,
            'maxTries': 3, 'cacheMillis': 50, 'type': 'holding'},
    }
    for uid, start in zip(THINGS, ('88', '74')):
        configs[uid] = {'readValueType': 'uint32', 'readTransform': ['default'],
            'writeTransform': ['default'], 'readStart': start, 'updateUnchangedValuesEveryMillis': 0,
            'writeMultipleEvenWithSingleRegisterOrCoil': False, 'writeMaxTries': 3}
    return {uid: {'thingTypeUID': ':'.join(uid.split(':')[:2]),
                 'bridgeUID': None if uid == BRIDGE else BRIDGE if uid == POLLER else POLLER,
                 'configuration': config} for uid, config in configs.items()}


def verify_sources(actual):
    if actual != expected_sources():
        raise RuntimeError('original BMS read-only source configuration drift')


def thing_definition():
    sources = expected_sources()
    def options(uid):
        config = dict(sources[uid]['configuration'])
        if uid == BRIDGE: config.update(host='127.0.0.1', port=1503)
        return ', '.join(k + '=' + json.dumps(v[0] if isinstance(v, list) else v)
                         for k, v in config.items())
    return ('Bridge ' + BRIDGE + ' [' + options(BRIDGE) + '] {\n'
        + ' Bridge poller bmsMain [' + options(POLLER) + '] {\n'
        + ''.join('  Thing data ' + uid.rsplit(':', 1)[1] + ' [' + options(uid) + ']\n' for uid in THINGS)
        + ' }\n}\n')


def check_request(method, path):
    allowed = (method == 'GET' and (
        path in {'/items/' + name for name in (ITEM, *INPUTS)}
        or path in {'/things/' + name for name in (BRIDGE, POLLER, *THINGS)}
        or path == '/rules/' + UID
        or path == '/persistence/items/' + ITEM + '?serviceId=jdbc')
        or method == 'POST' and path == '/rules')
    if not allowed: raise RuntimeError('request outside disconnected BMS observation scope')


def rule_definition():
    source = (ROOT / 'openhab/rules/bms-aux-evidence.js').read_text()
    if sha256(source.encode()).hexdigest() != SOURCE_SHA or 'sendCommand' in source:
        raise RuntimeError('observational collector source drift')
    descriptor = json.loads((ROOT / 'openhab/bms-aux-evidence-resources.json').read_bytes())['rule']
    if descriptor['uid'] != UID or descriptor['enabled'] is not False:
        raise RuntimeError('original disabled descriptor drift')
    return {'uid': UID, 'name': 'Disconnected actual BMS Modbus observation',
        'triggers': descriptor['triggers'], 'conditions': [], 'actions': [{
            'id': 'collect', 'type': 'script.ScriptAction',
            'configuration': {'type': 'application/javascript', 'script': source}}]}


def install_mode(runtime, container, mode):
    if mode not in ('healthy', 'fault'): raise RuntimeError('unsupported fixture peer mode')
    body = (mode + '\n').encode()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as output:
        entry = tarfile.TarInfo('tmp/hex-bms-mode')
        entry.size, entry.mode = len(body), 0o600
        output.addfile(entry, io.BytesIO(body))
    runtime.run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/'], archive.getvalue())


def validate_history(rows, first, repeated, fault, recovery):
    decoded = []
    previous = -1
    for row in rows:
        if row['time'] <= previous: raise RuntimeError('JDBC ordered prefix changed')
        previous = row['time']
        decoded.append(json.loads(row['state']))
    anchors = (first, repeated, fault, recovery)
    try: positions = [decoded.index(value) for value in anchors]
    except ValueError: raise RuntimeError('original checkpoint missing from JDBC') from None
    if positions != sorted(set(positions)): raise RuntimeError('durable checkpoint ordering differs')
    if repeated['recordedAt'] - first['recordedAt'] < 60000:
        raise RuntimeError('original periodic unchanged publication not exercised')
    for sequence, value in enumerate(decoded, 1):
        if (value.get('version') != 1 or value.get('basis') != 'discover_bms_190_native_aux_v1'
                or value.get('streamEpoch') != first['streamEpoch'] or value.get('sequence') != sequence
                or set(value['fields']) != set(FIELDS)):
            raise RuntimeError('original BMS stream identity differs')
        for name, field in value['fields'].items():
            if field['status'] == 'valid' and (
                    field['reason'] != 'ok' or field['value'] != VALUES[name]
                    or not field['observedAt'] <= value['recordedAt'] < field['validUntil']
                    or field['validUntil'] != field['observedAt'] + 120000):
                raise RuntimeError('native BMS acquisition/expiry contract differs')
            if field['status'] == 'unavailable' and any(
                    field[key] is not None for key in ('value', 'observedAt', 'validUntil')):
                raise RuntimeError('unavailable BMS field retained valid data')
    for name in FIELDS:
        a, b, barrier, new = [value['fields'][name] for value in anchors]
        if (a['status'] != 'valid' or b['status'] != 'valid' or new['status'] != 'valid'
                or b['observedAt'] <= a['observedAt'] or barrier['status'] != 'unavailable'
                or barrier['reason'] != 'source_unavailable'
                or new['observedAt'] <= fault['recordedAt']):
            raise RuntimeError('unchanged receipt, fault barrier or new native recovery missing')
    return {'status': 'qualified_disconnected_actual_modbus_transport',
        'unchanged_native_reports': True, 'source_fault_and_native_recovery': True,
        'durable_receipts': len(rows), 'source_sha256': SOURCE_SHA,
        'original_rows_sha256': sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'checkpoint_times_ms': [value['recordedAt'] for value in anchors],
        'poll_refresh_ms': 30000, 'household_physical_sources_tested': False, 'production_writes': 0}


def main():
    jdbc = module('bms_transport_jdbc', 'qualify-persistence-jdbc.py')
    fixture = module('bms_transport_runtime', 'qualify-bms-runtime-estimator.py').fixture
    containment = module('bms_transport_containment', 'qualify-tplink-transport.py')
    runtime = fixture.runtime
    rule = rule_definition()
    actual = {}
    for uid in expected_sources():
        obj = runtime.oh.get('/things/' + uid)
        config = dict(obj['configuration'])
        if uid == BRIDGE: config.pop('host', None)
        actual[uid] = {'thingTypeUID': obj['thingTypeUID'], 'bridgeUID': obj.get('bridgeUID'),
                      'configuration': config}
    verify_sources(actual)
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not all(p.is_file() for p in (BINDING, TRANSPORT, SERIAL, runtime.ADDON)):
        raise RuntimeError('version-pinned disconnected dependencies unavailable')
    peer = jdbc.compile_probe('HexBmsLoopbackProbe', ['org.osgi.framework'])
    with tempfile.TemporaryDirectory(prefix='earthship-bms-wire-') as directory:
        with zipfile.ZipFile(io.BytesIO(peer)) as bundle: bundle.extract('HexBmsLoopbackProbe.class', directory)
        framework = SYSTEM / 'org/apache/felix/org.apache.felix.framework/7.0.5/org.apache.felix.framework-7.0.5.jar'
        classpath = os.pathsep.join(map(str, [Path(directory), TRANSPORT, framework]))
        print(runtime.run(['java', '-cp', classpath, 'HexBmsLoopbackProbe', '--self-test']).decode().strip(), flush=True)
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
                '-e', 'HEX_BMS_ISOLATED=1', '--entrypoint', '/bin/sh', runtime.IMAGE, '-c',
                'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']).decode().strip()
            info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
            # Reuse the already qualified strict checker with its explicit label,
            # never relax its network/resource/ownership checks.
            checked = {**info, 'Config': {**info['Config'], 'Labels': {
                **info['Config']['Labels'], containment.LABEL: info['Config']['Labels'].get(LABEL)}}}
            containment.check_clone(checked, marker, database.network)
            db = json.loads(runtime.run(['docker', 'inspect', database.cid]))[0]
            host = db['HostConfig']
            if (db['Config']['Labels'].get('hex.jdbc.qualification') != database.marker
                    or host['NetworkMode'] != 'none' or host['Privileged'] or host.get('Binds')
                    or host.get('Devices') or host.get('PortBindings')
                    or host['Memory'] != 402653184 or host['MemorySwap'] != 402653184):
                raise RuntimeError('disconnected database containment mismatch')
            print('owned_disconnected_bms_fixture=' + container, flush=True)
            database.stage(container)
            runtime.install(container, 'conf/persistence/jdbc.persist', (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            runtime.install(container, 'conf/items/bms-aux-evidence.items', (ROOT / 'openhab/file-config/items/bms-aux-evidence.items').read_bytes())
            items = ''.join('Number ' + name + ' { channel="' + uid + ':number" }\n' for name, uid in zip(INPUTS, THINGS))
            runtime.install(container, 'conf/items/bms-native-inputs.items', items.encode())
            runtime.install(container, 'conf/things/disconnected-bms.things', thing_definition().encode())
            runtime.install(container, 'addons/hex-bms-peer.jar', peer)
            install_mode(runtime, container, 'healthy')
            runtime.install_bundles(container, [*bundles, SERIAL, TRANSPORT, BINDING])
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/ready'])
            fixture.wait_for(lambda: fixture._startup_item(container, ITEM), seconds=240)
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.graalvm.js.js-language'))
            runtime.install_bundles(container, [runtime.ADDON])
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.automation.jsscripting'))
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.binding.modbus'))
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.core.io.transport.modbus'))
            runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20) + ' administrator'], b'\n')
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', runtime.run(client + [
                "openhab:users addApiToken qualification qualification ''"], b'\n').decode())
            if len(tokens) != 1: raise RuntimeError('fixture credential creation failed; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
            def rest(method, path, body=None):
                check_request(method, path)
                if method == 'POST' and body != rule: raise RuntimeError('only original observation rule allowed')
                command = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method, '-H', '@-', '-H', 'Content-Type: application/json']
                if body is not None: command += ['--data-binary', json.dumps(body)]
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
            if rest('POST', '/rules', rule)[0] != 201: raise RuntimeError('original observation rule creation failed')
            fixture.wait_for(lambda: rest('GET', '/rules/' + UID)[1]['status']['status'] == 'IDLE')
            first = fixture.wait_for(valid, seconds=100)
            print('actual_native_uint32_modbus_reports=valid', flush=True)
            def renewed():
                value = valid()
                return value if value and value['sequence'] > first['sequence'] else False
            repeated = fixture.wait_for(renewed, seconds=100)
            print('unchanged_native_30_second_reports_and_periodic_renewal=verified', flush=True)
            install_mode(runtime, container, 'fault')
            def failed():
                value = state()
                return value if value and all(value['fields'][name]['reason'] == 'source_unavailable' for name in FIELDS) else False
            fault = fixture.wait_for(failed, seconds=90)
            wire = json.loads(runtime.run(['docker', 'exec', container, 'cat', '/tmp/hex-bms-wire']))
            if wire['faults'] < 1 or wire['rejected'] != 0: raise RuntimeError('actual read fault missing or forbidden request attempted')
            if rest('GET', '/things/' + POLLER)[1]['statusInfo']['status'] != 'OFFLINE':
                raise RuntimeError('actual binding poller fault not reflected')
            held = {name: rest('GET', '/items/' + name)[1]['state'] for name in INPUTS}
            print('actual_tcp_failure_poller_offline_and_both_receipt_barriers=verified', flush=True)
            install_mode(runtime, container, 'healthy')
            recovery = fixture.wait_for(valid, seconds=100)
            def persisted():
                status, payload = rest('GET', '/persistence/items/' + ITEM + '?serviceId=jdbc')
                rows = payload.get('data', []) if status == 200 and isinstance(payload, dict) else []
                return rows if any(json.loads(row['state']) == recovery for row in rows) else False
            rows = fixture.wait_for(persisted, seconds=40)
            proof = validate_history(rows, first, repeated, fault, recovery)
            wire = json.loads(runtime.run(['docker', 'exec', container, 'cat', '/tmp/hex-bms-wire']))
            if wire['rejected'] != 0: raise RuntimeError('forbidden Modbus request attempted')
            print(json.dumps({**proof, 'binding_sha256': sha256(BINDING.read_bytes()).hexdigest(),
                'transport_sha256': sha256(TRANSPORT.read_bytes()).hexdigest(),
                'fault_numeric_item_states': held, 'wire_counts': wire,
                'fixture_host': '127.0.0.1', 'fixture_port': 1503, 'production_port': 503}, sort_keys=True), flush=True)
        finally:
            if container is not None:
                owner = runtime.run(['docker', 'inspect', '--format',
                    '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
                if owner != marker: raise RuntimeError('fixture cleanup ownership mismatch')
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_bms_fixture_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'reason': str(error)}))
        raise SystemExit(1) from None
