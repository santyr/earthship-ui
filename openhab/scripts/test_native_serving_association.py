"""Serving receipt audit evidence is separate from original numerical capture bytes."""
from pathlib import Path
import json
import pytest
from test_native_serving_live import fixture,originals


def test_publication_retains_externally_pinned_model_association_outside_capture(tmp_path,originals,monkeypatch):
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    result=live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    origin=Path(result['origin_path']);capture=json.loads(origin.read_bytes())
    association=origin.with_name(capture['capture_sha256']+'.native-serving-model-binding-v1.json')
    assert association.is_file(), 'serving receipt association was not retained'
    value=json.loads(association.read_bytes())
    assert value['schema']=='earthship-native-serving-model-binding/v1'
    assert value['capture_sha256']==capture['capture_sha256']
    assert value['artifact_sha256']==settings['artifact_sha256']
    assert value['model_receipt_path']==settings['model_receipt_path']
    assert value['model_receipt_sha256']==settings['model_receipt_sha256']
    assert value['stage']==str(stage)
    assert value['deployment_sha256']==json.loads(model._selection._encoded)['deployment_sha256']
    assert 'model_receipt_path' not in capture and 'model_receipt_sha256' not in capture
    assert association.stat().st_mode&0o777==0o600
