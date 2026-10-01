#!/usr/bin/env python3
"""Retain/rehearse an inactive household collector baseline, not a release.

Production PostgreSQL is read-only; restored v2 DDL/fixtures are disposable.
The private question is a PROPOSAL, never a signed observation or sending policy.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'openhab/scripts'))
import thermal_confirmation as t
import thermal_messaging as m
import thermal_state_backup as b


def helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


baseline = helper('thermal_baseline_preparer', 'prepare-thermal-collector-baseline.py')
recovery = helper('thermal_live_restore', 'qualify-thermal-journal-live-restore.py')


def empty_state(directory):
    b._private_directory(directory)
    for name, tables, version in (
            ('confirmations.sqlite3', ('receipts', 'terminal_prompts', 'corrections'), 1),
            ('delivery.sqlite3', ('delivery', 'inbox_ingested', 'inbox_refused'), 3)):
        path = directory/name
        b._private_file(path)
        with sqlite3.connect('file:'+str(path)+'?mode=ro', uri=True) as db:
            if db.execute('PRAGMA user_version').fetchone() != (version,):
                raise ValueError('baseline SQLite version differs')
            if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('baseline SQLite integrity failed')
            if any(db.execute('SELECT count(*) FROM '+table).fetchone() != (0,) for table in tables):
                raise ValueError('baseline SQLite contains live state')


def check_config(policy, routes, keyer=None):
    configured = t.Policy.load(m.read_private(policy))
    if (configured.version != 2 or configured.recipient != baseline.C
            or configured.operators != frozenset({baseline.O}) or len(configured.prompts) != 1
            or set(dict(configured.prompts[0].actions)) != {'window', 'skylight'}):
        raise ValueError('unexpected proposed baseline policy')
    m.Routes(m.read_private(routes), configured,
             keyer or m.Keyer(m.DEFAULT_NAK, m.DEFAULT_SHA256))
    return configured


def restore_sqlite_pair(bundle, directory):
    directory.mkdir(mode=0o700)
    for name in b.DATABASES:
        fd = os.open(directory/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output, (bundle/name).open('rb') as source:
            shutil.copyfileobj(source, output)
    empty_state(directory)
    # Reopen through the real application classes, not only sqlite integrity.
    with b.state_lock(directory):
        spool, outbox = t.Spool(directory), m.Outbox(directory)
        try:
            if outbox.rows() or spool.db.execute('SELECT count(*) FROM receipts').fetchone()[0] != 0:
                raise ValueError('restored baseline gained pending work')
        finally:
            outbox.close()
            spool.close()


def qualify(state, policy, routes, destination, runtime_root, expected_revision, *, keyer=None,
            source_schema='v1'):
    baseline.require_gates_closed()
    expected_schema = recovery.schema_fingerprint(source_schema)
    if policy.name != 'policy.proposed.json':
        raise ValueError('only explicitly proposed policy may be snapshotted here')
    configured = check_config(policy, routes, keyer)
    if configured.prompts[0].expires_at <= datetime.now(timezone.utc):
        raise ValueError('proposed trial question expired')
    empty_state(state)
    b._private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise ValueError('existing collector bundle must not be overwritten')
    container = 'thermal-baseline-bundle-'+uuid4().hex
    started = False
    source_proofs = None
    consumer = None
    temporary_path = None
    try:
        with closing(recovery.runtime_connection()[0]) as source:
            params = recovery.parse_dsn(os.environ['THERMAL_DATABASE_URL'])
            with source.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='3s'")
                cursor.execute("SET LOCAL statement_timeout='30s'")
                cursor.execute('LOCK TABLE thermal_intel.action_events, '
                    'thermal_intel.message_receipts, thermal_intel.mode_events IN ACCESS SHARE MODE')
                cursor.execute('SELECT current_user, pg_get_userbyid(nspowner) '
                    'FROM pg_namespace WHERE nspname=%s', ('thermal_intel',))
                role, owner = cursor.fetchone()
                if role != params['user'] or role == owner:
                    raise ValueError('restricted household role required')
                observed = recovery.airflow_migration._fingerprint(
                    cursor, runtime_role=role, expected_owner=owner)
                if observed != expected_schema:
                    raise ValueError('household baseline selected schema mismatch')
                cursor.execute('''SELECT count(*) FROM pg_stat_activity
                    WHERE datname=current_database() AND usename=%s AND pid<>pg_backend_pid()''', (role,))
                if cursor.fetchone() != (0,):
                    raise ValueError('other journal-role sessions are not quiescent')
                cursor.execute('SELECT pg_export_snapshot()')
                snapshot = cursor.fetchone()[0]
            source_proofs = recovery.table_proofs(source)
            def export(target):
                baseline.require_gates_closed()
                empty_state(state)
                recovery.export_archive(target, params, snapshot)
            b.snapshot_state(state, destination, policy=policy, routes=routes,
                             journal_exporter=export)
            source.rollback()
        verification = b.verify_snapshot(destination)
        if verification['version'] != 3 or verification['verified_files'] != 5:
            raise ValueError('complete baseline bundle required')
        if m.read_private(destination/'policy.json') != m.read_private(policy) or m.read_private(destination/'routes.json') != m.read_private(routes):
            raise ValueError('snapshot configuration differs')
        check_config(destination/'policy.json', destination/'routes.json', keyer)
        with TemporaryDirectory(prefix='thermal-baseline-bundle-restore-') as temporary:
            temporary_path = Path(temporary)
            restore_sqlite_pair(destination, temporary_path/'state')
            started = True
            disposable = recovery.disposable_database(container, uuid4().hex, role)
            restored_proofs = recovery.restore_and_rehearse(destination/'journal.dump', disposable, role,
                source_schema=source_schema)
            if restored_proofs != source_proofs:
                raise ValueError('household bundle journal rows differ')
            consumer = recovery.qualify_consumer(disposable, role, runtime_root, expected_revision)
    finally:
        if started:
            subprocess.run(['docker', 'rm', '--force', '--volumes', container],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=30)
            remaining = subprocess.run(['docker', 'ps', '-a', '--filter', 'name=^/'+container+'$',
                '--format', '{{.Names}}'], capture_output=True, check=True, timeout=10)
            if remaining.stdout.strip():
                raise ValueError('owned bundle container cleanup failed')
        if temporary_path is not None and temporary_path.exists():
            raise ValueError('owned restored SQLite cleanup failed')
    baseline.require_gates_closed()
    b.verify_snapshot(destination)
    result = {'status': 'inactive_household_baseline_bundle_qualified',
        'bundle': str(destination), 'version': 3, 'verified_components': 5,
        'policy_reviewed': False, 'sending_policy': False, 'signed_trial_verified': False,
        'operational_ready': False, 'collector_activated': False, 'production_writes': 0,
        'source_runtime_role_other_sessions': 0, 'source_table_proofs': source_proofs,
        'source_schema_version': source_schema, 'source_schema_fingerprint': observed,
        'restored_sqlite_baseline_rows': 0, 'consumer': consumer,
        'question_id': configured.prompts[0].event_id, 'off_host_copy': False}
    fd = os.open(destination/'qualification.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(t.canonical(result)+b'\n')
        output.flush()
        os.fsync(output.fileno())
    directory_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--routes', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--consumer-runtime', required=True, type=Path)
    parser.add_argument('--expected-consumer-revision', required=True)
    parser.add_argument('--source-schema', choices=('v1', 'v2'), default='v1')
    args = parser.parse_args()
    try:
        result = qualify(args.state_dir, args.policy, args.routes, args.destination,
                         args.consumer_runtime, args.expected_consumer_revision,
                         source_schema=args.source_schema)
    except Exception as error:
        print(json.dumps({'status': 'withheld', 'error_type': type(error).__name__,
            'private_bundle_directory': str(args.destination), 'collector_activated': False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
