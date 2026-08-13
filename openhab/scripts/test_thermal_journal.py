import json
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

from thermal_model.journal import ActionJournal, IdempotencyConflict, migrate
from thermal_model.schema import ActionEvent, ModeEvent


@dataclass(frozen=True)
class EphemeralPostgres:
    admin_dsn: str
    runtime_dsn: str
    runtime_role: str


@pytest.fixture(scope="module")
def ephemeral_postgres():
    suffix = uuid4().hex
    container = f"thermal-journal-test-{suffix}"
    admin_password = uuid4().hex
    runtime_password = uuid4().hex
    runtime_role = f"thermal_runtime_{suffix}"
    run = subprocess.run(
        [
            "docker", "run", "--detach", "--rm", "--name", container,
            "--publish", "127.0.0.1::5432",
            "--env", f"POSTGRES_PASSWORD={admin_password}",
            "postgres:16",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert run.stdout.strip()
    try:
        port_output = subprocess.run(
            ["docker", "port", container, "5432/tcp"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        port = int(port_output.rsplit(":", 1)[1])
        admin_dsn = (
            f"postgresql://postgres:{quote(admin_password)}@127.0.0.1:{port}/postgres"
        )
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg2.connect(admin_dsn):
                    break
            except psycopg2.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

        with psycopg2.connect(admin_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(
                        sql.Identifier(runtime_role)
                    ),
                    (runtime_password,),
                )
        runtime_dsn = (
            f"postgresql://{runtime_role}:{quote(runtime_password)}"
            f"@127.0.0.1:{port}/postgres"
        )
        migrate(admin_dsn, runtime_role=runtime_role)
        # The setup path is intentionally repeatable.
        migrate(admin_dsn, runtime_role=runtime_role)
        yield EphemeralPostgres(admin_dsn, runtime_dsn, runtime_role)
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container],
            check=False,
            capture_output=True,
            text=True,
        )


@pytest.fixture
def journal(ephemeral_postgres):
    return ActionJournal(ephemeral_postgres.runtime_dsn)


def _action(event_id="vent-open", key="receipt-1", **changes):
    base = ActionEvent(
        event_id=event_id,
        idempotency_key=key,
        received_at=datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc),
        effective_at=datetime(2026, 8, 13, 20, 30, tzinfo=timezone.utc),
        action="vent",
        state="open",
        source="manual_dm",
        confidence=1.0,
    )
    return replace(base, **changes)


def _mode(event_id="mode-warm", key="mode-receipt", **changes):
    base = ModeEvent(
        event_id=event_id,
        idempotency_key=key,
        received_at=datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc),
        effective_at=datetime(2026, 8, 13, 18, 30, tzinfo=timezone.utc),
        mode="warm",
        source="manual_dm",
        confidence=1.0,
    )
    return replace(base, **changes)


