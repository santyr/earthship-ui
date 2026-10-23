"""Explicit optional scenario producer consumes original household sources only."""
from copy import deepcopy
from datetime import timedelta
from importlib import import_module
from pathlib import Path
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_energy_forecast import fixture
from test_native_thermal_artifact import originals
from test_household_weather_scenarios import POLICY


def api():return import_module('weather_learning.scenario_worker')


def owned(tmp_path,monkeypatch,originals):
 from household.model_snapshot import restore_snapshot
 from weather_learning import native_scenarios
 energy_api,args,plan=fixture(tmp_path,monkeypatch,originals)
 energy=energy_api.seal_energy_forecast(**args)
 snap=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts']);capture=snap.weather.original_capture
 monkeypatch.setattr(native_scenarios,'current_native_runtime',lambda **kw:capture['candidate']['runtime'])
 return energy,plan,capture,args


def test_original_energy_sources_freeze_same_native_geometry_initial_state_and_parameters(tmp_path,monkeypatch,originals):
 energy,plan,capture,args=owned(tmp_path,monkeypatch,originals);before=canonical((energy,plan))
 result=api().prepare_owned_inputs(energy=energy,plan=plan)
 assert result['forcing']['origin']==capture['issued_at']
 house=result['household_inputs'];assert len(house['positions'])==24*12
 assert house['load_ac_w']==1000
 assert house['initial_soc_pct']==energy['output']['nominal_storage']['initial_soc_pct']
 assert house['nominal_bank_kwh']==energy['output']['nominal_storage']['nominal_bank_kwh']
 assert house['thermal_context']['capture_sha256']==capture['capture_sha256']
 assert canonical((energy,plan))==before


@pytest.mark.parametrize('damage',['plan_binding','system_bytes','native_runtime'])
def test_adapter_refuses_changed_source_bindings_without_repinning(tmp_path,monkeypatch,originals,damage):
 energy,plan,capture,args=owned(tmp_path,monkeypatch,originals)
 if damage=='plan_binding':energy['inputs']['plan_document_sha256']='f'*64
 elif damage=='system_bytes':energy['inputs']['system_source']['raw']+=' '
 else:
  from weather_learning import native_scenarios
  monkeypatch.setattr(native_scenarios,'current_native_runtime',lambda **kw:{})
 energy['receipt_sha256']=identity({k:v for k,v in energy.items() if k!='receipt_sha256'})
 with pytest.raises(ValueError):api().prepare_owned_inputs(energy=energy,plan=plan)


def test_disabled_profile_and_preview_never_create_state_or_publish(tmp_path,monkeypatch,originals):
 module=api();profile=dict(schema=module.SCHEMA,enabled=False,state=str(tmp_path/'absent'),energy_path=str(tmp_path/'missing'),template_paths=[],observation_cohort_sha256='e'*64,runtime_sha256='f'*64)
 assert module.run(profile,policy=POLICY)['status']=='disabled';assert not (tmp_path/'absent').exists()
 energy,plan,capture,args=owned(tmp_path,monkeypatch,originals)
 from household_solar_score import SUFFIX
 from hashlib import sha256
 path=tmp_path/(sha256(canonical(energy)).hexdigest()+SUFFIX);path.write_bytes(canonical(energy));path.chmod(0o600)
 plan_path=tmp_path/(energy['inputs']['plan_document_sha256']+'.household-model-plan-v6.json');plan_path.write_bytes(canonical(plan));plan_path.chmod(0o600)
 profile.update(enabled=True,energy_path=str(path),runtime_sha256=module.runtime_sha256())
 monkeypatch.setattr(module,'retain_report',lambda *a,**kw:pytest.fail('preview publication'))
 result=module.run(profile,policy=POLICY,clock=lambda:instant(capture['issued_at'])+timedelta(seconds=1))
 assert result['status']=='prepared';assert result['retained'] is False
 assert result['stress_cases']==3;assert result['joint_status']=='insufficient_evidence'
 assert not (tmp_path/'absent').exists()


