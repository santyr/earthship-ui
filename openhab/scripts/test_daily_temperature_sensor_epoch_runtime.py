"""Native daily migration preserves complete coverage and existing learning."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import json
import pytest
import daily_temperature_runtime as runtime
from test_daily_temperature_runtime import START,END,ASSESSED,REQUEST,ENV,payload,scoring_fixture,fi
from test_hourly_temperature_sensor_epoch_runtime import private_policy
from test_temperature_sensor_epoch_windows import PHASE,POLICY,Connection
from weather_temperature_receiver import TemperatureCollector


def native_request():return REQUEST|{'receipt_version':2,'sensor_epoch':PHASE}
def native_payload():
    result=payload();result.update(version=2,request=native_request(),sensor_epoch=PHASE)
    result['summary'].update(receiptVersion=2,sensorEpoch=PHASE)
    return result

def native_env(tmp_path):return ENV|{'DAILY_TEMP_RECEIPT_VERSION':'2','DAILY_TEMP_POLICY':str(private_policy(tmp_path))}


def test_daily_native_worker_uses_original_complete_day_receipts(tmp_path,monkeypatch):
    import hourly_temperature_runtime,psycopg2
    policy=private_policy(tmp_path);clock={'at':START};rows=[]
    collector=TemperatureCollector({'outdoor':POLICY},sensor_epochs={'outdoor':PHASE},clock=lambda:clock['at'],process_id=lambda:1,monotonic=lambda:clock['at'].timestamp())
    for index in range(-1,721):
        clock['at']=START+timedelta(seconds=index*120)
        collector.observe({'model':POLICY.model,'id':'206','tempf':str(40 if index%2 else 80)})
        rows.append((clock['at'],json.dumps(collector.snapshot())))
    connection=Connection(rows=rows)
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    monkeypatch.setattr(psycopg2,'connect',lambda **_:connection)
    result=runtime.collect_v2(native_request(),config_path='/private/db',policy_path=str(policy))
    assert result['version']==2 and result['sensor_epoch']==PHASE
    assert result['summary']['fully_covered'] and result['summary']['covered_seconds']==86400
    assert result['summary']['observed_high_f']==80 and result['summary']['observed_low_f']==40
    assert result['summary']['sensorEpoch']==PHASE and connection.closed and connection.session['readonly']


def test_daily_native_parent_retains_phase_and_bounds(tmp_path,monkeypatch):
    def child(argv,**kwargs):
        assert argv[-1]=='--read-v2' and json.loads(kwargs['input'])==native_request()
        assert kwargs['timeout']==30 and kwargs['check']
        return SimpleNamespace(stdout=json.dumps(native_payload()))
    monkeypatch.setattr(runtime.subprocess,'run',child)
    high,low,evidence=runtime.read_daily_actuals(START,END,ASSESSED,native_env(tmp_path))
    assert (high,low)==(80,40) and evidence['summary']['sensorEpoch']==PHASE
    assert evidence['cutover']==START.isoformat()


@pytest.mark.parametrize('damage',['phase','summary_phase','version','legacy','gap'])
def test_daily_native_bad_child_never_becomes_learning_actuals(tmp_path,monkeypatch,damage):
    value=native_payload()
    if damage=='phase':value['sensor_epoch']='00000000-0000-0000-0000-000000000001'
    elif damage=='summary_phase':value['summary']['sensorEpoch']='00000000-0000-0000-0000-000000000001'
    elif damage=='version':value['summary']['receiptVersion']=True
    elif damage=='legacy':value=payload()
    else:value['summary'].update(covered_seconds=86399,maximum_gap_seconds=1,gap_count=1,fully_covered=False)
    monkeypatch.setattr(runtime.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=json.dumps(value)))
    assert runtime.read_daily_actuals(START,END,ASSESSED,native_env(tmp_path))==(None,None,None)


def test_daily_native_selection_without_optin_never_uses_numeric_fallback(monkeypatch):
    monkeypatch.delenv('DAILY_TEMP_QUALIFIED_ENABLE',raising=False)
    monkeypatch.setenv('DAILY_TEMP_RECEIPT_VERSION','2')
    monkeypatch.setattr(fi,'measured_day_weather',lambda _:pytest.fail('numeric temperature fallback'))
    monkeypatch.setattr(fi,'series',lambda *_:[])
    assert fi.measured_day_weather_with_evidence(START.date())==(None,None,None,None)


def test_daily_native_evidence_keeps_existing_daily_and_day3_math(monkeypatch):
    legacy,_,_=scoring_fixture(monkeypatch)
    with pytest.raises(RuntimeError,match='after-scoring'):fi.main()
    expected={key:deepcopy(legacy[key]) for key in ('kalman','temp_hi_errors','temp_lo_errors','day3_hi_errors')}
    state,_,_=scoring_fixture(monkeypatch)
    old=fi.measured_day_weather_with_evidence
    def actuals(day):
        rain,high,low,evidence=old(day);evidence.update(version=2,sensor_epoch=PHASE)
        evidence['request'].update(receipt_version=2,sensor_epoch=PHASE)
        evidence['summary'].update(receiptVersion=2,sensorEpoch=PHASE)
        return rain,high,low,evidence
    monkeypatch.setattr(fi,'measured_day_weather_with_evidence',actuals)
    with pytest.raises(RuntimeError,match='after-scoring'):fi.main()
    assert {key:state[key] for key in expected}==expected
    assert all(row['evidence']['summary']['sensorEpoch']==PHASE for row in state['daily_temperature_evidence'])


def test_daily_native_phase_change_refuses_before_database(tmp_path,monkeypatch):
    import psycopg2
    monkeypatch.setattr(psycopg2,'connect',lambda **_:pytest.fail('mismatched phase reached database'))
    with pytest.raises(ValueError,match='phase'):
        runtime.collect_v2(native_request()|{'sensor_epoch':'00000000-0000-0000-0000-000000000001'},config_path='/private/db',policy_path=str(private_policy(tmp_path)))


def test_legacy_daily_reader_refuses_native_contract():
    with pytest.raises(ValueError):runtime.validate_result(native_payload(),native_request())


@pytest.mark.parametrize('month,day,hours',[(3,8,23),(11,1,25)])
def test_native_daily_preserves_actual_dst_day_bounds(month,day,hours):
    from datetime import datetime
    start=datetime(2026,month,day,tzinfo=runtime.SITE_ZONE)
    end=datetime(2026,month,day+1,tzinfo=runtime.SITE_ZONE)
    request=dict(start=start.isoformat(),end=end.isoformat(),assessed_at=end.isoformat(),receipt_version=2,sensor_epoch=PHASE)
    value=native_payload();value['request']=request
    value['summary'].update(total_seconds=hours*3600,covered_seconds=hours*3600)
    assert runtime.validate_result_v2(value,request,sensor_epoch=PHASE) is value
