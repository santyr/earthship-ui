"""Retained scorers expose bounded reasons without logging private exception text."""
from hashlib import sha256
import json
from pathlib import Path
import pytest
import household_forecast_score as score


@pytest.mark.parametrize('error,reason',[
    (ValueError('training host pressure or memory reserve unavailable: interval memory pressure exceeded'),'memory_pressure'),
    (ValueError('training host pressure or memory reserve unavailable: host swap-read activity exceeded bounded allowance'),'host_swap_read'),
    (ValueError('publication memory headroom unavailable'),'memory_headroom'),
    (ValueError('score lifetime elapsed'),'deadline'),
    (TimeoutError('private query details'),'deadline'),
    (OSError('private connection details'),'io_unavailable'),
    (ValueError('private token-bearing input'),'validation_refused'),
    (RuntimeError('private runtime details'),'unexpected_failure'),
])
def test_cli_failure_reasons_never_include_original_error_text(error,reason,tmp_path,monkeypatch,capsys):
    def fail(*a,**kw):raise error
    monkeypatch.setattr(score,'run',fail)
    assert score.main(['--config',str(tmp_path/'config.json')])==1
    result=json.loads(capsys.readouterr().out)
    site=result.pop('site');assert site['source']=='test_household_score_diagnostics.py' and site['line']>0
    assert result==dict(status='score_withheld',reason=reason,fit_executed=False,automatic_actuation=False)


def archive(tmp_path,monkeypatch,body):
    import household_cycle_deploy as deploy
    monkeypatch.setattr(score,'production_resource_preflight',lambda:None)
    tmp_path.chmod(0o700);stage=tmp_path/'old';stage.mkdir(mode=0o700)
    script=stage/'sources/openhab/scripts/household_forecast_score.py';script.parent.mkdir(parents=True)
    script.write_text(body);manifest=stage/'deployment.json';manifest.write_text('{}');manifest.chmod(0o600)
    config=stage/'forecast.json';config.write_text(json.dumps({'schema':'earthship-weathernext-thermal-live-config/v2'}));config.chmod(0o600)
    cycle=stage/'cycle.json';cycle.write_text(json.dumps({'forecast_config':str(config)}));cycle.chmod(0o600)
    source_hash=sha256(script.read_bytes()).hexdigest()
    monkeypatch.setattr(deploy,'__file__',str(script.parent/'household_cycle_deploy.py'))
    monkeypatch.setattr(deploy,'verify_stage',lambda actual,**kwargs:dict(schema='earthship-household-cycle-deployment/v3',source_manifest={'openhab/scripts/household_forecast_score.py':source_hash}))
    return stage,script,sha256(manifest.read_bytes()).hexdigest()


def test_retired_worker_cannot_run_original_function_with_its_original_stage(tmp_path,monkeypatch):
    native=False
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(config, **kwargs):\n return dict(status='waiting',config=str(config),stage=str(kwargs['stage']),native=kwargs.get('retained_native',False),pin=kwargs.get('deployment_sha256'))\n")
    with pytest.raises(ValueError,match='Google-only'):
        score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=native)


def test_retained_worker_refuses_source_drift_before_executing(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    script.write_text(script.read_text()+'# changed\n')
    with pytest.raises(ValueError):score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=False)


def test_retained_worker_refuses_external_manifest_drift(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    (stage/'deployment.json').write_text('{ }')
    with pytest.raises(ValueError):score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=False)


def test_retired_archive_refusal_reaches_current_secret_free_cli(tmp_path,monkeypatch,capsys):
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(*args, **kwargs):\n raise OSError('private connection details')\n")
    result=score.main(['--config',str(stage/'forecast.json'),'--stage',str(stage),'--worker-script',str(script),'--worker-deployment-sha256',pin])
    assert result==1
    result=json.loads(capsys.readouterr().out)
    site=result.pop('site');assert site['source']=='household_forecast_score.py'
    assert result==dict(status='score_withheld',reason='validation_refused',fit_executed=False,automatic_actuation=False)


