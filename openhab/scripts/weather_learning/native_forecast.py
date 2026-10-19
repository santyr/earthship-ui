"""Original Google weather for native thermal/energy forcing, without incumbent SQL.

Complete original API capsules are retained in bounded compressed form. Replay
rederives their native points and selected rows; it never invents legacy metric
receipts, a weather code, historical availability, or a model/release grant.
"""
from datetime import timedelta
from hashlib import sha256
import base64,binascii,json,sqlite3,zlib
from .config import Site
from .contracts import canonical,identity,instant,validate_snapshot
from .evidence import utc
from .features import prospective_snapshot
from .weathernext_ee import parse_collection_response

SCHEMA='earthship-weathernext-native-forecast/v1'
REQUIRED=frozenset({'station_head_temperature_2m','surface_solar_radiation_downwards_1hr','wind_speed_10m'})
FIELDS={'schema','source','origin','horizon_hours','issued_at','captured_at','available_by','site','rows','rows_sha256',
        'snapshot_sha256','source_original','release_authorized','automatic_actuation','forecast_sha256'}
SOURCE_FIELDS={'schema','provider','run_id','initialized_at','first_seen_at','ingestion_completed_at','historical','site','source_originals'}
MAX_SOURCE_BYTES=8*1024*1024
MAX_CAPSULE_BYTES=1024*1024


def _window(origin,hours):
    origin=utc(origin)
    if type(hours) is not int or not 1<=hours<=72:raise ValueError('native forecast horizon must be 1 through 72 hours')
    first=origin.replace(minute=0,second=0,microsecond=0);last=(origin+timedelta(hours=hours)).replace(minute=0,second=0,microsecond=0)
    if last<origin+timedelta(hours=hours):last+=timedelta(hours=1)
    return tuple(first+timedelta(hours=i) for i in range(int((last-first).total_seconds()/3600)+1))


def _encode(body):
    raw=canonical(body)
    if len(raw)>MAX_SOURCE_BYTES:raise ValueError('bounded original Google source required')
    return dict(encoding='zlib-base64-v1',uncompressed_bytes=len(raw),uncompressed_sha256=sha256(raw).hexdigest(),
        data=base64.b64encode(zlib.compress(raw,9)).decode())


def _decode(packet):
    try:
        if (not isinstance(packet,dict) or set(packet)!={'encoding','uncompressed_bytes','uncompressed_sha256','data'} or
                packet['encoding']!='zlib-base64-v1' or type(packet['uncompressed_bytes']) is not int or
                not 1<=packet['uncompressed_bytes']<=MAX_SOURCE_BYTES or not isinstance(packet['data'],str) or len(packet['data'])>MAX_CAPSULE_BYTES):raise ValueError()
        packed=base64.b64decode(packet['data'],validate=True)
        if base64.b64encode(packed).decode()!=packet['data']:raise ValueError()
        decoder=zlib.decompressobj();raw=decoder.decompress(packed,packet['uncompressed_bytes']+1)
        if (not decoder.eof or decoder.unconsumed_tail or decoder.unused_data or len(raw)!=packet['uncompressed_bytes'] or
                sha256(raw).hexdigest()!=packet['uncompressed_sha256']):raise ValueError()
        body=json.loads(raw)
        if canonical(body)!=raw:raise ValueError()
        return body
    except (ValueError,TypeError,KeyError,UnicodeError,RecursionError,binascii.Error,zlib.error):
        raise ValueError('unchanged bounded original Google capsule required') from None


def _snapshot(body):
    if not isinstance(body,dict) or set(body)!=SOURCE_FIELDS or not isinstance(body['source_originals'],list) or not 1<=len(body['source_originals'])<=2:
        raise ValueError('complete original Google source header required')
    if not isinstance(body['site'],dict) or set(body['site'])!={'latitude','longitude','timezone'}:raise ValueError('original Google site required')
    site=Site(**body['site']);initialized=instant(body['initialized_at']);points=[]
    for original in body['source_originals']:
        if not isinstance(original,dict) or set(original)!={'collection','payload'} or not isinstance(original['payload'],dict):raise ValueError('original collection capsule required')
        payload=original['payload']
        if not isinstance(payload.get('region'),list) or not payload['region'] or not isinstance(payload['region'][0],list) or not isinstance(payload.get('metadata'),list):raise ValueError('original collection rows required')
        _,rows=parse_collection_response(payload,collection=original['collection'],bands=payload['region'][0][4:],site=site,
            initialized_at=initialized,horizon=len(payload['metadata']))
        points.extend(rows)
    return validate_snapshot(body|dict(points=points))


