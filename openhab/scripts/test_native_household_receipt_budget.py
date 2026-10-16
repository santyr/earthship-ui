"""Valid full-precision native context and bounded original JSON must fit privately."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json,math
import pytest
from test_native_serving_forecast import context,originals


def pretty_original(raw,maximum=4000):
    value=json.loads(raw);low,high=0,4096
    while low<high:
        middle=(low+high+1)//2
        if len(json.dumps(value,indent=middle).encode())<=maximum:low=middle
        else:high=middle-1
    return json.dumps(value,indent=low)


def test_valid_native_receipt_replays_above_one_mebibyte_with_bounded_public_view(tmp_path,originals,monkeypatch):
    from astro_geometry import build_source,build_cache
    from astro_geometry_series import build_series
    from household.codec import canonical
    from household.control_contracts import instant
    from household.weather_context import prepare_serving_native_cycle_contexts
    from household.power_snapshot import compile_power_inputs
    from household.energy_configuration import prepare_energy_configuration
    from household.measured_weather import prepare_measured_weather
    from household.measured_weather_snapshot import bind_measured_weather_snapshot
    from test_household_model_snapshot import source_at
    from test_household_capabilities import originals as registry_originals
    from test_household_energy_configuration import args as configuration_args
    from test_household_measured_weather import sources
    from test_household_model_pipeline import run,RUNTIME
    forecasts,_,_,model,inputs,kwargs,_=context(tmp_path,originals,monkeypatch)
    issue=kwargs['issue'];packet=kwargs['geometry'].to_dict();caches=[];index=0
    for old in packet['caches']:
        request=old['request'];source=old['source'];rows=[]
        for at in request['instants']:
            index+=1;rows.append(f'{at}\t{-25+55*math.sin(index/91.123456789)}\t{(index*1.2345678910111213)%360}\n')
        caches.append(build_cache(request,source,native_output=''.join(rows).encode(),computed_at=issue-timedelta(seconds=4)))
    geometry=build_series(packet['request'],caches,expected_native_runtime=packet['native_runtime'])
    kwargs.update(geometry=geometry,expected_geometry_sha256=geometry.sha256)
    capture=forecasts.build_serving_capture(model,inputs,**kwargs)
    thermal,weather=prepare_serving_native_cycle_contexts(capture,model,code_revision='a'*40,expected_capture_sha256=capture['capture_sha256'],check_budget=lambda:None)
    original_source=source_at(issue);power_inputs=deepcopy(original_source['inputs']['bundle'])
    # Pretty-printed source JSON remains a valid original. Each source stays
    # below its existing 4 KiB bound; its actual byte identity is resealed.
    for row in power_inputs['base_inputs']['sources']+power_inputs['power_sources']:
        row['raw']=pretty_original(row['raw']);row['expected_sha256']=sha256(row['raw'].encode()).hexdigest()
    # A normal bounded history can contain several full receiver snapshots.
    # Preserve all originals for each declared native role, as production does.
    from weather_temperature_receiver import TemperatureCollector
    from weather_temperature_evidence import TemperaturePolicy,MODELS
    from weather_temperature_sources import build_temperature_source
    from thermal_model.temperature_history import STREAMS,POLICY
    from test_thermal_sensor_epoch_origins import EPOCHS,VALUES
    policies={stream:TemperaturePolicy(model_name,sensor,**POLICY) for stream,model_name,sensor in STREAMS.values()}
    phases={identity[0]:EPOCHS[role] for role,identity in STREAMS.items()}
    observed={'at':issue-timedelta(seconds=119),'tick':1000}
    receiver=TemperatureCollector(policies,sensor_epochs=phases,clock=lambda:observed['at'],monotonic=lambda:observed['tick'],process_id=lambda:1)
    rows=[]
    for index in range(6):
        observed.update(at=issue-timedelta(seconds=119-index*20),tick=1000+index*20)
        for stream,policy in policies.items():receiver.observe({'model':policy.model,'id':str(policy.sensor_id),MODELS[policy.model][1]:str(VALUES[stream])})
        rows.append((observed['at']+timedelta(seconds=1),pretty_original(json.dumps(receiver.snapshot()),7900)))
    for role,identity in STREAMS.items():
        stream=identity[0];packet=build_temperature_source(rows=rows,targets=[issue],assessed_at=issue,stream=stream,policy=policies[stream],sensor_epoch=EPOCHS[role])
        raw=canonical(packet).decode();name=role+'_temperature'
        power_inputs['base_inputs']['sources'].append(dict(kind='native_temperature',source_role=name,source_identity='Weather_Temperature_Evidence_JSON:'+stream,expected_epoch=EPOCHS[role],expected_sha256=sha256(raw.encode()).hexdigest(),persisted_at=None,raw=raw))
        power_inputs['base_inputs']['policy']['max_age_seconds'][name]=120
    managed,ownership=registry_originals()
    source=compile_power_inputs(power_inputs,managed=managed,ownership=ownership,code_revision='c'*40,runtime_manifest=original_source['runtime_manifest'])
    config=configuration_args();config.update(bank_available_at=issue-timedelta(seconds=2),topology_available_at=issue-timedelta(seconds=1),as_of=issue,created_at=issue+timedelta(seconds=1))
    energy=prepare_energy_configuration(**config)
    measured=prepare_measured_weather(sources=sources(issue),as_of=issue,created_at=issue+timedelta(seconds=1))
    snapshot=bind_measured_weather_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],weather_context=weather,energy_configuration=energy,measured_weather=measured,code_revision='a'*40)
    result=run(snapshot,thermal,runtime_manifest=RUNTIME)
    assert 1024*1024<len(canonical(result))<=2*1024*1024
    assert result['output']['projections']['thermal']['output']==capture['output']
    from household.pipeline import replay_pipeline
    # observe_pipeline below performs the complete independent receipt replay.
    from household_observation import observe_pipeline
    view=observe_pipeline(result,runtime_manifest=RUNTIME,thermal_runtime=thermal.to_dict()['executing_runtime'],observed_at=instant(result['inputs']['now']))
    assert len(canonical(view))<=32768 and view['automatic_actuation'] is False
    oversized=deepcopy(result);oversized['inputs']['coordination']['facts']['untrusted']='x'*(2*1024*1024)
    import household.pipeline as pipeline
    monkeypatch.setattr(pipeline,'_restore',lambda *a,**k:pytest.fail('oversized untrusted receipt reached model replay'))
    with pytest.raises(ValueError,match='closed bounded original model/plan receipt'):
        replay_pipeline(oversized,runtime_manifest=RUNTIME,thermal_runtime=thermal.to_dict()['executing_runtime'])