def test_retained_worker_rejects_mixed_dependency_context(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    original_file=deploy.__file__
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    monkeypatch.setattr(deploy,'__file__',original_file)
    with pytest.raises(ValueError,match='Google-only'):
        score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=False)


def test_python_safe_path_keeps_archived_dependencies_in_the_child(tmp_path):
    import os,subprocess,sys
    current=tmp_path/'current';old=tmp_path/'old';current.mkdir();old.mkdir()
    (current/'selected_dependency.py').write_text("VALUE='current'\n")
    (old/'selected_dependency.py').write_text("VALUE='retained'\n")
    runner=current/'worker.py';runner.write_text('import selected_dependency; print(selected_dependency.VALUE)\n')
    output=subprocess.check_output([sys.executable,'-P',str(runner)],env=dict(os.environ,PYTHONPATH=str(old)),text=True,timeout=5)
    assert output.strip()=='retained'


def test_retired_dispatch_executor_cannot_reenter_any_archived_dependency():
    assert not hasattr(score,'execute_legacy_score')


def test_retired_worker_does_not_consult_original_bytes_helper(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    def forbidden(*args,**kwargs):pytest.fail('retired worker read archived source')
    monkeypatch.setattr(deploy,'_bytes',forbidden)
    with pytest.raises(ValueError,match='Google-only'):
        score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=False)


@pytest.mark.parametrize('message',[
    'capture read deadline exceeded','capture request pacing exceeds deadline',
    'native query deadline elapsed or too short','bounded native connection deadline unavailable',
])
def test_reader_deadlines_are_not_misreported_as_validation_failures(message):
    assert score.failure_reason(ValueError(message))=='deadline'


def test_failure_site_contains_only_owned_source_and_line(tmp_path):
    source=tmp_path/'sources/openhab/scripts/thermal_model/sample.py'
    source.parent.mkdir(parents=True)
    source.write_text("raise ValueError('private token-bearing input')\n")
    import runpy
    try:runpy.run_path(str(source))
    except ValueError as error:
        assert score.failure_site(error)==dict(source='thermal_model/sample.py',line=1)


def test_failure_site_omits_external_code_and_invalid_source_paths():
    for filename in ['/private/credentials.py','/archive/openhab/scripts/../private.py','/archive/openhab/scripts/private value.py']:
        try:exec(compile("raise ValueError('private input')",filename,'exec'),{})
        except ValueError as error:assert score.failure_site(error) is None


def test_retired_entrypoint_cannot_request_even_current_admission(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    calls=[]
    monkeypatch.setattr(score,'production_resource_preflight',lambda:calls.append('current'))
    with pytest.raises(ValueError,match='Google-only'):
        score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=False)
    assert calls==[]


def test_retained_native_worker_uses_current_orchestration_with_original_archive(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(*args, **kwargs):\n raise ValueError('obsolete fifty-second coordinator executed')\n")
    import types
    def current(config,*,stage,deployment_sha256,deadline,resource_preflight,pressure_factory,source_guard,verify_archive,clock,monotonic):
        assert deployment_sha256==pin and deadline==120. and stage==script.parents[3]
        resource_preflight();source_guard();verify_archive()
        return dict(status='waiting',automatic_actuation=False)
    monkeypatch.setattr(score,'production_retained_runner',lambda:types.SimpleNamespace(run=current))
    assert score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,
        retained_native=True,monotonic=lambda:0.)==dict(status='waiting',automatic_actuation=False)


def test_current_retained_helper_source_drift_refuses_before_archive_runs(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(*args, **kwargs):\n raise AssertionError('archive must not execute')\n")
    helper=tmp_path/'household_retained_native_score.py';helper.write_text("raise AssertionError('unverified helper executed')\n");helper.chmod(0o600)
    monkeypatch.setattr(score,'__file__',str(tmp_path/'household_forecast_score.py'))
    with pytest.raises(ValueError,match='retained coordinator source differs'):
        score.run_retained_worker(script,stage/'forecast.json',stage=stage,deployment_sha256=pin,retained_native=True)
