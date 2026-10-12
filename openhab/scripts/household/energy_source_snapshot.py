"""Declared bank parameters and topology-bound AC load share one frozen clock."""
from dataclasses import dataclass
from .codec import canonical,loads,identity
from .control_contracts import instant
from .snapshot import HouseholdSnapshot
from .model_snapshot import MAX_SOURCE_BYTES
from .weather_snapshot import WeatherSnapshot,bind_weather_snapshot
from .weather_context import PreparedWeatherContext,MAX_BYTES as MAX_WEATHER_BYTES
from .energy_configuration import PreparedEnergyConfiguration,project_energy_configuration,MAX_BYTES

CONTEXT_SCHEMA='earthship-household-energy-source-context/v1'


def _configuration_row(role,value,unit,configuration,projection):
    original=configuration.to_dict();source=original['bank_source'];bank=projection['bank']
    reason=bank['reason'] if bank['status']=='unavailable' else 'nominal_capacity_unavailable' if value is None else None
    return dict(value=value,unit=unit,reason=reason,evidence=dict(source_role=role,source_identity=source['source_identity'],
        digest=source['sha256'],source_epoch=None,hardware_epoch=None,observed_at=None,received_at=source['available_at'],
        available_at=source['available_at'],valid_until=bank.get('effective_until'),assessed_at=projection['as_of'],
        quality='retained_configuration_context',reason=reason,parent_digests=[original['configuration_sha256']]))


def _render(source,weather,configuration,revision):
    original=bind_weather_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],weather_context=weather,code_revision=revision)
    doc=original.to_dict();base_id=doc.pop('snapshot_id');at=instant(doc['as_of'])
    doc['created_at']=max(instant(doc['created_at']),instant(configuration.to_dict()['created_at'])).isoformat()
    projection=project_energy_configuration(configuration,as_of=at);bank=projection['bank'];topology=projection['load_topology']
    energy=doc['domains']['energy']
    energy['physical_bank_epoch']=_configuration_row('physical_bank_epoch',bank.get('epoch_id'),'identity',configuration,projection)
    energy['nominal_bank_kwh']=_configuration_row('nominal_bank_kwh',bank.get('nominal_usable_kwh'),'kWh',configuration,projection)
    energy['nominal_bank_capacity_ah']=_configuration_row('nominal_bank_capacity_ah',bank.get('nominal_capacity_ah'),'Ah',configuration,projection)
    ac=energy['inverter_output_w'];load=loads(canonical(ac));ref=load['evidence']
    load['basis']=topology.get('basis')
    if ref is not None:
        original_digest=ref['digest']
        ref['source_role']='estimated_load_w'
        ref['parent_digests']=list(dict.fromkeys([*ref['parent_digests'],*([original_digest] if original_digest is not None else []),projection['configuration_sha256']]))
        if topology['status']=='attested' and topology['effective_until'] is not None and ref['valid_until'] is not None:
            ref['valid_until']=min(instant(ref['valid_until']),instant(topology['effective_until'])).isoformat()
        ref['digest']=None if original_digest is None else identity(dict(source_role='estimated_load_w',original_inverter_evidence_sha256=original_digest,
            configuration_sha256=projection['configuration_sha256'],topology=topology,valid_until=ref['valid_until']))
    if topology['status']!='attested':load.update(value=None,reason=topology['reason'])
    elif ac['value'] is None or ac['reason'] is not None or ref is None or ref['quality']!='qualified':
        load.update(value=None,reason=ac['reason'] or 'source_unqualified')
    elif (ref['observed_at'] is None or instant(ref['observed_at'])<instant(topology['effective_from']) or
          instant(ref['observed_at'])<instant(topology['cutover']) or
          topology['effective_until'] is not None and instant(ref['observed_at'])>=instant(topology['effective_until'])):
        load.update(value=None,reason='observation_outside_topology')
    if ref is not None and load['value'] is None:
        ref.update(quality='unavailable',reason=load['reason'])
    energy['estimated_load_w']=load
    ages=doc['temporal_policy']['max_age_seconds']
    if 'inverter_output_w' in ages:ages['estimated_load_w']=ages['inverter_output_w']
    doc['temporal_policy']['requirements']['household_ac_load']=['estimated_load_w']
    complete=load['value'] is not None and load['reason'] is None
    doc['completeness']['household_ac_load']=complete
    doc['capability_reasons']['household_ac_load']=None if complete else 'required_source_unavailable'
    doc.update(schema='earthship-household-snapshot/v5',base_weather_snapshot_id=base_id,
        energy_configuration_sha256=projection['configuration_sha256'],energy_configuration_context=projection,
        energy_configuration_scope='original_declared_bank_and_attested_ac_topology')
    # The new policy's identity covers its added load requirement, not a bank calibration.
    doc['config_revision']=identity(doc['temporal_policy'])
    return doc


@dataclass(frozen=True)
class EnergySourceSnapshot(WeatherSnapshot):
    original_energy_configuration:bytes

    def __post_init__(self):
        HouseholdSnapshot.__post_init__(self)
        for data,maximum in ((self.original_source,MAX_SOURCE_BYTES),(self.original_weather,MAX_WEATHER_BYTES),(self.original_energy_configuration,MAX_BYTES)):
            if not isinstance(data,bytes) or len(data)>maximum:raise ValueError('bounded immutable original energy sources required')
        doc=loads(self.content)
        if doc.get('schema')!='earthship-household-snapshot/v5' or doc.get('planner_authority')!='none':raise ValueError('original energy-source snapshot required')
        weather=PreparedWeatherContext(self.original_weather);configuration=PreparedEnergyConfiguration(self.original_energy_configuration)
        if canonical(_render(loads(self.original_source),weather,configuration,doc['code_revision']))!=self.content:
            raise ValueError('original energy-source snapshot differs')

    @property
    def energy_configuration(self):return PreparedEnergyConfiguration(self.original_energy_configuration)

    @property
    def source_context(self):return dict(schema=CONTEXT_SCHEMA,power_receipt=self.source_receipt,
        weather_inputs=self.weather.to_dict(),energy_configuration=self.energy_configuration.to_dict())


def bind_energy_source_snapshot(*,source_receipt,source_runtime_manifest,weather_context,energy_configuration,code_revision):
    if not isinstance(weather_context,PreparedWeatherContext) or not isinstance(energy_configuration,PreparedEnergyConfiguration):
        raise ValueError('original prepared weather and configuration required')
    from .power_snapshot import replay_power_snapshot
    source=replay_power_snapshot(source_receipt,runtime_manifest=source_runtime_manifest)
    return EnergySourceSnapshot(canonical(_render(source,weather_context,energy_configuration,code_revision)),
        canonical(source),canonical(weather_context.to_dict()),canonical(energy_configuration.to_dict()))


def restore_energy_source_snapshot(document,context):
    if (not isinstance(context,dict) or set(context)!={'schema','power_receipt','weather_inputs','energy_configuration'} or
        context['schema']!=CONTEXT_SCHEMA):raise ValueError('closed original energy source context required')
    value=EnergySourceSnapshot(canonical({k:v for k,v in document.items() if k!='snapshot_id'}),
        canonical(context['power_receipt']),canonical(context['weather_inputs']),canonical(context['energy_configuration']))
    if value.snapshot_id!=document['snapshot_id']:raise ValueError('original energy source snapshot identity differs')
    return value
