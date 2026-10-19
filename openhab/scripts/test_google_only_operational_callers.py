"""Retired weather profiles cannot reach a production factory or private model."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import pytest

LEGACY='earthship-provisional-thermal-live-config/v1'


def refuse_legacy(*args,**kwargs):raise AssertionError('retired producer/reader was selected')


def private_config(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'forecast.json'
    path.write_text(json.dumps(dict(schema=LEGACY,candidate_path=str(tmp_path/'private-candidate'))));path.chmod(0o600)
    return path


def test_household_driver_refuses_old_profile_before_original_loader(tmp_path,monkeypatch):
    import household_cycle as driver
    import thermal_model.serial_publication_caps as installed
    import household_cycle_resources as resources
    import native_thermal_live as native
    config=private_config(tmp_path)
    monkeypatch.setattr(installed,'_resource_preflight',lambda:None)
    monkeypatch.setattr(resources,'publication_resource_preflight',lambda:None)
    monkeypatch.setattr(native,'load_settings',refuse_legacy)
    with pytest.raises(ValueError):driver.run_cycle(tmp_path/'unused-cycle',code_revision='a'*40,forecast_config=config)


def test_lazy_backend_refuses_old_profile_before_translating_credentials(tmp_path,monkeypatch):
    import household_cycle as driver
    import native_thermal_live as native
    monkeypatch.setattr(native,'make_forecast_backend',refuse_legacy)
    backend=driver.LazyForecastBackend({'schema':LEGACY},guard=lambda:None)
    with pytest.raises(ValueError):backend.collect(issue=datetime.now(timezone.utc),known_at=datetime.now(timezone.utc))


def test_score_runner_refuses_old_profile_before_original_loader(tmp_path,monkeypatch):
    import household_forecast_score as driver
    import native_thermal_live as native
    config=private_config(tmp_path)
    monkeypatch.setattr(driver,'production_resource_preflight',lambda:None)
    monkeypatch.setattr(native,'load_settings',refuse_legacy)
    with pytest.raises(ValueError):driver.run(config)


def test_score_dispatch_refuses_old_profile_before_legacy_model_or_report(monkeypatch):
    import household_forecast_score as driver
    import native_thermal_live as native
    monkeypatch.setattr(native,'current_runtime',refuse_legacy)
    with pytest.raises(ValueError):driver.score_with_report({'schema':LEGACY},guard=lambda:None)


def test_stage_refuses_old_profile_before_private_candidate_read(tmp_path,monkeypatch):
    from test_household_cycle_deploy import fixture
    import household_cycle_deploy as deploy
    args,_=fixture(tmp_path);path=args['forecast_config'];settings=json.loads(path.read_bytes())
    settings['schema']=LEGACY;path.write_text(json.dumps(settings))
    original=deploy._bytes
    def read(path,**kwargs):
        if Path(path)==Path(settings['candidate_path']):refuse_legacy()
        return original(path,**kwargs)
    monkeypatch.setattr(deploy,'_bytes',read)
    with pytest.raises(ValueError):deploy.stage_deployment(**args)
    assert not args['stage'].exists()


def test_verify_refuses_retired_non_native_stage(tmp_path):
    import household_cycle_deploy as deploy
    tmp_path.chmod(0o700);stage=tmp_path/'stage';stage.mkdir(mode=0o700)
    (stage/'sources').mkdir(mode=0o700)
    for name,raw in (('cycle.json',b'{}'),('service.conf',b'')):
        (stage/name).write_bytes(raw);(stage/name).chmod(0o600)
    record=dict(schema='earthship-household-cycle-deployment/v1',code_revision='a'*40,stage=str(stage),
        service_file=str(tmp_path/'unused.service'),original_bindings={},source_manifest={},protected_runtime_sources={},
        cycle_sha256=sha256(b'{}').hexdigest(),dropin_sha256=sha256(b'').hexdigest(),automatic_actuation=False)
    (stage/'deployment.json').write_text(json.dumps(record));(stage/'deployment.json').chmod(0o600)
    with pytest.raises(ValueError):deploy.verify_stage(stage)


def test_google_dispatch_writer_needs_no_legacy_stage(tmp_path):
    from household_native_family import prepare_score_dispatch
    tmp_path.chmod(0o700);output=tmp_path/'dispatch.json'
    result=prepare_score_dispatch(historical_selections=(),output=output,guard=lambda:None)
    assert json.loads(output.read_bytes())==dict(schema='earthship-native-score-dispatch/v2',current='current',historical=[])
    assert result['live_units_changed'] is False


def test_google_dispatch_reader_never_opens_legacy_context(tmp_path,monkeypatch):
    import household_forecast_score as score,household_cycle_deploy as deploy
    tmp_path.chmod(0o700);path=tmp_path/'dispatch.json'
    body=dict(schema='earthship-native-score-dispatch/v2',current='current',historical=[])
    path.write_text(json.dumps(body));path.chmod(0o600)
    record=dict(schema='earthship-household-cycle-deployment/v3',score_dispatch=dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest()))
    monkeypatch.setattr(deploy,'verify_stage',lambda actual,**kw:record if Path(actual)==tmp_path else refuse_legacy())
    assert score.read_score_dispatch(tmp_path,deployment_sha256='a'*64,guard=lambda:None)==body


def test_old_score_executor_is_absent():
    import household_forecast_score as score
    assert not hasattr(score,'execute_legacy_score')


def test_non_native_retained_worker_refuses_before_archive_access(tmp_path,monkeypatch):
    import household_forecast_score as score,household_cycle_deploy as deploy
    monkeypatch.setattr(deploy,'_path',refuse_legacy)
    with pytest.raises(ValueError):score.run_retained_worker(tmp_path/'old.py',tmp_path/'old.json',stage=tmp_path,
        deployment_sha256='a'*64,retained_native=False)


def test_aliased_archive_schema_cannot_reenable_old_score_loader(tmp_path,monkeypatch):
    import household_forecast_score as driver,native_thermal_live as native
    config=private_config(tmp_path)
    monkeypatch.setattr(driver,'production_resource_preflight',lambda:None)
    monkeypatch.setattr(native,'NATIVE_SCHEMAS',(LEGACY,))
    monkeypatch.setattr(native,'load_settings',refuse_legacy)
    with pytest.raises(ValueError):driver.run(config)


def test_retained_native_flag_cannot_relabel_an_old_stage(tmp_path,monkeypatch):
    from test_household_score_diagnostics import archive
    import household_forecast_score as driver,household_cycle_deploy as deploy
    stage,script,pin=archive(tmp_path,monkeypatch,"raise AssertionError('must not execute')\n")
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**k:dict(schema='earthship-household-cycle-deployment/v1',
        source_manifest={'openhab/scripts/household_forecast_score.py':sha256(script.read_bytes()).hexdigest()}))
    monkeypatch.setattr(driver,'production_retained_runner',refuse_legacy)
    with pytest.raises(ValueError):driver.run_retained_worker(script,tmp_path/'config',stage=stage,
        deployment_sha256=pin,retained_native=True)


def test_direct_score_dispatch_cannot_reenable_aliased_old_profile(monkeypatch):
    import household_forecast_score as driver,native_thermal_live as native
    monkeypatch.setattr(native,'LIVE_SCHEMAS',(LEGACY,))
    monkeypatch.setattr(native,'score_jobs',refuse_legacy)
    with pytest.raises(ValueError):driver.score_with_report({'schema':LEGACY},guard=lambda:None)
