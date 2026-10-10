"""Pure v2 receiver/reader integration; no services, DB or numerical fitting."""
from datetime import datetime,timedelta,timezone
import json
from flask import Flask
import pytest
from weather_temperature_evidence import TemperaturePolicy
from weather_temperature_receiver import TemperatureCollector
from weather_temperature_reader import select_temperature_at
import weather_temperature_reader as reader
from weather_temperature_config import configure_temperature_receiver,load_temperature_policies

AT=datetime(2026,10,8,12,tzinfo=timezone.utc)
SENSOR='d348bbfa-4108-4fdc-8319-6349cc54853b'
OTHER='415c5285-8039-4650-9c1d-73e76fb29612'
POLICY=TemperaturePolicy('Fineoffset-WH32B',235,-80,160,120)
PACKET={'model':POLICY.model,'id':'235','tempinf':'70'}


def collector():
    clock={'at':AT,'tick':1000,'pid':1}
    epochs={'indoor':SENSOR}
    source=TemperatureCollector({'indoor':POLICY},sensor_epochs=epochs,clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:clock['pid'])
    epochs['indoor']=OTHER
    return source,clock


def grid(rows,*,sensor_epoch=SENSOR,target=60):
    return reader.select_temperature_grid_v2(rows,targets=[AT+timedelta(seconds=target)],assessed_at=AT+timedelta(hours=1),history_start=AT-timedelta(minutes=5),stream='indoor',policy=POLICY,sensor_epoch=sensor_epoch)[0][1]


def test_restart_rotates_session_but_preserves_declared_sensor_phase_and_requires_new_packet():
    source,clock=collector();source.observe(PACKET);first=source.snapshot()
    clock.update(at=AT+timedelta(seconds=30),tick=1030,pid=2)
    empty=source.snapshot()
    assert empty['version']==2 and empty['streamEpoch']!=first['streamEpoch']
    assert empty['records']=={'indoor':None}
    clock.update(at=AT+timedelta(seconds=31),tick=1031)
    source.observe({**PACKET,'tempinf':'71'});second=source.snapshot()
    assert first['records']['indoor']['sensorEpoch']==second['records']['indoor']['sensorEpoch']==SENSOR
    rows=[(AT,json.dumps(first)),(AT+timedelta(seconds=30),json.dumps(empty))]
    assert grid(rows) is None
    rows.append((clock['at']+timedelta(seconds=1),json.dumps(second)))
    value=grid(rows)
    assert value['temperatureF']==71 and value['sensorEpoch']==SENSOR and value['receiptVersion']==2
    assert value['streamEpoch']==second['streamEpoch']
    assert select_temperature_at(rows,target=AT+timedelta(seconds=60),assessed_at=AT+timedelta(hours=1),history_start=AT-timedelta(minutes=5),stream='indoor',policy=POLICY) is None


def test_changed_hardware_phase_is_a_barrier_even_with_matching_device_id():
    source,clock=collector();source.observe(PACKET);first=source.snapshot()
    changed=TemperatureCollector({'indoor':POLICY},sensor_epochs={'indoor':OTHER},clock=lambda:AT+timedelta(seconds=30))
    changed.observe(PACKET)
    rows=[(AT,json.dumps(first)),(AT+timedelta(seconds=30),json.dumps(changed.snapshot()))]
    assert grid(rows) is None
    assert grid(rows,sensor_epoch=OTHER)['sensorEpoch']==OTHER


def test_copied_old_receipt_cannot_cross_new_collector_session():
    source,clock=collector();source.observe(PACKET);old=source.snapshot()
    clock.update(at=AT+timedelta(seconds=30),tick=1030,pid=2)
    fresh=source.snapshot();copied=dict(old['records']['indoor'],streamEpoch=fresh['streamEpoch'])
    fresh['records']['indoor']=copied
    assert grid([(AT,json.dumps(old)),(clock['at'],json.dumps(fresh))]) is None


@pytest.mark.parametrize('epochs',[{}, {'other':SENSOR}, {'indoor':'bad'}, {'indoor':True}])
def test_incomplete_or_invalid_hardware_binding_refuses(epochs):
    with pytest.raises(ValueError):TemperatureCollector({'indoor':POLICY},sensor_epochs=epochs)


def test_v2_private_config_drives_real_loopback_receiver_and_old_loader_refuses(tmp_path):
    path=tmp_path/'policy.json';path.write_text(json.dumps({'version':2,'streams':{'indoor':{'model':POLICY.model,'sensor_id':235,'minimum_f':-80,'maximum_f':160,'validity_seconds':120,'sensor_epoch':SENSOR}}}));path.chmod(0o600)
    with pytest.raises(ValueError):load_temperature_policies(str(path))
    app=Flask(__name__);app.add_url_rule('/weather','legacy',lambda:'legacy')
    source=configure_temperature_receiver(app,{'WEATHER_TEMP_EVIDENCE_ENABLE':'1','WEATHER_TEMP_EVIDENCE_POLICY':str(path)})
    assert source is not None
    client=app.test_client();assert client.get('/weather',query_string=PACKET).text=='legacy'
    snapshot=client.get('/temperature_evidence').get_json()
    assert snapshot['version']==2 and snapshot['records']['indoor']['sensorEpoch']==SENSOR


def test_legacy_receipts_cannot_be_relabelled_by_v2_reader():
    source=TemperatureCollector({'indoor':POLICY},clock=lambda:AT)
    source.observe(PACKET)
    assert grid([(AT,json.dumps(source.snapshot()))]) is None


@pytest.mark.parametrize('damage',['missing','wrong','nil','boolean','foreign_id','expired'])
def test_v2_bad_identity_or_expired_snapshot_remains_a_barrier(damage):
    source,clock=collector();source.observe(PACKET);old=source.snapshot()
    clock.update(at=AT+timedelta(seconds=30),tick=1030)
    source.observe(PACKET);latest=source.snapshot();record=latest['records']['indoor']
    if damage=='missing':record.pop('sensorEpoch')
    elif damage=='wrong':record['sensorEpoch']=OTHER
    elif damage=='nil':record['sensorEpoch']='00000000-0000-0000-0000-000000000000'
    elif damage=='boolean':record['sensorEpoch']=True
    elif damage=='foreign_id':record['sensorId']=999
    target=200 if damage=='expired' else 60
    assert grid([(AT,json.dumps(old)),(clock['at'],json.dumps(latest))],target=target) is None


@pytest.mark.parametrize('epoch',[True,'invalid','00000000-0000-0000-0000-000000000000'])
def test_bad_v2_config_preserves_legacy_service_and_installs_no_evidence(tmp_path,epoch):
    path=tmp_path/'policy.json';path.write_text(json.dumps({'version':2,'streams':{'indoor':{'model':POLICY.model,'sensor_id':235,'minimum_f':-80,'maximum_f':160,'validity_seconds':120,'sensor_epoch':epoch}}}));path.chmod(0o600)
    app=Flask(__name__);app.add_url_rule('/weather','legacy',lambda:'legacy')
    assert configure_temperature_receiver(app,{'WEATHER_TEMP_EVIDENCE_ENABLE':'1','WEATHER_TEMP_EVIDENCE_POLICY':str(path)}) is None
    client=app.test_client();assert client.get('/weather').text=='legacy'
    assert client.get('/temperature_evidence').status_code==404
    assert not app.before_request_funcs
