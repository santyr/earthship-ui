"""Extract actual original household inputs inside their retained producer.

No new forecast is issued here. Original receipts are replayed using the
producer's original imports; the new electrical model runs in its own process.
"""
from copy import deepcopy
from .contracts import canonical,identity,instant

SCHEMA='earthship-original-component-household-inputs/v1'


def prepare_original_inputs(*,energy,plan,profiled,guard=lambda:None):
    from household_energy_forecast import replay_energy_forecast,forecast_runtime_manifest
    from household_profiled_forecast import replay_profiled_forecast,profiled_runtime_manifest
    from household_ac_load_artifact import runtime_manifest as load_runtime
    from household.model_snapshot import restore_snapshot
    from household.weather_context import project_weather
    from .scenario_worker import _storage_inputs
    from .native_scenarios import current_native_runtime
    guard()
    snapshot=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts'])
    capture=snapshot.weather.original_capture
    if current_native_runtime(guard=guard)!=capture['candidate']['runtime']:
        raise ValueError('original producer environment or numerical source differs')
    energy=replay_energy_forecast(energy,plan_receipt=plan,runtime_manifest=forecast_runtime_manifest())
    if profiled is not None:
        profiled=replay_profiled_forecast(profiled,energy_receipt=energy,plan_receipt=plan,runtime_manifest=profiled_runtime_manifest(),
            energy_runtime_manifest=forecast_runtime_manifest(),load_runtime_manifest={} if profiled['inputs']['load_source'] is None else load_runtime())
    origin=instant(capture['issued_at']);weather=project_weather(snapshot.weather)
    if origin!=instant(energy['output']['array_pv']['origin']):raise ValueError('same original component household origin required')
    positions=weather.get('solar_geometry',{}).get('positions')
    if not isinstance(positions,list) or not 1<=len(positions)<=576:raise ValueError('complete original household native geometry required')
    initial=_storage_inputs(snapshot,topology_source=energy['inputs']['topology_source'],origin=origin)
    # Missing instantaneous load need not withdraw PV or the separate learned
    # load/storage hypothesis; preserve its own original exclusion reason.
    load=None if profiled is None else profiled['output']['load_forecast']
    model=None
    if profiled is not None and profiled['inputs']['load_source'] is not None:
        artifact=profiled['inputs']['load_source']['artifact'];profile=artifact['profile']
        model=dict(model_sha256=profile['model_sha256'],trained_through=profile['latest_qualified_hour_end'],training_cutoff=artifact['cutoff'])
    value=dict(schema=SCHEMA,issued_at=origin.isoformat(),forecast=deepcopy(capture['inputs']['forecast']),positions=deepcopy(positions),
        system_source=deepcopy(energy['inputs']['system_source']),horizon_source=deepcopy(energy['inputs']['horizon_source']),
        storage_initial_conditions=initial,load_forecast=load,load_model=model,
        original_document_sha256s=dict(energy=identity(energy),plan=identity(plan),profiled=None if profiled is None else identity(profiled)),
        physical_calibration_qualified=False,automatic_actuation=False)
    value['inputs_sha256']=identity(value)
    if len(canonical(value))>16*1024**2:raise ValueError('bounded original component household inputs required')
    guard();return value
