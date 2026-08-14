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


class SchemaMismatch(RuntimeError):
    pass


_SCHEMA_TABLES = ("action_events", "message_receipts", "mode_events")
_SCHEMA_FUNCTIONS = (
    "reject_action_correction_cycle",
    "reject_journal_mutation",
    "reject_mode_correction_cycle",
)
_SCHEMA_TRIGGERS = (
    "action_events.reject_correction_cycle",
    "action_events.reject_mutation",
    "message_receipts.reject_mutation",
    "mode_events.reject_correction_cycle",
    "mode_events.reject_mutation",
)
EXPECTED_SCHEMA_FINGERPRINT = "600061f21cf0d3f3ea7b19748e4b2bea96ce7e6c2cbfbecd56c533651b5432fa"


def _schema_shape(cursor, runtime_role=None):
    cursor.execute(
        """SELECT c.relname
             FROM pg_catalog.pg_class c
             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s
              AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            ORDER BY c.relname""",
        (SCHEMA,),
    )
    tables = [row[0] for row in cursor.fetchall()]

    cursor.execute(
        """SELECT c.relname, a.attnum, a.attname,
                  pg_catalog.format_type(a.atttypid, a.atttypmod),
                  a.atttypmod, a.attnotnull,
                  COALESCE(pg_catalog.pg_get_expr(d.adbin, d.adrelid), ''),
                  a.attidentity, a.attgenerated,
                  CASE WHEN a.attcollation = 0 THEN ''
                       ELSE cn.nspname || '.' || co.collname END
             FROM pg_catalog.pg_class c
             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
             LEFT JOIN pg_catalog.pg_attrdef d
                    ON d.adrelid = c.oid AND d.adnum = a.attnum
             LEFT JOIN pg_catalog.pg_collation co ON co.oid = a.attcollation
             LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid = co.collnamespace
            WHERE n.nspname = %s
              AND c.relkind IN ('r', 'p')
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum""",
        (SCHEMA,),
    )
    columns = [list(row) for row in cursor.fetchall()]

    cursor.execute(
        """SELECT c.relname, con.conname, con.contype,
                  con.condeferrable, con.condeferred, con.convalidated,
                  con.confupdtype, con.confdeltype, con.confmatchtype,
                  pg_catalog.pg_get_constraintdef(con.oid, true),
                  COALESCE(rn.nspname, ''), COALESCE(rc.relname, ''),
                  ARRAY(
                      SELECT a.attname
                        FROM unnest(con.conkey) WITH ORDINALITY AS key(attnum, ord)
                        JOIN pg_catalog.pg_attribute a
                          ON a.attrelid = con.conrelid AND a.attnum = key.attnum
                       ORDER BY key.ord
                  ),
                  ARRAY(
                      SELECT a.attname
                        FROM unnest(con.confkey) WITH ORDINALITY AS key(attnum, ord)
                        JOIN pg_catalog.pg_attribute a
                          ON a.attrelid = con.confrelid AND a.attnum = key.attnum
                       ORDER BY key.ord
                  )
             FROM pg_catalog.pg_constraint con
             JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             LEFT JOIN pg_catalog.pg_class rc ON rc.oid = con.confrelid
             LEFT JOIN pg_catalog.pg_namespace rn ON rn.oid = rc.relnamespace
            WHERE n.nspname = %s
            ORDER BY c.relname, con.conname""",
        (SCHEMA,),
    )
    constraints = [list(row) for row in cursor.fetchall()]

    cursor.execute(
        """SELECT c.relname, ic.relname, am.amname,
                  i.indisunique, i.indisprimary, i.indisvalid, i.indisready,
                  i.indislive, i.indisreplident, i.indnkeyatts, i.indnatts,
                  ARRAY(
                      SELECT pg_catalog.pg_get_indexdef(i.indexrelid, key, true)
                        FROM generate_series(1, i.indnatts) AS key
                       ORDER BY key
                  ),
                  COALESCE(pg_catalog.pg_get_expr(i.indpred, i.indrelid, true), ''),
                  pg_catalog.pg_get_indexdef(i.indexrelid)
             FROM pg_catalog.pg_index i
             JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_catalog.pg_class ic ON ic.oid = i.indexrelid
             JOIN pg_catalog.pg_am am ON am.oid = ic.relam
            WHERE n.nspname = %s
            ORDER BY c.relname, ic.relname""",
        (SCHEMA,),
    )
    indexes = [list(row) for row in cursor.fetchall()]

    cursor.execute(
        """SELECT c.relname, t.tgname, t.tgtype, t.tgenabled,
                  t.tgdeferrable, t.tginitdeferred,
                  pg_catalog.pg_get_triggerdef(t.oid, true),
                  p.proname
             FROM pg_catalog.pg_trigger t
             JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
             JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
            WHERE n.nspname = %s AND NOT t.tgisinternal
            ORDER BY c.relname, t.tgname""",
        (SCHEMA,),
    )
    triggers = [list(row) for row in cursor.fetchall()]

    cursor.execute(
        """SELECT p.proname,
                  pg_catalog.pg_get_function_identity_arguments(p.oid),
                  pg_catalog.pg_get_function_result(p.oid),
                  l.lanname, p.provolatile, p.proparallel, p.prosecdef,
                  p.proleakproof, p.proisstrict, p.prokind,
                  p.prosrc,
                  COALESCE(p.proconfig, ARRAY[]::text[])
             FROM pg_catalog.pg_proc p
             JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             JOIN pg_catalog.pg_language l ON l.oid = p.prolang
            WHERE n.nspname = %s
            ORDER BY p.proname,
                     pg_catalog.pg_get_function_identity_arguments(p.oid)""",
        (SCHEMA,),
    )
    functions = []
    for row in cursor.fetchall():
        values = list(row)
        values[10] = sha256(values[10].encode("utf-8")).hexdigest()
        functions.append(values)

    roles = [("public", "PUBLIC")]
    if runtime_role:
        roles.append(("runtime", runtime_role))
    privileges = {}
    for label, role in roles:
        if label == "public":
            cursor.execute(
                """SELECT COALESCE(bool_or(privilege_type = 'USAGE'), false),
                          COALESCE(bool_or(privilege_type = 'CREATE'), false)
                     FROM pg_catalog.pg_namespace n
                     LEFT JOIN LATERAL aclexplode(
                         COALESCE(n.nspacl, acldefault('n', n.nspowner))
                     ) acl ON true
                    WHERE n.nspname = %s AND acl.grantee = 0""",
                (SCHEMA,),
            )
        else:
            cursor.execute(
                """SELECT has_schema_privilege(%s, %s, 'USAGE'),
                          has_schema_privilege(%s, %s, 'CREATE')""",
                (role, SCHEMA, role, SCHEMA),
            )
        schema_privileges = list(cursor.fetchone())
        table_privileges = []
        for table in _SCHEMA_TABLES:
            qualified = f"{SCHEMA}.{table}"
            if label == "public":
                cursor.execute(
                    """SELECT
                           COALESCE(bool_or(privilege_type = 'SELECT'), false),
                           COALESCE(bool_or(privilege_type = 'INSERT'), false),
                           COALESCE(bool_or(privilege_type = 'UPDATE'), false),
                           COALESCE(bool_or(privilege_type = 'DELETE'), false),
                           COALESCE(bool_or(privilege_type = 'TRUNCATE'), false),
                           COALESCE(bool_or(privilege_type = 'REFERENCES'), false),
                           COALESCE(bool_or(privilege_type = 'TRIGGER'), false)
                       FROM pg_catalog.pg_class c
                       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                       LEFT JOIN LATERAL aclexplode(
                           COALESCE(c.relacl, acldefault('r', c.relowner))
                       ) acl ON true
                      WHERE n.nspname = %s AND c.relname = %s
                        AND acl.grantee = 0""",
                    (SCHEMA, table),
                )
            else:
                cursor.execute(
                    """SELECT has_table_privilege(%s, %s, 'SELECT'),
                              has_table_privilege(%s, %s, 'INSERT'),
                              has_table_privilege(%s, %s, 'UPDATE'),
                              has_table_privilege(%s, %s, 'DELETE'),
                              has_table_privilege(%s, %s, 'TRUNCATE'),
                              has_table_privilege(%s, %s, 'REFERENCES'),
                              has_table_privilege(%s, %s, 'TRIGGER')""",
                    (role, qualified) * 7,
                )
            table_privileges.append([table, *cursor.fetchone()])
        function_privileges = []
        for function in _SCHEMA_FUNCTIONS:
            qualified = f"{SCHEMA}.{function}()"
            if label == "public":
                cursor.execute(
                    """SELECT COALESCE(bool_or(privilege_type = 'EXECUTE'), false)
                         FROM pg_catalog.pg_proc p
                         JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                         LEFT JOIN LATERAL aclexplode(
                             COALESCE(p.proacl, acldefault('f', p.proowner))
                         ) acl ON true
                        WHERE n.nspname = %s AND p.proname = %s
                          AND acl.grantee = 0""",
                    (SCHEMA, function),
                )
            else:
                cursor.execute(
                    "SELECT has_function_privilege(%s, %s, 'EXECUTE')",
                    (role, qualified),
                )
            function_privileges.append([function, cursor.fetchone()[0]])
        privileges[label] = {
            "schema": schema_privileges,
            "tables": table_privileges,
            "functions": function_privileges,
        }

    return {
        "tables": tables,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "triggers": triggers,
        "functions": functions,
        "privileges": privileges,
    }


