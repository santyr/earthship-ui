"""Original controller-output hours, qualified with the deployed power policy.

No numeric-history fallback, interpolation, implicit zero or cutover inference.
"""
from datetime import timedelta
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,epoch
from earthship_energy.power_evidence import build_power_intervals,parse_power_evidence,PowerSequenceError
from earthship_energy.power_intervals import account_power_intervals

SCHEMA='earthship-controller-pv-hour-source/v1'
FIELDS={'schema','source_identity','item_id','policy_raw','window_start','window_end','query_start','query_end','requested_at','received_at','rows','source_sha256'}
MAX_ROWS=6000
MAX_BYTES=8*1048576


def policy_cutover(raw):
    if not isinstance(raw,str) or len(raw.encode())>4096:raise ValueError('bounded original power policy required')
    value=loads(raw.encode())
    if (not isinstance(value,dict) or set(value)!={'version','policy','item_name','cutover'} or type(value['version']) is not int or value['version']!=1 or
        value['policy']!='qualified_power_evidence_v1' or value['item_name']!='Power_Evidence_JSON'):
        raise ValueError('qualified controller-output policy required')
    return instant(value['cutover'])


def build_hour_source(*,rows,start,end,requested_at,received_at,item_id,policy_raw):
    start,end,requested,received=map(utc,(start,end,requested_at,received_at));policy_cutover(policy_raw)
    if end-start!=timedelta(hours=1) or not end+timedelta(minutes=5)<=requested<=received or received-requested>timedelta(seconds=15):
        raise ValueError('mature bounded original controller-output hour required')
    if type(item_id) is not int or not 0<=item_id<=2147483647:raise ValueError('unique original power Item mapping required')
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_ROWS:raise ValueError('bounded original power rows required')
    floor=start-timedelta(seconds=120);original=[];previous=None;size=0
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('exact original power row required')
        at,raw=row;at=utc(at)
        if not floor<=at<end or previous is not None and at<=previous or raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):
            raise ValueError('ordered bounded original power rows required')
        size+=0 if raw is None else len(raw.encode());previous=at
        if size>MAX_BYTES:raise ValueError('bounded original power bytes required')
        original.append([at.isoformat(),raw])
    value=dict(schema=SCHEMA,source_identity='Power_Evidence_JSON:pv.output_power_w',item_id=item_id,policy_raw=policy_raw,
        window_start=start.isoformat(),window_end=end.isoformat(),query_start=floor.isoformat(),query_end=end.isoformat(),
        requested_at=requested.isoformat(),received_at=received.isoformat(),rows=original)
    value['source_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original controller-output source required')
    return loads(canonical(value))


def account_hour(source,*,assessed_at,start,end,source_epoch):
    assessed,start,end=map(utc,(assessed_at,start,end))
    if source_epoch is not None:epoch(source_epoch)
    if not isinstance(source,dict) or set(source)!=FIELDS or source['schema']!=SCHEMA:raise ValueError('closed controller-output hour source required')
    expected=build_hour_source(rows=[(instant(at),raw) for at,raw in source['rows']],start=instant(source['window_start']),end=instant(source['window_end']),
        requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=source['item_id'],policy_raw=source['policy_raw'])
    if canonical(source)!=canonical(expected) or instant(source['window_start'])!=start or instant(source['window_end'])!=end or instant(source['received_at'])>assessed:
        raise ValueError('original controller-output identity or clocks differ')
    rows=[(instant(at),raw) for at,raw in source['rows']]
    out=dict(source_sha256=source['source_sha256'],status='unavailable',reason='ambiguous_source_sequence',known_controller_dc_kwh=None,covered_seconds=None,missing_seconds=None,coverage=None)
    if source_epoch is None:
        out['reason']='original_power_epoch_unavailable';return out
    # A producer restart is not silently equated with the original stream. The
    # new origin will bind its own epoch; this old comparison remains withheld.
    for at,raw in rows:
        record=parse_power_evidence(raw,at)
        if record is not None and record.stream_epoch!=source_epoch:
            out['reason']='original_power_epoch_differs';return out
    try:intervals=build_power_intervals(rows,'pv.output_power_w',start,end,cutover=policy_cutover(source['policy_raw']))
    except PowerSequenceError:return out
    value=account_power_intervals(intervals,window_start=start,window_end=end)
    out.update(status='accounted',reason=None,known_controller_dc_kwh=value.positive_kwh,covered_seconds=value.covered_seconds,missing_seconds=value.missing_seconds,coverage=value.coverage)
    return out


def capture_hour(*,connect,start,end,clock,remaining,policy_path):
    from household_snapshot import _read
    start,end=map(utc,(start,end));requested=utc(clock());remaining()
    if end-start!=timedelta(hours=1) or requested<end+timedelta(minutes=5):raise ValueError('mature controller-output hour required')
    policy=_read(policy_path,4096);policy_raw=policy.decode();policy_cutover(policy_raw)
    connection=connect(remaining=remaining)
    try:
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='2000ms'")
            cursor.execute("SET LOCAL lock_timeout='1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout='5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only original power transaction required')
            remaining();cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',('Power_Evidence_JSON',));mapping=cursor.fetchall()
            if len(mapping)!=1 or len(mapping[0])!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique original power Item required')
            item=mapping[0][0];remaining()
            cursor.execute(f'SELECT time,CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM public.item{item:04d} WHERE time>=%s AND time<%s ORDER BY time ASC LIMIT {MAX_ROWS+1}',(start-timedelta(seconds=120),end))
            rows=cursor.fetchall();remaining();received=clock()
            if _read(policy_path,4096)!=policy:raise ValueError('power policy changed during acquisition')
            return build_hour_source(rows=rows,start=start,end=end,requested_at=requested,received_at=received,item_id=item,policy_raw=policy_raw)
    finally:connection.close()
