"""Explicit operator routing only; no household transport, fitting or actuation."""
import json
from pathlib import Path
import pytest
from test_installed_shade_raw_live_cli import raw_settings


@pytest.fixture
def compressed_settings(raw_settings):
    path,value,refs=raw_settings
    value=dict(value,schema='earthship-installed-shade-live-config/v3')
    refs=dict(refs,schema='earthship-installed-shade-release-inputs/v4')
    Path(value['release_inputs_path']).write_text(json.dumps(refs))
    path.write_text(json.dumps(value))
    return path,value,refs


def test_compressed_config_requires_distinct_original_reference_profile(compressed_settings):
    from thermal_model import installed_shade_live_inputs as inputs
    path,value,refs=compressed_settings
    api=getattr(inputs,'load_compressed_live_settings',None)
    assert callable(api),'missing compressed operator configuration'
    assert api(path)==value
    with pytest.raises(ValueError):inputs.load_raw_live_settings(path)
    Path(value['release_inputs_path']).write_text(json.dumps(dict(refs,schema='earthship-installed-shade-release-inputs/v3')))
    with pytest.raises(ValueError):api(path)


def test_compressed_cli_check_constructs_no_transport(compressed_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs
    monkeypatch.setattr(inputs,'CompressedSourceLiveBackend',lambda *a,**kw:pytest.fail('check reached transport'))
    assert cli.main(['--config',str(compressed_settings[0]),'--contract-version','3','--check-only'])==0
    assert json.loads(capsys.readouterr().out)['publication_executed'] is False


def test_compressed_cli_publish_selects_source_backend_and_strong_worker(compressed_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live
    path,value,_=compressed_settings;events=[];backend=object()
    monkeypatch.setattr(cli,'_resource_preflight',lambda:events.append('guard'))
    monkeypatch.setattr(inputs,'CompressedSourceLiveBackend',lambda settings,**kw:backend)
    monkeypatch.setattr(inputs,'LiveBackend',lambda *a,**kw:pytest.fail('legacy backend selected'))
    def run(**kw):
        assert events==['guard'] and kw==dict(reference_path=value['release_inputs_path'],archive=value['evidence_directory'],backend=backend)
        return dict(status='published',mode='shadow',delivery_verified=True,automatic_actuation=False)
    monkeypatch.setattr(live,'run_compressed_live_cycle',run,raising=False)
    lock=path.parent/'lock';lock.touch(mode=0o600)
    assert cli.main(['--config',str(path),'--contract-version','3','--publish','--shared-lock',str(lock)])==0
    assert json.loads(capsys.readouterr().out)['mode']=='shadow'


def test_compressed_cli_resource_refusal_never_reaches_transport(compressed_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs
    def refuse():raise ValueError('private resource failure')
    monkeypatch.setattr(cli,'_resource_preflight',refuse)
    monkeypatch.setattr(inputs,'CompressedSourceLiveBackend',lambda *a,**kw:pytest.fail('failed preflight reached backend'))
    lock=compressed_settings[0].parent/'lock';lock.touch(mode=0o600)
    assert cli.main(['--config',str(compressed_settings[0]),'--contract-version','3','--publish','--shared-lock',str(lock)])==1
    output=capsys.readouterr();assert 'private resource failure' not in output.out+output.err


def test_compressed_worker_rejects_weaker_preparation_before_collection(tmp_path,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from thermal_model import installed_shade_live as live
    from thermal_model.installed_shade_publication import PreparedRawInstalledQualification
    from test_installed_shade_live import FakeBackend
    api=getattr(live,'run_compressed_live_cycle',None)
    assert callable(api),'missing compressed live worker'
    tmp_path.chmod(0o700);issue=datetime(2026,11,8,18,tzinfo=timezone.utc);live._test_time=issue-timedelta(seconds=45)
    monkeypatch.setattr(live,'_clock',lambda:live._test_time)
    monkeypatch.setattr(live,'prepare_compressed_installed_qualification',lambda _:PreparedRawInstalledQualification(None,None,True),raising=False)
    backend=FakeBackend(live,issue)
    result=api(reference_path=tmp_path/'refs',archive=tmp_path,backend=backend)
    assert result['status']=='withdrawn' and backend.collected is False
    assert [item for item,_ in backend.puts]==['Thermal_Model_JSON']
    assert backend.puts[0][1]['version']==7


def test_compressed_withdrawal_is_model_independent_and_verifies_actual_receipt(tmp_path,monkeypatch):
    from datetime import datetime,timezone
    from thermal_model import installed_shade_live as live
    from test_installed_shade_live import FakeBackend
    api=getattr(live,'withdraw_compressed_live_publication',None)
    assert callable(api),'missing compressed operational withdrawal'
    tmp_path.chmod(0o700);issue=datetime(2026,11,8,18,tzinfo=timezone.utc);live._test_time=issue
    monkeypatch.setattr(live,'_clock',lambda:live._test_time)
    backend=FakeBackend(live,issue)
    result=api(archive=tmp_path,backend=backend,reason='qualification withdrawn')
    assert result['status']=='withdrawn' and result['delivery_verified'] is True
    record=json.loads(Path(result['receipt_path']).read_text())
    assert record['schema']=='earthship-installed-shade-withdrawal/v3'
    assert record['publication']==backend.rows['Thermal_Model_JSON']
    assert backend.puts[0][1]['version']==7


def test_compressed_cli_withdraw_config_needs_no_model_or_native_sources(compressed_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live
    path,value,_=compressed_settings
    withdrawal={key:value[key] for key in inputs.WITHDRAW_FIELDS};withdrawal['schema']='earthship-installed-shade-withdraw-config/v3'
    path.write_text(json.dumps(withdrawal))
    for key in inputs.SOURCE_PATHS-{'token_file'}:Path(value[key]).unlink()
    assert inputs.load_compressed_withdraw_settings(path)==withdrawal
    with pytest.raises(ValueError):inputs.load_raw_withdraw_settings(path)
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'WithdrawalBackend',lambda settings:object())
    def withdraw(**kw):
        assert kw['archive']==value['evidence_directory'] and kw['reason']=='qualification withdrawn'
        return dict(status='withdrawn',mode='unavailable',delivery_verified=True,automatic_actuation=False)
    monkeypatch.setattr(live,'withdraw_compressed_live_publication',withdraw)
    assert cli.main(['--config',str(path),'--contract-version','3','--withdraw','--reason','qualification withdrawn'])==0
    assert json.loads(capsys.readouterr().out)['mode']=='unavailable'
