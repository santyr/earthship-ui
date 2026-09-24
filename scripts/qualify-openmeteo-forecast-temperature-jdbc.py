#!/usr/bin/env python3
"""Rehearse forecast-temperature state and future-series JDBC recovery.

All synthetic values and OpenHAB/PostgreSQL writes stay in two disposable
containers sharing only an isolated loopback network. Production is read-only.
"""
import importlib.util
import io
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import secrets
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'aqi_jdbc_fixture', ROOT / 'scripts/qualify-openmeteo-aqi-jdbc.py')
aqi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aqi)

SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-temperature.items'
NAMES = ('Forecast_Temp', 'Forecast_Daily_High', 'Forecast_Daily_Low')
SCALARS = {'Forecast_Temp': '68 °F', 'Forecast_Daily_High': '75 °F',
           'Forecast_Daily_Low': '52 °F'}
SERIES = {'Forecast_Temp': (48, 3600, 40),
          'Forecast_Daily_High': (7, 86400, 70),
          'Forecast_Daily_Low': (7, 86400, 30)}


def same_temperature(actual, expected):
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    left, left_unit = actual.rsplit(' ', 1) if ' ' in actual else ('', '')
    right, right_unit = expected.rsplit(' ', 1) if ' ' in expected else ('', '')
    if right_unit != '°F' or left_unit not in ('°F', '°C'):
        return False
    try:
        actual_f = (Decimal(left) if left_unit == '°F'
                    else Decimal(left) * Decimal(9) / Decimal(5) + Decimal(32))
        return abs(actual_f - Decimal(right)) <= Decimal('0.000001')
    except InvalidOperation:
        return False


def stored_temperature(value, unit, expected):
    if unit not in ('°F', '°C'):
        return False
    return same_temperature(str(value) + ' ' + unit, expected)


