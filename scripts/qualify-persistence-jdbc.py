#!/usr/bin/env python3
"""Actual JDBC checks in two disposable containers sharing only loopback."""
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tarfile
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

spec = importlib.util.spec_from_file_location('provider', Path(__file__).with_name('qualify-persistence-file-provider.py'))
provider = importlib.util.module_from_spec(spec); spec.loader.exec_module(provider)
run = provider.run
CACHE = Path('/var/lib/openhab/tmp/kar/openhab-addons-5.2.1')
BUNDLES = (
    'org/openhab/addons/bundles/org.openhab.persistence.jdbc/5.2.1/org.openhab.persistence.jdbc-5.2.1.jar',
    'org/postgresql/postgresql/42.7.11/postgresql-42.7.11.jar',
)
PROBE = 'JDBC_Qualification_Probe'
FORECAST = 'JDBC_Forecast_Probe'
NON_FORECAST = 'JDBC_NonForecast_Probe'


def compile_probe(class_name, packages):
    source = Path(__file__).with_name(class_name + '.java')
    jars = sorted(Path('/usr/share/openhab/runtime/system').rglob('*.jar'))
    if not jars:
        raise RuntimeError('version-matched OpenHAB compile dependencies missing')
    with tempfile.TemporaryDirectory(prefix='hex-jdbc-probe-') as directory:
        run(['java', '-m', 'jdk.compiler/com.sun.tools.javac.Main', '-cp',
            os.pathsep.join(map(str, jars)), '-d', directory, str(source)])
        compiled = (Path(directory) / (class_name + '.class')).read_bytes()
    archive = io.BytesIO()
    imports = 'Import-Package: ' + ',\r\n '.join(packages) + '\r\n\r\n'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('META-INF/MANIFEST.MF',
            'Manifest-Version: 1.0\r\n'
            'Bundle-ManifestVersion: 2\r\n'
            'Bundle-SymbolicName: hex.persistence.' + class_name.lower() + '\r\n'
            'Bundle-Version: 1.0.0\r\n'
            'Bundle-Activator: ' + class_name + '\r\n'
            + imports)
        bundle.writestr(class_name + '.class', compiled)
    return archive.getvalue()


def same_number(left, right):
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except InvalidOperation:
        return False


