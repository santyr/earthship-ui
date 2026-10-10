"""Immutable raw native-v2 query inputs for independent score replay.

Selected receipts are derived by the existing strict reader. This packet grants
no model/release authority and contains no credentials or supplied scalar scores.
"""
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import re

from forecast_input_capture import _canonical,_directory,_instant
from forecast_temperature_origin import _read,_write
from weather_temperature_config import _object,_nonfinite
from weather_temperature_evidence import TemperaturePolicy
from weather_temperature_reader import select_temperature_grid_v2,_utc
from weather_temperature_history import _fetch_rows

SCHEMA='earthship-native-temperature-query-sources/v1'
FIELDS={'schema','stream','policy','sensor_epoch','targets','assessed_at','history_start','native_rows','release_authority'}
MAX_BYTES=8*1024*1024
POLICY_FIELDS=set(TemperaturePolicy.__dataclass_fields__)


def replay_temperature_source(packet):
    """Validate and derive the original selected grid from retained raw bytes."""
    if (not isinstance(packet,dict) or set(packet)!=FIELDS or packet['schema']!=SCHEMA or
            packet['release_authority'] is not False):raise ValueError('closed native source packet required')
    if not isinstance(packet['stream'],str) or not 1<=len(packet['stream'])<=64:raise ValueError('bounded explicit stream required')
    document=packet['policy']
    if not isinstance(document,dict) or set(document)!=POLICY_FIELDS:raise ValueError('explicit original policy required')
    policy=TemperaturePolicy(**document)
    targets=packet['targets'];rows=packet['native_rows']
    if not isinstance(targets,list) or not 1<=len(targets)<=289:raise ValueError('bounded original targets required')
    targets=list(map(_instant,targets));start=_instant(packet['history_start'])
    if start!=targets[0]-timedelta(seconds=policy.validity_seconds):raise ValueError('original query window required')
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded raw native rows required')
    normalized=[];carry=0;size=0
    for row in rows:
        if not isinstance(row,list) or len(row)!=2:raise ValueError('original raw row required')
        at=_instant(row[0]);raw=row[1]
        if raw is not None and (not isinstance(raw,str) or len(raw.encode())>8192):raise ValueError('bounded raw snapshot or null barrier required')
        size+=len(raw.encode()) if raw is not None else 0
        if size>MAX_BYTES:raise ValueError('bounded raw native source bytes required')
        if at<start:carry+=1
        if carry>1 or at>targets[-1]:raise ValueError('original query rows outside bounded window')
        normalized.append((at,raw))
    if len(_canonical(packet))>MAX_BYTES:raise ValueError('bounded source packet required')
    return select_temperature_grid_v2(normalized,targets=targets,assessed_at=_instant(packet['assessed_at']),
        history_start=start,stream=packet['stream'],policy=policy,sensor_epoch=packet['sensor_epoch'])


def build_temperature_source(*,rows,targets,assessed_at,stream,policy,sensor_epoch):
    if not isinstance(policy,TemperaturePolicy) or not isinstance(targets,(list,tuple)) or not targets:
        raise ValueError('explicit original source request required')
    if not isinstance(rows,list) or len(rows)>10000 or len(targets)>289:raise ValueError('bounded original source request required')
    packet=dict(schema=SCHEMA,stream=stream,policy=asdict(policy),sensor_epoch=sensor_epoch,
        targets=[_utc(at).isoformat() for at in targets],assessed_at=_utc(assessed_at).isoformat(),
        history_start=(_utc(targets[0])-timedelta(seconds=policy.validity_seconds)).isoformat(),
        native_rows=[[_utc(at).isoformat(),raw] for at,raw in rows],release_authority=False)
    replay_temperature_source(packet)
    return packet


