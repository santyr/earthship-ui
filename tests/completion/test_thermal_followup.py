"""Automatic follow-up selection/reservation: fixtures only, no DMs or journal."""
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from uuid import UUID

import pytest

import thermal_confirmation as t
from advisory_records import INPUT_FIELDS, THRESHOLD_FIELDS, build_decision_record, build_result_record
import thermal_followup as f

UTC = timezone.utc
NOW = datetime(2026, 10, 3, 3, tzinfo=UTC)  # October 2, 21:00 Mountain.
O, C = '1' * 64, '2' * 64


def policy():
    return t.Policy.load(t.canonical(dict(version=2, recipient=C, operators=[O], prompts=[])),
                         allow_empty=True)


def evidence(*, advisory='vent_tonight', issued=None, day=date(2026, 10, 2),
             status='accepted', number=1, result_number=101):
    issued = issued or datetime(2026, 10, 2, 12, 40, tzinfo=UTC)
    inputs = dict.fromkeys(INPUT_FIELDS, 90.0)
    inputs['next_three_highs_raw_f'] = [90.0] * 3
    decision = build_decision_record(decision_id=UUID(int=number), issued_at=issued,
        site_timezone='America/Denver', source_revision='a' * 64,
        policy_version='forecast-intel-thermal-v1', bank_epoch='test-bank',
        prediction_day=day, advisory=advisory, inputs=inputs,
        thresholds=dict.fromkeys(THRESHOLD_FIELDS, 90.0),
        notification_eligible=False, notification_suppressed=False)
    result = build_result_record(result_id=UUID(int=result_number), decision_id=UUID(int=number),
        observed_at=issued + timedelta(seconds=1), kind='publication',
        target='Thermal_Advisory', status=status)
    return decision, result


def select(rows, **kwargs):
    return f.select_followup(rows, now=kwargs.pop('now', NOW),
        activated_at=datetime(2026, 10, 2, 12, tzinfo=UTC),
        bank_epoch='test-bank', **kwargs)


def test_only_actual_published_advice_is_selected_and_frozen():
    original = evidence()
    candidate = select([original])
    assert candidate.actions == (('window', 'open'),)
    assert candidate.decision_id == str(UUID(int=1))
    assert candidate.publication_result_id == str(UUID(int=101))
    assert candidate.decision_json == original[0]
    assert candidate.result_json == original[1]
    assert candidate.available_at == datetime(2026, 10, 3, 2, tzinfo=UTC)
    assert candidate.until == datetime(2026, 10, 3, 17, tzinfo=UTC)


@pytest.mark.parametrize('advisory,status', [('none', 'accepted'),
    ('vent_tonight', 'failed'), ('vent_tonight', 'unknown')])
def test_nonrecommendation_or_unsuccessful_publication_cannot_create_question(advisory, status):
    assert select([evidence(advisory=advisory, status=status)]) is None


def test_waits_for_action_opportunity_and_does_not_backfill_expired_window():
    assert select([evidence()], now=NOW - timedelta(hours=2)) is None
    assert select([evidence()], now=datetime(2026, 10, 3, 17, tzinfo=UTC)) is None
    assert select([evidence(issued=datetime(2026, 10, 2, 11, tzinfo=UTC))]) is None


def test_close_up_questions_do_not_infer_shades_or_skylights():
    rows = [evidence(advisory='close_up_tomorrow')]
    assert select(rows, now=datetime(2026, 10, 3, 13, 59, tzinfo=UTC)) is None
    candidate = select(rows, now=datetime(2026, 10, 3, 14, tzinfo=UTC))
    assert candidate.actions == (('window', 'closed'),)
    assert candidate.until == datetime(2026, 10, 4, 6, tzinfo=UTC)


@pytest.mark.parametrize('field,value', [
    ('bank_epoch', 'different-bank'), ('policy_version', 'unreviewed-v2'),
    ('site_timezone', 'UTC'), ('source_revision', 'not-a-source-hash')])
def test_other_identity_or_policy_is_ineligible(field, value):
    decision, result = evidence()
    payload = json.loads(decision)
    payload[field] = value
    # Some changes also forge derived windows and must be rejected, not ignored.
    if field == 'site_timezone':
        with pytest.raises(t.Refused):
            select([(json.dumps(payload), result)])
    else:
        assert select([(json.dumps(payload), result)]) is None


@pytest.mark.parametrize('problem', ['extra', 'parent', 'future', 'wrong-target', 'overflow'])
def test_bad_evidence_fails_closed(problem):
    decision, result = evidence()
    if problem == 'overflow':
        rows = [(decision, result)] * (f.MAX_CANDIDATES + 1)
    else:
        payload = json.loads(result if problem != 'extra' else decision)
        if problem == 'extra': payload['invented'] = True
        elif problem == 'parent': payload['decision_id'] = str(UUID(int=2))
        elif problem == 'future': payload['observed_at'] = (NOW + timedelta(seconds=1)).isoformat()
        elif problem == 'wrong-target': payload['target'] = 'Predicted_SoC_Trough_Tomorrow'
        rows = [(json.dumps(payload), result)] if problem == 'extra' else [(decision, json.dumps(payload))]
    with pytest.raises(t.Refused):
        select(rows)


