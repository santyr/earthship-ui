"""Explicit native-v2 hourly evidence keeps the existing Kalman equation."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import asdict
from types import SimpleNamespace
import json
import pytest
from test_temperature_sensor_epoch_windows import PHASE,POLICY,AT,native_rows,Connection
import hourly_temperature_runtime as runtime


from datetime import datetime,timedelta,timezone
import json
TARGET = datetime(2026, 9, 20, 18, tzinfo=timezone.utc)
CUTOVER = (TARGET - timedelta(days=2)).isoformat()
def receipt(target=TARGET):
    return {'temperatureF': 70.0, 'receivedAt': target - timedelta(seconds=40),
            'storedAt': target - timedelta(seconds=30), 'validUntil': target + timedelta(seconds=80),
            'snapshotSha256': 'a' * 64, 'streamEpoch': '882078a7-c0f2-4079-a979-120a100c5e92'}

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








def test_native_hourly_policy_change_refuses_before_database(tmp_path,monkeypatch):
    policy=private_policy(tmp_path)
    import psycopg2
    monkeypatch.setattr(psycopg2,'connect',lambda **kwargs:pytest.fail('changed hardware connected'))
    monkeypatch.setattr(runtime,'read_db_config',lambda _: {})
    with pytest.raises(ValueError):runtime.collect_v2(dict(targets=[AT.isoformat()],assessed_at=AT.isoformat(),receipt_version=2,sensor_epoch='00000000-0000-0000-0000-000000000001'),config_path='/private/db',policy_path=str(policy))
