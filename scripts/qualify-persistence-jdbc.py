#!/usr/bin/env python3
"""Actual JDBC checks in two disposable containers sharing only loopback."""
import importlib.util
import io
import json
from pathlib import Path
import secrets
import tarfile
import time
import uuid
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


def same_number(left, right):
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except InvalidOperation:
        return False


class Database:
    def __enter__(self):
        # Fail before allocating resources if the required cached code is absent.
        self.bundles = {Path(name).name: (CACHE/name).read_bytes() for name in BUNDLES}
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
        files = {'addons/' + name: body for name, body in self.bundles.items()}
        files['conf/services/jdbc.cfg'] = (
            'url=jdbc:postgresql://127.0.0.1:5432/postgres\nuser=postgres\n'
            'password=' + self.password + '\n').encode()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tar:
            for name, body in files.items():
                entry = tarfile.TarInfo(name); entry.mode = 0o600; entry.size = len(body)
                tar.addfile(entry, io.BytesIO(body))
        run(['docker', 'exec', '-i', cid, 'tar', '-xf', '-', '-C', '/openhab'], archive.getvalue())

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
            for _ in range(30):
                ready = run(['docker', 'exec', self.cid, 'psql', '-U', 'postgres', '-d', 'postgres',
                    '-Atc', "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND lower(table_name)='items')"]).decode().strip()
                if ready == 't':
                    break
                time.sleep(1)
            else:
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
        print('change_only_and_power_exclusion_' + label + '=verified', flush=True)

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


if __name__ == '__main__':
    with Database() as database:
        provider.main(database)
