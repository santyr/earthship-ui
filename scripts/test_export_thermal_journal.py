"""Source-export orchestration fixtures; never connect to household PostgreSQL."""
import importlib.util,json,os
from pathlib import Path
from hashlib import sha256
import pytest


def module():
    spec=importlib.util.spec_from_file_location('source_export',Path(__file__).with_name('export-thermal-journal.py'))
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source);return source


def paths(tmp_path):
    config=tmp_path/'config';config.mkdir(mode=0o700)
    dsn=config/'dsn';dsn.write_text('host=127.0.0.1 port=5432 dbname=openhab user=fixture_reader password=synthetic-only');dsn.chmod(0o600)
    output=tmp_path/'output';output.mkdir(mode=0o700)
    return dsn,output


class Cursor:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query,*args):self.query=query
    def fetchone(self):
        if 'pg_export_snapshot' in self.query:return ('00000003-0000001B-1',)
        return ('fixture_reader','fixture_owner',False,False,'on','repeatable read')


class Connection:
    closed=False;rolled_back=False
    def cursor(self):return Cursor()
    def set_session(self,**kwargs):assert kwargs==dict(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
    def rollback(self):self.rolled_back=True
    def close(self):self.closed=True


def setup(tmp_path,monkeypatch):
    source=module();dsn,output=paths(tmp_path);connection=Connection()
    monkeypatch.setattr(source,'_source_revision',lambda:'c'*64)
    monkeypatch.setattr(source.psycopg2,'connect',lambda *_args,**_kwargs:connection)
    monkeypatch.setattr(source.airflow_migration,'_fingerprint',lambda *_args,**_kwargs:source.airflow_migration.V2_FINGERPRINT)
    monkeypatch.setattr(source,'bounded_table_proofs',lambda *_args,**_kwargs:{name:{'rows':1,'sha256':'a'*64} for name in ('action_events','message_receipts','mode_events')})
    def dump(**kwargs):
        assert not connection.closed and not connection.rolled_back
        raw=b'PGDMPsynthetic';kwargs['target'].write_bytes(raw);kwargs['target'].chmod(0o600)
        return {'bytes':len(raw),'sha256':sha256(raw).hexdigest()}
    monkeypatch.setattr(source,'dump_journal',dump)
    return source,dsn,output,connection


def test_source_worker_retains_bound_private_generation_and_closes_snapshot(tmp_path,monkeypatch):
    source,dsn,output,connection=setup(tmp_path,monkeypatch)
    context=source._context(dsn,output,'v2')
    receipt=source._worker(dsn,output,'v2',context[-1])
    assert receipt['status']=='journal_export_prepared'
    assert all(receipt[key] is False for key in ('restored','installed','release_authorized'))
    generation=output/receipt['source_receipt_sha256']
    record=json.loads((generation/'source-receipt.json').read_text())
    assert record['source_snapshot_observed'] is True and record['source_export_authenticated'] is False
    assert record['archive_sha256']==sha256(b'PGDMPsynthetic').hexdigest()
    assert (generation/'transfer'/record['transfer_sha256']/'journal.dump').read_bytes()==b'PGDMPsynthetic'
    assert connection.closed and connection.rolled_back


@pytest.mark.parametrize('damage',['schema','dump_hash','code','configuration'])
def test_worker_failure_never_publishes_generation(tmp_path,monkeypatch,damage):
    source,dsn,output,connection=setup(tmp_path,monkeypatch);digest=source._context(dsn,output,'v2')[-1]
    if damage=='schema':monkeypatch.setattr(source.airflow_migration,'_fingerprint',lambda *_args,**_kwargs:'wrong')
    elif damage=='dump_hash':
        original=source.dump_journal
        def bad(**kwargs):return {**original(**kwargs),'sha256':'f'*64}
        monkeypatch.setattr(source,'dump_journal',bad)
    elif damage=='code':
        revisions=iter(['c'*64,'d'*64]);monkeypatch.setattr(source,'_source_revision',lambda:next(revisions))
    else:dsn.write_text(dsn.read_text()+' application_name=changed')
    with pytest.raises(ValueError):source._worker(dsn,output,'v2',digest)
    assert list(output.iterdir())==[]


def test_default_cli_refuses_before_source_access(tmp_path,monkeypatch):
    source=module();dsn,output=paths(tmp_path)
    monkeypatch.delenv('EARTHSHIP_THERMAL_JOURNAL_EXPORT',raising=False)
    monkeypatch.setattr(source.psycopg2,'connect',lambda *_args,**_kwargs:pytest.fail('unauthorized source connection'))
    assert source.main(['--journal-dsn-file',str(dsn),'--destination',str(output),'--source-schema','v2'])==2
    assert list(output.iterdir())==[]


@pytest.mark.parametrize('failure',['caps','worker_context','headroom','database'])
def test_cli_failure_is_sanitized_and_never_leaves_a_success_receipt(tmp_path,monkeypatch,capsys,failure):
    source,dsn,output,connection=setup(tmp_path,monkeypatch)
    monkeypatch.setenv('EARTHSHIP_THERMAL_JOURNAL_EXPORT','1')
    monkeypatch.setattr(source,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(source,'verify_host_headroom',lambda:None)
    monkeypatch.setenv('EARTHSHIP_GUARDED_CAPTURE_WORKER','1')
    monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','0')
    monkeypatch.setattr(source.os,'getpriority',lambda *_:15)
    digest=source._context(dsn,output,'v2')[-1]
    def refuse():raise ValueError('synthetic-only private detail')
    if failure=='caps':monkeypatch.setattr(source,'verify_resource_limits',refuse)
    elif failure=='worker_context':monkeypatch.delenv('EARTHSHIP_GUARDED_CAPTURE_WORKER')
    elif failure=='headroom':monkeypatch.setattr(source,'verify_host_headroom',refuse)
    else:
        def failed(*_args,**_kwargs):raise source.psycopg2.OperationalError('synthetic-only private detail')
        monkeypatch.setattr(source.psycopg2,'connect',failed)
    assert source.main(['--journal-dsn-file',str(dsn),'--destination',str(output),'--source-schema','v2','--worker','--expected-context-digest',digest])==2
    captured=capsys.readouterr()
    assert 'synthetic-only' not in captured.out+captured.err
    assert list(output.iterdir())==[]


def test_check_only_verifies_paths_without_opening_source_or_writing_output(tmp_path,monkeypatch):
    source=module();dsn,output=paths(tmp_path)
    monkeypatch.setattr(source,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(source.psycopg2,'connect',lambda *_args,**_kwargs:pytest.fail('check-only opened source'))
    assert source.main(['--journal-dsn-file',str(dsn),'--destination',str(output),'--source-schema','v2','--check-only'])==0
    assert list(output.iterdir())==[]


def revision_tree(source,tmp_path,monkeypatch,model_names=None):
    import thermal_intel
    monkeypatch.setattr(source,'ROOT',tmp_path)
    names=model_names or ['thermal_model/journal.py','thermal_model/schema.py']
    monkeypatch.setattr(thermal_intel,'_release_runtime_paths',lambda:names)
    files=['openhab/scripts/'+name for name in names]
    files+=['openhab/scripts/thermal_model/'+name+'.py' for name in ('environment_bundle','runtime_bundle','rollback','capture_guard','capture_readers','training_inputs','airflow_migration')]
    files+=['scripts/'+name for name in ('export-thermal-journal.py','thermal_journal_export_bounds.py','thermal_journal_dump.py','thermal_journal_transfer.py')]
    for name in files:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic source');path.chmod(0o644)
    class Pace:
        def reserve(self,amount):pass
    monkeypatch.setattr(source,'_pacer',lambda rate:Pace())
    return files


def test_schema_audit_helper_changes_export_source_identity(tmp_path,monkeypatch):
    source=module();revision_tree(source,tmp_path,monkeypatch)
    before=source._source_revision()
    (tmp_path/'openhab/scripts/thermal_model/airflow_migration.py').write_bytes(b'independent schema helper change')
    assert source._source_revision()!=before


def test_source_growth_cannot_read_beyond_enforced_file_allowance(tmp_path,monkeypatch):
    source=module();revision_tree(source,tmp_path,monkeypatch)
    target=tmp_path/'openhab/scripts/thermal_model/journal.py'
    original_open=os.open;original_read=os.read;changed=[];used=[]
    def opened(path,*args,**kwargs):
        if Path(path)==target and not changed:
            changed.append(True);target.write_bytes(b'x'*2000002)
        return original_open(path,*args,**kwargs)
    def read(fd,amount):
        raw=original_read(fd,amount)
        if os.readlink('/proc/self/fd/'+str(fd))==str(target):used.append(len(raw))
        return raw
    monkeypatch.setattr(source.os,'open',opened);monkeypatch.setattr(source.os,'read',read)
    with pytest.raises(ValueError):source._source_revision()
    assert sum(used)<=2000001


def test_aggregate_exhaustion_refuses_before_reading_next_source(tmp_path,monkeypatch):
    source=module();revision_tree(source,tmp_path,monkeypatch,['a.py','b.py','c.py'])
    for name in ('a.py','b.py','c.py'):(tmp_path/'openhab/scripts'/name).write_bytes(b'x'*2000000)
    target=tmp_path/'openhab/scripts/c.py';original=os.read;used=[]
    def read(fd,amount):
        raw=original(fd,amount)
        if os.readlink('/proc/self/fd/'+str(fd))==str(target):used.append(len(raw))
        return raw
    monkeypatch.setattr(source.os,'read',read)
    with pytest.raises(ValueError):source._source_revision()
    assert sum(used)==0
