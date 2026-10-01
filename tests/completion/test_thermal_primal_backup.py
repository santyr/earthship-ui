"""Explicit Primal snapshot/recovery; synthetic keys and disposable databases."""
from datetime import timedelta
from contextlib import closing
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest

from test_thermal_nip04_ledger import codec, signed, policy, queue, C, O, NOW
from test_thermal_nip04_delivery import FixtureCodec, ReceiptSink, routes
from test_thermal_state_backup import seeded_state
from test_thermal_airflow_migration import database
import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n
import thermal_state_backup as b
from thermal_model import airflow_migration as migration, journal
from thermal_model.schema import ActionEvent


SPEC=importlib.util.spec_from_file_location('primal_journal_restore',
    Path(__file__).resolve().parents[2]/'scripts/qualify-thermal-journal-live-restore.py')
recovery=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(recovery)


@pytest.fixture
def restored_database(database):
    """Start both isolated databases before the crypto fixture clears host env."""
    name='thermal-primal-restore-test-'+uuid4().hex
    password=uuid4().hex
    try:
        params=recovery.disposable_database(name,uuid4().hex,database.runtime_role)
        with psycopg2.connect(**params) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD %s').format(
                    sql.Identifier(database.runtime_role)),(password,))
        runtime=psycopg2.extensions.make_dsn(**{**params,'user':database.runtime_role,'password':password})
        yield params,runtime
    finally:
        subprocess.run(['docker','rm','--force','--volumes',name],
                       capture_output=True,check=False,timeout=30)


def state(path):
    ledger=n.PrimalLedger(path); outbox=n.PrimalOutbox(path)
    try:
        for db,value in ((ledger.db,'original-cipher fixture'),(outbox.db,'delivery fixture')):
            db.execute('CREATE TABLE backup_marker(value TEXT NOT NULL)')
            db.execute('INSERT INTO backup_marker VALUES (?)',(value,)); db.commit()
    finally:
        outbox.close(); ledger.close()


def configuration(tmp_path):
    root=tmp_path/'config'; root.mkdir(mode=0o700)
    paths=(root/'policy.json',root/'routes.json')
    for path,data in zip(paths,(b'{"policy":"synthetic-private"}',b'{"routes":"synthetic-private"}')):
        path.write_bytes(data); path.chmod(0o600)
    return dict(zip(('policy','routes'),paths))


@pytest.mark.parametrize('include_config',[False,True])
def test_explicit_primal_snapshot_restores_both_new_files_without_touching_legacy(tmp_path, include_config):
    source=tmp_path/'state'; state(source); seeded_state(source)
    legacy={name:sha256((source/name).read_bytes()).hexdigest() for name in b.DATABASES}
    config=configuration(tmp_path) if include_config else {}
    destination=tmp_path/'snapshot'
    manifest=b.snapshot_state(source,destination,transport='nip04',**config)
    expected={'primal.sqlite3','primal-delivery.sqlite3'}|({'policy.json','routes.json'} if include_config else set())
    assert set(manifest['files_sha256'])==expected
    assert manifest['version']==(5 if include_config else 4)
    assert b.verify_snapshot(destination)['verified_files']==(4 if include_config else 2)
    for name,value in (('primal.sqlite3','original-cipher fixture'),('primal-delivery.sqlite3','delivery fixture')):
        with sqlite3.connect(destination/name) as db:
            assert db.execute('SELECT value FROM backup_marker').fetchall()==[(value,)]
    assert {name:sha256((source/name).read_bytes()).hexdigest() for name in b.DATABASES}==legacy
    restored=n.PrimalLedger(destination); delivered=n.PrimalOutbox(destination)
    delivered.close(); restored.close()


def test_primal_snapshot_cli_is_explicit_and_does_not_print_private_contents(tmp_path,capsys):
    source=tmp_path/'state'; state(source); destination=tmp_path/'snapshot'
    config=configuration(tmp_path)
    assert b.main(['--snapshot','--transport','nip04','--source-dir',str(source),
        '--snapshot-dir',str(destination),'--policy',str(config['policy']),
        '--routes',str(config['routes'])])==0
    output=capsys.readouterr().out
    assert 'synthetic-private' not in output
    assert json.loads(output)['scope']=='thermal_primal_sqlite_pair_and_config_no_postgresql_journal'


@pytest.mark.parametrize('problem',['missing','version','public','busy','unknown'])
def test_primal_preflight_refuses_before_creating_destination(tmp_path, problem):
    source=tmp_path/'state'; state(source); destination=tmp_path/'snapshot'
    if problem=='missing': (source/'primal-delivery.sqlite3').unlink()
    elif problem=='version':
        with sqlite3.connect(source/'primal.sqlite3') as db: db.execute('PRAGMA user_version=99')
    elif problem=='public': (source/'primal.sqlite3').chmod(0o644)
    if problem=='busy':
        with b.state_lock(source):
            with pytest.raises(ValueError): b.snapshot_state(source,destination,transport='nip04')
    else:
        with pytest.raises((ValueError,FileNotFoundError)):
            b.snapshot_state(source,destination,transport='auto' if problem=='unknown' else 'nip04')
    assert not destination.exists()


