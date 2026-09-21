#!/usr/bin/env python3
"""Qualify JDBC strategy provider in a disconnected disposable OpenHAB instance."""
import importlib.util
import io
import json
from pathlib import Path
import re
import secrets
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('isolated', Path(__file__).with_name('qualify-extrema-file-provider.py'))
isolated = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolated)
run = isolated.run
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
from persistence_source import render
import openhab_sanity_check as oh


def main():
    source = (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes()
    expected = oh.get('/persistence/jdbc')
    if render(expected).encode() != source:
        raise RuntimeError('prepared/live strategy drift')
    marker = str(uuid.uuid4())
    command = ['docker', 'run', '-d', '--label', 'hex.persistence.qualification=' + marker,
        '--network', 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
        '--memory', '1536m', '--cpus', '1', '--pids-limit', '256']
    for path, size in [('tmp', '64m'), ('openhab/conf', '64m'), ('openhab/userdata', '512m'), ('openhab/addons', '32m')]:
        command += ['--tmpfs', '/' + path + ':rw,exec,nosuid,nodev,size=' + size + ',uid=9001,gid=9001']
    command += ['-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
        '--entrypoint', '/bin/sh', isolated.IMAGE, '-c',
        'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
        'touch /tmp/bootstrap-ready; while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server']
    cid = run(command).decode().strip()
    print('isolated_container=' + cid, flush=True)
    try:
        info = json.loads(run(['docker', 'inspect', cid]))[0]
        host = info['HostConfig']
        assert host['NetworkMode'] == 'none' and not host['Privileged']
        assert not host.get('Binds') and not host.get('Devices') and not host.get('PortBindings')
        assert info['AppArmorProfile'] == 'docker-default'
        run(['docker', 'exec', cid, 'sh', '-c', 'while [ ! -f /tmp/bootstrap-ready ]; do sleep 1; done'])
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            entry = tarfile.TarInfo('persistence/jdbc.persist'); entry.mode = 0o644; entry.size = len(source)
            tar.addfile(entry, io.BytesIO(source))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/openhab/conf'], archive.getvalue())
        run(['docker', 'exec', cid, 'touch', '/tmp/ready'])
        for _ in range(80):
            try:
                run(['docker', 'exec', cid, 'curl', '-fsS', '--max-time', '2', 'http://127.0.0.1:8080/rest/'])
                break
            except RuntimeError:
                time.sleep(3)
        else:
            raise RuntimeError('isolated REST startup timeout')
        time.sleep(20)
        # Ephemeral isolated administrator only; no production credentials copied.
        client = ['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client', '-h', '127.0.0.1',
                  '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        run(client + ['openhab:users add qualification ' + secrets.token_hex(20) + ' administrator'], b'\n')
        output = run(client + ["openhab:users addApiToken qualification qualification ''"], b'\n').decode()
        tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
        if len(tokens) != 1:
            raise RuntimeError('isolated API token response not recognized; secret output withheld')
        header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
        url = 'http://127.0.0.1:8080/rest/persistence/jdbc'
        actual = json.loads(run(['docker', 'exec', '-i', cid, 'curl', '-fsS', '--retry', '5',
            '--retry-all-errors', '--retry-delay', '2', '--max-time', '3', '-H', '@-', url], header))
        expected = {**expected, 'editable': False}
        if actual != expected:
            # Strategy DTO excludes connection settings and credentials.
            raise RuntimeError('strategy DTO mismatch: ' + json.dumps({'expected': expected, 'actual': actual}, sort_keys=True))
        print('exact_file_strategy_dto_verified=true', flush=True)

        def request(method='GET', body=None):
            command = ['docker', 'exec', '-i', cid, 'curl', '-sS', '--max-time', '5',
                '-X', method, '-H', '@-', '-w', '\\n%{http_code}', url]
            if body is not None:
                command += ['-H', 'Content-Type: application/json', '--data-binary', json.dumps(body)]
            output = run(command, header).decode()
            value, status = output.rsplit('\n', 1)
            return int(status), value

        def wait_for(wanted):
            for _ in range(30):
                status, body = request()
                if wanted is None and status == 404:
                    return
                if wanted is not None and status == 200 and json.loads(body) == wanted:
                    return
                time.sleep(1)
            raise RuntimeError('isolated provider transition did not reach exact expected state')

        # Both providers must never overlap: observe absence before each handoff.
        # These files and REST mutations exist only inside this network-none CID.
        active = '/openhab/conf/persistence/jdbc.persist'
        parked = '/tmp/jdbc.persist.parked'
        managed = {**expected, 'editable': True}
        for cycle in range(2):
            status, _ = request('DELETE')
            if status != 405:
                raise RuntimeError('file-owned provider unexpectedly allowed REST deletion')
            run(['docker', 'exec', cid, 'mv', active, parked])
            wait_for(None)
            status, _ = request('PUT', managed)
            if status != 201:
                raise RuntimeError('isolated managed provider creation failed: HTTP ' + str(status))
            wait_for(managed)
            status, _ = request('DELETE')
            if status != 200:
                raise RuntimeError('isolated managed provider removal failed')
            wait_for(None)
            run(['docker', 'exec', cid, 'mv', parked, active])
            wait_for(expected)
            print('exact_file_managed_file_roundtrip_' + str(cycle + 1) + '=verified', flush=True)
        print('database_writes_restore_and_production_cutover=not_tested', flush=True)
    finally:
        label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.persistence.qualification"}}', cid]).decode().strip()
        if label != marker:
            raise RuntimeError('cleanup ownership mismatch')
        run(['docker', 'rm', '-f', '-v', cid])
        print('owned_container_tmpfs_and_test_identity_removed=true', flush=True)


if __name__ == '__main__':
    main()