def _derive(snapshot,*,origin,available_by,horizon_hours,site):
    origin,known=map(utc,(origin,available_by));targets=_window(origin,horizon_hours)
    if not known<=origin:raise ValueError('native input collection must precede origin')
    if not isinstance(site,Site):raise ValueError('authoritative native site required')
    source=prospective_snapshot(snapshot,issued_at=known)
    prospective_snapshot(source,issued_at=origin)
    if source['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):raise ValueError('native Google site differs')
    index={(point['variable'],instant(point['valid_at'])):point['value'] for point in source['points'] if point['statistic']=='mean'}
    rows=[]
    for at in targets:
        temp=index.get(('station_head_temperature_2m',at));ghi=index.get(('surface_solar_radiation_downwards_1hr',at));wind=index.get(('wind_speed_10m',at))
        if any(value is None for value in (temp,ghi,wind)):raise ValueError('complete original Google bracket required')
        temp=temp*9/5+32
        if not -40<=temp<=140 or not 0<=ghi<=1600 or wind<0:raise ValueError('Google forcing outside existing physical bounds')
        rows.append(dict(at=at.isoformat(),tempF=temp,radiationWm2=ghi,windMph=wind/.44704,weatherCode=None))
    return source,rows


def make_native_forecast(snapshot,*,origin,available_by,horizon_hours,site):
    source,rows=_derive(snapshot,origin=origin,available_by=available_by,horizon_hours=horizon_hours,site=site)
    original={key:value for key,value in source.items() if key not in ('points','snapshot_sha256')}
    # The frozen packet must reconstruct the exact full archived source digest,
    # not merely contain a plausible subset carrying an asserted parent hash.
    if identity(_snapshot(original))!=source['snapshot_sha256']:raise ValueError('original Google point order or source differs')
    value=dict(schema=SCHEMA,source='weathernext3',origin=utc(origin).isoformat(),horizon_hours=horizon_hours,
        issued_at=source['initialized_at'],captured_at=source['ingestion_completed_at'],available_by=utc(available_by).isoformat(),
        site=source['site'],rows=rows,rows_sha256=identity(rows),snapshot_sha256=source['snapshot_sha256'],
        source_original=_encode(original),release_authorized=False,automatic_actuation=False)
    value['forecast_sha256']=identity(value)
    if len(canonical(value))>MAX_CAPSULE_BYTES:raise ValueError('native Google capsule exceeds byte limit')
    return value


def validate_native_forecast(value):
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or value['source']!='weathernext3' or
            value['release_authorized'] is not False or value['automatic_actuation'] is not False or len(canonical(value))>MAX_CAPSULE_BYTES or
            identity({k:v for k,v in value.items() if k!='forecast_sha256'})!=value['forecast_sha256']):
        raise ValueError('closed original native Google forecast required')
    if not isinstance(value['site'],dict) or set(value['site'])!={'latitude','longitude','timezone'}:raise ValueError('native Google site required')
    body=_decode(value['source_original']);snapshot=_snapshot(body)
    if identity(snapshot)!=value['snapshot_sha256']:raise ValueError('original Google snapshot identity differs')
    source,rows=_derive(snapshot,origin=instant(value['origin']),available_by=instant(value['available_by']),
        horizon_hours=value['horizon_hours'],site=Site(**value['site']))
    if (source['initialized_at']!=value['issued_at'] or source['ingestion_completed_at']!=value['captured_at'] or
            canonical(rows)!=canonical(value['rows']) or identity(rows)!=value['rows_sha256']):
        raise ValueError('native Google weather differs from original rows or clocks')
    return value


def load_native_forecast(archive,*,origin,available_by,horizon_hours,site):
    targets=_window(origin,horizon_hours)
    try:
        snapshot=archive.eligible_snapshot(utc(available_by),targets[-1],required_variables=REQUIRED)
        if snapshot is None:return None
        return make_native_forecast(snapshot,origin=origin,available_by=available_by,horizon_hours=horizon_hours,site=site)
    except (ValueError,KeyError,TypeError,OverflowError,OSError,sqlite3.Error):return None
