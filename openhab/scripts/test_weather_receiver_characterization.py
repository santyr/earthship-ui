"""Characterize known source-proof gaps without touching live receiver state.

These assertions describe current limitations, not desired evidence semantics.
Replace them with positive freshness-contract tests when that receiver changes.
"""
import builtins
import importlib.util
import json
import math
from pathlib import Path

import pytest
import requests

SOURCE = Path('/home/sat/bin/weather.py')


def load_isolated_receiver(monkeypatch, tmp_path):
    if not SOURCE.is_file():
        pytest.skip('host receiver source unavailable')
    pytest.importorskip('flask')
    pytest.importorskip('flask_cors')
    # Seed only disposable state so import-time load does not seed from OpenHAB.
    state = tmp_path / 'previous_data.json'
    state.write_text(json.dumps({'totalrainin': 0, 'max_daily_windgust': 1,
                                 'WH65B_tempf': 70}), encoding='utf-8')
    monkeypatch.setenv('OPENHAB_API_KEY', 'test-only')
    monkeypatch.setenv('OPENHAB_TOKEN', 'test-only')
    monkeypatch.setenv('OPENHAB_WRITE', '0')
    def no_network(*args, **kwargs):
        pytest.fail('receiver test attempted network access')
    monkeypatch.setattr(requests.sessions.Session, 'request', no_network)
    original_open = builtins.open
    def safe_open(path, *args, **kwargs):
        if isinstance(path, (str, bytes, Path)) and Path(path).resolve() == SOURCE.parent / 'previous_data.json':
            pytest.fail('receiver test attempted production state access')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', safe_open)
    spec = importlib.util.spec_from_file_location('isolated_weather_characterization', SOURCE)
    module = importlib.util.module_from_spec(spec)
    # Loader reads code from SOURCE, while receiver's __file__-relative mutable
    # state resolves into tmp_path before its import-time initializer runs.
    module.__file__ = str(tmp_path / 'weather.py')
    spec.loader.exec_module(module)
    assert Path(module.previous_data_file) == state
    assert module._last_update == {}
    return module


@pytest.fixture
def receiver(monkeypatch, tmp_path):
    return load_isolated_receiver(monkeypatch, tmp_path)


def test_empty_sensor_map_reports_ok_without_any_field_observation(receiver):
    health = receiver.app.test_client().get('/health').get_json()
    assert health == {'status': 'ok', 'sensors': {}}


@pytest.mark.parametrize('temperature', [None, 'invalid'])
def test_packet_health_refreshes_even_when_temperature_is_old_fallback(receiver, temperature):
    client = receiver.app.test_client()
    params = {'model': 'Fineoffset-WH65B'}
    if temperature is not None:
        params['tempf'] = temperature
    assert client.get('/weather', query_string=params).status_code == 200
    value = client.get('/get_received_data').get_json()
    assert value['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature'] == 70
    health = client.get('/health').get_json()
    assert health['status'] == 'ok'
    assert health['sensors']['Fineoffset-WH65B']['stale'] is False
    assert health['sensors']['Fineoffset-WH65B']['age_seconds'] <= 1


def test_nonfinite_temperature_is_accepted_into_receiver_state(receiver):
    response = receiver.app.test_client().get('/weather', query_string={
        'model': 'Fineoffset-WH65B', 'tempf': 'nan'})
    assert response.status_code == 200
    assert math.isnan(receiver.previous_data['WH65B_tempf'])
    assert 'Fineoffset-WH65B' in receiver._last_update


def test_indoor_identity_is_not_pinned_or_retained_in_health(receiver):
    client = receiver.app.test_client()
    for sensor_id, temperature in [('test-a', '65'), ('test-b', '85')]:
        assert client.get('/weather', query_string={
            'model': 'Fineoffset-WH32B', 'id': sensor_id, 'tempinf': temperature}).status_code == 200
    assert receiver.previous_data['WH32B_tempinf'] == 85
    health = client.get('/health').get_json()['sensors']['Fineoffset-WH32B']
    assert 'id' not in health
