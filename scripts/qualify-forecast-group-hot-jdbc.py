#!/usr/bin/env python3
"""Qualify gForecast hot handoff against isolated JDBC forecast-series writes.

Synthetic future series are posted before, during and after the Group provider
gap, then after managed rollback. Two disconnected disposable containers are
removed on exit. No production Item, Group, database or service is changed.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import re
import secrets
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_temperature_jdbc', ROOT / 'scripts/qualify-openmeteo-forecast-temperature-jdbc.py')
temperature = importlib.util.module_from_spec(spec)
spec.loader.exec_module(temperature)
aqi = temperature.aqi

GROUP_SOURCE = ROOT / 'openhab/file-config/items/forecast-group.items'
MEMBER_SOURCES = tuple(ROOT / 'openhab/file-config/items' / name for name in (
    'openmeteo-forecast-temperature.items',
    'openmeteo-forecast-meteorology.items',
    'openmeteo-forecast-daily.items',
))
EXPECTED_MEMBERS = frozenset((
    'Forecast_Temp', 'Forecast_Daily_High', 'Forecast_Daily_Low',
    'Forecast_Cloudiness', 'Forecast_Radiation', 'Forecast_PrecipProb',
    'Forecast_Daily_PrecipSum', 'Forecast_Daily_PrecipProbMax',
    'Forecast_Daily_WeatherCode', 'Forecast_Daily_UVIndex',
))
LABEL = 'hex.forecast.group.hot.jdbc'


def wait(predicate, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except (RuntimeError, ValueError, KeyError):
            pass
        time.sleep(2)
    return False


def get(container, header, path):
    code, body = aqi.request(container, header, path)
    return (code, json.loads(body)) if code == 200 else (code, None)


def group_state(container, header, *, file_owned):
    code, row = get(container, header, '/items/gForecast?metadata=.*')
    if code != 200 or row.get('editable') is not (not file_owned):
        return False
    if (row.get('type') != 'Group' or row.get('label') != 'Forecast Items'
            or row.get('tags') != ['forecast'] or row.get('groupNames') != []):
        return False
    code, rows = get(container, header, '/items?recursive=false')
    if code != 200:
        return False
    members = {item['name'] for item in rows
               if 'gForecast' in item.get('groupNames', [])}
    return members == EXPECTED_MEMBERS


def group_absent_members_present(container, header):
    code, _ = get(container, header, '/items/gForecast')
    if code != 404:
        return False
    code, rows = get(container, header, '/items?recursive=false')
    return (code == 200 and
            {item['name'] for item in rows
             if 'gForecast' in item.get('groupNames', [])} == EXPECTED_MEMBERS)


def store_tmp(container, files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        for name, body in files.items():
            member = tarfile.TarInfo(name)
            member.mode = 0o600
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    aqi.run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/tmp'],
            output.getvalue())


def publish_probe(container, client, archive, first):
    store_tmp(container, {
        'hex-forecast-temperature-probe.jar': archive,
        'hex-forecast-temperature-first': first.isoformat().replace('+00:00', 'Z').encode(),
    })
    installed = aqi.run(client + [
        'bundle:install file:/tmp/hex-forecast-temperature-probe.jar'], b'\n').decode()
    matches = re.findall(r'Bundle IDs?:\s*(\d+)', installed)
    if len(matches) != 1:
        raise RuntimeError('isolated forecast probe did not install')
    bundle_id = matches[0]
    try:
        started = aqi.run(client + ['bundle:start ' + bundle_id], b'\n').decode()
        if 'Error executing command' in started:
            raise RuntimeError('isolated forecast probe did not start')
    finally:
        aqi.run(client + ['bundle:uninstall ' + bundle_id], b'\n')


def check_series(database, first, units, previous, *, seconds=90):
    current = {}
    for name in temperature.NAMES:
        rows = temperature.wait_history(database, name,
            lambda values, target=name: temperature.assert_series(
                values, target, first, units[target]), seconds=seconds)
        if previous and Counter(map(tuple, previous[name])) - Counter(map(tuple, rows)):
            raise RuntimeError('forecast JDBC prefix changed: ' + name)
        current[name] = rows
    return current


def gap_row_counts(database, first):
    counts = {}
    for name in temperature.NAMES:
        count, step, _ = temperature.SERIES[name]
        last = first + timedelta(seconds=count * step)
        counts[name] = sum(first <= datetime.fromisoformat(row[0]) < last
                           for row in temperature.database_rows(database, name))
    return counts


def main():
    if (GROUP_SOURCE.read_bytes().count(b'Group gForecast "Forecast Items" ["forecast"]') != 1
            or sum(source.read_bytes().count(b'(gForecast)') for source in MEMBER_SOURCES) != 10):
        raise RuntimeError('prepared Group/member sources changed')
    marker = secrets.token_hex(8)
    with aqi.Database() as database:
        container = None
        try:
            container = aqi.run(['docker', 'run', '-d', '--label', LABEL + '=' + marker,
                '--network', database.network, '--cap-drop', 'ALL',
                '--pids-limit', '384', '--memory', '2g',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                '-e', 'HEX_JDBC_ISOLATED=1',
                '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver',
                '--entrypoint', '/bin/sh', aqi.IMAGE, '-c',
                'cp -a /openhab/dist/conf/. /openhab/conf/; '
                'cp -a /openhab/dist/userdata/. /openhab/userdata/; '
                'touch /tmp/bootstrap-ready; '
                'while [ ! -f /openhab/conf/.forecast-group-jdbc-ready ]; do sleep 1; done; '
                'exec /openhab/start.sh server']).decode().strip()
            owner = aqi.run(['docker', 'inspect', '--format',
                '{{index .Config.Labels "' + LABEL + '"}}', container]).decode().strip()
            if owner != marker:
                raise RuntimeError('isolated OpenHAB ownership mismatch')
            aqi.run(['docker', 'exec', container, 'sh', '-c',
                     'while [ ! -f /tmp/bootstrap-ready ]; do sleep 1; done'])
            database.stage(container)
            aqi.install(container, 'services/runtime.cfg',
                b'org.openhab.i18n:language=en\norg.openhab.i18n:region=US\n'
                b'org.openhab.i18n:measurementSystem=US\n'
                b'org.openhab.i18n:timezone=America/Denver\n')
            aqi.install(container, 'persistence/jdbc.persist',
                (ROOT / 'openhab/file-config/persistence/jdbc.persist').read_bytes())
            aqi.run(['docker', 'exec', container, 'touch',
                     '/openhab/conf/.forecast-group-jdbc-ready'])
            if not wait(lambda: aqi.run(['docker', 'exec', container, 'curl', '-fsS',
                    '--max-time', '2', 'http://127.0.0.1:8080/rest/']) is not None, 240):
                raise RuntimeError('isolated OpenHAB REST startup timeout')
            time.sleep(20)
            client = ['docker', 'exec', '-i', container, '/openhab/runtime/bin/client',
                '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
            aqi.run(client + ['openhab:users add qualification ' + secrets.token_hex(20)
                              + ' administrator'], b'\n')
            output = aqi.run(client + [
                "openhab:users addApiToken qualification qualification ''"], b'\n').decode()
            tokens = re.findall(r'oh\.[A-Za-z0-9._-]+', output)
            if len(tokens) != 1:
                raise RuntimeError('isolated API token unavailable; output withheld')
            header = ('Authorization: Bearer ' + tokens[0] + '\n').encode()
            code, _ = aqi.request(container, header, '/items/gForecast', 'PUT',
                json.dumps({'type': 'Group', 'name': 'gForecast',
                            'label': 'Forecast Items', 'tags': ['forecast']}),
                'application/json')
            if code not in (200, 201):
                raise RuntimeError('isolated managed Group creation refused')
            for source in MEMBER_SOURCES:
                aqi.install(container, 'items/' + source.name, source.read_bytes())
            if not wait(lambda: group_state(container, header, file_owned=False), 240):
                raise RuntimeError('managed Group/file-owned member baseline failed')
            if not wait(lambda: get(container, header, '/persistence/jdbc')[0] == 200,
                        120):
                raise RuntimeError('isolated JDBC strategy unavailable')
            units = {}
            for name, value in temperature.SCALARS.items():
                code, _ = aqi.request(container, header, '/items/' + name + '/state',
                                      'PUT', value, 'text/plain')
                if code != 202 or not temperature.item(container, header, name,
                                                       value=value, seconds=30):
                    raise RuntimeError('isolated scalar state failed: ' + name)
                units[name] = get(container, header, '/items/' + name)[1]['state'].rsplit(' ', 1)[-1]
            probe = aqi.isolated.compile_probe(temperature.PROBE_CLASS, [
                'org.osgi.framework', 'org.openhab.core.events',
                'org.openhab.core.items.events', 'org.openhab.core.library.types',
                'org.openhab.core.types'])
            first = (datetime.now(timezone.utc) + timedelta(days=7)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            previous = {}
            publish_probe(container, client, probe, first)
            previous = check_series(database, first, units, previous)
            print('before_handoff_forecast_series_persisted=true', flush=True)
            code, _ = aqi.request(container, header, '/items/gForecast', 'DELETE')
            if code not in (200, 202, 204) or not wait(
                    lambda: group_absent_members_present(container, header), 90):
                raise RuntimeError('managed Group deletion lost file-owned membership')
            gap_first = first + timedelta(days=30)
            publish_probe(container, client, probe, gap_first)
            try:
                previous = check_series(database, gap_first, units, previous,
                                        seconds=20)
                gap_persisted = True
            except RuntimeError:
                gap_persisted = False
            print('provider_gap_forecast_series_persisted=' +
                  str(gap_persisted).lower(), flush=True)
            aqi.install(container, 'items/' + GROUP_SOURCE.name, GROUP_SOURCE.read_bytes())
            if not wait(lambda: group_state(container, header, file_owned=True), 90):
                raise RuntimeError('file Group failed with file-owned members')
            file_first = first + timedelta(days=60)
            publish_probe(container, client, probe, file_first)
            previous = check_series(database, file_first, units, previous)
            print('file_group_forecast_series_persisted=true', flush=True)
            print('gap_rows_after_file_group=' +
                  json.dumps(gap_row_counts(database, gap_first), sort_keys=True), flush=True)
            aqi.run(['docker', 'exec', container, 'rm',
                     '/openhab/conf/items/' + GROUP_SOURCE.name])
            if not wait(lambda: group_absent_members_present(container, header), 90):
                raise RuntimeError('file Group withdrawal lost file-owned membership')
            code, _ = aqi.request(container, header, '/items/gForecast', 'PUT',
                json.dumps({'type': 'Group', 'name': 'gForecast',
                            'label': 'Forecast Items', 'tags': ['forecast']}),
                'application/json')
            if code not in (200, 201) or not wait(
                    lambda: group_state(container, header, file_owned=False), 90):
                raise RuntimeError('managed Group rollback failed')
            rollback_first = first + timedelta(days=90)
            publish_probe(container, client, probe, rollback_first)
            check_series(database, rollback_first, units, previous)
            print('managed_rollback_forecast_series_persisted=true', flush=True)
            print('hot_handoff_safe=' + str(gap_persisted).lower(), flush=True)
        finally:
            if container is not None:
                try:
                    owner = aqi.run(['docker', 'inspect', '--format',
                        '{{index .Config.Labels "' + LABEL + '"}}', container]
                        ).decode().strip()
                except RuntimeError:
                    owner = None
                if owner == marker:
                    aqi.run(['docker', 'rm', '-f', '-v', container])
                    print('owned_isolated_openhab_removed=true', flush=True)
    if not gap_persisted:
        print('status=failed_provider_gap; production_writes=0; '
              'isolated_postgresql_removed=true', flush=True)
        raise SystemExit(2)
    print('status=passed; production_writes=0; isolated_postgresql_removed=true')


if __name__ == '__main__':
    main()
