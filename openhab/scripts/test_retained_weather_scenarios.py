"""Original native process boundary retains code, model, clocks and inputs."""
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from hashlib import sha256
import json
import pytest
from household.codec import canonical,identity
from test_native_thermal_artifact import originals
from test_household_scenario_worker import owned
from test_household_weather_scenarios import POLICY


def api():return import_module('weather_learning.retained_scenarios')


def bridge(tmp_path,monkeypatch,originals):
 module=api();energy,plan,capture,args=owned(tmp_path,monkeypatch,originals)
 stage=tmp_path/'retained';(stage/'sources/openhab/scripts').mkdir(parents=True);(stage/'sources/openhab/scripts/original.py').write_text('original=True\n');stage.chmod(0o700)
 producer=dict(schema=module.PRODUCER_SCHEMA,stage=str(stage),deployment_sha256='a'*64)
 monkeypatch.setattr(module,'verify_stage',lambda stage,**kw:None)
 from weather_learning.scenario_worker import prepare_owned_inputs
 from weather_learning.native_scenarios import restore_native_context,project_native_scenario
 from weather_learning.scenarios import ScenarioForcing
 prepared=prepare_owned_inputs(energy=energy,plan=plan);native=restore_native_context(prepared['household_inputs'].pop('thermal_context'))
 def launch(request,*,guard):
  assert request['energy']==energy and request['plan']==plan
  guard();result=dict(prepared=prepared,native_context_sha256=native.to_dict()['context_sha256'],artifact_sha256=native.to_dict()['artifact_sha256'])
  if request['action']=='project':result=dict(native_context_sha256=native.to_dict()['context_sha256'],projection=project_native_scenario(ScenarioForcing(canonical(request['scenario'])),native,positions=request['positions']))
  environment,binaries=module._binary_inventory();reply=dict(schema=module.REPLY_SCHEMA,request_sha256=identity(request),deployment_sha256=producer['deployment_sha256'],environment=environment,binary_files=binaries,result=result)
  reply['reply_sha256']=identity(reply);return canonical(reply)
 monkeypatch.setattr(module,'_launch',launch)
 return module,producer,energy,plan,prepared,native,launch


