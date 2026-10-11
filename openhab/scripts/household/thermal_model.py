"""Prepare verified originals once, then project over immutable numerical inputs.

Preparation reuses the existing complete provisional origin validator, including
original files. Projection never rereads files, SQL or mutable OpenHAB state.
The preserved provisional forecast grants no action-effect or release authority.
"""
from dataclasses import dataclass,asdict
from datetime import datetime
from hashlib import sha256
from .codec import canonical,loads,identity
from .evidence import EvidenceRef,Observation,digest
from .snapshot import build_snapshot
from thermal_model.installed_shade_dynamics import InstalledShadeDynamics,InstalledShadeForcing

FIELDS={'schema','original_capture_sha256','artifact_sha256','runtime_sha256','issue','initial','actions',
        'forcings','horizon_hours','coefficients','snapshot','executing_runtime','prepared_sha256'}
ROLES={'air':'air_temperature','mass':'mass_temperature','outdoor':'outdoor_temperature'}


def _at(value):return datetime.fromisoformat(value)


@dataclass(frozen=True)
class PreparedProjection:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>262144:raise ValueError('bounded frozen thermal inputs required')
        value=loads(self.content)
        if set(value)!=FIELDS or value['schema']!='earthship-household-prepared-thermal/v1':raise ValueError('closed prepared thermal context required')
        if identity({key:item for key,item in value.items() if key!='prepared_sha256'})!=value['prepared_sha256']:
            raise ValueError('prepared thermal context changed')
        for key in ('original_capture_sha256','artifact_sha256','runtime_sha256'):digest(value[key])

    def to_dict(self):return loads(self.content)


def _execution_runtime(root):
    from thermal_model.provisional_live import RUNTIME_PATHS
    from thermal_model.origin_capture import build_runtime_binding,_source_bytes
    paths=('household/__init__.py','household/thermal_model.py','household/codec.py','household/evidence.py','household/snapshot.py')
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
    value=prepared.to_dict();initial=value['initial']
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
