"""Serving admission must not change frozen household output or replay authority."""
import importlib
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import pytest
from test_native_serving_forecast import context,originals

CODE='a'*40


def api():
    module=importlib.import_module('household.weather_context')
    assert callable(getattr(module,'prepare_serving_native_cycle_contexts',None)), 'serving household preparation is missing'
    return module


def test_serving_household_context_matches_independent_full_projection(tmp_path,originals,monkeypatch):
    module=api();forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    capture=forecasts.build_capture(candidate,inputs,runtime=model.runtime,expected_artifact_sha256=candidate['artifact_sha256'],**kwargs)
    full=module.prepare_native_cycle_contexts(capture,code_revision=CODE,runtime=model.runtime,expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'],check_budget=lambda:None)
    def forbidden(*args,**kwargs):pytest.fail('serving household repeated numerical candidate validation')
    monkeypatch.setattr(forecasts,'validate_native_candidate',forbidden)
    served=module.prepare_serving_native_cycle_contexts(capture,model,code_revision=CODE,expected_capture_sha256=capture['capture_sha256'],check_budget=lambda:None)
    assert served[0].to_dict()==full[0].to_dict()
    assert served[1].to_dict()==full[1].to_dict()
    from household.thermal_model import project
    assert project(served[0])==project(full[0])
    assert module.project_weather(served[1])==module.project_weather(full[1])
    assert project(served[0])['action_effects_qualified'] is False


def test_serving_household_refuses_changed_original_source(tmp_path,originals,monkeypatch):
    module=api();forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    capture=forecasts.build_serving_capture(model,inputs,**kwargs)
    Path(paths['air']).unlink()
    with pytest.raises((ValueError,OSError)):module.prepare_serving_native_cycle_contexts(capture,model,code_revision=CODE,expected_capture_sha256=capture['capture_sha256'],check_budget=lambda:None)


def test_serving_household_freezes_capture_before_guard_callbacks(tmp_path,originals,monkeypatch):
    module=api();forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    capture=forecasts.build_serving_capture(model,inputs,**kwargs);expected=deepcopy(capture['output'])
    def mutate():capture['output']['trajectory'][0]['air_f']=99
    prepared,_=module.prepare_serving_native_cycle_contexts(capture,model,code_revision=CODE,expected_capture_sha256=capture['capture_sha256'],check_budget=mutate)
    from household.thermal_model import project
    assert project(prepared)['output']==expected
    assert capture['output']['trajectory'][0]['air_f']==99