def test_retained_context_preserves_original_model_and_actual_native_projection(tmp_path,monkeypatch,originals):
 module,producer,energy,plan,base,native,launch=bridge(tmp_path,monkeypatch,originals)
 from weather_learning.scenarios import stress_cases,propagate
 prepared=module.prepare_retained_inputs(energy=energy,plan=plan,producer=producer);context=module.restore_retained_context(prepared['household_inputs']['thermal_context'])
 assert context.to_dict()['owned_sources']==dict(energy=energy,plan=plan)
 assert context.to_dict()['original_source_package'] and context.to_dict()['native_environment']
 with pytest.raises(AttributeError):context._content=b'changed'
 case=stress_cases(forcing=prepared['forcing'],policy=POLICY)[0]
 result=propagate(case,**prepared['household_inputs'])
 assert result['thermal']['central_parity_max_abs_f']<=1e-9
 assert result['thermal']['model_sha256']==native.to_dict()['artifact_sha256']
 assert len(result['thermal']['trajectory'])==24
 assert result['probability_claim'] is result['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['request','identity','environment'])
def test_retained_transport_refuses_unbound_or_changed_process_reply(tmp_path,monkeypatch,originals,damage):
 module,producer,energy,plan,base,native,launch=bridge(tmp_path,monkeypatch,originals)
 def bad(request,*,guard):
  value=json.loads(launch(request,guard=guard))
  if damage=='request':value['request_sha256']='f'*64
  elif damage=='identity':value['result']['native_context_sha256']='f'*64;return canonical(value)
  else:value['environment']['binary_sha256s']={}
  value['reply_sha256']=identity({k:v for k,v in value.items() if k!='reply_sha256'});return canonical(value)
 monkeypatch.setattr(module,'_launch',bad)
 with pytest.raises(ValueError):module.prepare_retained_inputs(energy=energy,plan=plan,producer=producer)


def test_retained_context_replay_refuses_source_edits_and_resealed_prepared_values(tmp_path,monkeypatch,originals):
 module,producer,energy,plan,base,native,launch=bridge(tmp_path,monkeypatch,originals);prepared=module.prepare_retained_inputs(energy=energy,plan=plan,producer=producer);value=prepared['household_inputs']['thermal_context']
 changed=deepcopy(value);changed['prepared']['household_inputs']['initial_soc_pct']=0;changed['context_sha256']=identity({k:v for k,v in changed.items() if k!='context_sha256'})
 with pytest.raises(ValueError):module.restore_retained_context(changed)
 (Path(producer['stage'])/'sources/openhab/scripts/original.py').write_text('changed=True\n')
 with pytest.raises(ValueError):module.restore_retained_context(value)


def test_invocation_cache_does_not_reuse_projection_after_original_binary_changes(tmp_path,monkeypatch,originals):
 module,producer,energy,plan,base,native,launch=bridge(tmp_path,monkeypatch,originals)
 binary=tmp_path/'native-python';binary.write_bytes(b'original binary')
 def boundary(request,*,guard):
  v=json.loads(launch(request,guard=guard));v['binary_files']={str(binary):sha256(b'original binary').hexdigest()};v['environment']['binary_sha256s']={binary.name:sha256(b'original binary').hexdigest()};v['reply_sha256']=identity({k:x for k,x in v.items() if k!='reply_sha256'});return canonical(v)
 monkeypatch.setattr(module,'_launch',boundary)
 with module.retained_cache():
  module.prepare_retained_inputs(energy=energy,plan=plan,producer=producer)
  binary.write_bytes(b'changed binary')
  with pytest.raises(ValueError):module.prepare_retained_inputs(energy=energy,plan=plan,producer=producer)


def test_disabled_retained_profile_opens_no_stage_or_subprocess(tmp_path,monkeypatch):
 module=api();worker=import_module('weather_learning.scenario_worker')
 def forbidden(*args,**kwargs):pytest.fail('disabled retained producer accessed original stage')
 monkeypatch.setattr(module,'_launch',forbidden);monkeypatch.setattr(module,'verify_stage',forbidden)
 profile=dict(schema=worker.RETAINED_SCHEMA,enabled=False,state=str(tmp_path/'absent'),energy_path=str(tmp_path/'missing'),template_paths=[],observation_cohort_sha256='e'*64,runtime_sha256='f'*64,retained_producer=dict(schema=module.PRODUCER_SCHEMA,stage=str(tmp_path/'missing-stage'),deployment_sha256='a'*64))
 assert worker.run(profile,policy=POLICY)['status']=='disabled'
 assert not (tmp_path/'absent').exists()


def test_retained_worker_explicit_apply_archives_both_source_packages_and_replays(tmp_path,monkeypatch,originals):
 module,producer,energy,plan,base,native,launch=bridge(tmp_path,monkeypatch,originals)
 worker=import_module('weather_learning.scenario_worker');reporting=import_module('weather_learning.scenario_reporting')
 path=tmp_path/(sha256(canonical(energy)).hexdigest()+'.household-energy-forecast-v1.json');path.write_bytes(canonical(energy));path.chmod(0o600)
 plan_path=tmp_path/(energy['inputs']['plan_document_sha256']+'.household-model-plan-v6.json');plan_path.write_bytes(canonical(plan));plan_path.chmod(0o600)
 from weather_learning.contracts import instant
 from datetime import timedelta
 clock=lambda:instant(base['forcing']['origin'])+timedelta(seconds=1)
 state=tmp_path/'advisory';profile=dict(schema=worker.RETAINED_SCHEMA,enabled=True,state=str(state),energy_path=str(path),template_paths=[],observation_cohort_sha256='e'*64,runtime_sha256=worker.runtime_sha256(),retained_producer=producer)
 result=worker.run(profile,policy=POLICY,apply=True,clock=clock)
 assert result['status']=='retained' and result['retained'] and result['cached']
 saved=list((state/'scenario-reports').glob('*.json'));assert len(saved)==1
 value=json.loads(saved[0].read_bytes());assert value['runtime']['source_package']
 context=value['inputs']['household_inputs']['thermal_context'];assert context['original_source_manifest']=={'openhab/scripts/original.py':sha256(b'original=True\n').hexdigest()}
 assert value['inputs']['owned_sources']['retained_producer']==producer
 with module.retained_cache():assert reporting.replay_report(saved[0].read_bytes()).to_dict()==value
 view=json.loads((state/'scenario-advisory.json').read_bytes());assert len(view['stress'][0]['thermal_trajectory'])==24
 assert view['probability_claim'] is view['automatic_actuation'] is False
 assert not (state/'current-model.json').exists()


def test_native_process_cannot_substitute_another_model_in_a_bound_reply(tmp_path,monkeypatch,originals):
 module,producer,energy,plan,base,native,launch=bridge(tmp_path,monkeypatch,originals)
 prepared=module.prepare_retained_inputs(energy=energy,plan=plan,producer=producer);context=module.restore_retained_context(prepared['household_inputs']['thermal_context'])
 def foreign(request,*,guard):
  value=json.loads(launch(request,guard=guard));value['result']['projection']['model_sha256']='f'*64;value['reply_sha256']=identity({k:v for k,v in value.items() if k!='reply_sha256'});return canonical(value)
 monkeypatch.setattr(module,'_launch',foreign)
 from weather_learning.scenarios import stress_cases
 case=stress_cases(forcing=prepared['forcing'],policy=POLICY)[0]
 with pytest.raises(ValueError):module.project_retained_scenario(case,context,positions=prepared['household_inputs']['positions'])