@pytest.mark.parametrize('problem',['cipher','scope','missing','schema','extra'])
def test_primal_snapshot_verifier_refuses_changed_or_mislabeled_bundle(tmp_path, problem):
    source=tmp_path/'state'; state(source); destination=tmp_path/'snapshot'
    b.snapshot_state(source,destination,transport='nip04')
    if problem=='missing': (destination/'primal.sqlite3').unlink()
    elif problem=='extra':
        (destination/'delivery.sqlite3').write_bytes(b'unbound legacy file')
    elif problem=='cipher':
        with sqlite3.connect(destination/'primal.sqlite3') as db:
            db.execute("UPDATE backup_marker SET value='altered'")
    elif problem=='schema':
        with sqlite3.connect(destination/'primal.sqlite3') as db: db.execute('PRAGMA user_version=99')
        manifest=json.loads((destination/'manifest.json').read_bytes())
        manifest['files_sha256']['primal.sqlite3']=sha256((destination/'primal.sqlite3').read_bytes()).hexdigest()
        (destination/'manifest.json').write_bytes(t.canonical(manifest))
    else:
        manifest=json.loads((destination/'manifest.json').read_bytes())
        manifest.update(version=1,scope=b.SQLITE_SCOPE)
        (destination/'manifest.json').write_bytes(t.canonical(manifest))
    with pytest.raises((ValueError,FileNotFoundError)):
        b.verify_snapshot(destination)


def test_restored_primal_state_keeps_original_reply_first_receipt_and_pending_ack(codec,monkeypatch,tmp_path):
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    p=policy(); source=tmp_path/'state'; ledger=n.PrimalLedger(source); outbox=n.PrimalOutbox(source)
    sink=ReceiptSink(); codec_out=FixtureCodec(codec,monkeypatch)
    relay=n.PrimalRelay(codec.keyer,C,p.operators)
    signed_routes=routes(codec,monkeypatch,p,'wss://relay.example')
    try:
        question=queue(ledger,codec,monkeypatch,p)
        delivery=n.PrimalDelivery(p,signed_routes,ledger,outbox,codec_out,relay,sink)
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id)
        receipt=delivery.receive(t.canonical(event),NOW)
        first=ledger.get(event['id']); outgoing=outbox.rows()[0]
    finally:
        outbox.close(); ledger.close()
    config_root=tmp_path/'config'; config_root.mkdir(mode=0o700)
    policy_path=config_root/'policy.json'; route_path=config_root/'routes.json'
    policy_path.write_bytes(t.canonical({'version':2,'recipient':C,'operators':[O],
        'prompts':[prompt.snapshot() for prompt in p.prompts]})); policy_path.chmod(0o600)
    # Public route signatures are reverified by the transport separately.
    route_path.write_bytes(b'{"synthetic":"route-copy-only"}'); route_path.chmod(0o600)
    destination=tmp_path/'snapshot'
    b.snapshot_state(source,destination,transport='nip04',policy=policy_path,routes=route_path)
    assert b.verify_snapshot(destination)['verified_files']==4
    ledger=n.PrimalLedger(destination); outbox=n.PrimalOutbox(destination)
    try:
        assert ledger.question(p,p.prompts[0].event_id,codec)==question
        assert ledger.get(event['id'])==first and outbox.rows()[0]==outgoing
        restored=n.PrimalDelivery(p,signed_routes,ledger,outbox,codec_out,relay,sink)
        assert restored.receive(t.canonical(event),NOW+timedelta(hours=3))==receipt
        assert ledger.get(event['id'])['first_received_at']=='2026-10-01T14:00:00+00:00'
        assert outbox.rows()[0]==outgoing and len(sink.records)==1
    finally:
        outbox.close(); ledger.close()


def test_explicit_verification_refuses_other_transport(tmp_path):
    source=tmp_path/'state'; state(source); destination=tmp_path/'snapshot'
    b.snapshot_state(source,destination,transport='nip04')
    assert b.verify_snapshot(destination,transport='nip04')['version']==4
    with pytest.raises(ValueError,match='transport'):
        b.verify_snapshot(destination,transport='nip17')


