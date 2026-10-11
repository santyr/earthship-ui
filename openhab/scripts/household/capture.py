"""Bounded source collection. Produces offline inputs; never sends requests."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import time
from .codec import canonical, loads, identity
from .evidence import epoch, utc
from .snapshot import build_snapshot
from .replay import MAX_BYTES

RECEIPT_ITEMS={'battery_soc':'BMS_SOC_Evidence_JSON','pv_day_wh':'MPPT60_PV_Day_Evidence_JSON'}
NATIVE_ROLES={'air_temperature':'air','mass_temperature':'mass','outdoor_temperature':'outdoor'}


def collect_inputs(*,epochs,policy,receipt_reader,native_reader,
                   clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    """Freeze independently declared epochs, gather bounded originals, then assess.

    Readers receive a total deadline, not a renewed per-source allowance. A missing
    source is explicit; reader errors abort the collection rather than hide errors.
    """
    if not isinstance(epochs,dict) or not 1<=len(epochs)<=5 or any(role not in RECEIPT_ITEMS|NATIVE_ROLES for role in epochs):
        raise ValueError('explicit fixed source bindings required')
    epochs={role:epoch(value) for role,value in epochs.items()}
    if not isinstance(policy,dict) or set(policy)!={'requirements','max_age_seconds','max_skew_seconds'}:
        raise ValueError('closed temporal policy required')
    policy=loads(canonical(policy))
    started=utc(clock());deadline=monotonic()+15.0
    build_snapshot([],as_of=started,created_at=started,code_revision='0'*40,config_revision=identity(policy),**policy)
    if any(role not in policy['max_age_seconds'] for role in epochs):raise ValueError('collected role lacks age policy')
    def remaining():
        value=deadline-monotonic()
        if not 0.001<=value<=15.0:raise ValueError('collection deadline elapsed or invalid')
        return value
    sources=[]
    for role in sorted(epochs):
        remaining()
        if role in RECEIPT_ITEMS:
            row=receipt_reader(role,started-timedelta(seconds=120),started,remaining)
            if row is None:persisted,raw=started,None
            else:
                if not isinstance(row,(tuple,list)) or len(row)!=2:raise ValueError('exact persisted receipt required')
                persisted,raw=row;persisted=utc(persisted)
                if not started-timedelta(seconds=120)<=persisted<=started:raise ValueError('persisted receipt outside query window')
                if raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):raise ValueError('bounded original receipt required')
            kind=role;source_identity=RECEIPT_ITEMS[role];persisted=persisted.isoformat()
        else:
            from thermal_model.temperature_history import STREAMS,POLICY
            from weather_temperature_evidence import TemperaturePolicy
            from weather_temperature_sources import replay_temperature_source
            stream,model,sensor_id=STREAMS[NATIVE_ROLES[role]]
            request=dict(stream=stream,policy=TemperaturePolicy(model,sensor_id,**POLICY),sensor_epoch=epochs[role],targets=[started],assessed_at=started)
            packet=native_reader(remaining_timeout=remaining,**request)
            replay_temperature_source(packet)
            if (packet['stream']!=stream or packet['sensor_epoch']!=epochs[role] or packet['policy']!=dict(model=model,sensor_id=sensor_id,**POLICY)
                or packet['targets']!=[started.isoformat()] or packet['assessed_at']!=started.isoformat()):
                raise ValueError('original native query binding differs')
            raw=canonical(packet).decode();kind='native_temperature';source_identity='Weather_Temperature_Evidence_JSON:'+stream;persisted=None
        if raw is not None and len(raw.encode())>MAX_BYTES:raise ValueError('original source byte budget exceeded')
        sources.append(dict(kind=kind,source_role=role,source_identity=source_identity,expected_epoch=epochs[role],
            expected_sha256=None if raw is None else sha256(raw.encode()).hexdigest(),persisted_at=persisted,raw=raw))
        if sum(len(row['raw'].encode()) for row in sources if row['raw'] is not None)>MAX_BYTES:raise ValueError('original collection byte budget exceeded')
        remaining()
    finished=utc(clock());remaining()
    if finished<started or finished-started>timedelta(seconds=15):raise ValueError('collection clock changed or elapsed')
    bundle=dict(schema='earthship-household-inputs/v1',as_of=finished.isoformat(),created_at=finished.isoformat(),policy=policy,sources=sources)
    if len(canonical(bundle))>MAX_BYTES:raise ValueError('original collection byte budget exceeded')
    return bundle


def fetch_receipt(connection_factory,*,role,start,end,remaining):
    """Fixed Item, private stable read-only transaction; NULL remains a barrier."""
    if role not in RECEIPT_ITEMS:raise ValueError('unsupported source role')
    start,end=utc(start),utc(end)
    if not timedelta(0)<end-start<=timedelta(seconds=120):raise ValueError('bounded receipt query window required')
    connection=None
    def check():
        value=remaining()
        if type(value) not in (int,float) or not 0.001<=value<=15:raise ValueError('source query deadline elapsed')
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
            if cursor.fetchone()!=('on',):raise ValueError('read-only source transaction required')
            execute('SHOW transaction_isolation')
            if cursor.fetchone()!=('repeatable read',):raise ValueError('stable source transaction required')
            execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',(RECEIPT_ITEMS[role],))
            mapping=cursor.fetchall()
            if len(mapping)!=1 or type(mapping[0][0]) is not int or not 0<=mapping[0][0]<=2147483647:
                raise ValueError('unique original Item mapping required')
            table=f'public.item{mapping[0][0]:04d}'
            execute(f'SELECT time, CASE WHEN octet_length(value::text)<=4096 THEN value::text ELSE NULL END FROM {table} WHERE time >= %s AND time <= %s ORDER BY time DESC LIMIT 2',(start,end))
            rows=cursor.fetchall()
        check()
        if not isinstance(rows,list) or len(rows)>2:raise ValueError('bounded original rows required')
        normalized=[]
        for row in rows:
            if not isinstance(row,(tuple,list)) or len(row)!=2:raise ValueError('exact original row required')
            at,raw=row;at=utc(at)
            if not start<=at<=end or raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):
                raise ValueError('source row outside bounds')
            normalized.append((at,raw))
        if len(normalized)==2 and normalized[0][0]<=normalized[1][0]:raise ValueError('ambiguous or unordered latest original')
        return normalized[0] if normalized else None
    finally:
        if connection is not None:connection.close()
