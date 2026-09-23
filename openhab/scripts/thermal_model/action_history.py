"""Capture-safe, read-only action knowledge for historical forecast origins.

This is an epistemic snapshot, not proof that planned actions occurred and not
an advisory/actuation authority. A backdated receipt is unavailable until its
actual database creation time; later corrections cannot rewrite past origins.
"""
from datetime import datetime, timezone
from math import isfinite

from .schema import ACTION_KINDS, SOURCE_WEIGHTS

MAX_ROWS = 10000
MODES = frozenset(('spring', 'warm', 'fall_charge', 'winter'))


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware action timestamp required')
    return value.astimezone(timezone.utc)


def _select(rows, origin, *, kind):
    candidates = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
                'event_id', 'received_at', 'created_at', 'effective_at', 'name',
                'state', 'source', 'confidence', 'supersedes'}:
            raise ValueError('unexpected action-journal row')
        identity = row['event_id']
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError('duplicate or invalid action identity')
        seen.add(identity)
        received, created, effective = (_utc(row[key]) for key in
                                        ('received_at', 'created_at', 'effective_at'))
        if received > created or effective > received:
            raise ValueError('invalid action receipt chronology')
        if row['name'] not in (ACTION_KINDS if kind == 'action' else MODES):
            raise ValueError('unexpected action or mode')
        if row['source'] not in SOURCE_WEIGHTS or (type(row['confidence']) not in (int, float)
                or not isfinite(row['confidence']) or not 0 <= row['confidence'] <= 1):
            raise ValueError('invalid action source or confidence')
        if not isinstance(row['state'], str) or not row['state'] or len(row['state']) > 128:
            raise ValueError('invalid action state')
        if row['supersedes'] is not None and (not isinstance(row['supersedes'], str)
                                            or not row['supersedes']):
            raise ValueError('invalid action correction')
        if received <= origin and created <= origin and effective <= origin:
            candidates.append((row, received, created, effective))
    superseded = {row['supersedes'] for row, *_ in candidates if row['supersedes']}
    active = [entry for entry in candidates if entry[0]['event_id'] not in superseded]
    latest = {}
    for row, received, created, effective in active:
        name = row['name']
        rank = (effective, received, created, row['event_id'])
        if name not in latest or rank > latest[name][0]:
            latest[name] = (rank, {'state': row['state'], 'source': row['source'],
                                  'confidence': float(row['confidence']),
                                  'effective_at': effective, 'received_at': received,
                                  'created_at': created, 'event_id': row['event_id']})
    return {name: value for name, (_, value) in latest.items()}


def select_origin_actions(action_rows, mode_rows, *, origin):
    origin = _utc(origin)
    actions = _select(action_rows, origin, kind='action')
    modes = _select(mode_rows, origin, kind='mode')
    mode = max(modes.values(), key=lambda x: (x['effective_at'], x['received_at'],
                                               x['created_at'], x['event_id'])) if modes else None
    return {'source': 'thermal_intel_append_only_journal', 'origin': origin,
            'actions': actions, 'mode': mode,
            'missing_actions': sorted(set(ACTION_KINDS) - set(actions)),
            'status': 'as_of_snapshot_not_outcome_confirmation'}


def fetch_origin_actions(connection_factory, *, origin):
    """Read both journal tables in one bounded, repeatable-read transaction."""
    origin = _utc(origin)
    connection = connection_factory()
    try:
        if connection.get_transaction_status() != 0:
            raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '3000ms'")
            cursor.execute("SET LOCAL lock_timeout = '1000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone() != ('on',):
                raise ValueError('read-only transaction required')
            def read(table, name, state):
                cursor.execute(f'''SELECT e.event_id, e.received_at, r.created_at,
                           e.effective_at, e.{name}, e.{state}, e.source,
                           e.confidence, e.supersedes
                    FROM thermal_intel.{table} e
                    JOIN thermal_intel.message_receipts r
                      ON r.idempotency_key = e.idempotency_key
                    WHERE e.received_at <= %s AND r.created_at <= %s
                      AND e.effective_at <= %s
                    ORDER BY e.effective_at, e.received_at, e.event_id
                    LIMIT %s''', (origin, origin, origin, MAX_ROWS + 1))
                rows = cursor.fetchall()
                if len(rows) > MAX_ROWS:
                    raise ValueError('action journal row bound exceeded')
                return [dict(zip(('event_id', 'received_at', 'created_at',
                    'effective_at', 'name', 'state', 'source', 'confidence', 'supersedes'), row))
                    for row in rows]
            actions = read('action_events', 'action', 'state')
            modes = read('mode_events', 'mode', 'mode')
        return select_origin_actions(actions, modes, origin=origin)
    finally:
        connection.close()
