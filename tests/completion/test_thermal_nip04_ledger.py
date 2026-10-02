"""Real pinned stock nak for synthetic fixtures; no relays or household keys.

Stock positional encryption is used only for public disposable test messages;
the production outbound codec still requires the reviewed stdin backport.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'openhab/scripts'))
import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n
from test_thermal_airflow_migration import database
from thermal_model import airflow_migration as migration
from thermal_model import journal
from thermal_model.schema import ActionEvent

C = 'c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5'
O = '79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798'
NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def policy(*, states=None, correction_of=None):
    prompt = {'operator': O, 'issued_at': (NOW-timedelta(minutes=5)).isoformat(),
              'expires_at': (NOW+timedelta(minutes=30)).isoformat(),
              'actions': states or {'window': 'open', 'skylight': 'closed'}}
    if correction_of:
        prompt['correction_of'] = correction_of
    return t.Policy.load(t.canonical({'version': 2, 'recipient': C,
        'operators': [O], 'prompts': [prompt]}), assign_ids=True)


@pytest.fixture
def codec(monkeypatch, tmp_path):
    if not m.DEFAULT_NAK.is_file():
        pytest.skip('pinned stock nak unavailable')
    assert sha256(m.DEFAULT_NAK.read_bytes()).hexdigest() == m.DEFAULT_SHA256
    for key in tuple(os.environ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path/'config'))
    monkeypatch.setenv('PATH', os.defpath)
    monkeypatch.setenv('NOSTR_SECRET_KEY', format(2, '064x'))
    return n.Nip04Codec(m.Keyer(m.DEFAULT_NAK, m.DEFAULT_SHA256))


def signed(codec, monkeypatch, text, *, outgoing=False, at=NOW, extra=()):
    monkeypatch.setenv('NOSTR_SECRET_KEY', format(2 if outgoing else 1, '064x'))
    author, recipient = (C, O) if outgoing else (O, C)
    cipher = codec.keyer.call(['encrypt', '--nip04', '-p', recipient, '--', text],
                             identity=True).decode().removesuffix('\n')
    event = t.strict_json(codec.keyer.call(['event'], t.canonical({
        'kind': 4, 'pubkey': author, 'created_at': int(at.timestamp()),
        'tags': [['p', recipient], *extra], 'content': cipher})+b'\n', identity=True))
    monkeypatch.setenv('NOSTR_SECRET_KEY', format(2, '064x'))
    return event


def queue(ledger, codec, monkeypatch, p):
    prompt = p.prompts[0]
    question = signed(codec, monkeypatch, n.question_text(p, prompt.event_id),
                      outgoing=True, at=prompt.issued_at)
    ledger.queue_question(question, p, prompt.event_id, codec)
    return question


def test_question_ciphertext_survives_restart_and_conflicting_replacement_refuses(codec, monkeypatch, tmp_path):
    assert hasattr(n, 'PrimalLedger'), 'durable Primal ledger is not implemented'
    p = policy(); prompt = p.prompts[0]; root = tmp_path/'ledger'
    ledger = n.PrimalLedger(root)
    try:
        question = queue(ledger, codec, monkeypatch, p)
        ledger.close(); ledger = n.PrimalLedger(root)
        retained = ledger.question(p, prompt.event_id, codec)
        assert retained == question
        assert retained['id'] != prompt.event_id  # Cipher identity is not canonical reference.
        altered = signed(codec, monkeypatch, n.question_text(p, prompt.event_id),
                         outgoing=True, at=prompt.issued_at)
        assert altered['id'] != question['id']
        with pytest.raises(t.Refused, match='conflict'):
            ledger.queue_question(altered, p, prompt.event_id, codec)
        assert ledger.question(p, prompt.event_id, codec) == question
    finally:
        ledger.close()


def test_original_reply_receipt_and_records_survive_expired_restart(codec, monkeypatch, tmp_path):
    assert hasattr(n, 'PrimalLedger'), 'durable Primal ledger is not implemented'
    p = policy(); root = tmp_path/'ledger'; ledger = n.PrimalLedger(root)
    try:
        q = queue(ledger, codec, monkeypatch, p)
        event = signed(codec, monkeypatch, 'yes '+p.prompts[0].event_id,
                       extra=(['e', q['id']],))
        raw = t.canonical(event)
        first = ledger.receive(raw, p, codec, now=NOW)
        assert first['event_id'] == event['id'] and first['transport'] == 'nip04'
        assert first['original_event'] == raw
        assert first['first_received_at'] == '2026-10-01T14:00:00+00:00'
        records = t.strict_json(first['records_json'].encode())
        assert {r['action']:r['state'] for r in records} == {'window':'open','skylight':'closed'}
        assert {r['idempotency_key'] for r in records} == {'nostr:'+event['id']}
        assert all(r['received_at']=='2026-10-01T14:00:00+00:00' for r in records)
        assert all('NIP-04' in r['note'] for r in records)
        ledger.close(); ledger = n.PrimalLedger(root)
        replay = ledger.receive(raw, p, codec, now=NOW+timedelta(hours=3))
        assert replay == first
        assert ledger.get(event['id']) == first
    finally:
        ledger.close()


@pytest.mark.parametrize('context',['other','canonical','duplicate'])
def test_native_reply_context_must_match_retained_original_wire_question(codec, monkeypatch, tmp_path, context):
    assert hasattr(n, 'PrimalLedger'), 'durable Primal ledger is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        q=queue(ledger,codec,monkeypatch,p)
        reference=p.prompts[0].event_id
        extra=([['e','f'*64]] if context=='other' else [['e',reference]]
               if context=='canonical' else [['e',q['id']],['e',q['id']]])
        event=signed(codec,monkeypatch,'yes '+reference,extra=extra)
        with pytest.raises(t.Refused):
            ledger.receive(t.canonical(event),p,codec,now=NOW)
        assert ledger.get(event['id']) is None
    finally:
        ledger.close()


def test_reply_cannot_record_without_original_outgoing_question(codec, monkeypatch, tmp_path):
    assert hasattr(n,'PrimalLedger'), 'durable Primal ledger is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        with pytest.raises(t.Refused):
            ledger.receive(t.canonical(event),p,codec,now=NOW)
        assert ledger.get(event['id']) is None
    finally:
        ledger.close()


def test_forged_cipher_signature_cannot_enter_receipt_ledger(codec, monkeypatch, tmp_path):
    assert hasattr(n,'PrimalLedger'), 'durable Primal ledger is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id); event['sig']='0'*128
        with pytest.raises(t.Refused):
            ledger.receive(t.canonical(event),p,codec,now=NOW)
        assert ledger.get(event['id']) is None
    finally:
        ledger.close()


@pytest.mark.parametrize('answer',['not yet','skip'])
def test_negative_reply_records_no_actions(codec, monkeypatch, tmp_path, answer):
    assert hasattr(n,'PrimalLedger'), 'durable Primal ledger is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,answer+' '+p.prompts[0].event_id)
        row=ledger.receive(t.canonical(event),p,codec,now=NOW)
        assert row['records_json']=='[]'
        assert row['disposition']==('not_yet' if answer=='not yet' else 'skipped')
    finally:
        ledger.close()


def test_stale_new_reply_and_second_terminal_reply_cannot_replace_first(codec, monkeypatch, tmp_path):
    assert hasattr(n,'PrimalLedger'), 'durable Primal ledger is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        first=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        original=ledger.receive(t.canonical(first),p,codec,now=NOW)
        second=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id,at=NOW+timedelta(seconds=1))
        with pytest.raises(t.Refused,match='terminal'):
            ledger.receive(t.canonical(second),p,codec,now=NOW+timedelta(seconds=2))
        assert ledger.get(second['id']) is None and ledger.get(first['id'])==original
        assert ledger.receive(t.canonical(first),p,codec,now=NOW+timedelta(hours=3))==original
    finally:
        ledger.close()


def test_tampered_saved_records_cannot_replay(codec, monkeypatch, tmp_path):
    assert hasattr(n,'PrimalLedger'), 'durable Primal ledger is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        ledger.receive(t.canonical(event),p,codec,now=NOW)
        with ledger.db:
            ledger.db.execute("UPDATE receipts SET records_json='[]'")
        with pytest.raises(t.Refused,match='stored'):
            ledger.receive(t.canonical(event),p,codec,now=NOW+timedelta(minutes=1))
    finally:
        ledger.close()


def test_world_readable_ledger_refuses_without_creating_database(tmp_path):
    assert hasattr(n,'PrimalLedger'), 'durable Primal ledger is not implemented'
    directory=tmp_path/'public'; directory.mkdir(mode=0o755); directory.chmod(0o755)
    with pytest.raises(t.Refused,match='private'):
        n.PrimalLedger(directory)
    assert list(directory.iterdir())==[]


def test_live_ingress_gate_refuses_before_any_dependency_or_write():
    assert hasattr(n, 'ingest_primal'), 'gated Primal journal ingress is not implemented'
    with pytest.raises(t.Refused, match='release'):
        n.ingest_primal(b'not a real event', None, None, None, None, now=NOW)


def test_new_reply_after_expiry_cannot_create_a_receipt(codec, monkeypatch, tmp_path):
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        with pytest.raises(t.Refused,match='expired'):
            ledger.receive(t.canonical(event),p,codec,now=NOW+timedelta(minutes=31))
        assert ledger.get(event['id']) is None
    finally:
        ledger.close()


def test_withdrawn_policy_or_corrupted_outgoing_cipher_cannot_replay(codec, monkeypatch, tmp_path):
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        ledger.receive(t.canonical(event),p,codec,now=NOW)
        changed=policy(states={'window':'closed','skylight':'closed'})
        with pytest.raises(t.Refused):
            ledger.receive(t.canonical(event),changed,codec,now=NOW+timedelta(minutes=1))
        with ledger.db:
            ledger.db.execute("UPDATE questions SET digest=?",('0'*64,))
        with pytest.raises(t.Refused,match='stored outgoing'):
            ledger.receive(t.canonical(event),p,codec,now=NOW+timedelta(minutes=1))
    finally:
        ledger.close()


def test_default_sink_preflight_then_reply_stores_real_v2_action(
        database, codec, monkeypatch, tmp_path):
    """Exercise the CLI's unconfigured sink, not an injected record factory."""
    monkeypatch.setattr(migration, 'RELEASE_READY', True)  # Disposable DB only.
    monkeypatch.setattr(journal, 'V2_WRITE_RELEASE_READY', True)
    migration.migrate_v2(database.admin_dsn, runtime_role=database.runtime_role,
                         expected_owner=database.owner)
    monkeypatch.setenv('THERMAL_DATABASE_URL', database.runtime_dsn)
    monkeypatch.setenv('THERMAL_DATABASE_RUNTIME_ROLE', database.runtime_role)
    monkeypatch.setenv('THERMAL_DATABASE_EXPECTED_OWNER', database.owner)
    monkeypatch.setattr(n, 'PRIMAL_RELEASE_READY', True)
    sink = t.JournalSink()
    sink.require_v2_storage()
    assert sink.action_factory is ActionEvent
    p = policy(states={'indoor_shade': 'closed'})
    ledger = n.PrimalLedger(tmp_path / 'default-sink-ledger')
    try:
        queue(ledger, codec, monkeypatch, p)
        event = signed(codec, monkeypatch, 'yes ' + p.prompts[0].event_id)
        raw = t.canonical(event)
        receipt = n.ingest_primal(raw, p, ledger, codec, sink, now=NOW)
        assert receipt['status'] == 'stored'
        rows = sink.journal.events_for_receipt('nostr:' + event['id'])
        assert len(rows) == 1
        assert rows[0].action == 'indoor_shade' and rows[0].state == 'closed'
        assert ledger.get(event['id'])['original_event'] == raw
        assert n.ingest_primal(raw, p, ledger, codec, sink,
                               now=NOW + timedelta(minutes=1)) == receipt
        assert sink.journal.events_for_receipt('nostr:' + event['id']) == rows
    finally:
        ledger.close()


