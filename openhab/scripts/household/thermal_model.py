"""Prepare verified originals once, then project over immutable numerical inputs.

Preparation reuses the existing complete provisional origin validator, including
original files. Projection never rereads files, SQL or mutable OpenHAB state.
The preserved provisional forecast grants no action-effect or release authority.
"""
from dataclasses import dataclass,asdict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from .codec import canonical,loads,identity
from .evidence import EvidenceRef,Observation,digest
from .snapshot import build_snapshot
from thermal_model.installed_shade_dynamics import InstalledShadeDynamics,InstalledShadeForcing

FIELDS={'schema','original_capture_sha256','artifact_sha256','runtime_sha256','issue','initial','actions',
        'forcings','horizon_hours','coefficients','snapshot','executing_runtime','prepared_sha256'}
NATIVE_FIELDS=FIELDS|{'geometry','geometry_series_sha256','model_rule'}
CONDITIONED_FIELDS=NATIVE_FIELDS|{'weather_conditioning','inputs_available_at'}
NATIVE_SCHEMAS=('earthship-household-prepared-thermal/v2','earthship-household-prepared-thermal/v3')


# Frozen v1 contexts keep their original closure; v2 has its own closed reader contract.
PRODUCTION_CONDITIONING_SOURCES=(
    'production_thermal_source.py','household/production_weather_conditioning.py','thermal_weather_source.py',
    'household/thermal_weather_conditioning.py','household/codec.py','household/control_contracts.py',
    'weather_learning/production_emissions.py','weather_learning/production_forecast.py','weather_learning/production_scoring.py',
    'weather_learning/contracts.py','weather_learning/provider.py','weather_source_files.py')


def _execution_sources(conditioned,*,production=False):
    if production:
        return tuple(sorted(set(EXECUTION_SOURCES)|set(PRODUCTION_CONDITIONING_SOURCES)))
    if conditioned:
        from thermal_weather_source import RUNTIME_SOURCES
        return tuple(sorted(set(EXECUTION_SOURCES)|set(RUNTIME_SOURCES)))
    return EXECUTION_SOURCES
EXECUTION_SOURCES=('household/__init__.py','household/thermal_model.py','household/codec.py','household/evidence.py','household/snapshot.py')
ROLES={'air':'air_temperature','mass':'mass_temperature','outdoor':'outdoor_temperature'}


def _at(value):return datetime.fromisoformat(value)


@dataclass(frozen=True)
class PreparedProjection:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>262144:raise ValueError('bounded frozen thermal inputs required')
        value=loads(self.content)
        if not isinstance(value,dict):raise ValueError('closed prepared thermal object required')
        native=value.get('schema') in NATIVE_SCHEMAS
        conditioned=value.get('schema')==NATIVE_SCHEMAS[1]
        if (set(value)!=(CONDITIONED_FIELDS if conditioned else NATIVE_FIELDS if native else FIELDS) or
                value['schema'] not in ('earthship-household-prepared-thermal/v1',*NATIVE_SCHEMAS)):
            raise ValueError('closed prepared thermal context required')
        if native:_native_prepared(value)
        if identity({key:item for key,item in value.items() if key!='prepared_sha256'})!=value['prepared_sha256']:
            raise ValueError('prepared thermal context changed')
        for key in ('original_capture_sha256','artifact_sha256','runtime_sha256'):digest(value[key])

    def to_dict(self):return loads(self.content)


def _execution_runtime(root):
    from thermal_model.native_operational_io import RUNTIME_PATHS
    from thermal_model.origin_capture import build_runtime_binding,_source_bytes
    paths=EXECUTION_SOURCES
    manifest={name:sha256(_source_bytes(root/name,maximum=262144)).hexdigest() for name in paths}
    thermal=build_runtime_binding(root,sorted(RUNTIME_PATHS))
    for name,expected in manifest.items():
        if sha256(_source_bytes(root/name,maximum=262144)).hexdigest()!=expected:raise ValueError('household model source changed during binding')
    return dict(schema='earthship-household-model-runtime/v1',thermal_runtime=thermal,household_source_manifest=manifest)


