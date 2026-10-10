"""Strong scorer profile dispatch under the existing real shared lock."""
import json
import os
from pathlib import Path
import pytest


@pytest.fixture
def settings(tmp_path,monkeypatch):
    from thermal_model import installed_shade_score_inputs as inputs
    for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'):
        monkeypatch.setenv(key,os.environ.get(key,'0'))
    tmp_path.chmod(0o700);out=tmp_path/'out';out.mkdir(mode=0o700)
    fields={key:str(tmp_path/key) for key in inputs.SOURCE_PATHS}
    for path in fields.values():Path(path).write_text('fixture');Path(path).chmod(0o600)
    value=dict(schema='earthship-installed-shade-score-config/v2',openhab_base='http://127.0.0.1:8080/rest',output_directory=str(out),**fields)
    path=tmp_path/'config';path.write_text(json.dumps(value));path.chmod(0o600)
    lock=tmp_path/'shared-lock';lock.touch(mode=0o600)
    return path,value,lock


def test_raw_score_config_refuses_legacy_reader_and_active_overrides(settings):
    from thermal_model import installed_shade_score_inputs as inputs
    path,value,_=settings
    assert inputs.load_raw_score_settings(path)==value
    with pytest.raises(ValueError):inputs.load_score_settings(path)
    path.write_text(json.dumps({**value,'active':True}))
    with pytest.raises(ValueError):inputs.load_raw_score_settings(path)


def test_default_raw_score_check_does_not_collect_or_create_archive_files(settings,monkeypatch,capsys):
    import thermal_installed_score as cli
    from thermal_model import installed_shade_score_inputs as inputs
    path,value,_=settings
    monkeypatch.setattr(inputs,'ScoreReader',lambda *a,**kw:pytest.fail('configuration check reached sources'))
    assert cli.main(['--config',str(path)])==0
    assert json.loads(capsys.readouterr().out)['collection_executed'] is False
    assert list(Path(value['output_directory']).iterdir())==[]


@pytest.mark.parametrize('batch',[False,True])
def test_default_score_dispatches_strong_collector_with_live_shared_lock(settings,monkeypatch,capsys,batch):
    import thermal_installed_score as cli,thermal_installed_intel as publication
    from thermal_model import installed_shade_score_inputs as inputs,installed_shade_score_collection as collection,installed_shade_score_jobs as queueing
    path,value,lock=settings;events=[]
    monkeypatch.setattr(publication,'_resource_preflight',lambda:events.append('guard'))
    class Reader:
        def __init__(self,settings,*,shared_lock_guard):
            assert events==['guard'];self.guard=shared_lock_guard;self.guard()
        def verify_unchanged(self):self.guard()
    monkeypatch.setattr(inputs,'ScoreReader',Reader)
    monkeypatch.setattr(collection,'collect_published_score',lambda **kw:pytest.fail('weak collector selected'))
    monkeypatch.setattr(queueing,'collect_queued_score',lambda **kw:pytest.fail('weak queue selected'))
    def collect(**kw):
        kw['backend'].verify_unchanged()
        assert kw['output_directory']==value['output_directory']
        return dict(status='scored',release_authorized=False)
    monkeypatch.setattr(collection,'collect_raw_published_score',collect)
    monkeypatch.setattr(queueing,'collect_raw_queued_score',collect,raising=False)
    args=['--batch','--queue',str(path.parent/'queue')] if batch else ['--collect','--origin',str(path.parent/'origin'),'--horizon','1']
    assert cli.main(['--config',str(path),'--shared-lock',str(lock),*args])==0
    assert json.loads(capsys.readouterr().out)['release_authorized'] is False


def test_raw_score_resource_refusal_precedes_config_and_native_reads(settings,monkeypatch,capsys):
    import thermal_installed_score as cli,thermal_installed_intel as publication
    from thermal_model import installed_shade_score_inputs as inputs
    path,_,lock=settings
    def refused():raise ValueError('synthetic resource refusal')
    monkeypatch.setattr(publication,'_resource_preflight',refused)
    monkeypatch.setattr(inputs,'load_raw_score_settings',lambda *_:pytest.fail('source read after resource refusal'),raising=False)
    assert cli.main(['--config',str(path),'--shared-lock',str(lock),'--collect','--origin','/missing','--horizon','1'])==1
    assert json.loads(capsys.readouterr().out)['status']=='withheld'
