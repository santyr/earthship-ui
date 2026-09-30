#!/usr/bin/env python3
"""Read-only household thermal journal export and disposable v2 restore check.

Run under a user-level transient unit with only THERMAL_DATABASE_URL supplied
through its private EnvironmentFile. No production SQL write, collector
activation, model change, persistent archive, or admin credential is used.
Errors are intentionally sanitized; never print DSNs, rows or subprocess stderr.
"""
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import parse_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_state_backup as backup  # noqa: E402
from thermal_model import airflow_migration, journal  # noqa: E402

TABLES = {'message_receipts': 'idempotency_key',
          'action_events': 'event_id', 'mode_events': 'event_id'}
MAX_ARCHIVE_BYTES = backup.MAX_JOURNAL_BYTES


class DigestWriter:
    def __init__(self):
        self.digest = sha256()

    def write(self, value):
        self.digest.update(value.encode() if isinstance(value, str) else value)


def table_proofs(connection):
    """Count and digest all rows in one already-open repeatable-read snapshot."""
    proofs = {}
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        for table, key in TABLES.items():
            cursor.execute(sql.SQL('SELECT count(*) FROM thermal_intel.{}').format(
                sql.Identifier(table)))
            count = cursor.fetchone()[0]
            writer = DigestWriter()
            command = sql.SQL('COPY (SELECT * FROM thermal_intel.{} ORDER BY {}) '
                              'TO STDOUT WITH CSV').format(sql.Identifier(table), sql.Identifier(key))
            cursor.copy_expert(command.as_string(connection), writer)
            proofs[table] = {'rows': count, 'sha256': writer.digest.hexdigest()}
    return proofs


def runtime_connection():
    dsn = os.environ['THERMAL_DATABASE_URL']
    params = parse_dsn(dsn)
    if (params.get('host') != '127.0.0.1' or str(params.get('port')) != '5432'
            or params.get('dbname') != 'openhab' or not params.get('user')
            or not params.get('password')):
        raise ValueError('restricted local journal connection required')
    connection = psycopg2.connect(dsn, connect_timeout=3)
    connection.set_session(readonly=True, autocommit=False,
                           isolation_level='REPEATABLE READ')
    return connection, params


def postgres_env(params):
    return {'PATH': '/usr/bin:/bin', 'PGHOST': params['host'],
            'PGPORT': str(params['port']), 'PGDATABASE': params['dbname'],
            'PGUSER': params['user'], 'PGPASSWORD': params['password']}


def export_archive(target, params, snapshot):
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, 'wb') as output:
        subprocess.run(['pg_dump', '--format=custom', '--schema=thermal_intel',
                        '--snapshot=' + snapshot], env=postgres_env(params),
                       stdout=output, stderr=subprocess.DEVNULL,
                       check=True, timeout=90)
        output.flush()
        os.fsync(output.fileno())
    if not 0 < target.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError('journal archive outside bound')
    backup._check_journal_archive(target)


