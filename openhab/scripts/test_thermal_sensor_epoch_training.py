"""Source-bound v2 input/model persistence; numerical fitting is replaced locally."""
from copy import deepcopy
from dataclasses import asdict,replace
from datetime import datetime,timedelta
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest
from test_thermal_training_inputs import inputs
from test_thermal_pipeline import training_samples,RecordingRegistry,orchestration_dependencies,FakeJournal,NOW
from test_thermal_artifacts import valid_artifact
from test_thermal_sensor_epoch_history import EPOCHS
from thermal_model.forcing_capture import _canonical
from thermal_model.schema import THERMAL_ITEMS,OPTIONAL_OBSERVATION_ITEMS
from thermal_model.temperature_history import QualifiedTemperatureHistoryV2,STREAMS,POLICY
from weather_temperature_evidence import TemperaturePolicy,MODELS
from weather_temperature_receiver import TemperatureCollector
from weather_temperature_reader import select_temperature_grid_v2
import thermal_model.training_inputs as original_inputs
import thermal_model.training_sources as original_sources
import thermal_model.artifacts as models


def inputs_v2():
    data=inputs();samples=training_samples();known={row.at:row for row in samples}
    policies={stream:TemperaturePolicy(model,sensor,**POLICY) for stream,model,sensor in STREAMS.values()}
    phases={STREAMS[role][0]:epoch for role,epoch in EPOCHS.items()}
    clock={'at':data['start'],'tick':1000,'pid':1}
    source=TemperatureCollector(policies,sensor_epochs=phases,clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:clock['pid'])
    envelopes=[]
    for index,row in enumerate(samples):
        clock.update(at=row.at,tick=1000+300*index,pid=1 if index<2 else 2)
        for role,(stream,model,sensor) in STREAMS.items():
            field={'air':'air_f','mass':'mass_f','outdoor':'outdoor_f'}[role]
            source.observe({'model':model,'id':str(sensor),MODELS[model][1]:str(getattr(row,field))})
        envelopes.append((row.at,json.dumps(source.snapshot())))
    def grid(stream,targets,assessed):
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        selected=[pair for pair in envelopes if pair[0]<=targets[-1]]
        return select_temperature_grid_v2(selected,targets=targets,assessed_at=assessed,history_start=targets[0]-timedelta(seconds=120),stream=stream,policy=policies[stream],sensor_epoch=EPOCHS[role])
    def legacy(item,start,end):
        assert item not in {THERMAL_ITEMS[role] for role in STREAMS}
        if item==THERMAL_ITEMS['radiation']:return [(row.at,row.radiation_wm2) for row in samples]
        return []
    data['series_reader']=QualifiedTemperatureHistoryV2(legacy,grid,cutover=data['start'],assessed_at=data['end'],sensor_epochs=EPOCHS,retain_raw=True)
    return data


def capture():return original_inputs.capture_training_inputs_v2(**inputs_v2())


def test_v2_input_roundtrip_retains_sensor_and_session_without_legacy_reader_relabel(tmp_path):
    tmp_path.chmod(0o700);record=capture()
    assert record['schema']=='earthship-thermal-training-inputs/v2'
    frozen=original_inputs.restore_training_inputs_v2(record)
    assert len(frozen.samples)==4
    for role,rows in frozen.series_reader.temperature_grids().items():
        assert {value['sensorEpoch'] for at,value in rows}=={EPOCHS[role]}
        assert len({value['streamEpoch'] for at,value in rows})==2
    path=original_inputs.write_training_inputs_v2(tmp_path,record)
    assert path.name.endswith('.training-inputs-v2.json') and path.stat().st_mode&0o777==0o600
    assert original_inputs.read_training_inputs_v2(path)==record
    with pytest.raises(ValueError):original_inputs.read_training_inputs(path)
    with pytest.raises(ValueError):original_inputs.capture_training_inputs(**inputs_v2())


@pytest.mark.parametrize('damage',['phase','version','raw','extra'])
def test_rehashed_v2_inputs_cannot_change_source_metadata(damage):
    record=capture()
    if damage=='phase':record['temperature_grids']['air'][0][1]['sensorEpoch']=EPOCHS['mass']
    elif damage=='version':record['temperature_evidence']['version']=1
    elif damage=='raw':record['series_by_role']['air'][0][1]=99
    else:record['qualified']=True
    record['snapshot_sha256']=original_inputs._digest({key:value for key,value in record.items() if key!='snapshot_sha256'})
    with pytest.raises(ValueError):original_inputs.restore_training_inputs_v2(record)


def test_v2_training_source_files_require_matching_model_schema_and_native_phases(tmp_path):
    tmp_path.chmod(0o700);record=capture();frozen=original_inputs.restore_training_inputs_v2(record)
    descriptor=SimpleNamespace(schema='earthship-thermal-model/v6',data_manifest={**record['dataset_manifest'],'temperature_evidence':record['temperature_evidence']})
    raw=original_sources.build_training_sources(frozen.samples,frozen.series_reader)
    assert raw['schema']=='earthship-thermal-training-sources/v2'
    path=original_sources.write_training_sources_v2(tmp_path,raw,descriptor)
    assert path.name.endswith('.training-sources-v2.json')
    assert original_sources.read_training_sources_v2(path,descriptor)==raw
    with pytest.raises(ValueError):original_sources.read_training_sources(path,descriptor)
    descriptor.schema=models.MODEL_SCHEMA
    with pytest.raises(ValueError):original_sources.validate_sensor_training_sources(raw,descriptor)


