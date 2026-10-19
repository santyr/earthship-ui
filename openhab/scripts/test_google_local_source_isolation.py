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
