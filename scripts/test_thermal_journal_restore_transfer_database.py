"""Hosted CI only: real disposable archive, restore, consumer and owned cleanup.

Never select this test on the household host; fixtures are synthetic.
"""
from contextlib import closing
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,shutil
import pytest,psycopg2
from psycopg2.extensions import parse_dsn
from test_thermal_airflow_migration import database
from test_thermal_origin_capture import private_interpreter
from thermal_model.schema import ActionEvent
from thermal_model.origin_capture import _source_bytes
from thermal_journal_transfer import prepare_journal_transfer
import thermal_journal_restore_transfer as worker


@pytest.mark.parametrize('version',['v1','v2'])
@pytest.mark.parametrize('source_binding',[False,True])
def test_real_transfer_restore_and_consumer_are_recorded_after_owned_cleanup(database,tmp_path,monkeypatch,version,source_binding):
    live=worker._live();now=datetime.now(timezone.utc)
    live.journal.ActionJournal(database.admin_dsn).append(ActionEvent('transfer-fixture','transfer-receipt',now,now,'vent','closed','manual_dm',1.0))
    if version=='v2':
        with psycopg2.connect(database.admin_dsn) as connection:
            with connection.cursor() as cursor:live.airflow_migration._replace_constraint(cursor)
    archive=tmp_path/'journal.dump'
    with closing(psycopg2.connect(database.admin_dsn)) as source:
        source.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with source.cursor() as cursor:cursor.execute('SELECT pg_export_snapshot()');snapshot=cursor.fetchone()[0]
        proofs=live.table_proofs(source);live.export_archive(archive,parse_dsn(database.admin_dsn),snapshot)
    packages=tmp_path/'packages';packages.mkdir(mode=0o700)
    package=prepare_journal_transfer(archive=archive,directory=packages,source_schema=version,runtime_role=database.runtime_role,
        table_proofs=proofs,exported_at=now,source_code_revision='a'*64)
    source_options={}
    if source_binding:
        from thermal_model.forcing_capture import _canonical
        from thermal_journal_transfer import read_journal_transfer
        transferred=read_journal_transfer(package)
        stage=tmp_path/'source-stage';stage.mkdir(mode=0o700)
        parent=stage/'transfer';parent.mkdir(mode=0o700)
        shutil.move(str(package),str(parent/package.name));package=parent/package.name
        prepared=datetime.now(timezone.utc)
        source_record=dict(schema='earthship-thermal-journal-source-export/v1',observed_at=now.isoformat(),prepared_at=prepared.isoformat(),
            source_schema_version=version,source_schema_fingerprint=transferred['source_schema_fingerprint'],runtime_role=database.runtime_role,
            snapshot_identity=snapshot,source_code_revision='a'*64,configuration_binding_sha256='b'*64,
            archive_sha256=transferred['archive_sha256'],archive_bytes=transferred['archive_bytes'],table_proofs=proofs,
            transfer_sha256=transferred['transfer_sha256'],source_snapshot_observed=True,source_export_authenticated=False,
            restored=False,installed=False,release_authorized=False,automatic_actuation=False)
        source_record['source_receipt_sha256']=sha256(_canonical(source_record)).hexdigest()
        receipt=stage/'source-receipt.json';receipt.write_bytes(_canonical(source_record));receipt.chmod(0o600)
        generation=tmp_path/source_record['source_receipt_sha256'];stage.rename(generation)
        package=generation/'transfer'/transferred['transfer_sha256']
        source_options=dict(source_generation=generation,expected_source_receipt_sha256=source_record['source_receipt_sha256'],expected_exporter_revision='a'*64)
    runtime=tmp_path/'consumer';runtime.mkdir(mode=0o700);(runtime/'thermal_model').mkdir(mode=0o700)
    runtime_source=Path(__file__).resolve().parents[1]/'openhab/scripts'
    names=['thermal_intel.py']+['thermal_model/'+name+'.py' for name in ('__init__','journal','dataset','schema','actions','solar')]
    # Exact byte hashing for this synthetic consumer entrypoint, using real
    # journal/dataset implementations. This is not a household runtime generation.
    (runtime/'thermal_intel.py').write_text('from pathlib import Path\nfrom hashlib import sha256\nFILES='+repr(names)+'\ndef _code_revision():\n    root=Path(__file__).parent\n    return sha256(b"".join((root/name).read_bytes() for name in FILES)).hexdigest()\n')
    for name in names[1:]:shutil.copyfile(runtime_source/name,runtime/name)
    for name in names:(runtime/name).chmod(0o600)
    revision=sha256(b''.join((runtime/name).read_bytes() for name in names)).hexdigest()
    executable=private_interpreter(tmp_path,monkeypatch)
    interpreter=sha256(_source_bytes(executable,maximum=64000000)).hexdigest()
    destination=tmp_path/'proof';destination.mkdir(mode=0o700)
    monkeypatch.setenv('EARTHSHIP_REMOTE_JOURNAL_RESTORE','1')
    report_path=worker.qualify_journal_transfer(package=package,consumer_runtime=runtime,expected_consumer_revision=revision,
        expected_interpreter_sha256=interpreter,proof_directory=destination,**source_options)
    report=json.loads(report_path.read_text())
    assert report['schema']=='earthship-thermal-journal-restore-report/'+('v2' if source_binding else 'v1')
    if source_binding:assert report['source_export_binding']['original_receipt_verified'] is True
    assert report['source_export_authenticated'] is False
    assert report['disposable_restore_qualified'] is True and report['consumer_qualified'] is True
    assert report['disposable_cleanup_verified'] is True
    assert report['consumer_probe']['connection_read_only'] is True
    assert report['journal_recovery_qualified'] is False and report['installed'] is False and report['release_authorized'] is False
