"""Separate capture audit association can select only a retained owned stage."""
from pathlib import Path
from hashlib import sha256
import json
import pytest
from test_native_serving_forecast import context,originals
from test_native_thermal_forecast import ISSUE


def fixture(tmp_path,originals,monkeypatch):
    import native_thermal_live as live
    reader=getattr(live,'serving_delivery_model',None)
    assert callable(reader),'historical serving selector is missing'
    forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    selected=json.loads(model._selection._encoded)
    delivery={'capture_sha256':'a'*64,'artifact_sha256':candidate['artifact_sha256'],'runtime_sha256':candidate['runtime_sha256'],'issued_at':ISSUE.isoformat()}
    path=tmp_path/'unused.native-provisional-delivery-v2.json'
    association=dict(schema='earthship-native-serving-model-binding/v1',**delivery,stage=selected['stage'],deployment_sha256=selected['deployment_sha256'],
        model_receipt_path=selected['receipt']['path'],model_receipt_sha256=selected['receipt']['sha256'],automatic_actuation=False)
    association['binding_sha256']=forecasts.digest(association,'binding_sha256')
    target=tmp_path/(delivery['capture_sha256']+'.native-serving-model-binding-v1.json')
    def persist():
        association['binding_sha256']=forecasts.digest(association,'binding_sha256');target.write_bytes(__import__('thermal_model.forcing_capture',fromlist=['_canonical'])._canonical(association));target.chmod(0o600)
    persist()
    return reader,path,delivery,model,association,target,persist


def test_historical_capture_requires_its_exact_owned_association(tmp_path,originals,monkeypatch):
    reader,path,delivery,model,association,target,persist=fixture(tmp_path,originals,monkeypatch)
    assert reader(path,delivery,current_model=model,historical_selections=(),assessed_at=ISSUE,guard=lambda:None) is model
    association['deployment_sha256']='f'*64;persist()
    assert reader(path,delivery,current_model=model,historical_selections=(),assessed_at=ISSUE,guard=lambda:None) is None
    # Historical absence cannot borrow even an otherwise identical active candidate.
    target.unlink()
    assert reader(path,delivery,current_model=model,historical_selections=(),assessed_at=ISSUE,guard=lambda:None) is None


def test_resealed_audit_cannot_qualify_another_candidate_or_receipt(tmp_path,originals,monkeypatch):
    reader,path,delivery,model,association,target,persist=fixture(tmp_path,originals,monkeypatch)
    association['model_receipt_sha256']='e'*64;persist()
    with pytest.raises(ValueError):reader(path,delivery,current_model=model,historical_selections=(),assessed_at=ISSUE,guard=lambda:None)
    association['artifact_sha256']='f'*64;persist()
    with pytest.raises(ValueError):reader(path,delivery,current_model=model,historical_selections=(),assessed_at=ISSUE,guard=lambda:None)
