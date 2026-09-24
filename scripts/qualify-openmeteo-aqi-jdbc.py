#!/usr/bin/env python3
"""Isolated AQI file-Item/JDBC state recovery; synthetic data never leaves Docker.

Two disposable containers share only their loopback network. They have no
ports, mounts, host database credentials, external network or live writes.
"""
import importlib.util
import argparse
import io
import json
from pathlib import Path
import re
import secrets
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'isolated_jdbc', ROOT / 'scripts/qualify-persistence-jdbc.py')
isolated = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolated)
Database = isolated.Database
run = isolated.run
IMAGE = isolated.provider.isolated.IMAGE
ITEM = 'Current_US_AQI'
VALUE = '42.5'  # Disposable test value, never sent to production.
TEST_VALUES = {'current': '42.5', 'forecast': 'REFRESH'}
CANDIDATES = {
    'current': ('Current_US_AQI', ROOT / 'openhab/file-config/items/openmeteo-current-aqi.items'),
    'forecast': ('Forecast_AQI', ROOT / 'openhab/file-config/items/openmeteo-forecast-aqi.items'),
}


def install(container, name, body):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        member = tarfile.TarInfo(name)
        member.mode = 0o644
        member.size = len(body)
        archive.addfile(member, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/openhab/conf'],
        output.getvalue())


def request(container, header, path, method='GET', body=None, content_type='text/plain'):
    command = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '6',
               '-X', method, '-H', '@-', '-w', '\n%{http_code}',
               'http://127.0.0.1:8080/rest' + path]
    if body is not None:
        command += ['-H', 'Content-Type: ' + content_type, '--data-binary', body]
    result = run(command, header).decode()
    payload, code = result.rsplit('\n', 1)
    return int(code), payload


