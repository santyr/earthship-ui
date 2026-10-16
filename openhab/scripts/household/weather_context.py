"""Original weather and operator context; forecasts are not measured sources."""
from dataclasses import dataclass,asdict
from copy import deepcopy
from hashlib import sha256
import base64,binascii,zlib
from .codec import canonical,loads,identity
from .control_contracts import instant
from .thermal_model import PreparedProjection,project as project_thermal,ROLES
from .evidence import EvidenceRef,Observation
from .snapshot import build_snapshot
from thermal_model.provisional_artifact import candidate_digest
from thermal_model.temperature_history import STREAMS,_validate_sensor_receipt
from thermal_model.provisional_forecast import CAPTURE_FIELDS,CAPTURE_SCHEMA,digest as capture_digest
from thermal_model.installed_shade_origin import _forecast_forcing,_origin_actions

MAX_BYTES=262144
MAX_ORIGINAL_BYTES=2*1024*1024
ORIGINAL_FIELDS={'encoding','uncompressed_bytes','uncompressed_sha256','data'}
FIELDS={'schema','original_capture','prepared_thermal','weather_sha256'}
UNKNOWN_OBSERVATIONS=('solar_radiation_wm2','relative_humidity','precipitation','wind_speed','daylight_geometry')


def _encode_original(original):
    raw=canonical(original)
    if not 1<=len(raw)<=MAX_ORIGINAL_BYTES:raise ValueError('bounded complete original capture required')
    return dict(encoding='zlib-base64-v1',uncompressed_bytes=len(raw),uncompressed_sha256=sha256(raw).hexdigest(),
        data=base64.b64encode(zlib.compress(raw,9)).decode('ascii'))


def _decode_original(value):
    try:
        if (not isinstance(value,dict) or set(value)!=ORIGINAL_FIELDS or value['encoding']!='zlib-base64-v1' or
            type(value['uncompressed_bytes']) is not int or not 1<=value['uncompressed_bytes']<=MAX_ORIGINAL_BYTES or
            not isinstance(value['data'],str) or len(value['data'])>MAX_BYTES):raise ValueError()
        packed=base64.b64decode(value['data'],validate=True)
        if base64.b64encode(packed).decode('ascii')!=value['data']:raise ValueError()
        decoder=zlib.decompressobj();raw=decoder.decompress(packed,value['uncompressed_bytes']+1)
        if (not decoder.eof or decoder.unconsumed_tail or decoder.unused_data or
            len(raw)!=value['uncompressed_bytes'] or sha256(raw).hexdigest()!=value['uncompressed_sha256']):raise ValueError()
        original=loads(raw)
        if canonical(original)!=raw:raise ValueError()
        return original
    except (ValueError,TypeError,UnicodeError,RecursionError,binascii.Error,zlib.error):
        raise ValueError('bounded compressed original capture required') from None


