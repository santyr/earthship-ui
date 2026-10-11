"""Original atomic whole-night evidence; pure replay grants no action authority."""
from datetime import date,datetime,timedelta
import math,re
from hashlib import sha256
from .codec import canonical,loads,identity
from .evidence import utc,epoch
from .control_contracts import instant
from advisory_windows import trough_window,local_day_window
from earthship_energy.bms_evidence import parse_evidence
from earthship_energy.trough_assessment import assess_trough_measurement,MAX_OBSERVATIONS

MAX_BYTES=4*1024*1024
FIELDS={'schema','source_identity','prediction_day','site_timezone','assessed_at','bank_config_raw',
        'bank_config_sha256','expected_bank_epoch','expected_stream_epoch','owner_binding','rows','assessment','source_sha256'}


def _bank(raw,expected):
    if not isinstance(raw,str) or len(raw.encode())>65536:raise ValueError('bounded original physical bank configuration required')
    value=loads(raw)
    if (not isinstance(value,dict) or set(value)!={'version','timezone','epochs'} or type(value['version']) is not int or
        value['version']!=1 or value['timezone']!='America/Denver' or not isinstance(value['epochs'],list) or not 1<=len(value['epochs'])<=32):
        raise ValueError('original physical bank configuration differs')
    parsed=[];ids=set();current=0
    def day(text):
        if text is None:return None
        if not isinstance(text,str):raise ValueError('physical boundary date required')
        result=date.fromisoformat(text)
        if result.isoformat()!=text:raise ValueError('canonical physical boundary date required')
        return result
    for row in value['epochs']:
        if not isinstance(row,dict) or not {'id','start_local_date','end_local_date_exclusive','current_analytics'}<=set(row):
            raise ValueError('complete original physical bank row required')
        name=row['id']
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',name) or name in ids:
            raise ValueError('unique physical bank identity required')
        ids.add(name);start,end=day(row['start_local_date']),day(row['end_local_date_exclusive'])
        if end is not None and start is not None and end<=start:raise ValueError('ordered physical bank boundaries required')
        if type(row['current_analytics']) is not bool:raise ValueError('explicit current bank flag required')
        current+=row['current_analytics']
        for key in ('nominal_capacity_ah','nominal_usable_kwh'):
            number=row.get(key)
            if number is not None and (type(number) not in (int,float) or not math.isfinite(number) or not 0<number<=10000):
                raise ValueError('bounded physical bank capacity required')
        parsed.append((name,start,end))
    if current!=1:raise ValueError('one current physical bank required')
    ordered=sorted(parsed,key=lambda item:item[1] or date.min)
    for left,right in zip(ordered,ordered[1:]):
        if left[2] is None or right[1] is None or right[1]<left[2]:raise ValueError('physical bank intervals overlap')
    selected=next((row for row in parsed if row[0]==expected),None)
    if selected is None or selected[1] is None:raise ValueError('independently bound physical bank start required')
    return (local_day_window(selected[1],'America/Denver').start,
            None if selected[2] is None else local_day_window(selected[2],'America/Denver').start)


def _owner_binding(value,phase,assessed):
    if value is None:return
    if (not isinstance(value,dict) or set(value)!={'source_identity','raw','sha256','available_at'} or
        value['source_identity']!='BMS_SOC_Evidence_JSON' or not isinstance(value['raw'],str) or len(value['raw'].encode())>4096 or
        sha256(value['raw'].encode()).hexdigest()!=value['sha256']):raise ValueError('exact independent owner receipt required')
    available=instant(value['available_at']);record=parse_evidence(value['raw'],available)
    if (record is None or record.status!='valid' or record.stream_epoch!=phase or
        not record.recorded_at<=available<=assessed<record.valid_until):
        raise ValueError('fresh independently bound owner stream required')


def build_night_source(*,rows,prediction_day,assessed_at,bank_config_raw,expected_bank_epoch,expected_stream_epoch,owner_binding=None):
    if not isinstance(prediction_day,date) or isinstance(prediction_day,datetime):raise ValueError('explicit prediction day required')
    assessed=utc(assessed_at);phase=epoch(expected_stream_epoch)
    _owner_binding(owner_binding,phase,assessed)
    start,end=_bank(bank_config_raw,expected_bank_epoch);window=trough_window(prediction_day,'America/Denver')
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_OBSERVATIONS:raise ValueError('bounded whole-night original rows required')
    originals=[];previous=None;total=len(bank_config_raw.encode())
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('exact original persistence row required')
        at,raw=row;at=utc(at)
        if not window.start-timedelta(seconds=120)<=at<window.end or at>assessed or previous is not None and at<=previous:
            raise ValueError('ordered original night query clocks required')
        if raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):raise ValueError('bounded raw atomic evidence required')
        total+=0 if raw is None else len(raw.encode())
        if total>MAX_BYTES:raise ValueError('whole-night original byte limit exceeded')
        record=parse_evidence(raw,at) if raw is not None else None
        if record is not None and record.stream_epoch!=phase:raise ValueError('original atomic stream differs from independent binding')
        originals.append((at,raw));previous=at
    assessment=assess_trough_measurement(prediction_day=prediction_day,site_timezone='America/Denver',assessed_at=assessed,
        observations=[(at,'null' if raw is None else raw) for at,raw in originals],epoch_start=start,epoch_end=end)
    if start>window.start or end is not None and end<window.end:
        assessment.update(status='insufficient_data',reason='physical_bank_window_mismatch',min_soc_pct=None)
    value=dict(schema='earthship-household-energy-night-source/v1',source_identity='BMS_SOC_Evidence_JSON',
        prediction_day=prediction_day.isoformat(),site_timezone='America/Denver',assessed_at=assessed.isoformat(),
        bank_config_raw=bank_config_raw,bank_config_sha256=sha256(bank_config_raw.encode()).hexdigest(),
        expected_bank_epoch=expected_bank_epoch,expected_stream_epoch=phase,owner_binding=owner_binding,rows=[(at.isoformat(),raw) for at,raw in originals],assessment=assessment)
    value['source_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original night packet required')
    return loads(canonical(value))


