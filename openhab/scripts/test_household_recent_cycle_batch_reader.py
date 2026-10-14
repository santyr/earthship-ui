"""Coalesce baseline acquisition without changing original score replay inputs."""
from datetime import timedelta
from pathlib import Path
import pytest
from test_installed_shade_score_inputs import settings
from test_native_paired_score_reader import reader
from test_weather_temperature_reader import AT
from test_thermal_sensor_epoch_history import EPOCHS


def setup_reader(settings,monkeypatch):
    import native_thermal_live as native
    import household_native_score_queries as queries
    selected=getattr(queries,'RecentCycleWindowReader',queries.EndpointWindowScoreReader)
    monkeypatch.setattr(native,'NativeScoreReader',selected)
    r,calls=reader(settings,monkeypatch)
    tick={'at':0.}
    from thermal_model.capture_readers import ReadBudget
    def sleep(seconds):tick['at']+=seconds
    r.budget=r.transport.budget=ReadBudget(50,max_requests=40,clock=lambda:tick['at'],sleeper=sleep,guard=lambda:None)
    connect=r._connect
    def paced(config):r.budget.begin();return connect(config)
    monkeypatch.setattr(r,'_connect',paced)
    return r,calls,tick


def history(r,*,count=31):
    issue=AT+timedelta(days=30)
    for lag in range(1,count+1):
        points=[issue-timedelta(days=lag),issue-timedelta(days=lag)+timedelta(hours=1)]
        assert r.native(points,assessed_at=issue,sensor_epoch=EPOCHS['air'])==[(at,None) for at in points]
    return issue


def test_baseline_batch_and_outcome_use_two_paced_closed_readonly_transactions(settings,monkeypatch):
    r,calls,tick=setup_reader(settings,monkeypatch)
    issue=history(r);target=issue+timedelta(hours=1)
    assert r.native([target],assessed_at=target+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])==[(target,None)]
    assert len(calls)==r.budget.requests==2
    assert tick['at']==1 and r.budget.max_requests==40 and r.budget.interval==1
    assert all(c.closed and c.session=={'readonly':True,'autocommit':False,'isolation_level':'REPEATABLE READ'} for c in calls)
    assert len(r.native_source_paths)==32
    from weather_temperature_sources import read_compressed_temperature_source
    for path in r.native_source_paths:
        packet=read_compressed_temperature_source(Path(path).parent,Path(path))
        assert 1<=len(packet['targets'])<=2 and packet['release_authority'] is False


def test_early_comparator_stop_retains_only_requested_original_packets(settings,monkeypatch):
    r,calls,tick=setup_reader(settings,monkeypatch);history(r,count=7)
    assert len(calls)==1 and len(r.native_source_paths)==7
    Path(settings[1]['native_policy']).write_text('{}')
    issue=AT+timedelta(days=30);targets=[issue-timedelta(days=8),issue-timedelta(days=8)+timedelta(hours=1)]
    with pytest.raises(ValueError):r.native(targets,assessed_at=issue,sensor_epoch=EPOCHS['air'])
    assert len(calls)==1 and len(r.native_source_paths)==7


def test_serving_coordinator_uses_the_paced_baseline_batch(settings,monkeypatch,tmp_path):
    import household_forecast_score as coordinator,native_thermal_live as native
    from household_native_score_queries import RecentCycleWindowReader
    evidence=tmp_path/'evidence';evidence.mkdir(mode=0o700)
    config={**settings[1],'schema':native.SERVING_SCHEMA,'evidence_directory':str(evidence)}
    context=object()
    def score(value,**kwargs):
        assert isinstance(kwargs['reader'],RecentCycleWindowReader)
        assert value==config and kwargs['serving_model'] is context
        return {'status':'original-score-result'}
    monkeypatch.setattr(native,'score_jobs',score)
    assert coordinator.score_with_report(config,guard=lambda:None,serving_model=context)=={'status':'original-score-result'}


@pytest.mark.parametrize('null_barrier',[False,True])
def test_batched_original_receipts_equal_full_original_selection(settings,monkeypatch,tmp_path,null_barrier):
    from native_thermal_live import NativeScoreReader as OriginalScoreReader
    from test_installed_shade_score_inputs import WindowConnection
    from test_thermal_sensor_epoch_history import sources
    from thermal_model.installed_shade_score_inputs import COMPRESSED_SOURCE_SCHEMA
    _,rows=sources(tmp_path,monkeypatch)
    if null_barrier:rows.insert(1,(AT+timedelta(seconds=30),None))
    batch,calls,tick=setup_reader(settings,monkeypatch)
    connect=batch._connect
    def connected(config):
        connection=connect(config);connection.rows=rows;return connection
    monkeypatch.setattr(batch,'_connect',connected)
    original=OriginalScoreReader({**settings[1],'schema':COMPRESSED_SOURCE_SCHEMA},shared_lock_guard=lambda:None)
    monkeypatch.setattr(original,'_connect',lambda _:WindowConnection(rows=rows))
    targets=[AT+timedelta(minutes=1),AT+timedelta(minutes=6)]
    assessed=targets[0]+timedelta(days=1)
    kwargs=dict(assessed_at=assessed,sensor_epoch=EPOCHS['air'])
    expected=original.native(targets,**kwargs)
    assert batch.native(targets,**kwargs)==expected
    assert expected[0][1] is None if null_barrier else expected[0][1]['temperatureF']==70
    assert expected[1][1]['temperatureF']==71
    assert len(calls)==1 and calls[0].closed


def test_batch_aggregate_bound_refuses_before_any_packet_retention(settings,monkeypatch):
    import native_thermal_live as native
    batch,calls,tick=setup_reader(settings,monkeypatch)
    monkeypatch.setattr(native,'MAX_QUERY_BYTES',1)
    with pytest.raises(ValueError,match='aggregate'):history(batch,count=1)
    assert len(calls)==1 and calls[0].closed and not batch.native_source_paths
