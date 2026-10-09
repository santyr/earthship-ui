"""Invariant tests for original corrected forecasts; fixtures confer no skill."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
import pytest
import forecast_intel as fi


def module():
    assert importlib.util.find_spec('forecast_temperature_origin') is not None, 'missing exact temperature origin capture'
    return importlib.import_module('forecast_temperature_origin')


def inputs():
    snapshot = {
        'daily': {'time':['2026-10-09','2026-10-10'],
            'temperature_2m_max':[90.,90.], 'temperature_2m_min':[60.,60.],
            'shortwave_radiation_sum':[25.,25.], 'precipitation_probability_max':[10,10],
            'precipitation_sum':[0.,0.], 'weather_code':[1,3]},
        'hourly': {'time':['2026-10-10T12:00'], 'temperature_2m':[68.],
            'precipitation_probability':[10], 'precipitation':[0.],
            'shortwave_radiation':[400.], 'wind_speed_10m':[5.], 'weather_code':[3]}}
    model=fi.hourly_model_seed();model['12']={'b':4.,'P':1.,'count':14}
    adjustment={'highCorrectionF':2.5,'lowCorrectionF':-9.}
    now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN)
    payloads=fi.build_forecast_payloads(snapshot,[],now,temperature_adjustment=adjustment,hourly_model=model)
    return snapshot,model,adjustment,payloads


@pytest.fixture
def setup(tmp_path,monkeypatch):
    m=module();root=tmp_path/'origins';root.mkdir(mode=0o700)
    runtime=tmp_path/'code';runtime.mkdir(mode=0o700)
    for name in m.RUNTIME_PATHS:
        source=Path(fi.__file__).parent/name
        (runtime/name).write_bytes(source.read_bytes());(runtime/name).chmod(0o600)
    monkeypatch.setattr(m,'RUNTIME_ROOT',runtime)
    # Match the established origin-binding fixture: hosted toolcache Python
    # may be writable. Tests use its exact bytes in an owned protected file;
    # production continues hashing and checking the actual executing binary.
    interpreter=tmp_path/'qualified-python'
    shutil.copyfile(Path(sys.executable).resolve(),interpreter)
    interpreter.chmod(0o700)
    monkeypatch.setattr(sys,'executable',str(interpreter))
    policy={'version':2,'streams':{'outdoor':{'model':'Fineoffset-WH65B','sensor_id':206,
        'minimum_f':-40.,'maximum_f':140.,'validity_seconds':300,
        'sensor_epoch':'11111111-1111-4111-8111-111111111111'}}}
    policy_path=tmp_path/'policy.json';policy_path.write_text(json.dumps(policy));policy_path.chmod(0o600)
    clock=lambda:datetime(2026,10,9,13,tzinfo=timezone.utc)
    monkeypatch.setattr(m,'_clock',clock)
    return m,root,runtime,policy_path


def prepare(setup):
    m,root,_,policy=setup
    observer=m.TemperatureOriginObserver(root,policy)
    snapshot,model,adjustment,payloads=inputs()
    token=observer.prepare(snapshot=snapshot,payloads=payloads,hourly_model=model,temperature_adjustment=adjustment)
    return observer,token,snapshot,model,payloads


def complete(observer,token):
    return observer.complete(token,publication_started_at=datetime(2026,10,9,13,0,1,tzinfo=timezone.utc),
        publication_completed_at=datetime(2026,10,9,13,0,2,tzinfo=timezone.utc))


def test_original_raw_and_corrected_values_survive_later_model_updates(setup):
    m,root,_,_=setup;observer,token,snapshot,model,payloads=prepare(setup)
    model['12']['b']=19.;snapshot['hourly']['temperature_2m'][0]=100.;payloads[2]['days'][1]['hours'][0]['tempF']=101.
    path=complete(observer,token);record,weather=m.read_origin(root,path)
    assert record['hourly_model']['12']['b']==4.
    assert weather['snapshot']['hourly']['temperature_2m']==[68.]
    detail=json.loads(record['detail_state'])
    assert detail['days'][1]['hours'][0]['tempF']==64.
    assert record['delivery_verified'] is False
    assert record['publication_item']=='Forecast_10Day_JSON'


@pytest.mark.parametrize('damage',['runtime','policy','future','reversed','root-permissions'])
def test_drift_and_false_publication_clocks_do_not_produce_origins(setup,damage):
    m,root,runtime,policy=setup;observer,token,*_=prepare(setup)
    start=datetime(2026,10,9,13,0,1,tzinfo=timezone.utc);end=start+timedelta(seconds=1)
    if damage=='runtime':(runtime/'forecast_intel.py').write_text('changed')
    elif damage=='policy':policy.write_text('{}')
    elif damage=='future':start-=timedelta(days=1)
    elif damage=='reversed':end=start-timedelta(seconds=1)
    else:root.chmod(0o755)
    with pytest.raises((ValueError,OSError)):
        observer.complete(token,publication_started_at=start,publication_completed_at=end)
    assert not list(root.glob('*.temperature-origin-v1.json'))


def test_corrupt_origin_cannot_be_overwritten_or_read(setup):
    m,root,_,_=setup;observer,token,*_=prepare(setup);path=complete(observer,token)
    path.write_text('corrupt')
    with pytest.raises(ValueError):complete(observer,token)
    with pytest.raises(ValueError):m.read_origin(root,path)
    assert path.read_text()=='corrupt'


def test_raw_weather_archive_tampering_is_not_hidden_by_intact_origin(setup):
    m,root,_,_=setup;observer,token,*_=prepare(setup);path=complete(observer,token)
    record,_=m.read_origin(root,path)
    (root/'weather-inputs'/record['weather_reference']['path']).write_bytes(b'bad')
    with pytest.raises((ValueError,OSError,EOFError)):m.read_origin(root,path)


def test_successful_real_publisher_retains_exact_detail_bytes(setup):
    m,root,_,policy=setup;snapshot,model,adjustment,_=inputs();sent=[]
    observer=m.TemperatureOriginObserver(root,policy)
    fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=lambda item,state:sent.append((item,state)),
        temperature_adjustment=adjustment,hourly_model=model,origin_observer=observer)
    paths=list(root.glob('*.temperature-origin-v1.json'));assert len(paths)==1
    record,_=m.read_origin(root,paths[0])
    assert record['detail_state']==dict(sent)['Forecast_10Day_JSON']
    assert [x[0] for x in sent]==['Forecast_Hourly_JSON','Forecast_Daily_JSON','Forecast_10Day_JSON']


def test_failed_detail_put_does_not_archive_an_issued_forecast(setup):
    m,root,_,policy=setup;snapshot,model,adjustment,_=inputs()
    def put(item,state):
        if item=='Forecast_10Day_JSON':raise OSError('synthetic HTTP failure')
    with pytest.raises(OSError):
        fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
            put_state=put,temperature_adjustment=adjustment,hourly_model=model,
            origin_observer=m.TemperatureOriginObserver(root,policy))
    assert not list(root.glob('*.temperature-origin-v1.json'))


def test_capture_error_preserves_publication_and_learning_state(setup):
    m,root,_,policy=setup;snapshot,model,adjustment,_=inputs();prior=deepcopy(model);sent=[]
    policy.write_text('{}')
    result=fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=lambda item,state:sent.append((item,state)),
        temperature_adjustment=adjustment,hourly_model=model,origin_observer=m.TemperatureOriginObserver(root,policy))
    assert len(sent)==3 and result[2]['days'][1]['hours'][0]['tempF']==64.
    assert model==prior
    assert not list(root.glob('*.temperature-origin-v1.json'))


def test_group_writable_runtime_refuses_capture_without_changing_published_output(setup):
    m,root,runtime,policy=setup;snapshot,model,adjustment,_=inputs();sent=[]
    (runtime/'forecast_intel.py').chmod(0o664)
    fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=lambda item,state:sent.append((item,state)),temperature_adjustment=adjustment,
        hourly_model=model,origin_observer=m.TemperatureOriginObserver(root,policy))
    assert len(sent)==3
    assert not list(root.glob('*.temperature-origin-v1.json'))


def test_post_put_runtime_drift_keeps_exact_output_but_refuses_origin(setup):
    m,root,runtime,policy=setup;snapshot,model,adjustment,_=inputs();sent=[]
    def put(item,state):
        sent.append((item,state))
        if item=='Forecast_10Day_JSON':(runtime/'forecast_intel.py').write_text('changed after PUT')
    fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=put,temperature_adjustment=adjustment,hourly_model=model,
        origin_observer=m.TemperatureOriginObserver(root,policy))
    assert json.loads(dict(sent)['Forecast_10Day_JSON'])['days'][1]['hours'][0]['tempF']==64.
    assert not list(root.glob('*.temperature-origin-v1.json'))


def test_default_disabled_has_no_archive_io_or_observer_calls(monkeypatch):
    m=module();monkeypatch.delenv('FORECAST_TEMPERATURE_ORIGIN_DIR',raising=False)
    monkeypatch.delenv('FORECAST_TEMPERATURE_ORIGIN_POLICY',raising=False)
    def forbidden():raise AssertionError('disabled observer attempted I/O')
    monkeypatch.setattr(m,'_runtime_binding',forbidden)
    snapshot,model,adjustment,_=inputs();sent=[]
    fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=lambda item,state:sent.append((item,state)),temperature_adjustment=adjustment,hourly_model=model)
    assert len(sent)==3


def test_retained_code_tamper_is_rejected_on_replay(setup):
    m,root,_,_=setup;observer,token,*_=prepare(setup);path=complete(observer,token)
    record,_=m.read_origin(root,path)
    code=root/'runtime-sources'/record['runtime']['code_revision']/'forecast_intel.py'
    code.write_text('tampered archived code')
    with pytest.raises(ValueError):m.read_origin(root,path)


def test_main_safe_put_false_does_not_complete_a_failed_detail_origin(setup,monkeypatch):
    m,root,_,policy=setup;snapshot,model,adjustment,_=inputs();failures=[]
    def failed_http(item,state):
        if item=='Forecast_10Day_JSON':raise OSError('synthetic detail transport failure')
    monkeypatch.setattr(fi,'oh_put_state',failed_http)
    result=fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=lambda item,state:fi.safe_put(item,state,failures),
        temperature_adjustment=adjustment,hourly_model=model,
        origin_observer=m.TemperatureOriginObserver(root,policy))
    assert failures==['Forecast_10Day_JSON']
    assert result[2]['days'][1]['hours'][0]['tempF']==64.
    assert not list(root.glob('*.temperature-origin-v1.json'))


def test_writable_interpreter_refuses_capture_without_weakening_publication(setup):
    m,root,_,policy=setup;snapshot,model,adjustment,_=inputs();sent=[]
    Path(sys.executable).chmod(0o775)
    fi.build_json_items(snapshot=snapshot,pv_per_day=[],now=datetime(2026,10,9,6,40,tzinfo=fi.MOUNTAIN),
        put_state=lambda item,state:sent.append((item,state)),temperature_adjustment=adjustment,
        hourly_model=model,origin_observer=m.TemperatureOriginObserver(root,policy))
    assert len(sent)==3
    assert not list(root.glob('*.temperature-origin-v1.json'))
