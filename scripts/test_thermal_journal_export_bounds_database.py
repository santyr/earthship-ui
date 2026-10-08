"""Hosted CI only: genuine bounded COPY/hash parity on synthetic PostgreSQL."""
from contextlib import closing
from datetime import datetime,timezone
import pytest,psycopg2
from test_thermal_airflow_migration import database
from thermal_model.schema import ActionEvent
from thermal_journal_restore_transfer import _live
from thermal_journal_export_bounds import bounded_table_proofs


@pytest.mark.parametrize('version',['v1','v2'])
def test_bounded_source_proofs_match_original_csv_digests(database,version):
    live=_live();now=datetime.now(timezone.utc)
    live.journal.ActionJournal(database.admin_dsn).append(ActionEvent('bounds-fixture','bounds-receipt',now,now,'vent','closed','manual_dm',1.0,note='synthetic é, "quoted"'))
    if version=='v2':
        with psycopg2.connect(database.admin_dsn) as connection:
            with connection.cursor() as cursor:live.airflow_migration._replace_constraint(cursor)
    with closing(psycopg2.connect(database.admin_dsn)) as source:
        source.set_session(readonly=True,isolation_level='REPEATABLE READ')
        assert bounded_table_proofs(source)==live.table_proofs(source)


def test_multibyte_oversized_row_refuses_before_source_copy(database):
    live=_live();now=datetime.now(timezone.utc)
    live.journal.ActionJournal(database.admin_dsn).append(ActionEvent('oversize-fixture','oversize-receipt',now,now,'vent','closed','manual_dm',1.0,note='é'*1025))
    with closing(psycopg2.connect(database.admin_dsn)) as source:
        source.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with pytest.raises(ValueError,match='source rows exceed'):bounded_table_proofs(source)


def test_source_table_above_row_limit_refuses(database):
    with psycopg2.connect(database.admin_dsn) as source:
        with source.cursor() as cursor:
            cursor.execute("INSERT INTO thermal_intel.message_receipts (idempotency_key,payload_digest,received_at) SELECT 'bounded-fixture-'||n::text, repeat('a',64), now() FROM generate_series(1,10001) AS n")
    with closing(psycopg2.connect(database.admin_dsn)) as source:
        source.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with pytest.raises(ValueError,match='source rows exceed'):bounded_table_proofs(source)
