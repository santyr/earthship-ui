"""Private hourly power/AC/SoC originals and explicit provisional PV targets."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from math import fsum
from hashlib import sha256
import gzip,json,os,time
from uuid import uuid4
from .contracts import canonical,identity,instant
from weather_source_files import _read

ITEMS={'power':('Power_Evidence_JSON',6000),'ac':('Inverter_AC_Evidence_JSON',2000),'soc':('BMS_SOC_Evidence_JSON',1000)}
FIELDS={'schema','start','end','requested_at','received_at','policy_raw','bank_start','rows','items','automatic_actuation','source_sha256'}


def validate_source(value):
    from household_pv_window import policy_cutover
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!='earthship-historical-energy-hour/v1' or
        value['automatic_actuation'] is not False or value['source_sha256']!=identity({k:v for k,v in value.items() if k!='source_sha256'})):
        raise ValueError('original energy source identity differs')
    start,end=map(instant,(value['start'],value['end']));requested,received=map(instant,(value['requested_at'],value['received_at']))
    if (start.minute or start.second or start.microsecond or end-start!=timedelta(hours=1) or
        not end+timedelta(minutes=5)<=requested<=received or received-requested>timedelta(seconds=15) or
        set(value['rows'])!=set(ITEMS) or set(value['items'])!=set(ITEMS)):raise ValueError('bounded mature original energy hour required')
    policy_cutover(value['policy_raw']);instant(value['bank_start'])
    for role,rows in value['rows'].items():
        if not isinstance(rows,list) or len(rows)>ITEMS[role][1]:raise ValueError('bounded energy source rows required')
        previous=None
        for at,raw in rows:
            at=instant(at)
            if (not start-timedelta(seconds=120)<=at<end or previous is not None and at<=previous or
                raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096)):raise ValueError('ordered bounded energy rows required')
            previous=at
    return value


def capture_hour(root,start,*,connect,policy_raw,bank_start,clock=lambda:datetime.now(timezone.utc)):
    from household_native_training import directory
    root=directory(root);end=start+timedelta(hours=1);path=root/(start.strftime('%Y%m%dT%H')+'.energy.json.gz')
    if path.exists():
        with gzip.open(path,'rb') as stream:raw=stream.read(16*1024**2+1)
        if len(raw)>16*1024**2:raise ValueError('bounded energy hour required')
        value=validate_source(json.loads(raw))
        if value['start']!=start.isoformat() or value['policy_raw']!=policy_raw or value['bank_start']!=bank_start:raise ValueError('original energy context changed')
        return value,path
    requested=clock();deadline=time.monotonic()+14
    def remaining():
        left=deadline-time.monotonic()
        if left<1:raise TimeoutError('energy original acquisition deadline elapsed')
        return min(14.,left)
    connection=connect(remaining=remaining);rows={};items={}
    try:
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='2000ms'");cursor.execute("SET LOCAL lock_timeout='1000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout='5000ms'")
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only energy history required')
            for role,(name,limit) in ITEMS.items():
                remaining();cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',(name,));mapping=cursor.fetchall()
                if len(mapping)!=1 or len(mapping[0])!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:raise ValueError('unique energy source Item required')
                item=items[role]=mapping[0][0]
                cursor.execute(f'SELECT time,CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM public.item{item:04d} WHERE time>=%s AND time<%s ORDER BY time ASC LIMIT {limit+1}',(start-timedelta(seconds=120),end))
                rows[role]=[[at.astimezone(timezone.utc).isoformat(),raw] for at,raw in cursor.fetchall()];remaining()
    finally:connection.close()
    value=dict(schema='earthship-historical-energy-hour/v1',start=start.isoformat(),end=end.isoformat(),requested_at=requested.isoformat(),received_at=clock().isoformat(),
        policy_raw=policy_raw,bank_start=bank_start,rows=rows,items=items,automatic_actuation=False)
    value['source_sha256']=identity(value);validate_source(value);raw=canonical(value)
    if len(raw)>16*1024**2:raise ValueError('bounded energy original bytes required')
    temporary=path.with_name('.energy-'+uuid4().hex)
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(gzip.compress(raw,compresslevel=3,mtime=0));stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return value,path


def summarize_hour(source):
    from earthship_energy.power_evidence import build_power_intervals,PowerSequenceError
    from earthship_energy.ac_evidence import parse_ac_evidence,BOUNDS as AC_BOUNDS
    from earthship_energy.bms_evidence import build_soc_intervals,soc_at
    from household_pv_window import policy_cutover
    value=validate_source(source);start,end=map(instant,(value['start'],value['end']))
    rows={role:[(instant(at),raw) for at,raw in originals] for role,originals in value['rows'].items()}
    intervals={};problems={}
    for field in ('pv.input_power_w','pv.output_power_w','battery.dc_power_w','inverter.ac_output_w'):
        try:
            kwargs=dict(parser=parse_ac_evidence,bounds=AC_BOUNDS) if field=='inverter.ac_output_w' else {}
            role='ac' if kwargs else 'power';cutover=start-timedelta(seconds=120) if kwargs else policy_cutover(value['policy_raw'])
            intervals[field]=build_power_intervals(rows[role],field,start,end,cutover=cutover,**kwargs)
        except (ValueError,PowerSequenceError):intervals[field]=[];problems[field]='ambiguous_source_sequence'
    try:soc=build_soc_intervals(rows['soc'],start,end,epoch_start=instant(value['bank_start']))
    except ValueError:soc=[];problems['soc']='ambiguous_source_sequence'
    result=[]
    for i in range(12):
        left=start+timedelta(minutes=5*i);right=left+timedelta(minutes=5);fields={}
        for field,values in intervals.items():
            pieces=[(max(0.,(min(v.end,right)-max(v.start,left)).total_seconds()),v.watts) for v in values if v.start<right and left<v.end]
            fields[field]=dict(covered_seconds=fsum(s for s,w in pieces),positive_kwh=fsum(s*max(0,w) for s,w in pieces)/3600000,
                negative_kwh=fsum(s*max(0,-w) for s,w in pieces)/3600000)
        coverage=fsum(max(0.,(min(v.end,right)-max(v.start,left)).total_seconds()) for v in soc if v.start<right and left<v.end)
        samples=[soc_at(soc,at) for at in (left,left+timedelta(seconds=150),right-timedelta(microseconds=1))]
        qualified=coverage>=285 and all(v is not None for v in samples)
        output=fields['pv.output_power_w'];input_=fields['pv.input_power_w'];battery=fields['battery.dc_power_w']
        # This is an empirical censoring proxy, not proof of MPPT/charge mode.
        # 2400 W is below 60 A even at 40 V; leave certification false.
        eligible=(qualified and max(samples)<=90 and min(v['covered_seconds'] for v in (input_,output,battery))>=285 and
            100<=input_['positive_kwh']*3600000/input_['covered_seconds'] and
            output['positive_kwh']*3600000/output['covered_seconds']<2400 and
            battery['positive_kwh']>battery['negative_kwh'])
        result.append(dict(start=left.isoformat(),end=right.isoformat(),fields=fields,soc=samples if qualified else None,soc_covered_seconds=coverage,
            potential_proxy_eligible=bool(eligible),censoring_basis='low_soc_charging_below_controller_clip_proxy',physical_calibration_qualified=False,
            source_sha256=value['source_sha256'],problems=problems))
    return result
