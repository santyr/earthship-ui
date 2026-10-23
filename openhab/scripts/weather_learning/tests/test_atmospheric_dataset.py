"""Retained pair datasets remain bound to complete immutable parent chunks."""
import gzip,importlib,json
from pathlib import Path
import pytest
from weather_learning.contracts import identity,canonical
from weather_learning.training_dataset import retain_dataset


def parent(tmp_path):
    values=[]
    for i in range(3):
        r=dict(kind='outdoor_temperature_c',origin=str(i),outcome=float(i));r['pair_sha256']=identity(r);values.append(r)
    data=retain_dataset(tmp_path,metadata=dict(kind='outdoor_temperature_c',automatic_actuation=False),pairs=values)
    return data,values


def read(root,pin,**kwargs):return importlib.import_module('weather_learning.atmospheric_dataset').read_dataset(root,pin,**kwargs)


def test_loads_complete_original_chunks_and_verifies_each_parent_pair(tmp_path):
    data,values=parent(tmp_path);actual,rows=read(tmp_path,data['dataset_sha256'])
    assert actual==data and rows==values


def test_changed_chunk_bytes_cannot_keep_the_original_parent_binding(tmp_path):
    data,values=parent(tmp_path);file=tmp_path/(data['chunks'][0]['sha256']+'.pairs.json.gz')
    raw=json.loads(gzip.decompress(file.read_bytes()));raw['pairs'][0]['outcome']=99.;file.write_bytes(gzip.compress(canonical(raw)))
    with pytest.raises(ValueError):read(tmp_path,data['dataset_sha256'])


def test_rehashed_parent_with_a_forged_pair_still_fails_original_pair_identity(tmp_path):
    data,values=parent(tmp_path);values[0]['outcome']=99.
    changed=retain_dataset(tmp_path,metadata=dict(kind='outdoor_temperature_c',automatic_actuation=False),pairs=values)
    with pytest.raises(ValueError):read(tmp_path,changed['dataset_sha256'])


def test_count_capacity_and_duplicate_originals_are_refused(tmp_path):
    data,values=parent(tmp_path)
    with pytest.raises(ValueError):read(tmp_path,data['dataset_sha256'],maximum_rows=2)
    duplicate=retain_dataset(tmp_path,metadata=dict(kind='outdoor_temperature_c',automatic_actuation=False),pairs=[*values,values[0]])
    with pytest.raises(ValueError):read(tmp_path,duplicate['dataset_sha256'])


def test_temperature_replays_the_literal_receipt_source_and_retains_capture_availability(tmp_path,monkeypatch):
    from test_weather_historical_measurements import AT,POLICY,PHASE,raw
    from datetime import timedelta
    from weather_learning.historical_measurements import capture_temperature_day
    import weather_temperature_history
    monkeypatch.setattr(weather_temperature_history,'_fetch_rows',lambda *args:[(AT,raw(AT))])
    original=capture_temperature_day(tmp_path,'2026-09-20',connection_factory=None,policies=dict(indoor=POLICY),epochs=dict(indoor=PHASE),clock=lambda:AT+timedelta(days=2))
    manifest=[dict(date='2026-09-20',grid_sha256=original['grid_sha256'],source_sha256=original['source_sha256'])]
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()};monkeypatch.setattr(weather_temperature_history,'_fetch_rows',lambda *args:pytest.fail('retained replay attempted a live read'))
    values,availability=importlib.import_module('weather_learning.atmospheric_dataset').temperature_receipts(tmp_path,manifest)
    assert values[AT.isoformat()]['indoor']['temperatureF']==70
    assert availability[(AT.isoformat(),'indoor')]==(AT+timedelta(days=2)).isoformat()
    assert before=={p.name:p.read_bytes() for p in tmp_path.iterdir()}


def test_wind_replay_retains_complete_hour_and_actual_http_capture_clock(tmp_path):
    from datetime import timedelta
    from hashlib import sha256
    from learning_fixtures import T
    item='AmbientWeatherWS2902A_WindSpeed';payload=dict(name=item,unit='mph',data=[dict(time=(T+timedelta(minutes=i)).timestamp()*1000,state='10 mph') for i in range(60)])
    source=dict(schema='earthship-historical-weather-inventory-source/v1',item=item,raw=json.dumps(payload),requested_at=(T+timedelta(days=2)).isoformat(),received_at=(T+timedelta(days=2,seconds=1)).isoformat(),automatic_actuation=False)
    source['source_sha256']=identity(source);raw=gzip.compress(canonical(source));p=tmp_path/('2026-01-01.'+item+'.json.gz');p.write_bytes(raw);p.chmod(0o600)
    manifest=dict(days=[dict(date='2026-01-01',sources={item:dict(file_sha256=sha256(raw).hexdigest(),source_sha256=source['source_sha256'])})])
    values=importlib.import_module('weather_learning.atmospheric_dataset').wind_measurements(tmp_path,manifest)
    value=values[(T+timedelta(hours=1)).isoformat()]
    assert value['mean_m_s']==pytest.approx(10/2.2369362921) and value['actual_available_at']==source['received_at']
    assert value['measurement_health_qualified'] is False
