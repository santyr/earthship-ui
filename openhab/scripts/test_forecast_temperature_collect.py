"""Private explicit collection entrypoint; no household requests in tests."""
import importlib,importlib.util,json,os
from pathlib import Path
import pytest


def module():
    assert importlib.util.find_spec('forecast_temperature_collect') is not None, 'missing explicit correction collection entrypoint'
    return importlib.import_module('forecast_temperature_collect')


@pytest.fixture
def config(tmp_path):
    root=tmp_path/'private';root.mkdir(mode=0o700)
    for name in ('origins','packets'):(root/name).mkdir(mode=0o700)
    for name,raw in [('token','fixture'),('db.json',json.dumps(dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='fixture'))),('shared.lock','')]:
        p=root/name;p.write_text(raw);p.chmod(0o600)
    value={'schema':'earthship-temperature-correction-collect-config/v1','openhab_base':'http://127.0.0.1:8080/rest',
        'token_file':str(root/'token'),'native_db_config':str(root/'db.json'),'shared_lock':str(root/'shared.lock'),
        'origin_directory':str(root/'origins'),'output_directory':str(root/'packets')}
    path=root/'config.json';path.write_text(json.dumps(value));path.chmod(0o600)
    return path,value


def test_default_checks_private_configuration_without_live_collection(config,monkeypatch,capsys):
    m=module();path,_=config
    monkeypatch.setattr(m,'Backend',lambda _:pytest.fail('default constructed live backend'))
    assert m.main(['--config',str(path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='configuration_verified' and result['collection_executed'] is False and result['release_authority'] is False


@pytest.mark.parametrize('damage',['remote','extra','public_token','wrong_role','symlink','public_directory'])
def test_closed_private_restricted_configuration(config,damage):
    m=module();path,v=config
    if damage=='remote':v['openhab_base']='https://remote.example/rest'
    elif damage=='extra':v['active']=True
    elif damage=='public_token':Path(v['token_file']).chmod(0o644)
    elif damage=='wrong_role':
        p=Path(v['native_db_config']);db=json.loads(p.read_text());db['user']='postgres';p.write_text(json.dumps(db))
    elif damage=='symlink':
        q=path.parent/'linked';q.symlink_to(v['token_file']);v['token_file']=str(q)
    else:Path(v['output_directory']).chmod(0o755)
    path.write_text(json.dumps(v))
    with pytest.raises(ValueError):m.load_settings(path)


def test_secret_config_exception_is_not_printed(config,monkeypatch,capsys):
    m=module();path,_=config
    def failure(_):raise ValueError('SECRET transport configuration')
    monkeypatch.setattr(m,'load_settings',failure)
    assert m.main(['--config',str(path)])==1
    output=capsys.readouterr();assert 'SECRET' not in output.out+output.err
    assert json.loads(output.out)['release_authority'] is False


def test_shared_consumer_lock_skips_backend_construction(config,monkeypatch,capsys):
    import fcntl
    m=module();path,v=config
    monkeypatch.setattr(m,'_resource_preflight',lambda:None)
    monkeypatch.setattr(m,'Backend',lambda _:pytest.fail('busy shared lock constructed live backend'))
    with open(v['shared_lock'],'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert m.main(['--config',str(path),'--collect','--origin-sha256','a'*64,'--target','2026-10-09T14:00:00Z'])==0
    assert json.loads(capsys.readouterr().out)['status']=='busy'


def test_backend_refuses_changed_private_sources(config):
    m=module();path,v=config;backend=m.Backend(m.load_settings(path))
    Path(v['token_file']).write_text('changed fixture')
    with pytest.raises(ValueError):backend.verify_unchanged()


def test_backend_native_reads_fixed_role_and_original_raw_rows(config,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from test_weather_temperature_history import Connection
    import psycopg2
    m=module();path,v=config;now=datetime.now(timezone.utc);end=now-timedelta(minutes=6)
    c=Connection(rows=[(end-timedelta(seconds=1),'original invalid barrier')]);seen=[]
    def connect(**kwargs):seen.append(kwargs);return c
    monkeypatch.setattr(psycopg2,'connect',connect)
    backend=m.Backend(m.load_settings(path))
    result=backend.native(start=end-timedelta(minutes=5),end=end,assessed_at=now)
    assert result==[[(end-timedelta(seconds=1)).isoformat(),'original invalid barrier']]
    assert len(seen)==1 and seen[0]['user']=='weather_temperature_reader' and seen[0]['connect_timeout']==3
    assert c.closed and c.session['readonly'] is True


def test_default_fresh_process_does_not_import_heavy_transports(config):
    import subprocess,sys
    path,_=config
    script='''import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in ('numpy','scipy','psycopg2') or fullname in ('forecast_temperature_reads','thermal_model.capture_readers'):
   raise AssertionError('unguarded heavy transport import')
sys.meta_path.insert(0,Block())
import forecast_temperature_collect as command
raise SystemExit(command.main(['--config',sys.argv[1]]))
'''
    result=subprocess.run([sys.executable,'-c',script,str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0, 'config-only imported guarded dependencies: '+result.stderr
    assert json.loads(result.stdout)['collection_executed'] is False


def test_replaced_empty_shared_lock_is_refused(config):
    m=module();path,v=config
    with open(v['shared_lock'],'r+') as held:
        backend=m.Backend(m.load_settings(path))
        replacement=path.parent/'replacement.lock';replacement.write_text('');replacement.chmod(0o600)
        os.replace(replacement,v['shared_lock'])
        with pytest.raises(ValueError):backend.verify_unchanged()