def test_newest_publication_controls_opportunity_not_an_obsolete_older_advice():
    old = evidence()
    replacement = evidence(advisory='none', issued=NOW - timedelta(minutes=5),
                           number=2, result_number=102)
    assert select([old, replacement]) is None
    assert select([replacement, old]) is None


def test_multiple_results_for_same_decision_are_deterministic():
    a, b = evidence(), evidence(result_number=102)
    assert select([a, b]) == select([b, a])
    assert select([a, b]).publication_result_id == str(UUID(int=102))


def database():
    db = sqlite3.connect(':memory:')
    f.initialize(db)
    return db


def test_reservation_commits_before_send_and_retry_retains_same_question():
    with database() as db:
        candidate = select([evidence()])
        first = f.reserve_followup(db, candidate, policy=policy(), now=NOW)
        retry = f.reserve_followup(db, candidate, policy=policy(), now=NOW + timedelta(minutes=5))
        assert first == retry
        assert first.actions == (('window', 'open'),)
        assert first.issued_at == NOW
        assert first.expires_at == candidate.until
        assert db.execute('SELECT count(*) FROM automatic_questions').fetchone() == (1,)
        assert not db.in_transaction
        replayed = f.retained_prompts(db, policy=policy())
        assert replayed == (first,)


def test_different_advisory_on_same_day_cannot_generate_second_question():
    with database() as db:
        first = f.reserve_followup(db, select([evidence()]), policy=policy(), now=NOW)
        newer = select([evidence(number=2, result_number=102, issued=NOW - timedelta(minutes=1))])
        assert f.reserve_followup(db, newer, policy=policy(), now=NOW + timedelta(minutes=5)) == first


def test_manual_question_also_consumes_daily_budget():
    p = t.Policy.load(t.canonical(dict(version=2, recipient=C, operators=[O], prompts=[dict(
        operator=O, issued_at=(NOW - timedelta(hours=1)).isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(), actions={'indoor_shade': 'closed'})])),
        assign_ids=True)
    with database() as db:
        assert f.reserve_followup(db, select([evidence()]), policy=p, now=NOW) is None
        assert db.execute('SELECT count(*) FROM automatic_questions').fetchone() == (0,)


def test_expired_retry_cannot_replace_same_days_question():
    with database() as db:
        candidate = select([evidence()])
        first = f.reserve_followup(db, candidate, policy=policy(), now=NOW)
        assert f.reserve_followup(db, candidate, policy=policy(), now=candidate.until) is None
        assert f.retained_prompts(db, policy=policy()) == (first,)


@pytest.mark.parametrize('now', [
    datetime(2026, 11, 1, 7, 30, tzinfo=UTC),
    datetime(2026, 11, 1, 8, 30, tzinfo=UTC),
    datetime(2026, 3, 8, 8, 30, tzinfo=UTC),
    datetime(2026, 3, 8, 9, 30, tzinfo=UTC)])
def test_dst_never_resets_the_same_local_days_budget(now):
    day = now.astimezone(t.DENVER).date() - timedelta(days=1)
    issued = datetime.combine(day, datetime.min.time(), t.DENVER).astimezone(UTC)
    candidate = f.select_followup([evidence(day=day, issued=issued)], now=now,
        activated_at=issued - timedelta(days=1), bank_epoch='test-bank')
    with database() as db:
        first = f.reserve_followup(db, candidate, policy=policy(), now=now)
        assert f.reserve_followup(db, candidate, policy=policy(), now=now + timedelta(minutes=10)) == first


def test_corrupt_or_changed_authority_reservation_is_not_reissued():
    with database() as db:
        candidate = select([evidence()])
        f.reserve_followup(db, candidate, policy=policy(), now=NOW)
        db.execute("UPDATE automatic_questions SET decision_json='{}'")
        db.commit()
        with pytest.raises(t.Refused):
            f.retained_prompts(db, policy=policy())


def test_reservation_requires_one_v2_operator_and_no_ambient_transaction():
    with database() as db:
        p = t.Policy.load(t.canonical(dict(version=2, recipient=C, operators=[O, '3' * 64], prompts=[])),
                         allow_empty=True)
        with pytest.raises(t.Refused):
            f.reserve_followup(db, select([evidence()]), policy=p, now=NOW)
        db.execute('BEGIN')
        with pytest.raises(t.Refused):
            f.reserve_followup(db, select([evidence()]), policy=policy(), now=NOW)


