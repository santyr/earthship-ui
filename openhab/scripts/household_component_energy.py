"""Shared selected native-component PV into conditional nominal storage."""
from datetime import timedelta
from copy import deepcopy
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household_pv_model import simulate_storage
from household_profiled_storage import simulate_profiled_storage
from weather_learning.production_pv_runtime import ComponentOwner


def project(owner,*,forecast,positions,storage_inputs,load_forecast):
    if not isinstance(owner,ComponentOwner):raise ValueError('explicit selected component model owner required')
    origin=instant(forecast['origin']);owner.verify()
    window=owner.project(forecast=forecast,positions=positions,start=origin,end=origin+timedelta(hours=24))
    raw=window['raw_projection'];pv=window['projection'];initial=deepcopy(storage_inputs);reason=initial['reason']
    constant=dict(status='unavailable',reason=reason or initial['current_load_reason'])
    if constant['reason'] is None:
        constant=dict(simulate_storage(steps=pv['steps'],initial_soc_pct=initial['initial_soc_pct'],
            nominal_bank_kwh=initial['nominal_bank_kwh'],load_ac_w=initial['current_load_w']),status='conditional_nominal_simulation',reason=None)
    load_available=isinstance(load_forecast,dict) and load_forecast.get('status')=='projected'
    load_reason='load_model_unavailable' if load_forecast is None else load_forecast.get('reason') or 'load_model_unavailable'
    profiled=dict(status='unavailable',reason=reason or (None if load_available else load_reason));unadjusted=None
    if profiled['reason'] is None:
        if instant(load_forecast['origin'])!=origin:raise ValueError('same original component and learned-load origin required')
        args=dict(initial_soc_pct=initial['initial_soc_pct'],nominal_bank_kwh=initial['nominal_bank_kwh'],load_forecast=load_forecast)
        profiled=dict(simulate_profiled_storage(steps=pv['steps'],**args),status='conditional_nominal_simulation',reason=None)
        unadjusted=dict(simulate_profiled_storage(steps=raw['steps'],**args),status='conditional_nominal_simulation',reason=None)
    applied=pv['calibrated_segments']>0
    body=owner.body
    value=dict(status='projected_provisional_calibrated_potential',reason=None,issued_at=origin.isoformat(),
        raw_potential_kwh=raw['potential_pv_kwh'],calibrated_potential_kwh=pv['potential_pv_kwh'],steps=pv['steps'],
        constant_load_storage=constant,profiled_storage=profiled,uncalibrated_profiled_storage=unadjusted,storage_initial_conditions=initial,
        calibration_sha256=body['calibration_sha256'],calibration_model_sha256=body['model']['model_sha256'],
        calibration_policy_sha256=body['policy_sha256'],procedure_sha256=body['procedure_sha256'],baseline_rule=body['baseline_rule'],
        measurement_cohort_sha256=owner.context['measurement_cohort_sha256'],power_policy_sha256=owner.context['power_policy_sha256'],solar_grid_sha256=owner.context['solar_grid_sha256'],
        calibration_scope=pv['calibration_scope'],calibration_mode='experimental_production' if applied else 'raw_component_fallback',
        source_support=pv['source_support'],component_window=window,confidence='experimental_native_component_model',
        physical_calibration_qualified=False,automatic_actuation=False)
    value['output_sha256']=identity(value);owner.verify();return loads(canonical(value))


def project_inputs(owner,context):
    """Compile only the original producer's measured-availability snapshot."""
    from weather_learning.retained_scenarios import RetainedComponentInputs
    from weather_learning.native_forecast import _snapshot,_decode,make_native_component_forecast
    from weather_learning.config import Site
    if type(context) is not RetainedComponentInputs:raise ValueError('verified retained component inputs required')
    prepared=context.to_dict()['prepared']
    for field in ('system','horizon'):
        if prepared[field+'_source']['raw'].encode()!=owner.configurations[field+'_path'][1]:
            raise ValueError('same original household component physical configuration required')
    original=prepared['forecast']
    forcing=make_native_component_forecast(_snapshot(_decode(original['source_original'])),origin=instant(prepared['issued_at']),
        available_by=instant(original['available_by']),horizon_hours=original['horizon_hours'],site=Site(**original['site']))
    result=project(owner,forecast=forcing,positions=prepared['positions'],storage_inputs=prepared['storage_initial_conditions'],load_forecast=prepared['load_forecast'])
    return forcing,result
