"""Native-v2 point/window evidence preserves fresh sessions, barriers and DST bounds."""
from datetime import timedelta
import json
import pytest
from test_weather_temperature_reader import AT
from test_weather_temperature_history import Connection
from test_thermal_sensor_epoch_history import EPOCHS
from weather_temperature_evidence import TemperaturePolicy,MODELS
from weather_temperature_receiver import TemperatureCollector
import weather_temperature_reader as reader
import weather_temperature_history as history

PHASE=EPOCHS['outdoor']
POLICY=TemperaturePolicy('Fineoffset-WH65B',206,minimum_f=-40,maximum_f=140,validity_seconds=120)


def native_rows():
    clock={'at':AT,'pid':1,'tick':1000}
    source=TemperatureCollector({'outdoor':POLICY},sensor_epochs={'outdoor':PHASE},clock=lambda:clock['at'],process_id=lambda:clock['pid'],monotonic=lambda:clock['tick'])
    rows=[]
    for seconds in (-30,0,30,90,150,210,270,300):
        clock.update(at=AT+timedelta(seconds=seconds),pid=1 if seconds<150 else 2,tick=1000+seconds)
        value=100 if seconds==300 else 95 if seconds==30 else 70
        source.observe({'model':POLICY.model,'id':str(POLICY.sensor_id),MODELS[POLICY.model][1]:str(value)})
        rows.append((clock['at']+timedelta(seconds=10),json.dumps(source.snapshot())))
    return rows


def context():
    return dict(start=AT,end=AT+timedelta(seconds=300),assessed_at=AT+timedelta(seconds=360),history_start=AT-timedelta(seconds=120),stream='outdoor',policy=POLICY,sensor_epoch=PHASE)


def test_native_window_keeps_true_extrema_half_open_end_and_fresh_sessions():
    result=reader.select_temperature_window_v2(native_rows(),**context())
    assert result['fully_covered'] and result['covered_seconds']==300
    assert result['observed_high_f']==95 and result['observed_low_f']==70
    assert result['receiptVersion']==2 and result['sensorEpoch']==PHASE
    assert result['gap_count']==0
    old=reader.select_temperature_window(native_rows(),**{key:value for key,value in context().items() if key!='sensor_epoch'})
    assert old['covered_seconds']==0 and old['observed_high_f'] is None


def test_native_point_selection_uses_fresh_packet_not_session_uuid_as_hardware():
    rows=native_rows()
    value=reader.select_temperature_at_v2(rows,target=AT+timedelta(seconds=180),assessed_at=AT+timedelta(seconds=360),history_start=AT-timedelta(seconds=120),stream='outdoor',policy=POLICY,sensor_epoch=PHASE)
    assert value['temperatureF']==70 and value['sensorEpoch']==PHASE
    assert reader.select_temperature_at(rows,target=AT+timedelta(seconds=180),assessed_at=AT+timedelta(seconds=360),history_start=AT-timedelta(seconds=120),stream='outdoor',policy=POLICY) is None


def test_native_window_wrong_hardware_is_missing_coverage_not_old_value():
    rows=native_rows();value=json.loads(rows[3][1]);value['records']['outdoor']['sensorEpoch']=EPOCHS['air']
    rows[3]=(rows[3][0],json.dumps(value))
    result=reader.select_temperature_window_v2(rows,**context())
    assert not result['fully_covered'] and result['maximum_gap_seconds']==60
    assert result['gap_count']==1 and result['covered_seconds']==240


def test_native_point_fetch_and_window_fetch_keep_readonly_snapshot_and_original_digest():
    connections=[]
    def connect_point():
        original=native_rows();start=AT+timedelta(seconds=60);target=AT+timedelta(seconds=180)
        carry=max((pair for pair in original if pair[0]<start),key=lambda pair:pair[0])
        value=Connection(carry=carry,rows=[pair for pair in original if start<=pair[0]<=target]);connections.append(value);return value
    def connect_window():
        value=Connection(rows=[pair for pair in native_rows() if pair[0]<=AT+timedelta(seconds=300)]);connections.append(value);return value
    value=history.fetch_temperature_target_v2(connect_point,target=AT+timedelta(seconds=180),assessed_at=AT+timedelta(seconds=360),stream='outdoor',policy=POLICY,sensor_epoch=PHASE)
    assert value['sensorEpoch']==PHASE and value['temperatureF']==70
    result=history.fetch_temperature_window_v2(connect_window,include_provenance=True,**{key:value for key,value in context().items() if key!='history_start'})
    assert result['fully_covered'] and result['sensorEpoch']==PHASE and len(result['history_sha256'])==64
    assert all(value.closed and value.session['readonly'] for value in connections)
    assert all(sum('time >=' in query for query,_ in value.calls)==1 for value in connections)


@pytest.mark.parametrize('damage',['nil_phase','future','too_long'])
def test_native_window_bad_context_never_connects(damage):
    kwargs={key:value for key,value in context().items() if key!='history_start'}
    if damage=='nil_phase':kwargs['sensor_epoch']='00000000-0000-0000-0000-000000000000'
    elif damage=='future':kwargs['assessed_at']=AT
    else:kwargs['end']=AT+timedelta(hours=25,seconds=1);kwargs['assessed_at']=kwargs['end']
    with pytest.raises(history.TemperatureHistoryUnavailable):history.fetch_temperature_window_v2(lambda:pytest.fail('invalid native window connected'),**kwargs)
