"""Receipt serving must preserve independent as-issued numerics and provenance."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from test_native_model_serving_receipt import serving,originals
from test_native_thermal_forecast import ISSUE,future
from test_installed_shade_origin import weather,actions
from test_installed_shade_inputs import EPOCHS


def context(tmp_path,originals,monkeypatch):
    forecasts=importlib.import_module('native_thermal_forecast')
    assert callable(getattr(forecasts,'build_serving_capture',None)), 'receipt serving forecast is missing'
    values=serving(tmp_path,originals);module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=values
    model=module.read_serving_model(selection,assessed_at=ISSUE,guard=lambda:None)
    import test_thermal_sensor_epoch_origins as old
    from thermal_model.temperature_history import STREAMS
    from weather_temperature_sources import build_temperature_source,write_compressed_temperature_source,replay_temperature_source
    from thermal_temperature_runtime import shadow_temperatures_v2
    retained_paths={};saved=[]
    def retained(rows,*,targets,assessed_at,history_start,stream,policy,sensor_epoch):
        packet=build_temperature_source(rows=rows,targets=targets,assessed_at=assessed_at,stream=stream,policy=policy,sensor_epoch=sensor_epoch)
        assert packet['history_start']==history_start.isoformat()
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        retained_paths[role]=str(write_compressed_temperature_source(tmp_path,packet))
        return replay_temperature_source(packet)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old,'NOW',ISSUE);patch.setattr(old,'select_temperature_grid_v2',retained)
        selected=shadow_temperatures_v2(ISSUE,old.native_grid(),sensor_epochs=EPOCHS,origin_observer=saved.append)
    inputs=dict(forecast=weather(ISSUE),current={role:row['current'] for role,row in selected.items()},origin_temperatures=saved[0],action_snapshot=actions(ISSUE),native_source_paths=retained_paths)
    geometry=future(ISSUE)
    kwargs=dict(geometry=geometry,expected_geometry_sha256=geometry.sha256,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2),check_budget=lambda:None)
    return forecasts,artifacts,candidate,model,inputs,kwargs,retained_paths


def test_serving_and_full_forecasts_keep_identical_bytes_and_real_source_lineage(tmp_path,originals,monkeypatch):
    forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    full=forecasts.build_capture(candidate,inputs,runtime=model.runtime,expected_artifact_sha256=candidate['artifact_sha256'],**kwargs)
    def forbidden(*args,**kwargs):pytest.fail('receipt serving repeated full numerical candidate validation')
    monkeypatch.setattr(forecasts,'validate_native_candidate',forbidden)
    served=forecasts.build_serving_capture(model,inputs,**kwargs)
    assert served==full
    assert served['native_origin_binding']==full['native_origin_binding']
    assert forecasts.validate_serving_capture(served,model,expected_capture_sha256=served['capture_sha256'],check_budget=lambda:None)==full
    assert forecasts.publication(served)==forecasts.publication(full)
    assert served['output']['automatic_actuation'] is False
    target=forecasts.persist(tmp_path,served)
    assert forecasts.read_serving_capture(target,model,expected_capture_sha256=served['capture_sha256'],check_budget=lambda:None)==full
    from pathlib import Path
    Path(paths['air']).unlink()
    with pytest.raises((ValueError,OSError)):forecasts.validate_serving_capture(served,model,expected_capture_sha256=served['capture_sha256'],check_budget=lambda:None)


def test_receipt_serving_and_independent_full_replay_both_reject_resealed_predictions(tmp_path,originals,monkeypatch):
    forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    value=forecasts.build_serving_capture(model,inputs,**kwargs)
    damaged=deepcopy(value);damaged['output']['trajectory'][0]['air_f']+=1;damaged['capture_sha256']=forecasts.digest(damaged,'capture_sha256')
    with pytest.raises(ValueError):forecasts.validate_serving_capture(damaged,model,expected_capture_sha256=damaged['capture_sha256'],check_budget=lambda:None)
    with pytest.raises(ValueError):forecasts.validate_capture(damaged,runtime=model.runtime,expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=damaged['capture_sha256'],check_budget=lambda:None)


def test_caller_candidate_dictionary_cannot_select_receipt_serving(tmp_path,originals,monkeypatch):
    forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    with pytest.raises((ValueError,TypeError)):forecasts.build_serving_capture(candidate,inputs,**kwargs)
