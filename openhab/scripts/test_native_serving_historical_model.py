"""An older candidate remains scoreable only through its own retained receipt."""
from datetime import timedelta
from pathlib import Path
import json
import pytest
from test_native_serving_forecast import context,originals
from test_native_thermal_forecast import ISSUE
from test_installed_shade_origin import outcome
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
from thermal_model.forcing_capture import _canonical


def test_real_historical_candidate_uses_its_retained_model_not_active_receipt(tmp_path,originals,monkeypatch):
    old=tmp_path/'old';old.mkdir(mode=0o700);new=tmp_path/'new';new.mkdir(mode=0o700)
    forecasts,artifacts,candidate,old_model,inputs,kwargs,paths=context(old,originals,monkeypatch)
    _,_,active,active_model,_,_,_=context(new,originals,monkeypatch)
    assert candidate['artifact_sha256']!=active['artifact_sha256'] and old_model.runtime==active_model.runtime
    capture=forecasts.build_serving_capture(old_model,inputs,**kwargs)
    selected=json.loads(old_model._selection._encoded)
    delivery=dict(capture_sha256=capture['capture_sha256'],artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],issued_at=ISSUE.isoformat())
    association=dict(schema='earthship-native-serving-model-binding/v1',**delivery,stage=selected['stage'],deployment_sha256=selected['deployment_sha256'],model_receipt_path=selected['receipt']['path'],model_receipt_sha256=selected['receipt']['sha256'],automatic_actuation=False)
    association['binding_sha256']=forecasts.digest(association,'binding_sha256')
    path=tmp_path/(capture['capture_sha256']+'.native-serving-model-binding-v1.json');path.write_bytes(_canonical(association));path.chmod(0o600)
    from native_thermal_live import serving_delivery_model
    def resolve(history):return serving_delivery_model(tmp_path/'delivery.json',delivery,current_model=active_model,historical_selections=history,assessed_at=ISSUE,guard=lambda:None)
    assert resolve(()) is None
    actual=resolve((old_model._selection,))
    assert actual.candidate==old_model.candidate and actual.candidate!=active_model.candidate
    receipts={name:dict(item=name,time=int((ISSUE+timedelta(seconds=3+i)).timestamp()*1000),state=json.dumps(value)) for i,(name,value) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,forecasts.publication(capture))))}
    import native_thermal_score as scores
    options=dict(expected_capture_sha256=capture['capture_sha256'],horizon_hours=1,assessed_at=ISSUE+timedelta(hours=1,minutes=10),recent={'status':'unavailable','prediction_f':None},check_budget=lambda:None)
    with pytest.raises(ValueError):scores.score_serving(capture,active_model,receipts,outcome(ISSUE+timedelta(hours=1)),**options)
    pair=scores.score_serving(capture,actual,receipts,outcome(ISSUE+timedelta(hours=1)),**options)
    assert pair['artifact_sha256']==candidate['artifact_sha256'] and pair['automatic_actuation'] is False
