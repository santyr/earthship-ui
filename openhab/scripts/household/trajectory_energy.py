"""Snapshot-bound Google/PV energy planning; historical daily arithmetic stays separate."""
from dataclasses import dataclass
from .codec import canonical, loads, identity
from .control_contracts import instant
from .evidence import utc, digest

SCHEMA='earthship-household-prepared-trajectory-energy/v1'
FIELDS={'schema','snapshot_id','as_of','available_at','system_source','topology_source','horizon_source'}
RUNTIME_ROOTS=('household_energy_forecast.py','household_pv_model.py','household_solar_horizon.py','household_outcomes.py')


@dataclass(frozen=True)
class PreparedTrajectoryInputs:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>131072:raise ValueError('bounded trajectory energy inputs required')
        value=loads(self.content)
        if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:raise ValueError('closed trajectory energy inputs required')
        digest(value['snapshot_id'])
        if instant(value['available_at'])<instant(value['as_of']):raise ValueError('trajectory energy precedes shared snapshot')
        if any(value[k] is not None and not isinstance(value[k],dict) for k in ('system_source','topology_source','horizon_source')):
            raise ValueError('original configuration source or explicit absence required')

    def to_dict(self):return loads(self.content)


def prepare_inputs(*,snapshot,system_source,topology_source,horizon_source):
    from .energy_source_snapshot import EnergySourceSnapshot
    if not isinstance(snapshot,EnergySourceSnapshot) or snapshot.weather.original_capture['inputs']['forecast']['source']!='weathernext3':
        raise ValueError('Google-only configured weather snapshot required')
    doc=snapshot.to_dict()
    return PreparedTrajectoryInputs(canonical(dict(schema=SCHEMA,snapshot_id=snapshot.snapshot_id,
        as_of=doc['as_of'],available_at=doc['created_at'],system_source=system_source,
        topology_source=topology_source,horizon_source=horizon_source)))


def project(inputs,*,snapshot,now):
    from household_pv_model import project_pv
    from household_energy_forecast import _storage
    from .power_flows import project_power_flows
    if not isinstance(inputs,PreparedTrajectoryInputs):raise ValueError('prepared Google trajectory inputs required')
    original=inputs.to_dict();doc=snapshot.to_dict();now=utc(now)
    if original['snapshot_id']!=snapshot.snapshot_id or original['as_of']!=doc['as_of'] or original['available_at']!=doc['created_at'] or instant(original['available_at'])>now:
        raise ValueError('trajectory energy origin differs from shared snapshot')
    if snapshot.weather.original_capture['inputs']['forecast']['source']!='weathernext3':raise ValueError('original Google weather required')
    pv=project_pv(weather=snapshot.weather,system_source=original['system_source'],horizon_source=original['horizon_source'],now=now)
    flows=project_power_flows(snapshot=snapshot,topology_source=original['topology_source'],now=now)
    storage=_storage(snapshot,pv,flows,original['topology_source'],now)
    available=storage['status']=='conditional_nominal_simulation';rows=storage['trajectory']
    initial=storage.get('initial_soc_pct')
    output=dict(status=storage['status'],reason=storage['reason'],origin=pv['origin'],horizon_hours=24,
        target='rolling_24h_nominal_storage_not_complete_next_night',confidence='low',
        minimum_nominal_soc_pct=min(initial,*(r['nominal_soc_pct'] for r in rows)) if available else None,
        final_nominal_soc_pct=rows[-1]['nominal_soc_pct'] if available else None,
        potential_pv_kwh=pv['potential_pv_kwh'],modeled_captured_pv_kwh=storage.get('modeled_captured_pv_kwh'),
        modeled_unaccepted_pv_kwh=storage.get('modeled_unaccepted_pv_kwh'),trajectory=rows,
        physical_calibration_qualified=False,action_effects_qualified=False,automatic_actuation=False)
    result=dict(schema='earthship-household-trajectory-energy-projection/v1',inputs_sha256=identity(original),
        collection_binding={k:original[k] for k in ('snapshot_id','as_of','available_at')},output=output,
        input_qualification='conditional_uncalibrated_scenario',action_effects_qualified=False,automatic_actuation=False)
    result['projection_sha256']=identity(result);return loads(canonical(result))
