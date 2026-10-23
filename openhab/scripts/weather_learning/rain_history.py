"""Bounded read-only raw counter acquisitions, including qualified refusals.

Persisted row clocks describe old receipts. Only the actual completed query
clock is observation availability. Importing this module performs no I/O.
"""
from dataclasses import dataclass,asdict
from datetime import datetime,timedelta,timezone
import json
from household_job_budget import AdmissionDeferred
from weather_rain_evidence import RainPolicy
from weather_rain_day import MAX_ROWS,MAX_BYTES as ROW_BYTES
from weather_rain_history import ITEM
from .contracts import canonical,identity,instant
from .rain_calibration import make_observation,_policy,MAX_BYTES
from .rain_two_part import _clock

SCHEMA='earthship-original-rain-counter-acquisition/v1'
REQUEST={'start','end','cutover','requested_at','received_at','policy'}
SOURCE={'observations','resolution_source','experiment_policy','transport_status','transport_error_type'}
FIELDS={'schema','source_item','request','sources','status','reason','observation_sha256','continuous_depth_mm','boundary_uncertainty_mm','resolution_status','physical_calibration_qualified','automatic_actuation','acquisition_sha256'}


def _derive(request,sources):
    if not isinstance(request,dict) or set(request)!=REQUEST or not isinstance(sources,dict) or set(sources)!=SOURCE:raise ValueError('closed raw counter acquisition required')
    policy=RainPolicy(**request['policy']);experiment=_policy(sources['experiment_policy']);start,end,cutover,requested,received=map(instant,(request['start'],request['end'],request['cutover'],request['requested_at'],request['received_at']))
    if not start<end<=start+timedelta(hours=25) or received<requested:raise ValueError('bounded positive counter interval and actual clocks required')
    rows=sources['observations'];transport=sources['transport_status'];error=sources['transport_error_type']
    if (transport not in ('not_queried','complete_read_only_repeatable_read','unavailable') or not isinstance(rows,list) or len(rows)>MAX_ROWS+2 or
        error is not None and (not isinstance(error,str) or not 1<=len(error)<=80) or transport=='not_queried' and rows):raise ValueError('bounded original raw acquisition state required')
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('original counter row pair required')
        at,raw=row
        if at is not None:instant(at)
        if raw is not None and (not isinstance(raw,str) or len(raw.encode())>ROW_BYTES):raise ValueError('bounded literal counter row required')
    result=dict(schema=SCHEMA,source_item=ITEM,request=request,sources=sources,status='withheld',reason=None,observation_sha256=None,continuous_depth_mm=None,boundary_uncertainty_mm=None,resolution_status='not_assessed',physical_calibration_qualified=False,automatic_actuation=False)
    observation=None
    if not cutover<=start or requested<end+timedelta(seconds=policy.validity_seconds):result['reason']='interval_before_cutover_or_not_mature'
    elif received-requested>timedelta(seconds=15):result['reason']='actual_acquisition_duration_exceeds_fifteen_seconds'
    elif transport!='complete_read_only_repeatable_read':result['reason']='raw_counter_transport_unavailable'
    elif error is not None:raise ValueError('completed counter acquisition cannot retain a transport error')
    else:
        try:
            observation=make_observation(start=start,end=end,requested_at=requested,received_at=received,cutover=cutover,observations=[(instant(at),raw) for at,raw in rows],policy=policy,resolution_source=sources['resolution_source'],experiment_policy=experiment)
            value=observation.to_dict();result.update(status='qualified',reason=None,observation_sha256=value['observation_sha256'],continuous_depth_mm=value['observed_mm'],boundary_uncertainty_mm=value['boundary_uncertainty_mm'],resolution_status=value['resolution_status'])
        except (ValueError,TypeError,KeyError) as fault:result['reason']='native_counter_qualification_refused: '+str(fault)[:160]
    result['acquisition_sha256']=identity(result);return result,observation


@dataclass(frozen=True)
class RainAcquisition:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded original counter acquisition required')
        value=json.loads(self.content)
        if not isinstance(value,dict) or set(value)!=FIELDS or canonical(_derive(value['request'],value['sources'])[0])!=canonical(value):raise ValueError('counter acquisition differs from its original sources')
    def to_dict(self):return json.loads(self.content)
    def observation(self):
        value=self.to_dict();return _derive(value['request'],value['sources'])[1]


def read_interval(connection_factory,*,start,end,cutover,policy,resolution_source,experiment_policy,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    """One dedicated RR/SELECT acquisition, no legacy numeric fallback or writes.

    Transport and native quality failures retain the bounded returned originals.
    Global cancellation/admission/deadline failures remain owner-level stops.
    """
    start,end,cutover=map(_clock,(start,end,cutover));experiment_policy=_policy(experiment_policy)
    if not callable(connection_factory) or not isinstance(policy,RainPolicy) or not start<end<=start+timedelta(hours=25):raise ValueError('bounded native counter acquisition context required')
    guard();requested=_clock(clock());rows=[];connection=None;transport='not_queried';error=None
    if cutover<=start and requested>=end+timedelta(seconds=policy.validity_seconds):
        try:
            connection=connection_factory();guard()
            if connection.get_transaction_status()!=0:raise ValueError('dedicated idle connection required')
            connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
            with connection.cursor() as cursor:
                def execute(sql,params=None):
                    guard();cursor.execute(sql,params);guard()
                execute("SET LOCAL statement_timeout = '2000ms'")
                execute("SET LOCAL lock_timeout = '1000ms'")
                execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
                execute('SHOW transaction_read_only')
                if cursor.fetchone()!=('on',):raise ValueError('read-only transaction required')
                execute('SHOW transaction_isolation')
                if cursor.fetchone()!=('repeatable read',):raise ValueError('stable snapshot required')
                execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',(ITEM,));matches=cursor.fetchall()
                if len(matches)!=1 or type(matches[0][0]) is not int or not 0<=matches[0][0]<=2147483647:raise ValueError('unique native rain Item mapping required')
                table=f'public.item{matches[0][0]:04d}';value=f'CASE WHEN octet_length(value::text) <= {ROW_BYTES} THEN value::text ELSE NULL END'
                execute(f'SELECT time, {value} FROM {table} WHERE time < %s ORDER BY time DESC LIMIT 1',(start,));carry=cursor.fetchone()
                if carry is not None:rows.append(carry)
                execute(f'SELECT time, {value} FROM {table} WHERE time >= %s AND time <= %s ORDER BY time LIMIT {MAX_ROWS+1}',(start,end+timedelta(seconds=policy.validity_seconds)));rows.extend(cursor.fetchall())
                if len(rows)>MAX_ROWS+2:raise ValueError('bounded driver row response required')
            transport='complete_read_only_repeatable_read'
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception as fault:transport='unavailable';error=type(fault).__name__[:80]
        finally:
            if connection is not None:
                try:connection.close() # rollback on close, never commit
                except Exception:pass
    guard();received=_clock(clock())
    # Preserve SQL NULLs as unknown originals. Never fill a missing counter.
    originals=[(None if at is None else _clock(at).isoformat(),raw) for at,raw in rows]
    request=dict(start=start.isoformat(),end=end.isoformat(),cutover=cutover.isoformat(),requested_at=requested.isoformat(),received_at=received.isoformat(),policy=asdict(policy));sources=dict(observations=originals,resolution_source=resolution_source,experiment_policy=experiment_policy,transport_status=transport,transport_error_type=error)
    return RainAcquisition(canonical(_derive(request,sources)[0]))
