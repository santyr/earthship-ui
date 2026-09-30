#!/usr/bin/env python3
"""Synthetic real-event/real-JDBC collector probe in disconnected owned containers."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


jdbc = module('delivery_jdbc', 'qualify-persistence-jdbc.py')
fixture = module('delivery_fixture', 'qualify-bms-runtime-estimator.py').fixture
runtime = fixture.runtime
ITEM = 'BMS_Runtime_Input_Evidence_JSON'
UID = 'isolated_runtime_delivery_probe'
LABEL = 'hex.bms.runtime.delivery'
RESULT = '/tmp/hex-runtime-delivery-result.json'
SOURCE_SHA = '621f4ac7416de35e1b68f87f7d0ed4096c729319cad08e5b71bc95b1b0062c80'
READINGS = [12479, 13120, 10701, 11679, 11617, 5827, 6439, 6828, 6330, 6818]


def probe(source):
    if sha256(source.encode()).hexdigest() != SOURCE_SHA:
        raise RuntimeError('collector source hash drift')
    return r'''
const System = Java.type('java.lang.System');
if (System.getenv('HEX_BMS_RUNTIME_ISOLATED') !== '1') throw Error('isolated guard missing');
const real = require('openhab');
const Factory = Java.type('org.openhab.core.items.events.ItemEventFactory');
const Decimal = Java.type('org.openhab.core.library.types.DecimalType');
const Thread = Java.type('java.lang.Thread');
const Files = Java.type('java.nio.file.Files');
const Paths = Java.type('java.nio.file.Paths');
const store = new Map(), emitted = [];
let offline = null;
const output = real.items.getItem('BMS_Runtime_Input_Evidence_JSON');
function collect(event) {
  const require = name => {
    if (name !== 'openhab') throw Error('unexpected dependency');
    return {
      cache: { private: { get: key => store.get(key), put: (key, value) => store.set(key, value) } },
      things: { getThing: uid => ({ status: uid === offline ? 'OFFLINE' : 'ONLINE' }) },
      items: { getItem: name => {
        if (name !== 'BMS_Runtime_Input_Evidence_JSON') throw Error('unexpected output');
        return { rawItem: output.rawItem, postUpdate: value => {
          emitted.push(JSON.parse(value)); output.postUpdate(value);
        } };
      } },
    };
  };
''' + source + r'''
}
const sources = {
  current: ['DCData_Native_Current_Raw_cA', 'modbus:data:schneiderBatterySunSpec:battery802Core:currentRawCentiA', -309],
  voltage: ['DCData_Native_Voltage_Raw_cV', 'modbus:data:schneiderBatterySunSpec:battery802Core:voltageRawCentiV', 5297],
  ttd: ['BMS_TimeToDischarge_Min', 'modbus:data:discoverBms190:bmsMain:ttdMin', 5510],
  ttf: ['BMS_TimeToFull_Min', 'modbus:data:discoverBms190:bmsMain:ttfMin', 0],
};
function receive(key, value = sources[key][2]) {
  Thread.sleep(3);
  const spec = sources[key];
  collect(Factory.createStateEvent(spec[0], new Decimal(String(value)),
    'org.openhab.core.thing$' + spec[1] + ':number'));
}
collect(null);
for (const key of Object.keys(sources)) receive(key);
if (!Object.values(emitted.at(-1).fields).every(f => f.status === 'valid')) throw Error('warmup failed');
const beforeBurst = emitted.length;
for (let n = 0; n < 20; n++) receive('current', -330 - n);
if (emitted.length !== beforeBurst) throw Error('high-rate current writes escaped bound');
const readings = [12479, 13120, 10701, 11679, 11617, 5827, 6439, 6828, 6330, 6818];
const beforeRuntime = emitted.length;
for (const value of readings) receive('ttd', value);
if (emitted.length !== beforeRuntime + readings.length) throw Error('runtime sample omitted');
const delivered = emitted.slice(beforeRuntime).map(r => r.fields['battery.ttd_min'].value);
if (JSON.stringify(delivered) !== JSON.stringify(readings)) throw Error('runtime sequence mismatch');
const beforeRepeated = emitted.length;
receive('ttf', 0); receive('ttf', 0);
if (emitted.length !== beforeRepeated + 2) throw Error('unchanged native observations omitted');
offline = sources.ttd[1]; collect(null);
if (emitted.at(-1).fields['battery.ttd_min'].reason !== 'source_unavailable') throw Error('fault barrier missing');
Files.writeString(Paths.get('/tmp/hex-runtime-delivery-result.json'), JSON.stringify({
  synthetic: true, highRateWrites: 0, readings, emitted,
}));
'''


def validate(result, rows):
    if (result.get('synthetic') is not True or result.get('highRateWrites') != 0
            or result.get('readings') != READINGS):
        raise RuntimeError('synthetic probe qualification failed')
    receipts = result.get('emitted', [])
    if len(receipts) != 18 or len(rows) != len(receipts):
        raise RuntimeError('JDBC delivery count mismatch')
    previous = -1
    native = {'battery.ttd_min': [], 'battery.ttf_min': []}
    identities = {}
    for sequence, (receipt, row) in enumerate(zip(receipts, rows), 1):
        if (receipt.get('sequence') != sequence or receipt.get('basis') != 'native_runtime_inputs_v1'
                or json.loads(row['state']) != receipt or row['time'] <= previous):
            raise RuntimeError('JDBC receipt sequence or unique timestamp mismatch')
        previous = row['time']
        for key in native:
            field = receipt.get('fields', {}).get(key, {})
            identity = (receipt.get('streamEpoch'), field.get('observedAt'))
            if field.get('status') == 'valid' and identities.get(key) != identity:
                identities[key] = identity
                native[key].append(field.get('value'))
    if (native['battery.ttd_min'] != [5510, *READINGS]
            or native['battery.ttf_min'] != [0, 0, 0]
            or receipts[-1].get('fields', {}).get('battery.ttd_min', {}).get('reason') != 'source_unavailable'):
        raise RuntimeError('persisted original-observation or fault sequence mismatch')
    for receipt, expected in zip(receipts[5:15], READINGS):
        field = receipt['fields']['battery.ttd_min']
        if field.get('value') != expected or field.get('observedAt') != receipt.get('recordedAt'):
            raise RuntimeError('native TTD observation was not delivered immediately')
    for receipt in receipts[15:17]:
        field = receipt['fields']['battery.ttf_min']
        if field.get('observedAt') != receipt.get('recordedAt'):
            raise RuntimeError('unchanged native TTF observation was delayed or omitted')
    return {'status': 'qualified_synthetic_real_event_jdbc', 'receipts': len(receipts),
        'runtime_readings': len(result['readings']), 'high_rate_current_writes': 0,
        'source_sha256': SOURCE_SHA, 'physical_sources_tested': False, 'production_writes': 0}


def main():
    source = (ROOT / 'openhab/rules/bms-runtime-input-evidence.js').read_text()
    script = probe(source)
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file():
        raise RuntimeError('isolated JavaScript dependencies unavailable')
    marker = secrets.token_hex(8)
    with jdbc.Database(candidate_runtime=True) as database:
        # No extra swap allowance; both containers have explicit memory limits.
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
                '-e', 'HEX_BMS_RUNTIME_ISOLATED=1', '--entrypoint', '/bin/sh', runtime.IMAGE, '-c',
                'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']).decode().strip()
            info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
            host = info['HostConfig']
            if (info['Config']['Labels'].get(LABEL) != marker or host['NetworkMode'] != database.network
                    or host['Privileged'] or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
                    or not host['ReadonlyRootfs'] or host['Memory'] != host['MemorySwap']
                    or host['Memory'] != 2147483648 or host['NanoCpus'] != 2000000000
                    or info['AppArmorProfile'] != 'docker-default'):
                raise RuntimeError('isolated runtime containment mismatch')
            db = json.loads(runtime.run(['docker', 'inspect', database.cid]))[0]
            if (db['HostConfig']['NetworkMode'] != 'none' or db['HostConfig']['Privileged']
                    or db['HostConfig'].get('Binds') or db['HostConfig'].get('Devices')
                    or db['HostConfig'].get('PortBindings') or db['HostConfig']['Memory'] != 402653184
                    or db['HostConfig']['MemorySwap'] != 402653184):
                raise RuntimeError('isolated database containment mismatch')
            print('owned_disconnected_delivery_fixture=' + container, flush=True)
            database.stage(container)
            runtime.install(container, 'conf/persistence/jdbc.persist',
                (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            runtime.install_bundles(container, bundles)
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/ready'])
            fixture.wait_for(lambda: fixture._startup_item(container, ITEM), seconds=240)
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.graalvm.js.js-language'))
            runtime.install_bundles(container, [runtime.ADDON])
            fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.automation.jsscripting'))
            runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20) + ' administrator'], b'\n')
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', runtime.run(client +
                ["openhab:users addApiToken qualification qualification ''"], b'\n').decode())
            if len(tokens) != 1: raise RuntimeError('isolated credential unavailable; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
            def rest(method, path, body=None):
                if not (method == 'GET' and path in ('/rules/' + UID, '/persistence/items/' + ITEM + '?serviceId=jdbc')
                    or method == 'POST' and path in ('/rules', '/rules/' + UID + '/runnow')):
                    raise RuntimeError('request outside isolated collector scope')
                if path == '/rules' and (body.get('uid') != UID or body.get('triggers') != []):
                    raise RuntimeError('isolated triggerless probe identity mismatch')
                args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8', '-w', '\n%{http_code}',
                    '-X', method, '-H', '@-', '-H', 'Content-Type: application/json']
                if body is not None: args += ['--data-binary', json.dumps(body)]
                payload, status = runtime.run(args + ['http://127.0.0.1:8080/rest' + path], header).rsplit(b'\n', 1)
                return int(status), json.loads(payload) if payload else None
            rule = {'uid': UID, 'name': 'Synthetic collector delivery probe', 'triggers': [], 'conditions': [],
                'actions': [{'id': 'probe', 'type': 'script.ScriptAction', 'configuration': {
                    'type': 'application/javascript', 'script': script}}]}
            if rest('POST', '/rules', rule)[0] != 201: raise RuntimeError('isolated probe creation failed')
            fixture.wait_for(lambda: rest('GET', '/rules/' + UID)[1].get('status', {}).get('status') == 'IDLE')
            if rest('POST', '/rules/' + UID + '/runnow', {})[0] != 200: raise RuntimeError('isolated execution refused')
            fixture.wait_for(lambda: runtime.run(['docker', 'exec', container, 'test', '-f', RESULT]) == b'', seconds=60)
            result = json.loads(runtime.run(['docker', 'exec', container, 'cat', RESULT]))
            def delivered():
                status, payload = rest('GET', '/persistence/items/' + ITEM + '?serviceId=jdbc')
                rows = payload.get('data', []) if status == 200 and isinstance(payload, dict) else []
                return rows if len(rows) == len(result['emitted']) else False
            rows = fixture.wait_for(delivered, seconds=60)
            print(json.dumps(validate(result, rows), sort_keys=True), flush=True)
        finally:
            if container is not None:
                owner = runtime.run(['docker', 'inspect', '--format',
                    '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
                if owner != marker: raise RuntimeError('fixture cleanup ownership mismatch')
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_delivery_fixture_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1) from None
