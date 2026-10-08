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
def test_real_transfer_restore_and_consumer_are_recorded_after_owned_cleanup(database,tmp_path,monkeypatch,version):
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
        expected_interpreter_sha256=interpreter,proof_directory=destination)
    report=json.loads(report_path.read_text())
    assert report['disposable_restore_qualified'] is True and report['consumer_qualified'] is True
    assert report['disposable_cleanup_verified'] is True
    assert report['consumer_probe']['connection_read_only'] is True
    assert report['journal_recovery_qualified'] is False and report['installed'] is False and report['release_authorized'] is False
