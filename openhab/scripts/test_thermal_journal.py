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

from thermal_model.journal import (
    ActionJournal,
    IdempotencyConflict,
    SchemaMismatch,
    audit_schema,
    migrate,
)
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



def test_effective_action_read_includes_persistent_carry_in_and_kiva_context(
    journal,
):
    start = datetime(2025, 6, 1, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    events = (
        _action(
            event_id="carry-outdoor",
            key="carry-outdoor-receipt",
            action="outdoor_shade",
            state="installed",
            effective_at=start - timedelta(days=3),
        ),
        _action(
            event_id="carry-indoor",
            key="carry-indoor-receipt",
            action="indoor_shade",
            state="closed",
            effective_at=start - timedelta(days=2),
        ),
        _action(
            event_id="carry-vent",
            key="carry-vent-receipt",
            state="open",
            effective_at=start - timedelta(days=1),
        ),
        _action(
            event_id="carry-kiva-on",
            key="carry-kiva-on-receipt",
            action="kiva",
            state="on",
            effective_at=start - timedelta(hours=3),
        ),
        _action(
            event_id="carry-kiva-off",
            key="carry-kiva-off-receipt",
            action="kiva",
            state="off",
            effective_at=start - timedelta(hours=1),
        ),
        _action(
            event_id="carry-vent-close",
            key="carry-vent-close-receipt",
            state="closed",
            effective_at=start + timedelta(hours=1),
        ),
    )
    for event in events:
        assert journal.append(event)

    effective = journal.effective_events(start, end)

    assert [event.event_id for event in effective] == [
        "carry-outdoor",
        "carry-indoor",
        "carry-vent",
        "carry-kiva-on",
        "carry-kiva-off",
        "carry-vent-close",
    ]
    assert len({event.event_id for event in effective}) == len(effective)


def test_carry_in_kiva_state_and_cross_boundary_cooldown_exclude_passive_samples(
    journal,
):
    from thermal_model.dataset import build_samples

    start = datetime(2025, 7, 1, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=3)
    events = (
        _action(
            event_id="cross-kiva-on",
            key="cross-kiva-on-receipt",
            action="kiva",
            state="on",
            effective_at=start - timedelta(hours=3),
        ),
        _action(
            event_id="cross-kiva-off",
            key="cross-kiva-off-receipt",
            action="kiva",
            state="off",
            effective_at=start - timedelta(minutes=30),
        ),
        _action(
            event_id="cross-vent",
            key="cross-vent-receipt",
            state="open",
            effective_at=start - timedelta(days=1),
        ),
        _action(
            event_id="cross-indoor",
            key="cross-indoor-receipt",
            action="indoor_shade",
            state="open",
            effective_at=start - timedelta(days=1),
        ),
        _action(
            event_id="cross-outdoor",
            key="cross-outdoor-receipt",
            action="outdoor_shade",
            state="removed",
            effective_at=start - timedelta(days=1),
        ),
    )
    for event in events:
        assert journal.append(event)

    rows = {role: [] for role in ("air", "mass", "glazing", "outdoor", "radiation")}
    cursor = start
    while cursor < end:
        for role, value in (
            ("air", 70.0),
            ("mass", 68.0),
            ("glazing", 72.0),
            ("outdoor", 60.0),
            ("radiation", 0.0),
        ):
            rows[role].append((cursor, value))
        cursor += timedelta(minutes=5)

    effective = journal.effective_events(start, end)
    samples = build_samples(rows, effective, (), start, end)
    by_at = {sample.at: sample for sample in samples}

    assert by_at[start].vent_open == 1.0
    assert by_at[start].indoor_shade_closed == 0.0
    assert by_at[start].outdoor_shade_present == 0.0
    assert by_at[start].passive_fit_allowed is False
    assert by_at[start + timedelta(hours=1, minutes=25)].passive_fit_allowed is False
    assert by_at[start + timedelta(hours=1, minutes=30)].passive_fit_allowed is True


def test_schema_audit_proves_exact_shape_and_privileges(ephemeral_postgres):
    result = audit_schema(
        ephemeral_postgres.admin_dsn,
        runtime_role=ephemeral_postgres.runtime_role,
    )

    assert result["schema"] == "thermal_intel"
    assert result["tables"] == [
        "action_events",
        "message_receipts",
        "mode_events",
    ]
    assert result["functions"] == [
        "reject_action_correction_cycle",
        "reject_journal_mutation",
        "reject_mode_correction_cycle",
    ]
    assert result["triggers"] == [
        "action_events.reject_correction_cycle",
        "action_events.reject_mutation",
        "message_receipts.reject_mutation",
        "mode_events.reject_correction_cycle",
        "mode_events.reject_mutation",
    ]
    assert len(result["fingerprint"]) == 64
    assert result["fingerprint"] == "600061f21cf0d3f3ea7b19748e4b2bea96ce7e6c2cbfbecd56c533651b5432fa"


def test_migrate_refuses_partial_schema_before_mutating_it(ephemeral_postgres):
    backup = f"thermal_intel_exact_{uuid4().hex}"
    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER SCHEMA thermal_intel RENAME TO {}").format(
                    sql.Identifier(backup)
                )
            )
            cursor.execute("CREATE SCHEMA thermal_intel")
            cursor.execute("CREATE TABLE thermal_intel.partial_marker (id integer)")
    try:
        with pytest.raises(SchemaMismatch, match="exact schema audit"):
            migrate(
                ephemeral_postgres.admin_dsn,
                runtime_role=ephemeral_postgres.runtime_role,
            )
        with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'thermal_intel' ORDER BY table_name"
                )
                assert cursor.fetchall() == [("partial_marker",)]
    finally:
        with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA thermal_intel CASCADE")
                cursor.execute(
                    sql.SQL("ALTER SCHEMA {} RENAME TO thermal_intel").format(
                        sql.Identifier(backup)
                    )
                )