def prepare_projection(capture,*,code_revision):
    """Verify retained original sources at the collection boundary, not mid-plan."""
    from thermal_model.provisional_forecast import validate_capture
    from thermal_model.installed_shade_origin import _origin_actions,_forecast_forcing
    from thermal_model.origin_capture import _temperatures
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    executing_runtime=_execution_runtime(root)
    original=validate_capture(capture)
    issue=_at(original['issued_at']);published=_at(original['published_at']);available=_at(original['inputs_available_at'])
    inputs=original['inputs'];candidate=original['candidate']
    _,initial=_temperatures(inputs['origin_temperatures'],inputs['current'],issued_at=issue,published_at=published,version=2)
    actions=_origin_actions(inputs['action_snapshot'],issue)
    forcings=_forecast_forcing(inputs['forecast'],issue,available,actions)
    observations=[]
    for role,name in ROLES.items():
        source=inputs['origin_temperatures']['roles'][role];receipt=source['grid'][-1][1]
        ref=EvidenceRef(name,'Weather_Temperature_Evidence_JSON:'+source['identity']['stream'],receipt['snapshotSha256'],
            receipt['streamEpoch'],receipt['sensorEpoch'],None,_at(receipt['receivedAt']),_at(receipt['storedAt']),
            _at(receipt['validUntil']),issue,'qualified',None,(original['capture_sha256'],))
        observations.append(Observation(ref,receipt['temperatureF'],'degF'))
    policy=dict(requirements={'thermal_current':list(ROLES.values())},max_age_seconds={role:120 for role in ROLES.values()},max_skew_seconds=120)
    snapshot=build_snapshot(observations,as_of=issue,created_at=published,code_revision=code_revision,config_revision=identity(policy),**policy)
    value=dict(schema='earthship-household-prepared-thermal/v1',original_capture_sha256=original['capture_sha256'],
        artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],issue=issue.isoformat(),
        initial=initial,actions=actions,forcings=[asdict(row) for row in forcings],horizon_hours=inputs['forecast']['horizon_hours'],
        coefficients=list(candidate['fit']['coefficients']),snapshot=snapshot.to_dict(),executing_runtime=executing_runtime)
    value['prepared_sha256']=identity(value)
    prepared=PreparedProjection(canonical(value))
    if canonical(project(prepared)['output'])!=canonical(original['output']):raise ValueError('frozen projection differs from original production forecast')
    if canonical(_execution_runtime(root))!=canonical(executing_runtime):raise ValueError('executing projection runtime changed during preparation')
    return prepared


def project(prepared):
    """Pure deterministic math; original qualification happened before freezing."""
    if not isinstance(prepared,PreparedProjection):raise ValueError('frozen original thermal context required')
    value=prepared.to_dict()
    if value['schema'] in NATIVE_SCHEMAS:return _project_native(value)
    initial=value['initial']
    forcings=tuple(InstalledShadeForcing(**{**row,'at':_at(row['at'])}) for row in value['forcings'])
    model=InstalledShadeDynamics(tuple(value['coefficients']))
    rolled=model.rollout(origin_at=_at(value['issue']),air_f=initial['air'],mass_f=initial['mass'],forcings=forcings)
    trajectory=[dict(at=row.at.isoformat(),air_f=state[0],mass_f=state[1]) for i,(row,state) in enumerate(zip(forcings,rolled.states),1) if i%12==0]
    output=dict(schema='earthship-provisional-thermal-forecast/v1',status='provisional',generated_at=value['issue'],
        artifact_sha256=value['artifact_sha256'],runtime_sha256=value['runtime_sha256'],horizon_hours=value['horizon_hours'],
        initial=dict(air_f=initial['air'],mass_f=initial['mass'],outdoor_f=initial['outdoor']),origin_actions=value['actions'],
        trajectory=trajectory,confidence='low',prediction_intervals=None,advice=[],graduated=False,automatic_actuation=False)
    result=dict(schema='earthship-household-thermal-projection/v1',snapshot=value['snapshot'],prepared_sha256=value['prepared_sha256'],
        original_capture_sha256=value['original_capture_sha256'],initial_mass_semantics='existing_latent_observer_state',
        output=output,executing_runtime_sha256=identity(value['executing_runtime']),action_effects_qualified=False,automatic_actuation=False)
    result['projection_sha256']=identity(result)
    return result


def _geometry(value):
    from astro_geometry_series import replay_series
    from astro_geometry import _instant
    packet=value['geometry']
    geometry=replay_series(canonical(packet),request=packet['request'],expected_series_sha256=value['geometry_series_sha256'],expected_native_runtime=packet['native_runtime'])
    if geometry.descriptor()['available_at'] and _instant(geometry.descriptor()['available_at'])>_instant(value['issue']):
        raise ValueError('native prepared geometry unavailable at issue')
    if packet['request']['instants']!=[row['at'] for row in value['forcings']]:
        raise ValueError('native prepared geometry differs from forcing grid')
    return geometry