def test_append_is_idempotent_and_timestamptz_round_trips(journal, ephemeral_postgres):
    event = _action()
    assert journal.append(event) is True
    assert journal.append(event) is False

    stored = journal.effective_events(
        event.effective_at - timedelta(minutes=1),
        event.effective_at + timedelta(minutes=1),
    )
    assert stored == (event,)
    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT data_type FROM information_schema.columns
                   WHERE table_schema = 'thermal_intel'
                     AND table_name = 'action_events'
                     AND column_name IN ('received_at', 'effective_at')
                   ORDER BY column_name"""
            )
            assert cursor.fetchall() == [
                ("timestamp with time zone",),
                ("timestamp with time zone",),
            ]


def test_receipt_key_replay_requires_identical_payload_digest(journal):
    event = _action(event_id="digest-event", key="digest-receipt")
    assert journal.append_batch((event,), (), payload=b"exact message bytes") == 1
    assert journal.append_batch((event,), (), payload=b"exact message bytes") == 0
    with pytest.raises(IdempotencyConflict, match="idempotency key"):
        journal.append_batch((event,), (), payload=b"different message bytes")


def test_correction_preserves_history_and_effective_read_returns_leaf(journal, ephemeral_postgres):
    original = _action(
        event_id="original",
        key="original-receipt",
        effective_at=datetime(2026, 8, 20, 20, 30, tzinfo=timezone.utc),
    )
    correction = _action(
        event_id="correction",
        key="correction-receipt",
        state="closed",
        effective_at=original.effective_at + timedelta(minutes=15),
        supersedes=original.event_id,
    )
    assert journal.append(original)
    assert journal.append(correction)

    effective = journal.effective_events(
        original.effective_at - timedelta(hours=1),
        correction.effective_at + timedelta(hours=1),
    )
    assert effective == (correction,)
    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, supersedes FROM thermal_intel.action_events "
                "WHERE event_id IN ('original', 'correction') ORDER BY event_id"
            )
            assert cursor.fetchall() == [("correction", "original"), ("original", None)]


def test_mode_query_includes_last_effective_mode_before_start_and_excludes_superseded(journal):
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    old = _mode(
        event_id="mode-old",
        key="mode-old-receipt",
        effective_at=start - timedelta(days=30),
    )
    prior = _mode(
        event_id="mode-prior",
        key="mode-prior-receipt",
        effective_at=start - timedelta(days=2),
        mode="fall_charge",
    )
    correction = _mode(
        event_id="mode-correction",
        key="mode-correction-receipt",
        effective_at=start - timedelta(days=1),
        mode="winter",
        supersedes=prior.event_id,
    )
    within = _mode(
        event_id="mode-within",
        key="mode-within-receipt",
        effective_at=start + timedelta(days=1),
        mode="spring",
    )
    for mode in (old, prior, correction, within):
        assert journal.append_batch((), (mode,)) == 1

    assert journal.effective_modes(start, start + timedelta(days=2)) == (
        correction,
        within,
    )


def test_mixed_batch_rolls_back_receipt_and_rows_on_foreign_key_failure(journal, ephemeral_postgres):
    key = "atomic-receipt"
    action = _action(event_id="atomic-action", key=key)
    bad_mode = _mode(
        event_id="atomic-mode", key=key, supersedes="missing-mode-target"
    )
    with pytest.raises(psycopg2.IntegrityError):
        journal.append_batch((action,), (bad_mode,), payload=b"atomic batch")

    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM thermal_intel.message_receipts WHERE idempotency_key = %s), "
                "(SELECT count(*) FROM thermal_intel.action_events WHERE event_id = %s), "
                "(SELECT count(*) FROM thermal_intel.mode_events WHERE event_id = %s)",
                (key, action.event_id, bad_mode.event_id),
            )
            assert cursor.fetchone() == (0, 0, 0)


def test_runtime_role_is_least_privilege_and_database_guards_are_append_only(
    ephemeral_postgres,
):
    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT has_table_privilege(%s, 'thermal_intel.action_events', 'SELECT'), "
                "has_table_privilege(%s, 'thermal_intel.action_events', 'INSERT'), "
                "has_table_privilege(%s, 'thermal_intel.action_events', 'UPDATE'), "
                "has_table_privilege(%s, 'thermal_intel.action_events', 'DELETE')",
                (ephemeral_postgres.runtime_role,) * 4,
            )
            assert cursor.fetchone() == (True, True, False, False)

    with psycopg2.connect(ephemeral_postgres.runtime_dsn) as connection:
        with connection.cursor() as cursor:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute(
                    "UPDATE thermal_intel.action_events SET note = 'mutated' "
                    "WHERE event_id = 'original'"
                )
            connection.rollback()

    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            with pytest.raises(psycopg2.DatabaseError, match="append-only"):
                cursor.execute(
                    "DELETE FROM thermal_intel.action_events WHERE event_id = 'original'"
                )
            connection.rollback()


def test_cli_journals_one_atomic_message_and_replay_reports_zero(
    journal, ephemeral_postgres, tmp_path
):
    message = tmp_path / "message.txt"
    message.write_text(
        "THERMAL\nmode: warm\nvent: 20:30-07:00\nnote: test receipt\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(Path(__file__).with_name("thermal_intel.py")),
        "journal",
        "--message-file",
        str(message),
        "--idempotency-key",
        "cli-receipt",
        "--received-at",
        "2026-08-13T18:00:00-06:00",
    ]
    environment = os.environ.copy()
    environment["THERMAL_DATABASE_URL"] = ephemeral_postgres.runtime_dsn
    first = subprocess.run(
        command, check=True, capture_output=True, text=True, env=environment
    )
    second = subprocess.run(
        command, check=True, capture_output=True, text=True, env=environment
    )
    first_receipt = json.loads(first.stdout)
    second_receipt = json.loads(second.stdout)
    assert first_receipt == {
        "action_event_ids": first_receipt["action_event_ids"],
        "idempotency_key": "cli-receipt",
        "inserted": 3,
        "mode_event_ids": first_receipt["mode_event_ids"],
    }
    assert len(first_receipt["action_event_ids"]) == 2
    assert len(first_receipt["mode_event_ids"]) == 1
    assert second_receipt["inserted"] == 0
    assert second_receipt["action_event_ids"] == first_receipt["action_event_ids"]
    assert second_receipt["mode_event_ids"] == first_receipt["mode_event_ids"]
    assert ephemeral_postgres.runtime_dsn not in first.stdout + first.stderr


def test_cli_has_no_transport_command_or_actuation_arguments():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("thermal_intel.py")), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "journal" in result.stdout
    assert not any(
        forbidden in result.stdout.lower()
        for forbidden in ("nostr", "relay", "shell", "openhab", "actuator", "command")
    )
