"""Exact schema selection and journal-only backup manifests."""
import importlib.util
import json
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
import subprocess
from uuid import uuid4

import psycopg2
import pytest
from psycopg2.extensions import parse_dsn
from thermal_model.schema import ActionEvent
from test_thermal_airflow_migration import database


SPEC = importlib.util.spec_from_file_location('live_journal_restore',
    Path(__file__).with_name('qualify-thermal-journal-live-restore.py'))
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_selected_schema_is_exact_not_auto_detected(version):
    expected = (restore.airflow_migration.LEGACY_FINGERPRINT if version == 'v1'
                else restore.airflow_migration.V2_FINGERPRINT)
    assert restore.schema_fingerprint(version) == expected


@pytest.mark.parametrize('version', [None, True, 2, 'v3', 'auto'])
def test_unknown_schema_cannot_relax_audit(version):
    with pytest.raises(ValueError):
        restore.schema_fingerprint(version)


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_retained_manifest_identifies_the_schema_actually_exported(tmp_path, monkeypatch, version):
    directory = tmp_path / 'new-retained-journal'
    directory.mkdir(mode=0o700)
    archive = directory / 'journal.dump'
    archive.write_bytes(b'qualified journal archive fixture')
    archive.chmod(0o600)
    digest = restore.backup._digest(archive)
    proofs = {table: {'rows': 0, 'sha256': 'a' * 64} for table in restore.TABLES}
    result = restore.finalize_retained(directory, digest, proofs,
        '2026-09-30T23:00:00+00:00', source_schema=version)
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    assert manifest['source_schema_fingerprint'] == restore.schema_fingerprint(version)
    assert manifest['source_schema_version'] == version
    assert result['full_collector_bundle'] is False
    assert manifest['off_host_copy'] is False
    assert manifest['table_proofs'] == proofs


def test_retained_manifest_still_defaults_to_legacy_for_existing_callers(tmp_path):
    directory = tmp_path / 'retained'
    directory.mkdir(mode=0o700)
    archive = directory / 'journal.dump'
    archive.write_bytes(b'fixture')
    archive.chmod(0o600)
    restore.finalize_retained(directory, restore.backup._digest(archive), {}, 'now')
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    assert manifest['source_schema_version'] == 'v1'


@pytest.mark.parametrize('damage', ['production-port', 'production-db', 'nonlocal', 'wrong-role'])
def test_restore_refuses_non_disposable_targets_before_any_subprocess(monkeypatch, damage):
    params = {'host': '127.0.0.1', 'port': 54321, 'dbname': 'postgres',
              'user': 'postgres', 'password': 'disposable fixture only'}
    role = 'fixture_reader'
    if damage == 'production-port': params['port'] = 5432
    elif damage == 'production-db': params['dbname'] = 'openhab'
    elif damage == 'nonlocal': params['host'] = '192.0.2.1'
    elif damage == 'wrong-role': role = 'unsafe role'
    monkeypatch.setattr(restore.subprocess, 'run', lambda *_args, **_kwargs:
                        pytest.fail('no command may touch a non-disposable target'))
    with pytest.raises(ValueError, match='disposable restore target'):
        restore.restore_and_rehearse(Path('unused'), params, role, source_schema='v2')


@pytest.mark.parametrize('source_schema,selected', [('v1', 'v1'), ('v2', 'v2'),
                                                   ('v1', 'v2'), ('v2', 'v1')])
def test_real_archive_restore_requires_exact_selected_schema(database, tmp_path, monkeypatch,
                                                            source_schema, selected):
    """Both databases are disposable; fixture rows are never household evidence."""
    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert restore.journal.ActionJournal(database.admin_dsn).append(ActionEvent(
        'fixture-vent', 'fixture-receipt', now, now, 'vent', 'closed', 'manual_dm', 1.0))
    if source_schema == 'v2':
        with psycopg2.connect(database.admin_dsn) as connection:
            with connection.cursor() as cursor:
                restore.airflow_migration._replace_constraint(cursor)
                cursor.execute('''INSERT INTO thermal_intel.action_events
                    (event_id,idempotency_key,received_at,effective_at,action,state,source,confidence)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                    ('fixture-window', 'fixture-receipt', now, now, 'window', 'open', 'manual_dm', 1.0))
    archive = tmp_path / 'journal.dump'
    source_params = parse_dsn(database.admin_dsn)
    with closing(psycopg2.connect(database.admin_dsn)) as source:
        source.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with source.cursor() as cursor:
            cursor.execute('SELECT pg_export_snapshot()')
            snapshot = cursor.fetchone()[0]
        expected_proofs = restore.table_proofs(source)
        restore.export_archive(archive, source_params, snapshot)
    name = 'thermal-live-restore-test-' + uuid4().hex
    try:
        params = restore.disposable_database(name, uuid4().hex, database.runtime_role)
        if source_schema == 'v2' or selected != source_schema:
            monkeypatch.setattr(restore.airflow_migration, '_replace_constraint',
                lambda *_args: pytest.fail('v2 restore or schema mismatch must never rerun DDL'))
        if selected != source_schema:
            with pytest.raises(ValueError, match='restored journal schema mismatch'):
                restore.restore_and_rehearse(archive, params, database.runtime_role,
                                            source_schema=selected)
            with psycopg2.connect(**params) as connection:
                with connection.cursor() as cursor:
                    fingerprint = restore.airflow_migration._fingerprint(cursor,
                        runtime_role=database.runtime_role, expected_owner='postgres')
            assert fingerprint == restore.schema_fingerprint(source_schema)
        else:
            proofs = restore.restore_and_rehearse(archive, params, database.runtime_role,
                                                source_schema=selected)
            assert proofs == expected_proofs
            assert proofs['action_events']['rows'] == (2 if source_schema == 'v2' else 1)
    finally:
        subprocess.run(['docker', 'rm', '--force', '--volumes', name],
                       check=False, capture_output=True, timeout=30)
