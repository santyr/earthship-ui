"""Closed, finite, provider-specific snapshot contracts with original clocks."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,math,re
from .config import Site

def instant(value):
    if not isinstance(value,str) or len(value)>64:raise ValueError('bounded ISO timestamp required')
    parsed=datetime.fromisoformat(value)
    if parsed.utcoffset() is None:raise ValueError('aware timestamp required')
    return parsed.astimezone(timezone.utc)

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def identity(value):return sha256(canonical(value)).hexdigest()
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def digest(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('source SHA256 required')
    return value

def validate_snapshot(value):
    fields={'schema','provider','run_id','initialized_at','first_seen_at','ingestion_completed_at','historical','site','points','source_originals'}
    if not isinstance(value,dict) or set(value)!=fields or value['schema']!='earthship-weathernext-snapshot/v1' or value['provider']!='weathernext3':
        raise ValueError('closed WeatherNext snapshot required')
    init,seen,completed=map(instant,(value['initialized_at'],value['first_seen_at'],value['ingestion_completed_at']))
    if not init<=seen<=completed or type(value['historical']) is not bool:
        raise ValueError('source availability clocks invalid')
    run_id=value['run_id']
    if not isinstance(run_id,str):raise ValueError('native source run required')
    if run_id.startswith('ee:'):
        run_init=instant(run_id[3:])
    elif re.fullmatch(r'\d{8}_\d{2}hr_\d{2}_preds',run_id):
        run_init=datetime.strptime(run_id[:11],'%Y%m%d_%H').replace(tzinfo=timezone.utc)
    else:raise ValueError('native source run required')
    if run_init!=init:raise ValueError('run initialization differs')
    if not isinstance(value['site'],dict) or set(value['site'])!={'latitude','longitude','timezone'}:
        raise ValueError('closed source site required')
    Site(**value['site'])
    originals=value['source_originals']
    if not isinstance(originals,list) or not 1<=len(originals)<=2:raise ValueError('retained original source payloads required')
    source_refs={}
    for original in originals:
        if not isinstance(original,dict) or set(original)!={'collection','payload'} or not isinstance(original['payload'],dict):
            raise ValueError('closed original source capsule required')
        if not isinstance(original['collection'],str) or not original['collection'].startswith('projects/gcp-public-data-weathernext/assets/'):
            raise ValueError('approved original source collection required')
        source_refs[identity(original)]=original['collection']
    points=value['points']
    if not isinstance(points,list) or not 1<=len(points)<=360*128:raise ValueError('bounded nonempty points required')
    seen_points=set()
    for row in points:
        keys={'variable','statistic','valid_at','value','unit','raw_value','raw_unit','period_seconds','source_ref','source_digest','latitude','longitude'}
        if not isinstance(row,dict) or set(row)!=keys:raise ValueError('closed original point required')
        valid=instant(row['valid_at'])
        if not init<valid<=init+timedelta(hours=360):raise ValueError('point outside native forecast horizon')
        if row['statistic'] not in ('mean','p10','p25','p50','p75','p90'):raise ValueError('native statistic required')
        for name in ('variable','unit','raw_unit','source_ref'):
            if not isinstance(row[name],str) or not 1<=len(row[name])<=512:raise ValueError('bounded point identity required')
        if not row['source_ref'].startswith('projects/gcp-public-data-weathernext/assets/'):
            raise ValueError('approved WeatherNext source asset required')
        digest(row['source_digest'])
        if row['source_digest'] not in source_refs or not row['source_ref'].startswith(source_refs[row['source_digest']]+'/'):
            raise ValueError('point source digest must resolve retained original')
        if type(row['period_seconds']) is not int or row['period_seconds'] not in (0,3600):raise ValueError('explicit native interval required')
        if any(v is not None and not finite(v) for v in (row['value'],row['raw_value'])) or ((row['value'] is None)!=(row['raw_value'] is None)):
            raise ValueError('finite paired original/normalized values required')
        Site(row['latitude'],row['longitude'],'UTC')
        key=(row['variable'],row['statistic'],valid)
        if key in seen_points:raise ValueError('duplicate forecast target refused')
        seen_points.add(key)
    if len(canonical(value))>8*1024*1024:raise ValueError('snapshot size cap exceeded')
    return value