def test_same_advice_cannot_be_asked_again_after_local_midnight():
    with database() as db:
        candidate = select([evidence()])
        first = f.reserve_followup(db, candidate, policy=policy(), now=NOW)
        tomorrow = datetime(2026, 10, 3, 7, tzinfo=UTC)
        assert tomorrow.astimezone(t.DENVER).date() != NOW.astimezone(t.DENVER).date()
        assert select([evidence()], now=tomorrow) == candidate
        assert f.reserve_followup(db, candidate, policy=policy(), now=tomorrow) is None
        assert f.retained_prompts(db, policy=policy()) == (first,)


def test_removed_manual_policy_prompt_still_consumes_daily_budget(tmp_path):
    import thermal_nip04 as n
    ledger = n.PrimalLedger(tmp_path / 'state')
    try:
        f.initialize(ledger.db)
        manual = t.Policy.load(t.canonical(dict(version=2, recipient=C, operators=[O], prompts=[dict(
            operator=O, issued_at=NOW.isoformat(), expires_at=(NOW + timedelta(hours=1)).isoformat(),
            actions={'indoor_shade': 'closed'})])), assign_ids=True).prompts[0]
        # No network or fake live receipt: disposable ledger fixture only.
        ledger.db.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?)',
            (manual.event_id, t.canonical(manual.snapshot()).decode(), C, O, '3' * 64, b'fixture', '4' * 64))
        ledger.db.commit()
        assert f.reserve_followup(ledger.db, select([evidence()]), policy=policy(), now=NOW) is None
    finally:
        ledger.close()


def test_original_reservation_survives_primal_snapshot_and_cold_restore(tmp_path):
    import thermal_nip04 as n
    import thermal_state_backup as b
    source, restored = tmp_path / 'source', tmp_path / 'restored'
    ledger, outbox = n.PrimalLedger(source), n.PrimalOutbox(source)
    try:
        f.initialize(ledger.db)
        original = f.reserve_followup(ledger.db, select([evidence()]), policy=policy(), now=NOW)
        assert ledger.db.execute('PRAGMA user_version').fetchone()[0] == 1
    finally:
        ledger.close()
        outbox.close()
    b.snapshot_state(source, restored, transport='nip04')
    assert b.verify_snapshot(restored)['verified_files'] == 2
    cold = n.PrimalLedger(restored)
    try:
        f.initialize(cold.db)
        assert f.retained_prompts(cold.db, policy=policy()) == (original,)
        assert f.reserve_followup(cold.db, select([evidence()]), policy=policy(), now=NOW) == original
    finally:
        cold.close()


def test_independent_connections_cannot_reserve_a_second_question(tmp_path):
    path = tmp_path / 'fixture.sqlite3'
    first, second = sqlite3.connect(path), sqlite3.connect(path)
    try:
        f.initialize(first)
        f.initialize(second)
        original = f.reserve_followup(first, select([evidence()]), policy=policy(), now=NOW)
        other = select([evidence(number=2, result_number=102, issued=NOW - timedelta(minutes=1))])
        assert f.reserve_followup(second, other, policy=policy(), now=NOW) == original
        assert second.execute('SELECT count(*) FROM automatic_questions').fetchone() == (1,)
    finally:
        first.close()
        second.close()


def test_missing_unique_constraints_are_not_accepted_as_the_reservation_schema():
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE automatic_questions (local_day TEXT, decision_id TEXT, '
            'publication_result_id TEXT, decision_json TEXT, result_json TEXT, '
            'prompt_json TEXT, collector TEXT, operator TEXT, evidence_sha256 TEXT)')
        with pytest.raises(t.Refused):
            f.initialize(db)


class ReadConnection:
    def __init__(self, rows, role='advisory_assessor', elevated=False):
        self.rows, self.role, self.elevated = rows, role, elevated
        self.statements = []
    def set_session(self, **settings):
        assert settings == dict(isolation_level='REPEATABLE READ', readonly=True, autocommit=False)
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def execute(self, query, params=None): self.statements.append((query, params))
    def fetchone(self):
        return (self.role,) if self.statements[-1][0] == 'SELECT current_user' else (
            self.elevated, False, False, False, False)
    def fetchall(self): return self.rows


def relational_row():
    decision, result = evidence()
    d, r = json.loads(decision), json.loads(result)
    return [decision, result, d['decision_id'], t.aware(d['issued_at']),
            'test-bank', r['result_id'], t.aware(r['observed_at'])]


def read(connection):
    return f.fetch_publications(connection, now=NOW,
        activated_at=NOW - timedelta(days=1), bank_epoch='test-bank')