def disposable_database(container, password, role):
    subprocess.run(['docker', 'run', '--detach', '--rm', '--name', container,
                    '--publish', '127.0.0.1::5432', '--env',
                    'POSTGRES_PASSWORD=' + password, 'postgres:16'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=30)
    mapped = subprocess.run(['docker', 'port', container, '5432/tcp'],
                            capture_output=True, check=True, timeout=10).stdout.decode().strip()
    port = int(mapped.rsplit(':', 1)[1])
    params = {'host': '127.0.0.1', 'port': port, 'dbname': 'postgres',
              'user': 'postgres', 'password': password}
    deadline = time.monotonic() + 30
    while True:
        try:
            connection = psycopg2.connect(connect_timeout=2, **params)
            break
        except psycopg2.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    with closing(connection):
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
    return params


def restore_and_rehearse(archive, params, role):
    subprocess.run(['pg_restore', '--dbname=postgres', '--no-owner', '--single-transaction',
                    '--exit-on-error', str(archive)], env=postgres_env(params),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=90)
    with closing(psycopg2.connect(connect_timeout=3, **params)) as connection:
        connection.set_session(readonly=True, autocommit=False,
                               isolation_level='REPEATABLE READ')
        restored_proofs = table_proofs(connection)
        connection.rollback()
    restored_dsn = psycopg2.extensions.make_dsn(**params)
    if journal.audit_schema(restored_dsn, runtime_role=role,
                            expected_owner='postgres')['fingerprint'] != migration_v1():
        raise ValueError('restored journal schema mismatch')
    with closing(psycopg2.connect(connect_timeout=3, **params)) as connection:
        with connection:
            with connection.cursor() as cursor:
                airflow_migration._replace_constraint(cursor)
                observed = airflow_migration._fingerprint(
                    cursor, runtime_role=role, expected_owner='postgres')
                if observed != airflow_migration.V2_FINGERPRINT:
                    raise ValueError('disposable v2 postimage mismatch')
    airflow_migration.audit_v2(restored_dsn, runtime_role=role,
                               expected_owner='postgres')
    return restored_proofs


def migration_v1():
    return airflow_migration.LEGACY_FINGERPRINT


def main():
    stage = 'preflight'
    container = 'thermal-live-restore-' + uuid4().hex
    start_attempted = False
    temporary_path = None
    try:
        with closing(runtime_connection()[0]) as source:
            params = parse_dsn(os.environ['THERMAL_DATABASE_URL'])
            with source.cursor() as cursor:
                cursor.execute("SELECT current_user, pg_get_userbyid(nspowner) "
                               "FROM pg_catalog.pg_namespace WHERE nspname=%s",
                               ('thermal_intel',))
                role, owner = cursor.fetchone()
                if role != params['user'] or role == owner:
                    raise ValueError('restricted journal role mismatch')
                cursor.execute('SELECT pg_export_snapshot()')
                snapshot = cursor.fetchone()[0]
            if journal.audit_schema(os.environ['THERMAL_DATABASE_URL'],
                                    runtime_role=role, expected_owner=owner)['fingerprint'] != migration_v1():
                raise ValueError('live journal v1 preimage mismatch')
            source_proofs = table_proofs(source)
            stage = 'export'
            with TemporaryDirectory(prefix='thermal-journal-live-restore-') as temporary:
                temporary_path = Path(temporary)
                archive = temporary_path / 'journal.dump'
                export_archive(archive, params, snapshot)
                source.rollback()
                stage = 'restore'
                password = uuid4().hex
                start_attempted = True
                disposable = disposable_database(container, password, role)
                restored_proofs = restore_and_rehearse(archive, disposable, role)
                if restored_proofs != source_proofs:
                    raise ValueError('restored journal rows differ')
                stage = 'cleanup'
        result = {'status': 'qualified_disposable_restore',
                  'production_writes': 0, 'tables': {
                      name: value['rows'] for name, value in source_proofs.items()},
                  'row_digests_equal': True, 'v1_restored': True,
                  'v2_disposable_postimage': True}
    except Exception:
        result = {'status': 'withheld', 'stage': stage}
    finally:
        if start_attempted:
            try:
                subprocess.run(['docker', 'rm', '--force', '--volumes', container],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False, timeout=30)
                remaining = subprocess.run(
                    ['docker', 'ps', '-a', '--filter', f'name=^/{container}$',
                     '--format', '{{.Names}}'],
                    capture_output=True, check=False, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                result = {'status': 'withheld', 'stage': 'container_cleanup'}
            else:
                if remaining.returncode != 0 or remaining.stdout.strip():
                    result = {'status': 'withheld', 'stage': 'container_cleanup'}
        if temporary_path is not None and temporary_path.exists():
            result = {'status': 'withheld', 'stage': 'temporary_cleanup'}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'qualified_disposable_restore' else 2


if __name__ == '__main__':
    raise SystemExit(main())
