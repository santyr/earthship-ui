"""Original native-process inputs for new PV; no borrowed calibrated outputs."""
from copy import deepcopy
from datetime import timedelta
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_native_thermal_artifact import originals
from test_household_scenario_worker import owned


def test_component_inputs_keep_raw_sources_and_qualified_state_without_requiring_a_load_model(tmp_path,monkeypatch,originals):
 from weather_learning.component_household_inputs import prepare_original_inputs
 energy,plan,capture,_=owned(tmp_path,monkeypatch,originals);before=canonical([energy,plan])
 value=prepare_original_inputs(energy=energy,plan=plan,profiled=None)
 assert value['schema']=='earthship-original-component-household-inputs/v1'
 assert value['issued_at']==capture['issued_at'] and value['forecast']==capture['inputs']['forecast']
 assert value['system_source']==energy['inputs']['system_source'] and value['horizon_source']==energy['inputs']['horizon_source']
 assert value['storage_initial_conditions']['reason'] is None
 assert value['storage_initial_conditions']['current_load_w'] is not None
 assert value['load_forecast'] is None and value['load_model'] is None
 assert len(value['positions'])>=288 and canonical([energy,plan])==before
 assert value['automatic_actuation'] is False


def test_original_learned_load_is_replayed_in_its_producer_and_retained_separately(tmp_path,monkeypatch,originals):
 from weather_learning.component_household_inputs import prepare_original_inputs
 from household_profiled_forecast import seal_profiled_forecast,profiled_runtime_manifest
 from household_energy_forecast import forecast_runtime_manifest
 from test_household_profiled_forecast import supported_source
 energy,plan,capture,args=owned(tmp_path,monkeypatch,originals);issue=instant(capture['issued_at'])
 source,lr=supported_source(issue)
 profiled=seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=source,now=args['now'],
  runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=forecast_runtime_manifest(),load_runtime_manifest=lr)
 before=canonical(profiled);value=prepare_original_inputs(energy=energy,plan=plan,profiled=profiled)
 assert value['load_forecast']==profiled['output']['load_forecast'] and len(value['load_forecast']['trajectory'])==24
 assert value['load_model']['model_sha256']==source['artifact']['profile']['model_sha256']
 assert canonical(profiled)==before
 profiled['output']['load_forecast']['trajectory'][0]['mean_ac_w']+=1
 profiled['receipt_sha256']=identity({k:v for k,v in profiled.items() if k!='receipt_sha256'})
 with pytest.raises(ValueError):prepare_original_inputs(energy=energy,plan=plan,profiled=profiled)


def test_changed_original_energy_or_plan_cannot_supply_new_component_inputs(tmp_path,monkeypatch,originals):
 from weather_learning.component_household_inputs import prepare_original_inputs
 energy,plan,capture,_=owned(tmp_path,monkeypatch,originals)
 energy['output']['array_pv']['potential_pv_kwh']+=1
 energy['receipt_sha256']=identity({k:v for k,v in energy.items() if k!='receipt_sha256'})
 with pytest.raises(ValueError):prepare_original_inputs(energy=energy,plan=plan,profiled=None)

def test_retained_component_transport_keeps_original_source_packages_and_binary_identity(tmp_path,monkeypatch,originals):
 from weather_learning import retained_scenarios as boundary
 from weather_learning.component_household_inputs import prepare_original_inputs
 from pathlib import Path
 energy,plan,_,_=owned(tmp_path,monkeypatch,originals)
 stage=tmp_path/'retained';(stage/'sources/openhab/scripts').mkdir(parents=True);stage.chmod(0o700)
 (stage/'sources/openhab/scripts/original.py').write_text('original=True\n')
 producer=dict(schema=boundary.PRODUCER_SCHEMA,stage=str(stage),deployment_sha256='a'*64)
 monkeypatch.setattr(boundary,'verify_stage',lambda *a,**k:None)
 def launch(request,*,guard):
  assert request['schema']=='earthship-retained-native-scenario-request/v2' and request['action']=='household' and request['profiled'] is None
  result=prepare_original_inputs(energy=request['energy'],plan=request['plan'],profiled=request['profiled'],guard=guard)
  env,binary=boundary._binary_inventory()
  reply=dict(schema='earthship-retained-native-scenario-reply/v2',request_sha256=identity(request),deployment_sha256=producer['deployment_sha256'],environment=env,binary_files=binary,result=result)
  reply['reply_sha256']=identity(reply);return canonical(reply)
 monkeypatch.setattr(boundary,'_launch',launch)
 result=boundary.prepare_component_inputs(energy=energy,plan=plan,profiled=None,producer=producer)
 value=result.to_dict()
 assert value['prepared']['original_document_sha256s']['energy']==identity(energy)
 assert value['original_source_package'] and value['native_environment']
 assert boundary.restore_component_inputs(value).to_dict()==value
 changed=deepcopy(value);changed['prepared']['storage_initial_conditions']['initial_soc_pct']=1
 changed['context_sha256']=identity({k:v for k,v in changed.items() if k!='context_sha256'})
 with pytest.raises(ValueError):boundary.restore_component_inputs(changed)


def test_explicit_new_producer_interpreter_is_byte_bound_and_old_reference_still_supported(tmp_path):
 from weather_learning import retained_scenarios as boundary
 from pathlib import Path
 from hashlib import sha256
 import sys
 original=dict(schema=boundary.PRODUCER_SCHEMA,stage=str(tmp_path),deployment_sha256='a'*64)
 assert boundary.producer_reference(original)==original
 value=dict(original,schema='earthship-retained-native-scenario-producer/v2',python_path=sys.executable,
  python_sha256=sha256(Path(sys.executable).resolve().read_bytes()).hexdigest())
 assert boundary.producer_reference(value)==value
 value['python_sha256']='f'*64
 with pytest.raises(ValueError):boundary.producer_reference(value)

def test_original_producer_environment_cannot_be_substituted_when_values_happen_to_match(tmp_path,monkeypatch,originals):
 from weather_learning.component_household_inputs import prepare_original_inputs
 from weather_learning import native_scenarios
 energy,plan,_,_=owned(tmp_path,monkeypatch,originals)
 monkeypatch.setattr(native_scenarios,'current_native_runtime',lambda **kw:{'changed_environment':True})
 with pytest.raises(ValueError,match='producer.*environment|environment.*producer'):
  prepare_original_inputs(energy=energy,plan=plan,profiled=None)
