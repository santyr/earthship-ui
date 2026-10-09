"""Cached score receipts must match selection from retained raw query packets."""
from datetime import timedelta
import importlib
import pytest
from test_thermal_sensor_epoch_history import sources,EPOCHS
from test_weather_temperature_reader import AT
from weather_temperature_config import load_temperature_receiver_configuration
from weather_temperature_sources import build_temperature_source,write_temperature_source,replay_temperature_source
from thermal_model.forcing_capture import _canonical
import json


def module():
    assert importlib.util.find_spec('thermal_model.installed_shade_raw_score_sources') is not None,'missing raw score binding'
    return importlib.import_module('thermal_model.installed_shade_raw_score_sources')


def inputs(tmp_path,monkeypatch):
    policy_path,rows=sources(tmp_path,monkeypatch);policies,_=load_temperature_receiver_configuration(str(policy_path))
    tmp_path.chmod(0o700);issue=AT+timedelta(minutes=2);target=issue+timedelta(hours=1)
    # Shift unchanged whole snapshots and embedded original receipt clocks for
    # a later synthetic outcome, without copying a selected scalar receipt.
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_evidence import MODELS
    collector=TemperatureCollector({'indoor':policies['indoor']},sensor_epochs={'indoor':EPOCHS['air']},clock=lambda:target-timedelta(seconds=30),monotonic=lambda:1000,process_id=lambda:1)
    p=policies['indoor'];collector.observe({'model':p.model,'id':str(p.sensor_id),MODELS[p.model][1]:'73'})
    outcome_rows=[(target-timedelta(seconds=20),json.dumps(collector.snapshot()))]
    paths=[];grids=[]
    for raw,targets,assessed in [(rows[:1],[AT+timedelta(seconds=60)],issue),(outcome_rows,[target],target+timedelta(minutes=10))]:
        packet=build_temperature_source(rows=raw,targets=targets,assessed_at=assessed,stream='indoor',policy=p,sensor_epoch=EPOCHS['air'])
        paths.append(str(write_temperature_source(tmp_path,packet)));grids.append(json.loads(_canonical(replay_temperature_source(packet))))
    score=dict(origin_path='/fixture/origin',publication={'fixture':True},horizon_hours=1,outcome={'target_at':target.isoformat(),'receipt':grids[1][0][1]},recent_cycle_grid=grids[0])
    return dict(score_packet=score,source_paths=paths,issue_at=issue,sensor_epoch=EPOCHS['air'],assessed_at=target+timedelta(minutes=10))


def test_binding_replays_raw_sources_without_trusting_cached_receipts(tmp_path,monkeypatch):
    m=module();args=inputs(tmp_path,monkeypatch);binding=m.build_native_score_binding(**args)
    assert binding['release_authority'] is False
    assert m.replay_native_score_binding(binding,args['score_packet'],issue_at=args['issue_at'],sensor_epoch=args['sensor_epoch'],assessed_at=args['assessed_at'])==binding


@pytest.mark.parametrize('damage',['changed_outcome','changed_comparator','missing_query','duplicate_query','phase','future_assessment','deleted_source'])
def test_wrong_or_missing_raw_sources_refuse_binding(tmp_path,monkeypatch,damage):
    from pathlib import Path
    m=module();args=inputs(tmp_path,monkeypatch)
    if damage=='changed_outcome':args['score_packet']['outcome']['receipt']['temperatureF']=99.
    elif damage=='changed_comparator':args['score_packet']['recent_cycle_grid'][0][1]['temperatureF']=99.
    elif damage=='missing_query':args['source_paths'].pop()
    elif damage=='duplicate_query':args['source_paths'].append(args['source_paths'][0])
    elif damage=='phase':args['sensor_epoch']=EPOCHS['mass']
    elif damage=='future_assessment':args['assessed_at']=args['issue_at']
    else:Path(args['source_paths'][0]).unlink()
    with pytest.raises((ValueError,OSError)):m.build_native_score_binding(**args)
