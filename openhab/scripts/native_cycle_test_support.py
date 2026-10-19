"""Synthetic current-native publication and native-query fixtures; no live I/O."""
from datetime import timedelta
import json


def module():
    import native_thermal_live
    return native_thermal_live


def fixture(tmp_path,monkeypatch):
    from google_weather_fixtures import native_originals
    from test_native_thermal_live_publication import fixture as native_fixture,earlier_geometry
    from test_installed_shade_origin import native,weather,actions
    live,settings,backend,clock,candidate,geometry,runtime=native_fixture(tmp_path,monkeypatch,native_originals())
    original=backend.collect
    def collect(*,issue,known_at):
        values=original(issue=issue,known_at=known_at)
        clock[0]=known_at
        values['current'],values['origin_temperatures']=native(known_at)
        values['forecast']=weather(issue)
        values['action_snapshot']=actions(known_at)
        values['action_snapshot']['origin']=issue
        return values
    backend.collect=collect
    monkeypatch.setattr(live,'read_geometry',lambda settings,*,issue,guard:earlier_geometry(issue))
    return settings,backend,clock,candidate


def native_packet(directory,target,assessed,phase,*,qualified=False,stream='indoor'):
    from thermal_model.temperature_history import POLICY
    from weather_temperature_evidence import TemperaturePolicy,MODELS
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_sources import build_temperature_source,write_compressed_temperature_source
    policy=TemperaturePolicy('Fineoffset-WH32B',235,**POLICY);rows=[]
    if qualified:
        received=target-timedelta(seconds=30)
        collector=TemperatureCollector({'indoor':policy},sensor_epochs={'indoor':phase},clock=lambda:received,process_id=lambda:1,monotonic=lambda:1000.)
        collector.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:'70'})
        rows=[(target-timedelta(seconds=20),json.dumps(collector.snapshot()))]
    packet=build_temperature_source(rows=rows,targets=[target],assessed_at=assessed,stream=stream,policy=policy,sensor_epoch=phase)
    return write_compressed_temperature_source(directory,packet)


def energy_cycle(tmp_path,monkeypatch,originals=None):
    """One current publication supplies both coordinator and frozen plan."""
    from pathlib import Path
    from household.codec import loads
    from household.weather_context import prepare_native_cycle_contexts
    from test_household_cycle_coordinator import setup
    from test_household_energy_forecast import fixture as energy_fixture
    cycle,args,calls=setup(tmp_path,monkeypatch)
    capture=loads(Path(args['publication']['origin_path']).read_bytes())
    thermal,weather=prepare_native_cycle_contexts(capture,code_revision='e'*40,runtime=args['runtime'],
        expected_artifact_sha256=args['expected_artifact_sha256'],expected_capture_sha256=args['expected_capture_sha256'])
    _,source,plan=energy_fixture(tmp_path,monkeypatch,originals,native_context=(capture,None,thermal,weather))
    return cycle,args,calls,source,plan
