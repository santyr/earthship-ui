"""Original meteorological forecasts remain context, never measured weather."""
import importlib,base64,zlib
from hashlib import sha256
from pathlib import Path
import pytest
from household.codec import canonical,identity
from test_household_models import prepared_thermal


def api():return importlib.import_module('household.weather_context')


def make(tmp_path,monkeypatch):
    prepared,capture=prepared_thermal(tmp_path,monkeypatch)
    frozen=api().prepare_weather_context(capture,prepared_thermal=prepared)
    return frozen,prepared,capture


def test_original_receipts_and_exact_forcing_clocks_units_are_preserved(tmp_path,monkeypatch):
    frozen,prepared,capture=make(tmp_path,monkeypatch);out=api().project_weather(frozen);source=capture['inputs']['forecast']
    assert out['original_capture_sha256']==capture['capture_sha256']
    assert out['weather_rows_sha256']==source['rows_sha256']
    assert out['provider_issued_at']==source['issued_at'] and out['provider_captured_at']==source['captured_at']
    assert out['origin']==prepared.to_dict()['issue'] and out['available_at']==capture['inputs_available_at']
    assert out['forcings']==prepared.to_dict()['forcings']
    assert out['hourly_forecast']==source['rows']
    assert out['origin_states']==prepared.to_dict()['actions']
    assert out['confidence']=='not_assessed' and out['input_qualification']=='not_assessed'
    assert out['action_effects_qualified'] is False and out['automatic_actuation'] is False
    assert out['unknown_observations']==['solar_radiation_wm2','relative_humidity','precipitation','wind_speed','daylight_geometry']


@pytest.mark.parametrize('damage',['wind','availability','action','prepared','extra'])
def test_resealed_context_cannot_detach_original_weather_or_model(damage,tmp_path,monkeypatch):
    frozen,_,_=make(tmp_path,monkeypatch);body=frozen.to_dict()
    original=frozen.original_capture
    if damage=='wind':original['inputs']['forecast']['rows'][0]['windMph']+=1
    elif damage=='availability':original['inputs_available_at']=original['published_at']
    elif damage=='action':original['output']['origin_actions']['vent_open']=1-original['output']['origin_actions']['vent_open']
    elif damage=='prepared':body['prepared_thermal']['forcings'][0]['radiation_wm2']+=1
    else:body['owner_available']=True
    if damage in ('wind','availability','action'):
        raw=canonical(original);body['original_capture']=dict(encoding='zlib-base64-v1',uncompressed_bytes=len(raw),uncompressed_sha256=sha256(raw).hexdigest(),data=base64.b64encode(zlib.compress(raw,9)).decode())
    body['weather_sha256']=identity({k:v for k,v in body.items() if k!='weather_sha256'})
    with pytest.raises(ValueError):api().PreparedWeatherContext(canonical(body))


def test_originals_and_returned_values_cannot_mutate_context(tmp_path,monkeypatch):
    frozen,prepared,capture=make(tmp_path,monkeypatch);before=api().project_weather(frozen)
    capture['inputs']['forecast']['rows'][0]['windMph']+=1
    after=frozen.original_capture;after['inputs']['forecast']['rows'][0]['windMph']+=1
    assert api().project_weather(frozen)==before
    assert frozen.to_dict()['prepared_thermal']==prepared.to_dict()


def test_projection_and_restore_perform_no_reads(tmp_path,monkeypatch):
    frozen,_,_=make(tmp_path,monkeypatch);expected=api().project_weather(frozen)
    import builtins,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('read inside frozen weather boundary')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    restored=api().PreparedWeatherContext(canonical(frozen.to_dict()))
    assert api().project_weather(restored)==expected


@pytest.mark.parametrize('damage',['trailing','truncated','oversize','size'])
def test_compressed_original_has_strict_complete_bounded_decode(damage,tmp_path,monkeypatch):
    frozen,_,_=make(tmp_path,monkeypatch);body=frozen.to_dict();original=body['original_capture'];packed=base64.b64decode(original['data'])
    if damage=='trailing':packed+=b'ignored-trailer'
    elif damage=='truncated':packed=packed[:-1]
    elif damage=='size':original['uncompressed_bytes']-=1
    else:
        packed=zlib.compress(b'X'*(2*1024*1024+1),9);original['uncompressed_bytes']=2*1024*1024
    original['data']=base64.b64encode(packed).decode();body['weather_sha256']=identity({k:v for k,v in body.items() if k!='weather_sha256'})
    with pytest.raises(ValueError,match='bounded compressed original'):api().PreparedWeatherContext(canonical(body))


