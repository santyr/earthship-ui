"""Runtime qualification routes v3 through the owned reader under old caps."""
import inspect,json
from datetime import timedelta
from pathlib import Path
import pytest
from test_native_serving_selection import stage


def test_receipt_runtime_probe_uses_external_selection_and_unchanged_headroom(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    assert 'deployment_sha256' in inspect.signature(deploy.verify_runtime).parameters,'runtime selection pin missing'
    deploy,args,settings,helper,libraries,pin=stage(tmp_path,monkeypatch)
    import native_thermal_live as native,native_thermal_artifact as artifact
    import thermal_model.provisional_live as legacy,native_inference_pressure as pressure
    import thermal_installed_intel as installed,household_cycle_sources as collection
    import native_model_serving_receipt as serving
    candidate=json.loads(Path(settings['candidate_path']).read_bytes());calls=[];selection=object()
    monkeypatch.setattr(deploy,'__file__',str(args['stage']/'sources/openhab/scripts/household_cycle_deploy.py'))
    monkeypatch.setattr(installed,'_resource_preflight',lambda:None)
    monkeypatch.setattr(legacy,'_next_issue',lambda now:now+timedelta(minutes=5))
    monkeypatch.setattr(native,'load_settings',lambda path:settings)
    class Headroom:
        def preflight(self):calls.append('quiet')
        def check(self):calls.append('pressure')
    monkeypatch.setattr(pressure,'NativeInferenceHeadroom',Headroom)
    monkeypatch.setattr(artifact,'current_native_runtime',lambda *,guard:(guard(),candidate['runtime'])[1])
    monkeypatch.setattr(artifact,'read_native_candidate',lambda *a,**kw:pytest.fail('receipt probe repeated numerical admission'))
    def selected(actual,*,expected_deployment_sha256,assessed_at,guard):
        assert actual==args['stage'] and expected_deployment_sha256==pin;guard();calls.append('selected');return selection
    class Model:
        runtime=candidate['runtime']
        def verify_bindings(self,*,assessed_at,guard):guard();calls.append('fresh')
    def read(actual,*,assessed_at,guard):assert actual is selection;guard();calls.append('read');return Model()
    monkeypatch.setattr(serving,'load_serving_selection',selected);monkeypatch.setattr(serving,'read_serving_model',read)
    class Collector:
        def __init__(self,**kw):assert kw['code_revision']==args['code_revision'];calls.append('collector')
        def verify_unchanged(self):calls.append('collector_verified')
    monkeypatch.setattr(collection,'CycleSourceCollector',Collector)
    result=deploy.verify_runtime(args['stage'],deployment_sha256=pin)
    assert result['status']=='runtime_verified' and result['deployment_sha256']==pin
    assert calls.count('read')==1 and calls.index('quiet')<calls.index('selected') and 'fresh' in calls


def test_capped_qualification_command_pins_receipt_stage_without_new_limits(tmp_path,monkeypatch):
    import household_cycle_deploy as deploy
    assert 'deployment_sha256' in inspect.signature(deploy._qualify).parameters,'capped verifier pin missing'
    deploy,args,settings,helper,libraries,pin=stage(tmp_path,monkeypatch);seen=[]
    def execute(command,*,timeout):
        seen.append(command);assert timeout==55
        return json.dumps({'status':'runtime_verified','deployment_sha256':pin,'automatic_actuation':False}).encode()
    monkeypatch.setattr(deploy.subprocess,'check_output',execute)
    deploy._qualify(args['stage'],deployment_sha256=pin)
    command=seen[0]
    assert command[-2:]==['--deployment-sha256',pin]
    for cap in ('CPUQuota=20%','MemoryMax=256M','MemorySwapMax=0','TasksMax=24','IOWeight=10'):assert cap in command
    assert '45s' in command
