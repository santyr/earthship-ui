"""Production CLI profile selection, without household transport or fitting."""
import json
import os
from pathlib import Path
import pytest


@pytest.fixture
def raw_settings(tmp_path,monkeypatch):
    # CLI fitting flags belong to one invocation; keep their mutation local
    # to this test rather than changing later hosted-suite fit permissions.
    for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'):
        monkeypatch.setenv(key,os.environ.get(key,'0'))
    from thermal_model import installed_shade_live_inputs as inputs
    tmp_path.chmod(0o700);archive=tmp_path/'evidence';archive.mkdir(mode=0o700)
    fields={key:str(tmp_path/key) for key in inputs.SOURCE_PATHS}
    for value in fields.values():
        path=Path(value);path.write_text('fixture');path.chmod(0o600)
    refs=dict(schema='earthship-installed-shade-release-inputs/v3',registration_path=None,
        candidate_path=str(tmp_path/'candidate'),runtime_bundle_path=str(tmp_path/'runtime'),original_pairs_path=str(tmp_path/'pairs'))
    Path(fields['release_inputs_path']).write_text(json.dumps(refs))
    value=dict(schema='earthship-installed-shade-live-config/v2',openhab_base='http://127.0.0.1:8080/rest',evidence_directory=str(archive),**fields)
    config=tmp_path/'config';config.write_text(json.dumps(value));config.chmod(0o600)
    return config,value,refs


def test_raw_config_requires_closed_strong_reference_and_legacy_reader_refuses_it(raw_settings):
    from thermal_model import installed_shade_live_inputs as inputs
    path,value,refs=raw_settings
    assert inputs.load_raw_live_settings(path)==value
    with pytest.raises(ValueError):inputs.load_live_settings(path)
    for schema in ('earthship-installed-shade-release-inputs/v1','earthship-installed-shade-release-inputs/v2'):
        Path(value['release_inputs_path']).write_text(json.dumps({**refs,'schema':schema}))
        with pytest.raises(ValueError):inputs.load_raw_live_settings(path)
    Path(value['release_inputs_path']).write_text(json.dumps({**refs,'active':True}))
    with pytest.raises(ValueError):inputs.load_raw_live_settings(path)


