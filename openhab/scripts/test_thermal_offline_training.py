"""Offline orchestration uses frozen authorities; local tests never optimize."""
from dataclasses import replace,asdict
from types import SimpleNamespace
from hashlib import sha256
import json
import pytest
from test_thermal_training_inputs import inputs,module as input_module
from test_thermal_origin_capture import capture_inputs
from thermal_model.forcing_capture import _canonical


def module():
    from thermal_model import offline_training
    return offline_training


def setup_case(tmp_path,monkeypatch):
    data=inputs();snapshot=input_module().capture_training_inputs(**data)
    artifact=capture_inputs()['artifact']
    artifact=replace(artifact,code_revision='b'*64,trained_from=snapshot['start'],trained_through=snapshot['end'],
        data_manifest={**artifact.data_manifest,**snapshot['dataset_manifest'],'temperature_evidence':snapshot['temperature_evidence']})
    monkeypatch.setenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT','1')
    monkeypatch.setattr(module(),'write_fit_evidence',lambda root,proof,model:root/'controlled-fit-proof')
    return data,snapshot,artifact


def test_default_workload_guard_refuses_before_reconstruction_or_fitting(monkeypatch,tmp_path):
    source=module();monkeypatch.delenv('EARTHSHIP_REMOTE_QUALIFICATION_FIT',raising=False)
    def prohibited(*args,**kwargs):pytest.fail('fitting or reconstruction reached without opt-in')
    monkeypatch.setattr(source,'restore_training_inputs',prohibited);monkeypatch.setattr(source,'run_training',prohibited)
    with pytest.raises(ValueError):source.run_snapshot_training({},registry=None,fit_evidence_directory=tmp_path,clock=lambda:None,revision_reader=lambda:'a'*64)


def test_frozen_readers_and_both_proof_writers_reach_existing_pipeline(tmp_path,monkeypatch):
    source=module();data,record,artifact=setup_case(tmp_path,monkeypatch);registry=object();calls=[]
    def train(**kwargs):
        assert kwargs['registry'] is registry
        assert kwargs['start']==data['start'] and kwargs['end']==data['end']
        assert kwargs['revision_reader']()=='b'*64
        assert kwargs.get('site_settings_loader') is None and kwargs.get('forecast_reader') is None
        assert kwargs['journal'].effective_events(data['start'],data['end'])==tuple(data['journal'].effective_events(data['start'],data['end']))
        assert kwargs['series_reader'].temperature_grids()==record['temperature_grids']
        kwargs['training_sources_writer'](artifact,dict(schema='earthship-thermal-training-sources/v1',samples=[],temperature_grids={}))
        kwargs['fit_evidence_writer'](artifact,dict(release_authorized=False));calls.append('pipeline')
        return SimpleNamespace(artifact=artifact,promoted=True)
    def save_sources(root,raw,model):calls.append('sources');return root/'controlled-source-proof'
    monkeypatch.setattr(source,'write_training_sources',save_sources);monkeypatch.setattr(source,'run_training',train)
    result=source.run_snapshot_training(record,registry=registry,fit_evidence_directory=tmp_path,clock=lambda:data['end'],revision_reader=lambda:'b'*64)
    assert result.artifact==artifact and calls==['sources','pipeline']
    bindings=list(tmp_path.glob('*.training-input-binding-v1.json'));assert len(bindings)==1
    value=json.loads(bindings[0].read_text())
    assert value['snapshot_sha256']==record['snapshot_sha256']
    assert value['artifact_sha256']==sha256(_canonical(asdict(artifact))).hexdigest()
    assert value['release_authorized'] is False and bindings[0].stat().st_mode&0o777==0o600


