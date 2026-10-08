"""Capture-only bounded read transports. No writes, fitting or default activation."""
from datetime import datetime,timedelta,timezone
import json
import math
from time import monotonic,sleep
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler

from psycopg2 import Error as DatabaseError
from psycopg2.extensions import parse_dsn,make_dsn
from .graduation_policy import _utc
from .origin_capture import _object
from .training_inputs import ITEMS,MAX_SERIES_POINTS,MAX_WINDOW_STEPS
from .temperature_history import STEP
from .environment_bundle import _pacer

MAX_RESPONSE_BYTES=1048576
MAX_HTTP_TOTAL_BYTES=32000000
CHUNK=65536
BASES={'http://127.0.0.1:8080/rest','http://localhost:8080/rest','http://127.0.0.1:5190/rest'}


class ReadBudget:
    def __init__(self,seconds,*,clock=monotonic,max_requests=512,min_request_interval=1,sleeper=sleep):
        if type(seconds) is not int or not 1<=seconds<=90 or type(max_requests) is not int or not 1<=max_requests<=512:
            raise ValueError('bounded read deadline and request count required')
        if type(min_request_interval) is not int or not 1<=min_request_interval<=5:
            raise ValueError('capture requests must be spaced by one to five seconds')
        self.clock=clock;self.deadline=clock()+seconds;self.max_requests=max_requests;self.requests=0
        self.interval=min_request_interval;self.sleeper=sleeper;self.next_request=None
    def remaining(self):
        value=self.deadline-self.clock()
        if value<=0:raise ValueError('capture read deadline exceeded')
        return value
    def begin(self):
        remaining=self.remaining()
        if self.requests>=self.max_requests:raise ValueError('capture request count exceeded')
        if self.next_request is not None:
            delay=max(0,self.next_request-self.clock())
            if delay>=remaining:raise ValueError('capture request pacing exceeds deadline')
            if delay:self.sleeper(delay)
            remaining=self.remaining()
            if self.clock()<self.next_request:raise ValueError('capture request pacing interrupted')
        self.next_request=self.clock()+self.interval
        self.requests+=1
        return min(5,remaining)
    def call(self,operation,*args,**kwargs):
        self.begin();value=operation(*args,**kwargs);self.remaining();return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('capture redirects refused')


class BoundedJDBCReader:
    def __init__(self,*,base,token_reader,budget,opener=None,max_read_bytes_per_second=1048576):
        if base not in BASES:raise ValueError('approved loopback OpenHAB endpoint required')
        if type(max_read_bytes_per_second) is not int or not 1<=max_read_bytes_per_second<=1048576:
            raise ValueError('capture read pacing must remain at or below 1 MiB per second')
        self.base=base;self.token_reader=token_reader;self.budget=budget
        self.opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open
        self.pace=_pacer(max_read_bytes_per_second);self.total_bytes=0;self.total_points=0
    def __call__(self,item,start,end):
        start,end=map(_utc,(start,end))
        if item not in ITEMS.values() or not start<end or end-start>MAX_WINDOW_STEPS*STEP:
            raise ValueError('bounded approved history request required')
        result=[];left=start
        while left<end:
            right=min(end,left+timedelta(days=1));self.budget.remaining()
            fmt='%Y-%m-%dT%H:%M:%SZ'
            # Query whole seconds outward; retain the exact half-open interval below.
            query_left=left.replace(microsecond=0)
            query_right=right.replace(microsecond=0)+(timedelta(seconds=1) if right.microsecond else timedelta())
            query=urlencode(dict(serviceId='jdbc',starttime=query_left.strftime(fmt),endtime=query_right.strftime(fmt)))
            url=self.base+'/persistence/items/'+item+'?'+query
            token=self.token_reader()
            if not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(char)<32 for char in token):raise ValueError('bounded token required')
            request=Request(url,headers={'Authorization':'Bearer '+token},method='GET')
            timeout=self.budget.begin()
            with self.opener(request,timeout=timeout) as response:
                if hasattr(response,'geturl') and response.geturl()!=url:raise ValueError('capture redirect refused')
                raw=[];count=0
                while True:
                    self.budget.remaining();size=min(CHUNK,MAX_RESPONSE_BYTES+1-count)
                    if self.pace is not None:self.pace.reserve(size)
                    self.budget.remaining();part=response.read(size)
                    if not part:break
                    count+=len(part);self.total_bytes+=len(part)
                    if count>MAX_RESPONSE_BYTES or self.total_bytes>MAX_HTTP_TOTAL_BYTES:raise ValueError('capture response byte bound exceeded')
                    raw.append(part)
            self.budget.remaining()
            def reject(_):raise ValueError('nonfinite capture response')
            payload=json.loads(b''.join(raw),object_pairs_hook=_object,parse_constant=reject)
            if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):raise ValueError('history response required')
            for point in payload['data']:
                if not isinstance(point,dict) or type(point.get('time')) not in (int,float) or not math.isfinite(point['time']):
                    raise ValueError('original history timestamp invalid')
                try:at=datetime.fromtimestamp(point['time']/1000,tz=timezone.utc)
                except (OverflowError,OSError,ValueError):raise ValueError('original history timestamp invalid') from None
                if not left<=at<right:continue
                raw_value=point.get('state')
                if not isinstance(raw_value,str) or len(raw_value)>256:raise ValueError('bounded original history state required')
                try:value=float(raw_value.split()[0])
                except (ValueError,IndexError):value=None
                if value is not None and not math.isfinite(value):value=None
                self.total_points+=1
                if self.total_points>MAX_SERIES_POINTS:raise ValueError('capture history point bound exceeded')
                result.append((at,value))
            left=right
        return result


def bounded_journal_dsn(dsn):
    try:params=parse_dsn(dsn)
    except (DatabaseError,TypeError):raise ValueError('invalid journal connection configuration') from None
    if (params.get('host')!='127.0.0.1' or str(params.get('port','5432'))!='5432' or
            params.get('dbname')!='openhab' or not params.get('user') or params['user']=='postgres' or not params.get('password') or
            any(key in params for key in ('hostaddr','service','passfile'))):
        raise ValueError('explicit restricted local journal endpoint required')
    params['hostaddr']='127.0.0.1';params['port']='5432'
    params['connect_timeout']='3'
    params['options']='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=10000'
    return make_dsn(**params)
