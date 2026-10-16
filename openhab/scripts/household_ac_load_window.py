"""Original one-hour AC-energy observations for chronological load outcomes."""
from datetime import timedelta
from household.codec import canonical,loads,identity
from household.evidence import utc
from household.control_contracts import instant
from earthship_energy.ac_evidence import parse_ac_evidence,BOUNDS
from earthship_energy.power_evidence import build_power_intervals,PowerSequenceError
from earthship_energy.power_intervals import account_power_intervals

SCHEMA='earthship-ac-load-hour-source/v1'
FIELDS={'schema','source_identity','item_id','window_start','window_end','query_start','query_end','requested_at','received_at','rows','source_sha256'}
MAX_ROWS=2000
MAX_BYTES=1048576


def build_hour_source(*,rows,start,end,requested_at,received_at,item_id):
    start,end,requested,received=map(utc,(start,end,requested_at,received_at))
    if end-start!=timedelta(hours=1) or not end+timedelta(minutes=5)<=requested<=received or received-requested>timedelta(seconds=15):
        raise ValueError('mature bounded original AC hour required')
    if type(item_id) is not int or not 0<=item_id<=2147483647:raise ValueError('unique original AC Item mapping required')
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_ROWS:raise ValueError('bounded original AC hour rows required')
    floor=start-timedelta(seconds=120);previous=None;originals=[];size=0
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('exact original AC hour row required')
        at,raw=row;at=utc(at)
        if not floor<=at<end or previous is not None and at<=previous or raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):
            raise ValueError('bounded ordered original AC hour required')
        previous=at;size+=0 if raw is None else len(raw.encode())
        if size>MAX_BYTES:raise ValueError('bounded original AC hour bytes required')
        originals.append([at.isoformat(),raw])
    value=dict(schema=SCHEMA,source_identity='Inverter_AC_Evidence_JSON',item_id=item_id,window_start=start.isoformat(),window_end=end.isoformat(),
        query_start=floor.isoformat(),query_end=end.isoformat(),requested_at=requested.isoformat(),received_at=received.isoformat(),rows=originals)
    value['source_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded AC hour source required')
    return loads(canonical(value))


def account_hour(source,*,assessed_at,start,end):
    assessed,start,end=utc(assessed_at),utc(start),utc(end)
    if not isinstance(source,dict) or set(source)!=FIELDS or source['schema']!=SCHEMA:raise ValueError('closed original AC hour source required')
    expected=build_hour_source(rows=[(instant(at),raw) for at,raw in source['rows']],start=instant(source['window_start']),end=instant(source['window_end']),
        requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=source['item_id'])
    if canonical(expected)!=canonical(source) or instant(source['window_start'])!=start or instant(source['window_end'])!=end or instant(source['received_at'])>assessed:
        raise ValueError('original AC hour identity or clocks differ')
    out=dict(source_sha256=source['source_sha256'],status='unavailable',reason='ambiguous_source_sequence',known_ac_kwh=None,covered_seconds=None,missing_seconds=None,coverage=None)
    try:
        intervals=build_power_intervals([(instant(at),raw) for at,raw in source['rows']],'inverter.ac_output_w',start,end,
            cutover=instant(source['query_start']),parser=parse_ac_evidence,bounds=BOUNDS)
    except PowerSequenceError:return out
    value=account_power_intervals(intervals,window_start=start,window_end=end)
    out.update(status='accounted',reason=None,known_ac_kwh=value.positive_kwh,covered_seconds=value.covered_seconds,missing_seconds=value.missing_seconds,coverage=value.coverage)
    return out


def capture_hour(*,connect,start,end,clock,remaining):
    start,end=utc(start),utc(end);requested=utc(clock());remaining()
    if end-start!=timedelta(hours=1) or requested<end+timedelta(minutes=5):raise ValueError('mature original hour query required')
    connection=connect(remaining=remaining)
    try:
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='2000ms'")
            cursor.execute("SET LOCAL lock_timeout='1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout='5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only original AC transaction required')
            remaining();cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',('Inverter_AC_Evidence_JSON',));mapping=cursor.fetchall()
            if len(mapping)!=1 or len(mapping[0])!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique original AC Item required')
            item=mapping[0][0];remaining()
            cursor.execute(f'SELECT time,CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM public.item{item:04d} WHERE time>=%s AND time<%s ORDER BY time ASC LIMIT {MAX_ROWS+1}',(start-timedelta(seconds=120),end))
            rows=cursor.fetchall();remaining()
            return build_hour_source(rows=rows,start=start,end=end,requested_at=requested,received_at=clock(),item_id=item)
    finally:connection.close()
