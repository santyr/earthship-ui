"""Off-host orchestration tests never start Docker or touch a database locally."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json,subprocess,psycopg2
import pytest
from test_thermal_journal_transfer import inputs,NOW
import thermal_journal_transfer as transfer


def module():
    import thermal_journal_restore_transfer
    return thermal_journal_restore_transfer


def case(tmp_path,monkeypatch):
    data=inputs(tmp_path);package=transfer.prepare_journal_transfer(**data)
    proof=tmp_path/'proof';proof.mkdir(mode=0o700)
    runtime=tmp_path/'consumer';runtime.mkdir(mode=0o700)
    raw=b'controlled interpreter identity'
    monkeypatch.setenv('EARTHSHIP_REMOTE_JOURNAL_RESTORE','1')
    monkeypatch.setattr(module(),'_source_bytes',lambda *args,**kwargs:raw)
    args=dict(package=package,consumer_runtime=runtime,expected_consumer_revision='c'*64,
        expected_interpreter_sha256=sha256(raw).hexdigest(),proof_directory=proof,clock=lambda:NOW)
    return data,args


class Backend:
    def __init__(self,proofs):self.proofs=proofs;self.events=[]
    def check_archive(self,path):self.events.append('archive')
    def start(self,name,password,role,token):self.events.append('start');return dict(host='127.0.0.1',port=54321,dbname='postgres',user='postgres',password=password)
    def restore(self,path,params,role,source_schema):self.events.append('restore');return self.proofs
    def consumer(self,params,role,runtime,revision):
        self.events.append('consumer');return dict(status='installed_consumer_qualified',runtime_revision=revision,
            connection_read_only=True,runtime_role_verified=True,distinct_fixture_observations=6,
            legacy_samples_unchanged=True,legacy_support_rows=1,sample_sha256='d'*64)
    def cleanup(self,name,token):self.events.append('cleanup')


def test_default_optin_refuses_before_package_io_or_backend(tmp_path,monkeypatch):
    source=module();monkeypatch.delenv('EARTHSHIP_REMOTE_JOURNAL_RESTORE',raising=False)
    monkeypatch.setattr(source,'read_journal_transfer',lambda *_:pytest.fail('unapproved restore read package'))
    with pytest.raises(ValueError):source.qualify_journal_transfer(package=Path('/unread'),consumer_runtime=Path('/unread'),expected_consumer_revision='a'*64,expected_interpreter_sha256='b'*64,proof_directory=tmp_path)


def test_restore_report_publishes_only_after_cleanup_and_keeps_authority_closed(tmp_path,monkeypatch):
    data,args=case(tmp_path,monkeypatch);backend=Backend(data['table_proofs'])
    path=module().qualify_journal_transfer(**args,backend=backend)
    assert backend.events==['archive','start','restore','consumer','cleanup']
    report=json.loads(path.read_text())
    assert report['disposable_restore_qualified'] is True and report['consumer_qualified'] is True
    assert report['source_export_authenticated'] is False and report['cold_environment_qualified'] is False
    assert report['journal_recovery_qualified'] is False and report['installed'] is False and report['release_authorized'] is False
    assert path.stat().st_mode&0o777==0o600


@pytest.mark.parametrize('failure',['start','restore','consumer','cleanup','rows'])
def test_failed_restore_path_cannot_publish_success_proof(tmp_path,monkeypatch,failure):
    data,args=case(tmp_path,monkeypatch);backend=Backend(data['table_proofs'])
    if failure=='rows':backend.proofs={}
    else:
        def failed(*args,**kwargs):backend.events.append(failure);raise OSError('controlled backend failure')
        monkeypatch.setattr(backend,failure,failed)
    with pytest.raises((OSError,ValueError)):module().qualify_journal_transfer(**args,backend=backend)
    assert list(args['proof_directory'].iterdir())==[]
    assert backend.events[-1]=='cleanup'


@pytest.mark.parametrize('damage',['interpreter','proof_overlap','proof_nonempty','consumer_proof','package_changed','persistence'])
def test_changed_context_cannot_publish_restoration_proof(tmp_path,monkeypatch,damage):
    data,args=case(tmp_path,monkeypatch);backend=Backend(data['table_proofs']);source=module()
    if damage=='interpreter':args['expected_interpreter_sha256']='0'*64
    elif damage=='proof_overlap':args['proof_directory']=args['consumer_runtime']
    elif damage=='proof_nonempty':(args['proof_directory']/'prior').write_bytes(b'prior')
    elif damage=='consumer_proof':monkeypatch.setattr(backend,'consumer',lambda *args:{'status':'installed_consumer_qualified'})
    elif damage=='package_changed':
        original=backend.consumer
        def changed(*values):
            result=original(*values);(args['package']/'journal.dump').write_bytes(b'PGDMP changed');return result
        monkeypatch.setattr(backend,'consumer',changed)
    else:
        def interrupted(path,raw):path.write_bytes(b'partial');raise OSError('controlled proof persistence failure')
        monkeypatch.setattr(source,'_write_private',interrupted)
    with pytest.raises((ValueError,OSError)):source.qualify_journal_transfer(**args,backend=backend)
    assert list(args['proof_directory'].glob('*.journal-restore-report-v1.json'))==[]
    if 'start' in backend.events:assert backend.events[-1]=='cleanup'
    assert not list(args['proof_directory'].glob('.journal-proof-*'))


@pytest.mark.parametrize('ownership',['foreign','absent','owned'])
def test_default_cleanup_only_removes_label_owned_container(monkeypatch,ownership):
    source=module();name='thermal-transfer-'+'a'*32;token='b'*32;mutations=[]
    def docker(argv):
        if argv[0]=='ps':return SimpleNamespace(returncode=0,stdout=b'' if ownership=='absent' or mutations else name.encode())
        if argv[0]=='inspect':return SimpleNamespace(returncode=0,stdout=('d'*64+' /'+name+' '+(token if ownership=='owned' else 'c'*32)).encode())
        assert ownership=='owned','foreign container must not be removed'
        mutations.append(argv);return SimpleNamespace(returncode=0,stdout=b'')
    monkeypatch.setattr(source,'_docker',docker)
    if ownership=='foreign':
        with pytest.raises(ValueError,match='ownership'):source.DisposableBackend().cleanup(name,token)
    else:source.DisposableBackend().cleanup(name,token)
    assert len(mutations)==(1 if ownership=='owned' else 0)


def test_owned_start_label_is_applied_to_the_actual_docker_run(monkeypatch):
    source=module();live=source._live();commands=[]
    def run(argv,**kwargs):
        commands.append(argv);return SimpleNamespace(returncode=0,stdout=b'127.0.0.1:54321')
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):pass
    class Connection(Cursor):
        def cursor(self):return Cursor()
        def close(self):pass
    monkeypatch.setattr(live.subprocess,'run',run)
    monkeypatch.setattr(live.psycopg2,'connect',lambda **kwargs:Connection())
    live.disposable_database('fixture-owned-container','disposable fixture','fixture_reader',ownership_token='a'*32)
    argv=commands[0]
    assert argv[argv.index('--label')+1]=='earthship.thermal.restore-token='+'a'*32
    assert argv[argv.index('--publish')+1]=='127.0.0.1::5432'
    assert argv[argv.index('--memory')+1]=='512m'


@pytest.mark.parametrize("failure",[ValueError("fixture-private-password"),subprocess.CalledProcessError(1,["docker","fixture-private-password"]),psycopg2.OperationalError("fixture-private-password"),psycopg2.DataError("fixture-private-password in source row")])
def test_cli_failure_does_not_expose_backend_exception_details(tmp_path,monkeypatch,capsys,failure):
    import importlib.util
    spec=importlib.util.spec_from_file_location('journal_restore_cli',Path(__file__).with_name('qualify-thermal-journal-transfer.py'))
    command=importlib.util.module_from_spec(spec);spec.loader.exec_module(command)
    def refused(**kwargs):raise failure
    monkeypatch.setattr(command,'qualify_journal_transfer',refused)
    assert command.main(['--transfer','/private/input','--consumer-runtime','/private/runtime','--expected-consumer-revision','a'*64,'--expected-interpreter-sha256','b'*64,'--proof-directory','/private/proof'])==2
    assert 'fixture-private-password' not in capsys.readouterr().err


def test_name_replacement_after_inspection_never_removes_foreign_container(monkeypatch):
    source=module();name='thermal-transfer-'+'a'*32;token='b'*32;owned='d'*64
    state=dict(replaced=False,owned_removed=False,foreign_removed=False)
    def docker(argv):
        if argv[0]=='ps':
            if '--filter' in argv and argv[argv.index('--filter')+1].startswith('id='):
                return SimpleNamespace(returncode=0,stdout=b'' if state['owned_removed'] else owned.encode())
            return SimpleNamespace(returncode=0,stdout=name.encode())
        if argv[0]=='inspect':
            state['replaced']=True
            body=token if argv[argv.index('--format')+1].startswith('{{index') else owned+' /'+name+' '+token
            return SimpleNamespace(returncode=0,stdout=body.encode())
        if argv[0]=='rm':
            state['owned_removed']=argv[-1]==owned
            state['foreign_removed']=state['replaced'] and argv[-1]==name
            return SimpleNamespace(returncode=0,stdout=b'')
        pytest.fail('unexpected Docker operation')
    monkeypatch.setattr(source,'_docker',docker)
    with pytest.raises(ValueError):source.DisposableBackend().cleanup(name,token)
    assert state['foreign_removed'] is False
    assert state['owned_removed'] is True


@pytest.mark.parametrize('error',[psycopg2.OperationalError('private database endpoint'),psycopg2.DataError('private source row')])
def test_database_failure_cleans_owned_target_without_success_proof(tmp_path,monkeypatch,error):
    data,args=case(tmp_path,monkeypatch);backend=Backend(data['table_proofs'])
    def failed(*args):backend.events.append('consumer');raise error
    monkeypatch.setattr(backend,'consumer',failed)
    with pytest.raises(psycopg2.Error):module().qualify_journal_transfer(**args,backend=backend)
    assert backend.events[-1]=='cleanup'
    assert list(args['proof_directory'].iterdir())==[]


def source_case(tmp_path,monkeypatch):
    from test_thermal_journal_source_receipt import generation
    _,args=case(tmp_path,monkeypatch)
    generation_path,record=generation(tmp_path)
    args.update(package=generation_path/'transfer'/record['transfer_sha256'],source_generation=generation_path,
        expected_source_receipt_sha256=record['source_receipt_sha256'],expected_exporter_revision=record['source_code_revision'])
    return record,args


def test_original_source_binding_uses_v2_report_and_keeps_authority_closed(tmp_path,monkeypatch):
    record,args=source_case(tmp_path,monkeypatch);backend=Backend(record['table_proofs'])
    path=module().qualify_journal_transfer(**args,backend=backend)
    result=json.loads(path.read_text())
    assert result['schema']=='earthship-thermal-journal-restore-report/v2'
    assert result['source_export_binding']['source_receipt_sha256']==record['source_receipt_sha256']
    assert result['source_export_binding']['original_receipt_verified'] is True
    assert result['source_export_authenticated'] is False and result['journal_recovery_qualified'] is False
    assert result['installed'] is False and result['release_authorized'] is False
    assert backend.events[-1]=='cleanup'


@pytest.mark.parametrize('damage',['missing_pin','wrong_pin','wrong_code','other_package'])
def test_invalid_source_context_refuses_before_backend_work(tmp_path,monkeypatch,damage):
    record,args=source_case(tmp_path,monkeypatch);backend=Backend(record['table_proofs'])
    if damage=='missing_pin':args['expected_source_receipt_sha256']=None
    elif damage=='wrong_pin':args['expected_source_receipt_sha256']='f'*64
    elif damage=='wrong_code':args['expected_exporter_revision']='f'*64
    else:args['package']=tmp_path/'packages'/'another'
    with pytest.raises(ValueError):module().qualify_journal_transfer(**args,backend=backend)
    assert backend.events==[] and list(args['proof_directory'].iterdir())==[]


def test_changed_original_receipt_after_consumer_refuses_success_proof(tmp_path,monkeypatch):
    record,args=source_case(tmp_path,monkeypatch);backend=Backend(record['table_proofs']);original=backend.consumer
    def changed(*values):
        result=original(*values)
        (args['source_generation']/'source-receipt.json').write_bytes(b'changed original')
        return result
    monkeypatch.setattr(backend,'consumer',changed)
    with pytest.raises(ValueError):module().qualify_journal_transfer(**args,backend=backend)
    assert backend.events[-1]=='cleanup' and list(args['proof_directory'].iterdir())==[]


def test_cli_forwards_original_source_generation_and_independent_pins(monkeypatch,tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('source_bound_restore_cli',Path(__file__).with_name('qualify-thermal-journal-transfer.py'))
    command=importlib.util.module_from_spec(spec);spec.loader.exec_module(command)
    received=[]
    def invoked(**kwargs):received.append(kwargs);return tmp_path/'private-report.json'
    monkeypatch.setattr(command,'qualify_journal_transfer',invoked)
    assert command.main(['--transfer','/private/source/transfer','--consumer-runtime','/private/runtime','--expected-consumer-revision','a'*64,
        '--expected-interpreter-sha256','b'*64,'--proof-directory','/private/proof','--source-generation','/private/source',
        '--expected-source-receipt-sha256','c'*64,'--expected-exporter-revision','d'*64])==0
    assert received[0]['source_generation']==Path('/private/source')
    assert received[0]['expected_source_receipt_sha256']=='c'*64 and received[0]['expected_exporter_revision']=='d'*64
