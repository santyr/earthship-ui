#!/usr/bin/env python3
"""Disconnected real-JVM display-estimator fault/restart/rollback rehearsal.

All write requests go through docker exec to the owned networkless fixture.
Production is read-only. Synthetic receipts never become household evidence.
"""
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'display_rehearsal_fixture', ROOT / 'scripts/qualify-season-rule-provider.py')
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
runtime = fixture.runtime
UID = 'hex_bms_ttd_smooth'
LABEL = 'hex.bms.estimator.qualification'
BASELINE = '8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a794'
EVIDENCE = ('BMS_SOC_Evidence_JSON', 'BMS_Aux_Evidence_JSON',
            'BMS_Runtime_Input_Evidence_JSON', 'Power_Evidence_JSON',
            'Inverter_AC_Evidence_JSON')
OUTPUTS = ('BMS_Runtime_Basis', 'BMS_TimeToDischarge_Smoothed', 'BMS_TimeToFull_Smoothed')
ITEMS = ('\n'.join('String ' + name for name in EVIDENCE)
         + '\nString BMS_Runtime_Basis\n'
         + '\n'.join('Number ' + name for name in (
             'BMS_TimeToDischarge_Smoothed', 'BMS_TimeToFull_Smoothed',
             'Sun_Position_Elevation', 'ConextGateway_ACPowerValue',
             'BMS_SOC', 'BMS_Capacity_Remaining_Ah', 'DCData_Current',
             'DCData_Voltage', 'BMS_TimeToDischarge_Min',
             'BMS_TimeToFull_Min', 'MPPT60_PV_Power')) + '\n').encode()
WRITABLE = frozenset((*EVIDENCE, 'Sun_Position_Elevation'))


def check_clone(info, marker):
    host = info.get('HostConfig', {})
    if (info.get('Config', {}).get('Labels', {}).get(LABEL) != marker
            or host.get('NetworkMode') != 'none' or host.get('Privileged')
            or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
            or host.get('ReadonlyRootfs') is not True
            or host.get('Memory') != 2147483648 or host.get('MemorySwap') != 2147483648
            or host.get('NanoCpus') != 2000000000
            or info.get('AppArmorProfile') != 'docker-default'):
        raise RuntimeError('isolated estimator containment mismatch')


def check_request(method, path):
    allowed = (
        method == 'GET' and (path == '/rules/' + UID
                            or path in {'/items/' + name for name in (*EVIDENCE, *OUTPUTS)})
        or method == 'PUT' and path in {'/items/' + name + '/state' for name in WRITABLE}
        or method == 'POST' and path in {'/rules', '/rules/' + UID + '/runnow'}
        or method == 'DELETE' and path == '/rules/' + UID)
    if not allowed:
        raise RuntimeError('request outside isolated estimator scope')


def receipts(now, current_ca):
    def field(value, ttl, property='value'):
        return {'status': 'valid', 'reason': 'ok', 'observedAt': now,
                'validUntil': now + ttl, property: value}

    def envelope(basis, fields):
        return {'version': 1, 'basis': basis, 'streamEpoch': 'synthetic-isolated',
                'sequence': 1, 'recordedAt': now, 'fields': fields}

    return {
        'BMS_SOC_Evidence_JSON': {'version': 1, 'streamEpoch': 'synthetic-isolated',
            'recordedAt': now, 'status': 'valid', 'reason': 'ok',
            'observedAt': now, 'scaleObservedAt': now, 'validUntil': now + 120000, 'soc': 80},
        'BMS_Aux_Evidence_JSON': envelope('discover_bms_190_native_aux_v1', {
            'battery.remaining_ah': field(320, 120000)}),
        'BMS_Runtime_Input_Evidence_JSON': envelope('native_runtime_inputs_v1', {
            'battery.dc_current_ca': field(current_ca, 90000),
            'battery.dc_voltage_cv': field(5000, 90000),
            'battery.ttd_min': field(500, 120000), 'battery.ttf_min': field(120, 120000)}),
        'Inverter_AC_Evidence_JSON': envelope('inverter_output', {
            'inverter.ac_output_w': field(150, 30000, 'watts')}),
        'Power_Evidence_JSON': envelope('synthetic-isolated', {
            'pv.input_power_w': field(500, 120000, 'watts')}),
    }