def replay_night_source(packet):
    if (not isinstance(packet,dict) or set(packet)!=FIELDS or packet['schema']!='earthship-household-energy-night-source/v1' or
        packet['source_identity']!='BMS_SOC_Evidence_JSON' or packet['site_timezone']!='America/Denver' or len(canonical(packet))>MAX_BYTES):
        raise ValueError('closed original whole-night packet required')
    if not isinstance(packet['rows'],list) or len(packet['rows'])>MAX_OBSERVATIONS:raise ValueError('bounded original night rows required')
    for row in packet['rows']:
        if not isinstance(row,list) or len(row)!=2:raise ValueError('exact retained night row required')
    rebuilt=build_night_source(rows=[(instant(at),raw) for at,raw in packet['rows']],prediction_day=date.fromisoformat(packet['prediction_day']),
        assessed_at=instant(packet['assessed_at']),bank_config_raw=packet['bank_config_raw'],
        expected_bank_epoch=packet['expected_bank_epoch'],expected_stream_epoch=packet['expected_stream_epoch'],owner_binding=packet['owner_binding'])
    if canonical(rebuilt)!=canonical(packet):raise ValueError('rederived whole-night evidence differs')
    return rebuilt['assessment']


def fetch_night_source(connection_factory,*,prediction_day,assessed_at,bank_config_raw,expected_bank_epoch,expected_stream_epoch,remaining,owner_binding=None):
    """One fixed bounded read-only query; incomplete nights do not acquire rows."""
    args=dict(prediction_day=prediction_day,assessed_at=assessed_at,bank_config_raw=bank_config_raw,
        expected_bank_epoch=expected_bank_epoch,expected_stream_epoch=expected_stream_epoch,owner_binding=owner_binding)
    empty=build_night_source(rows=[],**args);window=trough_window(prediction_day,'America/Denver')
    if not window.is_complete(assessed_at):return empty
    connection=None
    def check():
        value=remaining()
        if type(value) not in (int,float) or not 0.001<=value<=15:raise ValueError('bounded source acquisition deadline required')
        return min(2000,int(value*1000))
    try:
        check();connection=connection_factory();check()
        if connection.get_transaction_status()!=0:raise ValueError('dedicated idle source connection required')
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            def execute(query,params=None):
                cursor.execute('SET LOCAL statement_timeout = %s',(str(check())+'ms',));check()
                cursor.execute(query,params);check()
            execute("SET LOCAL lock_timeout = '1000ms'")
            execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only night transaction required')
            execute('SHOW transaction_isolation')
            if cursor.fetchone()!=('repeatable read',):raise ValueError('stable original night transaction required')
            execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',('BMS_SOC_Evidence_JSON',))
            mapping=cursor.fetchall()
            if len(mapping)!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique fixed atomic Item mapping required')
            table=f'public.item{mapping[0][0]:04d}'
            execute(f'SELECT time, CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END, octet_length(value::text) FROM {table} WHERE time >= %s AND time < %s ORDER BY time LIMIT 10001',
                (window.start-timedelta(seconds=120),window.end))
            selected=cursor.fetchall()
        check()
        if not isinstance(selected,list) or len(selected)>MAX_OBSERVATIONS:raise ValueError('bounded complete night rows required')
        rows=[]
        for row in selected:
            if not isinstance(row,(list,tuple)) or len(row)!=3:raise ValueError('complete original database row required')
            at,raw,size=row
            if raw is None:
                if size is not None:raise ValueError('oversized original night row refused')
            elif not isinstance(raw,str) or type(size) is not int or size!=len(raw.encode()) or size>4096:
                raise ValueError('original night byte size differs')
            rows.append((at,raw))
        result=build_night_source(rows=rows,**args);check();return result
    except Exception:
        raise ValueError('Original energy night acquisition refused.') from None
    finally:
        if connection is not None:connection.close()
