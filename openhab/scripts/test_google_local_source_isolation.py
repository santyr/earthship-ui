"""Qualified local measurements remain usable after legacy weather removal."""
from pathlib import Path
import os
import subprocess
import sys


def test_native_temperature_sources_import_without_retired_forecast_workers():
    source=Path(__file__).parent
    code="""import builtins
original=builtins.__import__
retired={'forecast_intel','forecast_input_capture','forecast_temperature_origin'}
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in retired:raise ImportError('retired forecast dependency: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
import weather_temperature_sources
assert callable(weather_temperature_sources.replay_temperature_source)
"""
    result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(source)),
        capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_current_native_runtime_does_not_include_retired_forecast_capture_code():
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    assert {'forecast_input_capture.py','forecast_temperature_origin.py'}.isdisjoint(RAW_RUNTIME_PATHS)
    assert 'weather_source_files.py' in RAW_RUNTIME_PATHS


def _current_receipt_manifests_without_legacy_reads(monkeypatch):
    import household_snapshot as snapshot
    import household_pipeline as pipeline
    import household_outcomes as outcomes
    retired={'forecast_intel.py','forecast_input_capture.py','forecast_temperature_origin.py'}
    original=snapshot._read
    def current_source(path,*args,**kwargs):
        if Path(path).name in retired:
            raise AssertionError('current receipt opened retired worker '+Path(path).name)
        return original(path,*args,**kwargs)
    for module in (snapshot,pipeline,outcomes):monkeypatch.setattr(module,'_read',current_source)
    return snapshot,pipeline,outcomes


def test_current_snapshot_receipt_pins_only_executed_validators(monkeypatch):
    from hashlib import sha256
    snapshot,_,_=_current_receipt_manifests_without_legacy_reads(monkeypatch)
    manifest=snapshot.runtime_manifest()
    required=('pv_day_evidence.py','weather_temperature_sources.py','weather_temperature_reader.py',
              'weather_temperature_evidence.py','weather_temperature_config.py','weather_temperature_history.py',
              'thermal_model/temperature_history.py','thermal_model/schema.py')
    for name in required:
        assert manifest['openhab/scripts/'+name]==sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
    assert not {'openhab/scripts/forecast_input_capture.py','openhab/scripts/forecast_temperature_origin.py'}&set(manifest)


def test_current_pipeline_receipt_does_not_open_old_forecast_worker(monkeypatch):
    _,pipeline,_=_current_receipt_manifests_without_legacy_reads(monkeypatch)
    manifest=pipeline.pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    assert 'openhab/scripts/forecast_intel.py' not in manifest
    assert {'openhab/scripts/household_plan.py','openhab/scripts/household_pipeline.py',
            'openhab/scripts/weather_radiation_reader.py','openhab/scripts/weather_rain_evidence.py'}<=set(manifest)


def test_current_outcome_receipt_does_not_open_old_forecast_worker(monkeypatch):
    _,_,outcomes=_current_receipt_manifests_without_legacy_reads(monkeypatch)
    manifest=outcomes.outcome_runtime_manifest()
    assert 'openhab/scripts/forecast_intel.py' not in manifest
    assert 'openhab/scripts/household_outcomes.py' in manifest


def test_original_plan_receipt_keeps_exact_closure_and_refuses_old_or_tampered_sources(monkeypatch):
    import pytest
    _,pipeline,outcomes=_current_receipt_manifests_without_legacy_reads(monkeypatch)
    actual=pipeline.pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    plan={'schema':'earthship-household-model-plan-receipt/v1','runtime_manifest':dict(actual)}
    assert outcomes.original_plan_runtime(plan,actual=actual)==actual
    old={'schema':plan['schema'],'runtime_manifest':dict(actual,**{'openhab/scripts/forecast_intel.py':'a'*64})}
    with pytest.raises(ValueError):outcomes.original_plan_runtime(old,actual=actual)
    changed=dict(actual);changed['openhab/scripts/weather_temperature_history.py']='b'*64
    with pytest.raises(ValueError):outcomes.original_plan_runtime(plan,actual=changed)
    missing=dict(actual);del missing['openhab/scripts/weather_temperature_history.py']
    with pytest.raises(ValueError):outcomes.original_plan_runtime(plan,actual=missing)
