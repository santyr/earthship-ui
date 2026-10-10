"""A replaced global lock must never authorize another input consumer."""
import os
import pytest


def guard(path):
    import thermal_installed_score as cli
    assert hasattr(cli,'SharedScoreLock'),'missing no-follow owned global score lock'
    return cli.SharedScoreLock(path)


def test_missing_and_symlink_global_lock_never_created_or_followed(tmp_path):
    tmp_path.chmod(0o700);missing=tmp_path/'missing'
    with pytest.raises((ValueError,OSError)):
        with guard(missing):pytest.fail('missing lock accepted')
    assert not missing.exists()
    actual=tmp_path/'actual';actual.touch(mode=0o600);link=tmp_path/'link';link.symlink_to(actual)
    with pytest.raises((ValueError,OSError)):
        with guard(link):pytest.fail('symlink lock accepted')


def test_held_global_lock_blocks_second_reader_and_detects_replacement(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'lock';path.touch(mode=0o600)
    with guard(path) as held:
        held.verify()
        with pytest.raises(BlockingIOError):
            with guard(path):pytest.fail('concurrent reader accepted')
        path.unlink();path.touch(mode=0o600)
        with pytest.raises(ValueError):held.verify()


def test_public_or_hardlinked_lock_refused(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'lock';path.touch(mode=0o644)
    with pytest.raises(ValueError):
        with guard(path):pytest.fail('public lock accepted')
    path.chmod(0o600);os.link(path,tmp_path/'alias')
    with pytest.raises(ValueError):
        with guard(path):pytest.fail('hardlinked lock accepted')


def test_persistence_guard_runs_after_request_pacing(tmp_path):
    from datetime import datetime,timezone,timedelta
    from thermal_model.installed_shade_live_inputs import TelemetryTransport
    from thermal_model.capture_readers import ReadBudget
    tmp_path.chmod(0o700);path=tmp_path/'lock';path.touch(mode=0o600);calls=[];clock=[0.]
    def sleep(seconds):
        clock[0]+=seconds;path.unlink();path.touch(mode=0o600)
    def forbidden(*args,**kwargs):calls.append(args);pytest.fail('request sent after lock replacement')
    budget=ReadBudget(30,min_request_interval=1,sleeper=sleep,clock=lambda:clock[0]);budget.next_request=1.
    transport=TelemetryTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'fixture',budget=budget,opener=forbidden)
    at=datetime(2026,10,9,tzinfo=timezone.utc)
    with guard(path) as held:
        with pytest.raises(ValueError,match='shared lock'):
            transport.persisted('Thermal_Model_JSON','{}',since=at,until=at+timedelta(seconds=1),preflight=held.verify)
    assert calls==[]


def test_database_guard_runs_after_connection_pacing(tmp_path,monkeypatch):
    import psycopg2
    from thermal_model.installed_shade_score_inputs import ScoreReader
    tmp_path.chmod(0o700);path=tmp_path/'lock';path.touch(mode=0o600);calls=[]
    class Budget:
        def remaining(self):return 30
        def begin(self):path.unlink();path.touch(mode=0o600);return 30
    def connect(*args,**kwargs):calls.append(args);raise ValueError('fixture connection attempted')
    monkeypatch.setattr(psycopg2,'connect',connect)
    with guard(path) as held:
        reader=object.__new__(ScoreReader);reader.shared_lock_guard=held.verify
        reader.settings={};reader.hashes={};reader.budget=Budget()
        with pytest.raises(ValueError,match='shared lock'):
            reader._connect(dict(dbname='openhab',user='weather_temperature_reader',host='127.0.0.1',password='fixture'))
    assert calls==[]


def test_cli_busy_global_lock_constructs_no_source_reader(tmp_path,monkeypatch,capsys):
    import thermal_installed_score as cli
    import thermal_installed_intel as publication_cli
    from thermal_model import installed_shade_score_inputs as inputs
    tmp_path.chmod(0o700);path=tmp_path/'lock';path.touch(mode=0o600)
    monkeypatch.setattr(publication_cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'load_score_settings',lambda _:dict(output_directory=str(tmp_path)))
    monkeypatch.setattr(inputs,'ScoreReader',lambda *args,**kwargs:pytest.fail('busy lock constructed source reader'))
    with guard(path):
        result=cli.main(['--contract-version','1','--config',str(tmp_path/'config'),'--collect','--origin',str(tmp_path/'origin'),
            '--horizon','24','--shared-lock',str(path)])
    assert result==75
    import json
    assert json.loads(capsys.readouterr().out)==dict(status='busy',collection_executed=False,release_authorized=False)


def test_cli_collection_requires_global_lock_before_preflight(monkeypatch):
    import thermal_installed_score as cli
    import thermal_installed_intel as publication_cli
    monkeypatch.setattr(publication_cli,'_resource_preflight',lambda:pytest.fail('invalid intent reached resources'))
    with pytest.raises(SystemExit) as error:
        cli.main(['--config','/missing/config','--collect','--origin','/missing/origin','--horizon','1'])
    assert error.value.code==2


def test_shared_lock_implementation_is_in_declared_prediction_closure():
    import inspect
    import thermal_installed_score as cli
    from pathlib import Path
    from thermal_model.installed_shade_publication import RUNTIME_PATHS,RAW_RUNTIME_PATHS
    root=Path(cli.__file__).resolve().parent
    name=Path(inspect.getsourcefile(cli.SharedScoreLock)).resolve().relative_to(root).as_posix()
    assert name in RUNTIME_PATHS and name in RAW_RUNTIME_PATHS
    assert len(RAW_RUNTIME_PATHS)==64


def test_pinned_shared_guard_locks_without_scoring_cli_available(tmp_path):
    import subprocess,sys
    from pathlib import Path
    root=tmp_path/'sources';package=root/'thermal_model';package.mkdir(parents=True,mode=0o700)
    original=Path(__file__).resolve().parent/'thermal_model'
    for name in ('__init__.py','capture_guard.py','forcing_capture.py'):(package/name).write_bytes((original/name).read_bytes())
    lock=tmp_path/'lock';tmp_path.chmod(0o700);lock.touch(mode=0o600)
    code="""import sys,importlib.abc
sys.path.insert(0,sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='thermal_installed_score' or fullname.split('.')[0] in ('numpy','scipy'):raise RuntimeError('undeclared guard dependency')
sys.meta_path.insert(0,Block())
from thermal_model.capture_guard import SharedScoreLock
with SharedScoreLock(sys.argv[2]) as held:
 held.verify()
 try:
  with SharedScoreLock(sys.argv[2]):raise RuntimeError('concurrent reader accepted')
 except BlockingIOError:pass
"""
    result=subprocess.run([sys.executable,'-c',code,str(root),str(lock)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('source',['http','database','publication'])
def test_shared_budget_guard_refuses_publication_source_after_pacing(tmp_path,monkeypatch,source):
    from thermal_model.capture_readers import ReadBudget
    from thermal_model.installed_shade_live_inputs import TelemetryTransport,LiveBackend
    import psycopg2
    tmp_path.chmod(0o700);path=tmp_path/'lock';path.touch(mode=0o600);clock=[0.];calls=[]
    def sleep(seconds):clock[0]+=seconds;path.unlink();path.touch(mode=0o600)
    def forbidden(*a,**kw):calls.append(True);pytest.fail('source opened after shared lock replacement')
    with guard(path) as held:
        budget=ReadBudget(30,clock=lambda:clock[0],sleeper=sleep,guard=held.verify);budget.next_request=1.
        if source in ('http','publication'):
            backend=TelemetryTransport(base='http://127.0.0.1:8080/rest',token_reader=lambda:'fixture',budget=budget,opener=forbidden)
            if source=='publication':
                backend.checked.add('Thermal_Model_JSON');operation=lambda:backend.put('Thermal_Model_JSON','{}')
            else:operation=lambda:backend.require_string('Thermal_Model_JSON')
        else:
            monkeypatch.setattr(psycopg2,'connect',forbidden)
            backend=object.__new__(LiveBackend);backend.budget=budget;operation=lambda:backend._connect('fixture')
        with pytest.raises(ValueError,match='shared lock'):operation()
    assert calls==[]


def test_real_live_backend_requires_shared_guard_before_private_settings():
    from thermal_model.installed_shade_live_inputs import LiveBackend
    with pytest.raises(ValueError,match='shared'):
        LiveBackend({})
