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
from persistence_boundary import BoundaryLedger


def main(database=None):
    source = (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes()
    expected = oh.get('/persistence/jdbc')
    if render(expected).encode() != source:
        raise RuntimeError('prepared/live strategy drift')
    boundaries = BoundaryLedger() if database else None
    marker = str(uuid.uuid4())
    command = ['docker', 'run', '-d', '--label', 'hex.persistence.qualification=' + marker,
        '--network', database.network if database else 'none', '--read-only', '--user', '9001:9001', '--cap-drop', 'ALL',
        '--memory', '1536m', '--cpus', '1', '--pids-limit', '256']
    for path, size in [('tmp', '64m'), ('openhab/conf', '64m'), ('openhab/userdata', '512m'), ('openhab/addons', '32m')]:
        command += ['--tmpfs', '/' + path + ':rw,exec,nosuid,nodev,size=' + size + ',uid=9001,gid=9001']
    command += ['-e', 'EXTRA_JAVA_OPTS=-Xmx512m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
        '-e', 'HEX_JDBC_ISOLATED=1' if database else 'HEX_JDBC_ISOLATED=0',
        '--entrypoint', '/bin/sh', isolated.IMAGE, '-c',
        'cp -a /openhab/dist/conf/. /openhab/conf/; cp -a /openhab/dist/userdata/. /openhab/userdata/; '
        'touch /tmp/bootstrap-ready; while [ ! -f /tmp/ready ]; do sleep 1; done; '
        + ('for boot in 1 2; do /openhab/start.sh server; done' if database
           else 'exec /openhab/start.sh server')]
    cid = run(command).decode().strip()
    print('isolated_container=' + cid, flush=True)
    try:
        info = json.loads(run(['docker', 'inspect', cid]))[0]
        host = info['HostConfig']
        assert host['NetworkMode'] == (database.network if database else 'none') and not host['Privileged']
        assert not host.get('Binds') and not host.get('Devices') and not host.get('PortBindings')
        assert info['AppArmorProfile'] == 'docker-default'
        run(['docker', 'exec', cid, 'sh', '-c', 'while [ ! -f /tmp/bootstrap-ready ]; do sleep 1; done'])
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            entry = tarfile.TarInfo('persistence/jdbc.persist'); entry.mode = 0o644; entry.size = len(source)
            tar.addfile(entry, io.BytesIO(source))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/openhab/conf'], archive.getvalue())
        if database:
            database.stage(cid)
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
        if database:
            database.checkpoint(cid, header, 'initial-file')

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
                    return status
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
            if boundaries:
                boundaries.begin('file-to-managed-' + str(cycle + 1), database.previous)
            run(['docker', 'exec', cid, 'mv', active, parked])
            absent_status = wait_for(None)
            if boundaries:
                boundaries.exercise_absence(database, cid, header, absent_status)
            status, _ = request('PUT', managed)
            if status != 201:
                raise RuntimeError('isolated managed provider creation failed: HTTP ' + str(status))
            wait_for(managed)
            if database:
                database.checkpoint(cid, header, 'managed-' + str(cycle + 1))
                boundaries.finish(database.previous)
                boundaries.begin('managed-to-file-' + str(cycle + 1), database.previous)
            status, _ = request('DELETE')
            if status != 200:
                raise RuntimeError('isolated managed provider removal failed')
            absent_status = wait_for(None)
            if boundaries:
                boundaries.exercise_absence(database, cid, header, absent_status)
            run(['docker', 'exec', cid, 'mv', parked, active])
            wait_for(expected)
            if database:
                database.checkpoint(cid, header, 'file-' + str(cycle + 1))
                boundaries.finish(database.previous)
            print('exact_file_managed_file_roundtrip_' + str(cycle + 1) + '=verified', flush=True)
        if database:
            database.restore(cid, header)
            database.power_write(cid, header)
            database.restart(cid, header)
            if database.forecast_verified != 5 or not database.power_restore_verified:
                raise RuntimeError('isolated forecast or power restoration qualification incomplete')
            wait_for(expected)
            boundaries.complete()
            boundaries.forecast_timeseries_behavior = 'verified_with_negative_control_and_restart'
            boundaries.independently_written_power_restore = 'verified_after_jvm_restart'
            print('exact_file_strategy_after_jvm_restart=verified', flush=True)
        else:
            print('database_writes_and_restore=not_tested', flush=True)
        print('whole_host_restart_and_production_cutover=not_tested', flush=True)
    finally:
        try:
            label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.persistence.qualification"}}', cid]).decode().strip()
            if label != marker:
                raise RuntimeError('cleanup ownership mismatch')
            run(['docker', 'rm', '-f', '-v', cid])
            print('owned_container_tmpfs_and_test_identity_removed=true', flush=True)
        except BaseException:
            if boundaries:
                boundaries.suite_complete = False
            raise
        finally:
            if boundaries:
                print('persistence_collection_boundary_report=' +
                      json.dumps(boundaries.report(), sort_keys=True, separators=(',', ':')), flush=True)



if __name__ == '__main__':
    main()