def _native_prepared(value):
    from native_thermal_model import RULE
    from native_joint_shade import RULE as JOINT_RULE
    from native_thermal_artifact import validate_native_runtime,digest as native_digest
    from native_irradiance_shade import RULE as IRRADIANCE_RULE
    if value['model_rule'] not in (RULE,JOINT_RULE,IRRADIANCE_RULE):raise ValueError('native prepared model rule required')
    runtime=value['executing_runtime'];conditioned=value['schema']==NATIVE_SCHEMAS[1]
    if (not isinstance(runtime,dict) or set(runtime)!={'schema','thermal_runtime','household_source_manifest'} or
            runtime['schema']!=('earthship-household-model-runtime/v3' if conditioned else 'earthship-household-model-runtime/v2')):
        raise ValueError('native prepared execution runtime required')
    sources=runtime['household_source_manifest']
    production=conditioned and isinstance(value['weather_conditioning'],dict) and value['weather_conditioning'].get('schema')=='earthship-thermal-weather-context/v2'
    if not isinstance(sources,dict) or set(sources)!=set(_execution_sources(conditioned,production=production)):raise ValueError('complete native household source closure required')
    for sha in sources.values():digest(sha)
    validated=validate_native_runtime(runtime['thermal_runtime'])
    if native_digest(validated)!=value['runtime_sha256']:raise ValueError('native prepared runtime identity differs')
    _geometry(value)
    if conditioned:
        from .thermal_weather_conditioning import validate_context
        proof=validate_context(value['weather_conditioning'],issue=_at(value['issue']),available=_at(value['inputs_available_at']))
        if production:
            original=proof['runtime_manifest'];required=PRODUCTION_CONDITIONING_SOURCES
        else:
            from thermal_weather_source import RUNTIME_SOURCES
            original=proof['admission']['runtime_manifest'];required=RUNTIME_SOURCES
        if set(original)!=set(required) or any(sources.get(k)!=sha for k,sha in original.items()):raise ValueError('conditioned source admission differs from execution')


def _native_execution_runtime(root,runtime,guard,*,conditioned=False,production=False):
    from native_thermal_artifact import current_native_runtime,validate_native_runtime
    from thermal_model.origin_capture import _source_bytes
    expected=validate_native_runtime(runtime);guard()
    if canonical(current_native_runtime(guard=guard))!=canonical(expected):raise ValueError('native executing runtime differs from selected model')
    paths=_execution_sources(conditioned,production=production)
    manifest={name:sha256(_source_bytes(root/name,maximum=262144)).hexdigest() for name in paths}
    for name,sha in manifest.items():
        guard()
        if sha256(_source_bytes(root/name,maximum=262144)).hexdigest()!=sha:raise ValueError('native household source changed during preparation')
    if canonical(current_native_runtime(guard=guard))!=canonical(expected):raise ValueError('native executing runtime changed during preparation')
    return dict(schema='earthship-household-model-runtime/v3' if conditioned else 'earthship-household-model-runtime/v2',thermal_runtime=expected,household_source_manifest=manifest)


def _prepare_native_projection(capture,*,code_revision,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget,capture_validator):
    from pathlib import Path
    from astro_geometry import _instant
    from native_thermal_forecast import validate_capture
    from thermal_model.installed_shade_origin import _origin_actions,_forecast_forcing
    from thermal_model.origin_capture import _temperatures
    capture,runtime=map(deepcopy,(capture,runtime));root=Path(__file__).resolve().parents[1]
    conditioned=capture.get('schema')=='earthship-provisional-thermal-origin/v3'
    production=conditioned and isinstance(capture.get('weather_conditioning'),dict) and capture['weather_conditioning'].get('schema')=='earthship-thermal-weather-context/v2'
    execution=_native_execution_runtime(root,runtime,check_budget,conditioned=conditioned,production=production)
    original=capture_validator(capture,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    issue,published,available=map(_instant,(original['issued_at'],original['published_at'],original['inputs_available_at']))
    inputs=original['inputs'];candidate=original['candidate']
    _,initial=_temperatures(inputs['origin_temperatures'],inputs['current'],issued_at=issue,published_at=published,version=2)
    actions=_origin_actions(inputs['action_snapshot'],issue,allow_removed=candidate['fit']['model_rule'] in ('earthship-native-joint-shade-dynamics/v3','earthship-native-irradiance-shade-dynamics/v4'));forcings=_forecast_forcing(inputs['forecast'],issue,available,actions)
    observations=[]
    for role,name in ROLES.items():
        source=inputs['origin_temperatures']['roles'][role];receipt=source['grid'][-1][1]
        ref=EvidenceRef(name,'Weather_Temperature_Evidence_JSON:'+source['identity']['stream'],receipt['snapshotSha256'],
            receipt['streamEpoch'],receipt['sensorEpoch'],None,_instant(receipt['receivedAt']),_instant(receipt['storedAt']),
            _instant(receipt['validUntil']),issue,'qualified',None,(original['capture_sha256'],))
        observations.append(Observation(ref,receipt['temperatureF'],'degF'))
    policy=dict(requirements={'thermal_current':list(ROLES.values())},max_age_seconds={role:120 for role in ROLES.values()},max_skew_seconds=120)
    snapshot=build_snapshot(observations,as_of=issue,created_at=published,code_revision=code_revision,config_revision=identity(policy),**policy)
    value=dict(schema='earthship-household-prepared-thermal/v2',original_capture_sha256=original['capture_sha256'],
        artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],issue=issue.isoformat(),initial=initial,
        actions=actions,forcings=[asdict(row) for row in forcings],horizon_hours=inputs['forecast']['horizon_hours'],
        coefficients=list(candidate['fit']['coefficients']),snapshot=snapshot.to_dict(),executing_runtime=execution,
        geometry=original['geometry'],geometry_series_sha256=original['geometry_series_sha256'],model_rule=original['output']['model_rule'])
    if conditioned:value.update(schema=NATIVE_SCHEMAS[1],weather_conditioning=original['weather_conditioning'],inputs_available_at=original['inputs_available_at'])
    value['prepared_sha256']=identity(value);prepared=PreparedProjection(canonical(value))
    if canonical(project(prepared)['output'])!=canonical(original['output']):raise ValueError('native frozen projection differs from original forecast')
    if canonical(_native_execution_runtime(root,runtime,check_budget,conditioned=conditioned,production=production))!=canonical(execution):raise ValueError('native executing source closure changed')
    check_budget();return prepared



