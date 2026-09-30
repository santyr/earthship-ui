#!/usr/bin/env python3
"""Exact journal-only preflight/apply; never activate collection or controls.

Use --apply only after explicit operator approval. Owner/runtime credentials
come solely from private systemd EnvironmentFiles; failures are sanitized.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import psycopg2
from psycopg2.extensions import parse_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_state_backup as backup
from thermal_model import airflow_migration as migration

def helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

recovery = helper('thermal_cutover_recovery', 'qualify-thermal-journal-live-restore.py')
baseline = helper('thermal_cutover_baseline', 'prepare-thermal-collector-baseline.py')


def require_runtime(revision):
    if not re.fullmatch('[0-9a-f]{64}', revision):
        raise ValueError('exact consumer pin required')
    env = dict(os.environ, PYTHONPATH='/home/sat/openhab/scripts', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-c',
        'import thermal_intel; print(thermal_intel._code_revision())'],
        cwd='/home/sat/openhab/scripts', env=env, capture_output=True, timeout=15, check=True)
    if result.stdout.decode().strip() != revision:
        raise ValueError('installed consumer pin changed')
    status = subprocess.run(['systemctl', '--user', 'show', '-p', 'ActiveState', '--value',
        'thermal-model-shadow.service', 'thermal-model-train.service'],
        capture_output=True, timeout=5, check=True).stdout.decode().split()
    if status != ['inactive', 'inactive']:
        raise ValueError('thermal jobs are not quiescent')
    baseline.require_gates_closed()


def retained_proofs(directory):
    verified = backup.verify_snapshot(directory)
    if verified['version'] != 3 or verified['verified_files'] != 5:
        raise ValueError('complete retained collector baseline required')
    path = directory / 'qualification.json'
    backup._private_file(path)
    if path.stat().st_size > 16384:
        raise ValueError('qualification receipt exceeds bound')
    receipt = json.loads(path.read_bytes())
    if (receipt.get('status') != 'inactive_household_baseline_bundle_qualified'
            or receipt.get('production_writes') != 0
            or receipt.get('collector_activated') is not False):
        raise ValueError('retained baseline was not qualified')
    proofs = receipt['source_table_proofs']
    if set(proofs) != set(recovery.TABLES):
        raise ValueError('complete table proofs required')
    return proofs


def transaction_guard(proofs):
    def guard(cursor, phase):
        if phase == 'before':
            cursor.execute("SET LOCAL lock_timeout='3s'")
            cursor.execute("SET LOCAL statement_timeout='15s'")
            cursor.execute('LOCK TABLE thermal_intel.action_events, '
                'thermal_intel.message_receipts, thermal_intel.mode_events IN ACCESS EXCLUSIVE MODE')
        if recovery.table_proofs(cursor.connection) != proofs:
            raise ValueError('journal rows differ from retained baseline')
    return guard


def run(directory, revision, *, apply=False):
    directory = Path(directory)
    require_runtime(revision)
    proofs = retained_proofs(directory)
    runtime = parse_dsn(os.environ['THERMAL_DATABASE_URL'])
    admin = parse_dsn(os.environ['THERMAL_DATABASE_ADMIN_URL'])
    for params in (runtime, admin):
        if (params.get('host') != '127.0.0.1' or str(params.get('port')) != '5432'
                or params.get('dbname') != 'openhab' or not params.get('password')):
            raise ValueError('exact private local connection required')
    role, owner = runtime['user'], admin['user']
    if role == owner:
        raise ValueError('distinct runtime and owner identities required')
    with closing(psycopg2.connect(os.environ['THERMAL_DATABASE_ADMIN_URL'], connect_timeout=3)) as connection:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            migration._require_owner(cursor, owner)
            observed = migration._fingerprint(cursor, runtime_role=role, expected_owner=owner)
            if observed != migration.LEGACY_FINGERPRINT:
                raise ValueError('exact legacy schema preimage required')
            cursor.execute('''SELECT count(*) FROM pg_stat_activity
                WHERE datname=current_database() AND pid<>pg_backend_pid()
                  AND (usename IN (%s,%s)
                       OR (state='active' AND query ILIKE %s))''',
                (role, owner, '%thermal_intel%'))
            if cursor.fetchone() != (0,):
                raise ValueError('other journal-role sessions or active journal queries exist')
        if recovery.table_proofs(connection) != proofs:
            raise ValueError('retained baseline row digests changed')
    result = {'status': 'qualified_journal_only_preflight', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'schema_fingerprint': observed, 'runtime_revision': revision,
        'unchanged_table_proofs': proofs, 'production_ddl_committed': False,
        'collector_activated': False, 'model_or_control_changed': False}
    if apply:
        require_runtime(revision)
        migration.RELEASE_READY = True  # Process-local authority for this approved DDL only.
        try:
            applied = migration.migrate_v2(os.environ['THERMAL_DATABASE_ADMIN_URL'],
                runtime_role=role, expected_owner=owner, transaction_guard=transaction_guard(proofs))
        finally:
            migration.RELEASE_READY = False
        migration.audit_v2(os.environ['THERMAL_DATABASE_ADMIN_URL'], runtime_role=role, expected_owner=owner)
        require_runtime(revision)
        result.update(status=applied['status'], schema_fingerprint=applied['fingerprint'],
            production_ddl_committed=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--expected-consumer-revision', required=True)
    parser.add_argument('--apply', action='store_true', help='Requires explicit operator journal-only approval')
    args = parser.parse_args()
    try:
        result = run(args.baseline, args.expected_consumer_revision, apply=args.apply)
    except Exception:
        raise SystemExit('Journal-only operation failed; inspect exact schema before retry; private diagnostics withheld') from None
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