def same_definition(expected, actual):
    # RuleDTO supplies an empty inputs map on ScriptActionDTO readback.
    # No nonempty input, configuration, trigger or unknown-field drift is ignored.
    def actions(rule):
        return [{**row, 'inputs': row.get('inputs', {})} for row in rule['actions']]
    return (actual['triggers'] == expected['triggers']
            and actions(actual) == actions(expected))


def number_is(state, expected):
    try:
        return float(state) == expected
    except (TypeError, ValueError):
        return False


def main():
    original = runtime.oh.get('/rules/' + UID)
    source = (ROOT / 'openhab/rules/bms-runtime-estimator-evidence.js').read_text()
    descriptor = json.loads((ROOT / 'openhab/bms-runtime-estimator-evidence-resources.json').read_text())
    if (original.get('uid') != UID or original.get('editable') is not True
            or len(original.get('actions', [])) != 1 or original.get('conditions')
            or hashlib.sha256(original['actions'][0]['configuration']['script'].encode()).hexdigest() != BASELINE
            or descriptor.get('enabled') is not False or descriptor.get('replacesRule') != UID
            or 'sendCommand' in source):
        raise RuntimeError('production baseline or disabled candidate drift')
    baseline = {key: original.get(key) for key in
                ('uid', 'name', 'description', 'tags', 'triggers', 'conditions', 'actions')}
    candidate = {**baseline, 'name': 'Isolated source-bound runtime estimator',
                 'triggers': descriptor['triggers'], 'actions': [{
                     'id': 'estimator', 'type': 'script.ScriptAction', 'configuration': {
                         'type': 'application/javascript', 'script': source}}]}
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file():
        raise RuntimeError('pinned isolated JavaScript add-ons missing')
    marker = secrets.token_hex(8)
    container = None
    try:
        container = runtime.run(['docker', 'run', '-d', '--init', '--label', LABEL + '=' + marker,
            '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
            '--memory', '2048m', '--memory-swap', '2048m', '--cpus', '2', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
            '--entrypoint', '/bin/sh', runtime.IMAGE, '-c',
            'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
            'while [ ! -f /tmp/ready ]; do sleep 1; done; '
            'while true; do while [ ! -f /tmp/boot-permit ]; do sleep 1; done; '
            'rm /tmp/boot-permit; /openhab/start.sh server & jvm_child=$!; '
            'wait "$jvm_child"; touch /tmp/jvm-stopped; done']).decode().strip()
        check_clone(json.loads(runtime.run(['docker', 'inspect', container]))[0], marker)
        print('owned_networkless_estimator_fixture=' + container, flush=True)
        runtime.install(container, 'conf/items/estimator-rehearsal.items', ITEMS)
        runtime.install_bundles(container, bundles)
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/ready', '/tmp/boot-permit'])
        fixture.wait_for(lambda: fixture._startup_item(container, EVIDENCE[0]), seconds=240)
        time.sleep(20)
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        fixture.wait_for(lambda: fixture._active_bundle(client, 'org.graalvm.js.js-language'))
        runtime.install_bundles(container, [runtime.ADDON])
        fixture.wait_for(lambda: fixture._active_bundle(client, 'org.openhab.automation.jsscripting'))
        runtime.run(client + ['openhab:users add qualification ' + secrets.token_hex(20) + ' administrator'], b'\n')
        output = runtime.run(client + ["openhab:users addApiToken qualification qualification ''"], b'\n').decode()
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
        if len(tokens) != 1:
            raise RuntimeError('isolated credential creation failed; output withheld')
        header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()

        def rest(method, path, body=None, text=False):
            check_request(method, path)
            if method == 'POST' and path == '/rules' and body.get('uid') != UID:
                raise RuntimeError('isolated rule identity mismatch')
            args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method, '-H', '@-',
                    '-H', 'Content-Type: ' + ('text/plain' if text else 'application/json')]
            if body is not None:
                args += ['--data-binary', str(body) if text else json.dumps(body)]
            args += ['http://127.0.0.1:8080/rest' + path]
            payload, status = runtime.run(args, header).rsplit(b'\n', 1)
            try:
                payload = json.loads(payload) if payload else None
            except ValueError:
                payload = None
            return int(status), payload

        def install_rule(rule):
            if rest('POST', '/rules', rule)[0] != 201:
                raise RuntimeError('isolated rule creation failed')
            fixture.wait_for(lambda: fixture._managed_rule(rest, UID))
            installed = rest('GET', '/rules/' + UID)[1]
            if not same_definition(rule, installed):
                raise RuntimeError('isolated definition readback mismatch')

        def withdraw():
            if rest('DELETE', '/rules/' + UID)[0] not in (200, 204):
                raise RuntimeError('isolated rule withdrawal failed')
            fixture.wait_for(lambda: rest('GET', '/rules/' + UID)[0] == 404)

        def state(name):
            status, item = rest('GET', '/items/' + name)
            if status != 200:
                raise RuntimeError('isolated output unavailable')
            return item['state']

        def put(name, value):
            raw = json.dumps(value, separators=(',', ':')) if isinstance(value, dict) else str(value)
            if rest('PUT', '/items/' + name + '/state', raw, text=True)[0] not in (200, 202):
                raise RuntimeError('isolated synthetic input write failed')

        def feed(current=-300):
            for name, value in receipts(time.time_ns() // 1000000, current).items():
                put(name, value)
            put('Sun_Position_Elevation', 30)

        def execute(expected=None):
            if rest('POST', '/rules/' + UID + '/runnow', {})[0] != 200:
                raise RuntimeError('isolated execution request refused')
            if expected is not None:
                fixture.wait_for(lambda: state('BMS_Runtime_Basis') == expected, seconds=20)
            else:
                time.sleep(1)

        def outputs(ttd=None, ttf=0):
            # postUpdate is asynchronous across Items: basis readback alone
            # does not prove that both numeric publications have settled.
            def matches():
                return (number_is(state(OUTPUTS[2]), ttf)
                        and (ttd is None or number_is(state(OUTPUTS[1]), ttd)))
            try:
                fixture.wait_for(matches, seconds=20)
            except RuntimeError:
                print('isolated_output_diagnostic=' + json.dumps({
                    name: state(name)[:64] for name in OUTPUTS}), flush=True)
                raise RuntimeError('isolated numeric output readback failed') from None

        install_rule(candidate)
        execute('off')
        outputs(0)
        feed(); execute('evening'); execute('evening')
        feed(); execute('bms')
        outputs(500)
        feed(500); execute('now')
        outputs(ttf=120)
        feed(-500); execute()
        outputs()
        expired = receipts(time.time_ns() // 1000000 - 90000, -300)
        put(EVIDENCE[2], expired[EVIDENCE[2]]); execute('off')
        outputs(0)
        withdraw(); install_rule(candidate)
        feed(); execute('evening'); execute('evening')
        feed(); execute('bms')
        print('real_jvm_missing_expiry_charge_reversal_reload_checks=passed', flush=True)

        before = fixture.java_pids(container)
        if len(before) != 1:
            raise RuntimeError('one isolated server JVM required')
        try:
            runtime.run(client + ['system:shutdown -f'], b'\n')
        except RuntimeError:
            pass
        fixture.wait_for(lambda: before[0] not in fixture.java_pids(container), seconds=60)
        fixture.wait_for(lambda: fixture._jvm_stopped(container), seconds=30)
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit'])
        fixture.wait_for(lambda: fixture._startup_item(container, EVIDENCE[0]), seconds=240)
        after = fixture.java_pids(container)
        if len(after) != 1 or after == before:
            raise RuntimeError('isolated full JVM restart identity failed')
        fixture.wait_for(lambda: fixture._managed_rule(rest, UID), seconds=120)
        execute('off')
        outputs(0)
        feed(); execute('evening'); feed(); execute('bms')
        withdraw(); install_rule(baseline)
        if rest('GET', '/rules/' + UID)[1]['actions'] != baseline['actions']:
            raise RuntimeError('exact isolated baseline rollback failed')
        print('real_jvm_full_restart_fresh_recovery_exact_rollback=passed', flush=True)
        latest = runtime.oh.get('/rules/' + UID)
        if latest['actions'] != original['actions'] or latest['triggers'] != original['triggers']:
            raise RuntimeError('production baseline changed concurrently')
        print('status=qualified_isolated; production_writes=0; natural_charge_transition=not_tested; live_java_jdbc_average=not_tested', flush=True)
    finally:
        if container is not None:
            owner = runtime.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
            if owner != marker:
                raise RuntimeError('isolated cleanup ownership mismatch')
            runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
            print('owned_fixture_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    main()
