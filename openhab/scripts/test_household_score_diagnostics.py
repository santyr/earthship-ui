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
    assert result==dict(status='score_withheld',reason=reason,fit_executed=False,automatic_actuation=False)


def archive(tmp_path,monkeypatch,body):
    import household_cycle_deploy as deploy
    tmp_path.chmod(0o700);stage=tmp_path/'old';stage.mkdir(mode=0o700)
    script=stage/'sources/openhab/scripts/household_forecast_score.py';script.parent.mkdir(parents=True)
    script.write_text(body);manifest=stage/'deployment.json';manifest.write_text('{}');manifest.chmod(0o600)
    source_hash=sha256(script.read_bytes()).hexdigest()
    monkeypatch.setattr(deploy,'__file__',str(script.parent/'household_cycle_deploy.py'))
    monkeypatch.setattr(deploy,'verify_stage',lambda actual,**kwargs:dict(source_manifest={'openhab/scripts/household_forecast_score.py':source_hash}))
    return stage,script,sha256(manifest.read_bytes()).hexdigest()


@pytest.mark.parametrize('native',[False,True])
def test_retained_worker_runs_original_function_with_its_original_stage(tmp_path,monkeypatch,native):
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(config, **kwargs):\n return dict(status='waiting',config=str(config),stage=str(kwargs['stage']),native=kwargs.get('retained_native',False),pin=kwargs.get('deployment_sha256'))\n")
    result=score.run_retained_worker(script,tmp_path/'config.json',stage=stage,deployment_sha256=pin,retained_native=native)
    assert result==dict(status='waiting',config=str(tmp_path/'config.json'),stage=str(stage),native=native,pin=pin if native else None)


def test_retained_worker_refuses_source_drift_before_executing(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    script.write_text(script.read_text()+'# changed\n')
    with pytest.raises(ValueError):score.run_retained_worker(script,tmp_path/'config',stage=stage,deployment_sha256=pin,retained_native=False)


def test_retained_worker_refuses_external_manifest_drift(tmp_path,monkeypatch):
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    (stage/'deployment.json').write_text('{ }')
    with pytest.raises(ValueError):score.run_retained_worker(script,tmp_path/'config',stage=stage,deployment_sha256=pin,retained_native=False)


def test_archived_exception_reaches_current_secret_free_cli(tmp_path,monkeypatch,capsys):
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(*args, **kwargs):\n raise OSError('private connection details')\n")
    result=score.main(['--config',str(tmp_path/'config'),'--stage',str(stage),'--worker-script',str(script),'--worker-deployment-sha256',pin])
    assert result==1
    assert json.loads(capsys.readouterr().out)==dict(status='score_withheld',reason='io_unavailable',fit_executed=False,automatic_actuation=False)


def test_retained_worker_rejects_mixed_dependency_context(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    original_file=deploy.__file__
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    monkeypatch.setattr(deploy,'__file__',original_file)
    with pytest.raises(ValueError,match='dependency context'):
        score.run_retained_worker(script,tmp_path/'config',stage=stage,deployment_sha256=pin,retained_native=False)


def test_python_safe_path_keeps_archived_dependencies_in_the_child(tmp_path):
    import os,subprocess,sys
    current=tmp_path/'current';old=tmp_path/'old';current.mkdir();old.mkdir()
    (current/'selected_dependency.py').write_text("VALUE='current'\n")
    (old/'selected_dependency.py').write_text("VALUE='retained'\n")
    runner=current/'worker.py';runner.write_text('import selected_dependency; print(selected_dependency.VALUE)\n')
    output=subprocess.check_output([sys.executable,'-P',str(runner)],env=dict(os.environ,PYTHONPATH=str(old)),text=True,timeout=5)
    assert output.strip()=='retained'


def test_legacy_dispatch_reenters_reporting_wrapper_with_archived_dependencies(tmp_path,monkeypatch):
    import os
    import household_cycle_deploy as deploy
    stage,script,pin=archive(tmp_path,monkeypatch,"def run(*args, **kwargs): return dict(status='waiting')\n")
    config=stage/'forecast.json';config.write_text('{}');config.chmod(0o600)
    record=dict(schema='earthship-household-cycle-deployment/v1',source_manifest={
        'openhab/scripts/household_forecast_score.py':sha256(script.read_bytes()).hexdigest()})
    monkeypatch.setattr(deploy,'verify_stage',lambda actual,**kwargs:record)
    seen=[]
    monkeypatch.setattr(os,'execve',lambda *args:seen.append(args))
    selection=dict(stage=str(stage),deployment_sha256=pin,config=str(config),config_sha256=sha256(config.read_bytes()).hexdigest())
    score.execute_legacy_score(selection)
    executable,args,environment=seen.pop()
    assert args==[executable,'-P',str(Path(score.__file__).resolve()),'--worker-script',str(script),
        '--worker-deployment-sha256',pin,'--config',str(config),'--stage',str(stage)]
    assert environment['PYTHONPATH']==str(script.parent)+':/home/sat/Solar_PV/analytics/src'
    config.write_text('{ }')
    with pytest.raises(ValueError):score.execute_legacy_score(selection)
    assert seen==[]
