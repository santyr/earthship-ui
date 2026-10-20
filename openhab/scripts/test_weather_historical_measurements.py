from datetime import datetime,timedelta,timezone
import json
import pytest
from weather_temperature_evidence import TemperaturePolicy,temperature_receipt

AT=datetime(2026,9,20,12,tzinfo=timezone.utc)
POLICY=TemperaturePolicy('Fineoffset-WH32B',235,-40,140,120)
EPOCH='831b737c-ab25-48d7-9a90-889746e56410'
PHASE='00000000-0000-4000-8000-000000000001'

def raw(at,value='70',version=1):
 r=temperature_receipt(dict(model=POLICY.model,id='235',tempinf=value),policy=POLICY,stream_epoch=EPOCH,received_at=at)
 r['version']=version
 if version==2:r['sensorEpoch']=PHASE
 return json.dumps(dict(version=version,streamEpoch=EPOCH,records=dict(indoor=r)))

def select(rows,targets):
 from weather_learning.historical_measurements import temperature_grid
 return temperature_grid(rows,targets=targets,assessed_at=AT+timedelta(days=1),policies=dict(indoor=POLICY),epochs=dict(indoor=PHASE))

def test_historical_receipt_versions_keep_their_actual_hardware_evidence():
 targets=[AT+timedelta(seconds=30),AT+timedelta(minutes=5,seconds=30)]
 values=select([(AT,raw(AT)),(AT+timedelta(minutes=5),raw(AT+timedelta(minutes=5),'72',2))],targets)
 old,new=values['indoor']
 assert old['temperatureF']==70;assert old['receiptVersion']==1;assert old['sensorEpoch'] is None
 assert new['temperatureF']==72;assert new['receiptVersion']==2;assert new['sensorEpoch']==PHASE
 assert old['sourceModel']=='Fineoffset-WH32B';assert old['sourceSensorId']==235
 assert old['snapshotSha256']!=new['snapshotSha256']


def test_missing_expired_or_invalid_receipts_are_not_imputed():
 targets=[AT+timedelta(seconds=30),AT+timedelta(minutes=3),AT+timedelta(minutes=5,seconds=30)]
 barrier=json.loads(raw(AT+timedelta(minutes=5),'75',2));barrier['records']['indoor']['sensorEpoch']='00000000-0000-4000-8000-000000000009'
 values=select([(AT,raw(AT)),(AT+timedelta(minutes=5),json.dumps(barrier))],targets)['indoor']
 assert values[0] is not None;assert values[1:] == [None,None]


def test_capture_keeps_raw_receipts_and_replays_without_querying_again(tmp_path,monkeypatch):
 from weather_learning.historical_measurements import capture_temperature_day
 import weather_temperature_history
 calls=[]
 def fetch(*args):calls.append(args);return [(AT,raw(AT))]
 monkeypatch.setattr(weather_temperature_history,'_fetch_rows',fetch)
 kwargs=dict(connection_factory=lambda:None,policies=dict(indoor=POLICY),epochs=dict(indoor=PHASE),clock=lambda:AT+timedelta(days=2))
 first=capture_temperature_day(tmp_path,'2026-09-20',**kwargs)
 second=capture_temperature_day(tmp_path,'2026-09-20',**kwargs)
 assert len(calls)==1
 assert first==second
 assert first['streams']['indoor'][144]['temperatureF']==70
 assert len(list(tmp_path.glob('*.temperature-source.json.gz')))==1
