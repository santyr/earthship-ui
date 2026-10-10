"""Read transport boundaries; all sources are fixtures, not release evidence."""
from datetime import datetime,timedelta,timezone
import importlib,importlib.util,io,json
import pytest
from test_weather_temperature_history import Connection

AT=datetime(2026,10,9,13,tzinfo=timezone.utc)
ORIGIN={'publication_started_at':AT.isoformat(),'publication_completed_at':(AT+timedelta(seconds=2)).isoformat(),'detail_state':'{"issued":"original"}'}


def module():
    assert importlib.util.find_spec('forecast_temperature_reads') is not None, 'missing bounded original transport'
    return importlib.import_module('forecast_temperature_reads')


class Response(io.BytesIO):
    def __init__(self,data,url):super().__init__(json.dumps(data).encode());self.url=url
    def geturl(self):return self.url


def reader(payload,*,redirect=False):
    requests=[]
    def open(request,timeout):
        requests.append(request)
        return Response(payload,'http://unexpected/' if redirect else request.full_url)
    value=module().DetailReader(base='http://127.0.0.1:8080/rest',token_reader=lambda:'fixture',opener=open,clock=lambda:AT+timedelta(minutes=10))
    return value,requests


def payload(state=None):return {'name':'Forecast_10Day_JSON','datapoints':1,'data':[{'time':int((AT+timedelta(seconds=1)).timestamp()*1000),'state':state or ORIGIN['detail_state']}]}


def test_requires_exact_original_bytes_and_only_fixed_jdbc_get():
    r,requests=reader(payload());receipt=r.publication(ORIGIN)
    assert receipt=={'item':'Forecast_10Day_JSON','stored_at':(AT+timedelta(seconds=1)).isoformat(),'state':ORIGIN['detail_state']}
    assert len(requests)==1 and requests[0].method=='GET'
    assert '/persistence/items/Forecast_10Day_JSON?' in requests[0].full_url and 'serviceId=jdbc' in requests[0].full_url


@pytest.mark.parametrize('damage',['whitespace','duplicate','wrong_item','future','oversized','redirect'])
def test_ambiguous_modified_or_unbounded_receipts_refused(damage):
    p=payload()
    if damage=='whitespace':p['data'][0]['state']+=' '
    elif damage=='duplicate':p['data']*=2
    elif damage=='wrong_item':p['name']='Other'
    elif damage=='future':p['data'][0]['time']=int((AT+timedelta(hours=1)).timestamp()*1000)
    elif damage=='oversized':p['padding']='x'*140000
    r,_=reader(p,redirect=damage=='redirect')
    with pytest.raises(ValueError):r.publication(ORIGIN)


def test_native_read_retains_original_raw_barriers_and_readonly_transaction():
    start=AT-timedelta(minutes=5);c=Connection(carry=(start-timedelta(seconds=1),'old'),rows=[(AT-timedelta(seconds=1),'invalid')])
    result=module().native_rows(lambda:c,start=start,end=AT,assessed_at=AT+timedelta(minutes=5),now=AT+timedelta(minutes=6))
    assert result==[[(start-timedelta(seconds=1)).isoformat(),'old'],[(AT-timedelta(seconds=1)).isoformat(),'invalid']]
    assert c.closed and c.session['readonly'] is True


def test_future_or_large_native_window_refused_before_connection():
    def forbidden():pytest.fail('invalid request opened a connection')
    m=module()
    for start,end,assessed in [(AT-timedelta(days=1),AT,AT+timedelta(minutes=5)),(AT-timedelta(minutes=5),AT,AT+timedelta(minutes=4)),(AT-timedelta(minutes=5),AT,AT+timedelta(days=1))]:
        with pytest.raises(ValueError):m.native_rows(forbidden,start=start,end=end,assessed_at=assessed,now=AT+timedelta(minutes=6))
