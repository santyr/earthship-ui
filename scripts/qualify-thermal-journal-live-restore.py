#!/usr/bin/env python3
"""Read-only household thermal journal export and disposable v2 restore check.

Run under a user-level transient unit with only THERMAL_DATABASE_URL supplied
through its private EnvironmentFile. No production SQL write, collector
activation, model change, or production admin credential is used. Optional
--retain-dir keeps a qualified private same-host JOURNAL-ONLY recovery point;
it does not create a full collector/config/signing-authority backup.
Errors are intentionally sanitized; never print DSNs, rows or subprocess stderr.
Select --source-schema v2 explicitly after the approved journal cutover; the
default remains exact v1 for existing pre-cutover workflows. No auto-detection
or relaxed schema audit is permitted.
"""
from contextlib import closing
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
import re
import shutil
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


def disposable_database(container, password, role, *, ownership_token=None):
    if ownership_token is not None and re.fullmatch("[0-9a-f]{32}", ownership_token) is None:
        raise ValueError("exact disposable ownership token required")
    subprocess.run(['docker', 'run', '--detach', '--rm', '--name', container,
                    '--memory', '512m', '--memory-swap', '512m', '--cpus', '1',
                    '--publish', '127.0.0.1::5432', '--env',
                    'POSTGRES_PASSWORD=' + password,
                    *(['--label', 'earthship.thermal.restore-token='+ownership_token] if ownership_token is not None else []),
                    'postgres:16'],
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


def schema_fingerprint(version):
    if version == 'v1':
        return airflow_migration.LEGACY_FINGERPRINT
    if version == 'v2':
        return airflow_migration.V2_FINGERPRINT
    raise ValueError('exact v1 or v2 source schema required')


def restore_and_rehearse(archive, params, role, *, source_schema='v1'):
    expected = schema_fingerprint(source_schema)
    if (params.get('host') != '127.0.0.1' or params.get('dbname') != 'postgres'
            or params.get('user') != 'postgres' or not params.get('password')
            or not 1024 < int(params.get('port', 0)) < 65536 or int(params['port']) == 5432
            or re.fullmatch('[a-z_][a-z0-9_]*', role) is None):
        raise ValueError('explicit disposable restore target required')
    subprocess.run(['pg_restore', '--dbname=postgres', '--no-owner', '--single-transaction',
                    '--exit-on-error', str(archive)], env=postgres_env(params),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=90)
    with closing(psycopg2.connect(connect_timeout=3, **params)) as connection:
        connection.set_session(readonly=True, autocommit=False,
                               isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            observed = airflow_migration._fingerprint(
                cursor, runtime_role=role, expected_owner='postgres')
        if observed != expected:
            raise ValueError('restored journal schema mismatch')
        restored_proofs = table_proofs(connection)
        connection.rollback()
    restored_dsn = psycopg2.extensions.make_dsn(**params)
    if source_schema == 'v1':
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


def retain_archive(archive, directory):
    """Keep a private NEW recovery point; never overwrite or prune one."""
    directory = Path(directory)
    backup._private_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('retained destination already exists')
    backup._private_file(archive)
    backup._check_journal_archive(archive)
    if not 0 < archive.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError('retained archive outside bound')
    directory.mkdir(mode=0o700)
    target = directory/'journal.dump'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output, archive.open('rb') as source:
        shutil.copyfileobj(source, output, length=65536)
        output.flush()
        os.fsync(output.fileno())
    if backup._digest(target) != backup._digest(archive):
        raise ValueError('retained archive digest mismatch')
    backup._check_journal_archive(target)
    return backup._digest(target)


def finalize_retained(directory, digest, proofs, observed_at, consumer=None, *, source_schema='v1'):
    """Publish the journal-only manifest AFTER owned disposable cleanup."""
    expected = schema_fingerprint(source_schema)
    directory = Path(directory)
    backup._private_directory(directory)
    backup._private_file(directory/'journal.dump')
    if set(path.name for path in directory.iterdir()) != {'journal.dump'}:
        raise ValueError('unexpected retained destination contents')
    if backup._digest(directory/'journal.dump') != digest:
        raise ValueError('retained archive changed before finalization')
    manifest = {'version': 1, 'scope': 'thermal_intel_journal_only_recovery',
        'full_collector_bundle': False, 'export_observed_at': observed_at,
        'source_schema_fingerprint': expected, 'source_schema_version': source_schema,
        'archive_sha256': digest,
        'table_proofs': proofs, 'disposable_restore_qualified': True,
        'consumer': consumer, 'off_host_copy': False}
    fd = os.open(directory/'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()+b'\n')
        output.flush()
        os.fsync(output.fileno())
    fd = os.open(directory, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'directory': str(directory), 'scope': manifest['scope'],
            'archive_sha256': digest, 'full_collector_bundle': False}


def qualify_consumer(params, role, runtime_root, expected_revision):
    """Insert labeled fixture rows only into the restored disposable database."""
    if (params.get('host') != '127.0.0.1' or params.get('dbname') != 'postgres'
            or not 1024 < int(params.get('port', 0)) < 65536 or int(params['port']) == 5432
            or re.fullmatch('[a-z_][a-z0-9_]*', role) is None):
        raise ValueError('disposable probe target required')
    with closing(psycopg2.connect(connect_timeout=3, **params)) as connection:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute('''SELECT min(effective_at) FROM (
                    SELECT effective_at FROM thermal_intel.action_events
                    UNION ALL SELECT effective_at FROM thermal_intel.mode_events) history''')
                earliest = cursor.fetchone()[0] or datetime.now(timezone.utc)
                start = (earliest-timedelta(days=2)).astimezone(timezone.utc)
                start = start.replace(minute=start.minute//5*5, second=0, microsecond=0)
                key = 'disposable-consumer-fixture-'+uuid4().hex
                cursor.execute('''INSERT INTO thermal_intel.message_receipts
                    (idempotency_key, payload_digest, received_at) VALUES (%s,%s,%s)''',
                    (key, sha256(key.encode()).hexdigest(), start+timedelta(minutes=10)))
                for name, state, minutes in (
                        ('vent', 'closed', 0), ('indoor_shade', 'open', 0),
                        ('outdoor_shade', 'removed', 0), ('kiva', 'off', 0),
                        ('window', 'open', 5), ('skylight', 'closed', 10)):
                    effective = start+timedelta(minutes=minutes)
                    cursor.execute('''INSERT INTO thermal_intel.action_events
                        (event_id,idempotency_key,received_at,effective_at,action,state,source,confidence,note)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (key+'-'+name, key, start+timedelta(minutes=10), effective,
                         name, state, 'manual_dm', 1., 'DISPOSABLE FIXTURE; not household evidence'))
    probe_dsn = psycopg2.extensions.make_dsn(**params,
        options='-c default_transaction_read_only=on -c role='+role)
    env = {'PATH': '/usr/bin:/bin', 'THERMAL_RESTORE_PROBE_URL': probe_dsn}
    result = subprocess.run([sys.executable, str(ROOT/'scripts/verify-thermal-restored-consumer.py'),
        '--runtime-root', str(runtime_root), '--expected-runtime-revision', expected_revision,
        '--fixture-start', start.isoformat(), '--runtime-role', role],
        env=env, capture_output=True, check=False, timeout=30)
    if result.returncode != 0:
        try:
            failure = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('restored consumer probe failed') from None
        raise ValueError(
            'restored consumer probe failed: '
            + str(failure.get('error', failure.get('error_type', 'withheld')))
        )
    proof = json.loads(result.stdout)
    if proof.get('status') != 'installed_consumer_qualified' or proof.get('runtime_revision') != expected_revision:
        raise ValueError('restored consumer qualification failed')
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consumer-runtime', type=Path)
    parser.add_argument('--expected-consumer-revision')
    parser.add_argument('--source-schema', choices=('v1', 'v2'), default='v1',
        help='exact source vocabulary; v2 must be selected after the approved cutover')
    parser.add_argument('--retain-dir', type=Path,
        help='new private same-host journal-only recovery directory; never overwritten')
    args = parser.parse_args(argv)
    if ((args.consumer_runtime is None) != (args.expected_consumer_revision is None)
            or args.expected_consumer_revision is not None
            and re.fullmatch('[0-9a-f]{64}', args.expected_consumer_revision) is None):
        parser.error('consumer runtime and full revision pin must be supplied together')
    stage = 'preflight'
    container = 'thermal-live-restore-' + uuid4().hex
    start_attempted = False
    temporary_path = None
    retained_digest = None
    try:
        if args.retain_dir is not None:
            backup._private_directory(args.retain_dir.parent)
            if args.retain_dir.exists() or args.retain_dir.is_symlink():
                raise ValueError('retained destination already exists')
        with closing(runtime_connection()[0]) as source:
            params = parse_dsn(os.environ['THERMAL_DATABASE_URL'])
            with source.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='3s'")
                cursor.execute("SET LOCAL statement_timeout='30s'")
                # Read-only ACCESS SHARE locks prevent concurrent journal DDL
                # during fingerprinting/export without blocking normal inserts.
                cursor.execute('LOCK TABLE thermal_intel.action_events, '
                    'thermal_intel.message_receipts, thermal_intel.mode_events IN ACCESS SHARE MODE')
                cursor.execute("SELECT current_user, pg_get_userbyid(nspowner) "
                               "FROM pg_catalog.pg_namespace WHERE nspname=%s",
                               ('thermal_intel',))
                role, owner = cursor.fetchone()
                if role != params['user'] or role == owner:
                    raise ValueError('restricted journal role mismatch')
                observed = airflow_migration._fingerprint(
                    cursor, runtime_role=role, expected_owner=owner)
                if observed != schema_fingerprint(args.source_schema):
                    raise ValueError('live journal exact selected schema mismatch')
                cursor.execute('SELECT pg_export_snapshot()')
                snapshot = cursor.fetchone()[0]
            observed_at = datetime.now(timezone.utc).isoformat()
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
                restored_proofs = restore_and_rehearse(archive, disposable, role,
                    source_schema=args.source_schema)
                if restored_proofs != source_proofs:
                    raise ValueError('restored journal rows differ')
                consumer_proof = None
                if args.consumer_runtime is not None:
                    stage = 'consumer'
                    consumer_proof = qualify_consumer(disposable, role,
                        args.consumer_runtime, args.expected_consumer_revision)
                if args.retain_dir is not None:
                    stage = 'retention'
                    retained_digest = retain_archive(archive, args.retain_dir)
                stage = 'cleanup'
        result = {'status': 'qualified_disposable_restore',
                  'production_writes': 0, 'tables': {
                      name: value['rows'] for name, value in source_proofs.items()},
                  'row_digests_equal': True, 'v1_restored': args.source_schema == 'v1',
                  'source_schema_version': args.source_schema,
                  'source_schema_fingerprint': observed,
                  'v2_disposable_postimage': True}
        if consumer_proof is not None:
            result['consumer'] = consumer_proof
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
    if args.retain_dir is not None and args.retain_dir.exists():
        if result['status'] == 'qualified_disposable_restore' and retained_digest:
            try:
                result['private_recovery'] = finalize_retained(args.retain_dir,
                    retained_digest, source_proofs, observed_at, consumer_proof,
                    source_schema=args.source_schema)
            except Exception:
                result = {'status': 'withheld', 'stage': 'retained_finalize',
                          'private_partial_directory': str(args.retain_dir)}
        elif retained_digest is not None or result.get('stage') == 'retention':
            result['private_partial_directory'] = str(args.retain_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'qualified_disposable_restore' else 2


if __name__ == '__main__':
    raise SystemExit(main())
