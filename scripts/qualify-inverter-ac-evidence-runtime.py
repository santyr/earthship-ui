#!/usr/bin/env python3
"""Disposable, networkless OpenHAB 5.2.1 evidence-rule qualifier."""
import argparse
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

IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'
ADDON = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/addons/bundles/'
             'org.openhab.automation.jsscripting/5.2.1/org.openhab.automation.jsscripting-5.2.1.jar')
GRAAL = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1/org/openhab/osgiify')
CANDIDATES = {
    'ac': {
        'item': 'Inverter_AC_Evidence_JSON',
        'source': ROOT / 'openhab/rules/inverter-ac-evidence.js',
        'item_source': ROOT / 'openhab/file-config/items/inverter-ac-evidence.items',
        'resource': ROOT / 'openhab/inverter-ac-evidence-resources.json',
        'basis': 'inverter_output', 'field': 'inverter.ac_output_w',
        'warning': 'Inverter AC evidence persistence enqueue failed',
    },
    'pv-day': {
        'item': 'MPPT60_PV_Day_Evidence_JSON',
        'source': ROOT / 'openhab/rules/mppt60-pv-day-evidence.js',
        'item_source': ROOT / 'openhab/candidates/mppt60-pv-day-evidence.items',
        'observation_source': ROOT / 'openhab/candidates/mppt60-pv-day-observation.items',
        'transform_source': ROOT / 'openhab/transform/mppt60_pv_day_observation.js',
        'resource': ROOT / 'openhab/mppt60-pv-day-evidence-resources.json',
        'basis': 'mppt60_native_pv_day_wh', 'field': 'mppt60.pv_day_wh',
        'warning': 'MPPT60 PV evidence persistence enqueue failed',
    },
}


def run(args, data=None, *, timeout=45):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError('isolated command failed: ' + args[0])
    return result.stdout


def install(container, destination, body):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as output:
        entry = tarfile.TarInfo(destination)
        entry.size, entry.mode = len(body), 0o644
        output.addfile(entry, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/openhab'],
        archive.getvalue())


def install_bundles(container, files):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as output:
        for path in files:
            body = path.read_bytes()
            entry = tarfile.TarInfo('addons/' + path.name)
            entry.size, entry.mode = len(body), 0o644
            output.addfile(entry, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/openhab'],
        archive.getvalue(), timeout=90)


