"""Native geometry and weather remain bound to the same frozen household issue."""
from copy import deepcopy
from pathlib import Path
import importlib
import pytest
from household.codec import canonical,identity
from test_household_native_thermal import context,prepare,originals,CODE


def api():return importlib.import_module('household.weather_context')

def made(tmp_path,monkeypatch,originals):
    c,k=context(tmp_path,monkeypatch,originals)
    thermal,weather=api().prepare_native_cycle_contexts(c,code_revision=CODE,**k)
    return c,k,thermal,weather


def test_native_weather_and_thermal_share_original_geometry_and_issue(tmp_path,monkeypatch,originals):
    c,k,p,w=made(tmp_path,monkeypatch,originals);out=api().project_weather(w)
    assert w.to_dict()['schema']=='earthship-household-prepared-weather/v2'
    assert w.original_capture==c and w.prepared.to_dict()==p.to_dict()
    assert out['schema']=='earthship-household-weather-projection/v2'
    assert out['geometry_series_sha256']==c['geometry_series_sha256']
    assert out['model_rule']==c['output']['model_rule']
    assert out['origin']==c['issued_at'] and out['forcings']==p.to_dict()['forcings']
    assert out['input_qualification']=='not_assessed' and out['automatic_actuation'] is False
    assert api().prepare_native_weather_context(c,prepared_thermal=p,**k).to_dict()==w.to_dict()


def test_native_weather_restore_project_and_pipeline_have_no_io(tmp_path,monkeypatch,originals):
    c,k,p,w=made(tmp_path,monkeypatch,originals)
    from household.weather_snapshot import bind_weather_snapshot
    from household.control_contracts import instant
    from test_household_model_snapshot import source_at
    from test_household_model_pipeline import run,RUNTIME
    from household.pipeline import replay_pipeline
    source=source_at(instant(c['issued_at']))
    snap=bind_weather_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],weather_context=w,code_revision=CODE)
    record=run(snap,p);expected=api().project_weather(w)
    import builtins,os,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('I/O during native weather/pipeline replay')
    for target,name in ((builtins,'open'),(os,'open'),(Path,'read_bytes'),(psycopg2,'connect')):monkeypatch.setattr(target,name,forbidden)
    restored=api().PreparedWeatherContext(canonical(w.to_dict()))
    assert api().project_weather(restored)==expected
    assert replay_pipeline(record,runtime_manifest=RUNTIME,thermal_runtime=p.to_dict()['executing_runtime'])==record
    assert record['output']['projections']['thermal']['output']==c['output']
    assert record['output']['projections']['weather']==expected


@pytest.mark.parametrize('damage',['geometry','model','runtime','forcing','version','measurement'])
def test_resealed_native_weather_refuses_detached_originals(tmp_path,monkeypatch,originals,damage):
    c,k,p,w=made(tmp_path,monkeypatch,originals);body=w.to_dict();model=body['prepared_thermal']
    if damage=='geometry':model['geometry_series_sha256']='f'*64
    if damage=='model':model['coefficients'][0]*=.99
    if damage=='runtime':model['runtime_sha256']='f'*64
    if damage=='forcing':model['forcings'][0]['radiation_wm2']+=1
    if damage=='version':body['schema']='earthship-household-prepared-weather/v1'
    if damage=='measurement':model['snapshot']['domains']['thermal']['air_temperature']['value']+=1
    model['prepared_sha256']=identity({key:v for key,v in model.items() if key!='prepared_sha256'})
    body['weather_sha256']=identity({key:v for key,v in body.items() if key!='weather_sha256'})
    with pytest.raises(ValueError):api().PreparedWeatherContext(canonical(body))


def test_native_cycle_contexts_freeze_caller_and_require_external_pins(tmp_path,monkeypatch,originals):
    c,k=context(tmp_path,monkeypatch,originals);saved=deepcopy(c)
    def changed():c['inputs']['forecast']['rows'][0]['tempF']=99
    p,w=api().prepare_native_cycle_contexts(c,code_revision=CODE,**k,check_budget=changed)
    assert w.original_capture==saved
    k['expected_capture_sha256']='f'*64
    with pytest.raises(ValueError):api().prepare_native_cycle_contexts(saved,code_revision=CODE,**k)


def test_native_private_pipeline_cli_replays_full_source_closure(tmp_path,monkeypatch,originals,capsys):
    c,k,p,w=made(tmp_path,monkeypatch,originals)
    import household_pipeline as cli
    from household.power_snapshot import compile_power_inputs
    from household.weather_snapshot import bind_weather_snapshot
    from household.control_contracts import instant
    from test_household_model_snapshot import source_at
    from test_household_model_pipeline import run
    runtime=cli.pipeline_runtime_manifest(expanded=True);source=source_at(instant(c['issued_at']));original=source['inputs']
    source=compile_power_inputs(original['bundle'],managed=original['managed'],ownership=original['ownership'],code_revision=original['code_revision'],runtime_manifest=runtime)
    snapshot=bind_weather_snapshot(source_receipt=source,source_runtime_manifest=runtime,weather_context=w,code_revision=CODE)
    record=run(snapshot,p,runtime_manifest=runtime);path=tmp_path/'native-pipeline.json';path.write_bytes(canonical(record));path.chmod(0o600)
    assert cli.main(['--receipt',str(path)])==0
    import json
    assert json.loads(capsys.readouterr().out)==record
    import native_thermal_artifact as artifacts
    wrong=deepcopy(k['runtime']);wrong['native_source_manifest']['openhab/scripts/native_thermal_forecast.py']='f'*64
    wrong['native_code_revision']=artifacts.digest(wrong['native_source_manifest'])
    monkeypatch.setattr(artifacts,'current_native_runtime',lambda **kw:wrong)
    assert cli.main(['--receipt',str(path)])==1
    assert 'replay refused' in capsys.readouterr().err
