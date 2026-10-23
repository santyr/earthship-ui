"""Fixed read-only native child, bootstrapped with original global imports."""
from pathlib import Path
from hashlib import sha256
import json,sys,time,types


def main():
    root=Path(__file__).resolve().parents[3];raw=sys.stdin.buffer.read(16*1024**2+1)
    if len(raw)>16*1024**2:raise ValueError('bounded original native request required')
    request=json.loads(raw);started=time.monotonic()
    def guard():
        if time.monotonic()-started>70:raise TimeoutError('bounded original native projection elapsed')
    from household.codec import canonical,identity
    from household_cycle_deploy import verify_stage
    stage=Path(request['producer']['stage']);pin=request['producer']['deployment_sha256'];verify_stage(stage,expected_deployment_sha256=pin)
    package=types.ModuleType('earthship_scenario_overlay');package.__path__=[str(root/'openhab/scripts/weather_learning')];sys.modules[package.__name__]=package
    from earthship_scenario_overlay.retained_scenarios import REQUEST_SCHEMA,REPLY_SCHEMA,REQUEST_V2,REPLY_V2,_adapter_sha,_binary_inventory,producer_reference
    from earthship_scenario_overlay.scenario_worker import prepare_owned_inputs
    from earthship_scenario_overlay.native_scenarios import restore_native_context,project_native_scenario
    from earthship_scenario_overlay.scenarios import ScenarioForcing
    producer_reference(request['producer'])
    household=request.get('schema')==REQUEST_V2
    fields={'schema','producer','energy','plan','action','scenario','positions','adapter_source_sha256'}
    if (set(request)!=(fields|{'profiled'} if household else fields) or request['schema'] not in (REQUEST_SCHEMA,REQUEST_V2) or
        request['action'] not in (('household',) if household else ('prepare','project')) or request['adapter_source_sha256']!=_adapter_sha()):
        raise ValueError('closed current original native request required')
    if household:
        def no_acquisition(event,args):
            if event.startswith('socket.') or event=='subprocess.Popen':
                raise ValueError('original household input replay cannot acquire network/SQL data or launch workers')
        sys.addaudithook(no_acquisition)
        if request['scenario'] is not None or request['positions'] is not None:raise ValueError('original household input request cannot supply constructed forcing')
        from earthship_scenario_overlay.component_household_inputs import prepare_original_inputs
        result=prepare_original_inputs(energy=request['energy'],plan=request['plan'],profiled=request['profiled'],guard=guard)
    else:
        prepared=prepare_owned_inputs(energy=request['energy'],plan=request['plan'],guard=guard);context=restore_native_context(prepared['household_inputs'].pop('thermal_context'),guard=guard);prepared['household_inputs']['thermal_context']=None
        value=context.to_dict();result=dict(prepared=prepared,native_context_sha256=value['context_sha256'],artifact_sha256=value['artifact_sha256'])
        if request['action']=='project':result=dict(native_context_sha256=value['context_sha256'],projection=project_native_scenario(ScenarioForcing(canonical(request['scenario'])),context,positions=request['positions'],guard=guard))
        elif request['scenario'] is not None or request['positions'] is not None:raise ValueError('preparation cannot substitute a constructed trajectory')
    import native_thermal_artifact,household.model_snapshot,thermal_model.installed_shade_dynamics
    if any(not Path(m.__file__).resolve().is_relative_to(stage/'sources') for m in (native_thermal_artifact,household.model_snapshot,thermal_model.installed_shade_dynamics)):raise ValueError('original native global imports required')
    verify_stage(stage,expected_deployment_sha256=pin);guard();environment,binaries=_binary_inventory();reply=dict(schema=REPLY_V2 if household else REPLY_SCHEMA,request_sha256=identity(request),deployment_sha256=pin,environment=environment,binary_files=binaries,result=result);reply['reply_sha256']=identity(reply);raw=canonical(reply)
    if len(raw)>16*1024**2:raise ValueError('bounded original native reply required')
    sys.stdout.buffer.write(raw+b'\n')


if __name__=='__main__':main()
