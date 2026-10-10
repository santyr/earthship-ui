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


def test_compressed_source_retains_exact_raw_query_and_old_reader_refuses(tmp_path,monkeypatch):
    import gzip,json
    args=case(tmp_path,monkeypatch);m=module();packet=m.build_temperature_source(**args)
    assert hasattr(m,'write_compressed_temperature_source'),'missing lossless native source codec'
    assert hasattr(m,'read_compressed_temperature_source'),'missing typed compressed source reader'
    root=tmp_path/'compressed';root.mkdir(mode=0o700)
    path=m.write_compressed_temperature_source(root,packet)
    assert path.name.endswith('.native-temperature-sources-v2.json.gz')
    assert path.stat().st_mode&0o777==0o600
    assert m.read_compressed_temperature_source(root,path)==packet
    assert m.replay_temperature_source(m.read_compressed_temperature_source(root,path))==m.replay_temperature_source(packet)
    assert m.write_compressed_temperature_source(root,packet)==path
    with pytest.raises(ValueError):m.read_temperature_source(root,path)
    container=json.loads(gzip.decompress(path.read_bytes()))
    assert container['schema']=='earthship-native-temperature-query-container/v2'
    assert container['raw_query']==packet and packet['release_authority'] is False


@pytest.mark.parametrize('damage',['oversized','truncated','duplicate','digest'])
def test_compressed_source_refuses_unbounded_or_corrupted_original_data(tmp_path,monkeypatch,damage):
    import gzip,json,hashlib
    args=case(tmp_path,monkeypatch);m=module();packet=m.build_temperature_source(**args)
    assert hasattr(m,'write_compressed_temperature_source'),'missing lossless native source codec'
    root=tmp_path/'compressed';root.mkdir(mode=0o700)
    path=m.write_compressed_temperature_source(root,packet)
    original=gzip.decompress(path.read_bytes())
    if damage=='oversized':raw=gzip.compress(b' '*((8*1024*1024)+4097),mtime=0)
    elif damage=='truncated':raw=path.read_bytes()[:-5]
    elif damage=='duplicate':raw=gzip.compress(original[:-1]+b',"schema":"earthship-native-temperature-query-container/v2"}',mtime=0)
    else:
        value=json.loads(original);value['raw_query_sha256']='0'*64
        raw=gzip.compress(json.dumps(value,sort_keys=True,separators=(',',':')).encode(),mtime=0)
    changed=root/(hashlib.sha256(raw).hexdigest()+'.native-temperature-sources-v2.json.gz');changed.write_bytes(raw);changed.chmod(0o600)
    with pytest.raises((ValueError,OSError,EOFError)):m.read_compressed_temperature_source(root,changed)


def test_compressed_source_final_guard_runs_after_actual_temporary_write(tmp_path,monkeypatch):
    import os
    args=case(tmp_path,monkeypatch);m=module();packet=m.build_temperature_source(**args)
    assert hasattr(m,'write_compressed_temperature_source'),'missing lossless native source codec'
    root=tmp_path/'compressed';root.mkdir(mode=0o700);state={'written':False};original=os.chmod
    def written(path,mode,*a,**kw):
        original(path,mode,*a,**kw)
        if str(path).split('/')[-1].startswith('.temperature-origin-'):state['written']=True
    monkeypatch.setattr(os,'chmod',written)
    def guard():
        assert state['written'];raise ValueError('synthetic source authority lost after retention')
    with pytest.raises(ValueError):m.write_compressed_temperature_source(root,packet,before_publish=guard)
    assert state['written'] and list(root.iterdir())==[]


def test_compressed_storage_does_not_relax_original_raw_query_byte_bound(tmp_path,monkeypatch):
    args=case(tmp_path,monkeypatch);m=module();packet=m.build_temperature_source(**args)
    packet['native_rows']=[[packet['targets'][0],'x'*8192] for _ in range(1025)]
    root=tmp_path/'compressed';root.mkdir(mode=0o700)
    with pytest.raises(ValueError):m.write_compressed_temperature_source(root,packet)
    assert list(root.iterdir())==[]