def wait_item(container, header, *, present, value=None, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            code, payload = request(container, header, '/items/' + ITEM)
            if not present and code == 404:
                return True
            if present and code == 200:
                item = json.loads(payload)
                if item.get('editable') is False and (value is None or item.get('state') == value):
                    return True
        except (RuntimeError, ValueError):
            pass  # Bounded startup/reload retry; never infer success from an error.
        time.sleep(2)
    return False


def rows(container, header):
    code, payload = request(container, header, '/persistence/items/' + ITEM + '?serviceId=jdbc')
    if code != 200:
        raise RuntimeError('isolated JDBC history unavailable')
    result = json.loads(payload).get('data')
    if not isinstance(result, list):
        raise RuntimeError('isolated JDBC history malformed')
    return result


def main():
    global ITEM, VALUE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', choices=tuple(CANDIDATES), default='current')
    args = parser.parse_args()
    ITEM, source = CANDIDATES[args.candidate]
    VALUE = TEST_VALUES[args.candidate]
    marker = secrets.token_hex(8)
    with Database() as database:
        container = None
        try:
            container = run(['docker', 'run', '-d',
                             '--label', 'hex.aqi.jdbc=' + marker,
                             '--network', database.network,
                             '--cap-drop', 'ALL',
                             '--pids-limit', '384', '--memory', '2g',
                             '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                             '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
                             '--entrypoint', '/bin/sh', IMAGE, '-c',
                             'cp -a /openhab/dist/conf/. /openhab/conf/; '
                             'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                             'touch /tmp/bootstrap-ready; '
                             'while [ ! -f /openhab/conf/.aqi-jdbc-ready ]; do sleep 1; done; '
                             'exec /openhab/start.sh server']).decode().strip()
            owner = run(['docker', 'inspect', '--format',
                         '{{index .Config.Labels "hex.aqi.jdbc"}}', container]).decode().strip()
            if owner != marker:
                raise RuntimeError('isolated OpenHAB container ownership mismatch')
            run(['docker', 'exec', container, 'sh', '-c',
                 'while [ ! -f /tmp/bootstrap-ready ]; do sleep 1; done'])
            database.stage(container)
            install(container, 'items/' + source.name, source.read_bytes())
            install(container, 'persistence/jdbc.persist',
                    (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            run(['docker', 'exec', container, 'touch', '/openhab/conf/.aqi-jdbc-ready'])
            for _ in range(80):
                try:
                    run(['docker', 'exec', container, 'curl', '-fsS', '--max-time', '2',
                         'http://127.0.0.1:8080/rest/'])
                    break
                except RuntimeError:
                    time.sleep(3)
            else:
                raise RuntimeError('isolated OpenHAB REST startup timeout')
            # REST can answer before Karaf's local console accepts user commands.
            # The established JDBC provider harness uses the same settle window.
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                      '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                          + ' administrator'], b'\n')
            output = run(client + ["openhab:users addApiToken qualification qualification ''"],
                         b'\n').decode()
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
            if len(tokens) != 1:
                raise RuntimeError('isolated API token unavailable; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
            if not wait_item(container, header, present=True):
                raise RuntimeError('isolated file AQI Item not available')
            for _ in range(90):
                ready = run(['docker', 'exec', database.cid, 'psql', '-U', 'postgres',
                             '-d', 'postgres', '-Atc',
                             "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                             "WHERE table_schema='public' AND lower(table_name)='items')"]).decode().strip()
                try:
                    strategy_code, strategy_body = request(container, header,
                                                           '/persistence/jdbc')
                    strategy_ready = (strategy_code == 200 and
                                      json.loads(strategy_body).get('editable') is False)
                except (RuntimeError, ValueError):
                    strategy_ready = False
                if ready == 't' and strategy_ready:
                    break
                time.sleep(2)
            else:
                raise RuntimeError('isolated JDBC mapping or file strategy not ready')
            print(json.dumps({'phase': 'jdbc_ready', 'mapping_table': True,
                              'file_strategy': True}), flush=True)
            code, _ = request(container, header, '/items/' + ITEM + '/state', 'PUT', VALUE)
            if code != 202:
                raise RuntimeError('isolated AQI state update refused')
            if not wait_item(container, header, present=True, value=VALUE):
                raise RuntimeError('isolated AQI state did not update')
            before = None
            for _ in range(45):
                try:
                    found = rows(container, header)
                    if found and found[-1].get('state') == VALUE:
                        before = found
                        break
                except (RuntimeError, ValueError):
                    pass
                time.sleep(2)
            if before is None:
                raise RuntimeError('isolated AQI state did not persist in JDBC')
            print(json.dumps({'phase': 'jdbc_write', 'history_rows': len(before)}), flush=True)
            run(['docker', 'exec', container, 'mv',
                 '/openhab/conf/items/' + source.name, '/tmp/aqi.items.parked'])
            if not wait_item(container, header, present=False, seconds=90):
                raise RuntimeError('isolated AQI file Item did not disappear')
            run(['docker', 'exec', container, 'mv', '/tmp/aqi.items.parked',
                 '/openhab/conf/items/' + source.name])
            hot_restore = wait_item(container, header, present=True, value=VALUE, seconds=45)
            if rows(container, header)[:len(before)] != before:
                raise RuntimeError('AQI JDBC history prefix changed across hot reload')
            print(json.dumps({'phase': 'file_reload', 'state_restored': hot_restore,
                              'history_prefix_preserved': True}), flush=True)
            run(['docker', 'restart', container])
            if not wait_item(container, header, present=True, value=VALUE, seconds=240):
                raise RuntimeError('AQI state did not restore after isolated JVM restart')
            after = rows(container, header)
            if after[:len(before)] != before:
                raise RuntimeError('AQI JDBC history prefix changed across restart')
            print(json.dumps({'phase': 'full_restart', 'state_restored': True,
                              'history_prefix_preserved': True}), flush=True)
        finally:
            if container is not None:
                owner = run(['docker', 'inspect', '--format',
                             '{{index .Config.Labels "hex.aqi.jdbc"}}', container],
                            ).decode().strip()
                if owner != marker:
                    raise RuntimeError('isolated OpenHAB cleanup ownership mismatch')
                run(['docker', 'rm', '-f', '-v', container])
                print('owned_isolated_openhab_removed=true', flush=True)
    print(json.dumps({'status': 'passed', 'production_writes': 0,
                      'isolated_postgresql_removed': True}), flush=True)


if __name__ == '__main__':
    main()
