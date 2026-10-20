from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import json
import pytest
from household_native_training import NativeTraining,save,directory
from weather_learning.contracts import identity


def fixture(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    now=datetime(2026,10,20,2,tzinfo=timezone.utc);root=directory(tmp_path/'evidence');policy=Path(__file__).parent/'thermal_model/native_operational_io.py';policy_sha=sha256(policy.read_bytes()).hexdigest();records={};refs=[]
    for i in range(3):
        stage=directory(tmp_path/str(i));config=tmp_path/(str(i)+'.config.json');save(config,dict(evidence_directory=str(root)));save(stage/'cycle.json',dict(forecast_config=str(config)))
        record=dict(source_manifest={'openhab/scripts/thermal_model/native_operational_io.py':policy_sha if i<2 else 'c'*64});save(stage/'deployment.json',record);pin=sha256((stage/'deployment.json').read_bytes()).hexdigest();records[str(stage)]=record;refs.append(dict(stage=str(stage),deployment_sha256=pin))
    monkeypatch.setattr(deploy,'verify_stage',lambda stage,expected_deployment_sha256:records[str(stage)])
    folder=directory(root/'origins-20261020');binding=dict(schema='earthship-native-serving-model-binding/v1',capture_sha256='a'*64,artifact_sha256='b'*64,runtime_sha256='c'*64,
        issued_at=now.isoformat(),stage=refs[1]['stage'],deployment_sha256=refs[1]['deployment_sha256'],model_receipt_path='/private/receipt.json',model_receipt_sha256='d'*64,automatic_actuation=False)
    binding['binding_sha256']=identity(binding);path=folder/('a'*64+'.native-serving-model-binding-v1.json');save(path,binding)
    backend=object.__new__(NativeTraining);backend.guard=lambda:None;return backend,refs,path,now


def test_active_history_follows_original_archive_window_without_deleting_scores(tmp_path,monkeypatch):
    backend,refs,path,now=fixture(tmp_path,monkeypatch);original=path.read_bytes();archive=tmp_path/'older.score.json';save(archive,{'original':True});raw=archive.read_bytes()
    retained=backend.active_score_history(tuple(refs),now=now)
    assert retained==(refs[1],refs[2]) # Unknown frozen archive policy stays retained.
    assert path.read_bytes()==original and archive.read_bytes()==raw


def test_changed_capture_binding_refuses_history_filtering(tmp_path,monkeypatch):
    backend,refs,path,now=fixture(tmp_path,monkeypatch);value=json.loads(path.read_bytes());value['stage']=refs[0]['stage'];save(path,value)
    with pytest.raises(ValueError,match='binding'):backend.active_score_history(tuple(refs),now=now)
