"""One fixed, read-only station wind history target; no sensor-health claim."""
from datetime import datetime,timedelta,timezone
import json
from urllib.parse import urlencode
from urllib.request import Request,build_opener,ProxyHandler
from openhab_runtime_io import ReadBudget,_NoRedirect
from thermal_model.environment_bundle import _pacer
from thermal_model.origin_capture import _object
from .contracts import finite,identity
from .evidence import utc
from .openhab import auth_token
from .correction_monitor import wind_outcome

ITEM='AmbientWeatherWS2902A_WindSpeed'
MAX_BYTES=1048576


def _clock():return datetime.now(timezone.utc)


def read_wind_hour(*,start,assessed_at,budget,opener=None,token_reader=auth_token):
    start,assessed_at=map(utc,(start,assessed_at));end=start+timedelta(hours=1)
    if start.minute or start.second or start.microsecond or not end<=assessed_at:raise ValueError('mature complete native wind hour required')
    if not isinstance(budget,ReadBudget) or budget.max_requests>32:raise ValueError('shared bounded wind read budget required')
    budget.remaining();token=token_reader();budget.remaining()
    if not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(c)<33 or ord(c)==127 for c in token):raise ValueError('bounded wind token required')
    left=start-timedelta(seconds=120);fmt='%Y-%m-%dT%H:%M:%SZ'
    query=urlencode(dict(serviceId='jdbc',starttime=left.strftime(fmt),endtime=end.strftime(fmt)))
    url='http://127.0.0.1:8080/rest/persistence/items/'+ITEM+'?'+query
    request=Request(url,headers={'Authorization':'Bearer '+token},method='GET')
    opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open
    timeout=budget.begin();requested=utc(_clock())
    if requested<assessed_at:raise ValueError('future wind assessment refused')
    parts=[];count=0;pace=_pacer(MAX_BYTES)
    with opener(request,timeout=timeout) as response:
        if not hasattr(response,'geturl') or response.geturl()!=url or getattr(response,'status',200)!=200:raise ValueError('wind response redirect or status refused')
        while True:
            budget.remaining();size=min(65536,MAX_BYTES+1-count);pace.reserve(size);budget.remaining()
            part=response.read(size)
            if not part:break
            count+=len(part)
            if count>MAX_BYTES:raise ValueError('wind response byte bound exceeded')
            parts.append(part)
    budget.remaining();received=utc(_clock())
    if received<requested:raise ValueError('wind response clock moved backwards')
    raw=b''.join(parts).decode()
    def reject(_):raise ValueError('nonfinite wind response refused')
    payload=json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
    if (not isinstance(payload,dict) or payload.get('name')!=ITEM or payload.get('unit')!='mph' or
        not isinstance(payload.get('data'),list) or len(payload['data'])>10000):raise ValueError('bounded exact station mph history required')
    rows=[]
    for row in payload['data']:
        budget.remaining()
        if not isinstance(row,dict) or type(row.get('time')) not in (int,float) or not finite(row['time']):raise ValueError('finite original wind timestamp required')
        try:at=datetime.fromtimestamp(row['time']/1000,timezone.utc)
        except (ValueError,OverflowError,OSError):raise ValueError('bounded original wind timestamp required') from None
        if not left<=at<=end:raise ValueError('wind state outside original query')
        state=row.get('state')
        if not isinstance(state,str) or len(state)>128:raise ValueError('bounded original wind state required')
        words=state.split()
        if len(words)>2 or len(words)==2 and words[1]!='mph':raise ValueError('original wind state unit differs')
        try:value=float(words[0])
        except (ValueError,IndexError):value=None
        if not finite(value):value=None
        if rows and at<rows[-1][0]:raise ValueError('ordered original wind states required')
        if rows and at==rows[-1][0]:
            if rows[-1][1]!=value:rows[-1]=(at,None)
        else:rows.append((at,value))
    original=dict(schema='earthship-station-wind-http-source/v1',item=ITEM,unit='mph',query_start=left.isoformat(),query_end=end.isoformat(),
        assessment_started_at=assessed_at.isoformat(),requested_at=requested.isoformat(),received_at=received.isoformat(),raw=raw,automatic_actuation=False)
    result=wind_outcome(rows,start=start,assessed_at=received,source_available_at=received,unit='mph')
    if result is None:return None
    return result|dict(source_sha256=identity(original),original=original,unit='m_s')