def test_changed_fitted_dataset_refuses_before_any_proof_is_saved(tmp_path,monkeypatch):
    source=module();data,record,artifact=setup_case(tmp_path,monkeypatch)
    artifact=replace(artifact,data_manifest={**artifact.data_manifest,'canonical_rows_sha256':'c'*64})
    def train(**kwargs):kwargs['training_sources_writer'](artifact,{})
    def prohibited(*args,**kwargs):pytest.fail('incompatible source proof was saved')
    monkeypatch.setattr(source,'run_training',train);monkeypatch.setattr(source,'write_training_sources',prohibited)
    with pytest.raises(ValueError):source.run_snapshot_training(record,registry=None,fit_evidence_directory=tmp_path,clock=lambda:data['end'],revision_reader=lambda:'b'*64)
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('damage',['future_snapshot','proof_directory'])
def test_invalid_context_refuses_before_pipeline(tmp_path,monkeypatch,damage):
    source=module();data,record,artifact=setup_case(tmp_path,monkeypatch)
    def prohibited(*args,**kwargs):pytest.fail('invalid context reached training')
    monkeypatch.setattr(source,'run_training',prohibited)
    if damage=='proof_directory':tmp_path.chmod(0o755)
    now=data['start'] if damage=='future_snapshot' else data['end']
    with pytest.raises(ValueError):source.run_snapshot_training(record,registry=None,fit_evidence_directory=tmp_path,clock=lambda:now,revision_reader=lambda:'b'*64)


@pytest.mark.parametrize('failure',['sources','binding','proof'])
def test_real_pipeline_storage_failures_preserve_previous_candidate(tmp_path,monkeypatch,failure):
    """Actual orchestration with controlled numerical/evaluation boundaries only."""
    from functools import partial
    import thermal_model.pipeline as pipeline
    import thermal_model.fit_evidence as fit_evidence
    from test_thermal_pipeline import RecordingRegistry,multihorizon_fit_result,warm_behavior,backtest_report
    source=module();data,record,_=setup_case(tmp_path,monkeypatch);registry=RecordingRegistry()
    def fit(rows,*,collect_graduation_evidence=False):
        assert collect_graduation_evidence is True
        return multihorizon_fit_result()
    monkeypatch.setattr(fit_evidence,'build_fit_evidence',lambda *args:dict(release_authorized=False))
    monkeypatch.setattr(source,'run_training',partial(pipeline.run_training,
        dynamics_fitter=fit,behavior_fitter=lambda rows:warm_behavior(),
        evaluator=lambda rows,fitter:backtest_report(eligible=True),artifact_validator=lambda artifact:artifact))
    def interrupted(*args,**kwargs):raise OSError('controlled persistence failure')
    monkeypatch.setattr(source,{'sources':'write_training_sources','binding':'_persist_binding','proof':'write_fit_evidence'}[failure],interrupted)
    with pytest.raises(pipeline.TrainingRefused):
        source.run_snapshot_training(record,registry=registry,fit_evidence_directory=tmp_path,clock=lambda:data['end'],revision_reader=lambda:'b'*64)
    assert registry.calls==['report'] and registry.artifact is None


@pytest.mark.parametrize('damage',['revision','interval'])
def test_changed_fit_context_refuses_before_proof_writes(tmp_path,monkeypatch,damage):
    from datetime import timedelta
    source=module();data,record,artifact=setup_case(tmp_path,monkeypatch);revision=['b'*64]
    if damage=='interval':artifact=replace(artifact,trained_through=(data['end']+timedelta(minutes=5)).isoformat())
    def train(**kwargs):
        if damage=='revision':revision[0]='c'*64
        kwargs['training_sources_writer'](artifact,{})
    monkeypatch.setattr(source,'run_training',train)
    with pytest.raises(ValueError):source.run_snapshot_training(record,registry=None,fit_evidence_directory=tmp_path,clock=lambda:data['end'],revision_reader=lambda:revision[0])
    assert list(tmp_path.iterdir())==[]


def test_interrupted_binding_write_cleans_private_partial_file(tmp_path,monkeypatch):
    source=module()
    def interrupted(path,raw):path.write_bytes(b'partial');raise OSError('controlled interruption')
    monkeypatch.setattr(source,'_write_private',interrupted)
    with pytest.raises(OSError):source._persist_binding(tmp_path,dict(schema=source.SCHEMA,release_authorized=False))
    assert list(tmp_path.iterdir())==[]
