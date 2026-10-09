"""Raw native score inputs must survive independent replay without DB access."""
from datetime import timedelta
import importlib
import pytest
from test_thermal_sensor_epoch_history import sources,EPOCHS
from test_weather_temperature_reader import AT
from test_weather_temperature_history import Connection
from weather_temperature_config import load_temperature_receiver_configuration


def module():
    assert importlib.util.find_spec('weather_temperature_sources') is not None,'missing raw native source packet'
    return importlib.import_module('weather_temperature_sources')


def case(tmp_path,monkeypatch):
    path,rows=sources(tmp_path,monkeypatch);policies,_=load_temperature_receiver_configuration(str(path))
    return dict(rows=rows,targets=[AT+timedelta(seconds=60),AT+timedelta(seconds=360)],assessed_at=AT+timedelta(minutes=10),stream='indoor',policy=policies['indoor'],sensor_epoch=EPOCHS['air'])


def test_retained_raw_packet_replays_rotating_sessions_and_hardware_phase(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch);m=module();packet=m.build_temperature_source(**args)
    args['rows'].clear()
    grid=m.replay_temperature_source(packet)
    assert [r['temperatureF'] for _,r in grid]==[70.,71.]
    assert grid[0][1]['streamEpoch']!=grid[1][1]['streamEpoch']
    assert {r['sensorEpoch'] for _,r in grid}=={EPOCHS['air']}
    assert packet['release_authority'] is False and len(packet['native_rows'])==2


def test_null_and_invalid_snapshot_barriers_survive_packet_replay(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch);args['rows'].insert(1,(AT+timedelta(seconds=30),None));m=module()
    packet=m.build_temperature_source(**args)
    assert packet['native_rows'][1][1] is None
    assert [r['temperatureF'] if r else None for _,r in m.replay_temperature_source(packet)]==[None,71.]


@pytest.mark.parametrize('damage',['authority','extra','future_target','unordered','wrong_epoch','too_many','oversized_raw','stream_bound'])
def test_packet_refuses_invalid_contract_or_source_window(tmp_path,monkeypatch,damage):
    m=module();packet=m.build_temperature_source(**case(tmp_path,monkeypatch))
    if damage=='authority':packet['release_authority']=True
    elif damage=='extra':packet['selected_receipts']=[]
    elif damage=='future_target':packet['assessed_at']=AT.isoformat()
    elif damage=='unordered':packet['native_rows'].reverse()
    elif damage=='wrong_epoch':packet['sensor_epoch']='not-a-phase'
    elif damage=='too_many':packet['native_rows']*=5001
    elif damage=='stream_bound':packet['stream']='x'*65
    else:packet['native_rows'][0][1]='x'*8193
    with pytest.raises(ValueError):m.replay_temperature_source(packet)


def test_private_immutable_source_archive_detects_changed_bytes(tmp_path,monkeypatch):
    m=module();packet=m.build_temperature_source(**case(tmp_path,monkeypatch));archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    path=m.write_temperature_source(archive,packet)
    assert m.read_temperature_source(archive,path)==packet
    assert path.stat().st_mode&0o777==0o600
    assert m.write_temperature_source(archive,packet)==path
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):m.read_temperature_source(archive,path)


def test_fetch_retains_one_read_only_snapshot_and_can_replay_after_connection_closed(tmp_path,monkeypatch):
    m=module();args=case(tmp_path,monkeypatch);rows=args.pop('rows');connection=Connection(rows=rows)
    packet=m.fetch_temperature_source(lambda:connection,**args)
    assert connection.closed and connection.session['readonly'] is True
    assert [r['temperatureF'] for _,r in m.replay_temperature_source(packet)]==[70.,71.]
    assert packet['native_rows'][0][1]==rows[0][1]


def test_invalid_request_cannot_open_database(tmp_path,monkeypatch):
    m=module();args=case(tmp_path,monkeypatch);args.pop('rows');args['targets'].reverse()
    def forbidden():pytest.fail('invalid request reached database')
    with pytest.raises(ValueError):m.fetch_temperature_source(forbidden,**args)


def test_fetch_freezes_query_context_before_database_callback(tmp_path,monkeypatch):
    m=module();args=case(tmp_path,monkeypatch);rows=args.pop('rows');connection=Connection(rows=rows)
    def connect():
        args['targets'][-1]=AT+timedelta(minutes=10)
        return connection
    packet=m.fetch_temperature_source(connect,**args)
    assert packet['targets']==['2026-09-10T12:01:00+00:00','2026-09-10T12:06:00+00:00']
    assert [r['temperatureF'] for _,r in m.replay_temperature_source(packet)]==[70.,71.]
