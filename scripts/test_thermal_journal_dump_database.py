"""Hosted only: actual custom dump on disposable synthetic PostgreSQL."""
from contextlib import closing
from datetime import datetime,timezone
import psycopg2
from psycopg2.extensions import parse_dsn
from test_thermal_airflow_migration import database
from thermal_model.schema import ActionEvent
from thermal_journal_restore_transfer import _live
import thermal_journal_dump as dump


def test_actual_bounded_dump_preserves_audited_custom_archive(database,tmp_path,monkeypatch):
    live=_live();now=datetime.now(timezone.utc)
    live.journal.ActionJournal(database.admin_dsn).append(ActionEvent('dump-fixture','dump-receipt',now,now,'vent','closed','manual_dm',1.0))
    # Only the approved household endpoint differs for this disposable fixture.
    # The real pg_dump process/stream/bounds remain unchanged. This does not
    # attest the household source or qualify its restoration.
    def environment(params,snapshot):
        result=live.postgres_env(parse_dsn(database.admin_dsn))
        result.update(PGCLIENTENCODING='UTF8',PGCONNECT_TIMEOUT='3',PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000')
        return result
    monkeypatch.setattr(dump,'_request',environment)
    target=tmp_path/'journal.dump'
    with closing(psycopg2.connect(database.admin_dsn)) as source:
        source.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with source.cursor() as cursor:cursor.execute('SELECT pg_export_snapshot()');snapshot=cursor.fetchone()[0]
        result=dump.dump_journal(target=target,params={},snapshot=snapshot)
    assert 5<result['bytes']<=32000000
    live.backup._check_journal_archive(target)
