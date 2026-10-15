"""Original bounded AC-output receipts and deterministic hourly accounting.

This source measures inverter AC output. It does not infer historic household
DC topology, repair invalid rows or interpolate through missing observations.
"""
from datetime import timedelta
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household_ac_load_model import _zone
from earthship_energy.ac_evidence import parse_ac_evidence,BOUNDS
from earthship_energy.power_evidence import build_power_intervals,PowerSequenceError
from earthship_energy.power_intervals import account_power_intervals

SCHEMA='earthship-ac-load-day-source/v1'
FIELDS={'schema','source_identity','item_id','timezone','window_start','window_end','query_start','query_end','requested_at','received_at','rows','source_sha256'}
MAX_ROWS=20000
MAX_DAY_BYTES=16*1024**2


def build_day_source(*,rows,start,end,requested_at,received_at,item_id):
    start,end,requested,received=map(utc,(start,end,requested_at,received_at));zone=_zone('America/Denver')
    left,right=start.astimezone(zone),end.astimezone(zone)
    if (left!=left.replace(hour=0,minute=0,second=0,microsecond=0) or right!=right.replace(hour=0,minute=0,second=0,microsecond=0) or
        right.date()!=left.date()+timedelta(days=1) or end-start not in (timedelta(hours=23),timedelta(hours=24),timedelta(hours=25)) or
        not end<=requested<=received or received-requested>timedelta(seconds=15)):
        raise ValueError('bounded completed original local-day query required')
    if type(item_id) is not int or not 0<=item_id<=2147483647:raise ValueError('unique original AC Item mapping required')
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_ROWS:raise ValueError('bounded original AC rows required')
    floor=start-timedelta(seconds=120);original=[];previous=None;size=0
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('exact original AC row required')
        at,raw=row;at=utc(at)
        if not floor<=at<end or previous is not None and at<=previous or raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):
            raise ValueError('ordered bounded original AC query rows required')
        previous=at;size+=0 if raw is None else len(raw.encode())
        if size>MAX_DAY_BYTES:raise ValueError('bounded original AC content required')
        original.append([at.isoformat(),raw])
    value=dict(schema=SCHEMA,source_identity='Inverter_AC_Evidence_JSON',item_id=item_id,timezone='America/Denver',
        window_start=start.isoformat(),window_end=end.isoformat(),query_start=floor.isoformat(),query_end=end.isoformat(),
        requested_at=requested.isoformat(),received_at=received.isoformat(),rows=original)
    value['source_sha256']=identity(value)
    if len(canonical(value))>MAX_DAY_BYTES:raise ValueError('bounded original day envelope required')
    return loads(canonical(value))


def replay_day_source(source):
    if not isinstance(source,dict) or set(source)!=FIELDS or source['schema']!=SCHEMA:raise ValueError('closed original AC day source required')
    value=build_day_source(rows=[(instant(at),raw) for at,raw in source['rows']],start=instant(source['window_start']),end=instant(source['window_end']),
        requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=source['item_id'])
    if canonical(value)!=canonical(source):raise ValueError('original AC source identity or clocks differ')
    return value


def summarize_day(source):
    source=replay_day_source(source);start,end=instant(source['window_start']),instant(source['window_end'])
    rows=[(instant(at),raw) for at,raw in source['rows']]
    result=dict(schema='earthship-ac-load-day-accounting/v1',source_sha256=source['source_sha256'],window_start=start.isoformat(),
        window_end=end.isoformat(),status='accounted',reason=None,hourly_rows=[])
    try:
        intervals=build_power_intervals(rows,'inverter.ac_output_w',start,end,cutover=instant(source['query_start']),parser=parse_ac_evidence,bounds=BOUNDS)
    except PowerSequenceError:
        result.update(status='unavailable',reason='ambiguous_source_sequence');return result
    at=start
    while at<end:
        stop=at+timedelta(hours=1);account=account_power_intervals(intervals,window_start=at,window_end=stop)
        result['hourly_rows'].append(dict(start=at.isoformat(),end=stop.isoformat(),known_ac_kwh=account.positive_kwh,covered_seconds=account.covered_seconds));at=stop
    result['accounting_sha256']=identity(result);return loads(canonical(result))
