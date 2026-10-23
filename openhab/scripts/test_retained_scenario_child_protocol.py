"""Exercise the child transport branch independently of native numerical work."""
from importlib import import_module
from pathlib import Path
from types import ModuleType,SimpleNamespace
import io,json,sys
import pytest
from household.codec import canonical,identity


@pytest.mark.parametrize('action',['prepare','project'])
def test_legacy_reply_schema_survives_importing_the_household_package(tmp_path,monkeypatch,action):
    child=import_module('weather_learning.retained_scenario_child')
    boundary=import_module('weather_learning.retained_scenarios')
    stage=tmp_path/'stage';source=stage/'sources';source.mkdir(parents=True)
    producer=dict(schema=boundary.PRODUCER_SCHEMA,stage=str(stage),deployment_sha256='a'*64)
    request=dict(schema=boundary.REQUEST_SCHEMA,producer=producer,energy={},plan={},action=action,
        scenario={} if action=='project' else None,positions=[] if action=='project' else None,adapter_source_sha256='d'*64)
    # Numerical preparation is an external boundary here. Keep real Python
    # imports, request validation and reply encoding to catch import shadowing.
    context=SimpleNamespace(to_dict=lambda:dict(context_sha256='e'*64,artifact_sha256='f'*64))
    modules={
        'retained_scenarios':dict(REQUEST_SCHEMA=boundary.REQUEST_SCHEMA,REPLY_SCHEMA=boundary.REPLY_SCHEMA,
            REQUEST_V2=boundary.REQUEST_V2,REPLY_V2=boundary.REPLY_V2,_adapter_sha=lambda:'d'*64,
            _binary_inventory=lambda:({'scope':'transport_fixture'},{}),producer_reference=boundary.producer_reference),
        'scenario_worker':dict(prepare_owned_inputs=lambda **kw:dict(household_inputs={'thermal_context':{}})),
        'native_scenarios':dict(restore_native_context=lambda *a,**kw:context,project_native_scenario=lambda *a,**kw:dict(model_sha256='f'*64)),
        'scenarios':dict(ScenarioForcing=lambda raw:raw),
    }
    monkeypatch.setitem(sys.modules,'earthship_scenario_overlay',ModuleType('earthship_scenario_overlay'))
    for name,attrs in modules.items():
        module=ModuleType('earthship_scenario_overlay.'+name);module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules,module.__name__,module)
    import household_cycle_deploy,native_thermal_artifact,household.model_snapshot,thermal_model.installed_shade_dynamics
    monkeypatch.setattr(household_cycle_deploy,'verify_stage',lambda *a,**kw:None)
    for module in (native_thermal_artifact,household.model_snapshot,thermal_model.installed_shade_dynamics):
        monkeypatch.setattr(module,'__file__',str(source/(module.__name__.replace('.','/')+'.py')))
    output=io.BytesIO()
    with monkeypatch.context() as streams:
        streams.setattr(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(canonical(request))))
        streams.setattr(sys,'stdout',SimpleNamespace(buffer=output))
        child.main()
    reply=json.loads(output.getvalue())
    assert reply['schema']=='earthship-retained-native-scenario-reply/v1'
    assert reply['request_sha256']==identity(request)
    assert reply['deployment_sha256']=='a'*64
    assert reply['reply_sha256']==identity({k:v for k,v in reply.items() if k!='reply_sha256'})