def item(container, header, name, *, value=None, present=True, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            code, body = aqi.request(container, header, '/items/' + name)
            if not present and code == 404:
                return True
            if present and code == 200:
                row = json.loads(body)
                if row.get('editable') is False and (
                    value is None or same_temperature(row.get('state'), value)
                ):
                    return True
        except (RuntimeError, ValueError):
            pass
        time.sleep(2)
    return False


def database_rows(database, name):
    if name not in NAMES:
        raise ValueError('unrecognized forecast Item')
    identity = aqi.run(['docker', 'exec', database.cid, 'psql', '-U', 'postgres',
        '-d', 'postgres', '-Atc',
        "SELECT itemid FROM public.items WHERE itemname='" + name + "'"]).decode().strip()
    if not re.fullmatch(r'[1-9][0-9]*', identity):
        raise RuntimeError('isolated JDBC Item identity missing: ' + name)
    table = 'item' + identity.zfill(4)
    encoded = aqi.run(['docker', 'exec', database.cid, 'psql', '-U', 'postgres',
        '-d', 'postgres', '-Atc',
        'SELECT coalesce(json_agg(json_build_array(time,value) ORDER BY time)::text,\'[]\') '
        'FROM public.' + table]).decode().strip()
    return json.loads(encoded)


def wait_history(database, name, predicate, seconds=90):
    deadline = time.monotonic() + seconds
    last = []
    while time.monotonic() < deadline:
        try:
            rows = database_rows(database, name)
            last = rows
            if predicate(rows):
                return rows
        except (RuntimeError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError('isolated JDBC history did not meet target: ' + name
                       + ' rows=' + str(last[-3:]))


def assert_series(rows, name, first, stored_unit='°F'):
    count, step, base = SERIES[name]
    first_ms = int(first.timestamp() * 1000)
    future = [row for row in rows if datetime.fromisoformat(row[0]).timestamp() * 1000 >= first_ms]
    if len(future) != count:
        return False
    for index, (stamp, value) in enumerate(future):
        if (int(datetime.fromisoformat(stamp).timestamp() * 1000)
                != first_ms + index * step * 1000):
            return False
        if not (same_temperature(value, str(base + index) + ' °F')
                if isinstance(value, str) and ' ' in value
                else stored_temperature(value, stored_unit,
                                        str(base + index) + ' °F')):
            return False
    return True


def main():
    source = SOURCE.read_bytes()
    if not all(source.count(('Number:Temperature ' + name + ' ').encode()) == 1
               for name in NAMES):
        raise RuntimeError('prepared forecast source changed')
    marker = secrets.token_hex(8)
    with aqi.Database() as database:
        container = None
        try:
            container = aqi.run(['docker', 'run', '-d',
                '--label', 'hex.forecast.temperature.jdbc=' + marker,
                '--network', database.network, '--cap-drop', 'ALL',
                '--pids-limit', '384', '--memory', '2g',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                '-e', 'HEX_JDBC_ISOLATED=1',
                '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
                '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
                'cp -a /openhab/dist/conf/. /openhab/conf/; '
                'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                'touch /tmp/bootstrap-ready; '
                'while [ ! -f /openhab/conf/.forecast-temperature-ready ]; do sleep 1; done; '
                'exec /openhab/start.sh server']).decode().strip()
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "hex.forecast.temperature.jdbc"}}',
                container]).decode().strip()
            if owner != marker:
                raise RuntimeError('isolated OpenHAB container ownership mismatch')
            aqi.run(['docker', 'exec', container, 'sh', '-c',
                     'while [ ! -f /tmp/bootstrap-ready ]; do sleep 1; done'])
            database.stage(container)
            aqi.install(container, 'services/runtime.cfg',
                b'org.openhab.i18n:language=en\norg.openhab.i18n:region=US\n'
                b'org.openhab.i18n:measurementSystem=US\n'
                b'org.openhab.i18n:timezone=America/Denver\n')
            aqi.install(container, 'items/forecast-group.items', b'Group gForecast\n')
            aqi.install(container, 'items/' + SOURCE.name, source)
            aqi.install(container, 'persistence/jdbc.persist',
                (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            aqi.run(['docker', 'exec', container, 'touch',
                     '/openhab/conf/.forecast-temperature-ready'])
            for _ in range(80):
                try:
                    aqi.run(['docker', 'exec', container, 'curl', '-fsS',
                        '--max-time', '2', 'http://127.0.0.1:8080/rest/'])
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
            if not all(item(container, header, name) for name in NAMES):
                raise RuntimeError('isolated forecast file Items unavailable')
            for _ in range(90):
                try:
                    ready = aqi.run(['docker', 'exec', database.cid, 'psql',
                        '-U', 'postgres', '-d', 'postgres', '-Atc',
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name='items')"]).decode().strip()
                    code, body = aqi.request(container, header, '/persistence/jdbc')
                    if ready == 't' and code == 200 and json.loads(body).get('editable') is False:
                        break
                except (RuntimeError, ValueError):
                    pass
                time.sleep(2)
            else:
                raise RuntimeError('isolated JDBC/file strategy not ready')
            observed_units = {}
            for name, value in SCALARS.items():
                code, _ = aqi.request(container, header, '/items/' + name + '/state',
                                      'PUT', value)
                if code != 202 or not item(container, header, name, value=value, seconds=20):
                    observed_code, observed_body = aqi.request(
                        container, header, '/items/' + name)
                    observed = (json.loads(observed_body).get('state')
                        if observed_code == 200 else None)
                    raise RuntimeError('isolated scalar update failed: ' + name
                        + ' status=' + str(code) + ' observed=' + str(observed))
                _, state_body = aqi.request(container, header, '/items/' + name)
                observed_state = json.loads(state_body)['state']
                observed_units[name] = observed_state.rsplit(' ', 1)[-1]
                wait_history(database, name,
                             lambda rows: any(stored_temperature(
                                 row[1], observed_units[name], value) for row in rows))
            print('isolated_numeric_states_persisted=3', flush=True)
            first = (datetime.now(timezone.utc) + timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            probe = aqi.isolated.compile_probe('HexForecastTemperatureProbe', [
                'org.osgi.framework', 'org.openhab.core.events',
                'org.openhab.core.items.events', 'org.openhab.core.library.types',
                'org.openhab.core.types'])
            # The probe and its target exist only in the isolated container.
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode='w') as tar:
                for name, body in (
                    ('hex-forecast-temperature-probe.jar', probe),
                    ('hex-forecast-temperature-first', first.isoformat().encode()),
                ):
                    entry = tarfile.TarInfo(name)
                    entry.mode = 0o600
                    entry.size = len(body)
                    tar.addfile(entry, io.BytesIO(body))
            aqi.run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/tmp'],
                    archive.getvalue())
            installed = aqi.run(client + [
                'bundle:install file:/tmp/hex-forecast-temperature-probe.jar'],
                b'\n').decode()
            matches = re.findall(r'Bundle IDs?:\s*(\d+)', installed)
            if len(matches) != 1:
                raise RuntimeError('isolated forecast probe did not install')
            bundle_id = matches[0]
            try:
                started = aqi.run(client + ['bundle:start ' + bundle_id], b'\n').decode()
                if 'Error executing command' in started:
                    raise RuntimeError('isolated forecast probe did not start')
                for name in NAMES:
                    wait_history(database, name,
                                 lambda rows, target=name: assert_series(
                                     rows, target, first, observed_units[target]))
            finally:
                aqi.run(client + ['bundle:uninstall ' + bundle_id], b'\n')
            before = {name: database_rows(database, name) for name in NAMES}
            print('isolated_future_series_persisted=48,7,7', flush=True)
            aqi.run(['docker', 'exec', container, 'mv',
                '/openhab/conf/items/' + SOURCE.name,
                '/tmp/forecast-temperature.items.parked'])
            if not all(item(container, header, name, present=False, seconds=90)
                       for name in NAMES):
                raise RuntimeError('file Items did not withdraw at hot reload')
            aqi.run(['docker', 'exec', container, 'mv',
                '/tmp/forecast-temperature.items.parked',
                '/openhab/conf/items/' + SOURCE.name])
            if not all(item(container, header, name, value=SCALARS[name], seconds=90)
                       for name in NAMES):
                raise RuntimeError('scalar state did not restore at hot reload')
            if any(database_rows(database, name)[:len(before[name])] != before[name]
                   for name in NAMES):
                raise RuntimeError('JDBC prefix changed at file reload')
            print('hot_reload_states_and_series_preserved=3', flush=True)
            aqi.run(['docker', 'restart', container])
            if not all(item(container, header, name, value=SCALARS[name], seconds=240)
                       for name in NAMES):
                raise RuntimeError('scalar state did not restore at full restart')
            if any(database_rows(database, name)[:len(before[name])] != before[name]
                   for name in NAMES):
                raise RuntimeError('JDBC prefix changed at full restart')
            print('full_restart_states_and_series_preserved=3', flush=True)
        finally:
            if container is not None:
                try:
                    owner = aqi.run(['docker', 'inspect', '--format',
                        '{{index .Config.Labels "hex.forecast.temperature.jdbc"}}',
                        container]).decode().strip()
                except RuntimeError:
                    owner = None
                if owner == marker:
                    aqi.run(['docker', 'rm', '-f', '-v', container])
                    print('owned_isolated_openhab_removed=true', flush=True)
    print('status=passed; production_writes=0; isolated_postgresql_removed=true')


if __name__ == '__main__':
    main()
