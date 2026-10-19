"""Bounded collection preserves originals and never refreshes their clocks."""
from datetime import timedelta
from hashlib import sha256
import importlib
import pytest
from test_household_replay import bundle
from local_measurement_test_support import NOW


def api():
    assert importlib.util.find_spec('household.capture') is not None, 'household source capture missing'
    return importlib.import_module('household.capture')


def bindings():
    return {'battery_soc': '00000000-0000-0000-0000-000000000001'}


def collect(reader=None, **kwargs):
    source=bundle()['sources'][0]
    return api().collect_inputs(epochs=bindings(),policy=bundle()['policy'],
        receipt_reader=reader or (lambda role,start,end,remaining:(NOW,source['raw'])),
        native_reader=lambda **request: pytest.fail('undeclared native source read'),
        clock=kwargs.pop('clock',lambda: NOW),monotonic=kwargs.pop('monotonic',lambda: 0.0),**kwargs)


def test_collection_preserves_exact_original_and_persisted_clock():
    source=bundle()['sources'][0];seen=[]
    def reader(role,start,end,remaining):
        seen.append((role,start,end,remaining()))
        return NOW-timedelta(seconds=1),source['raw']+' '
    result=collect(reader)
    row=result['sources'][0]
    assert seen==[('battery_soc',NOW-timedelta(seconds=120),NOW,15.0)]
    assert row['raw']==source['raw']+' '
    assert row['expected_sha256']==sha256(row['raw'].encode()).hexdigest()
    assert row['persisted_at']==(NOW-timedelta(seconds=1)).isoformat()
    assert row['expected_epoch']==bindings()['battery_soc']
    assert row['source_identity']=='BMS_SOC_Evidence_JSON'


def test_missing_source_explicit_and_final_asof_follows_collection():
    clocks=iter([NOW,NOW+timedelta(seconds=2)])
    result=collect(lambda *args:None,clock=lambda:next(clocks))
    assert result['as_of']==(NOW+timedelta(seconds=2)).isoformat()
    assert result['sources'][0]['raw'] is None
    assert result['sources'][0]['expected_sha256'] is None
    assert result['sources'][0]['persisted_at']==NOW.isoformat()


@pytest.mark.parametrize('damage',['unknown_role','bad_epoch','future','old','size','deadline','backward','empty','policy'])
def test_invalid_context_or_budget_refused(damage):
    mod=api();epoch=bindings();clock=lambda:NOW;mono=lambda:0.0;policy=bundle()['policy']
    source=bundle()['sources'][0];value=(NOW,source['raw'])
    if damage=='unknown_role':epoch['pump']='unknown'
    elif damage=='bad_epoch':epoch['battery_soc']=''
    elif damage=='future':value=(NOW+timedelta(seconds=1),source['raw'])
    elif damage=='old':value=(NOW-timedelta(seconds=121),source['raw'])
    elif damage=='size':value=(NOW,'x'*4097)
    elif damage=='deadline':ticks=iter([0.0,16.0]);mono=lambda:next(ticks)
    elif damage=='backward':clocks=iter([NOW,NOW-timedelta(seconds=1)]);clock=lambda:next(clocks)
    elif damage=='empty':epoch={}
    else:policy['max_age_seconds']['battery_soc']=0
    with pytest.raises(ValueError):
        mod.collect_inputs(epochs=epoch,policy=policy,receipt_reader=lambda *args:value,
            native_reader=lambda **kwargs:None,clock=clock,monotonic=mono)


def test_native_packet_uses_fixed_sensor_binding_and_single_original_target(tmp_path,monkeypatch):
    from test_weather_temperature_sources import case
    from thermal_model.temperature_history import STREAMS,POLICY
    from weather_temperature_evidence import TemperaturePolicy
    from weather_temperature_sources import build_temperature_source
    from household.codec import canonical
    source=case(tmp_path,monkeypatch)
    source.update(rows=[],targets=[NOW],assessed_at=NOW,policy=TemperaturePolicy(STREAMS["air"][1],STREAMS["air"][2],**POLICY))
    packet=build_temperature_source(**source);seen=[]
    def reader(**request):seen.append(request);return packet
    result=api().collect_inputs(epochs={'air_temperature':packet['sensor_epoch']},
        policy={'requirements':{'air_display':['air_temperature']},'max_age_seconds':{'air_temperature':120},'max_skew_seconds':60},
        receipt_reader=lambda *args:pytest.fail('unexpected energy read'),native_reader=reader,
        clock=lambda:NOW,monotonic=lambda:0.0)
    assert seen[0]['stream']=='indoor' and seen[0]['targets']==[NOW]
    assert result['sources'][0]['raw']==canonical(packet).decode()
    assert result['sources'][0]['persisted_at'] is None


def db_fetch(connection,role='battery_soc'):
    return api().fetch_receipt(lambda:connection,role=role,start=NOW-timedelta(seconds=120),end=NOW,remaining=lambda:15.0)


def test_receipt_database_reads_only_latest_bounded_original():
    from test_weather_temperature_history import Connection
    original=bundle()['sources'][0]['raw']
    connection=Connection(rows=[(NOW,original),(NOW-timedelta(seconds=5),'bad older row')])
    assert db_fetch(connection)==(NOW,original)
    assert connection.closed and connection.session['readonly'] is True
    assert all(q.startswith(('SET LOCAL','SHOW ','SELECT ')) for q,_ in connection.calls)
    query,params=connection.calls[-1]
    assert 'ORDER BY time DESC LIMIT 2' in query and 'octet_length' in query
    assert params==(NOW-timedelta(seconds=120),NOW)
    assert ('BMS_SOC_Evidence_JSON',) in [params for _,params in connection.calls]


