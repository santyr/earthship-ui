#!/usr/bin/env python3
"""Read-only production snapshot; restore/rehearse in a networkless container.

Writes a private local archive/manifest, never changes production SQL or jobs.
The restored container is temporary and contains only this analytics schema.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, '/home/sat/Solar_PV/analytics/src')
from earthship_energy.db import parse_openhab_jdbc_config
import psycopg2


def execute(argv, *, data=None, env=None, timeout=120):
    result = subprocess.run(argv, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Backup/rehearsal command failed: ' + argv[0])
    return result.stdout


def fingerprint_query(table):
    if not re.fullmatch('[a-z][a-z0-9_]+', table):
        raise ValueError('unexpected analytics identifier')
    return ("SELECT count(*)::text || '|' || COALESCE(md5(string_agg("
            "to_jsonb(t)::text, E'\\n' ORDER BY to_jsonb(t)::text COLLATE \"C\")), 'empty') "
            f'FROM energy_analytics.{table} t;')


def write_artifact(path, value):
    if path.exists():
        raise RuntimeError('artifact already exists')
    body = json.dumps(value, indent=2, sort_keys=True)
    patch = '*** Begin Patch\n*** Add File: ' + str(path) + '\n'
    patch += ''.join('+' + line + '\n' for line in body.splitlines()) + '*** End Patch\n'
    execute(['apply_patch'], data=patch.encode())


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: verify-energy-schema-backup.py MIGRATION_DIRECTORY')
    migrations = Path(sys.argv[1]).resolve()
    pending = sorted(migrations.glob('000[34]_*.sql'))
    if len(pending) != 2:
        raise RuntimeError('exact migrations3/4 required')
    os.umask(0o077)
    destination = Path(tempfile.mkdtemp(prefix='trough-activation-backup-', dir='/tmp'))
    archive = destination / 'energy_analytics.dump'
    settings = parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config')
    connection = psycopg2.connect(**settings.connect_kwargs, connect_timeout=3)
    original = {}
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='60s'")
            cursor.execute("SET LOCAL lock_timeout='2s'")
            cursor.execute("SET LOCAL timezone='UTC'")
            cursor.execute("SELECT version,sha256 FROM energy_analytics.schema_migrations ORDER BY version")
            applied = dict(cursor.fetchall())
            if list(applied) != [1, 2]:
                raise RuntimeError('unexpected live migration versions')
            for version, digest in applied.items():
                sources = list(migrations.glob(f'{version:04d}_*.sql'))
                if len(sources) != 1 or hashlib.sha256(sources[0].read_bytes()).hexdigest() != digest:
                    raise RuntimeError('migration checksum drift')
            cursor.execute('SELECT pg_export_snapshot()')
            snapshot = cursor.fetchone()[0]
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='energy_analytics' ORDER BY tablename")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(fingerprint_query(table))
                original[table] = cursor.fetchone()[0]
            env = {**os.environ, 'PGPASSWORD': settings.password, 'PGCONNECT_TIMEOUT': '3'}
            execute(['pg_dump', '-h', settings.host, '-p', str(settings.port), '-U', settings.user,
                     '-d', settings.dbname, '--schema=energy_analytics', '--format=custom',
                     '--snapshot=' + snapshot, '--file=' + str(archive)], env=env)
    finally:
        connection.close()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    marker = uuid.uuid4().hex
    container = None
    try:
        container = execute(['docker', 'run', '--detach', '--network', 'none', '--memory', '768m',
            '--cpus', '1', '--label', 'hex.trough.restore=' + marker,
            '--name', 'hex-trough-restore-' + marker, '-e', 'POSTGRES_HOST_AUTH_METHOD=trust',
            'postgres:16']).decode().strip()
        if not re.fullmatch('[0-9a-f]{64}', container):
            raise RuntimeError('unverified container identity')
        for _ in range(40):
            status = subprocess.run(['docker', 'exec', container, 'pg_isready', '-U', 'postgres'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            if status.returncode == 0:
                break
            time.sleep(.5)
        else:
            raise RuntimeError('isolated restore database unavailable')
        execute(['docker', 'exec', '-i', container, 'pg_restore', '--exit-on-error',
                 '--no-owner', '--no-privileges', '-U', 'postgres', '-d', 'postgres'], data=archive.read_bytes())
        def query(sql):
            return execute(['docker', 'exec', '-i', container, 'psql', '-X', '-U', 'postgres',
                            '-d', 'postgres', '-At', '-v', 'ON_ERROR_STOP=1'],
                           data=("SET timezone='UTC'; SET statement_timeout='60s'; " + sql).encode()).decode().splitlines()[2:]
        restored = {table: query(fingerprint_query(table))[0] for table in original}
        if restored != original:
            raise RuntimeError('restored fingerprints mismatch')
        script = ['BEGIN;']
        for path in pending:
            version = int(path.name[:4]); name = path.stem[5:]
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            script.extend([path.read_text(), f"INSERT INTO energy_analytics.schema_migrations(version,name,sha256) VALUES ({version},'{name}','{checksum}');"])
        script.append('COMMIT;')
        query('\n'.join(script))
        if query('SELECT version FROM energy_analytics.schema_migrations ORDER BY version;') != ['1', '2', '3', '4']:
            raise RuntimeError('rehearsal migration ledger mismatch')
        for table in original:
            if table != 'schema_migrations' and query(fingerprint_query(table))[0] != original[table]:
                raise RuntimeError('migration changed unrelated data')
        for table in ('advisory_trough_outcomes', 'advisory_trough_selection'):
            if query(fingerprint_query(table))[0] != '0|empty':
                raise RuntimeError('unexpected synthetic outcome')
        manifest = dict(version=1, database='openhab', status='restore_verified',
            archive_path=str(archive), archive_sha256=digest, scope='energy_analytics',
            verified_at=datetime.now(timezone.utc).isoformat(), fingerprints=original,
            rehearsal_versions=[1, 2, 3, 4], production_mutations=False)
        write_artifact(destination / 'backup-manifest.json', manifest)
        print(json.dumps({'status': 'restore_verified', 'directory': str(destination),
            'archive_sha256': digest, 'tables': len(original), 'rehearsal_versions': [1, 2, 3, 4]}))
    finally:
        if container and re.fullmatch('[0-9a-f]{64}', container):
            label = execute(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.trough.restore"}}', container]).decode().strip()
            if label != marker:
                raise RuntimeError('container ownership changed; cleanup refused')
            execute(['docker', 'rm', '--force', container])
            print('temporary_restore_container_removed=true; private_backup_retained=true')


if __name__ == '__main__':
    main()