def _original(value):
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema'] not in ('earthship-household-prepared-weather/v1','earthship-household-prepared-weather/v2','earthship-household-prepared-weather/v3'):
        raise ValueError('closed original weather context required')
    if identity({key:item for key,item in value.items() if key!='weather_sha256'})!=value['weather_sha256']:
        raise ValueError('sealed original weather context differs')
    prepared=PreparedProjection(canonical(value['prepared_thermal']));model=prepared.to_dict();capture=_decode_original(value['original_capture'])
    native=value['schema'] in ('earthship-household-prepared-weather/v2','earthship-household-prepared-weather/v3')
    fields,schema=CAPTURE_FIELDS,CAPTURE_SCHEMA
    if native:
        from native_thermal_forecast import CAPTURE_FIELDS as fields,CAPTURE_SCHEMA as schema
    if model['schema']!='earthship-household-prepared-thermal/v'+str(2 if native else 1):
        raise ValueError('original weather and prepared model versions differ')
    if (not isinstance(capture,dict) or set(capture)!=fields or capture['schema']!=schema or
        capture_digest(capture,'capture_sha256')!=capture['capture_sha256'] or
        capture['capture_sha256']!=model['original_capture_sha256']):
        raise ValueError('original capture identity differs from prepared model')
    issue=instant(model['issue']);available=instant(capture['inputs_available_at']);published=instant(capture['published_at'])
    if (instant(capture['issued_at'])!=issue or not available<=issue<=published or
        instant(model['snapshot']['as_of'])!=issue or instant(model['snapshot']['created_at'])!=published or
        capture['candidate']['artifact_sha256']!=model['artifact_sha256'] or capture['candidate']['runtime_sha256']!=model['runtime_sha256']):
        raise ValueError('original weather/model origin differs')
    candidate=capture['candidate']
    if native and (canonical(model['executing_runtime']['thermal_runtime'])!=canonical(candidate['runtime']) or
            canonical(model['geometry'])!=canonical(capture['geometry']) or
            model['geometry_series_sha256']!=capture['geometry_series_sha256'] or
            model['model_rule']!=capture['output']['model_rule']):
        raise ValueError('original native model runtime or geometry differs')
    if (candidate_digest(candidate)!=candidate['artifact_sha256'] or
        canonical(candidate['fit']['coefficients'])!=canonical(model['coefficients'])):
        raise ValueError('original candidate identity or prepared coefficients differ')
    observations=[]
    for role,name in ROLES.items():
        row=capture['inputs']['origin_temperatures']['roles'][role]
        phase=candidate['fit']['sensor_epochs'][role]
        stream,sensor_model,sensor_id=STREAMS[role]
        if row['identity']!=dict(stream=stream,model=sensor_model,sensor_id=sensor_id,sensor_epoch=phase):
            raise ValueError('original sensor identity differs')
        target,receipt=row['grid'][-1]
        _validate_sensor_receipt(receipt,instant(target),sensor_epoch=phase)
        ref=EvidenceRef(name,'Weather_Temperature_Evidence_JSON:'+stream,receipt['snapshotSha256'],
            receipt['streamEpoch'],receipt['sensorEpoch'],None,instant(receipt['receivedAt']),instant(receipt['storedAt']),
            instant(receipt['validUntil']),issue,'qualified',None,(capture['capture_sha256'],))
        observations.append(Observation(ref,receipt['temperatureF'],'degF'))
    policy=dict(requirements={'thermal_current':list(ROLES.values())},
        max_age_seconds={role:120 for role in ROLES.values()},max_skew_seconds=120)
    snapshot=build_snapshot(observations,as_of=issue,created_at=published,
        code_revision=model['snapshot']['code_revision'],config_revision=identity(policy),**policy)
    if canonical(snapshot.to_dict())!=canonical(model['snapshot']):
        raise ValueError('prepared snapshot differs from original sensor evidence')
    actions=_origin_actions(capture['inputs']['action_snapshot'],issue,allow_removed=capture['output'].get('model_rule')=='earthship-native-joint-shade-dynamics/v3')
    if canonical(actions)!=canonical(model['actions']):raise ValueError('original operator context differs')
    forcings=_forecast_forcing(capture['inputs']['forecast'],issue,available,actions)
    if canonical([asdict(row) for row in forcings])!=canonical(model['forcings']):raise ValueError('original weather forcing differs')
    if canonical(project_thermal(prepared)['output'])!=canonical(capture['output']):raise ValueError('original model output differs')
    return prepared,capture


@dataclass(frozen=True)
class PreparedWeatherContext:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded immutable weather context required')
        _original(loads(self.content))

    def to_dict(self):return loads(self.content)

    @property
    def original_capture(self):return _decode_original(self.to_dict()['original_capture'])

    @property
    def prepared(self):return PreparedProjection(canonical(self.to_dict()['prepared_thermal']))


def prepare_weather_context(capture,*,prepared_thermal):
    if not isinstance(prepared_thermal,PreparedProjection):raise ValueError('separately prepared original model required')
    # Only this collection boundary may reopen the original source archives.
    from thermal_model.provisional_forecast import validate_capture
    original=validate_capture(capture)
    value=dict(schema='earthship-household-prepared-weather/v1',original_capture=_encode_original(original),prepared_thermal=prepared_thermal.to_dict())
    value['weather_sha256']=identity(value)
    return PreparedWeatherContext(canonical(value))


def prepare_cycle_contexts(capture,*,code_revision):
    """Validate one frozen original capture before preparing both model contexts.

    Callers cannot supply a trusted flag or a previously prepared lookalike.
    The complete native archive replay remains inside prepare_projection.
    Standalone weather preparation retains its separate validation boundary.
    """
    from .thermal_model import prepare_projection
    raw=canonical(capture)
    if not 1<=len(raw)<=MAX_ORIGINAL_BYTES:raise ValueError('bounded complete original capture required')
    original=loads(raw)
    thermal=prepare_projection(original,code_revision=code_revision)
    value=dict(schema='earthship-household-prepared-weather/v1',original_capture=_encode_original(original),prepared_thermal=thermal.to_dict())
    value['weather_sha256']=identity(value)
    return thermal,PreparedWeatherContext(canonical(value))