def _shape_fingerprint(shape):
    encoded = json.dumps(
        shape, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return sha256(encoded).hexdigest()


def _audit_cursor(cursor, runtime_role=None):
    try:
        shape = _schema_shape(cursor, runtime_role=runtime_role)
    except psycopg2.Error as exc:
        raise SchemaMismatch(
            "thermal_intel exact schema audit failed (missing or partial objects)"
        ) from exc
    fingerprint = _shape_fingerprint(shape)
    if EXPECTED_SCHEMA_FINGERPRINT is not None and fingerprint != EXPECTED_SCHEMA_FINGERPRINT:
        raise SchemaMismatch(
            "thermal_intel exact schema audit failed "
            f"(expected {EXPECTED_SCHEMA_FINGERPRINT}, observed {fingerprint})"
        )
    return {
        "schema": SCHEMA,
        "tables": shape["tables"],
        "functions": [row[0] for row in shape["functions"]],
        "triggers": [f"{row[0]}.{row[1]}" for row in shape["triggers"]],
        "fingerprint": fingerprint,
    }


def audit_schema(dsn, runtime_role=None):
    """Read-only exact catalog audit; never prints or returns a DSN."""
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            return _audit_cursor(cursor, runtime_role=runtime_role)


def _check_values(values):
    return sql.SQL(", ").join(sql.Literal(value) for value in values)


def _preflight_existing_schema(cursor, runtime_role=None):
    cursor.execute(
        "SELECT oid FROM pg_catalog.pg_namespace WHERE nspname = %s",
        (SCHEMA,),
    )
    schema_row = cursor.fetchone()
    if schema_row is None:
        return
    namespace_oid = schema_row[0]
    cursor.execute(
        """SELECT EXISTS (
               SELECT 1 FROM pg_catalog.pg_class WHERE relnamespace = %s
           ) OR EXISTS (
               SELECT 1 FROM pg_catalog.pg_proc WHERE pronamespace = %s
           )""",
        (namespace_oid, namespace_oid),
    )
    if cursor.fetchone()[0]:
        _audit_cursor(cursor, runtime_role=runtime_role)


def migrate(dsn, runtime_role=None):
    """Create only a new/empty schema or re-assert an already exact schema."""
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            _preflight_existing_schema(cursor, runtime_role=runtime_role)
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
                        supersedes TEXT UNIQUE,
                        CONSTRAINT action_events_event_id_action_key
                            UNIQUE (event_id, action),
                        CONSTRAINT action_events_supersedes_action_fkey
                            FOREIGN KEY (supersedes, action)
                            REFERENCES {schema}.action_events(event_id, action)
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
                """
                DO $migration$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'thermal_intel.action_events'::regclass
                          AND conname = 'action_events_supersedes_fkey'
                    ) THEN
                        ALTER TABLE thermal_intel.action_events
                            DROP CONSTRAINT action_events_supersedes_fkey;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'thermal_intel.action_events'::regclass
                          AND conname = 'action_events_event_id_action_key'
                    ) THEN
                        ALTER TABLE thermal_intel.action_events
                            ADD CONSTRAINT action_events_event_id_action_key
                            UNIQUE (event_id, action);
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'thermal_intel.action_events'::regclass
                          AND conname = 'action_events_supersedes_action_fkey'
                    ) THEN
                        ALTER TABLE thermal_intel.action_events
                            ADD CONSTRAINT action_events_supersedes_action_fkey
                            FOREIGN KEY (supersedes, action)
                            REFERENCES thermal_intel.action_events(event_id, action)
                            DEFERRABLE INITIALLY DEFERRED;
                    END IF;
                END;
                $migration$;
                """
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE OR REPLACE FUNCTION {schema}.reject_action_correction_cycle()
                    RETURNS trigger
                    LANGUAGE plpgsql
                    AS $function$
                    DECLARE
                        has_cycle BOOLEAN;
                    BEGIN
                        IF NEW.supersedes IS NULL THEN
                            RETURN NEW;
                        END IF;
                        WITH RECURSIVE ancestors(event_id, supersedes, path, cycle) AS (
                            SELECT event_id, supersedes, ARRAY[event_id], FALSE
                            FROM {schema}.action_events
                            WHERE event_id = NEW.supersedes
                            UNION ALL
                            SELECT parent.event_id,
                                   parent.supersedes,
                                   ancestors.path || parent.event_id,
                                   parent.event_id = ANY(ancestors.path)
                            FROM {schema}.action_events parent
                            JOIN ancestors ON parent.event_id = ancestors.supersedes
                            WHERE NOT ancestors.cycle
                        )
                        SELECT COALESCE(bool_or(event_id = NEW.event_id), FALSE)
                        INTO has_cycle
                        FROM ancestors;
                        IF has_cycle THEN
                            RAISE EXCEPTION 'thermal_intel action correction cycle'
                                USING ERRCODE = '23514';
                        END IF;
                        RETURN NEW;
                    END;
                    $function$;

                    CREATE OR REPLACE FUNCTION {schema}.reject_mode_correction_cycle()
                    RETURNS trigger
                    LANGUAGE plpgsql
                    AS $function$
                    DECLARE
                        has_cycle BOOLEAN;
                    BEGIN
                        IF NEW.supersedes IS NULL THEN
                            RETURN NEW;
                        END IF;
                        WITH RECURSIVE ancestors(event_id, supersedes, path, cycle) AS (
                            SELECT event_id, supersedes, ARRAY[event_id], FALSE
                            FROM {schema}.mode_events
                            WHERE event_id = NEW.supersedes
                            UNION ALL
                            SELECT parent.event_id,
                                   parent.supersedes,
                                   ancestors.path || parent.event_id,
                                   parent.event_id = ANY(ancestors.path)
                            FROM {schema}.mode_events parent
                            JOIN ancestors ON parent.event_id = ancestors.supersedes
                            WHERE NOT ancestors.cycle
                        )
                        SELECT COALESCE(bool_or(event_id = NEW.event_id), FALSE)
                        INTO has_cycle
                        FROM ancestors;
                        IF has_cycle THEN
                            RAISE EXCEPTION 'thermal_intel mode correction cycle'
                                USING ERRCODE = '23514';
                        END IF;
                        RETURN NEW;
                    END;
                    $function$;
                    """
                ).format(schema=sql.Identifier(SCHEMA))
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
            for table, function in (
                ("action_events", "reject_action_correction_cycle"),
                ("mode_events", "reject_mode_correction_cycle"),
            ):
                cursor.execute(
                    sql.SQL("DROP TRIGGER IF EXISTS reject_correction_cycle ON {}.{}").format(
                        sql.Identifier(SCHEMA), sql.Identifier(table)
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE CONSTRAINT TRIGGER reject_correction_cycle "
                        "AFTER INSERT ON {}.{} DEFERRABLE INITIALLY DEFERRED "
                        "FOR EACH ROW EXECUTE FUNCTION {}.{}()"
                    ).format(
                        sql.Identifier(SCHEMA),
                        sql.Identifier(table),
                        sql.Identifier(SCHEMA),
                        sql.Identifier(function),
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
            for function in (
                "reject_journal_mutation",
                "reject_action_correction_cycle",
                "reject_mode_correction_cycle",
            ):
                cursor.execute(
                    sql.SQL("REVOKE ALL ON FUNCTION {}.{}() FROM PUBLIC").format(
                        sql.Identifier(SCHEMA), sql.Identifier(function)
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
            _audit_cursor(cursor, runtime_role=runtime_role)


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
                    """WITH effective AS (
                           SELECT e.*
                           FROM thermal_intel.action_events e
                           WHERE NOT EXISTS (
                               SELECT 1
                               FROM thermal_intel.action_events correction
                               WHERE correction.supersedes = e.event_id
                           )
                       ), prior_by_action AS (
                           SELECT event_id
                           FROM (
                               SELECT event_id,
                                      row_number() OVER (
                                          PARTITION BY action
                                          ORDER BY effective_at DESC,
                                                   received_at DESC,
                                                   event_id DESC
                                      ) AS rank
                               FROM effective
                               WHERE effective_at < %s
                           ) ranked
                           WHERE rank = 1
                       ), kiva_recent AS (
                           SELECT event_id
                           FROM effective
                           WHERE action = 'kiva'
                             AND effective_at >= %s - interval '2 hours'
                             AND effective_at < %s
                       ), kiva_context AS (
                           SELECT event_id
                           FROM effective
                           WHERE action = 'kiva'
                             AND effective_at < %s - interval '2 hours'
                           ORDER BY effective_at DESC, received_at DESC, event_id DESC
                           LIMIT 1
                       )
                       SELECT e.event_id, e.idempotency_key, e.received_at,
                              e.effective_at, e.action, e.state, e.source,
                              e.confidence, e.interval_id, e.note, e.supersedes
                       FROM effective e
                       WHERE (e.effective_at >= %s AND e.effective_at < %s)
                          OR e.event_id IN (SELECT event_id FROM prior_by_action)
                          OR e.event_id IN (SELECT event_id FROM kiva_recent)
                          OR e.event_id IN (SELECT event_id FROM kiva_context)
                       ORDER BY e.effective_at, e.received_at, e.event_id""",
                    (start, start, start, start, start, end),
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
