"""Optional original-bound physical observations alongside canonical household state.

No live reader, model invocation, forecast training or action interface. Existing
snapshot/model schemas remain unchanged and do not consume this extension.
"""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from .codec import canonical,loads,identity
from .evidence import utc,epoch,digest
from .snapshot import HouseholdSnapshot

MAX_BYTES=262144


def _prepare(registry_raw,registry_sha256,sources,as_of,collector_raw=None,collector_sha256=None):
    from services.observations.registry import Registry
    from services.observations.contract import instant,measurement
    as_of=utc(as_of)
    if not isinstance(registry_raw,str) or len(registry_raw.encode())>65536 or sha256(registry_raw.encode()).hexdigest()!=digest(registry_sha256):
        raise ValueError('bounded exact original registry required')
    registry=Registry(loads(registry_raw))
    if not isinstance(sources,dict) or len(sources)>256:raise ValueError('bounded original observation sources required')
    collector=None
    if collector_raw is not None:
        if not isinstance(collector_raw,str) or len(collector_raw.encode())>131072 or sha256(collector_raw.encode()).hexdigest()!=digest(collector_sha256):
            raise ValueError('exact current collector supervision required')
        collector=loads(collector_raw)
        if collector.get('schema')!='earthship-sensor-view/v1' or collector.get('authority')!='observation_only':
            raise ValueError('collector supervision schema required')
        if instant(collector['generated_at'])>as_of:raise ValueError('future collector supervision refused')
        if collector.get('registry_sha256')!=registry.sha256:raise ValueError('collector registry binding differs')
        if not instant(collector['generated_at'])<instant(collector['expires_at'])<=instant(collector['generated_at'])+timedelta(seconds=45):raise ValueError('bounded collector validity required')
    elif collector_sha256 is not None:raise ValueError('absent collector cannot claim digest')
    observations={}
    expected_keys={device['sensor_id']+':'+kind for device in registry.devices.values() if device['enabled'] for kind in device['observation_types']}
    if set(sources)-expected_keys:raise ValueError('unregistered source refused')
    for device in registry.devices.values():
        if not device['enabled']:continue
        for kind in device['observation_types']:
            key=device['sensor_id']+':'+kind;source=sources.get(key);point=None;reason='missing_source'
            if source is not None:
                if set(source)!={'raw','sha256','available_at','expected_source_epoch'}:
                    raise ValueError('closed original source binding required')
                available=instant(source['available_at']);epoch(source['expected_source_epoch'])
                if available>as_of:raise ValueError('future source availability refused')
                raw=source['raw']
                if not isinstance(raw,str) or len(raw.encode())>8192 or sha256(raw.encode()).hexdigest()!=digest(source['sha256']):
                    raise ValueError('exact normalized original required')
                point=loads(raw)
                if (point.get('schema')!='earthship-observation/v1' or point.get('sensor_id')!=device['sensor_id'] or
                    point.get('device_id')!=device['device_id'] or point.get('transport')!=device['transport'] or point.get('observation_type')!=kind):
                    raise ValueError('registered source identity/type required')
                measurement(kind,point['value'],point['unit'])
                provenance=point['provenance'];digest(provenance['raw_sha256']);epoch(provenance['source_epoch']);epoch(provenance['hardware_epoch'])
                received=instant(point['received_at']);until=instant(point['valid_until'])
                observed=None if point['observed_at'] is None else instant(point['observed_at'])
                if received>available or received>as_of or (observed is not None and observed>received):reason='future_source'
                elif point.get('synthetic') is not False or registry.config['environment']=='simulation':reason='synthetic_source'
                elif point.get('quality')!='qualified' or not device['source_verified']:reason='unqualified_source'
                elif provenance['hardware_epoch']!=device['hardware_epoch'] or provenance['source_epoch']!=source['expected_source_epoch']:reason='wrong_epoch'
                elif as_of>=until or until>(observed or received)+timedelta(seconds=device['state_stale_seconds']):reason='expired_or_excess_validity'
                elif point.get('timestamp_basis') not in ('device_clock','network_reception','provider_receipt'):reason='unknown_timestamp_basis'
                else:reason=None
                if reason is None and device['transport']=='lorawan':
                    current=None if collector is None else next((s for s in collector['sensors'] if s['sensor_id']==device['sensor_id']),None)
                    if (current is None or collector.get('environment')!='production' or
                        as_of>=instant(collector['expires_at']) or not current.get('valid') or
                        current.get('quality')!='qualified' or current.get('health')!='ONLINE' or
                        current.get('last_received_at') is None or instant(current['last_received_at'])>as_of or
                        as_of>=instant(current['last_received_at'])+timedelta(seconds=device['communication_stale_seconds']) or
                        current.get('source_epoch')!=provenance['source_epoch'] or
                        current.get('hardware_epoch')!=provenance['hardware_epoch'] or
                        current.get('last_observed_at')!=point['observed_at'] or
                        (kind=='contact_state' and current.get('current_state')!=point['value'])):
                        reason='supervision_unavailable'
                    elif collector.get('normalized_observations',{}).get(key)!=point:
                        reason='collector_observation_differs'
            ref=None if point is None else dict(source_role=kind,source_identity=point['source_identity'],
                digest=source['sha256'],source_epoch=point['provenance']['source_epoch'],hardware_epoch=device['hardware_epoch'],
                observed_at=point['observed_at'],received_at=point['received_at'],available_at=source['available_at'],
                valid_until=point['valid_until'],assessed_at=as_of.isoformat(),quality='qualified' if reason is None else 'unavailable',
                reason=reason,parent_digests=[point['provenance']['raw_sha256'],registry_sha256])
            observations[key]=dict(value=point['value'] if reason is None else None,unit=device['units'][kind],
                reason=reason,evidence=ref,sensor_id=device['sensor_id'],zone=device['zone'],device_type=device['device_type'])
    return dict(schema='earthship-prepared-sensor-observations/v1',registry_raw=registry_raw,registry_sha256=registry_sha256,
        sources=sources,collector_raw=collector_raw,collector_sha256=collector_sha256,as_of=as_of.isoformat(),observations=observations,authority='none')


