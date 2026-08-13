from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json

import psycopg2
from psycopg2 import sql

from .schema import ACTION_KINDS, SOURCE_WEIGHTS, ActionEvent, ModeEvent


SCHEMA = "thermal_intel"
ACTION_COLUMNS = (
    "event_id",
    "idempotency_key",
    "received_at",
    "effective_at",
    "action",
    "state",
    "source",
    "confidence",
    "interval_id",
    "note",
    "supersedes",
)
MODE_COLUMNS = (
    "event_id",
    "idempotency_key",
    "received_at",
    "effective_at",
    "mode",
    "source",
    "confidence",
    "note",
    "supersedes",
)


class IdempotencyConflict(ValueError):
    pass


def _check_values(values):
    return sql.SQL(", ").join(sql.Literal(value) for value in values)


def migrate(dsn, runtime_role=None):
    """Create only the application-owned schema and append-only journal tables."""
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}") .format(
                sql.Identifier(SCHEMA)
            ))
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {schema}.message_receipts (
                        idempotency_key TEXT PRIMARY KEY
                            CHECK (octet_length(idempotency_key) BETWEEN 1 AND 512),
                        payload_digest CHAR(64) NOT NULL
                            CHECK (payload_digest ~ '^[0-9a-f]{{64}}$'),
                        received_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp()
                    );
                    CREATE TABLE IF NOT EXISTS {schema}.action_events (
                        event_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL
                            REFERENCES {schema}.message_receipts(idempotency_key),
                        received_at TIMESTAMPTZ NOT NULL,
                        effective_at TIMESTAMPTZ NOT NULL,
                        action TEXT NOT NULL CHECK (action IN ({actions})),
                        state TEXT NOT NULL,
                        source TEXT NOT NULL CHECK (source IN ({sources})),
                        confidence DOUBLE PRECISION NOT NULL
                            CHECK (confidence >= 0.0 AND confidence <= 1.0),
                        interval_id TEXT,
                        note TEXT NOT NULL DEFAULT '',
                        supersedes TEXT UNIQUE
                            REFERENCES {schema}.action_events(event_id)
                            DEFERRABLE INITIALLY DEFERRED,
                        CHECK (supersedes IS NULL OR supersedes <> event_id)
                    );
                    CREATE TABLE IF NOT EXISTS {schema}.mode_events (
                        event_id TEXT PRIMARY KEY,
                        idempotency_key TEXT NOT NULL
                            REFERENCES {schema}.message_receipts(idempotency_key),
                        received_at TIMESTAMPTZ NOT NULL,
                        effective_at TIMESTAMPTZ NOT NULL,
                        mode TEXT NOT NULL
                            CHECK (mode IN ('spring', 'warm', 'fall_charge', 'winter')),
                        source TEXT NOT NULL CHECK (source IN ({sources})),
                        confidence DOUBLE PRECISION NOT NULL
                            CHECK (confidence >= 0.0 AND confidence <= 1.0),
                        note TEXT NOT NULL DEFAULT '',
                        supersedes TEXT UNIQUE
                            REFERENCES {schema}.mode_events(event_id)
                            DEFERRABLE INITIALLY DEFERRED,
                        CHECK (supersedes IS NULL OR supersedes <> event_id)
                    );
                    """
                ).format(
                    schema=sql.Identifier(SCHEMA),
                    actions=_check_values(ACTION_KINDS),
                    sources=_check_values(SOURCE_WEIGHTS),
                )
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE OR REPLACE FUNCTION {schema}.reject_journal_mutation()
                    RETURNS trigger
                    LANGUAGE plpgsql
                    AS $function$
                    BEGIN
                        RAISE EXCEPTION 'thermal_intel journal is append-only'
                            USING ERRCODE = '55000';
                    END;
                    $function$;
                    """
                ).format(schema=sql.Identifier(SCHEMA))
            )
            for table in ("message_receipts", "action_events", "mode_events"):
                cursor.execute(
                    sql.SQL("DROP TRIGGER IF EXISTS reject_mutation ON {}.{}").format(
                        sql.Identifier(SCHEMA), sql.Identifier(table)
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE TRIGGER reject_mutation BEFORE UPDATE OR DELETE ON {}.{} "
                        "FOR EACH ROW EXECUTE FUNCTION {}.reject_journal_mutation()"
                    ).format(
                        sql.Identifier(SCHEMA),
                        sql.Identifier(table),
                        sql.Identifier(SCHEMA),
                    )
                )
            cursor.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(
                    sql.Identifier(SCHEMA)
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM PUBLIC").format(
                    sql.Identifier(SCHEMA)
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON FUNCTION {}.reject_journal_mutation() FROM PUBLIC").format(
                    sql.Identifier(SCHEMA)
                )
            )
            if runtime_role:
                role = sql.Identifier(runtime_role)
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(SCHEMA), role
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA {} TO {}").format(
                        sql.Identifier(SCHEMA), role
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
                        "ON ALL TABLES IN SCHEMA {} FROM {}"
                    ).format(sql.Identifier(SCHEMA), role)
                )