def test_schema_audit_and_migrate_reject_extra_index_drift(ephemeral_postgres):
    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE INDEX action_events_unapproved_idx "
                "ON thermal_intel.action_events (effective_at)"
            )
    try:
        with pytest.raises(SchemaMismatch, match="exact schema audit"):
            audit_schema(
                ephemeral_postgres.admin_dsn,
                runtime_role=ephemeral_postgres.runtime_role,
            )
        with pytest.raises(SchemaMismatch, match="exact schema audit"):
            migrate(
                ephemeral_postgres.admin_dsn,
                runtime_role=ephemeral_postgres.runtime_role,
            )
    finally:
        with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DROP INDEX IF EXISTS thermal_intel.action_events_unapproved_idx"
                )


def test_append_is_idempotent_and_timestamptz_round_trips(journal, ephemeral_postgres):
    event = _action()
    assert journal.append(event) is True
    assert journal.append(event) is False

    stored = journal.effective_events(
        event.effective_at - timedelta(minutes=1),
        event.effective_at + timedelta(minutes=1),
    )
    assert tuple(
        item for item in stored
        if event.effective_at - timedelta(minutes=1) <= item.effective_at
    ) == (event,)
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
    assert tuple(
        event for event in effective if event.effective_at >= original.effective_at
    ) == (correction,)
    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, supersedes FROM thermal_intel.action_events "
                "WHERE event_id IN ('original', 'correction') ORDER BY event_id"
            )
            assert cursor.fetchall() == [("correction", "original"), ("original", None)]