def test_real_v2_journal_recovers_commit_before_ack_and_preserves_original_cipher(
        database, codec, monkeypatch, tmp_path):
    assert hasattr(n,'ingest_primal'), 'gated Primal journal ingress is not implemented'
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    reader=journal.ActionJournal(database.runtime_dsn)
    sink=t.JournalSink(reader,ActionEvent,runtime_role=database.runtime_role,
                       expected_owner=database.owner)
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)  # Disposable test only.
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        raw=t.canonical(event); key='nostr:'+event['id']
        with pytest.raises(t.Retryable,match='preflight'):
            n.ingest_primal(raw,p,ledger,codec,sink,now=NOW)
        assert ledger.get(event['id']) is None
        assert reader.events_for_receipt(key)==()
        monkeypatch.setattr(migration,'RELEASE_READY',True)
        monkeypatch.setattr(journal,'V2_WRITE_RELEASE_READY',True)
        assert migration.migrate_v2(database.admin_dsn,runtime_role=database.runtime_role,
                                    expected_owner=database.owner)['status']=='migrated_v2'
        original=reader.events_for_receipt
        def readback_failure(_key):
            raise RuntimeError('synthetic readback interruption after actual commit')
        monkeypatch.setattr(reader,'events_for_receipt',readback_failure)
        with pytest.raises(t.Retryable,match='journal'):
            n.ingest_primal(raw,p,ledger,codec,sink,now=NOW)
        assert len(original(key))==2
        assert ledger.get(event['id'])['acknowledgement'] is None
        monkeypatch.setattr(reader,'events_for_receipt',original)
        first=n.ingest_primal(raw,p,ledger,codec,sink,now=NOW+timedelta(hours=3))
        assert first['status']=='stored' and first['transport']=='nip04'
        assert first['event_id']==event['id']
        assert first['first_received_at']=='2026-10-01T14:00:00+00:00'
        assert ledger.get(event['id'])['original_event']==raw
        assert len(original(key))==2
        assert n.ingest_primal(raw,p,ledger,codec,sink,now=NOW+timedelta(hours=4))==first
        import psycopg2
        with psycopg2.connect(database.runtime_dsn) as connection:
            connection.set_session(readonly=True)
            with connection.cursor() as cursor:
                cursor.execute('SELECT payload_digest FROM thermal_intel.message_receipts '
                               'WHERE idempotency_key=%s',(key,))
                assert cursor.fetchall()==[(sha256(raw).hexdigest(),)]

        correction=policy(states={'window':'closed','skylight':'closed'},correction_of=event['id'])
        queue(ledger,codec,monkeypatch,correction)
        c=signed(codec,monkeypatch,'yes '+correction.prompts[0].event_id,
                 at=NOW+timedelta(seconds=60))
        receipt=n.ingest_primal(t.canonical(c),correction,ledger,codec,sink,
                                now=NOW+timedelta(seconds=60))
        assert receipt['status']=='stored'
        revised=reader.events_for_receipt('nostr:'+c['id'])
        originals={r.action:r for r in original(key)}
        assert {r.action:r.state for r in revised}=={'window':'closed','skylight':'closed'}
        assert all(r.supersedes==originals[r.action].event_id for r in revised)
        ancestor=policy(states={'window':'open','skylight':'closed'},correction_of=event['id'])
        queue(ledger,codec,monkeypatch,ancestor)
        a=signed(codec,monkeypatch,'yes '+ancestor.prompts[0].event_id,
                 at=NOW+timedelta(seconds=120))
        with pytest.raises(t.Refused,match='latest'):
            n.ingest_primal(t.canonical(a),ancestor,ledger,codec,sink,
                            now=NOW+timedelta(seconds=120))
        assert reader.events_for_receipt('nostr:'+a['id'])==()
    finally:
        ledger.close()