def test_full_primal_bundle_restores_real_v2_journal_and_durable_delivery(
        database, restored_database, codec, monkeypatch, tmp_path):
    """Full five-file fixture recovery, not a live-household release check."""
    monkeypatch.setattr(n,'PRIMAL_RELEASE_READY',True)
    monkeypatch.setattr(migration,'RELEASE_READY',True)
    monkeypatch.setattr(journal,'V2_WRITE_RELEASE_READY',True)
    assert migration.migrate_v2(database.admin_dsn,runtime_role=database.runtime_role,
                               expected_owner=database.owner)['status']=='migrated_v2'
    p=policy(); source=tmp_path/'state'
    ledger=n.PrimalLedger(source); outbox=n.PrimalOutbox(source)
    reader=journal.ActionJournal(database.runtime_dsn)
    sink=t.JournalSink(reader,ActionEvent,runtime_role=database.runtime_role,
                       expected_owner=database.owner)
    announcements=[]
    for scalar,public in ((1,O),(2,C)):
        monkeypatch.setenv('NOSTR_SECRET_KEY',format(scalar,'064x'))
        announcements.append(t.strict_json(codec.keyer.call(['event'],t.canonical({
            'kind':10050,'pubkey':public,'created_at':int(NOW.timestamp()),
            'content':'','tags':[['relay','wss://relay.example']]})+b'\n',identity=True)))
    monkeypatch.setenv('NOSTR_SECRET_KEY',format(2,'064x'))
    route_bytes=t.canonical({'version':1,'announcements':announcements})
    signed_routes=m.Routes(route_bytes,p,codec.keyer)
    try:
        d=n.PrimalDelivery(p,signed_routes,ledger,outbox,FixtureCodec(codec,monkeypatch),
                          n.PrimalRelay(codec.keyer,C,p.operators),sink)
        d.queue_prompts(NOW)
        question=ledger.question(p,p.prompts[0].event_id,codec)
        outbox.accepted(outbox.rows()[0],'wss://relay.example')
        event=signed(codec,monkeypatch,'yes '+p.prompts[0].event_id,extra=(['e',question['id']],))
        receipt=d.receive(t.canonical(event),NOW)
        outbox.record_ingress(event)
        ack=next(row for row in outbox.rows() if row['intent'].startswith('ack:'))
        outbox.retry(ack,NOW.timestamp())
        original_rows=outbox.rows(); first=ledger.get(event['id'])
    finally:
        outbox.close(); ledger.close()
    config=configuration(tmp_path)
    config['policy'].write_bytes(t.canonical({'version':2,'recipient':C,'operators':[O],
        'prompts':[prompt.snapshot() for prompt in p.prompts]}))
    config['routes'].write_bytes(route_bytes)
    destination=tmp_path/'snapshot'
    with closing(psycopg2.connect(database.admin_dsn)) as connection:
        connection.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_export_snapshot()'); snapshot=cursor.fetchone()[0]
        proofs=recovery.table_proofs(connection)
        manifest=b.snapshot_state(source,destination,transport='nip04',**config,
            journal_exporter=lambda target: recovery.export_archive(
                target,psycopg2.extensions.parse_dsn(database.admin_dsn),snapshot))
    assert manifest['version']==6
    assert b.verify_snapshot(destination,transport='nip04')=={
        'version':6,'scope':'thermal_primal_stopped_writer_journal_sqlite_config_bundle',
        'verified_files':5}
    params,runtime_dsn=restored_database
    assert recovery.restore_and_rehearse(destination/'journal.dump',params,
        database.runtime_role,source_schema='v2')==proofs
    restored=tmp_path/'restored'; restored.mkdir(mode=0o700)
    for name in ('primal.sqlite3','primal-delivery.sqlite3'):
        shutil.copyfile(destination/name,restored/name); (restored/name).chmod(0o600)
    restored_policy=t.Policy.load((destination/'policy.json').read_bytes())
    restored_routes=m.Routes((destination/'routes.json').read_bytes(),restored_policy,codec.keyer)
    ledger=n.PrimalLedger(restored); outbox=n.PrimalOutbox(restored)
    restored_reader=journal.ActionJournal(runtime_dsn)
    restored_sink=t.JournalSink(restored_reader,ActionEvent,runtime_role=database.runtime_role,
                              expected_owner='postgres')
    try:
        d=n.PrimalDelivery(restored_policy,restored_routes,ledger,outbox,
            FixtureCodec(codec,monkeypatch),n.PrimalRelay(codec.keyer,C,p.operators),restored_sink)
        assert ledger.get(event['id'])==first and outbox.rows()==original_rows
        assert outbox.ingress_recorded(event)
        assert d.authorize(ack,NOW+timedelta(hours=3))==t.strict_json(ack['wrapped'].encode())
        assert d.receive(t.canonical(event),NOW+timedelta(hours=3))==receipt
        assert ledger.get(event['id'])==first and outbox.rows()==original_rows
        assert len(restored_reader.events_for_receipt('nostr:'+event['id']))==2
        with psycopg2.connect(runtime_dsn) as connection:
            connection.set_session(readonly=True)
            assert recovery.table_proofs(connection)==proofs
            with connection.cursor() as cursor:
                cursor.execute('SELECT payload_digest FROM thermal_intel.message_receipts '
                               'WHERE idempotency_key=%s',('nostr:'+event['id'],))
                assert cursor.fetchall()==[(sha256(t.canonical(event)).hexdigest(),)]
    finally:
        outbox.close(); ledger.close()