def fetch_temperature_source(connection_factory,*,remaining_timeout=None,**request):
    """One bounded read-only stable snapshot; validate before opening the DB."""
    packet=build_temperature_source(rows=[],**request)
    rows=_fetch_rows(connection_factory,_instant(packet['history_start']),_instant(packet['targets'][-1]),
        **({} if remaining_timeout is None else dict(remaining_timeout=remaining_timeout)))
    return build_temperature_source(rows=rows,targets=packet['targets'],assessed_at=packet['assessed_at'],
        stream=packet['stream'],policy=TemperaturePolicy(**packet['policy']),sensor_epoch=packet['sensor_epoch'])


def write_temperature_source(directory,packet,*,before_publish=None):
    replay_temperature_source(packet);raw=_canonical(packet)
    return _write(_directory(Path(directory)),sha256(raw).hexdigest()+'.native-temperature-sources-v1.json',raw,
        **({} if before_publish is None else dict(before_publish=before_publish)))


def read_temperature_source(directory,path):
    root=_directory(Path(directory));path=Path(path)
    if path.parent!=root or re.fullmatch('[0-9a-f]{64}\\.native-temperature-sources-v1\\.json',path.name) is None:
        raise ValueError('original private source address required')
    raw=_read(path,MAX_BYTES)
    if sha256(raw).hexdigest()!=path.name.split('.')[0]:raise ValueError('raw source digest differs')
    packet=json.loads(raw,object_pairs_hook=_object,parse_constant=_nonfinite)
    replay_temperature_source(packet)
    if _canonical(packet)!=raw:raise ValueError('canonical original source packet required')
    return packet


COMPRESSED_SCHEMA='earthship-native-temperature-query-container/v2'
COMPRESSED_FIELDS={'schema','raw_query_sha256','raw_query'}
MAX_CONTAINER_BYTES=MAX_BYTES+4096


def write_compressed_temperature_source(directory,packet,*,before_publish=None):
    """Losslessly retain the original v1 query in a distinct bounded container."""
    import gzip
    replay_temperature_source(packet)
    original=_canonical(packet)
    container=_canonical(dict(schema=COMPRESSED_SCHEMA,raw_query_sha256=sha256(original).hexdigest(),raw_query=packet))
    if len(container)>MAX_CONTAINER_BYTES:raise ValueError('bounded original query container required')
    raw=gzip.compress(container,compresslevel=1,mtime=0)
    if len(raw)>MAX_CONTAINER_BYTES:raise ValueError('bounded compressed query required')
    return _write(_directory(Path(directory)),sha256(raw).hexdigest()+'.native-temperature-sources-v2.json.gz',raw,
        **({} if before_publish is None else dict(before_publish=before_publish)))


def read_compressed_temperature_source(directory,path):
    """Verify compressed bytes and replay the exact underlying raw query."""
    import gzip,io,zlib
    root=_directory(Path(directory));path=Path(path)
    if path.parent!=root or re.fullmatch('[0-9a-f]{64}\\.native-temperature-sources-v2\\.json\\.gz',path.name) is None:
        raise ValueError('explicit original compressed source address required')
    compressed=_read(path,MAX_CONTAINER_BYTES)
    if sha256(compressed).hexdigest()!=path.name.split('.')[0]:raise ValueError('compressed source digest differs')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:raw=stream.read(MAX_CONTAINER_BYTES+1)
    except (OSError,EOFError,zlib.error):raise ValueError('invalid bounded compressed source') from None
    if len(raw)>MAX_CONTAINER_BYTES:raise ValueError('decompressed query container exceeds bound')
    container=json.loads(raw,object_pairs_hook=_object,parse_constant=_nonfinite)
    if (not isinstance(container,dict) or set(container)!=COMPRESSED_FIELDS or container['schema']!=COMPRESSED_SCHEMA or
            _canonical(container)!=raw):raise ValueError('closed canonical compressed source required')
    packet=container['raw_query'];original=_canonical(packet)
    if len(original)>MAX_BYTES or sha256(original).hexdigest()!=container['raw_query_sha256']:
        raise ValueError('original raw query digest or byte bound differs')
    replay_temperature_source(packet)
    return packet
