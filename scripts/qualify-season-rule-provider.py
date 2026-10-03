#!/usr/bin/env python3
"""Rehearse display rule managed/file/managed handoffs offline.

The disposable OpenHAB 5.2.1 container has no network or production mounts.
It is removed on success or failure. No live rule or Item is modified.
"""

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import stat
import time

import sky_control_probe

ROOT = Path(__file__).resolve().parents[1]
INSTALLED_RULE_DIRECTORY = Path('/etc/openhab/automation/js')
spec = importlib.util.spec_from_file_location(
    'isolated_jss_runtime', ROOT / 'scripts/qualify-inverter-ac-evidence-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

@dataclass(frozen=True)
class DisplayRule:
    uid: str
    source: Path
    baseline: str
    label: str
    items: bytes
    startup_item: str
    triggers: tuple


RULES = {
    'battery-icon': DisplayRule(
        uid='UpdateBatteryIcon',
        source=ROOT / 'openhab/file-config/automation/js/battery-icon.js',
        baseline='834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f',
        label='hex.battery.icon.rule.qualification',
        items=b'''Number BMS_SOC
Number:ElectricCurrent DCData_Current
String BatteryIcon
Switch BatteryChargingStatus
''',
        startup_item='BMS_SOC',
        triggers=(('timer.GenericCronTrigger',
                   (('cronExpression', '0/30 * * * * ?'),)),),
    ),
    'season': DisplayRule(
        uid='update_days_until_season',
        source=ROOT / 'openhab/file-config/automation/js/update_days_until_season.js',
        baseline='d43b3f993991966ade5d428bc4ff6af603a253a06f336ff93221cc22cc332311',
        label='hex.season.rule.qualification',
        items=b'''Number:Time Sun_TimeLeft "Sun time left"
String Sun_NextSeason "Next season"
String DaysUntilNextSeason "Days until next season"
''',
        startup_item='Sun_TimeLeft',
        triggers=(('core.ItemStateChangeTrigger', (('itemName', 'Sun_TimeLeft'),)),),
    ),
    'sky': DisplayRule(
        uid='sky-condition-calculator',
        source=ROOT / 'openhab/file-config/automation/js/sky-condition-calculator.js',
        baseline='d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c',
        label='hex.sky.rule.qualification',
        items=b'''String Sun_SunPhaseName
String Sun_TotalRadiation
String AmbientWeatherWS2902A_SolarRadiation
String WeatherData_HealthStatus
String WeatherData_WH65B_AgeSeconds
String SunPhaseIcon
String MoonPhaseicon
String SkyCondition
String SkyConditionIcon
String SkyCondition_LastEval
String SkyCondition_Diagnostic
''',
        startup_item='Sun_SunPhaseName',
        triggers=(
            ('core.ItemStateChangeTrigger', (('itemName', 'Sun_SunPhaseName'),)),
            ('core.ItemStateChangeTrigger', (('itemName', 'Sun_TotalRadiation'),)),
            ('core.ItemStateChangeTrigger', (('itemName', 'AmbientWeatherWS2902A_SolarRadiation'),)),
            ('core.ItemStateChangeTrigger', (('itemName', 'WeatherData_HealthStatus'),)),
            ('timer.GenericCronTrigger', (('cronExpression', '0 0/2 * * * ?'),)),
        ),
    ),
    'extrema': DisplayRule(
        uid='temp-highlow-24h',
        source=ROOT / 'openhab/file-config/automation/js/temperature-highlow-24h.js',
        baseline='a499269f5aabf7a82de55f9fbc168d7c281c3155d07d91321a2259199b7072db',
        label='hex.extrema.rule.qualification',
        items=b'''String AmbientWeatherWS2902A_IndoorSensor_Temperature
String AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature
String IndoorTemp_24h_Low
String IndoorTemp_24h_High
String OutdoorTemp_24h_Low
String OutdoorTemp_24h_High
''',
        startup_item='AmbientWeatherWS2902A_IndoorSensor_Temperature',
        triggers=(('timer.GenericCronTrigger',
                   (('cronExpression', '0 0/15 * * * ?'),)),),
    ),
    'bitcoin': DisplayRule(
        uid='hex_btc_24h_change',
        source=ROOT / 'openhab/file-config/automation/js/bitcoin-24h-change.js',
        baseline='9e15eb8e7f4e3d3118f12295d7b09f82525ab52f41b951f8809097c98fc369bb',
        label='hex.bitcoin.rule.qualification',
        items=b'''Number BTC_USD_Price
Number BTC_Price_24h_PercentChange
''',
        startup_item='BTC_USD_Price',
        triggers=(('core.ItemStateUpdateTrigger', (('itemName', 'BTC_USD_Price'),)),),
    ),
}


def trigger_contract(rule):
    return tuple((trigger.get('type'), tuple(sorted(trigger.get('configuration', {}).items())))
                 for trigger in rule.get('triggers', []))


def managed_payload(rule):
    # Optional descriptive fields can be absent in a genuine managed DTO.
    # Preserve omission rather than inventing values or exporting runtime status.
    return {key: rule[key] for key in (
        'uid', 'name', 'description', 'tags', 'triggers', 'conditions', 'actions')
        if key in rule}


def wait_for(check, *, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(2)
    raise RuntimeError('isolated display rule state timeout')


def managed_baseline(config, live, backup=None):
    """A migrated rule needs its exact private preimage, not a fabricated DTO."""
    if live.get('uid') != config.uid:
        raise RuntimeError('live display rule identity changed')
    if live.get('editable') is False:
        if backup is None:
            raise RuntimeError('file-owned rule requires its retained managed backup')
        path = Path(backup)
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > 65536):
            raise RuntimeError('private managed backup shape or permissions invalid')
        installed = INSTALLED_RULE_DIRECTORY / config.source.name
        if (installed.is_symlink() or installed.read_bytes() != config.source.read_bytes()
                or trigger_contract(live) != config.triggers):
            raise RuntimeError('installed display source or trigger drift')
        live = json.loads(path.read_bytes())
    if (live.get('uid') != config.uid or live.get('editable') is not True
            or trigger_contract(live) != config.triggers
            or len(live.get('actions', [])) != 1
            or live.get('conditions')):
        raise RuntimeError('managed display rule definition changed')
    script = live['actions'][0]['configuration']['script']
    if hashlib.sha256(script.encode()).hexdigest() != config.baseline:
        raise RuntimeError('managed display script baseline changed')
    return live


def java_pids(container):
    listing = runtime.run(['docker', 'exec', container, 'ps', '-eo', 'pid,stat,comm']).decode()
    return tuple(int(fields[0]) for line in listing.splitlines()
                 if len(fields := line.split()) == 3 and fields[2] == 'java'
                 and not fields[1].startswith('Z'))


def main(kind, *, managed_backups=None, restart=False, sky_control=False):
    if sky_control and (kind != 'sky' or not restart):
        raise RuntimeError('sky control probe requires sky scope and isolated JVM restart')
    kinds = ('season', 'extrema', 'bitcoin') if kind == 'display-set' else (kind,)
    configs = [RULES[name] for name in kinds]
    managed_backups = managed_backups or {}
    if set(managed_backups) - set(kinds):
        raise RuntimeError('backup supplied for a rule outside selected scope')
    baselines = {name: managed_baseline(RULES[name], runtime.oh.get('/rules/' + RULES[name].uid),
                                      managed_backups.get(name)) for name in kinds}
    control = sky_control_probe.control_payload(
        runtime.oh.get('/rules/' + sky_control_probe.UID),
        (ROOT / 'openhab/rules/southoutlet-cycle-current.js').read_bytes(),
    ) if sky_control else None
    bundles = sorted(runtime.GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if len(bundles) != 22 or not runtime.ADDON.is_file() or any(not c.source.is_file() for c in configs):
        raise RuntimeError('isolated JavaScript resources unavailable')
    marker = secrets.token_hex(8)
    label = 'hex.display.rules.qualification' if kind == 'display-set' else configs[0].label
    command = ('cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
               'while [ ! -f /tmp/ready ]; do sleep 1; done; ')
    command += ('while true; do while [ ! -f /tmp/boot-permit ]; do sleep 1; done; '
                'rm /tmp/boot-permit; /openhab/start.sh server & jvm_child=$!; '
                'wait "$jvm_child"; touch /tmp/jvm-stopped; done'
                if restart else 'exec /openhab/start.sh server')
    container = None
    try:
        container = runtime.run(['docker', 'run', '-d', '--init', '--label', label + '=' + marker,
            '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
            '--memory', '2048m', '--memory-swap', '2048m', '--cpus', '2', '--pids-limit', '256',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
            '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
            '-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
            '--entrypoint', '/bin/sh', runtime.IMAGE, '-c', command]).decode().strip()
        info = json.loads(runtime.run(['docker', 'inspect', container]))[0]
        host = info['HostConfig']
        if (info['Config']['Labels'].get(label) != marker
                or host['NetworkMode'] != 'none' or host['Privileged']
                or host.get('Binds') or host.get('Devices') or host.get('PortBindings')
                or info['AppArmorProfile'] != 'docker-default'):
            raise RuntimeError('isolated container policy mismatch')
        runtime.install(container, 'conf/items/display-rehearsal.items', b'\n'.join(c.items for c in configs))
        if sky_control:
            runtime.install(container, 'conf/items/sky-control-rehearsal.items', sky_control_probe.ITEMS)
        runtime.install_bundles(container, bundles)
        runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit', '/tmp/ready'])
        wait_for(lambda: all(_startup_item(container, c.startup_item) for c in configs), seconds=240)
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

        def rest(method, path, body=None, *, content_type='application/json'):
            args = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '8',
                    '-w', '\n%{http_code}', '-X', method,
                    '-H', 'Authorization: Bearer ' + token,
                    '-H', 'Content-Type: ' + content_type]
            if body is not None:
                args += ['--data-binary', '@-']
            args += ['http://127.0.0.1:8080/rest' + path]
            data = (str(body).encode() if content_type == 'text/plain' else json.dumps(body).encode()) \
                if body is not None else None
            raw = runtime.run(args, data)
            payload, status = raw.rsplit(b'\n', 1)
            try:
                decoded = json.loads(payload) if payload else None
            except ValueError:
                decoded = payload.decode(errors='replace')[:80]
            return int(status), decoded

        runtime.run(['docker', 'exec', container, 'mkdir', '-p', '/openhab/conf/automation/js'])
        def probe_control(phase):
            if sky_control:
                wait_for(lambda: _healthy_control(rest), seconds=120)
                sky_control_probe.run_probe(rest, lambda: runtime.run([
                    'docker', 'exec', container, 'cat', '/openhab/userdata/logs/events.log']).decode(),
                    wait_for, phase=phase)

        if sky_control and rest('POST', '/rules', control)[0] != 201:
            raise RuntimeError('isolated exact managed sky consumer creation failed')
        managed = {name: managed_payload(baselines[name]) for name in kinds}
        for name, config in zip(kinds, configs):
            if rest('POST', '/rules', managed[name])[0] != 201:
                raise RuntimeError('isolated managed rule creation failed')
            wait_for(lambda: _managed_rule(rest, config.uid))
            if rest('DELETE', '/rules/' + config.uid)[0] not in (200, 204):
                raise RuntimeError('isolated managed withdrawal failed')
            wait_for(lambda: rest('GET', '/rules/' + config.uid)[0] == 404)
            runtime.install(container, 'conf/automation/js/' + config.source.name, config.source.read_bytes())
            file_rule = wait_for(lambda: _file_rule(rest, config.uid), seconds=120)
            if trigger_contract(file_rule) != config.triggers:
                raise RuntimeError('isolated file rule trigger mismatch')
            print('isolated_file_rule_uid=' + file_rule['uid'], flush=True)
        probe_control('file-hot')
        if restart:
            before = java_pids(container)
            if len(before) != 1:
                # PID/state/command only, never arguments, environment or tokens.
                listing = runtime.run(['docker', 'exec', container, 'ps', '-eo', 'pid,stat,comm']).decode()
                print('isolated_process_identity_diagnostic=' + json.dumps(listing.splitlines()), flush=True)
                raise RuntimeError('one isolated active server JVM required before restart')
            try:
                runtime.run(client + ['system:shutdown -f'], b'\n')
            except RuntimeError:
                pass  # SSH may close on shutdown; actual process exit is checked.
            wait_for(lambda: before[0] not in java_pids(container), seconds=60)
            wait_for(lambda: _jvm_stopped(container), seconds=30)
            runtime.run(['docker', 'exec', container, 'touch', '/tmp/boot-permit'])
            wait_for(lambda: all(_startup_item(container, c.startup_item) for c in configs), seconds=240)
            after = java_pids(container)
            if len(after) != 1 or before == after:
                raise RuntimeError('isolated server JVM identity did not change')
            for config in configs:
                restored = wait_for(lambda: _file_rule(rest, config.uid), seconds=120)
                if trigger_contract(restored) != config.triggers:
                    raise RuntimeError('isolated restarted trigger contract mismatch')
            print('isolated_full_jvm_restart=true; file_rule_count=' + str(len(configs)), flush=True)
            probe_control('file-restarted')
        for name, config in zip(kinds, configs):
            runtime.run(['docker', 'exec', container, 'rm', '/openhab/conf/automation/js/' + config.source.name])
            wait_for(lambda: rest('GET', '/rules/' + config.uid)[0] == 404)
            if rest('POST', '/rules', managed[name])[0] != 201:
                raise RuntimeError('isolated managed rollback failed')
            restored = wait_for(lambda: _managed_rule(rest, config.uid))
            if (restored.get('triggers') != managed[name]['triggers']
                    or restored.get('actions') != managed[name]['actions']):
                raise RuntimeError('isolated managed rollback definition mismatch')
            print('isolated_managed_rollback_uid=' + config.uid, flush=True)
        probe_control('managed-rollback')
    finally:
        if container is not None:
            result = runtime.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + label + '"}}', container])
            if result.decode().strip() == marker:
                runtime.run(['docker', 'rm', '-f', '-v', container], timeout=90)
                print('owned_isolated_container_removed=true', flush=True)
    print('status=passed; production_writes=0; natural_updates=not_tested')