def main(kind='ac', *, installed_control=False):
    candidate = CANDIDATES[kind]
    item_name = candidate['item']
    definition = json.loads(candidate['resource'].read_text())
    rule_uid = definition['rule']['uid']
    isolated_rule = 'isolated_' + rule_uid
    for endpoint in ('/items/' + item_name, '/rules/' + rule_uid):
        try:
            oh.get(endpoint)
        except HTTPError as error:
            if error.code != 404:
                raise
        else:
            if kind == 'ac' and installed_control:
                continue
            raise RuntimeError('candidate already installed on production host')
    source = candidate['source'].read_text()
    bundles = sorted(GRAAL.glob('org.graalvm.*/25.0.1/*.jar'))
    if not ADDON.is_file() or len(bundles) != 22 or 'sendCommand' in source:
        raise RuntimeError('runtime add-on missing or action path in source')
    marker = secrets.token_hex(8)
    container = run(['docker', 'run', '-d', '--label', 'hex.evidence.rule=' + marker,
        '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
        '--memory', '2048m', '--cpus', '2', '--pids-limit', '256',
        '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,uid=9001,gid=9001',
        '--tmpfs', '/openhab/conf:rw,nosuid,nodev,size=64m,uid=9001,gid=9001',
        '--tmpfs', '/openhab/userdata:rw,exec,nosuid,nodev,size=512m,uid=9001,gid=9001',
        '--tmpfs', '/openhab/addons:rw,nosuid,nodev,size=160m,uid=9001,gid=9001',
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
        install(container, 'conf/items/' + candidate['item_source'].name,
                candidate['item_source'].read_bytes())
        # Graal's language inventory is frozen when the JSS factory creates
        # its shared Engine. Fileinstalling all bundles together races that
        # activation and can leave an Active JSS bundle with no JS language.
        install_bundles(container, bundles)
        run(['docker', 'exec', container, 'touch', '/tmp/ready'])
        for _ in range(80):
            try:
                run(['docker', 'exec', container, 'curl', '-fsS', '--max-time', '3',
                     'http://127.0.0.1:8080/rest/items/' + item_name])
                break
            except RuntimeError:
                time.sleep(3)
        else:
            raise RuntimeError('isolated Item provider startup timeout')
        time.sleep(20)
        client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                  '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        for _ in range(20):
            bundle_listing = run(client + ['bundle:list -s'], b'\n').decode(errors='replace')
            js_language = [line for line in bundle_listing.splitlines()
                           if 'org.graalvm.js.js-language' in line]
            if js_language and any('Active' in line for line in js_language):
                break
            time.sleep(3)
        else:
            raise RuntimeError('isolated Graal JavaScript language bundle unavailable')
        install_bundles(container, [ADDON])
        js_bundles = []
        for _ in range(12):
            bundle_listing = run(client + ['bundle:list -s'], b'\n').decode(errors='replace')
            js_bundles = [line for line in bundle_listing.splitlines()
                          if 'org.openhab.automation.jsscripting' in line]
            if any('Active' in line for line in js_bundles):
                break
            time.sleep(3)
        if not js_bundles:
            log = run(['docker', 'exec', container, 'cat',
                       '/openhab/userdata/logs/openhab.log']).decode(errors='replace')
            clues = [line for line in log.splitlines()
                     if any(term in line.lower() for term in ('fileinstall', 'graalvm', 'jsscripting'))]
            print('isolated_bundle_diagnostic_lines=' + str(len(clues)), flush=True)
            for line in clues[-5:]:
                print('isolated_bundle_diagnostic=' + line[:240], flush=True)
            raise RuntimeError('isolated JS scripting bundle absent')
        print('isolated_js_bundle_states=' + ','.join(
            'Active' if 'Active' in line else 'not_active' for line in js_bundles), flush=True)
        if not any('Active' in line for line in js_bundles):
            print('isolated_js_bundle_listing=' + js_bundles[0][:250], flush=True)
            bundle_id = re.match(r'\s*(\d+)\s*[|│]', js_bundles[0])
            if bundle_id:
                diagnosis = run(client + ['bundle:diag ' + bundle_id.group(1)],
                                b'\n').decode(errors='replace')
                for line in diagnosis.splitlines()[-12:]:
                    print('isolated_js_bundle_diag=' + line[:320], flush=True)
            log = run(['docker', 'exec', container, 'cat',
                       '/openhab/userdata/logs/openhab.log']).decode(errors='replace')
            lines = log.splitlines()
            for index, line in enumerate(lines):
                if 'Could not resolve module: org.openhab.automation.jsscripting' in line:
                    for detail in lines[index:index + 5]:
                        print('isolated_bundle_resolution=' + detail[:320], flush=True)
                    break
            raise RuntimeError('isolated JS scripting bundle unresolved')
        run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                      + ' administrator'], b'\n')
        output = run(client + ["openhab:users addApiToken qualification qualification ''"],
                     b'\n').decode()
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
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
            raw = run(args, json.dumps(body).encode() if body is not None else None)
            payload, status = raw.rsplit(b'\n', 1)
            return int(status), json.loads(payload) if payload else None

        # Keep transform-linked Item loading separate from bundle startup so a
        # failure can be attributed to the bundle or the candidate Item.
        # This is isolated-container installation, never production.
        if candidate.get('transform_source'):
            install(container, 'conf/transform/' + candidate['transform_source'].name,
                    candidate['transform_source'].read_bytes())
        if candidate.get('observation_source'):
            install(container, 'conf/items/' + candidate['observation_source'].name,
                    candidate['observation_source'].read_bytes())
            for _ in range(15):
                status, _ = rest('GET', '/items/MPPT60_PV_Day_Observation_JSON')
                if status == 200:
                    break
                time.sleep(2)
            else:
                raise RuntimeError('isolated observation Item provider timeout')

        rule_definition = definition['rule']
        rule = {'uid': isolated_rule, 'name': rule_definition['name'],
                'description': 'Isolated observational qualification',
                'triggers': rule_definition['triggers'], 'conditions': [],
                'actions': [{'id': 'evidence', 'type': 'script.ScriptAction',
                             'configuration': {'type': 'application/javascript', 'script': source}}]}
        status, _ = rest('POST', '/rules', rule)
        if status != 201:
            raise RuntimeError('isolated rule creation refused: HTTP ' + str(status))
        for _ in range(20):
            status, loaded = rest('GET', '/rules/' + isolated_rule)
            if status == 200 and loaded.get('status', {}).get('status') == 'IDLE':
                break
            time.sleep(2)
        else:
            raise RuntimeError('isolated rule failed to become IDLE')
        status, _ = rest('POST', '/rules/' + isolated_rule + '/runnow', {})
        if status != 200:
            raise RuntimeError('isolated rule execution request refused')
        time.sleep(5)
        status, loaded = rest('GET', '/rules/' + isolated_rule)
        if status != 200 or loaded.get('status', {}).get('status') != 'IDLE':
            raise RuntimeError('isolated rule did not return to IDLE')
        installed = loaded.get('triggers', [])
        if {(x.get('id'), x.get('type')) for x in installed} != {
                (x['id'], x['type']) for x in rule_definition['triggers']}:
            raise RuntimeError('isolated trigger registration differs')
        if candidate.get('observation_source'):
            observation_name = definition['observationItemSource'].split('/')[-1]
            if observation_name != candidate['observation_source'].name:
                raise RuntimeError('observation source does not match descriptor')
        status, item = rest('GET', '/items/' + item_name)
        try:
            body = json.loads(item['state']) if status == 200 else None
        except (ValueError, TypeError, KeyError):
            body = None
        log = run(['docker', 'exec', container, 'cat',
                   '/openhab/userdata/logs/openhab.log']).decode(errors='replace')
        item_receipt = (isinstance(body, dict) and body.get('basis') == candidate['basis']
                        and body.get('fields', {}).get(candidate['field'], {}).get('reason')
                        == 'source_unavailable')
        logger_receipt = candidate['warning'] in log
        if not (item_receipt or logger_receipt):
            print('isolated_item_status=' + str(status), flush=True)
            print('isolated_item_state=' + str(item.get('state') if isinstance(item, dict)
                                                 else type(item).__name__)[:180], flush=True)
            print('isolated_rule_status=' + str(loaded.get('status', {}))[:180], flush=True)
            clues = [line for line in log.splitlines()
                     if any(term in line.lower() for term in
                            (isolated_rule.lower(), 'jsscripting', 'script exception',
                             'script execution', 'evidence', 'error', 'exception'))]
            print('isolated_rule_diagnostic_lines=' + str(len(clues)), flush=True)
            for line in clues[-12:]:
                print('isolated_rule_diagnostic=' + line[:260], flush=True)
            docker_log = run(['docker', 'logs', '--tail', '40', container]).decode(errors='replace')
            for line in docker_log.splitlines()[-10:]:
                print('isolated_container_diagnostic=' + line[:260], flush=True)
            raise RuntimeError('isolated rule body execution receipt absent')
        print('isolated_rule_compiled_trigger_registered_and_runnow_idle=true', flush=True)
        print('isolated_rule_body_receipt=' + ('item' if item_receipt else 'no_jdbc_warning'), flush=True)
        print('isolated_candidate=' + kind, flush=True)
        print('physical_thing_and_jdbc_execution=not_tested', flush=True)
    finally:
        owner = run(['docker', 'inspect', '--format',
            '{{index .Config.Labels "hex.evidence.rule"}}', container]).decode().strip()
        if owner != marker:
            raise RuntimeError('isolated container ownership mismatch')
        run(['docker', 'rm', '-f', '-v', container])
        print('owned_container_and_tmpfs_removed=true', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', choices=sorted(CANDIDATES), default='ac')
    parser.add_argument('--installed-control', action='store_true',
                        help='read-only AC control when its production rule is already installed')
    args = parser.parse_args()
    if args.installed_control and args.candidate != 'ac':
        parser.error('--installed-control is only available for the AC control')
    main(args.candidate, installed_control=args.installed_control)
