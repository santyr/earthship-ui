from datetime import timedelta
import pytest
from weather_learning.tests.learning_fixtures import T


def api():
 from weather_learning import numeric_history
 return numeric_history


def test_legacy_state_is_labeled_as_unqualified_numeric_history_without_fake_receipt_clocks():
 rows=[(T,70.),(T+timedelta(hours=1),72.)]
 targets=[T+timedelta(minutes=5),T+timedelta(minutes=45),T+timedelta(hours=1,minutes=5)]
 values=api().temperature_targets(rows,targets,item='AmbientWeatherWS2902A_IndoorSensor_Temperature',source_sha256='a'*64,unit='F')
 assert values[0]['temperatureF']==70
 assert values[0]['provenance']=='persisted_numeric_state'
 assert values[0]['receivedAt'] is None and values[0]['sensorEpoch'] is None
 assert values[1] is None
 assert values[2]['temperatureF']==72


def test_unit_inference_uses_receipt_overlap_rather_than_winter_temperature_ranges():
 targets=[T+timedelta(minutes=5*i) for i in range(1,5)]
 rows=[(at,20.+i) for i,at in enumerate(targets)]
 labels={at.isoformat():dict(temperatureF=(20.+i)*9/5+32) for i,at in enumerate(targets)}
 unit=api().infer_temperature_unit(rows,labels)
 assert unit['unit']=='C'
 assert unit['pairs']==4
 assert unit['mae_f']==pytest.approx(0)
 assert api().infer_temperature_unit(rows,{})['unit'] is None


def test_numeric_barrier_or_missing_time_never_becomes_zero_or_a_fresh_reading():
 rows=[(T,70.),(T+timedelta(minutes=1),None)]
 values=api().temperature_targets(rows,[T+timedelta(minutes=2)],item='AmbientWeatherWS2902A_IndoorSensor_Temperature',source_sha256='a'*64,unit='F')
 assert values==[None]


def test_numeric_capture_keeps_original_bodies_and_replays_without_network(tmp_path,monkeypatch):
 from weather_learning.numeric_history import capture_numeric_day,original_series
 from weather_learning.tests.learning_fixtures import SITE
 import urllib.request,io,json
 from urllib.parse import urlsplit,unquote
 calls=[]
 class Response(io.BytesIO):
  def geturl(self):return self.url
 def open_request(request,timeout):
  calls.append(request.full_url)
  item=unquote(urlsplit(request.full_url).path.split('/')[-1])
  raw=json.dumps(dict(name=item,data=[dict(time=int((T+timedelta(hours=1)).timestamp()*1000),state='70.0')])).encode()
  response=Response(raw);response.url=request.full_url;return response
 class Opener:open=staticmethod(open_request)
 monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
 kw=dict(site=SITE.__dict__,token_reader=lambda:'unused',clock=lambda:T+timedelta(days=2))
 first=capture_numeric_day(tmp_path,'2026-01-01',**kw)
 second=capture_numeric_day(tmp_path,'2026-01-01',**kw)
 assert len(calls)==4 and first==second
 assert original_series(first,'air')==[(T+timedelta(hours=1),70.)]
 assert len(list(tmp_path.glob('*.numeric-source.json.gz')))==1


def test_conflicting_millisecond_states_become_a_barrier_not_an_arbitrary_value():
 from weather_learning.numeric_history import original_series
 from weather_learning.contracts import identity
 import json
 from thermal_model.schema import THERMAL_ITEMS
 raw=json.dumps(dict(name=THERMAL_ITEMS['air'],data=[dict(time=T.timestamp()*1000,state='70'),dict(time=T.timestamp()*1000,state='71'),dict(time=(T+timedelta(minutes=1)).timestamp()*1000,state='72')]))
 source=dict(start=T.isoformat(),end=(T+timedelta(days=1)).isoformat(),originals=dict(air=[dict(raw=raw)]))
 source['source_sha256']=identity(source)
 assert original_series(source,'air')==[(T,None),(T+timedelta(minutes=1),72.)]