def _aware(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")


def _canonical_bytes(actions, modes):
    def serializable(record):
        result = asdict(record)
        result["received_at"] = record.received_at.isoformat()
        result["effective_at"] = record.effective_at.isoformat()
        return result

    value = {
        "actions": [serializable(event) for event in actions],
        "modes": [serializable(event) for event in modes],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _payload_bytes(payload, actions, modes):
    if payload is None:
        return _canonical_bytes(actions, modes)
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, bytes):
        return payload
    raise TypeError("payload must be bytes, str, or None")


class ActionJournal:
    def __init__(self, dsn):
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self._dsn = dsn

    def append(self, event):
        if isinstance(event, ActionEvent):
            return bool(self.append_batch((event,), ()))
        if isinstance(event, ModeEvent):
            return bool(self.append_batch((), (event,)))
        raise TypeError("event must be ActionEvent or ModeEvent")

    def append_batch(self, actions, modes, payload=None):
        actions = tuple(actions)
        modes = tuple(modes)
        records = actions + modes
        if not records:
            raise ValueError("journal batch must contain an action or mode")
        if not all(isinstance(event, ActionEvent) for event in actions):
            raise TypeError("actions must contain only ActionEvent records")
        if not all(isinstance(event, ModeEvent) for event in modes):
            raise TypeError("modes must contain only ModeEvent records")
        key = records[0].idempotency_key
        received_at = records[0].received_at
        if not key or any(event.idempotency_key != key for event in records):
            raise ValueError("all batch records must share one non-empty idempotency key")
        if any(event.received_at != received_at for event in records):
            raise ValueError("all batch records must share received_at")
        for event in records:
            _aware(event.received_at, "received_at")
            _aware(event.effective_at, "effective_at")
        digest = sha256(_payload_bytes(payload, actions, modes)).hexdigest()

        with psycopg2.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO thermal_intel.message_receipts
                           (idempotency_key, payload_digest, received_at)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (idempotency_key) DO NOTHING
                       RETURNING idempotency_key""",
                    (key, digest, received_at),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        "SELECT payload_digest FROM thermal_intel.message_receipts "
                        "WHERE idempotency_key = %s",
                        (key,),
                    )
                    existing = cursor.fetchone()
                    if existing is None or existing[0].strip() != digest:
                        raise IdempotencyConflict(
                            "idempotency key was already used for different payload bytes"
                        )
                    return 0
                for event in actions:
                    cursor.execute(
                        """INSERT INTO thermal_intel.action_events
                               (event_id, idempotency_key, received_at, effective_at,
                                action, state, source, confidence, interval_id, note,
                                supersedes)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        tuple(getattr(event, name) for name in ACTION_COLUMNS),
                    )
                for event in modes:
                    cursor.execute(
                        """INSERT INTO thermal_intel.mode_events
                               (event_id, idempotency_key, received_at, effective_at,
                                mode, source, confidence, note, supersedes)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        tuple(getattr(event, name) for name in MODE_COLUMNS),
                    )
        return len(records)

    def effective_events(self, start, end):
        _aware(start, "start")
        _aware(end, "end")
        if end <= start:
            raise ValueError("end must be after start")
        with psycopg2.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT e.event_id, e.idempotency_key, e.received_at,
                              e.effective_at, e.action, e.state, e.source,
                              e.confidence, e.interval_id, e.note, e.supersedes
                       FROM thermal_intel.action_events e
                       WHERE e.effective_at >= %s AND e.effective_at < %s
                         AND NOT EXISTS (
                             SELECT 1 FROM thermal_intel.action_events correction
                             WHERE correction.supersedes = e.event_id
                         )
                       ORDER BY e.effective_at, e.received_at, e.event_id""",
                    (start, end),
                )
                return tuple(ActionEvent(*row) for row in cursor.fetchall())

    def effective_modes(self, start, end):
        _aware(start, "start")
        _aware(end, "end")
        if end <= start:
            raise ValueError("end must be after start")
        with psycopg2.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH effective AS (
                           SELECT m.*
                           FROM thermal_intel.mode_events m
                           WHERE NOT EXISTS (
                               SELECT 1 FROM thermal_intel.mode_events correction
                               WHERE correction.supersedes = m.event_id
                           )
                       ), prior AS (
                           SELECT event_id FROM effective
                           WHERE effective_at < %s
                           ORDER BY effective_at DESC, received_at DESC, event_id DESC
                           LIMIT 1
                       )
                       SELECT m.event_id, m.idempotency_key, m.received_at,
                              m.effective_at, m.mode, m.source, m.confidence,
                              m.note, m.supersedes
                       FROM effective m
                       WHERE (m.effective_at >= %s AND m.effective_at < %s)
                          OR m.event_id IN (SELECT event_id FROM prior)
                       ORDER BY m.effective_at, m.received_at, m.event_id""",
                    (start, start, end),
                )
                return tuple(ModeEvent(*row) for row in cursor.fetchall())

    def events_for_receipt(self, idempotency_key):
        with psycopg2.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT event_id, idempotency_key, received_at, effective_at,
                              action, state, source, confidence, interval_id, note,
                              supersedes
                       FROM thermal_intel.action_events
                       WHERE idempotency_key = %s
                       ORDER BY effective_at, received_at, event_id""",
                    (idempotency_key,),
                )
                return tuple(ActionEvent(*row) for row in cursor.fetchall())

    def modes_for_receipt(self, idempotency_key):
        with psycopg2.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT event_id, idempotency_key, received_at, effective_at,
                              mode, source, confidence, note, supersedes
                       FROM thermal_intel.mode_events
                       WHERE idempotency_key = %s
                       ORDER BY effective_at, received_at, event_id""",
                    (idempotency_key,),
                )
                return tuple(ModeEvent(*row) for row in cursor.fetchall())
