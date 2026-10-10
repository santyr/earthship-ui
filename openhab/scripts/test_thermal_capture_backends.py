"""Capture backend provenance and shared budgets with synthetic connections."""
from datetime import datetime,timedelta,timezone
import pytest
from thermal_model.capture_readers import ReadBudget
from thermal_model.schema import THERMAL_ITEMS


def module():
    from thermal_model import capture_backends
    return capture_backends


def environment(now):
    return {'THERMAL_TEMP_QUALIFIED_ENABLE':'1','THERMAL_TEMP_EVIDENCE_CUTOVER':now.isoformat(),
            'THERMAL_TEMP_DB_CONFIG':'/synthetic/private-db.json','THERMAL_TEMP_POLICY':'/synthetic/policy.json'}


def test_native_capture_uses_existing_collector_and_shared_connection_budget(monkeypatch):
    source=module();import thermal_temperature_runtime as runtime
    now=datetime(2026,8,1,tzinfo=timezone.utc);clock=[0.];connections=[];requests=[]
    config=dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic')
    def connect(dsn):connections.append((dsn,clock[0]));return object()
    def collect(request,*,config_path,policy_path,connection_factory):
        assert config_path=='/synthetic/private-db.json' and policy_path=='/synthetic/policy.json'
        requests.append(request);connection_factory(config)
        return [(datetime.fromisoformat(at),None) for at in request['targets']]
    monkeypatch.setattr(source.psycopg2,'connect',connect);monkeypatch.setattr(runtime,'collect',collect)
    def sleep(seconds):clock[0]+=seconds
    budget=ReadBudget(10,clock=lambda:clock[0],sleeper=sleep)
    reader=source.configured_capture_history(lambda *args:pytest.fail('postcutover used legacy'),now+timedelta(hours=1),environ=environment(now),budget=budget)
    for role in ('air','mass','outdoor'):reader(THERMAL_ITEMS[role],now,now+timedelta(hours=1))
    assert reader.retains_native_grids and len(reader.temperature_grids())==3
    assert [request['stream'] for request in requests]==['indoor','north_wall','outdoor']
    assert [at for dsn,at in connections]==[0.,1.,2.] and budget.requests==3
    from psycopg2.extensions import parse_dsn
    for dsn,at in connections:
        params=parse_dsn(dsn)
        assert params['hostaddr']=='127.0.0.1' and params['connect_timeout']=='3'
        assert 'default_transaction_read_only=on' in params['options']


@pytest.mark.parametrize('damage',['disabled','missing','unaligned'])
def test_invalid_native_capture_configuration_refuses_before_source_reads(damage,monkeypatch):
    source=module();now=datetime(2026,8,1,tzinfo=timezone.utc);env=environment(now)
    if damage=='disabled':env['THERMAL_TEMP_QUALIFIED_ENABLE']='0'
    if damage=='missing':env.pop('THERMAL_TEMP_POLICY')
    if damage=='unaligned':env['THERMAL_TEMP_EVIDENCE_CUTOVER']=(now+timedelta(seconds=1)).isoformat()
    monkeypatch.setattr(source.psycopg2,'connect',lambda *args:pytest.fail('invalid context connected'))
    with pytest.raises(ValueError):source.configured_capture_history(lambda *args:[],now+timedelta(hours=1),environ=env,budget=ReadBudget(5))


def test_native_capture_refuses_connection_without_remaining_timeout(monkeypatch):
    source=module();import thermal_temperature_runtime as runtime
    now=datetime(2026,8,1,tzinfo=timezone.utc);clock=[0.]
    def collect(request,*,config_path,policy_path,connection_factory):
        clock[0]=4
        return connection_factory(dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic'))
    monkeypatch.setattr(runtime,'collect',collect)
    monkeypatch.setattr(source.psycopg2,'connect',lambda *args:pytest.fail('expired context connected'))
    reader=source.configured_capture_history(lambda *args:[],now+timedelta(hours=1),environ=environment(now),budget=ReadBudget(5,clock=lambda:clock[0]))
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],now,now+timedelta(hours=1))


