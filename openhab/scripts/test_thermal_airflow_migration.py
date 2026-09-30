"""Disposable PostgreSQL proof for the source-only airflow vocabulary change."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4
import importlib.util
from urllib.parse import quote
import subprocess
import time

import psycopg2
from psycopg2 import sql
import pytest

import thermal_confirmation as confirmation
from thermal_model import airflow_migration as migration
from thermal_model import action_history, journal
from thermal_model.schema import ActionEvent
import thermal_state_backup


@dataclass(frozen=True)
class Database:
    admin_dsn: str = field(repr=False)
    runtime_dsn: str = field(repr=False)
    runtime_role: str
    owner: str = 'postgres'


@pytest.fixture
def database():
    suffix = uuid4().hex
    container = f'thermal-airflow-test-{suffix}'
    admin_password = uuid4().hex
    runtime_password = uuid4().hex
    role = f'thermal_airflow_{suffix}'
    subprocess.run(['docker', 'run', '--detach', '--rm', '--name', container,
                    '--publish', '127.0.0.1::5432', '--env',
                    f'POSTGRES_PASSWORD={admin_password}', 'postgres:16'],
                   check=True, capture_output=True, text=True)
    try:
        mapped = subprocess.run(['docker', 'port', container, '5432/tcp'],
                                check=True, capture_output=True, text=True).stdout.strip()
        port = int(mapped.rsplit(':', 1)[1])
        admin = f'postgresql://postgres:{quote(admin_password)}@127.0.0.1:{port}/postgres'
        runtime = f'postgresql://{role}:{quote(runtime_password)}@127.0.0.1:{port}/postgres'
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg2.connect(admin):
                    break
            except psycopg2.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        with psycopg2.connect(admin) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD %s').format(
                    sql.Identifier(role)), (runtime_password,))
        journal.migrate(admin, runtime_role=role, expected_owner='postgres')
        yield Database(admin, runtime, role)
    finally:
        subprocess.run(['docker', 'rm', '--force', '--volumes', container],
                       check=False, capture_output=True, text=True)


def candidate_fingerprint(database):
    """Rehearse the DDL then roll it back; never qualify by guesswork."""
    connection = psycopg2.connect(database.admin_dsn)
    try:
        with connection.cursor() as cursor:
            migration._replace_constraint(cursor)
            result = migration._fingerprint(cursor, runtime_role=database.runtime_role,
                                            expected_owner=database.owner)
        connection.rollback()
        return result
    finally:
        connection.close()


def test_v2_migration_preserves_legacy_rows_and_accepts_distinct_airflow(database, monkeypatch):
    original = ActionEvent('old-vent', 'old-receipt',
        datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 29, 12, tzinfo=timezone.utc),
        'vent', 'closed', 'manual_dm', 1.0)
    reader = journal.ActionJournal(database.runtime_dsn)
    assert reader.append(original)
    early = ActionEvent('too-early-window', 'early-receipt',
        original.received_at, original.effective_at,
        'window', 'open', 'nostr_confirmed', 1.0)
    monkeypatch.setattr(journal, 'V2_WRITE_RELEASE_READY', True)
    with pytest.raises(journal.SchemaMismatch, match='exact schema'):
        reader.append_batch((early,), (), vocabulary_version=2,
            runtime_role=database.runtime_role, expected_owner=database.owner)
    assert reader.events_for_receipt('early-receipt') == ()
    candidate = candidate_fingerprint(database)
    assert candidate == migration.V2_FINGERPRINT
    assert candidate != migration.LEGACY_FINGERPRINT
    assert journal.audit_schema(database.admin_dsn, runtime_role=database.runtime_role,
                                expected_owner=database.owner)['fingerprint'] == migration.LEGACY_FINGERPRINT
    monkeypatch.setattr(migration, 'V2_FINGERPRINT', candidate)
    monkeypatch.setattr(migration, 'RELEASE_READY', True)
    result = migration.migrate_v2(database.admin_dsn,
        runtime_role=database.runtime_role, expected_owner=database.owner)
    assert result == {'status': 'migrated_v2', 'fingerprint': candidate}
    assert migration.audit_v2(database.admin_dsn,
        runtime_role=database.runtime_role, expected_owner=database.owner)['status'] == 'exact_v2'
    assert migration.migrate_v2(database.admin_dsn,
        runtime_role=database.runtime_role, expected_owner=database.owner)['status'] == 'already_exact_v2'
    with pytest.raises(journal.SchemaMismatch):
        journal.audit_schema(database.admin_dsn, runtime_role=database.runtime_role,
                             expected_owner=database.owner)

    now = datetime(2026, 9, 29, 17, 30, tzinfo=timezone.utc)
    actions = tuple(ActionEvent(f'new-{name}', 'new-receipt', now, now,
        name, state, 'nostr_confirmed', 1.0)
        for name, state in [('window', 'closed'), ('skylight', 'open')])
    with pytest.raises(journal.SchemaMismatch, match='writer role mismatch'):
        reader.append_batch(actions, (), vocabulary_version=2,
            runtime_role='wrong_runtime_role', expected_owner=database.owner)
    assert reader.events_for_receipt('new-receipt') == ()
    assert reader.append_batch(actions, (), vocabulary_version=2,
        runtime_role=database.runtime_role, expected_owner=database.owner) == 2
    assert reader.events_for_receipt('old-receipt') == (original,)
    assert {event.event_id: event for event in reader.events_for_receipt('new-receipt')} == {
        event.event_id: event for event in actions}
    corrected = ActionEvent('window-correction', 'correction-receipt', now, now,
        'window', 'open', 'nostr_confirmed', 1.0,
        supersedes='new-window')
    assert reader.append_batch((corrected,), (), vocabulary_version=2,
        runtime_role=database.runtime_role, expected_owner=database.owner) == 1
    assert reader.events_for_receipt('correction-receipt') == (corrected,)
    wrong_action = ActionEvent('wrong-action-correction', 'wrong-action-receipt',
        now, now, 'skylight', 'closed', 'nostr_confirmed', 1.0,
        supersedes='new-window')
    with pytest.raises(psycopg2.IntegrityError):
        reader.append_batch((wrong_action,), (), vocabulary_version=2,
            runtime_role=database.runtime_role, expected_owner=database.owner)
    assert reader.events_for_receipt('wrong-action-receipt') == ()
    assert migration.audit_v2(database.admin_dsn,
        runtime_role=database.runtime_role, expected_owner=database.owner)['fingerprint'] == candidate


def test_bad_v2_fingerprint_rolls_back_constraint_atomically(database, monkeypatch):
    candidate = candidate_fingerprint(database)
    monkeypatch.setattr(migration, 'V2_FINGERPRINT', '0' * 64)
    monkeypatch.setattr(migration, 'RELEASE_READY', True)
    with pytest.raises(journal.SchemaMismatch, match='postimage'):
        migration.migrate_v2(database.admin_dsn,
            runtime_role=database.runtime_role, expected_owner=database.owner)
    assert journal.audit_schema(database.admin_dsn, runtime_role=database.runtime_role,
                                expected_owner=database.owner)['fingerprint'] == migration.LEGACY_FINGERPRINT
    assert candidate != migration.LEGACY_FINGERPRINT


def test_restored_consumer_probe_preserves_legacy_support_on_v2(database, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('thermal_live_restore',
        root/'scripts/qualify-thermal-journal-live-restore.py')
    qualifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualifier)
    import thermal_intel
    original = ActionEvent('consumer-original-vent', 'consumer-original-receipt',
        datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 12, tzinfo=timezone.utc), 'vent', 'closed', 'manual_dm', 1.)
    reader = journal.ActionJournal(database.runtime_dsn)
    assert reader.append(original)
    monkeypatch.setattr(migration, 'RELEASE_READY', True)
    migration.migrate_v2(database.admin_dsn, runtime_role=database.runtime_role,
                        expected_owner=database.owner)
    params = psycopg2.extensions.parse_dsn(database.admin_dsn)
    proof = qualifier.qualify_consumer(params, database.runtime_role,
        root/'openhab/scripts', thermal_intel._code_revision())
    assert proof['status'] == 'installed_consumer_qualified'
    assert proof['runtime_role_verified'] is True and proof['connection_read_only'] is True
    assert proof['distinct_fixture_observations'] == 6
    assert proof['legacy_samples_unchanged'] is True and proof['legacy_support_rows'] == 1
    assert reader.events_for_receipt(original.idempotency_key) == (original,)
    assert migration.audit_v2(database.admin_dsn, runtime_role=database.runtime_role,
                             expected_owner=database.owner)['status'] == 'exact_v2'


def test_consumer_fixture_cannot_target_production_database():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('thermal_live_restore',
        root/'scripts/qualify-thermal-journal-live-restore.py')
    qualifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qualifier)
    with pytest.raises(ValueError, match='disposable'):
        qualifier.qualify_consumer({'host': '127.0.0.1', 'port': '5432', 'dbname': 'openhab'},
            'thermal_runtime', root/'openhab/scripts', '0'*64)


def restore_qualifier():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('thermal_live_restore',
        root/'scripts/qualify-thermal-journal-live-restore.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retained_journal_is_private_exact_and_explicitly_not_full_bundle(database, tmp_path):
    qualifier = restore_qualifier()
    params = psycopg2.extensions.parse_dsn(database.admin_dsn)
    archive = tmp_path/'source.dump'
    fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        subprocess.run(['pg_dump', '--format=custom', '--schema=thermal_intel'],
            env=qualifier.postgres_env(params), stdout=output, stderr=subprocess.DEVNULL,
            check=True, timeout=30)
    destination = tmp_path/'retained'
    digest = qualifier.retain_archive(archive, destination)
    assert (destination/'journal.dump').read_bytes() == archive.read_bytes()
    assert destination.stat().st_mode & 0o077 == 0
    assert (destination/'journal.dump').stat().st_mode & 0o077 == 0
    assert not (destination/'manifest.json').exists()
    with psycopg2.connect(database.admin_dsn) as connection:
        proofs = qualifier.table_proofs(connection)
    proof = qualifier.finalize_retained(destination, digest, proofs,
        datetime.now(timezone.utc).isoformat())
    assert proof['full_collector_bundle'] is False
    assert proof['scope'] == 'thermal_intel_journal_only_recovery'
    import json
    manifest = json.loads((destination/'manifest.json').read_bytes())
    assert manifest['archive_sha256'] == digest
    assert manifest['table_proofs'] == proofs
    assert manifest['full_collector_bundle'] is False and manifest['off_host_copy'] is False
    assert (destination/'manifest.json').stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match='already exists'):
        qualifier.retain_archive(archive, destination)


def test_retained_archive_refuses_public_parent_or_existing_target(tmp_path):
    qualifier = restore_qualifier()
    public = tmp_path/'public'
    public.mkdir(mode=0o755)
    with pytest.raises(ValueError, match='private'):
        qualifier.retain_archive(tmp_path/'missing.dump', public/'retained')
    assert list(public.iterdir()) == []
    existing = tmp_path/'existing'
    existing.mkdir(mode=0o700)
    sentinel = existing/'do-not-overwrite'
    sentinel.write_text('owned fixture')
    with pytest.raises(ValueError, match='already exists'):
        qualifier.retain_archive(tmp_path/'missing.dump', existing)
    assert sentinel.read_text() == 'owned fixture'


def test_retained_manifest_refuses_changed_archive(tmp_path):
    qualifier = restore_qualifier()
    destination = tmp_path/'retained'
    destination.mkdir(mode=0o700)
    archive = destination/'journal.dump'
    archive.write_bytes(b'changed fixture')
    archive.chmod(0o600)
    with pytest.raises(ValueError, match='changed'):
        qualifier.finalize_retained(destination, '0'*64, {}, '2026-09-29T00:00:00+00:00')
    assert not (destination/'manifest.json').exists()


def test_position_ingress_retries_exact_v2_storage_without_duplicate(database, monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    operator = '1' * 64
    recipient = '2' * 64
    draft = {'version': 2, 'recipient': recipient, 'operators': [operator],
             'prompts': [{'operator': operator,
                          'issued_at': (now - timedelta(minutes=1)).isoformat(),
                          'expires_at': (now + timedelta(hours=1)).isoformat(),
                          'actions': {'window': 'open', 'skylight': 'closed'}}]}
    policy = confirmation.Policy.load(confirmation.canonical(draft), assign_ids=True)
    prompt = policy.prompts[0]
    rumor = {'pubkey': operator, 'created_at': int(now.timestamp()), 'kind': 14,
             'tags': [['p', recipient], ['e', prompt.event_id]], 'content': 'yes'}
    rumor['id'] = confirmation.event_id(rumor)

    class Decoder:
        def __init__(self, event):
            self.event = event

        def decode(self, raw, expected_recipient):
            assert raw == b'disposable encrypted fixture'
            assert expected_recipient == recipient
            return self.event

    monkeypatch.setattr(confirmation, 'POSITION_INGRESS_RELEASE_READY', True)
    monkeypatch.setattr(journal, 'V2_WRITE_RELEASE_READY', True)
    spool = confirmation.Spool(tmp_path / 'private')
    reader = journal.ActionJournal(database.runtime_dsn)
    sink = confirmation.JournalSink(reader, ActionEvent,
        runtime_role=database.runtime_role, expected_owner=database.owner)
    try:
        def ingest(at):
            return confirmation.ingest(b'disposable encrypted fixture', policy, spool,
                                       Decoder(rumor), sink, now=at)

        skipped = {**rumor, 'content': 'skip'}
        skipped['id'] = confirmation.event_id(skipped)
        with pytest.raises(confirmation.Retryable, match='preflight unavailable'):
            confirmation.ingest(b'disposable encrypted fixture', policy, spool,
                                Decoder(skipped), sink, now=now)
        assert spool.get(skipped['id']) is None
        with pytest.raises(confirmation.Retryable, match='preflight unavailable'):
            ingest(now)
        key = 'nostr:' + rumor['id']
        assert reader.events_for_receipt(key) == ()
        assert spool.get(rumor['id']) is None
        monkeypatch.setattr(migration, 'RELEASE_READY', True)
        assert migration.migrate_v2(database.admin_dsn,
            runtime_role=database.runtime_role, expected_owner=database.owner)['status'] == 'migrated_v2'
        original_events = reader.events_for_receipt

        def failed_readback(_key):
            raise psycopg2.OperationalError('disposable readback failure')

        monkeypatch.setattr(reader, 'events_for_receipt', failed_readback)
        with pytest.raises(confirmation.Retryable, match='journal unavailable'):
            ingest(now + timedelta(minutes=1))
        assert len(original_events(key)) == 2
        assert spool.get(rumor['id'])['acknowledgement'] is None
        monkeypatch.setattr(reader, 'events_for_receipt', original_events)
        receipt = ingest(now + timedelta(minutes=2))
        assert receipt['status'] == 'stored'
        assert {row.action: row.state for row in reader.events_for_receipt(key)} == {
            'window': 'open', 'skylight': 'closed'}
        assert ingest(now + timedelta(minutes=3)) == receipt
        assert len(reader.events_for_receipt(key)) == 2
        skip_draft = {**draft, 'prompts': [{**draft['prompts'][0],
                                          'actions': {'kiva': 'off'}}]}
        skip_policy = confirmation.Policy.load(
            confirmation.canonical(skip_draft), assign_ids=True)
        skip_rumor = {**rumor, 'tags': [['p', recipient],
                                      ['e', skip_policy.prompts[0].event_id]],
                      'content': 'skip'}
        skip_rumor['id'] = confirmation.event_id(skip_rumor)
        skip_receipt = confirmation.ingest(
            b'disposable encrypted fixture', skip_policy, spool,
            Decoder(skip_rumor), sink, now=now + timedelta(minutes=4))
        assert skip_receipt['status'] == 'no_action_recorded'
        assert reader.events_for_receipt('nostr:' + skip_rumor['id']) == ()
    finally:
        spool.close()


def test_gated_v2_reader_requires_exact_schema_and_keeps_airflow_separate(database, monkeypatch):
    event_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    origin = event_at + timedelta(minutes=4)
    events = tuple(ActionEvent(f'reader-{name}', 'reader-receipt', event_at, event_at,
        name, state, 'nostr_confirmed', 1.0)
        for name, state in [('window', 'open'), ('skylight', 'closed')])
    monkeypatch.setattr(action_history, 'V2_FETCH_RELEASE_READY', True)

    def fetch():
        return action_history.fetch_origin_actions(
            lambda: psycopg2.connect(database.runtime_dsn), origin=origin,
            vocabulary_version=2, runtime_role=database.runtime_role,
            expected_owner=database.owner)

    with pytest.raises(journal.SchemaMismatch, match='exact schema'):
        fetch()
    monkeypatch.setattr(migration, 'RELEASE_READY', True)
    assert migration.migrate_v2(database.admin_dsn,
        runtime_role=database.runtime_role, expected_owner=database.owner)['status'] == 'migrated_v2'
    monkeypatch.setattr(journal, 'V2_WRITE_RELEASE_READY', True)
    assert journal.ActionJournal(database.runtime_dsn).append_batch(events, (),
        vocabulary_version=2, runtime_role=database.runtime_role,
        expected_owner=database.owner) == 2
    result = fetch()
    assert result['vocabulary_version'] == 2
    assert result['actions']['window']['state'] == 'open'
    assert result['actions']['skylight']['state'] == 'closed'
    assert 'vent' in result['missing_actions']
    with pytest.raises(journal.SchemaMismatch, match='role mismatch'):
        action_history.fetch_origin_actions(
            lambda: psycopg2.connect(database.admin_dsn), origin=origin,
            vocabulary_version=2, runtime_role=database.runtime_role,
            expected_owner=database.owner)
    with pytest.raises(ValueError, match='distinct v2 journal role'):
        action_history.fetch_origin_actions(
            lambda: pytest.fail('database connection opened'), origin=origin,
            vocabulary_version=2)


def test_release_gate_refuses_before_database_connection():
    with pytest.raises(journal.SchemaMismatch, match='not release-qualified'):
        migration.migrate_v2('postgresql://invalid', runtime_role='reader',
                             expected_owner='postgres')


def test_v2_write_gate_and_legacy_vocabulary_refuse_before_database_connection():
    at = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    window = ActionEvent('gated-window', 'gated-receipt', at, at,
                         'window', 'open', 'nostr_confirmed', 1.0)
    disconnected = journal.ActionJournal('postgresql://invalid')
    with pytest.raises(journal.SchemaMismatch, match='not release-qualified'):
        disconnected.append_batch((window,), (), vocabulary_version=2,
            runtime_role='runtime', expected_owner='postgres')
    with pytest.raises(ValueError, match='outside selected'):
        disconnected.append_batch((window,), ())


def test_v3_private_bundle_restores_before_v2_migration(database, monkeypatch):
    source_event = ActionEvent('restored-vent', 'restored-receipt',
        datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 12, tzinfo=timezone.utc),
        'vent', 'closed', 'manual_dm', 1.0)
    assert journal.ActionJournal(database.runtime_dsn).append(source_event)
    with TemporaryDirectory(prefix='thermal-airflow-restore-') as temporary:
        root = Path(temporary)
        state, config, bundle = (root / name for name in ('state', 'config', 'bundle'))
        state.mkdir(mode=0o700)
        config.mkdir(mode=0o700)
        for name in thermal_state_backup.DATABASES:
            path = state / name
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE restore_marker(value TEXT NOT NULL)')
                connection.execute('INSERT INTO restore_marker VALUES (?)', (name,))
            path.chmod(0o600)
        policy, routes = (config / name for name in thermal_state_backup.CONFIG_FILES)
        for path in (policy, routes):
            path.write_bytes(b'{"disposable":true}')
            path.chmod(0o600)

        def export(target):
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600)
            with os.fdopen(descriptor, 'wb') as output:
                subprocess.run(['pg_dump', '--format=custom', '--schema=thermal_intel',
                                '--dbname=' + database.admin_dsn],
                               stdout=output, stderr=subprocess.PIPE, check=True, timeout=30)
                output.flush()
                os.fsync(output.fileno())

        manifest = thermal_state_backup.snapshot_state(
            state, bundle, policy=policy, routes=routes, journal_exporter=export)
        assert manifest['version'] == 3
        assert thermal_state_backup.verify_snapshot(bundle)['verified_files'] == 5
        for name in thermal_state_backup.DATABASES:
            with sqlite3.connect(bundle / name) as connection:
                assert connection.execute('SELECT value FROM restore_marker').fetchone() == (name,)

        restored_name = 'airflow_restore_' + uuid4().hex[:12]
        connection = psycopg2.connect(database.admin_dsn)
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(
                    sql.Identifier(restored_name)))
        finally:
            connection.close()
        restored_dsn = database.admin_dsn.rsplit('/', 1)[0] + '/' + restored_name
        restored_runtime_dsn = database.runtime_dsn.rsplit('/', 1)[0] + '/' + restored_name
        subprocess.run(['pg_restore', '--no-owner', '--exit-on-error',
                        '--single-transaction', '--dbname=' + restored_dsn,
                        str(bundle / thermal_state_backup.JOURNAL_FILE)],
                       capture_output=True, check=True, timeout=30)
        assert journal.audit_schema(restored_dsn, runtime_role=database.runtime_role,
                                    expected_owner=database.owner)['fingerprint'] == migration.LEGACY_FINGERPRINT
        assert journal.ActionJournal(restored_runtime_dsn).events_for_receipt('restored-receipt') == (source_event,)
        monkeypatch.setattr(migration, 'RELEASE_READY', True)
        assert migration.migrate_v2(restored_dsn, runtime_role=database.runtime_role,
                                    expected_owner=database.owner)['status'] == 'migrated_v2'
        assert migration.audit_v2(restored_dsn, runtime_role=database.runtime_role,
                                  expected_owner=database.owner)['status'] == 'exact_v2'