def test_action_correction_must_preserve_action_kind(journal, ephemeral_postgres):
    vent = _action(event_id="same-kind-vent", key="same-kind-vent-receipt")
    assert journal.append(vent)
    cross_kind = _action(
        event_id="cross-kind-kiva",
        key="cross-kind-kiva-receipt",
        action="kiva",
        state="on",
        supersedes=vent.event_id,
    )
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        journal.append(cross_kind)

    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT count(*) FROM thermal_intel.message_receipts "
                "WHERE idempotency_key = %s), "
                "(SELECT count(*) FROM thermal_intel.action_events WHERE event_id = %s)",
                (cross_kind.idempotency_key, cross_kind.event_id),
            )
            assert cursor.fetchone() == (0, 0)


@pytest.mark.parametrize(
    "key, links",
    [
        (
            "cycle-two-receipt",
            (("cycle-two-a", "cycle-two-b"), ("cycle-two-b", "cycle-two-a")),
        ),
        (
            "cycle-three-receipt",
            (
                ("cycle-three-a", "cycle-three-b"),
                ("cycle-three-b", "cycle-three-c"),
                ("cycle-three-c", "cycle-three-a"),
            ),
        ),
    ],
)
def test_action_correction_cycles_are_rejected_at_commit(
    journal, ephemeral_postgres, key, links
):
    events = tuple(
        _action(event_id=event_id, key=key, supersedes=supersedes)
        for event_id, supersedes in links
    )
    with pytest.raises(psycopg2.errors.CheckViolation, match="cycle"):
        journal.append_batch(events, (), payload=key.encode("ascii"))

    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT count(*) FROM thermal_intel.message_receipts "
                "WHERE idempotency_key = %s), "
                "(SELECT count(*) FROM thermal_intel.action_events "
                "WHERE idempotency_key = %s)",
                (key, key),
            )
            assert cursor.fetchone() == (0, 0)


def test_legitimate_action_correction_chain_remains_effective(journal):
    start = datetime(2026, 8, 25, 20, tzinfo=timezone.utc)
    first = _action(
        event_id="chain-first", key="chain-first-receipt", effective_at=start
    )
    second = _action(
        event_id="chain-second",
        key="chain-second-receipt",
        state="closed",
        effective_at=start + timedelta(minutes=10),
        supersedes=first.event_id,
    )
    third = _action(
        event_id="chain-third",
        key="chain-third-receipt",
        effective_at=start + timedelta(minutes=20),
        supersedes=second.event_id,
    )
    for event in (first, second, third):
        assert journal.append(event)

    assert tuple(
        event
        for event in journal.effective_events(start, start + timedelta(hours=1))
        if event.effective_at >= start
    ) == (third,)


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
    journal, ephemeral_postgres,
):
    guarded = _action(
        event_id="append-only-guard-row",
        key="append-only-guard-receipt",
        effective_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    assert journal.append(guarded)
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
                    "WHERE event_id = %s",
                    (guarded.event_id,),
                )
            connection.rollback()

    with psycopg2.connect(ephemeral_postgres.admin_dsn) as connection:
        with connection.cursor() as cursor:
            with pytest.raises(psycopg2.DatabaseError, match="append-only"):
                cursor.execute(
                    "DELETE FROM thermal_intel.action_events WHERE event_id = %s",
                    (guarded.event_id,),
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


def test_cli_schema_audit_is_read_only_and_never_prints_dsn(ephemeral_postgres):
    command = [
        sys.executable,
        str(Path(__file__).with_name("thermal_intel.py")),
        "schema-audit",
    ]
    environment = os.environ.copy()
    environment["THERMAL_DATABASE_ADMIN_URL"] = ephemeral_postgres.admin_dsn
    environment["THERMAL_DATABASE_RUNTIME_ROLE"] = ephemeral_postgres.runtime_role

    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    payload = json.loads(result.stdout)

    assert payload == {
        "fingerprint": "600061f21cf0d3f3ea7b19748e4b2bea96ce7e6c2cbfbecd56c533651b5432fa",
        "schema": "thermal_intel",
        "status": "exact",
    }
    assert ephemeral_postgres.admin_dsn not in result.stdout + result.stderr


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
