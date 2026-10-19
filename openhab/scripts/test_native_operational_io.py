"""Current Google execution must not load a retired standalone publisher."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import importlib,importlib.util,subprocess,sys
import pytest

ROOT=Path(__file__).resolve().parent


def api():
    assert importlib.util.find_spec('thermal_model.native_operational_io') is not None,'neutral native operational helpers are absent'
    return importlib.import_module('thermal_model.native_operational_io')


def test_native_runtime_uses_neutral_binding_and_original_source_inventory():
    helper=api()
    import native_thermal_artifact
    assert native_thermal_artifact.current_base_runtime is helper.current_runtime
    assert {'thermal_model/native_operational_io.py','thermal_model/serial_publication_caps.py'}<=helper.RUNTIME_PATHS
    assert helper.RUNTIME_ROOT==ROOT


def test_current_native_imports_do_not_load_legacy_publishers():
    code="""
import importlib.abc,sys
blocked={'thermal_model.provisional_live','thermal_model.provisional_monitor','thermal_installed_intel','provisional_thermal'}
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,*args):
  if fullname in blocked:raise AssertionError('retired standalone runtime imported: '+fullname)
sys.meta_path.insert(0,Block())
import native_thermal_artifact,native_thermal_live,household_forecast_score,household_cycle_deploy
import household.thermal_model
household_forecast_score.production_resource_preflight=lambda:None
with household_forecast_score.production_score_policy():pass
assert not blocked.intersection(sys.modules)
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_issue_clock_and_three_day_discovery_keep_original_boundaries(tmp_path):
    helper=api();tmp_path.chmod(0o700)
    at=datetime(2026,10,18,12,4,59,tzinfo=timezone.utc)
    assert helper._next_issue(at)==at.replace(minute=5,second=15)
    for offset in range(4):
        helper._phase_directory(tmp_path,'scores',at-timedelta(days=offset))
    assert [path.name for path in helper._folders(tmp_path,'scores',at)]==['scores-20261018','scores-20261017','scores-20261016']


def test_receipt_retry_uses_issuing_clock_and_rechecks_guard(monkeypatch):
    helper=api()
    from thermal_model.installed_shade_live_inputs import TelemetryTransport
    backend=TelemetryTransport.__new__(TelemetryTransport)
    at=datetime(2026,10,18,12,tzinfo=timezone.utc);calls=[];checks=[];waits=[]
    def persisted(item,state,*,since,until,preflight):
        calls.append((since,until));preflight()
        if len(calls)==1:raise ValueError('one exact actual persisted publication required')
        return {'item':item,'state':state}
    backend.persisted=persisted
    monkeypatch.setattr(helper,'sleep',waits.append)
    result=helper._persisted_after_write(backend,'Thermal_Model_JSON','{}',since=at,
        guard=lambda:checks.append('held'),clock=lambda:at+timedelta(milliseconds=10))
    assert result=={'item':'Thermal_Model_JSON','state':'{}'}
    assert calls==[(at,at+timedelta(milliseconds=10))]*2 and waits==[1]
    assert len(checks)>=3


def test_current_consumers_import_helpers_without_legacy_runtime():
    import ast
    names=('native_thermal_artifact.py','native_thermal_live.py','household_cycle.py','household_forecast_score.py',
           'household_cycle_deploy.py','household_retained_native_score.py','household_native_geometry_prepare.py','household/thermal_model.py')
    for name in names:
        tree=ast.parse((ROOT/name).read_bytes())
        modules=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        assert not {'thermal_model.provisional_live','thermal_model.provisional_monitor'}&set(modules),name


def test_shared_worker_imports_and_collection_admission_do_not_load_old_cli():
    import ast
    for name in ('capture-thermal-inputs.py','assemble-thermal-inputs.py','qualify-installed-shade.py','household_energy_source_install.py'):
        path=ROOT.parents[1]/'scripts'/name
        imports=[node.module for node in ast.walk(ast.parse(path.read_bytes())) if isinstance(node,ast.ImportFrom)]
        assert 'thermal_installed_intel' not in imports,name
    code="""
import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,*args):
  if fullname=='thermal_installed_intel':raise AssertionError('shared worker imported old publisher CLI')
sys.meta_path.insert(0,Block())
import astro_geometry_worker,thermal_installed_train,thermal_installed_calibrate,thermal_installed_score,forecast_temperature_collect
from thermal_model import serial_publication_caps,training_pressure_guard
class CurrentPolicy(Exception):pass
def refuse():raise CurrentPolicy('neutral verifier reached before collection')
serial_publication_caps._resource_preflight=refuse
try:training_pressure_guard.run_collection_worker(['/usr/bin/false'])
except CurrentPolicy:pass
else:raise AssertionError('collection bypassed its resource verifier')
"""
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_native_geometry_and_capture_source_closures_pin_neutral_verifier():
    import astro_geometry_worker as geometry
    neutral='openhab/scripts/thermal_model/serial_publication_caps.py'
    assert neutral in geometry.CODE_FILES
    assert 'openhab/scripts/thermal_installed_intel.py' not in geometry.CODE_FILES
    import importlib.util
    path=ROOT.parents[1]/'scripts/capture-thermal-inputs.py'
    spec=importlib.util.spec_from_file_location('_native_capture_source_closure',path)
    capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
    seen=[]
    from thermal_model import origin_capture
    from unittest.mock import patch
    def read(path,**kwargs):seen.append(str(path.relative_to(capture.ROOT)));return b'isolated source closure'
    with patch.object(origin_capture,'_source_bytes',read):capture._capture_revision()
    assert neutral in seen
    assert 'openhab/scripts/thermal_installed_intel.py' not in seen
