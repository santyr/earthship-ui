"""Bounded read-only original detail receipts and native outcome rows.

No Item state write, current forecast fallback, model fit or permission change.
Private credential configuration and scheduled execution are separate layers.
"""
from datetime import datetime,timedelta,timezone
import json
from urllib.parse import urlencode
from urllib.request import Request,build_opener,ProxyHandler

from weather_temperature_reader import _utc as _instant
from weather_temperature_config import _object,_nonfinite
from weather_temperature_history import _fetch_rows
from thermal_model.capture_readers import BASES,ReadBudget,_NoRedirect

MAX_RESPONSE_BYTES=128*1024


def _clock():return datetime.now(timezone.utc)


class DetailReader:
    def __init__(self,*,base,token_reader,opener=None,clock=_clock):
        if base not in BASES:raise ValueError('fixed approved loopback REST base required')
        self.base=base;self.token_reader=token_reader;self.clock=clock
        self.opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open
        self.budget=ReadBudget(30,max_requests=4)
    def publication(self,origin):
        now=_instant(self.clock());start=_instant(origin['publication_started_at'])
        floor=start.replace(microsecond=start.microsecond//1000*1000)
        completed=_instant(origin['publication_completed_at']);end=min(now,completed+timedelta(minutes=5))
        state=origin['detail_state']
        if not start<=completed<=now or completed-start>timedelta(seconds=180) or not isinstance(state,str) or len(state.encode())>MAX_RESPONSE_BYTES:
            raise ValueError('bounded completed original publication required')
        token=self.token_reader()
        if not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(c)<32 for c in token):
            raise ValueError('bounded original token required')
        query=urlencode({'serviceId':'jdbc','starttime':floor.isoformat(),'endtime':end.isoformat()})
        url=self.base+'/persistence/items/Forecast_10Day_JSON?'+query
        request=Request(url,method='GET',headers={'Authorization':'Bearer '+token})
        timeout=self.budget.begin()
        with self.opener(request,timeout=timeout) as response:
            if hasattr(response,'geturl') and response.geturl()!=url:raise ValueError('redirect refused')
            raw=response.read(MAX_RESPONSE_BYTES+1)
        self.budget.remaining()
        if len(raw)>MAX_RESPONSE_BYTES:raise ValueError('bounded original receipt response required')
        payload=json.loads(raw,object_pairs_hook=_object,parse_constant=_nonfinite)
        if not isinstance(payload,dict) or payload.get('name')!='Forecast_10Day_JSON' or not isinstance(payload.get('data'),list) or len(payload['data'])>32:
            raise ValueError('fixed bounded original detail history required')
        matches=[]
        for row in payload['data']:
            if not isinstance(row,dict) or set(row)!={'time','state'} or type(row['time']) is not int or not isinstance(row['state'],str):
                raise ValueError('closed original detail receipt row required')
            try:at=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=row['time'])
            except OverflowError:raise ValueError('bounded original stored clock required') from None
            if not floor<=at<=end:raise ValueError('original stored clock outside requested interval')
            if row['state']==state:matches.append({'item':'Forecast_10Day_JSON','stored_at':at.isoformat(),'state':row['state']})
        if len(matches)!=1:raise ValueError('one exact original detail receipt required')
        return matches[0]


def native_rows(connection_factory,*,start,end,assessed_at,now):
    start,end,assessed,now=map(_instant,(start,end,assessed_at,now))
    if not timedelta(0)<end-start<=timedelta(minutes=5) or not end+timedelta(minutes=5)<=assessed<=now:
        raise ValueError('bounded mature original native interval required')
    # Existing fixed-Item reader enforces a stable read-only transaction,
    # 2s statement/1s lock deadlines, raw-byte SQL bounds and 10000-row cap.
    # This collector further refuses any packet over its tighter 512-row cap.
    rows=_fetch_rows(connection_factory,start,end)
    if len(rows)>512:raise ValueError('bounded original native packet required')
    result=[]
    for at,raw in rows:
        if not isinstance(raw,str) or len(raw.encode())>8192:
            # Oversize/NULL remains a refusal, never dropped to expose an older
            # healthy value through a missing invalid barrier.
            raise ValueError('complete original native barrier rows required')
        result.append([_instant(at).isoformat(),raw])
    return result
