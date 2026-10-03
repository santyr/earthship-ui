"""Capture-safe, read-only action knowledge for historical forecast origins.

This is an epistemic snapshot, not proof that planned actions occurred and not
an advisory/actuation authority. A backdated receipt is unavailable until its
actual database creation time; later corrections cannot rewrite past origins.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import isfinite

from .schema import ACTION_KINDS, ACTION_KINDS_V2, SOURCE_WEIGHTS

MAX_ROWS = 10000
MAX_ORIGINS = 96
MAX_ORIGIN_WINDOW = timedelta(days=14)
MODES = frozenset(('spring', 'warm', 'fall_charge', 'winter'))
V2_FETCH_RELEASE_READY = False  # Exact household journal/runtime cutover pending.
MAX_HELD_SHADE_AGE = timedelta(hours=48)
MAX_HELD_SHADE_HORIZON = timedelta(hours=72)


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware action timestamp required')
    return value.astimezone(timezone.utc)


def _select(rows, origin, *, kind, action_kinds=ACTION_KINDS):
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
        if row['name'] not in (action_kinds if kind == 'action' else MODES):
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


def select_origin_actions(action_rows, mode_rows, *, origin, vocabulary_version=1):
    origin = _utc(origin)
    if type(vocabulary_version) is not int or vocabulary_version not in (1, 2):
        raise ValueError('unsupported action vocabulary version')
    action_kinds = ACTION_KINDS if vocabulary_version == 1 else ACTION_KINDS_V2
    actions = _select(action_rows, origin, kind='action', action_kinds=action_kinds)
    modes = _select(mode_rows, origin, kind='mode')
    mode = max(modes.values(), key=lambda x: (x['effective_at'], x['received_at'],
                                               x['created_at'], x['event_id'])) if modes else None
    result = {'source': 'thermal_intel_append_only_journal', 'origin': origin,
              'actions': actions, 'mode': mode,
              'missing_actions': sorted(set(action_kinds) - set(actions)),
              'status': 'as_of_snapshot_not_outcome_confirmation'}
    if vocabulary_version == 2:
        result['vocabulary_version'] = 2
    return result


def hold_confirmed_shades(forcings, *, snapshot, origin):
    """Pure scenario: hold recent confirmed shades, never label future actions.

    The caller must supply a qualified origin-time journal snapshot. This does
    not authenticate arbitrary dictionaries, read a database, choose a schedule,
    publish advice or command devices. Unsupported/unknown airflow remains an
    explicitly unresolved baseline assumption, never inferred from windows.
    This is not approved for live legacy three-regime dynamics: compound shade
    forcing can increase that model's solar gain. Use the qualified versioned
    joint-shade model and its own refit for operational forecasts.
    """
    from .operational_origin import _validate_actions

    origin = _utc(origin)
    _validate_actions(snapshot, origin)
    kinds = ACTION_KINDS if snapshot.get('vocabulary_version', 1) == 1 else ACTION_KINDS_V2
    mapping = {
        'indoor_shade': ('indoor_shade_closed', {'open': 0., 'closed': 1.}),
        'outdoor_shade': ('outdoor_shade_present',
                          {'absent': 0., 'removed': 0., 'present': 1., 'installed': 1.}),
    }
    held, overrides = {}, {}
    for name, (field, states) in mapping.items():
        event = snapshot['actions'].get(name)
        if event is None:
            continue
        confidence = event['confidence']
        if (type(confidence) not in (int, float) or not isfinite(confidence)
                or not 0 <= confidence <= 1):
            raise ValueError('invalid shade confidence')
        if (event['source'] not in {'nostr_confirmed', 'manual_dm'} or confidence == 0
                or origin-_utc(event['effective_at']) > MAX_HELD_SHADE_AGE):
            continue
        if event['state'] not in states or not isinstance(event['event_id'], str) or not event['event_id']:
            raise ValueError('invalid confirmed shade state or identity')
        held[name] = deepcopy(event)
        overrides[field] = states[event['state']]
    if not held:
        raise ValueError('no recent confirmed shade state for held scenario')
    if not isinstance(forcings, (list, tuple)) or not 1 <= len(forcings) <= 864:
        raise ValueError('bounded nonempty forcing grid required')
    fields = {'at', 'outdoor_f', 'radiation_wm2', 'vent_open',
              'indoor_shade_closed', 'outdoor_shade_present'}
    result, previous = [], None
    for row in forcings:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('closed held-shade forcing contract required')
        at = _utc(row['at'])
        if (not origin < at <= origin+MAX_HELD_SHADE_HORIZON
                or previous is None and at-origin > timedelta(minutes=5)
                or previous is not None and at-previous != timedelta(minutes=5)):
            raise ValueError('complete future five-minute forcing grid required')
        if any(type(row[key]) not in (int, float) or not isfinite(row[key])
               for key in fields-{'at'}):
            raise ValueError('finite forcing values required')
        if (not -40 <= row['outdoor_f'] <= 140 or not 0 <= row['radiation_wm2'] <= 1600
                or not 0 <= row['vent_open'] <= 2
                or any(not 0 <= row[field] <= 1 for field, _ in mapping.values())):
            raise ValueError('forcing values outside qualified bounds')
        result.append({**row, **overrides})
        previous = at
    return {'schema': 'earthship-held-shade-forcing/v1', 'origin': origin,
            'forcings': result, 'held_actions': held,
            'unresolved_forcing_actions': sorted(set(kinds)-set(held)),
            'interpretation': 'held_last_confirmed_shade_state_not_future_observation',
            'maximum_observation_age_hours': 48,
            'maximum_scenario_horizon_hours': 72,
            'future_action_evidence': False, 'actuation_authority': False}


def fetch_origin_actions(connection_factory, *, origin, vocabulary_version=1,
                         runtime_role=None, expected_owner=None):
    """Compatibility entrypoint for one exact origin-time snapshot."""
    return fetch_origin_actions_batch(connection_factory, origins=[origin],
        vocabulary_version=vocabulary_version, runtime_role=runtime_role,
        expected_owner=expected_owner)[0]


def fetch_origin_actions_batch(connection_factory, *, origins, vocabulary_version=1,
                               runtime_role=None, expected_owner=None):
    """Share one bounded read snapshot; select receipt knowledge per origin.

    Later receipts/corrections remain unavailable to earlier origins. This
    avoids two journal queries per forecast without mixing knowledge clocks.
    Results preserve caller order. No write, commit or runtime gate activation.
    """
    if not isinstance(origins, (list, tuple)) or not 1 <= len(origins) <= MAX_ORIGINS:
        raise ValueError('bounded nonempty origin list required')
    origins = tuple(_utc(origin) for origin in origins)
    if len(set(origins)) != len(origins) or max(origins)-min(origins) > MAX_ORIGIN_WINDOW:
        raise ValueError('unique origins within a bounded window required')
    last_origin = max(origins)
    if type(vocabulary_version) is not int or vocabulary_version not in (1, 2):
        raise ValueError('unsupported action vocabulary version')
    if vocabulary_version == 2 and not V2_FETCH_RELEASE_READY:
        raise ValueError('v2 action history read is not release-qualified')
    if vocabulary_version == 2 and (not runtime_role or not expected_owner
                                    or runtime_role == expected_owner):
        raise ValueError('distinct v2 journal role and owner required')
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
            if vocabulary_version == 2:
                from . import airflow_migration, journal

                cursor.execute('SELECT current_user')
                if cursor.fetchone() != (runtime_role,):
                    raise journal.SchemaMismatch('v2 journal reader role mismatch')
                observed = airflow_migration._fingerprint(
                    cursor, runtime_role=runtime_role, expected_owner=expected_owner)
                if observed != airflow_migration.V2_FINGERPRINT:
                    raise journal.SchemaMismatch('v2 journal exact schema audit failed')
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
                    LIMIT %s''', (last_origin, last_origin, last_origin, MAX_ROWS + 1))
                rows = cursor.fetchall()
                if len(rows) > MAX_ROWS:
                    raise ValueError('action journal row bound exceeded')
                return [dict(zip(('event_id', 'received_at', 'created_at',
                    'effective_at', 'name', 'state', 'source', 'confidence', 'supersedes'), row))
                    for row in rows]
            actions = read('action_events', 'action', 'state')
            modes = read('mode_events', 'mode', 'mode')
        return [select_origin_actions(actions, modes, origin=origin,
                                      vocabulary_version=vocabulary_version)
                for origin in origins]
    finally:
        connection.close()
