"""Explicit native-v2 hourly evidence keeps the existing Kalman equation."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import asdict
from types import SimpleNamespace
import json
import pytest
from test_hourly_qualified_scoring import initial,receipt,TARGET,CUTOVER,fi
from test_temperature_sensor_epoch_windows import PHASE,POLICY,AT,native_rows,Connection
import hourly_temperature_runtime as runtime


def private_policy(tmp_path):
    path=tmp_path/'policy.json';path.write_text(json.dumps(dict(version=2,streams={'outdoor':{**asdict(POLICY),'sensor_epoch':PHASE}})));path.chmod(0o600);return path


def native_receipt():return {**receipt(),'receiptVersion':2,'sensorEpoch':PHASE}


def test_native_hourly_worker_reads_actual_hardware_bound_point(tmp_path,monkeypatch):
    policy=private_policy(tmp_path);connections=[]
    monkeypatch.setattr(runtime,'read_db_config',lambda _: {})
    import psycopg2
    def connect(**kwargs):
        rows=native_rows();left=AT+timedelta(seconds=60);right=AT+timedelta(seconds=180)
        value=Connection(carry=max((pair for pair in rows if pair[0]<left),key=lambda pair:pair[0]),rows=[pair for pair in rows if left<=pair[0]<=right]);connections.append(value);return value
    monkeypatch.setattr(psycopg2,'connect',connect)
    target=(AT+timedelta(seconds=180)).isoformat()
    result=runtime.collect_v2(dict(targets=[target],assessed_at=(AT+timedelta(seconds=360)).isoformat(),receipt_version=2,sensor_epoch=PHASE),config_path='/private/db',policy_path=str(policy))
    assert result[target]['temperatureF']==70 and result[target]['sensorEpoch']==PHASE
    assert all(value.closed and value.session['readonly'] for value in connections)


def test_native_hourly_routing_keeps_numeric_update_and_epoch_evidence(tmp_path,monkeypatch):
    policy=private_policy(tmp_path)
    monkeypatch.setenv('HOURLY_TEMP_QUALIFIED_ENABLE','1');monkeypatch.setenv('HOURLY_TEMP_EVIDENCE_CUTOVER',CUTOVER)
    monkeypatch.setenv('HOURLY_TEMP_RECEIPT_VERSION','2');monkeypatch.setenv('HOURLY_TEMP_POLICY',str(policy))
    monkeypatch.setattr(fi,'series',lambda *_:pytest.fail('native hourly fell back'))
    def worker(argv,**kwargs):
        assert argv[-1]=='--read-v2'
        request=json.loads(kwargs['input']);assert request['receipt_version']==2 and request['sensor_epoch']==PHASE
        assert kwargs['timeout']==30 and kwargs['check'] is True
        return SimpleNamespace(stdout=json.dumps({TARGET.isoformat():native_receipt()},default=lambda value:value.isoformat()))
    monkeypatch.setattr(runtime.subprocess,'run',worker)
    legacy=initial();fi.score_hourly_targets(legacy,TARGET+timedelta(minutes=30),qualified_reader=lambda **_:receipt(),evidence_cutover=CUTOVER)
    state=initial();assert runtime.score_runtime_hourly(state,TARGET+timedelta(minutes=30),fi.score_hourly_targets)==1
    assert state['hourly_temp_model']==legacy['hourly_temp_model']
    saved=state['hourly_temp_evidence_receipts'][0]
    assert saved['receiptVersion']==2 and saved['sensorEpoch']==PHASE and saved['streamEpoch']==native_receipt()['streamEpoch']


@pytest.mark.parametrize('damage',['phase','version','expired','legacy'])
def test_native_hourly_invalid_child_preserves_state(tmp_path,monkeypatch,damage):
    policy=private_policy(tmp_path)
    monkeypatch.setenv('HOURLY_TEMP_QUALIFIED_ENABLE','1');monkeypatch.setenv('HOURLY_TEMP_EVIDENCE_CUTOVER',CUTOVER)
    monkeypatch.setenv('HOURLY_TEMP_RECEIPT_VERSION','2');monkeypatch.setenv('HOURLY_TEMP_POLICY',str(policy))
    value=native_receipt()
    if damage=='phase':value['sensorEpoch']='00000000-0000-0000-0000-000000000001'
    elif damage=='version':value['receiptVersion']=True
    elif damage=='expired':value['validUntil']=TARGET
    else:value.pop('receiptVersion');value.pop('sensorEpoch')
    monkeypatch.setattr(runtime.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(stdout=json.dumps({TARGET.isoformat():value},default=lambda value:value.isoformat())))
    state=initial();before=deepcopy(state)
    assert runtime.score_runtime_hourly(state,TARGET+timedelta(minutes=30),fi.score_hourly_targets)==0 and state==before


def test_malformed_native_metadata_cannot_partially_update_kalman_state():
    value=receipt();value['receiptVersion']=2
    state=initial();before=deepcopy(state)
    assert fi.score_hourly_targets(state,TARGET+timedelta(minutes=30),qualified_reader=lambda **_:value,evidence_cutover=CUTOVER)==0
    assert state==before


def test_native_hourly_policy_change_refuses_before_database(tmp_path,monkeypatch):
    policy=private_policy(tmp_path)
    import psycopg2
    monkeypatch.setattr(psycopg2,'connect',lambda **kwargs:pytest.fail('changed hardware connected'))
    monkeypatch.setattr(runtime,'read_db_config',lambda _: {})
    with pytest.raises(ValueError):runtime.collect_v2(dict(targets=[AT.isoformat()],assessed_at=AT.isoformat(),receipt_version=2,sensor_epoch='00000000-0000-0000-0000-000000000001'),config_path='/private/db',policy_path=str(policy))


def test_native_hourly_uses_declared_policy_lifetime_without_thermal_narrowing(tmp_path,monkeypatch):
    from dataclasses import replace
    declared=replace(POLICY,validity_seconds=300)
    policy=tmp_path/'long-policy.json';policy.write_text(json.dumps(dict(version=2,streams={'outdoor':{**asdict(declared),'sensor_epoch':PHASE}})));policy.chmod(0o600)
    monkeypatch.setenv('HOURLY_TEMP_QUALIFIED_ENABLE','1');monkeypatch.setenv('HOURLY_TEMP_EVIDENCE_CUTOVER',CUTOVER)
    monkeypatch.setenv('HOURLY_TEMP_RECEIPT_VERSION','2');monkeypatch.setenv('HOURLY_TEMP_POLICY',str(policy))
    value=native_receipt();value['validUntil']=TARGET+timedelta(seconds=260)
    monkeypatch.setattr(runtime.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(stdout=json.dumps({TARGET.isoformat():value},default=lambda value:value.isoformat())))
    legacy=initial();fi.score_hourly_targets(legacy,TARGET+timedelta(minutes=30),qualified_reader=lambda **_:{key:entry for key,entry in value.items() if key not in ('receiptVersion','sensorEpoch')},evidence_cutover=CUTOVER)
    state=initial()
    assert runtime.score_runtime_hourly(state,TARGET+timedelta(minutes=30),fi.score_hourly_targets)==1
    assert state['hourly_temp_model']==legacy['hourly_temp_model']
