"""Original forecast/operator context extends one common observational identity."""
from dataclasses import dataclass
from functools import cached_property
from datetime import timedelta
from .codec import canonical,loads,identity
from .snapshot import HouseholdSnapshot
from .model_snapshot import ModelSnapshot,MAX_SOURCE_BYTES
from .weather_context import PreparedWeatherContext,project_weather,MAX_BYTES
from .control_contracts import instant

CONTEXT_SCHEMA='earthship-household-weather-source-context/v1'


def _row(role,value,unit,context,*,operator=False):
    body=context.to_dict();capture=context.original_capture;forecast=capture['inputs']['forecast'];issue=instant(capture['issued_at'])
    digest=identity(capture['inputs']['action_snapshot']) if operator else forecast['rows_sha256']
    return dict(value=value,unit=unit,reason=None,evidence=dict(source_role=role,
        source_identity='retained_origin_operator_context' if operator else forecast['source'],digest=digest,
        source_epoch=None,hardware_epoch=None,observed_at=None,received_at=capture['inputs_available_at'],
        available_at=capture['inputs_available_at'],valid_until=(issue+timedelta(hours=body['prepared_thermal']['horizon_hours'])).isoformat(),
        assessed_at=capture['issued_at'],quality='retained_operator_context' if operator else 'retained_forecast_context',
        reason=None,parent_digests=[capture['capture_sha256'],body['weather_sha256']]))


def _geometry_row(value,*,capture,weather_sha256):
    return dict(value=value,unit='solar_position_trajectory',reason=None,evidence=dict(
        source_role='solar_geometry',source_identity=value['source_identity'],digest=value['series_sha256'],
        source_epoch=None,hardware_epoch=None,observed_at=None,received_at=value['available_at'],
        available_at=value['available_at'],valid_until=value['positions'][-1]['at'],
        assessed_at=capture['issued_at'],quality='retained_native_calculation',reason=None,
        parent_digests=[capture['capture_sha256'],weather_sha256,*value['cache_sha256s']]))


def _render(source,weather,revision):
    from .model_snapshot import _render as render_model,describe_thermal
    # The original model renderer validates source replay and descriptor.
    # Compose its bounded document rather than constructing an intermediate
    # ModelSnapshot which would render and validate the same originals again.
    base=HouseholdSnapshot(canonical(render_model(source,describe_thermal(weather.prepared),revision)))
    doc=base.to_dict();base_id=doc.pop('snapshot_id');projection=project_weather(weather);capture=weather.original_capture;forecast=capture['inputs']['forecast']
    domain=doc['domains']['weather'];actions=projection['origin_states']
    fields={
        'forecast_issue':(dict(issued_at=forecast['issued_at'],captured_at=forecast['captured_at'],rows_sha256=forecast['rows_sha256']),'identity'),
        'outdoor_trajectory':([dict(at=row['at'],temperature_f=row['outdoor_f']) for row in projection['forcings']],'degF_trajectory'),
        'radiation_trajectory':([dict(at=row['at'],radiation_wm2=row['radiation_wm2']) for row in projection['forcings']],'W_m2_trajectory'),
        'forecast_wind_trajectory':([dict(at=row['at'],wind_mph=row['windMph']) for row in projection['hourly_forecast']],'mph_trajectory'),
        'forecast_weather_codes':([dict(at=row['at'],weather_code=row['weatherCode']) for row in projection['hourly_forecast']],'code_trajectory')}
    for role,(value,unit) in fields.items():domain[role]=_row(role,value,unit,weather)
    if 'solar_geometry' in projection:
        domain['solar_geometry']=_geometry_row(projection['solar_geometry'],capture=capture,weather_sha256=projection['weather_context_sha256'])
    doc['domains']['thermal']['shade_state']=_row('shade_state',dict(indoor_closed=actions['indoor_shade_closed'],outdoor_present=actions['outdoor_shade_present'],actuator_position=None),'state',weather,operator=True)
    doc['domains']['thermal']['ventilation_state']=_row('ventilation_state',dict(legacy_coarse_open=actions['vent_open'],provenance=actions['vent_provenance'],window=None,skylight=None),'state',weather,operator=True)
    if actions['mode']!='unknown':domain['season_mode']=_row('season_mode',actions['mode'],'state',weather,operator=True)
    doc.update(schema='earthship-household-snapshot/v4',base_model_snapshot_id=base_id,weather_context_sha256=weather.to_dict()['weather_sha256'],
        weather_context_scope='retained_original_forecast_and_operator_context')
    return doc


@dataclass(frozen=True)
class WeatherSnapshot(ModelSnapshot):
    original_weather:bytes

    def __post_init__(self):
        HouseholdSnapshot.__post_init__(self)
        if not isinstance(self.original_source,bytes) or len(self.original_source)>MAX_SOURCE_BYTES:raise ValueError('bounded original source required')
        if not isinstance(self.original_weather,bytes) or len(self.original_weather)>MAX_BYTES:raise ValueError('bounded original weather required')
        doc=loads(self.content)
        if doc.get('schema')!='earthship-household-snapshot/v4' or doc.get('planner_authority')!='none':raise ValueError('original weather snapshot required')
        weather=PreparedWeatherContext(self.original_weather)
        if canonical(_render(loads(self.original_source),weather,doc['code_revision']))!=self.content:raise ValueError('original weather snapshot differs')

    # Only immutable original context is reused; freshness is assessed by the planner.
    @cached_property
    def weather(self):return PreparedWeatherContext(self.original_weather)

    @property
    def source_context(self):return dict(schema=CONTEXT_SCHEMA,power_receipt=self.source_receipt,weather_inputs=self.weather.to_dict())


def bind_weather_snapshot(*,source_receipt,source_runtime_manifest,weather_context,code_revision):
    if not isinstance(weather_context,PreparedWeatherContext):raise ValueError('prepared original weather required')
    from .power_snapshot import replay_power_snapshot
    source=replay_power_snapshot(source_receipt,runtime_manifest=source_runtime_manifest)
    return WeatherSnapshot(canonical(_render(source,weather_context,code_revision)),canonical(source),canonical(weather_context.to_dict()))


def restore_weather_snapshot(document,context):
    if not isinstance(context,dict) or set(context)!={'schema','power_receipt','weather_inputs'} or context['schema']!=CONTEXT_SCHEMA:
        raise ValueError('closed original weather source context required')
    value=WeatherSnapshot(canonical({key:item for key,item in document.items() if key!='snapshot_id'}),canonical(context['power_receipt']),canonical(context['weather_inputs']))
    if value.snapshot_id!=document['snapshot_id']:raise ValueError('original weather snapshot identity differs')
    return value
