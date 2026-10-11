"""Read-only original power collection under one common household deadline."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import time
from .capture import collect_inputs
from .codec import canonical,loads,identity
from .evidence import epoch,utc
from .snapshot import build_snapshot
from .power_snapshot import SOURCES,POWER_ROLES,_policy,MAX_BYTES


def fetch_power_receipt(connection_factory,*,kind,start,end,remaining):
    if not isinstance(kind,str) or kind not in SOURCES:raise ValueError('fixed original power source required')
    start,end=utc(start),utc(end)
    if not timedelta(0)<end-start<=timedelta(seconds=120):raise ValueError('bounded original power query required')
    connection=None
    def check():
        value=remaining()
        if type(value) not in (int,float) or not .001<=value<=15.:raise ValueError('original power deadline elapsed')
        return min(2000,int(value*1000))
    try:
        check();connection=connection_factory(remaining=remaining);check()
        if connection.get_transaction_status()!=0:raise ValueError('dedicated idle power connection required')
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            def execute(query,params=None):
                cursor.execute('SET LOCAL statement_timeout = %s',(str(check())+'ms',));check()
                cursor.execute(query,params);check()
            execute("SET LOCAL lock_timeout = '1000ms'")
            execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only power transaction required')
            execute('SHOW transaction_isolation')
            if cursor.fetchone()!=('repeatable read',):raise ValueError('stable power transaction required')
            execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',(SOURCES[kind][0],))
            mapping=cursor.fetchall()
            if len(mapping)!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique original power mapping required')
            table=f'public.item{mapping[0][0]:04d}'
            execute(f'SELECT time, CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM {table} WHERE time >= %s AND time <= %s ORDER BY time DESC LIMIT 2',(start,end))
            rows=cursor.fetchall()
        check()
        if not isinstance(rows,list) or len(rows)>2:raise ValueError('bounded original power rows required')
        result=[]
        for row in rows:
            if not isinstance(row,(tuple,list)) or len(row)!=2:raise ValueError('exact original power row required')
            at,raw=row;at=utc(at)
            if not start<=at<=end or raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):
                raise ValueError('original power row outside bounds')
            result.append((at,raw))
        if len(result)==2 and result[0][0]<=result[1][0]:raise ValueError('ambiguous original power ordering')
        return result[0] if result else None
    except Exception:
        raise ValueError('original power query unavailable') from None
    finally:
        if connection is not None:
            try:connection.close()
            except Exception:raise ValueError('original power connection unavailable') from None


def collect_power_inputs(*,base_epochs,base_policy,power_epochs,power_policy,receipt_reader,native_reader,power_reader,
                         clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    started=utc(clock());deadline=monotonic()+15.
    if not isinstance(power_epochs,dict) or not 1<=len(power_epochs)<=2 or any(kind not in SOURCES for kind in power_epochs):
        raise ValueError('explicit fixed power source bindings required')
    power_epochs={kind:epoch(value) for kind,value in power_epochs.items()}
    base_policy=loads(canonical(base_policy));power_policy=loads(canonical(power_policy))
    build_snapshot([],as_of=started,created_at=started,code_revision='0'*40,config_revision=identity(base_policy),**base_policy)
    policy=_policy(power_policy,base_policy)
    if any(role not in policy['max_age_seconds'] for role,(kind,_) in POWER_ROLES.items() if kind in power_epochs):
        raise ValueError('collected power role lacks age policy')
    def remaining():
        value=deadline-monotonic()
        if not .001<=value<=15.:raise ValueError('common household deadline elapsed')
        return value
    first=True
    def base_clock():
        nonlocal first
        if first:first=False;return started
        return clock()
    def bounded_receipt(role,start,end,inner):
        return receipt_reader(role,start,end,lambda:min(remaining(),inner()))
    def bounded_native(**request):
        inner=request['remaining_timeout'];request['remaining_timeout']=lambda:min(remaining(),inner())
        return native_reader(**request)
    remaining()
    base=collect_inputs(epochs=base_epochs,policy=base_policy,receipt_reader=bounded_receipt,native_reader=bounded_native,
                        clock=base_clock,monotonic=monotonic)
    remaining();sources=[]
    for kind in sorted(power_epochs):
        remaining();row=power_reader(kind,started-timedelta(seconds=120),started,remaining)
        if row is None:persisted,raw=started,None
        else:
            if not isinstance(row,(tuple,list)) or len(row)!=2:raise ValueError('exact original power row required')
            persisted,raw=row;persisted=utc(persisted)
            if not started-timedelta(seconds=120)<=persisted<=started or raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):
                raise ValueError('original power receipt outside bounds')
        sources.append(dict(kind=kind,source_identity=SOURCES[kind][0],expected_epoch=power_epochs[kind],
            expected_sha256=None if raw is None else sha256(raw.encode()).hexdigest(),persisted_at=persisted.isoformat(),raw=raw))
        remaining()
    finished=utc(clock());remaining()
    if finished<started or finished-started>timedelta(seconds=15):raise ValueError('common household clock changed')
    base.update(as_of=finished.isoformat(),created_at=finished.isoformat())
    result=dict(schema='earthship-household-power-inputs/v1',base_inputs=base,power_sources=sources,power_policy=power_policy)
    if len(canonical(result))>MAX_BYTES:raise ValueError('bounded original household inputs required')
    return result
