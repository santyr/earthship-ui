"""Synthetic native sensor-phase integration; SQL transport is replaced locally."""
from datetime import timedelta
import json
from dataclasses import asdict
import pytest
from test_weather_temperature_reader import AT
from test_weather_temperature_history import Connection
from test_thermal_temperature_history import receipt
from weather_temperature_evidence import TemperaturePolicy,MODELS
from weather_temperature_receiver import TemperatureCollector
from thermal_model.schema import THERMAL_ITEMS
from thermal_model.temperature_history import STREAMS,POLICY,validate_evidence_manifest
import thermal_model.temperature_history as history
import thermal_temperature_runtime as runtime

EPOCHS={'air':'d348bbfa-4108-4fdc-8319-6349cc54853b','mass':'415c5285-8039-4650-9c1d-73e76fb29612','outdoor':'cbfe6b20-2b2f-4cf6-bfce-2e69111762a1'}


def sources(tmp_path,monkeypatch):
    policies={stream:TemperaturePolicy(model,sensor,**POLICY) for stream,model,sensor in STREAMS.values()}
    phases={STREAMS[role][0]:epoch for role,epoch in EPOCHS.items()}
    clock={'at':AT,'pid':1,'tick':1000}
    source=TemperatureCollector(policies,sensor_epochs=phases,clock=lambda:clock['at'],process_id=lambda:clock['pid'],monotonic=lambda:clock['tick'])
    rows=[]
    for index in range(2):
        clock.update(at=AT+timedelta(minutes=5*index),pid=index+1,tick=1000+300*index)
        for policy in policies.values():source.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:str(70+index)})
        rows.append((clock['at'],json.dumps(source.snapshot())))
    doc={'version':2,'streams':{name:{**asdict(policy),'sensor_epoch':phases[name]} for name,policy in policies.items()}}
    path=tmp_path/'policy.json';path.write_text(json.dumps(doc));path.chmod(0o600)
    import hourly_temperature_runtime
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    return path,rows


def test_source_to_native_sql_to_history_preserves_hardware_and_rotating_sessions(tmp_path,monkeypatch):
    path,rows=sources(tmp_path,monkeypatch);connections=[]
    def grid(stream,targets,assessed):
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        def connect(_):
            connection=Connection(rows=rows);connections.append(connection);return connection
        return runtime.collect_v2(dict(stream=stream,targets=[at.isoformat() for at in targets],assessed_at=assessed.isoformat(),receipt_version=2,sensor_epoch=EPOCHS[role]),config_path='/private/db',policy_path=str(path),connection_factory=connect)
    def prohibited(*args):pytest.fail('native v2 temperatures fell back to legacy values')
    copied=dict(EPOCHS)
    reader=history.QualifiedTemperatureHistoryV2(prohibited,grid,cutover=AT,assessed_at=AT+timedelta(days=1),retain_raw=True,sensor_epochs=copied)
    copied['air']=EPOCHS['mass']
    for role in STREAMS:
        assert reader(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=10))==[(AT,70),(AT+timedelta(minutes=5),71)]
    proof=reader.evidence_manifest()
    assert proof['version']==2
    history.validate_sensor_evidence_manifest(proof,start=AT,end=AT+timedelta(minutes=10))
    with pytest.raises(ValueError):validate_evidence_manifest(proof)
    for role,grid_rows in reader.temperature_grids().items():
        assert {value['sensorEpoch'] for at,value in grid_rows}=={EPOCHS[role]}
        assert len({value['streamEpoch'] for at,value in grid_rows})==2
        assert proof['roles'][role]['sensor_epoch']==EPOCHS[role]
    assert all(connection.closed and connection.session=={'readonly':True,'autocommit':False,'isolation_level':'REPEATABLE READ'} for connection in connections)


def test_wrong_declared_phase_is_refused_before_connection(tmp_path,monkeypatch):
    path,rows=sources(tmp_path,monkeypatch)
    def prohibited(_):pytest.fail('mismatched declared hardware phase reached database')
    with pytest.raises(ValueError):runtime.collect_v2(dict(stream='indoor',targets=[AT.isoformat()],assessed_at=(AT+timedelta(minutes=5)).isoformat(),receipt_version=2,sensor_epoch=EPOCHS['mass']),config_path='/private/db',policy_path=str(path),connection_factory=prohibited)


