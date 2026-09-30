"""Explicit, source-only thermal action-vocabulary migration.

The installed v1 runtime and collector remain authoritative. This module is
not called by normal journal creation, training or shadow publication. It
requires an exact preimage and a separately qualified v2 schema fingerprint;
an unsuccessful transaction leaves the v1 journal intact.
"""
from contextlib import closing

from psycopg2 import sql
import psycopg2

from . import journal
from .schema import ACTION_KINDS, ACTION_KINDS_V2


LEGACY_ACTIONS = ACTION_KINDS
V2_ACTIONS = ACTION_KINDS_V2
LEGACY_FINGERPRINT = journal.EXPECTED_SCHEMA_FINGERPRINT
# Exact normalized PostgreSQL 16 postimage from a disposable v1 replay.
V2_FINGERPRINT = "f3e09cdd6cbd82bcd34475485bbf326bbc4789f4bcb1f4e050d9fba213378790"
RELEASE_READY = False


def _fingerprint(cursor, *, runtime_role, expected_owner):
    return journal._shape_fingerprint(journal._schema_shape(
        cursor, runtime_role=runtime_role, expected_owner=expected_owner))


def _require_owner(cursor, expected_owner):
    if not expected_owner:
        raise ValueError("expected owner is required")
    cursor.execute("SELECT current_user = %s", (expected_owner,))
    if cursor.fetchone() != (True,):
        raise journal.SchemaMismatch("thermal action migration owner mismatch")


def _replace_constraint(cursor):
    cursor.execute("SET LOCAL lock_timeout = '3s'")
    cursor.execute("SET LOCAL statement_timeout = '15s'")
    cursor.execute("ALTER TABLE thermal_intel.action_events "
                   "DROP CONSTRAINT action_events_action_check")
    cursor.execute(sql.SQL("ALTER TABLE thermal_intel.action_events "
                           "ADD CONSTRAINT action_events_action_check "
                           "CHECK (action IN ({}))").format(
        journal._check_values(V2_ACTIONS)))


def audit_v2(dsn, *, runtime_role, expected_owner):
    """Read-only exact audit after a separately attended vocabulary cutover."""
    if not V2_FINGERPRINT:
        raise journal.SchemaMismatch("thermal v2 fingerprint not qualified")
    with closing(psycopg2.connect(dsn)) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            observed = _fingerprint(cursor, runtime_role=runtime_role,
                                    expected_owner=expected_owner)
    if observed != V2_FINGERPRINT:
        raise journal.SchemaMismatch("thermal v2 exact schema audit failed")
    return {"schema": journal.SCHEMA, "status": "exact_v2",
            "fingerprint": observed}


def migrate_v2(dsn, *, runtime_role, expected_owner, transaction_guard=None):
    """Change only the action CHECK inside one transaction after release gate."""
    if not RELEASE_READY or not V2_FINGERPRINT:
        raise journal.SchemaMismatch("thermal v2 migration not release-qualified")
    if not runtime_role or not expected_owner or runtime_role == expected_owner:
        raise ValueError("distinct runtime and owner roles required")
    if transaction_guard is not None and not callable(transaction_guard):
        raise ValueError("migration transaction guard must be callable")
    with closing(psycopg2.connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                _require_owner(cursor, expected_owner)
                if transaction_guard is not None:
                    transaction_guard(cursor, 'before')
                original = _fingerprint(cursor, runtime_role=runtime_role,
                                        expected_owner=expected_owner)
                if original == V2_FINGERPRINT:
                    return {"status": "already_exact_v2", "fingerprint": original}
                if original != LEGACY_FINGERPRINT:
                    raise journal.SchemaMismatch("thermal v1 preimage is not exact")
                _replace_constraint(cursor)
                observed = _fingerprint(cursor, runtime_role=runtime_role,
                                        expected_owner=expected_owner)
                if observed != V2_FINGERPRINT:
                    raise journal.SchemaMismatch("thermal v2 postimage is not exact")
                if transaction_guard is not None:
                    transaction_guard(cursor, 'after')
    return {"status": "migrated_v2", "fingerprint": observed}
