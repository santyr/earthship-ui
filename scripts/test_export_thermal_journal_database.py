"""Hosted-only genuine source snapshot/proof/dump/package integration."""
import importlib.util,json
from pathlib import Path
from datetime import datetime,timezone
import pytest,psycopg2
from psycopg2.extensions import parse_dsn
from test_thermal_airflow_migration import database
from thermal_model.schema import ActionEvent
from thermal_journal_restore_transfer import _live
from thermal_journal_transfer import read_journal_transfer


@pytest.mark.parametrize('version',['v1','v2'])
def test_disposable_source_exports_one_bound_original_generation(database,tmp_path,monkeypatch,version):
    spec=importlib.util.spec_from_file_location('real_source_export',Path(__file__).with_name('export-thermal-journal.py'))
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    live=_live();now=datetime.now(timezone.utc)
    live.journal.ActionJournal(database.admin_dsn).append(ActionEvent('source-fixture','source-receipt',now,now,'vent','closed','manual_dm',1.0))
    if version=='v2':
        with psycopg2.connect(database.admin_dsn) as connection:
            with connection.cursor() as cursor:live.airflow_migration._replace_constraint(cursor)
    config=tmp_path/'config';config.mkdir(mode=0o700)
    params=parse_dsn(database.runtime_dsn)
    dsn=config/'dsn';dsn.write_text('host=127.0.0.1 port=5432 dbname=openhab user='+params['user']+' password='+params['password']);dsn.chmod(0o600)
    root=tmp_path/'export';root.mkdir(mode=0o700)
    original=source._context
    # The household endpoint is replaced only at connection boundaries for this
    # synthetic disposable fixture. Actual SQL audit/proofs/dump/package remain.
    def context(*args):
        _,_,output,digest=original(*args)
        return database.runtime_dsn,params,output,digest
    monkeypatch.setattr(source,'_context',context)
    import thermal_journal_dump as transport
    def environment(*args):
        env=live.postgres_env(params)
        env.update(PGCLIENTENCODING='UTF8',PGCONNECT_TIMEOUT='3',PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000')
        return env
    monkeypatch.setattr(transport,'_request',environment)
    receipt=source._worker(dsn,root,version,source._context(dsn,root,version)[-1])
    generation=root/receipt['source_receipt_sha256']
    record=json.loads((generation/'source-receipt.json').read_text())
    package=generation/'transfer'/record['transfer_sha256']
    assert read_journal_transfer(package)['archive_sha256']==record['archive_sha256']
    assert record['table_proofs']['action_events']['rows']==1
    assert record['source_snapshot_observed'] is True
    assert record['source_export_authenticated'] is False and record['release_authorized'] is False
    live.backup._check_journal_archive(package/'journal.dump')
