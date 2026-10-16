"""Original receiver points extend the frozen bank/model state without effects."""
from dataclasses import dataclass
from .codec import canonical,loads,identity
from .control_contracts import instant
from .snapshot import HouseholdSnapshot
from .model_snapshot import MAX_SOURCE_BYTES
from .weather_context import PreparedWeatherContext,MAX_BYTES as WEATHER_BYTES
from .energy_configuration import PreparedEnergyConfiguration,MAX_BYTES as CONFIGURATION_BYTES
from .energy_source_snapshot import EnergySourceSnapshot
from .measured_weather import PreparedMeasuredWeather,project_measured_weather,MAX_BYTES,ROLES,_policy

CONTEXT_SCHEMA='earthship-household-measured-source-context/v1'
CAPABILITIES={'radiation_proxy_display':['light_lux','solar_radiation_proxy_wm2'],'rain_counter_display':['rain_counter_in']}


def _render(source,weather,configuration,measured,revision):
    from .energy_source_snapshot import _render as render_energy
    base=HouseholdSnapshot(canonical(render_energy(source,weather,configuration,revision)))
    doc=base.to_dict();base_id=doc.pop('snapshot_id');at=instant(doc['as_of'])
    projection=project_measured_weather(measured,as_of=at)
    doc['created_at']=max(instant(doc['created_at']),instant(measured.to_dict()['created_at'])).isoformat()
    doc['domains']['weather'].update(projection['observations'])
    originals=measured.to_dict()['sources'];ages=doc['temporal_policy']['max_age_seconds']
    for kind,roles in ROLES.items():
        try:age=_policy(kind,originals[kind]['policy_raw']).validity_seconds
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError):continue
        for role,_,_ in roles:ages[role]=age
    for capability,roles in CAPABILITIES.items():
        complete=all(projection['observations'][role]['value'] is not None and projection['observations'][role]['reason'] is None for role in roles)
        doc['temporal_policy']['requirements'][capability]=roles
        doc['completeness'][capability]=complete
        doc['capability_reasons'][capability]=None if complete else 'required_source_unavailable'
    doc.update(schema='earthship-household-snapshot/v6',base_energy_source_snapshot_id=base_id,
        measured_weather_sha256=projection['measured_weather_sha256'],measured_weather_context=projection,
        measured_weather_scope='original_receiver_proxy_and_cumulative_counter')
    doc['config_revision']=identity(doc['temporal_policy'])
    return doc


@dataclass(frozen=True)
class MeasuredWeatherSnapshot(EnergySourceSnapshot):
    original_measured_weather:bytes

    def __post_init__(self):
        HouseholdSnapshot.__post_init__(self)
        for data,maximum in ((self.original_source,MAX_SOURCE_BYTES),(self.original_weather,WEATHER_BYTES),
            (self.original_energy_configuration,CONFIGURATION_BYTES),(self.original_measured_weather,MAX_BYTES)):
            if not isinstance(data,bytes) or len(data)>maximum:raise ValueError('bounded immutable original measured sources required')
        doc=loads(self.content)
        if doc.get('schema')!='earthship-household-snapshot/v6' or doc.get('planner_authority')!='none':raise ValueError('original measured-weather snapshot required')
        expected=_render(loads(self.original_source),PreparedWeatherContext(self.original_weather),
            PreparedEnergyConfiguration(self.original_energy_configuration),self.measured_weather,doc['code_revision'])
        if canonical(expected)!=self.content:raise ValueError('original measured-weather snapshot differs')

    @property
    def measured_weather(self):return PreparedMeasuredWeather(self.original_measured_weather)

    @property
    def source_context(self):return dict(schema=CONTEXT_SCHEMA,power_receipt=self.source_receipt,
        weather_inputs=self.weather.to_dict(),energy_configuration=self.energy_configuration.to_dict(),measured_weather=self.measured_weather.to_dict())


def bind_measured_weather_snapshot(*,source_receipt,source_runtime_manifest,weather_context,energy_configuration,measured_weather,code_revision):
    if not isinstance(measured_weather,PreparedMeasuredWeather):raise ValueError('original prepared measured weather required')
    from .power_snapshot import replay_power_snapshot
    source=replay_power_snapshot(source_receipt,runtime_manifest=source_runtime_manifest)
    return MeasuredWeatherSnapshot(canonical(_render(source,weather_context,energy_configuration,measured_weather,code_revision)),
        canonical(source),canonical(weather_context.to_dict()),canonical(energy_configuration.to_dict()),canonical(measured_weather.to_dict()))


def restore_measured_weather_snapshot(document,context):
    if (not isinstance(context,dict) or set(context)!={'schema','power_receipt','weather_inputs','energy_configuration','measured_weather'} or
        context['schema']!=CONTEXT_SCHEMA):raise ValueError('closed original measured-weather context required')
    value=MeasuredWeatherSnapshot(canonical({k:v for k,v in document.items() if k!='snapshot_id'}),canonical(context['power_receipt']),
        canonical(context['weather_inputs']),canonical(context['energy_configuration']),canonical(context['measured_weather']))
    if value.snapshot_id!=document['snapshot_id']:raise ValueError('original measured-weather snapshot identity differs')
    return value
