"""Native historical endpoints share one read-only original query snapshot."""
from datetime import timedelta,datetime,timezone
from pathlib import Path
import importlib
import pytest
from test_installed_shade_score_inputs import settings,WindowConnection
from test_thermal_sensor_epoch_history import EPOCHS,sources
from test_weather_temperature_reader import AT
from thermal_model.installed_shade_score_inputs import COMPRESSED_SOURCE_SCHEMA


def api():return importlib.import_module('native_thermal_live')

def reader(settings,monkeypatch,*,rows=None):
    import hourly_temperature_runtime
    config={**settings[1],'schema':COMPRESSED_SOURCE_SCHEMA};r=api().NativeScoreReader(config,shared_lock_guard=lambda:None)
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    calls=[]
    def connect(config):
        connection=WindowConnection(rows=rows or []);calls.append(connection);return connection
    monkeypatch.setattr(r,'_connect',connect)
    return r,calls


def test_paired_native_endpoint_query_uses_one_closed_readonly_connection(settings,monkeypatch):
    r,calls=reader(settings,monkeypatch)
    targets=[AT,AT+timedelta(hours=24)];result=r.native(targets,assessed_at=targets[-1]+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])
    assert result==[(at,None) for at in targets]
    assert len(calls)==1 and calls[0].closed
    assert calls[0].session=={'readonly':True,'autocommit':False,'isolation_level':'REPEATABLE READ'}
    assert len(r.native_source_paths)==1
    assert r.budget is r.transport.budget and r.budget.max_requests==40 and r.budget.interval==1
    assert not hasattr(r,'put')


def test_full_missing_history_and_outcome_fit_paced_native_request_budget(settings,monkeypatch):
    r,calls=reader(settings,monkeypatch);tick={'at':0.}
    from thermal_model.capture_readers import ReadBudget
    def sleep(seconds):tick['at']+=seconds
    r.budget=r.transport.budget=ReadBudget(50,max_requests=40,clock=lambda:tick['at'],sleeper=sleep,guard=lambda:None)
    original=r._connect
    def paced(config):r.budget.begin();return original(config)
    monkeypatch.setattr(r,'_connect',paced)
    issue=AT+timedelta(days=30)
    for lag in range(1,32):
        points=[issue-timedelta(days=lag),issue-timedelta(days=lag)+timedelta(hours=1)]
        assert r.native(points,assessed_at=issue,sensor_epoch=EPOCHS['air'])==[(at,None) for at in points]
    target=issue+timedelta(hours=1)
    r.native([target],assessed_at=target+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])
    assert len(calls)==32 and r.budget.requests==32 and tick['at']==31 and r.budget.remaining()==19
    assert len(r.native_source_paths)==32


def test_native_pair_replays_original_receipts_and_missing_barriers(settings,monkeypatch,tmp_path):
    _,rows=sources(tmp_path,monkeypatch);r,calls=reader(settings,monkeypatch,rows=rows)
    targets=[AT+timedelta(seconds=60),AT+timedelta(minutes=6)]
    first=r.native(targets,assessed_at=AT+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert [row[1]['temperatureF'] for row in first]==[70,71]
    first[0][1]['temperatureF']=99
    second=r.native(targets,assessed_at=AT+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert second[0][1]['temperatureF']==70 and len(calls)==1
    Path(r.native_source_paths[0]).unlink()
    with pytest.raises((ValueError,OSError)):r.native(targets,assessed_at=AT+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert len(calls)==1


@pytest.mark.parametrize('damage',['phase','future','span','duplicate','order','precision'])
def test_native_pair_refuses_wrong_original_request_before_connection(settings,monkeypatch,damage):
    r,calls=reader(settings,monkeypatch);targets=[AT,AT+timedelta(hours=1)];assessed=targets[-1]+timedelta(minutes=5);epoch=EPOCHS['air']
    if damage=='phase':epoch=EPOCHS['mass']
    if damage=='future':assessed=datetime.now(timezone.utc)+timedelta(days=1)
    if damage=='span':targets[-1]=AT+timedelta(days=1,seconds=1);assessed=targets[-1]+timedelta(minutes=5)
    if damage=='duplicate':targets[1]=targets[0]
    if damage=='order':targets.reverse()
    if damage=='precision':targets[0]=AT.isoformat().split('+')[0]+'.0000009+00:00'
    with pytest.raises(ValueError):r.native(targets,assessed_at=assessed,sensor_epoch=epoch)
    assert not calls


def test_native_reader_refuses_legacy_profile_and_changed_private_configuration(settings,monkeypatch):
    with pytest.raises(ValueError):api().NativeScoreReader(settings[1],shared_lock_guard=lambda:None)
    r,calls=reader(settings,monkeypatch);Path(settings[1]['native_policy']).write_text('{}')
    with pytest.raises(ValueError):r.native([AT],assessed_at=AT+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])
    assert not calls


def test_native_pair_preserves_null_snapshot_barrier(settings,monkeypatch,tmp_path):
    _,rows=sources(tmp_path,monkeypatch)
    rows.insert(1,(AT+timedelta(seconds=30),None))
    r,calls=reader(settings,monkeypatch,rows=rows)
    targets=[AT+timedelta(minutes=1),AT+timedelta(minutes=6)]
    result=r.native(targets,assessed_at=AT+timedelta(minutes=10),sensor_epoch=EPOCHS['air'])
    assert result[0]==(targets[0],None) and result[1][1]['temperatureF']==71
    assert len(calls)==1


def test_native_pair_bounds_aggregate_bytes_before_retention(settings,monkeypatch):
    r,calls=reader(settings,monkeypatch);monkeypatch.setattr(api(),'MAX_QUERY_BYTES',1)
    with pytest.raises(ValueError,match='aggregate'):
        r.native([AT],assessed_at=AT+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])
    assert len(calls)==1 and calls[0].closed
    assert not r.native_source_paths and list(Path(settings[1]['output_directory']).iterdir())==[]
