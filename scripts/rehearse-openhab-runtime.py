#!/usr/bin/env python3
"""Integrated boot using an existing owned, networkless, read-only restore DB."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from private_receipt import save_private_json

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('rehearse-openhab-recovery.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def canonical_definition(endpoint, entry, fields):
    definition = {key: entry.get(key) for key in fields}
    for key in ('tags', 'groupNames'):
        if definition.get(key) is not None:
            definition[key] = sorted(definition[key])
    if endpoint == 'things' and definition.get('channels') is not None:
        definition['channels'] = sorted(definition['channels'], key=lambda channel: channel['uid'])
    return definition


def main():
    os.umask(0o077)
    directory = Path(sys.argv[1]).resolve(strict=True)
    if directory.parent != r.ROOT or not directory.name.startswith('runtime-recovery-'):
        raise ValueError('private recovery directory required')
    pg = sys.argv[2]
    inspection = json.loads(subprocess.check_output(['docker', 'inspect', pg]))[0]
    marker = inspection['Config']['Labels'].get('hex.recovery')
    if not marker or inspection['HostConfig']['NetworkMode'] != 'none':
        raise ValueError('owned networkless restore database required')
    pg = inspection['Id']
    receipt = Path(tempfile.mkdtemp(prefix='integrated-run-', dir=directory))
    print('integrated_receipt=' + str(receipt), flush=True)
    log = (receipt / 'commands-private.log').open('xb')
    def run(args, data=None, stdin=None):
        result = subprocess.run(args, input=data, stdin=stdin, stdout=subprocess.PIPE, stderr=log, timeout=600)
        if result.returncode:
            raise RuntimeError('isolated command failed: ' + args[0])
        return result.stdout
    readonly = run(['docker', 'exec', pg, 'psql', '-X', '-At', '-U', 'postgres', '-d', 'openhab',
                    '-c', 'SHOW default_transaction_read_only;']).decode().strip()
    if readonly != 'on' and '--allow-isolated-writes' not in sys.argv[3:]:
        raise RuntimeError('restore database must be read-only')
    item_id = int(run(['docker', 'exec', pg, 'psql', '-X', '-At', '-U', 'postgres', '-d', 'openhab',
                       '-c', "SELECT itemid FROM public.items WHERE itemname='Energy_Analytics_JSON';"]).decode().strip())
    if item_id <= 0:
        raise RuntimeError('invalid observational Item mapping')
    expected_state_hash = run(['docker', 'exec', pg, 'psql', '-X', '-At', '-U', 'postgres', '-d', 'openhab',
                               '-c', "SELECT encode(sha256(convert_to(value,'UTF8')),'hex') FROM public.item"
                               + format(item_id, '04d') + ' ORDER BY time DESC LIMIT 1;']).decode().strip()
    command = ['docker', 'run', '-d', '--label', 'hex.integrated.recovery=' + marker,
               '--network', 'container:' + pg, '--read-only', '--user', '9001:9001',
               '--cap-drop', 'ALL', '--memory', '4g', '--cpus', '1', '--pids-limit', '384']
    for path, size in [('/tmp', '128m'), ('/openhab/conf', '64m'), ('/openhab/userdata', '1536m'),
                       ('/openhab/addons', '800m'), ('/etc/openhab', '8m'), ('/var/lib/openhab', '8m'),
                       ('/usr/share/openhab', '8m'), ('/var/log/openhab', '128m')]:
        command += ['--tmpfs', path + ':rw,exec,nosuid,nodev,size=' + size + ',uid=9001,gid=9001']
    command += ['-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
                '--entrypoint', '/bin/sh', r.IMAGE, '-c',
                'while [ ! -f /tmp/ready ]; do sleep 1; done; '
                'mkdir -p /openhab/userdata/tmp /openhab/userdata/cache /openhab/userdata/logs; '
                'for f in /openhab/conf/* /openhab/conf/.[!.]*; do [ ! -e "$f" ] || ln -s "$f" /etc/openhab/; done; '
                'for f in /openhab/userdata/* /openhab/userdata/.[!.]*; do [ ! -e "$f" ] || ln -s "$f" /var/lib/openhab/; done; '
                'for f in /openhab/*; do ln -s "$f" /usr/share/openhab/; done; '
                'exec /openhab/start.sh server']
    cid = run(command).decode().strip()
    result = {'status': 'incomplete', 'database_read_only': readonly == 'on', 'hardware_connected': False,
              'host_path_aliases': True, 'container': cid}
    try:
        isolated = json.loads(run(['docker', 'inspect', cid]))[0]
        host = isolated['HostConfig']
        assert host['NetworkMode'] == 'container:' + pg
        assert not host['Privileged'] and not host.get('Binds') and not host.get('Devices') and not host.get('PortBindings')
        assert isolated['AppArmorProfile'] == 'docker-default'
        for name in ('conf', 'userdata', 'addons'):
            with (directory / (name + '.tar')).open('rb') as f:
                run(['docker', 'exec', '-i', cid, 'tar', '--no-same-owner', '--no-same-permissions',
                     '-xf', '-', '-C', '/openhab/' + name], stdin=f)
        run(['docker', 'exec', cid, 'touch', '/tmp/ready'])
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'openhab/scripts'))
        import openhab_sanity_check as sanity
        header = ('Authorization: Bearer ' + sanity.token() + '\n').encode()
        for _ in range(100):
            p = subprocess.run(['docker', 'exec', '-i', cid, 'curl', '-fsS', '--max-time', '3',
                                '-H', '@-', 'http://127.0.0.1:8080/rest/items'], input=header,
                               stdout=subprocess.PIPE, stderr=log)
            if p.returncode == 0:
                result['items'] = len(json.loads(p.stdout))
                break
            time.sleep(3)
        else:
            raise RuntimeError('integrated runtime startup timeout')
        # REST can disappear during feature installation; do not accept early state.
        time.sleep(90)
        for _ in range(60):
            try:
                state_data = json.loads(run(['docker', 'exec', '-i', cid, 'curl', '-fsS', '--max-time', '10',
                                             '-H', '@-', 'http://127.0.0.1:8080/rest/items'], data=header))
            except RuntimeError:
                time.sleep(5)
                continue
            if any(x.get('state') not in (None, 'NULL', 'UNDEF') for x in state_data):
                break
            time.sleep(5)
        for endpoint in ('items', 'things', 'rules', 'links'):
            data = json.loads(run(['docker', 'exec', '-i', cid, 'curl', '-fsS', '--retry', '5',
                                   '--retry-all-errors', '--retry-delay', '3', '--max-time', '30',
                                   '-H', '@-', 'http://127.0.0.1:8080/rest/' + endpoint], data=header))
            result[endpoint] = len(data)
            fields = {
                'items': ('name', 'type', 'label', 'category', 'tags', 'groupNames', 'editable'),
                'things': ('UID', 'thingTypeUID', 'bridgeUID', 'label', 'configuration', 'channels', 'editable'),
                'rules': ('uid', 'name', 'description', 'tags', 'configuration', 'triggers', 'conditions', 'actions'),
                'links': ('itemName', 'channelUID', 'configuration', 'editable'),
            }[endpoint]
            def index(entries):
                def identity(entry):
                    return (entry.get('itemName', '') + ' -> ' + entry.get('channelUID', '')) if endpoint == 'links' else entry[fields[0]]
                return {identity(x): canonical_definition(endpoint, x, fields) for x in entries}
            source_definitions = index(sanity.get('/' + endpoint))
            restored_definitions = index(data)
            result[endpoint + '_definition_mismatches'] = sorted(k for k in source_definitions.keys() | restored_definitions.keys()
                if source_definitions.get(k) != restored_definitions.get(k))
            mismatches = result[endpoint + '_definition_mismatches']
            if mismatches:
                result[endpoint + '_mismatched_fields'] = {k: [field for field in fields
                    if source_definitions.get(k, {}).get(field) != restored_definitions.get(k, {}).get(field)] for k in mismatches}
                private = {k: {'source': source_definitions.get(k), 'restored': restored_definitions.get(k)} for k in mismatches}
                save_private_json(receipt, endpoint + '-differences-private.json', private)
            if endpoint == 'items':
                result['items_with_restored_or_computed_state'] = sum(x.get('state') not in (None, 'NULL', 'UNDEF') for x in data)
                state = next((x.get('state', '') for x in data if x['name'] == 'Energy_Analytics_JSON'), '')
                result['observational_state_matches_backup'] = hashlib.sha256(state.encode()).hexdigest() == expected_state_hash
            if endpoint == 'rules':
                result['uninitialized_rules'] = [x['uid'] for x in data if x.get('status', {}).get('status') == 'UNINITIALIZED']
        services = json.loads(run(['docker', 'exec', '-i', cid, 'curl', '-fsS', '--max-time', '30',
                                   '-H', '@-', 'http://127.0.0.1:8080/rest/persistence'], data=header))
        result['persistence_services'] = [x.get('id') for x in services]
        result['status'] = 'integrated_boot_tested' if result.get('observational_state_matches_backup') and 'jdbc' in result['persistence_services'] else 'booted_without_qualified_state_recovery'
    finally:
        with (receipt / 'runtime-private.log').open('xb') as f:
            subprocess.run(['docker', 'logs', cid], stdout=f, stderr=f)
            subprocess.run(['docker', 'exec', cid, 'sh', '-c',
                            'for f in /var/log/openhab/openhab.log /openhab/userdata/logs/openhab.log; do '
                            'if [ -f "$f" ]; then tail -n 3000 "$f"; fi; done'], stdout=f, stderr=f)
        label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.integrated.recovery"}}', cid]).decode().strip()
        if label != marker:
            raise RuntimeError('cleanup ownership mismatch')
        run(['docker', 'rm', '-f', '-v', cid])
        result['container_removed'] = True
        save_private_json(receipt, 'report.json', result)
        log.close()
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
