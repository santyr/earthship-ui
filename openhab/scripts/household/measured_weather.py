"""Original receiver points; proxy irradiance and rain counters are not effects."""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from .codec import canonical,loads,identity
from .control_contracts import instant
from .evidence import utc,epoch,digest
from weather_radiation_evidence import RadiationPolicy
from weather_radiation_reader import _snapshot
from weather_rain_evidence import RainPolicy
from weather_rain_day import parse_rain_snapshot

MAX_BYTES=65536
SOURCES={'radiation':('Weather_Radiation_Evidence_JSON','http://127.0.0.1:5000/radiation_evidence',8192),
         'rain':('Weather_Rain_Evidence_JSON','http://127.0.0.1:5000/rain_evidence',4096)}
SOURCE_FIELDS={'source_identity','source_endpoint','raw','sha256','available_at','expected_epoch',
               'policy_raw','policy_sha256','policy_available_at'}
FIELDS={'schema','sources','as_of','created_at','measured_weather_sha256'}
ROLES={'radiation':(('light_lux','lux','original_received_lux'),
                    ('solar_radiation_proxy_wm2','W_m2','lux_proxy_126_7')),
       'rain':(('rain_counter_in','in','original_cumulative_counter'),)}


def _original_pair(row,raw_key,digest_key,maximum):
    raw=row[raw_key]
    if raw is None:
        if row[digest_key] is not None:raise ValueError('absent original cannot have a digest')
    elif (not isinstance(raw,str) or len(raw.encode())>maximum or
          sha256(raw.encode()).hexdigest()!=digest(row[digest_key])):
        raise ValueError('bounded exact original text required')


def _validate(value):
    if set(value)!=FIELDS or value['schema']!='earthship-household-measured-weather/v1':
        raise ValueError('closed original measured weather required')
    if identity({k:v for k,v in value.items() if k!='measured_weather_sha256'})!=value['measured_weather_sha256']:
        raise ValueError('original measured weather identity differs')
    at=instant(value['as_of']);created=instant(value['created_at'])
    if not at<=created<=at+timedelta(seconds=15):raise ValueError('bounded original collection clock required')
    sources=value['sources']
    if not isinstance(sources,dict) or set(sources)!=set(SOURCES):raise ValueError('fixed complete source records required')
    for kind,(name,endpoint,maximum) in SOURCES.items():
        row=sources[kind]
        if (not isinstance(row,dict) or set(row)!=SOURCE_FIELDS or
            row['source_identity']!=name or row['source_endpoint']!=endpoint):raise ValueError('fixed original source identity required')
        if any(instant(row[key])>at for key in ('available_at','policy_available_at')):raise ValueError('future source availability refused')
        if row['expected_epoch'] is not None:epoch(row['expected_epoch'])
        _original_pair(row,'raw','sha256',maximum);_original_pair(row,'policy_raw','policy_sha256',4096)


@dataclass(frozen=True)
class PreparedMeasuredWeather:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or not 1<=len(self.content)<=MAX_BYTES:raise ValueError('bounded frozen weather context required')
        _validate(loads(self.content))

    def to_dict(self):return loads(self.content)


def prepare_measured_weather(*,sources,as_of,created_at):
    value=dict(schema='earthship-household-measured-weather/v1',sources=sources,as_of=utc(as_of),created_at=utc(created_at))
    value['measured_weather_sha256']=identity(value)
    return PreparedMeasuredWeather(canonical(value))


def _policy(kind,raw):
    value=loads(raw)
    fields={'version','sensor_id','validity_seconds'}|({'maximum_counter_in'} if kind=='rain' else set())
    if set(value)!=fields or type(value['version']) is not int or value['version']!=1:raise ValueError('original explicit source policy required')
    return (RainPolicy if kind=='rain' else RadiationPolicy)(**{k:v for k,v in value.items() if k!='version'})


def _point(kind,row,at):
    if row['raw'] is None:return 'missing_source',None
    if row['policy_raw'] is None:return 'missing_policy',None
    if row['expected_epoch'] is None:return 'missing_owner_binding',None
    try:policy=_policy(kind,row['policy_raw'])
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return 'invalid_policy',None
    try:
        if kind=='radiation':
            envelope,point=_snapshot(row['raw'],instant(row['available_at']),policy)
            if envelope['streamEpoch']!=row['expected_epoch']:return 'owner_epoch_mismatch',None
            if point is None:return 'source_unavailable',None
            if point['fault_visibility']!='verified':return 'unverified_fault_visibility',point
        else:
            sample=parse_rain_snapshot(row['raw'],instant(row['available_at']),policy)
            if sample.epoch!=row['expected_epoch']:return 'owner_epoch_mismatch',None
            point=dict(totalRainIn=sample.counter_in,receivedAt=sample.received_at,validUntil=sample.valid_until,streamEpoch=sample.epoch)
        if at>=point['validUntil']:return 'expired_source',point
        return None,point
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return 'invalid_source',None


def _row(role,unit,basis,source,point,reason,at,context_digest):
    point={} if point is None else point
    received=point.get('receivedAt');until=point.get('validUntil')
    received=None if received is None else received.isoformat();until=None if until is None else until.isoformat()
    parents=list(dict.fromkeys([*[source[k] for k in ('sha256','policy_sha256') if source[k] is not None],context_digest]))
    evidence=dict(source_role=role,source_identity=source['source_identity'],
        digest=None if source['sha256'] is None else identity(dict(source_role=role,original_source_sha256=source['sha256'],
            original_policy_sha256=source['policy_sha256'],measured_weather_sha256=context_digest,valid_until=until)),
        source_epoch=point.get('streamEpoch'),hardware_epoch=None,observed_at=None,received_at=received,
        available_at=source['available_at'],valid_until=until,assessed_at=at.isoformat(),
        quality='qualified' if reason is None else 'unavailable',reason=reason,parent_digests=parents)
    key={'light_lux':'lightLux','solar_radiation_proxy_wm2':'irradianceWm2','rain_counter_in':'totalRainIn'}[role]
    return dict(value=point.get(key) if reason is None else None,unit=unit,basis=basis,reason=reason,evidence=evidence,
        radio_decoded_at=None if point.get('radioDecodedAt') is None else point['radioDecodedAt'].isoformat())


def project_measured_weather(context,*,as_of=None):
    if not isinstance(context,PreparedMeasuredWeather):raise ValueError('original frozen measured weather required')
    value=context.to_dict();at=instant(value['as_of']) if as_of is None else utc(as_of)
    if at<instant(value['as_of']):raise ValueError('measured weather cannot be backdated')
    observations={}
    for kind,roles in ROLES.items():
        source=value['sources'][kind];reason,point=_point(kind,source,at)
        for role,unit,basis in roles:observations[role]=_row(role,unit,basis,source,point,reason,at,value['measured_weather_sha256'])
    result=dict(schema='earthship-household-measured-weather-projection/v1',measured_weather_sha256=value['measured_weather_sha256'],
        as_of=at.isoformat(),observations=observations,calibrated_irradiance_qualified=False,rain_rate_qualified=False,
        physical_action_effects_qualified=False,automatic_actuation=False)
    result['projection_sha256']=identity(result)
    return result