def reseal_weather(body,original):
    from thermal_model.provisional_forecast import digest as capture_digest
    original['capture_sha256']=capture_digest(original,'capture_sha256')
    model=body['prepared_thermal'];model['original_capture_sha256']=original['capture_sha256']
    snapshot=model['snapshot']
    for rows in snapshot['domains'].values():
        for row in rows.values():
            if row['evidence'] is not None:
                row['evidence']['parent_digests']=[original['capture_sha256']]
    snapshot['snapshot_id']=identity({k:v for k,v in snapshot.items() if k!='snapshot_id'})
    model['prepared_sha256']=identity({k:v for k,v in model.items() if k!='prepared_sha256'})
    raw=canonical(original)
    body['original_capture']=dict(encoding='zlib-base64-v1',uncompressed_bytes=len(raw),
        uncompressed_sha256=sha256(raw).hexdigest(),data=base64.b64encode(zlib.compress(raw,9)).decode())
    body['weather_sha256']=identity({k:v for k,v in body.items() if k!='weather_sha256'})
    return canonical(body)


@pytest.mark.parametrize('damage',['measurement','source_clock','policy'])
def test_fully_resealed_snapshot_must_match_original_sensor_receipts(damage,tmp_path,monkeypatch):
    frozen,_,_=make(tmp_path,monkeypatch);body=frozen.to_dict();original=frozen.original_capture
    snapshot=body['prepared_thermal']['snapshot'];row=snapshot['domains']['thermal']['mass_temperature']
    if damage=='measurement':row['value']+=1
    elif damage=='source_clock':row['evidence']['received_at']=row['evidence']['available_at']
    else:snapshot['temporal_policy']['max_age_seconds']['mass_temperature']=121
    with pytest.raises(ValueError,match='original sensor evidence'):
        api().PreparedWeatherContext(reseal_weather(body,original))


@pytest.mark.parametrize('reseal_candidate',[False,True])
def test_fully_resealed_candidate_must_match_artifact_and_prepared_coefficients(reseal_candidate,tmp_path,monkeypatch):
    from thermal_model.provisional_artifact import candidate_digest
    frozen,_,_=make(tmp_path,monkeypatch);body=frozen.to_dict();original=frozen.original_capture
    candidate=original['candidate'];candidate['fit']['coefficients'][0]+=0.01
    if reseal_candidate:
        candidate['artifact_sha256']=candidate_digest(candidate)
        body['prepared_thermal']['artifact_sha256']=candidate['artifact_sha256']
        original['output']['artifact_sha256']=candidate['artifact_sha256']
    with pytest.raises(ValueError,match='original candidate'):
        api().PreparedWeatherContext(reseal_weather(body,original))


def test_shared_cycle_preparation_preserves_both_contexts_with_one_original_replay(tmp_path,monkeypatch):
    expected_weather,expected_thermal,capture=make(tmp_path,monkeypatch)
    from thermal_model import provisional_forecast
    original=provisional_forecast.validate_capture;calls=[]
    def validate(value,**kwargs):
        calls.append(value['capture_sha256'])
        return original(value,**kwargs)
    monkeypatch.setattr(provisional_forecast,'validate_capture',validate)
    thermal,weather=api().prepare_cycle_contexts(capture,code_revision='a'*40)
    assert thermal.content==expected_thermal.content
    assert weather.content==expected_weather.content
    assert calls==[capture['capture_sha256']]
    capture['inputs']['forecast']['rows'][0]['windMph']+=1
    assert weather.content==expected_weather.content


def test_shared_cycle_preparation_still_replays_original_native_binding(tmp_path,monkeypatch):
    _,_,capture=make(tmp_path,monkeypatch)
    from thermal_model import provisional_forecast
    def reject(*args,**kwargs):raise ValueError('changed original native archive')
    monkeypatch.setattr(provisional_forecast,'replay_binding',reject)
    with pytest.raises(ValueError,match='changed original native archive'):
        api().prepare_cycle_contexts(capture,code_revision='a'*40)


def test_shared_cycle_preparation_refuses_resealed_numerical_output(tmp_path,monkeypatch):
    _,_,capture=make(tmp_path,monkeypatch)
    from thermal_model.provisional_forecast import digest
    capture['output']['trajectory'][0]['air_f']+=1
    capture['capture_sha256']=digest(capture,'capture_sha256')
    with pytest.raises(ValueError):api().prepare_cycle_contexts(capture,code_revision='a'*40)
