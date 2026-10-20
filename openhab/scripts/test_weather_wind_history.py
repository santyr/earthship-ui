"""Fixed loopback wind history reads retain exact original evidence."""
from datetime import datetime,timedelta,timezone
from io import BytesIO
import json
from urllib.parse import urlparse,parse_qs
import pytest
from openhab_runtime_io import ReadBudget
from weather_learning.contracts import identity

START=datetime(2026,10,20,12,tzinfo=timezone.utc)

class Response(BytesIO):
    def __init__(self,raw,url):super().__init__(raw);self.url=url
    def geturl(self):return self.url

def source(rows=None,**changes):
    value=dict(name='AmbientWeatherWS2902A_WindSpeed',unit='mph',data=rows if rows is not None else [dict(time=int((START+timedelta(minutes=i)).timestamp()*1000),state='22.369362921 mph') for i in range(60)])
    return value|changes

def read(monkeypatch,payload=None,raw=None,redirect=False,budget=None):
    from weather_learning import wind_history
    times=iter([START+timedelta(hours=1,minutes=2),START+timedelta(hours=1,minutes=2,seconds=1)])
    monkeypatch.setattr(wind_history,'_clock',lambda:next(times))
    calls=[]
    def opener(request,timeout):
        calls.append((request,timeout));return Response(raw if raw is not None else json.dumps(payload or source()).encode(),'http://example.invalid/' if redirect else request.full_url)
    result=wind_history.read_wind_hour(start=START,assessed_at=START+timedelta(hours=1,minutes=1),budget=budget or ReadBudget(90,max_requests=32),opener=opener,token_reader=lambda:'synthetic-token')
    return result,calls

def test_fixed_get_range_unit_elapsed_mean_and_original_receive_clocks(monkeypatch):
    result,calls=read(monkeypatch);request,timeout=calls[0];url=urlparse(request.full_url);query=parse_qs(url.query)
    assert request.get_method()=='GET' and url.netloc=='127.0.0.1:8080'
    assert url.path=='/rest/persistence/items/AmbientWeatherWS2902A_WindSpeed'
    assert query==dict(serviceId=['jdbc'],starttime=['2026-10-20T11:58:00Z'],endtime=['2026-10-20T13:00:00Z'])
    assert timeout<=5 and result['value']==pytest.approx(10.) and result['measurement_health_qualified'] is False
    original=result['original'];assert json.loads(original['raw'])==source()
    assert result['source_sha256']==identity(original)
    assert original['requested_at']=='2026-10-20T13:02:00+00:00' and original['received_at']==result['available_at']=='2026-10-20T13:02:01+00:00'
    assert result['assessed_at']==result['available_at'] and 'synthetic-token' not in json.dumps(original)

@pytest.mark.parametrize('damage',['unit','item','redirect','bytes','order','rows','duplicate_json','future_row','point_unit'])
def test_rejects_wrong_source_units_redirects_and_unbounded_or_unordered_payloads(monkeypatch,damage):
    payload=source();raw=None
    if damage=='unit':payload['unit']='m_s'
    if damage=='item':payload['name']='OtherItem'
    if damage=='bytes':raw=b'x'*(1048576+1)
    if damage=='order':payload['data']=list(reversed(payload['data']))
    if damage=='rows':payload['data']*=167
    if damage=='duplicate_json':raw=b'{"name":"x","name":"y","data":[]}'
    if damage=='future_row':payload['data'][-1]['time']=int((START+timedelta(hours=2)).timestamp()*1000)
    if damage=='point_unit':payload['data'][0]['state']='22 m/s'
    with pytest.raises(ValueError):read(monkeypatch,payload=payload,raw=raw,redirect=damage=='redirect')

def test_conflicting_duplicates_form_missing_barrier_instead_of_selecting_a_value(monkeypatch):
    payload=source();payload['data'][0:0]=[dict(time=payload['data'][0]['time'],state='1')]
    result,_=read(monkeypatch,payload=payload)
    assert result['coverage_seconds']==3540 and result['value']==pytest.approx(10.)
    payload['data'][1:1]=[dict(time=payload['data'][0]['time'],state='NULL')]
    result,_=read(monkeypatch,payload=payload);assert result['coverage_seconds']==3540

def test_budget_and_invalid_context_refuse_before_network_or_token(monkeypatch):
    from weather_learning import wind_history
    called=[]
    kwargs=dict(start=START,assessed_at=START+timedelta(minutes=30),budget=ReadBudget(90,max_requests=32),opener=lambda *a,**k:called.append('http'),token_reader=lambda:called.append('token'))
    with pytest.raises(ValueError):wind_history.read_wind_hour(**kwargs)
    kwargs.update(assessed_at=START+timedelta(hours=1),budget=ReadBudget(90,max_requests=33))
    with pytest.raises(ValueError):wind_history.read_wind_hour(**kwargs)
    assert called==[]
