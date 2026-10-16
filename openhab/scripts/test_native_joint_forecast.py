"""Removed-shade forecasts retain all causal inputs and withhold action advice."""
from datetime import timedelta
import json
import pytest
import native_thermal_forecast as api
from test_native_joint_artifact import joint_originals,make
from test_native_thermal_forecast import future,ISSUE
from test_provisional_thermal_forecast import actions,weather,native

def issued(tmp_path,joint_originals,monkeypatch):
    c,_,runtime,_=make(tmp_path,joint_originals);current,proof=native(ISSUE)
    action=actions(ISSUE);action['actions']['outdoor_shade']['state']='removed'
    action['actions']['vent']['state']='open'
    inputs=dict(forecast=weather(ISSUE),current=current,origin_temperatures=proof,action_snapshot=action,native_source_paths={'mathematical':'source'})
    monkeypatch.setattr(api,'build_binding',lambda *a,**k:{'mathematical':'binding'});monkeypatch.setattr(api,'replay_binding',lambda *a,**k:None)
    g=future(ISSUE)
    capture=api.build_capture(c,inputs,geometry=g,runtime=runtime,expected_artifact_sha256=c['artifact_sha256'],expected_geometry_sha256=g.sha256,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2))
    return capture,runtime

def test_removed_shade_forecast_replays_with_vent_and_explicit_unlearned_priors(tmp_path,joint_originals,monkeypatch):
    capture,runtime=issued(tmp_path,joint_originals,monkeypatch);out=capture['output'];payload=api.publication(capture)
    assert out['origin_actions']['outdoor_shade_present']==0 and out['origin_actions']['vent_open']==1
    assert out['model_rule']=='earthship-native-joint-shade-dynamics/v3'
    assert out['advice']==[] and out['automatic_actuation'] is False
    assert any('65%' in r and 'prior' in r.lower() for r in payload['reasons'])
    assert api.validate_capture(capture,runtime=runtime,expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])==capture

def test_joint_household_replay_preserves_original_forecast_without_reads(tmp_path,joint_originals,monkeypatch):
    from household.weather_context import prepare_native_cycle_contexts,PreparedWeatherContext,project_weather
    from household.thermal_model import project
    from household.codec import canonical
    from pathlib import Path
    import builtins,os,psycopg2
    capture,runtime=issued(tmp_path,joint_originals,monkeypatch)
    thermal,weather=prepare_native_cycle_contexts(capture,code_revision='a'*40,runtime=runtime,expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    assert project(thermal)['output']==capture['output'];expected=project_weather(weather)
    def refused(*args,**kwargs):pytest.fail('I/O during frozen joint model replay')
    for target,name in ((builtins,'open'),(os,'open'),(Path,'read_bytes'),(psycopg2,'connect')):monkeypatch.setattr(target,name,refused)
    restored=PreparedWeatherContext(canonical(weather.to_dict()))
    assert project_weather(restored)==expected