def sensor_artifact():
    original=valid_artifact();manifest=deepcopy(original.data_manifest)
    start=models._iso_utc(original.trained_from,'start');end=models._iso_utc(original.trained_through,'end')
    left=start;right=end;count=int((right-left).total_seconds()/300)
    roles={role:dict(stream=stream,model=model,sensor_id=sensor,policy=dict(POLICY),legacy_points=0,targets=count,qualified=0,missing=count,grid_sha256='a'*64,sensor_epoch=EPOCHS[role]) for role,(stream,model,sensor) in STREAMS.items()}
    manifest['temperature_evidence']=dict(version=2,cutover=start.isoformat(),semantics='native_receipt_with_declared_sensor_epoch',roles=roles)
    return replace(original,schema='earthship-thermal-model/v6',data_manifest=manifest)


def test_v6_model_type_accepts_only_explicit_native_v2_manifest():
    artifact=sensor_artifact();assert models.validate_artifact(artifact)==artifact
    assert models._artifact_from_payload(json.loads(_canonical(asdict(artifact))))==artifact
    with pytest.raises(models.ArtifactValidationError):models.validate_artifact(replace(artifact,schema=models.MODEL_SCHEMA))
    with pytest.raises(models.ArtifactValidationError):models.validate_artifact(replace(valid_artifact(),schema='earthship-thermal-model/v6'))


def test_pipeline_selects_v6_for_native_v2_without_running_numerics():
    import thermal_model.pipeline as pipeline
    calls=[];registry=RecordingRegistry();dependencies=orchestration_dependencies(calls)
    original=dependencies['series_reader']
    original.evidence_manifest=lambda:sensor_artifact().data_manifest['temperature_evidence']
    pipeline.run_training(start=NOW-timedelta(days=30),end=NOW,registry=registry,journal=FakeJournal(calls),**dependencies)
    assert registry.artifact.schema=='earthship-thermal-model/v6'


def test_offline_v2_pipeline_persists_native_sources_and_v3_phase_binding_before_candidate(tmp_path,monkeypatch):
    from functools import partial
    import thermal_model.offline_training as offline
    import thermal_model.pipeline as pipeline
    import thermal_model.fit_evidence as fit_evidence
    from test_thermal_pipeline import multihorizon_fit_result,warm_behavior,backtest_report
    record=capture();registry=RecordingRegistry();writes=[]
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1')
    monkeypatch.setattr(fit_evidence,'build_fit_evidence',lambda artifact,fitted:dict(release_authorized=False))
    def proof(root,value,artifact):
        assert registry.calls==['report'] and artifact.schema=='earthship-thermal-model/v6'
        assert list(root.glob('*.training-sources-v2.json')) and list(root.glob('*.training-input-binding-v3.json'))
        writes.append('proof')
    monkeypatch.setattr(offline,'write_fit_evidence',proof)
    monkeypatch.setattr(offline,'run_training',partial(pipeline.run_training,dynamics_fitter=lambda rows,**kwargs:multihorizon_fit_result(),behavior_fitter=lambda rows:warm_behavior(),evaluator=lambda rows,fitter:backtest_report(eligible=True),artifact_validator=lambda artifact:artifact))
    result=offline.run_snapshot_training(record,registry=registry,fit_evidence_directory=tmp_path,clock=lambda:datetime.fromisoformat(record['end']),revision_reader=lambda:'b'*64)
    assert result.artifact.schema=='earthship-thermal-model/v6' and writes==['proof']
    binding=json.loads(next(tmp_path.glob('*.training-input-binding-v3.json')).read_text())
    assert binding['sensor_epochs']==EPOCHS and binding['release_authorized'] is False


def test_cli_v2_verification_is_explicit_and_does_not_fit(tmp_path,monkeypatch,capsys):
    from test_train_thermal_snapshot import cli
    tmp_path.chmod(0o700);path=original_inputs.write_training_inputs_v2(tmp_path,capture());command=cli()
    monkeypatch.setattr(command,'run_snapshot_training',lambda *args,**kwargs:pytest.fail('input verification reached fitting'))
    assert command.main(['--snapshot',str(path),'--verify-only','--receipt-version','2'])==0
    assert json.loads(capsys.readouterr().out)['release_authorized'] is False
    assert command.main(['--snapshot',str(path),'--verify-only'])==2


def test_cli_v2_fit_routes_only_explicit_private_inputs_without_release_authority(tmp_path,monkeypatch,capsys):
    from test_train_thermal_snapshot import cli
    tmp_path.chmod(0o700);path=original_inputs.write_training_inputs_v2(tmp_path,capture());command=cli()
    state=tmp_path/'state';proof=tmp_path/'proof';state.mkdir(mode=0o700);proof.mkdir(mode=0o700)
    monkeypatch.setenv('EARTHSHIP_QUALIFICATION_FIT','1');calls=[]
    def fit(record,**kwargs):
        assert record['schema']=='earthship-thermal-training-inputs/v2'
        assert kwargs['fit_evidence_directory']==proof and kwargs['registry'].directory==state
        calls.append('fit');return SimpleNamespace(artifact=sensor_artifact())
    monkeypatch.setattr(command,'run_snapshot_training',fit)
    assert command.main(['--snapshot',str(path),'--receipt-version','2','--fit','--state-dir',str(state),'--fit-evidence-dir',str(proof)])==0
    output=json.loads(capsys.readouterr().out)
    assert calls==['fit'] and output['release_authorized'] is False and output['automatic_actuation'] is False