@pytest.mark.parametrize('damage',['mapping','write','isolation','outside','tie','oversize','role','null'])
def test_receipt_database_refuses_bad_context_and_never_falls_back(damage):
    from test_weather_temperature_history import Connection
    original=bundle()['sources'][0]['raw'];kwargs={'rows':[(NOW,original)]};role='battery_soc'
    if damage=='mapping':kwargs['mapping']=[(613,),(614,)]
    elif damage=='write':kwargs['read_only']='off'
    elif damage=='isolation':kwargs['isolation']='read committed'
    elif damage=='outside':kwargs['rows']=[(NOW+timedelta(seconds=1),original)]
    elif damage=='tie':kwargs['rows']=[(NOW,original),(NOW,original)]
    elif damage=='oversize':kwargs['rows']=[(NOW,'x'*4097)]
    elif damage=='role':role='arbitrary_item'
    else:kwargs['rows']=[(NOW,None),(NOW-timedelta(seconds=1),original)]
    connection=Connection(**kwargs)
    if damage=='null':assert db_fetch(connection)==(NOW,None)
    else:
        with pytest.raises(ValueError):db_fetch(connection,role)
    assert connection.closed or not connection.calls


def test_capture_cli_refuses_bad_private_config_without_exposing_contents(tmp_path):
    import subprocess,sys,json
    from pathlib import Path
    script=Path(__file__).with_name('household_capture.py')
    assert script.exists(),'bounded capture CLI missing'
    config=tmp_path/'private.json';config.write_text(json.dumps({'unexpected':'must-stay-private'}));config.chmod(0o600)
    result=subprocess.run([sys.executable,str(script),'--config',str(config)],capture_output=True,text=True,timeout=5)
    assert result.returncode==1 and not result.stdout
    assert 'must-stay-private' not in result.stderr and 'Traceback' not in result.stderr


def test_capture_cli_never_waits_on_special_config_file(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    script=Path(__file__).with_name('household_capture.py')
    assert script.exists(),'bounded capture CLI missing'
    config=tmp_path/'fifo';os.mkfifo(config,0o600)
    result=subprocess.run([sys.executable,str(script),'--config',str(config)],capture_output=True,text=True,timeout=3)
    assert result.returncode==1 and not result.stdout


def test_collected_original_replays_without_refreshing_expiry():
    from household.replay import compile_inputs
    from test_household_capabilities import originals
    managed,ownership=originals();raw=bundle()['sources'][0]['raw']
    result=collect(lambda *args:(NOW,raw))
    receipt=compile_inputs(result,managed=managed,ownership=ownership,code_revision='c'*40,runtime_manifest={'capture.py':'d'*64})
    assert receipt['snapshot']['completeness']['battery_display'] is True
    clocks=iter([NOW,NOW+timedelta(seconds=10)])
    from household.codec import loads,canonical
    record=loads(raw);record['validUntil']=int((NOW+timedelta(seconds=5)).timestamp()*1000)
    expired=collect(lambda *args:(NOW,canonical(record).decode()),clock=lambda:next(clocks))
    receipt=compile_inputs(expired,managed=managed,ownership=ownership,code_revision='c'*40,runtime_manifest={'capture.py':'d'*64})
    assert receipt['snapshot']['completeness']['battery_display'] is False


@pytest.mark.parametrize('damage',['sensor_epoch','targets','assessed_at','stream','policy'])
def test_native_reader_cannot_substitute_a_different_query_context(tmp_path,monkeypatch,damage):
    from test_weather_temperature_sources import case
    from thermal_model.temperature_history import STREAMS,POLICY
    from weather_temperature_evidence import TemperaturePolicy
    from weather_temperature_sources import build_temperature_source
    source=case(tmp_path,monkeypatch)
    source.update(rows=[],targets=[NOW],assessed_at=NOW,policy=TemperaturePolicy(STREAMS['air'][1],STREAMS['air'][2],**POLICY))
    expected=source['sensor_epoch']
    if damage=='sensor_epoch':source['sensor_epoch']='different-source-phase'
    elif damage=='targets':source['targets']=[NOW-timedelta(seconds=1)]
    elif damage=='assessed_at':source['assessed_at']=NOW+timedelta(seconds=1)
    elif damage=='stream':source['stream']='outdoor'
    else:source['policy']=TemperaturePolicy(STREAMS['air'][1],STREAMS['air'][2],minimum_f=-40,maximum_f=140,validity_seconds=121)
    with pytest.raises(ValueError):
        packet=build_temperature_source(**source)
        api().collect_inputs(epochs={'air_temperature':expected},
            policy={'requirements':{'air_display':['air_temperature']},'max_age_seconds':{'air_temperature':120},'max_skew_seconds':60},
            receipt_reader=lambda *args:pytest.fail('unexpected energy read'),native_reader=lambda **request:packet,
            clock=lambda:NOW,monotonic=lambda:0.0)


def test_native_connection_timeout_obeys_remaining_total_budget(tmp_path,monkeypatch):
    import household_capture,psycopg2,json
    from uuid import uuid4
    private=tmp_path/'db.json'
    private.write_text(json.dumps(dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password=str(uuid4()))))
    private.chmod(0o600);calls=[]
    monkeypatch.setattr(psycopg2,'connect',lambda **kwargs:calls.append(kwargs['connect_timeout']) or object())
    factory=household_capture._connection(str(private),'weather_temperature_reader')
    with pytest.raises(ValueError):factory(remaining=lambda:0.9)
    assert calls==[]
    factory(remaining=lambda:1.9)
    factory(remaining=lambda:15.0)
    assert calls==[1,2]
