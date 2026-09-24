#!/usr/bin/env python3
"""Isolated JDBC recovery for all file-owned forecast JSON Items.

Only disposable OpenHAB/PostgreSQL containers receive synthetic values. No
production state, credentials, network, ports, or host volumes enter the test.
"""
import importlib.util
import json
from pathlib import Path
import re
import secrets
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'aqi_qualification', ROOT / 'scripts/qualify-openmeteo-aqi-jdbc.py')
aqi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aqi)

ITEMS = {
    'Forecast_Hourly_JSON': json.dumps({'hourly': [{'time': '2026-09-23T14:00', 'temperature': 71.5}]}),
    'Forecast_Daily_JSON': json.dumps({'daily': [{'date': '2026-09-24', 'high': 74, 'low': 48}]}),
    'Forecast_10Day_JSON': json.dumps({'days': [{'day': i, 'detail': 'forecast ' + 'x' * 3500}
                                           for i in range(10)]}),
}


def same_state(actual, expected):
    return actual == expected


def item(container, header, name, *, present=True, value=None, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            code, payload = aqi.request(container, header, '/items/' + name)
            if not present and code == 404:
                return True
            if present and code == 200:
                state = json.loads(payload)
                if state.get('editable') is False and (value is None or same_state(state.get('state'), value)):
                    return True
        except (RuntimeError, ValueError):
            pass
        time.sleep(2)
    return False


def history(container, header, name):
    code, payload = aqi.request(container, header,
                                '/persistence/items/' + name + '?serviceId=jdbc')
    if code != 200:
        raise RuntimeError('isolated JDBC history unavailable for ' + name)
    rows = json.loads(payload).get('data')
    if not isinstance(rows, list):
        raise RuntimeError('isolated JDBC history malformed for ' + name)
    return rows


def main(items=ITEMS, source_path=ROOT / 'openhab/file-config/items/forecast-json.items',
         types=None, setup_sources=()):
    types = types or {name: 'String' for name in items}
    definitions = {}
    for name in items:
        live = oh.get('/items/' + name + '?metadata=.*')
        if live.get('editable') not in (True, False) or live.get('type') != types[name]:
            raise RuntimeError('production Item preflight failed: ' + name)
        definitions[name] = {key: live[key] for key in ('name', 'type', 'label')}
        for key in ('category', 'tags', 'groupNames'):
            if key in live:
                definitions[name][key] = live[key]
    marker = secrets.token_hex(8)
    with aqi.Database() as database:
        container = None
        try:
            container = aqi.run(['docker', 'run', '-d',
                '--label', 'hex.forecast.jdbc=' + marker,
                '--network', database.network, '--cap-drop', 'ALL',
                '--pids-limit', '384', '--memory', '2g',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
                '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
                'cp -a /openhab/dist/conf/. /openhab/conf/; '
                'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                'touch /tmp/bootstrap-ready; '
                'while [ ! -f /openhab/conf/.forecast-jdbc-ready ]; do sleep 1; done; '
                'exec /openhab/start.sh server']).decode().strip()
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "hex.forecast.jdbc"}}', container]).decode().strip()
            if owner != marker:
                raise RuntimeError('isolated OpenHAB ownership mismatch')
            aqi.run(['docker', 'exec', container, 'sh', '-c',
                     'while [ ! -f /tmp/bootstrap-ready ]; do sleep 1; done'])
            database.stage(container)
            for relative_path, body in setup_sources:
                aqi.install(container, relative_path, body)
            aqi.install(container, 'items/' + source_path.name,
                        source_path.read_bytes())
            aqi.install(container, 'persistence/jdbc.persist',
                        (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            aqi.run(['docker', 'exec', container, 'touch',
                     '/openhab/conf/.forecast-jdbc-ready'])
            for _ in range(80):
                try:
                    aqi.run(['docker', 'exec', container, 'curl', '-fsS', '--max-time', '2',
                             'http://127.0.0.1:8080/rest/'])
                    break
                except RuntimeError:
                    time.sleep(3)
            else:
                raise RuntimeError('isolated OpenHAB REST startup timeout')
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                      '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            aqi.run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                              + ' administrator'], b'\n')
            output = aqi.run(client + ["openhab:users addApiToken qualification qualification ''"],
                             b'\n').decode()
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
            if len(tokens) != 1:
                raise RuntimeError('isolated API token unavailable; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
            if not all(item(container, header, name) for name in items):
                raise RuntimeError('isolated file forecast Items not available')
            for _ in range(90):
                ready = aqi.run(['docker', 'exec', database.cid, 'psql', '-U', 'postgres',
                                 '-d', 'postgres', '-Atc',
                                 "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                                 "WHERE table_schema='public' AND lower(table_name)='items')"]).decode().strip()
                try:
                    code, payload = aqi.request(container, header, '/persistence/jdbc')
                    strategy_ready = code == 200 and json.loads(payload).get('editable') is False
                except (RuntimeError, ValueError):
                    strategy_ready = False
                if ready == 't' and strategy_ready:
                    break
                time.sleep(2)
            else:
                raise RuntimeError('isolated JDBC mapping or strategy not ready')
            print('isolated_jdbc_and_file_strategy_ready=true', flush=True)
            before = {}
            for name, value in items.items():
                code, _ = aqi.request(container, header, '/items/' + name + '/state', 'PUT', value)
                if code != 202 or not item(container, header, name, value=value):
                    raise RuntimeError('isolated state write failed for ' + name)
                for _ in range(45):
                    try:
                        rows = history(container, header, name)
                        if rows and same_state(rows[-1].get('state'), value):
                            before[name] = rows
                            break
                    except (RuntimeError, ValueError):
                        pass
                    time.sleep(2)
                if name not in before:
                    raise RuntimeError('isolated JDBC write failed for ' + name)
            print('synthetic_states_persisted=' + str(len(items)), flush=True)
            aqi.run(['docker', 'exec', container, 'mv',
                     '/openhab/conf/items/' + source_path.name, '/tmp/forecast.items.parked'])
            if not all(item(container, header, name, present=False, seconds=90)
                       for name in items):
                raise RuntimeError('file Items did not withdraw cleanly')
            for name, definition in definitions.items():
                code, _ = aqi.request(container, header, '/items/' + name, 'PUT',
                                      json.dumps(definition), 'application/json')
                if code not in (200, 201):
                    raise RuntimeError('isolated managed restore refused: ' + name)
            deadline = time.monotonic() + 90
            for name, value in items.items():
                while time.monotonic() < deadline:
                    code, payload = aqi.request(container, header, '/items/' + name)
                    if code == 200:
                        actual = json.loads(payload)
                        if actual.get('editable') is True and same_state(actual.get('state'), value):
                            break
                    time.sleep(2)
                else:
                    raise RuntimeError('managed rollback state not restored: ' + name)
                if history(container, header, name)[:len(before[name])] != before[name]:
                    raise RuntimeError('history changed at managed rollback: ' + name)
            for name in items:
                code, _ = aqi.request(container, header, '/items/' + name, 'DELETE')
                if code not in (200, 202, 204) or not item(container, header, name,
                                                             present=False, seconds=60):
                    raise RuntimeError('isolated managed Item withdrawal failed: ' + name)
            print('managed_rollback_and_forward_transfer_restored=true', flush=True)
            aqi.run(['docker', 'exec', container, 'mv', '/tmp/forecast.items.parked',
                     '/openhab/conf/items/' + source_path.name])
            for name, value in items.items():
                if not item(container, header, name, value=value, seconds=90):
                    raise RuntimeError('state not restored at hot file reload: ' + name)
                if history(container, header, name)[:len(before[name])] != before[name]:
                    raise RuntimeError('history prefix changed at file reload: ' + name)
            print('hot_file_reload_history_prefix_preserved=true', flush=True)
            aqi.run(['docker', 'restart', container])
            for name, value in items.items():
                if not item(container, header, name, value=value, seconds=240):
                    raise RuntimeError('state not restored at JVM restart: ' + name)
                if history(container, header, name)[:len(before[name])] != before[name]:
                    raise RuntimeError('history prefix changed at restart: ' + name)
            print('full_restart_states_and_history_restored=' + str(len(items)), flush=True)
        finally:
            if container is not None:
                owner = aqi.run(['docker', 'inspect', '--format',
                    '{{index .Config.Labels "hex.forecast.jdbc"}}', container]).decode().strip()
                if owner != marker:
                    raise RuntimeError('isolated OpenHAB cleanup ownership mismatch')
                aqi.run(['docker', 'rm', '-f', '-v', container])
                print('owned_isolated_openhab_removed=true', flush=True)
    print(json.dumps({'status': 'passed', 'production_writes': 0,
                      'isolated_postgresql_removed': True}), flush=True)


if __name__ == '__main__':
    main()