@pytest.mark.parametrize('barrier',[False,True])
def test_native_capture_retains_actual_collector_receipts_and_missing_barriers(monkeypatch,barrier):
    import math
    import hourly_temperature_runtime
    import weather_temperature_config
    from weather_temperature_evidence import TemperaturePolicy
    from thermal_model.temperature_history import STREAMS,POLICY
    from test_weather_temperature_history import Connection
    from test_weather_temperature_reader import AT,raw
    source=module();connections=[];clock=[0.]
    config=dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic')
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda path:config)
    monkeypatch.setattr(weather_temperature_config,'load_temperature_policies',lambda path:{stream:TemperaturePolicy(model,sensor,**POLICY) for stream,model,sensor in STREAMS.values()})
    def connect(dsn):
        value=Connection(rows=[(AT,None if barrier else raw())]);connections.append(value);return value
    monkeypatch.setattr(source.psycopg2,'connect',connect)
    def sleep(seconds):clock[0]+=seconds
    reader=source.configured_capture_history(lambda *args:pytest.fail('native source fell back'),AT+timedelta(minutes=10),environ=environment(AT),budget=ReadBudget(10,clock=lambda:clock[0],sleeper=sleep))
    rows={role:reader(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=10)) for role in STREAMS}
    assert math.isnan(rows['air'][1][1])
    assert math.isnan(rows['air'][0][1]) if barrier else rows['air'][0][1]==70
    grid=reader.temperature_grids()['air']
    assert grid[1][1] is None
    if barrier:assert grid[0][1] is None
    else:
        assert grid[0][1]['temperatureF']==70 and grid[0][1]['storedAt']==AT.isoformat()
        assert len(grid[0][1]['snapshotSha256'])==64
    assert all(c.closed and c.session['readonly'] is True for c in connections)
    assert all('LIMIT 10001' in c.calls[-1][0] for c in connections)


def test_native_capture_refuses_result_completed_after_deadline(monkeypatch):
    source=module();import thermal_temperature_runtime as runtime
    now=datetime(2026,8,1,tzinfo=timezone.utc);clock=[0.]
    def collect(request,**kwargs):
        clock[0]=6
        return [(datetime.fromisoformat(at),None) for at in request['targets']]
    monkeypatch.setattr(runtime,'collect',collect)
    reader=source.configured_capture_history(lambda *args:pytest.fail('expired read fell back'),now+timedelta(hours=1),environ=environment(now),budget=ReadBudget(5,clock=lambda:clock[0]))
    with pytest.raises(ValueError):reader(THERMAL_ITEMS['air'],now,now+timedelta(hours=1))


@pytest.mark.parametrize('failure',['connect','sql'])
def test_actual_native_collector_failure_aborts_without_fallback(monkeypatch,failure):
    import hourly_temperature_runtime,weather_temperature_config
    from weather_temperature_evidence import TemperaturePolicy
    from thermal_model.temperature_history import STREAMS,POLICY
    from test_weather_temperature_history import Connection
    from test_weather_temperature_reader import AT
    source=module();connections=[]
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda path:dict(host='127.0.0.1',port=5432,dbname='openhab',user='weather_temperature_reader',password='synthetic'))
    monkeypatch.setattr(weather_temperature_config,'load_temperature_policies',lambda path:{stream:TemperaturePolicy(model,sensor,**POLICY) for stream,model,sensor in STREAMS.values()})
    def connect(dsn):
        if failure=='connect':raise RuntimeError('private-test-marker')
        value=Connection(fail='time >=');connections.append(value);return value
    monkeypatch.setattr(source.psycopg2,'connect',connect)
    reader=source.configured_capture_history(lambda *args:pytest.fail('failed read fell back'),AT+timedelta(hours=1),environ=environment(AT),budget=ReadBudget(5))
    from weather_temperature_history import TemperatureHistoryUnavailable
    with pytest.raises(TemperatureHistoryUnavailable) as error:reader(THERMAL_ITEMS['air'],AT,AT+timedelta(hours=1))
    assert 'private-test-marker' not in str(error.value)
    assert all(c.closed for c in connections)