def test_correction_reauthenticates_saved_original_instead_of_trusting_mutable_records(
        codec, monkeypatch, tmp_path):
    p=policy(); ledger=n.PrimalLedger(tmp_path/'ledger')
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        row=ledger.receive(t.canonical(event),p,codec,now=NOW)
        records=t.strict_json(row['records_json'].encode())
        receipt={'version':2,'transport':'nip04','status':'stored','disposition':'confirmed',
                 'event_id':event['id'],'question_id':p.prompts[0].event_id,
                 'idempotency_key':'nostr:'+event['id'],
                 'first_received_at':'2026-10-01T14:00:00+00:00',
                 'original_event_sha256':sha256(t.canonical(event)).hexdigest(),
                 'action_event_ids':[r['event_id'] for r in records]}
        # Private fixture only. This isolates correction authentication from
        # journal commits, which the real PostgreSQL test covers separately.
        with ledger.db:
            ledger.db.execute('UPDATE receipts SET acknowledgement=? WHERE event_id=?',
                              (t.canonical(receipt).decode(),event['id']))
            corrupted=t.strict_json(row['records_json'].encode())
            corrupted[0]['event_id']='b'*24
            ledger.db.execute('UPDATE receipts SET records_json=? WHERE event_id=?',
                              (t.canonical(corrupted).decode(),event['id']))
        correction=policy(states={'window':'closed','skylight':'closed'},correction_of=event['id'])
        queue(ledger,codec,monkeypatch,correction)
        reply=signed(codec,monkeypatch,'yes '+correction.prompts[0].event_id,
                     at=NOW+timedelta(seconds=60))
        with pytest.raises(t.Refused,match='stored'):
            ledger.receive(t.canonical(reply),correction,codec,now=NOW+timedelta(seconds=60))
        assert ledger.get(reply['id']) is None
    finally:
        ledger.close()


def test_new_primal_database_leaves_original_nip17_intents_unchanged(codec, monkeypatch, tmp_path):
    root=tmp_path/'ledger'; p=policy(); original=m.Outbox(root)
    original.queue('prompt:'+p.prompts[0].event_id,t.prompt_event(p.prompts[0],C),C,O)
    assert len(original.rows())==2
    original.close()
    path=root/'delivery.sqlite3'; digest=sha256(path.read_bytes()).hexdigest()
    ledger=n.PrimalLedger(root)
    try:
        queue(ledger,codec,monkeypatch,p)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        ledger.receive(t.canonical(event),p,codec,now=NOW)
        assert sha256(path.read_bytes()).hexdigest()==digest
    finally:
        ledger.close()


def test_native_context_without_verified_wire_mapping_remains_refused(codec, monkeypatch):
    p=policy()
    event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id,extra=(['e','f'*64],))
    message=codec.decode(t.canonical(event),recipient=C,authors=p.operators)
    with pytest.raises(t.Refused,match='context'):
        n.bind_reply(message,p,now=NOW)