def _startup_item(container, item):
    try:
        runtime.run(['docker', 'exec', container, 'curl', '-fsS', '--max-time', '3',
                     'http://127.0.0.1:8080/rest/items/' + item])
        return True
    except RuntimeError:
        return False


def _jvm_stopped(container):
    try:
        runtime.run(['docker', 'exec', container, 'test', '-f', '/tmp/jvm-stopped'])
        return True
    except RuntimeError:
        return False


def _active_bundle(client, name):
    listing = runtime.run(client + ['bundle:list -s'], b'\n').decode(errors='replace')
    return any(name in line and 'Active' in line for line in listing.splitlines())


def _file_rule(rest, uid):
    status, rule = rest('GET', '/rules/' + uid)
    return rule if (status == 200 and isinstance(rule, dict) and rule.get('uid') == uid
        and rule.get('editable') is False and rule.get('status') in (
            {'status': 'IDLE', 'statusDetail': 'NONE'},
            {'status': 'RUNNING', 'statusDetail': 'NONE'})) else None


def _managed_rule(rest, uid):
    status, rule = rest('GET', '/rules/' + uid)
    return rule if (status == 200 and isinstance(rule, dict) and rule.get('uid') == uid
                   and rule.get('editable') is True) else None


def _healthy_control(rest):
    rule = _managed_rule(rest, sky_control_probe.UID)
    return rule if rule and rule.get('status') == {'status': 'IDLE', 'statusDetail': 'NONE'} else None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=(*RULES, 'display-set'), required=True)
    parser.add_argument('--managed-backup', action='append', default=[], metavar='KIND=PATH')
    parser.add_argument('--restart', action='store_true', help='Verify an isolated full JVM restart, not production recovery')
    parser.add_argument('--sky-control-probe', action='store_true',
                        help='Include the exact pump consumer and synthetic fail-closed/positive probes, only with --kind sky --restart')
    args = parser.parse_args()
    backups = {}
    for value in args.managed_backup:
        name, separator, path = value.partition('=')
        if not separator or name not in RULES or name in backups or not path:
            parser.error('managed backups must be unique KIND=PATH entries')
        backups[name] = Path(path)
    main(args.kind, managed_backups=backups, restart=args.restart, sky_control=args.sky_control_probe)