def test_default_cli_checks_raw_config_without_transport(raw_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs
    path,value,_=raw_settings
    monkeypatch.setattr(inputs,'LiveBackend',lambda *_:pytest.fail('check reached transport'))
    assert cli.main(['--config',str(path)])==0
    assert json.loads(capsys.readouterr().out)['publication_executed'] is False
    assert list(Path(value['evidence_directory']).iterdir())==[]


def test_legacy_publish_refused_before_resource_or_transport(monkeypatch):
    import thermal_installed_intel as cli
    monkeypatch.setattr(cli,'_resource_preflight',lambda:pytest.fail('legacy publish reached resource preflight'))
    with pytest.raises(SystemExit) as error:
        cli.main(['--config','/missing','--contract-version','1','--publish'])
    assert error.value.code==2


def test_default_publish_dispatches_raw_worker_after_resource_guard(raw_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live
    path,value,_=raw_settings;events=[];backend=object()
    monkeypatch.setattr(cli,'_resource_preflight',lambda:events.append('guard'))
    monkeypatch.setattr(inputs,'LiveBackend',lambda settings,**kw:backend)
    monkeypatch.setattr(live,'run_live_cycle',lambda **kw:pytest.fail('weak worker selected'))
    def run(**kw):
        assert events==['guard'] and kw==dict(reference_path=value['release_inputs_path'],archive=value['evidence_directory'],backend=backend)
        return dict(status='published',mode='shadow',delivery_verified=True,automatic_actuation=False)
    monkeypatch.setattr(live,'run_raw_live_cycle',run)
    lock=path.parent/'lock';lock.touch(mode=0o600)
    assert cli.main(['--config',str(path),'--publish','--shared-lock',str(lock)])==0
    assert json.loads(capsys.readouterr().out)['mode']=='shadow'


def test_raw_withdraw_config_independent_of_model_and_source_files(raw_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live
    path,value,_=raw_settings
    withdrawal={key:value[key] for key in inputs.WITHDRAW_FIELDS};withdrawal['schema']='earthship-installed-shade-withdraw-config/v2'
    path.write_text(json.dumps(withdrawal))
    for key in inputs.SOURCE_PATHS-{'token_file'}:Path(value[key]).unlink()
    assert inputs.load_raw_withdraw_settings(path)==withdrawal
    with pytest.raises(ValueError):inputs.load_withdraw_settings(path)
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(inputs,'WithdrawalBackend',lambda settings:object())
    monkeypatch.setattr(live,'withdraw_live_publication',lambda **kw:pytest.fail('weak withdrawal selected'))
    def withdraw(**kw):
        assert kw['reason']=='operator' and kw['archive']==value['evidence_directory']
        return dict(status='withdrawn',mode='unavailable',delivery_verified=True,automatic_actuation=False)
    monkeypatch.setattr(live,'withdraw_raw_live_publication',withdraw)
    assert cli.main(['--config',str(path),'--withdraw','--reason','operator'])==0
    assert json.loads(capsys.readouterr().out)['delivery_verified'] is True


def test_explicit_base_bootstrap_dispatch_preserves_raw_native_shadow_route(raw_settings,monkeypatch,capsys):
    import thermal_installed_intel as cli
    from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live
    path,value,_=raw_settings;value={**value,'schema':'earthship-installed-shade-live-config/v1'}
    path.write_text(json.dumps(value));events=[]
    monkeypatch.setattr(cli,'_resource_preflight',lambda:events.append('guard'))
    monkeypatch.setattr(inputs,'LiveBackend',lambda _,**kw:object())
    monkeypatch.setattr(live,'run_live_cycle',lambda **kw:pytest.fail('unrestricted legacy worker selected'))
    def bootstrap(**kw):
        assert events==['guard']
        return dict(status='published',mode='shadow',delivery_verified=True,automatic_actuation=False)
    monkeypatch.setattr(live,'run_bootstrap_live_cycle',bootstrap,raising=False)
    lock=path.parent/'lock';lock.touch(mode=0o600)
    assert cli.main(['--config',str(path),'--contract-version','1','--bootstrap-shadow','--shared-lock',str(lock)])==0
    assert json.loads(capsys.readouterr().out)['mode']=='shadow'


@pytest.mark.parametrize('intent',['--publish','--bootstrap-shadow'])
def test_publisher_busy_shared_lock_reads_no_config_or_backend(tmp_path,monkeypatch,capsys,intent):
    import thermal_installed_intel as cli
    from thermal_model.capture_guard import SharedScoreLock
    from thermal_model import installed_shade_live_inputs as inputs
    tmp_path.chmod(0o700);lock=tmp_path/'lock';lock.touch(mode=0o600)
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    for name in ('load_live_settings','load_raw_live_settings','LiveBackend'):
        monkeypatch.setattr(inputs,name,lambda *a,**kw:pytest.fail('busy publisher reached protected sources'))
    argv=['--config','/missing','--shared-lock',str(lock),intent]
    if intent=='--bootstrap-shadow':argv+=['--contract-version','1']
    with SharedScoreLock(lock):assert cli.main(argv)==75
    assert json.loads(capsys.readouterr().out)==dict(status='busy',publication_executed=False,automatic_actuation=False)


def test_publication_requires_shared_lock_before_preflight(monkeypatch):
    import thermal_installed_intel as cli
    monkeypatch.setattr(cli,'_resource_preflight',lambda:pytest.fail('unserialized publication reached resources'))
    with pytest.raises(SystemExit) as error:cli.main(['--config','/missing','--publish'])
    assert error.value.code==2


def test_forecast_example_joins_shared_slice_and_requires_consumer_lock():
    path=Path(__file__).resolve().parents[1]/'systemd/user/thermal-installed-forecast.service'
    text=path.read_text()
    assert 'Slice=earthship-inputs.slice' in text
    assert '--shared-lock @VERIFIED_SHARED_LOCK@' in text