class Database:
    def __init__(self, *, candidate_ac=False):
        self.candidate_ac = candidate_ac

    def __enter__(self):
        # Fail before allocating resources if the required cached code is absent.
        self.bundles = {Path(name).name: (CACHE/name).read_bytes() for name in BUNDLES}
        self.forecast_probe = compile_probe('HexForecastProbe', [
            'org.osgi.framework', 'org.openhab.core.events',
            'org.openhab.core.items.events', 'org.openhab.core.library.types',
            'org.openhab.core.types'])
        self.power_probe = compile_probe('HexPowerRestoreProbe', [
            'org.osgi.framework', 'org.openhab.core.items',
            'org.openhab.core.persistence.extensions'])
        if self.candidate_ac:
            self.ac_probe = compile_probe('HexAcEvidenceProbe', [
                'org.osgi.framework', 'org.openhab.core.items',
                'org.openhab.core.persistence.extensions'])
        self.forecast_target = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)
        self.forecast_verified = 0
        self.power_restore_verified = False
        self.marker = str(uuid.uuid4())
        self.password = secrets.token_hex(24)
        self.cid = run(['docker', 'run', '-d', '--network', 'none', '--label',
            'hex.jdbc.qualification=' + self.marker, '--memory', '384m', '--cpus', '1',
            '--tmpfs', '/var/lib/postgresql/data:rw,size=256m',
            '-e', 'POSTGRES_PASSWORD=' + self.password, 'postgres:16']).decode().strip()
        self.network = 'container:' + self.cid
        self.previous = []
        return self

    def __exit__(self, *_):
        info = json.loads(run(['docker', 'inspect', self.cid]))[0]
        if info['Config']['Labels'].get('hex.jdbc.qualification') != self.marker:
            raise RuntimeError('database cleanup ownership mismatch')
        run(['docker', 'rm', '-f', '-v', self.cid])
        print('owned_postgresql_database_removed=true', flush=True)

    def stage(self, cid):
        info = json.loads(run(['docker', 'inspect', self.cid]))[0]
        host = info['HostConfig']
        assert host['NetworkMode'] == 'none' and not host['Privileged']
        assert not host.get('Binds') and not host.get('Devices') and not host.get('PortBindings')
        files = {'openhab/addons/' + name: body for name, body in self.bundles.items()}
        files['openhab/conf/services/jdbc.cfg'] = (
            'url=jdbc:postgresql://127.0.0.1:5432/postgres\nuser=postgres\n'
            'password=' + self.password + '\n').encode()
        files['tmp/hex-jdbc-forecast-probe.jar'] = self.forecast_probe
        files['tmp/hex-jdbc-power-probe.jar'] = self.power_probe
        if self.candidate_ac:
            files['tmp/hex-jdbc-ac-probe.jar'] = self.ac_probe
            files['openhab/conf/items/inverter-ac-evidence.items'] = (
                Path(__file__).resolve().parents[1]
                / 'openhab/file-config/drafts/inverter-ac-evidence.items').read_bytes()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            for name, body in files.items():
                entry = tarfile.TarInfo(name); entry.mode = 0o600; entry.size = len(body)
                tar.addfile(entry, io.BytesIO(body))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/'], archive.getvalue())

    def request(self, cid, header, path, method='GET', body=None, content_type='application/json'):
        assert path.startswith('/items/') or path.startswith('/persistence/items/')
        command = ['docker', 'exec', '-i', cid, 'curl', '-sS', '--max-time', '5',
            '-X', method, '-H', '@-', '-w', '\\n%{http_code}', 'http://127.0.0.1:8080/rest' + path]
        if body is not None:
            command += ['-H', 'Content-Type: ' + content_type, '--data-binary', body]
        value, status = run(command, header).decode().rsplit('\n', 1)
        return int(status), value

    def create(self, cid, header):
        status, _ = self.request(cid, header, '/items/' + PROBE, 'PUT',
            json.dumps({'type': 'Number', 'name': PROBE, 'label': 'Isolated JDBC probe'}))
        if status != 201:
            raise RuntimeError('isolated test Item creation failed: ' + str(status))

    def checkpoint(self, cid, header, label):
        if not self.previous:
            for _ in range(90):
                ready = run(['docker', 'exec', self.cid, 'psql', '-U', 'postgres', '-d', 'postgres',
                    '-Atc', "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND lower(table_name)='items')"]).decode().strip()
                if ready == 't':
                    break
                time.sleep(1)
            else:
                listing = run(['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client',
                    '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2',
                    'bundle:list -s'], b'\n').decode()
                for line in listing.splitlines():
                    if 'org.openhab.persistence.jdbc' in line or 'org.postgresql.jdbc' in line:
                        print('isolated_bundle_at_mapping_timeout=' + line.strip(), flush=True)
                raise RuntimeError('isolated JDBC mapping table not initialized')
            listing = run(['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client',
                '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2',
                'bundle:list -s'], b'\n').decode()
            for line in listing.splitlines():
                if 'org.openhab.persistence.jdbc' in line or 'org.postgresql.jdbc' in line:
                    print('isolated_bundle=' + line.strip(), flush=True)
            self.create(cid, header)
            status, _ = self.request(cid, header, '/items/Power_Evidence_JSON', 'PUT',
                json.dumps({'type': 'String', 'name': 'Power_Evidence_JSON', 'label': 'Isolated excluded probe'}))
            if status != 201:
                raise RuntimeError('isolated exclusion Item creation failed')
            for definition in [
                {'type': 'Group', 'name': 'gForecast', 'label': 'Isolated forecast group'},
                {'type': 'Number', 'name': FORECAST, 'label': 'Isolated forecast member',
                 'groupNames': ['gForecast']},
                {'type': 'Number', 'name': NON_FORECAST, 'label': 'Isolated negative control'}]:
                status, _ = self.request(cid, header, '/items/' + definition['name'], 'PUT',
                    json.dumps(definition))
                if status != 201:
                    raise RuntimeError('isolated forecast Item creation failed: ' + definition['name'])
        value = str(10 + len(self.previous))
        status, _ = self.request(cid, header, '/items/' + PROBE + '/state', 'PUT', value, 'text/plain')
        if status != 202:
            raise RuntimeError('isolated state update failed: ' + str(status))
        for _ in range(30):
            status, body = self.request(cid, header, '/persistence/items/' + PROBE + '?serviceId=jdbc')
            if status == 200:
                rows = json.loads(body).get('data', [])
                if rows and same_number(rows[-1]['state'], value):
                    if rows[:len(self.previous)] != self.previous or len(rows) != len(self.previous) + 1:
                        raise RuntimeError('JDBC historical prefix or write count changed')
                    self.previous = rows
                    print('jdbc_write_and_prefix_' + label + '=verified', flush=True)
                    self.policy_branches(cid, header, label, value)
                    self.forecast_checkpoint(cid, header, label)
                    return
            time.sleep(1)
        # This endpoint contains only this synthetic Item's history/error, never connection config.
        raise RuntimeError('isolated JDBC did not persist expected state; last history HTTP '
            + str(status) + ': ' + body[:250])

    def policy_branches(self, cid, header, label, value):
        # A repeated value must not become a periodic/update persistence policy.
        status, _ = self.request(cid, header, '/items/' + PROBE + '/state', 'PUT', value, 'text/plain')
        if status != 202:
            raise RuntimeError('isolated unchanged update failed')
        excluded = json.dumps({'isolatedQualification': label})
        status, _ = self.request(cid, header, '/items/Power_Evidence_JSON/state', 'PUT', excluded, 'text/plain')
        if status != 202:
            raise RuntimeError('isolated excluded update failed')
        if self.candidate_ac:
            status, _ = self.request(cid, header, '/items/Inverter_AC_Evidence_JSON/state',
                                     'PUT', excluded, 'text/plain')
            if status != 202:
                raise RuntimeError('isolated AC excluded update failed')
        status, body = self.request(cid, header, '/items/Power_Evidence_JSON/state')
        if status != 200 or body != excluded:
            raise RuntimeError('excluded test update was not applied to isolated Item')
        # Bounded negative observation plus a positive persistence control at each
        # checkpoint; this is not a claim about all future scheduler behavior.
        for _ in range(3):
            time.sleep(1)
            status, body = self.request(cid, header, '/persistence/items/' + PROBE + '?serviceId=jdbc')
            if status != 200 or json.loads(body).get('data') != self.previous:
                raise RuntimeError('unchanged probe update altered history')
            status, body = self.request(cid, header, '/persistence/items/Power_Evidence_JSON?serviceId=jdbc')
            if status != 404 and not (status == 200 and json.loads(body).get('data') == []):
                raise RuntimeError('excluded power Item persisted or its history check failed')
            if self.candidate_ac:
                status, body = self.request(cid, header,
                    '/persistence/items/Inverter_AC_Evidence_JSON?serviceId=jdbc')
                if status != 404 and not (status == 200 and json.loads(body).get('data') == []):
                    raise RuntimeError('excluded AC Item persisted or its history check failed')
        print('change_only_and_power_exclusion_' + label + '=verified', flush=True)

    def forecast_checkpoint(self, cid, header, label):
        value = 40 + len(self.previous)
        content = (self.forecast_target.isoformat().replace('+00:00', 'Z')
                   + '\n' + str(value) + '\n').encode()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            entry = tarfile.TarInfo('hex-jdbc-forecast-probe')
            entry.mode = 0o600; entry.size = len(content)
            tar.addfile(entry, io.BytesIO(content))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/tmp'], archive.getvalue())
        client = ['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client',
            '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        attempt = subprocess.run(client + ['bundle:install file:/tmp/hex-jdbc-forecast-probe.jar'],
            input=b'\n', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        installed = attempt.stdout.decode(errors='replace')
        if attempt.returncode:
            detail = (installed + attempt.stderr.decode(errors='replace'))[-500:]
            detail = re.sub(r'oh\.[A-Za-z0-9._-]+', '[redacted]', detail)
            raise RuntimeError('isolated forecast bundle install failed: ' + detail)
        match = re.search(r'Bundle IDs?:\s*(\d+)', installed)
        if not match:
            raise RuntimeError('isolated forecast bundle install did not return an ID')
        bundle_id = match.group(1)
        try:
            started = run(client + ['bundle:start ' + bundle_id], b'\n').decode()
            if 'Error executing command' in started:
                raise RuntimeError('isolated forecast bundle did not start: ' + started[-300:])
            start = (self.forecast_target - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
            end = (self.forecast_target + timedelta(hours=1, seconds=1)).isoformat().replace('+00:00', 'Z')
            query = '?serviceId=jdbc&starttime=' + start + '&endtime=' + end
            expected_times = [int(self.forecast_target.timestamp() * 1000),
                              int(self.forecast_target.timestamp() * 1000) + 3600000]
            last_status, last_rows = None, None
            for _ in range(30):
                status, body = self.request(cid, header, '/persistence/items/' + FORECAST + query)
                last_status = status
                if status == 200:
                    rows = json.loads(body).get('data', [])
                    last_rows = [(row.get('time'), row.get('state')) for row in rows]
                    if len(last_rows) == 2 and [row[0] for row in last_rows] == expected_times \
                            and all(same_number(row[1], expected)
                        for row, expected in zip(last_rows, [value, value + 1])):
                        break
                time.sleep(1)
            else:
                raise RuntimeError('isolated forecast series was not persisted as two future points: '
                    + str((last_status, last_rows)))
            status, body = self.request(cid, header, '/persistence/items/' + NON_FORECAST + query)
            if status != 404 and not (status == 200 and json.loads(body).get('data') == []):
                raise RuntimeError('negative-control future series unexpectedly persisted')
            print('forecast_group_future_series_' + label + '=verified', flush=True)
            self.forecast_verified += 1
        finally:
            run(client + ['bundle:uninstall ' + bundle_id], b'\n')

    def power_write(self, cid, header):
        self.power_expected = '{"isolatedQualification":"explicit-writer"}'
        client = ['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client',
            '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        installed = run(client + ['bundle:install file:/tmp/hex-jdbc-power-probe.jar'], b'\n').decode()
        match = re.search(r'Bundle IDs?:\s*(\d+)', installed)
        if not match:
            raise RuntimeError('isolated power bundle install failed: ' + installed[-300:])
        bundle_id = match.group(1)
        try:
            started = run(client + ['bundle:start ' + bundle_id], b'\n').decode()
            if 'Error executing command' in started:
                raise RuntimeError('isolated power bundle did not start: ' + started[-300:])
            for _ in range(30):
                status, body = self.request(cid, header, '/persistence/items/Power_Evidence_JSON?serviceId=jdbc')
                if status == 200:
                    rows = json.loads(body).get('data', [])
                    if len(rows) == 1 and rows[0]['state'] == self.power_expected:
                        break
                time.sleep(1)
            else:
                raise RuntimeError('explicit isolated power history did not appear')
            status, current = self.request(cid, header, '/items/Power_Evidence_JSON/state')
            if status != 200 or current == self.power_expected:
                raise RuntimeError('power probe unexpectedly changed live Item state')
            print('independent_power_writer_history=verified', flush=True)
        finally:
            run(client + ['bundle:uninstall ' + bundle_id], b'\n')
        if self.candidate_ac:
            self.ac_write(cid, header)

    def ac_write(self, cid, header):
        self.ac_expected = '{"isolatedQualification":"explicit-ac-writer"}'
        client = ['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client',
            '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '5', '-d', '2']
        installed = run(client + ['bundle:install file:/tmp/hex-jdbc-ac-probe.jar'], b'\n').decode()
        match = re.search(r'Bundle IDs?:\s*(\d+)', installed)
        if not match:
            raise RuntimeError('isolated AC bundle install failed: ' + installed[-300:])
        bundle_id = match.group(1)
        try:
            started = run(client + ['bundle:start ' + bundle_id], b'\n').decode()
            if 'Error executing command' in started:
                raise RuntimeError('isolated AC bundle did not start: ' + started[-300:])
            for _ in range(30):
                status, body = self.request(cid, header,
                    '/persistence/items/Inverter_AC_Evidence_JSON?serviceId=jdbc')
                if status == 200:
                    rows = json.loads(body).get('data', [])
                    if len(rows) == 1 and rows[0]['state'] == self.ac_expected:
                        break
                time.sleep(1)
            else:
                raise RuntimeError('explicit isolated AC history did not appear')
            status, current = self.request(cid, header, '/items/Inverter_AC_Evidence_JSON/state')
            if status != 200 or current == self.ac_expected:
                raise RuntimeError('AC probe unexpectedly changed live Item state')
            print('independent_ac_writer_history=verified', flush=True)
        finally:
            run(client + ['bundle:uninstall ' + bundle_id], b'\n')

    def restore(self, cid, header):
        status, _ = self.request(cid, header, '/items/' + PROBE, 'DELETE')
        if status != 200:
            raise RuntimeError('isolated Item removal failed')
        self.create(cid, header)
        for _ in range(30):
            status, body = self.request(cid, header, '/items/' + PROBE + '/state')
            if status == 200 and same_number(body, self.previous[-1]['state']):
                print('jdbc_restore_on_item_recreation=verified', flush=True)
                return
            time.sleep(1)
        raise RuntimeError('isolated Item did not restore its persisted state')

    def restart(self, cid, header):
        def java_pid():
            listing = run(['docker', 'top', cid, '-eo', 'pid,comm']).decode()
            pids = [line.split()[0] for line in listing.splitlines()[1:]
                    if line.split()[-1] == 'java']
            return pids[0] if len(pids) == 1 else None
        before = java_pid()
        if before is None:
            raise RuntimeError('isolated Java process is not uniquely identified')
        try:
            run(['docker', 'exec', '-i', cid, '/openhab/runtime/bin/client',
                '-h', '127.0.0.1', '-u', 'openhab', '-p', 'habopen', '-r', '2', '-d', '1',
                'system:shutdown -f'], b'\n')
        except RuntimeError:
            # Closing the console connection is not proof of either success or
            # failure. Require a different live JVM plus restored state below.
            pass
        for _ in range(90):
            time.sleep(2)
            try:
                after = java_pid()
                if after is None or after == before:
                    continue
                status, body = self.request(cid, header, '/items/' + PROBE + '/state')
                if status != 200 or not same_number(body, self.previous[-1]['state']):
                    continue
                status, body = self.request(cid, header, '/persistence/items/' + PROBE + '?serviceId=jdbc')
                if status != 200:
                    continue
                rows = json.loads(body).get('data', [])
                if rows[:len(self.previous)] != self.previous:
                    raise ValueError('history prefix changed across isolated JVM restart')
                if not all(same_number(row['state'], self.previous[-1]['state'])
                           for row in rows[len(self.previous):]):
                    raise ValueError('unexpected post-restore history state')
                status, power_state = self.request(cid, header, '/items/Power_Evidence_JSON/state')
                if status != 200 or power_state != self.power_expected:
                    continue
                status, body = self.request(cid, header,
                    '/persistence/items/Power_Evidence_JSON?serviceId=jdbc')
                if status != 200 or len(json.loads(body).get('data', [])) != 1 \
                        or json.loads(body)['data'][0]['state'] != self.power_expected:
                    continue
                if self.candidate_ac:
                    status, ac_state = self.request(cid, header,
                        '/items/Inverter_AC_Evidence_JSON/state')
                    if status != 200 or ac_state != self.ac_expected:
                        continue
                    status, body = self.request(cid, header,
                        '/persistence/items/Inverter_AC_Evidence_JSON?serviceId=jdbc')
                    if status != 200 or len(json.loads(body).get('data', [])) != 1 \
                            or json.loads(body)['data'][0]['state'] != self.ac_expected:
                        continue
                start = (self.forecast_target - timedelta(seconds=1)).isoformat().replace('+00:00', 'Z')
                end = (self.forecast_target + timedelta(hours=1, seconds=1)).isoformat().replace('+00:00', 'Z')
                query = '?serviceId=jdbc&starttime=' + start + '&endtime=' + end
                status, body = self.request(cid, header, '/persistence/items/' + FORECAST + query)
                if status != 200:
                    continue
                forecast_rows = json.loads(body).get('data', [])
                expected_times = [int(self.forecast_target.timestamp() * 1000),
                                  int(self.forecast_target.timestamp() * 1000) + 3600000]
                if len(forecast_rows) != 2 or [row['time'] for row in forecast_rows] != expected_times \
                        or not all(same_number(row['state'], value)
                    for row, value in zip(forecast_rows, [45, 46])):
                    continue
                self.power_restore_verified = True
                print('isolated_jvm_restart_and_jdbc_restore=verified', flush=True)
                print('forecast_future_series_after_restart=verified', flush=True)
                print('independently_written_power_restore=verified', flush=True)
                if self.candidate_ac:
                    print('independently_written_ac_restore=verified', flush=True)
                print('restore_generated_history_rows=' + str(len(rows)-len(self.previous)), flush=True)
                return
            except RuntimeError:
                continue
        raise RuntimeError('isolated JVM restart/restoration was not verified')


if __name__ == '__main__':
    with Database() as database:
        provider.main(database)