def test_reader_is_bounded_readonly_and_binds_payload_to_relational_origin():
    connection = ReadConnection([relational_row()])
    assert select(read(connection)) == select([evidence()])
    query, params = connection.statements[-1]
    assert params[-1] == f.MAX_CANDIDATES + 1
    assert 'JOIN energy_analytics.advisory_results' in query
    assert "r.payload->>'target'='Thermal_Advisory'" in query
    assert all(not query.lstrip().startswith(('INSERT', 'UPDATE', 'DELETE', 'GRANT', 'CREATE'))
               for query, _ in connection.statements)


@pytest.mark.parametrize('role,elevated', [('postgres', False), ('advisory_writer', False),
                                         ('advisory_assessor', True)])
def test_reader_refuses_writer_or_admin_before_evidence_access(role, elevated):
    connection = ReadConnection([relational_row()], role, elevated)
    with pytest.raises(t.Refused): read(connection)
    assert not any('advisory_decisions' in query for query, _ in connection.statements)


@pytest.mark.parametrize('field', [2, 3, 4, 5, 6])
def test_reader_rejects_forged_relational_metadata(field):
    row = relational_row()
    row[field] = NOW if field in (3, 6) else 'forged'
    with pytest.raises(t.Refused): read(ReadConnection([row]))


def configuration():
    return dict(version=1, activated_at=(NOW-timedelta(hours=1)).isoformat(),
                bank_epoch='test-bank', site_timezone='America/Denver', max_questions_per_day=1)


@pytest.mark.parametrize('field,value', [('version', True), ('max_questions_per_day', 2),
    ('max_questions_per_day', True), ('site_timezone', 'UTC'), ('bank_epoch', ''),
    ('activated_at', (NOW+timedelta(seconds=1)).isoformat())])
def test_automatic_settings_are_exact_single_day_consent(field, value):
    value_set = configuration(); value_set[field] = value
    with pytest.raises(t.Refused): f.load_configuration(t.canonical(value_set), now=NOW)


def test_configuration_pin_survives_reopen_and_refuses_activation_or_identity_change(tmp_path):
    path = tmp_path/'fixture.sqlite3'
    settings = f.load_configuration(t.canonical(configuration()), now=NOW)
    with sqlite3.connect(path) as db:
        f.initialize(db)
        f.pin_configuration(db, settings, policy=policy())
    with sqlite3.connect(path) as db:
        f.initialize(db)
        f.pin_configuration(db, settings, policy=policy())
        changed = {**settings, 'activated_at': (NOW-timedelta(hours=2)).isoformat()}
        with pytest.raises(t.Refused): f.pin_configuration(db, changed, policy=policy())
        different = t.Policy('3'*64, frozenset({O}), (), 2)
        with pytest.raises(t.Refused): f.pin_configuration(db, settings, policy=different)
        assert not db.in_transaction


@pytest.mark.parametrize('override', [dict(user='postgres'), dict(user='advisory_writer'),
    dict(host='192.0.2.1'), dict(port='5433'), dict(dbname='other'), dict(password=''),
    dict(service='ambient')])
def test_private_reader_dsn_does_not_adopt_other_credentials(override):
    from psycopg2.extensions import make_dsn
    values = dict(host='127.0.0.1', port='5432', dbname='openhab',
                  user='advisory_assessor', password='fixture')
    dsn = make_dsn(**(values|override))
    with pytest.raises(t.Refused): f.reader_dsn({'ADVISORY_ASSESS_DSN': dsn})


def test_exact_assessor_dsn_is_separate_and_ambient_services_are_refused():
    dsn = 'host=127.0.0.1 port=5432 dbname=openhab user=advisory_assessor password=fixture'
    assert f.reader_dsn({'ADVISORY_ASSESS_DSN': dsn}) == dsn
    with pytest.raises(t.Refused):
        f.reader_dsn({'ADVISORY_ASSESS_DSN': dsn, 'PGSERVICE': 'unexpected'})
    with pytest.raises(t.Refused): f.reader_dsn({'THERMAL_DATABASE_URL': dsn})


def test_more_than_one_hundred_retained_questions_do_not_disable_reply_recovery(tmp_path):
    import thermal_nip04 as n
    ledger = n.PrimalLedger(tmp_path/'state')
    try:
        f.initialize(ledger.db)
        for number in range(101):
            issued = NOW-timedelta(days=number+1)
            p = t.Policy.load(t.canonical(dict(version=2, recipient=C, operators=[O], prompts=[dict(
                operator=O, issued_at=issued.isoformat(), expires_at=(issued+timedelta(hours=1)).isoformat(),
                actions={'window': 'open'})])), assign_ids=True).prompts[0]
            ledger.db.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?)',
                (p.event_id, t.canonical(p.snapshot()).decode(), C, O, format(number, '064x'), b'fixture', '4'*64))
        ledger.db.commit()
        assert len(f.combined_policy(ledger.db, policy=policy()).prompts) == 101
        assert policy().prompts == ()  # The external reviewed policy was not changed.
    finally: ledger.close()