def test_v1_worker_refuses_v2_configuration(tmp_path,monkeypatch):
    path,rows=sources(tmp_path,monkeypatch)
    with pytest.raises(ValueError):runtime.collect(dict(stream='indoor',targets=[AT.isoformat()],assessed_at=AT.isoformat()),config_path='/private/db',policy_path=str(path),connection_factory=lambda _:pytest.fail('v1 reader connected to v2 source'))


def test_native_v2_rejects_old_receipts_and_pre_cutover_data():
    def prohibited(*args):pytest.fail('legacy history accessed')
    reader=history.QualifiedTemperatureHistoryV2(prohibited,lambda stream,targets,assessed:[(at,receipt(at)) for at in targets],cutover=AT,assessed_at=AT+timedelta(days=1),sensor_epochs=EPOCHS)
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],AT-timedelta(minutes=5),AT)
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=5))


@pytest.mark.parametrize('bindings',[{}, {'air':EPOCHS['air']}, {**EPOCHS,'air':True}, {**EPOCHS,'air':'bad'}])
def test_complete_canonical_phase_bindings_required(bindings):
    with pytest.raises(ValueError):history.QualifiedTemperatureHistoryV2(lambda *args:[],lambda *args:[],cutover=AT,assessed_at=AT,sensor_epochs=bindings)


def test_configured_v2_worker_request_pins_sensor_phase_and_never_uses_v1_mode(tmp_path,monkeypatch):
    from types import SimpleNamespace
    path,rows=sources(tmp_path,monkeypatch);calls=[]
    def worker(argv,**kwargs):
        assert argv[-1]=='--read-v2' and 0<kwargs['timeout']<=30
        request=json.loads(kwargs['input']);calls.append(request)
        role=next(role for role,identity in STREAMS.items() if identity[0]==request['stream'])
        assert request['sensor_epoch']==EPOCHS[role] and request['receipt_version']==2
        result=runtime.collect_v2(request,config_path='/private/db',policy_path=str(path),connection_factory=lambda _:Connection(rows=rows))
        return SimpleNamespace(stdout=json.dumps(result,default=lambda value:value.isoformat()))
    monkeypatch.setattr(runtime.subprocess,'run',worker)
    env={'THERMAL_TEMP_QUALIFIED_ENABLE':'1','THERMAL_TEMP_EVIDENCE_CUTOVER':AT.isoformat(),'THERMAL_TEMP_DB_CONFIG':'/private/db','THERMAL_TEMP_POLICY':str(path)}
    reader=runtime.configured_history_v2(lambda *args:pytest.fail('legacy values used'),AT+timedelta(days=1),environ=env,retain_raw=True)
    for role in STREAMS:
        assert len(reader(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=10)))==2
    assert len(calls)==3 and reader.evidence_manifest()['version']==2


@pytest.mark.parametrize('damage',['phase','version','expiry'])
def test_v2_history_refuses_invalid_receipt_without_partial_qualified_series(damage):
    def grid(stream,targets,assessed):
        rows=[]
        for index,target in enumerate(targets):
            value={**receipt(target), 'sensorEpoch':EPOCHS['air'],'receiptVersion':2}
            if index==1:
                if damage=='phase':value['sensorEpoch']=EPOCHS['mass']
                elif damage=='version':value['receiptVersion']=True
                else:value['validUntil']=target
            rows.append((target,value))
        return rows
    reader=history.QualifiedTemperatureHistoryV2(lambda *args:pytest.fail('legacy values used'),grid,cutover=AT,assessed_at=AT+timedelta(days=1),sensor_epochs=EPOCHS,retain_raw=True)
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=10))
    with pytest.raises(ValueError):reader.evidence_manifest()


def test_v2_manifest_rejects_legacy_or_rehashed_wrong_binding(tmp_path,monkeypatch):
    import copy
    def grid(stream,targets,assessed):
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        return [(target,{**receipt(target),'sensorEpoch':EPOCHS[role],'receiptVersion':2}) for target in targets]
    reader=history.QualifiedTemperatureHistoryV2(lambda *args:[],grid,cutover=AT,assessed_at=AT+timedelta(days=1),sensor_epochs=EPOCHS)
    for role in STREAMS:reader(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=5))
    for damage in ('legacy','epoch','version','extra'):
        proof=copy.deepcopy(reader.evidence_manifest())
        if damage=='legacy':proof['roles']['air']['legacy_points']=1
        elif damage=='epoch':proof['roles']['air']['sensor_epoch']='invalid'
        elif damage=='version':proof['version']=True
        else:proof['roles']['air']['extra']=1
        with pytest.raises(ValueError):history.validate_sensor_evidence_manifest(proof,start=AT,end=AT+timedelta(minutes=5))