def test_apply_has_explicit_partial_state_if_retention_raises(tmp_path,monkeypatch,originals):
 module=api();energy,plan,capture,args=owned(tmp_path,monkeypatch,originals)
 from household_solar_score import SUFFIX
 from hashlib import sha256
 path=tmp_path/(sha256(canonical(energy)).hexdigest()+SUFFIX);path.write_bytes(canonical(energy));path.chmod(0o600)
 p=tmp_path/(energy['inputs']['plan_document_sha256']+'.household-model-plan-v6.json');p.write_bytes(canonical(plan));p.chmod(0o600)
 profile=dict(schema=module.SCHEMA,enabled=True,state=str(tmp_path/'state'),energy_path=str(path),template_paths=[],observation_cohort_sha256='e'*64,runtime_sha256=module.runtime_sha256())
 def partial(*a,**kw):raise OSError('post-write readback failed')
 monkeypatch.setattr(module,'retain_report',partial)
 result=module.run(profile,policy=POLICY,apply=True,clock=lambda:instant(capture['issued_at'])+timedelta(seconds=1))
 assert result['status']=='publication_uncertain' and result['retained'] is None
 assert result['automatic_actuation'] is False


def test_owned_source_report_retains_and_replays_raw_configuration_bindings(tmp_path,monkeypatch,originals):
 module=api();energy,plan,capture,args=owned(tmp_path,monkeypatch,originals)
 from weather_learning.scenario_reporting import prepare_report,replay_report
 prepared=module.prepare_owned_inputs(energy=energy,plan=plan)
 report=prepare_report(**prepared,owned_sources=dict(energy=energy,plan=plan),policy=POLICY,blocks=[],cohort_sha256='e'*64,prepared_at=instant(capture['issued_at'])+timedelta(seconds=1))
 value=report.to_dict();assert value['inputs']['owned_sources']['energy']['inputs']['system_source']==energy['inputs']['system_source']
 assert replay_report(report.content).content==report.content
 value['inputs']['owned_sources']['energy']['inputs']['system_source']['raw']+=' '
 value['inputs']['owned_sources']['energy']['receipt_sha256']=identity({k:v for k,v in value['inputs']['owned_sources']['energy'].items() if k!='receipt_sha256'})
 value['report_sha256']=identity({k:v for k,v in value.items() if k!='report_sha256'})
 with pytest.raises(ValueError):replay_report(canonical(value))


def test_explicit_apply_retains_only_separate_unqualified_advisory(tmp_path,monkeypatch,originals):
 module=api();energy,plan,capture,args=owned(tmp_path,monkeypatch,originals)
 from household_solar_score import SUFFIX
 from hashlib import sha256
 path=tmp_path/(sha256(canonical(energy)).hexdigest()+SUFFIX);path.write_bytes(canonical(energy));path.chmod(0o600)
 p=tmp_path/(energy['inputs']['plan_document_sha256']+'.household-model-plan-v6.json');p.write_bytes(canonical(plan));p.chmod(0o600)
 state=tmp_path/'state';profile=dict(schema=module.SCHEMA,enabled=True,state=str(state),energy_path=str(path),template_paths=[],observation_cohort_sha256='e'*64,runtime_sha256=module.runtime_sha256())
 result=module.run(profile,policy=POLICY,apply=True,clock=lambda:instant(capture['issued_at'])+timedelta(seconds=1))
 assert result['status']=='retained' and result['retained'] and result['cached']
 import json
 view=json.loads((state/'scenario-advisory.json').read_bytes())
 assert len(view['stress'])==3
 assert len(view['stress'][0]['thermal_trajectory'])==24
 assert view['probability_claim'] is view['automatic_actuation'] is False
 saved=list((state/'scenario-reports').glob('*.json'));assert len(saved)==1
 original=json.loads(saved[0].read_bytes());assert original['inputs']['owned_sources']==dict(energy=energy,plan=plan)
 assert not (state/'current-model.json').exists()


def test_owned_state_adapter_does_not_require_later_calibrated_energy_package(tmp_path,monkeypatch,originals):
 import builtins
 energy,plan,capture,args=owned(tmp_path,monkeypatch,originals);module=api();original_import=builtins.__import__
 def original_packages_only(name,*args,**kwargs):
  if name=='household_calibrated_energy':raise ModuleNotFoundError('older original producer predates calibrated-energy sidecar')
  return original_import(name,*args,**kwargs)
 monkeypatch.setattr(builtins,'__import__',original_packages_only)
 prepared=module.prepare_owned_inputs(energy=energy,plan=plan)
 assert prepared['household_inputs']['load_ac_w']==1000
 assert prepared['household_inputs']['initial_soc_pct']==energy['output']['nominal_storage']['initial_soc_pct']