def prepare_native_projection(capture,*,code_revision,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    from native_thermal_forecast import validate_capture
    return _prepare_native_projection(capture,code_revision=code_revision,runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,
        check_budget=check_budget,capture_validator=validate_capture)


def prepare_serving_native_projection(capture,model,*,code_revision,expected_capture_sha256,check_budget=lambda:None):
    from native_model_serving_receipt import _require_model
    from native_thermal_forecast import validate_serving_capture
    _require_model(model)
    capture=deepcopy(capture)
    candidate=model.candidate
    def verified(value,*,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget):
        if canonical(runtime)!=canonical(model.runtime) or expected_artifact_sha256!=candidate['artifact_sha256']:
            raise ValueError('verified household serving model differs')
        return validate_serving_capture(value,model,expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    return _prepare_native_projection(capture,code_revision=code_revision,runtime=model.runtime,
        expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=expected_capture_sha256,
        check_budget=check_budget,capture_validator=verified)


def _project_native(value):
    from native_thermal_model import NativeInstalledShadeDynamics
    from native_joint_shade import NativeJointShadeDynamics,RULE as JOINT_RULE
    from astro_geometry import _instant
    geometry=_geometry(value);initial=value['initial']
    forcings=tuple(InstalledShadeForcing(**{**row,'at':_instant(row['at'])}) for row in value['forcings'])
    if value['schema']==NATIVE_SCHEMAS[1]:
        from .thermal_weather_conditioning import apply_conditioning
        forcings=apply_conditioning(forcings,value['weather_conditioning'],issue=_instant(value['issue']),available=_instant(value['inputs_available_at']),initial_outdoor_f=initial['outdoor'])
    from native_irradiance_shade import NativeIrradianceShadeDynamics,RULE as IRRADIANCE_RULE
    model_type=NativeIrradianceShadeDynamics if value['model_rule']==IRRADIANCE_RULE else NativeJointShadeDynamics if value['model_rule']==JOINT_RULE else NativeInstalledShadeDynamics
    model=model_type(tuple(value['coefficients']),geometry=geometry,expected_series_sha256=value['geometry_series_sha256'])
    rolled=model.rollout(origin_at=_instant(value['issue']),air_f=initial['air'],mass_f=initial['mass'],forcings=forcings)
    trajectory=[dict(at=row.at.isoformat(),air_f=state[0],mass_f=state[1]) for i,(row,state) in enumerate(zip(forcings,rolled.states),1) if i%12==0]
    output=dict(schema='earthship-provisional-thermal-forecast/v2',status='provisional',generated_at=value['issue'],
        artifact_sha256=value['artifact_sha256'],runtime_sha256=value['runtime_sha256'],model_rule=value['model_rule'],geometry_series_sha256=value['geometry_series_sha256'],
        horizon_hours=value['horizon_hours'],initial=dict(air_f=initial['air'],mass_f=initial['mass'],outdoor_f=initial['outdoor']),origin_actions=value['actions'],
        trajectory=trajectory,confidence='low',prediction_intervals=None,advice=[],graduated=False,automatic_actuation=False)
    result=dict(schema='earthship-household-thermal-projection/v2',snapshot=value['snapshot'],prepared_sha256=value['prepared_sha256'],
        original_capture_sha256=value['original_capture_sha256'],initial_mass_semantics='existing_latent_observer_state',output=output,
        executing_runtime_sha256=identity(value['executing_runtime']),action_effects_qualified=False,automatic_actuation=False)
    result['projection_sha256']=identity(result);return result