def project_weather(context):
    if not isinstance(context,PreparedWeatherContext):raise ValueError('frozen original weather context required')
    value=context.to_dict();capture=_decode_original(value['original_capture']);model=value['prepared_thermal'];forecast=capture['inputs']['forecast']
    native=value['schema'] in ('earthship-household-prepared-weather/v2','earthship-household-prepared-weather/v3')
    result=dict(schema='earthship-household-weather-projection/v'+value['schema'].rsplit('/v',1)[1],weather_context_sha256=value['weather_sha256'],
        original_capture_sha256=capture['capture_sha256'],weather_rows_sha256=forecast['rows_sha256'],
        provider_issued_at=forecast['issued_at'],provider_captured_at=forecast['captured_at'],origin=model['issue'],
        available_at=capture['inputs_available_at'],horizon_hours=model['horizon_hours'],forcings=model['forcings'],
        hourly_forecast=forecast['rows'],origin_states=model['actions'],confidence='not_assessed',input_qualification='not_assessed',
        original_weather_receipts_verified=True,unknown_observations=list(UNKNOWN_OBSERVATIONS),
        action_effects_qualified=False,automatic_actuation=False)
    if native:result.update(geometry_series_sha256=model['geometry_series_sha256'],model_rule=model['model_rule'])
    if value['schema']=='earthship-household-prepared-weather/v3':
        # PreparedWeatherContext already validates the complete original series,
        # native output, exact forcing grid and availability. Expose those same
        # frozen bytes; do not rerun astronomy or infer measured daylight/radiation.
        packet=model['geometry'];caches=packet['caches']
        result['solar_geometry']=dict(series_sha256=packet['series_sha256'],rule=packet['rule'],
            request_sha256=packet['request']['request_sha256'],native_runtime=packet['native_runtime'],
            source_identity=caches[0]['source']['source_thing'],site=caches[0]['source']['site'],
            timezone=packet['request']['timezone'],available_at=max(cache['computed_at'] for cache in caches),
            cache_sha256s=[cache['cache_sha256'] for cache in caches],
            positions=[row for cache in caches for row in cache['positions']],
            quality='retained_native_calculation',daylight_events_available=False)
        result['unknown_observations'].remove('daylight_geometry')
    result['projection_sha256']=identity(result)
    return result


def prepare_native_weather_context(capture,*,prepared_thermal,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    if not isinstance(prepared_thermal,PreparedProjection) or prepared_thermal.to_dict()['schema']!='earthship-household-prepared-thermal/v2':
        raise ValueError('separately prepared native model required')
    from native_thermal_forecast import validate_capture
    capture,runtime=map(deepcopy,(capture,runtime))
    original=validate_capture(capture,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    value=dict(schema='earthship-household-prepared-weather/v3',original_capture=_encode_original(original),prepared_thermal=prepared_thermal.to_dict())
    value['weather_sha256']=identity(value);result=PreparedWeatherContext(canonical(value));check_budget();return result


def prepare_native_cycle_contexts(capture,*,code_revision,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    from .thermal_model import prepare_native_projection
    original,runtime=map(deepcopy,(capture,runtime))
    thermal=prepare_native_projection(original,code_revision=code_revision,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    value=dict(schema='earthship-household-prepared-weather/v3',original_capture=_encode_original(original),prepared_thermal=thermal.to_dict())
    value['weather_sha256']=identity(value);weather=PreparedWeatherContext(canonical(value));check_budget();return thermal,weather


def prepare_serving_native_cycle_contexts(capture,model,*,code_revision,expected_capture_sha256,check_budget=lambda:None):
    from native_model_serving_receipt import _require_model
    from .thermal_model import prepare_serving_native_projection
    _require_model(model)
    original=deepcopy(capture)
    thermal=prepare_serving_native_projection(original,model,code_revision=code_revision,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)
    value=dict(schema='earthship-household-prepared-weather/v3',original_capture=_encode_original(original),prepared_thermal=thermal.to_dict())
    value['weather_sha256']=identity(value);weather=PreparedWeatherContext(canonical(value));check_budget()
    return thermal,weather
