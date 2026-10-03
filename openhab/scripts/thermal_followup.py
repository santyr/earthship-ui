"""Bounded, default-off automatic thermal follow-up planning.

No signer, relay, journal, forecast, actuator or service access. Caller supplies
immutable publication evidence and holds the collector state lock. Reservations
live inside its existing backed-up SQLite ledger, never a third state store.
This candidate is not yet wired into a production command or release bundle.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import re

from advisory_records import build_decision_record, build_result_record
import thermal_confirmation as t

MAX_CANDIDATES = 256
MAX_RESERVATIONS = 4096
POLICY_VERSION = 'forecast-intel-thermal-v1'
AUTOMATIC_RELEASE_READY = False


@dataclass(frozen=True)
class Candidate:
    decision_id: str
    publication_result_id: str
    decision_json: str
    result_json: str
    actions: tuple[tuple[str, str], ...]
    available_at: datetime
    until: datetime


def require(condition, message):
    if not condition:
        raise t.Refused(message)


def _record(encoded, kind):
    require(isinstance(encoded, str), 'encoded advisory evidence required')
    payload = t.strict_json(encoded.encode(), limit=16 * 1024)
    try:
        if kind == 'decision':
            rebuilt = build_decision_record(decision_id=payload['decision_id'],
                issued_at=t.aware(payload['issued_at']), site_timezone=payload['site_timezone'],
                source_revision=payload['source_revision'], policy_version=payload['policy_version'],
                bank_epoch=payload['bank_epoch'], prediction_day=date.fromisoformat(payload['prediction_day']),
                advisory=payload['advisory'], inputs=payload['inputs'], thresholds=payload['thresholds'],
                notification_eligible=payload['notification']['eligible'],
                notification_suppressed=payload['notification']['suppressed'])
        else:
            rebuilt = build_result_record(result_id=payload['result_id'], decision_id=payload['decision_id'],
                observed_at=t.aware(payload['observed_at']), kind=payload['kind'],
                target=payload['target'], status=payload['status'])
        require(t.canonical(payload) == t.canonical(t.strict_json(rebuilt.encode())),
                'advisory evidence differs from canonical schema')
        return payload, rebuilt
    except (ValueError, KeyError, TypeError, OverflowError):
        raise t.Refused('invalid immutable advisory evidence') from None


def select_followup(rows, *, now, activated_at, bank_epoch):
    """Select latest accepted publication, then check its action opportunity.

    Never fall back to obsolete advice if the newest accepted publication says
    none, or its action window has not started. Windows only: the old advisory
    vocabulary provides no explicit skylight or shade recommendation. The 08:00
    close-up question opportunity is a notification policy, not a control timer.
    """
    now, activated_at = t.aware(now), t.aware(activated_at)
    require(activated_at <= now and isinstance(bank_epoch, str) and bool(bank_epoch),
            'explicit past activation and bank epoch required')
    require(isinstance(rows, (list, tuple)) and len(rows) <= MAX_CANDIDATES,
            'follow-up evidence exceeds bounded inventory')
    publications = []
    for pair in rows:
        require(isinstance(pair, (list, tuple)) and len(pair) == 2, 'paired evidence required')
        decision, encoded_decision = _record(pair[0], 'decision')
        result, encoded_result = _record(pair[1], 'result')
        issued, observed = t.aware(decision['issued_at']), t.aware(result['observed_at'])
        require(result['decision_id'] == decision['decision_id']
                and result['kind'] == 'publication' and result['target'] == 'Thermal_Advisory'
                and issued <= observed <= now, 'publication parent, target or clock mismatch')
        if (result['status'] != 'accepted' or issued < activated_at
                or decision['bank_epoch'] != bank_epoch
                or decision['policy_version'] != POLICY_VERSION
                or decision['site_timezone'] != 'America/Denver'
                or re.fullmatch(r'[0-9a-f]{64}', decision['source_revision']) is None):
            continue
        require(issued.astimezone(t.DENVER).date().isoformat() == decision['prediction_day'],
                'advisory does not identify its actual publication day')
        publications.append((observed, issued, decision['decision_id'], result['result_id'],
                             decision, encoded_decision, encoded_result))
    if not publications:
        return None
    # UUID tie breakers make selection invariant to query/relay ordering.
    _, _, _, result_id, decision, encoded_decision, encoded_result = max(publications, key=lambda row: row[:4])
    day = date.fromisoformat(decision['prediction_day'])
    if decision['advisory'] == 'vent_tonight':
        available = t.aware(decision['targets']['action_transition']['start'])
        until = t.aware(decision['targets']['action_transition']['end'])
        actions = (('window', 'open'),)
    elif decision['advisory'] == 'close_up_tomorrow':
        available = t.aware(datetime.combine(day + timedelta(days=1), time(8), t.DENVER))
        until = t.aware(decision['targets']['weather_tomorrow']['end'])
        actions = (('window', 'closed'),)
    else:
        return None
    if not available <= now < until:
        return None
    return Candidate(decision['decision_id'], result_id, encoded_decision, encoded_result,
                     actions, available, until)


def fetch_publications(connection, *, now, activated_at, bank_epoch):
    """Read at most 256 recent publications using the existing restricted assessor.

    Caller supplies a dedicated connection, never an admin or capture writer.
    No schema/grants/records change. A repeatable read and short SQL timeouts
    bound the observation; an outer process timeout must also bound connection I/O.
    """
    now, activated_at = t.aware(now), t.aware(activated_at)
    require(activated_at <= now and isinstance(bank_epoch, str) and bool(bank_epoch),
            'explicit past activation and bank epoch required')
    connection.set_session(isolation_level='REPEATABLE READ', readonly=True, autocommit=False)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SET LOCAL statement_timeout=2000')
            cursor.execute('SET LOCAL lock_timeout=1000')
            cursor.execute('SELECT current_user')
            require(cursor.fetchone() == ('advisory_assessor',), 'restricted advisory reader required')
            cursor.execute('''SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
                FROM pg_roles WHERE rolname=current_user''')
            require(cursor.fetchone() == (False, False, False, False, False),
                    'elevated advisory reader refused')
            cursor.execute('''SELECT d.payload::text, r.payload::text,
                    d.decision_id::text, d.issued_at, d.bank_epoch, r.result_id::text, r.observed_at
                FROM energy_analytics.advisory_decisions d
                JOIN energy_analytics.advisory_results r USING (decision_id)
                WHERE d.bank_epoch=%s AND d.issued_at >= %s AND d.issued_at <= %s
                  AND r.observed_at <= %s AND r.payload->>'kind'='publication'
                  AND r.payload->>'target'='Thermal_Advisory'
                ORDER BY r.observed_at DESC, d.issued_at DESC, d.decision_id DESC, r.result_id DESC
                LIMIT %s''', (bank_epoch, max(activated_at, now - t.MAX_AGE), now, now, MAX_CANDIDATES + 1))
            rows = cursor.fetchall()
            require(len(rows) <= MAX_CANDIDATES, 'follow-up evidence exceeds bounded inventory')
            result = []
            for encoded_d, encoded_r, did, issued, epoch, rid, observed in rows:
                d, canonical_d = _record(encoded_d, 'decision')
                r, canonical_r = _record(encoded_r, 'result')
                require(d['decision_id'] == did and t.aware(d['issued_at']) == t.aware(issued)
                        and d['bank_epoch'] == epoch == bank_epoch and r['result_id'] == rid
                        and t.aware(r['observed_at']) == t.aware(observed),
                        'advisory relational provenance differs')
                result.append((canonical_d, canonical_r))
    return result


def initialize(db):
    """Add reservation table to an exclusively held ledger; no version rewrite."""
    require(not db.in_transaction, 'follow-up initialization needs idle connection')
    db.execute('''CREATE TABLE IF NOT EXISTS automatic_questions (
        local_day TEXT NOT NULL PRIMARY KEY,
        decision_id TEXT NOT NULL UNIQUE,
        publication_result_id TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        result_json TEXT NOT NULL,
        prompt_json TEXT NOT NULL,
        collector TEXT NOT NULL,
        operator TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL)''')
    db.commit()
    columns = tuple(row[1] for row in db.execute('PRAGMA table_info(automatic_questions)'))
    require(columns == ('local_day', 'decision_id', 'publication_result_id', 'decision_json',
                        'result_json', 'prompt_json', 'collector', 'operator', 'evidence_sha256'),
            'automatic question schema differs')
    unique_keys = set()
    for index in db.execute('PRAGMA index_list(automatic_questions)'):
        if index[2] == 1:
            # SQLite-generated names only; never interpolate stored identifiers.
            require(re.fullmatch(r'sqlite_autoindex_automatic_questions_\d+', index[1]) is not None,
                    'automatic question index differs')
            unique_keys.add(tuple(row[2] for row in db.execute('PRAGMA index_info(' + index[1] + ')')))
    require(unique_keys == {('local_day',), ('decision_id',)}, 'automatic question uniqueness differs')


def _authority(policy):
    require(isinstance(policy, t.Policy) and policy.version == 2 and len(policy.operators) == 1,
            'automatic follow-ups require exactly one v2 operator')
    return next(iter(policy.operators))


def _evidence_digest(decision, result):
    return sha256(t.canonical([t.strict_json(decision.encode()), t.strict_json(result.encode())])).hexdigest()


def _retained(row, policy):
    operator = _authority(policy)
    day, did, rid, decision, result, prompt, collector, stored_operator, digest = tuple(row)
    require(collector == policy.recipient and stored_operator == operator
            and digest == _evidence_digest(decision, result), 'reserved question authority or evidence changed')
    restored = t.Policy.load(t.canonical(dict(version=2, recipient=collector, operators=[operator],
                                             prompts=[t.strict_json(prompt.encode())])))
    value = restored.prompts[0]
    parent, _ = _record(decision, 'decision')
    candidate = select_followup([(decision, result)], now=value.issued_at,
        activated_at=t.aware(parent['issued_at']), bank_epoch=parent['bank_epoch'])
    require(candidate is not None and candidate.decision_id == did
            and candidate.publication_result_id == rid and value.actions == candidate.actions
            and value.expires_at == candidate.until and value.operator == operator
            and value.correction_of is None
            and value.issued_at.astimezone(t.DENVER).date().isoformat() == day,
            'reserved question differs from its immutable advisory origin')
    return value


def retained_prompts(db, *, policy):
    """Reconstruct exact questions after crash/restore; never regenerate their IDs."""
    _authority(policy)
    rows = db.execute('SELECT * FROM automatic_questions ORDER BY local_day LIMIT ?',
                      (MAX_RESERVATIONS + 1,)).fetchall()
    require(len(rows) <= MAX_RESERVATIONS, 'reviewed automatic-question retention required')
    return tuple(_retained(row, policy) for row in rows)


def _manual_day_used(db, policy, day):
    if any(p.issued_at.astimezone(t.DENVER).date().isoformat() == day for p in policy.prompts):
        return True
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='questions'").fetchone():
        return False
    rows = db.execute('SELECT prompt_json, collector, operator FROM questions LIMIT ?',
                      (MAX_RESERVATIONS + 1,)).fetchall()
    require(len(rows) <= MAX_RESERVATIONS, 'reviewed question retention required')
    for encoded, collector, operator in rows:
        require(collector == policy.recipient and operator in policy.operators,
                'retained question authority differs')
        recorded = t.Policy.load(t.canonical(dict(version=2, recipient=collector,
            operators=sorted(policy.operators), prompts=[t.strict_json(encoded.encode())])))
        if recorded.prompts[0].issued_at.astimezone(t.DENVER).date().isoformat() == day:
            return True
    return False


def reserve_followup(db, candidate, *, policy, now):
    """Durably claim the Mountain day BEFORE signing or any network publication.

    Repeat calls return the original question; changed advice cannot replace it.
    No retries create a new question on a later date for the same decision. All
    callers must share the collector state lock (also used by its backups).
    This function has no permission to send: production release remains off.
    """
    operator, now = _authority(policy), t.aware(now)
    require(not db.in_transaction, 'reservation needs an exclusive idle connection')
    if candidate is None:
        return None
    require(isinstance(candidate, Candidate), 'validated automatic follow-up candidate required')
    parent, _ = _record(candidate.decision_json, 'decision')
    validated = select_followup([(candidate.decision_json, candidate.result_json)], now=now,
        activated_at=t.aware(parent['issued_at']), bank_epoch=parent['bank_epoch'])
    if validated is None:
        return None
    require(validated == candidate, 'follow-up candidate differs from immutable evidence')
    day = now.astimezone(t.DENVER).date().isoformat()
    db.execute('BEGIN IMMEDIATE')
    try:
        old = db.execute('SELECT * FROM automatic_questions WHERE local_day=?', (day,)).fetchone()
        if old is not None:
            value = _retained(old, policy)
            if now >= value.expires_at:
                value = None
        elif db.execute('SELECT 1 FROM automatic_questions WHERE decision_id=?',
                        (candidate.decision_id,)).fetchone():
            value = None
        elif _manual_day_used(db, policy, day):
            value = None  # Conservatively count separately reviewed/manual questions too.
        else:
            require(db.execute('SELECT count(*) FROM automatic_questions').fetchone()[0] < MAX_RESERVATIONS,
                    'reviewed automatic-question retention required')
            value = t.Policy.load(t.canonical(dict(version=2, recipient=policy.recipient,
                operators=[operator], prompts=[dict(operator=operator, issued_at=t.iso(now),
                    expires_at=t.iso(candidate.until), actions=dict(candidate.actions))])), assign_ids=True).prompts[0]
            db.execute('INSERT INTO automatic_questions VALUES (?,?,?,?,?,?,?,?,?)',
                (day, candidate.decision_id, candidate.publication_result_id,
                 candidate.decision_json, candidate.result_json, t.canonical(value.snapshot()).decode(),
                 policy.recipient, operator, _evidence_digest(candidate.decision_json, candidate.result_json)))
        db.commit()
        return value
    except BaseException:
        db.rollback()
        raise
