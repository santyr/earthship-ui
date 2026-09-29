"""Disposable PostgreSQL proof for the source-only airflow vocabulary change."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import quote
import subprocess
import time

import psycopg2
from psycopg2 import sql
import pytest

from thermal_model import airflow_migration as migration
from thermal_model import journal
from thermal_model.schema import ActionEvent


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
    with pytest.raises(psycopg2.IntegrityError):
        reader.append(early)
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
    assert reader.append_batch(actions, ()) == 2
    assert reader.events_for_receipt('old-receipt') == (original,)
    assert {event.event_id: event for event in reader.events_for_receipt('new-receipt')} == {
        event.event_id: event for event in actions}
    corrected = ActionEvent('window-correction', 'correction-receipt', now, now,
        'window', 'open', 'nostr_confirmed', 1.0,
        supersedes='new-window')
    assert reader.append(corrected)
    assert reader.events_for_receipt('correction-receipt') == (corrected,)
    wrong_action = ActionEvent('wrong-action-correction', 'wrong-action-receipt',
        now, now, 'skylight', 'closed', 'nostr_confirmed', 1.0,
        supersedes='new-window')
    with pytest.raises(psycopg2.IntegrityError):
        reader.append(wrong_action)
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


def test_release_gate_refuses_before_database_connection():
    with pytest.raises(journal.SchemaMismatch, match='not release-qualified'):
        migration.migrate_v2('postgresql://invalid', runtime_role='reader',
                             expected_owner='postgres')