@dataclass(frozen=True)
class PreparedSensorObservations:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded frozen sensor context required')
        value=loads(self.content)
        from services.observations.contract import instant
        expected=_prepare(value['registry_raw'],value['registry_sha256'],value['sources'],instant(value['as_of']),value['collector_raw'],value['collector_sha256'])
        if canonical(expected)!=self.content:raise ValueError('original observation replay differs')

    def to_dict(self):return loads(self.content)


def prepare_sensor_observations(*,registry_raw,registry_sha256,sources,as_of,collector_raw=None,collector_sha256=None):
    return PreparedSensorObservations(canonical(_prepare(registry_raw,registry_sha256,sources,as_of,collector_raw,collector_sha256)))


def _render(parent,prepared):
    from services.observations.contract import instant
    doc=parent.to_dict();parent_id=doc.pop('snapshot_id');at=instant(doc['as_of']);context=prepared.to_dict()
    # Reassess at the frozen parent clock. A prepared context never refreshes time.
    if instant(context['as_of'])>at:raise ValueError('sensor collection is later than frozen parent')
    assessed=_prepare(context['registry_raw'],context['registry_sha256'],context['sources'],at,context['collector_raw'],context['collector_sha256'])
    by_domain={name:{} for name in ('thermal','water','environment','security')}
    for key,row in assessed['observations'].items():
        kind=key.split(':',1)[1]
        if kind=='contact_state' and row['device_type'] in ('window','skylight','door'):
            by_domain['thermal'][row['sensor_id']]=row
        elif kind in ('water_depth','water_flow','water_counter','line_pressure','pump_runtime','leak'):
            by_domain['water'][key]=row
        elif kind in ('contact_state','tamper','motion'):
            by_domain['security'][key]=row
        else:by_domain['environment'][key]=row
    doc['domains']['thermal']['ventilation']=by_domain.pop('thermal')
    for domain,rows in by_domain.items():doc['domains'].setdefault(domain,{})['sensor_observations']=rows
    doc.update(schema='earthship-household-sensor-snapshot/v1',parent_snapshot_id=parent_id,
        sensor_context_sha256=identity(context),sensor_registry_sha256=context['registry_sha256'],sensor_authority='none')
    return doc


@dataclass(frozen=True)
class SensorObservationSnapshot(HouseholdSnapshot):
    parent_content:bytes
    prepared_content:bytes

    def __post_init__(self):
        HouseholdSnapshot.__post_init__(self)
        if canonical(_render(HouseholdSnapshot(self.parent_content),PreparedSensorObservations(self.prepared_content)))!=self.content:
            raise ValueError('sensor extension differs from frozen originals')


def attach_sensor_observations(snapshot,prepared,*,enabled=False):
    if type(enabled) is not bool:raise ValueError('explicit boolean opt-in required')
    if not enabled:return snapshot
    if not isinstance(snapshot,HouseholdSnapshot) or not isinstance(prepared,PreparedSensorObservations):raise ValueError('canonical frozen originals required')
    return SensorObservationSnapshot(canonical(_render(snapshot,prepared)),snapshot.content,prepared.content)
