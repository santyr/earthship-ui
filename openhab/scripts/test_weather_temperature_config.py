import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from flask import Flask
import pytest
from weather_temperature_config import load_temperature_policies, configure_temperature_receiver

DOCUMENT = {'version': 1, 'streams': {'indoor': {'model': 'Fineoffset-WH32B', 'sensor_id': 235,
             'minimum_f': -80, 'maximum_f': 160, 'validity_seconds': 120}}}


@pytest.fixture
def policy_file(tmp_path):
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps(DOCUMENT))
    path.chmod(0o600)
    return path


def test_explicit_policy_roundtrip(policy_file):
    policies = load_temperature_policies(str(policy_file))
    assert policies['indoor'].sensor_id == 235
    assert policies['indoor'].validity_seconds == 120


@pytest.mark.parametrize('text', [
    '{}', '{"version":1,"version":1,"streams":{}}',
    '{"version":1,"streams":{},"extra":1}', '{"version":true,"streams":{}}',
    '{"version":1,"streams":{"indoor":{"model":"Fineoffset-WH32B","sensor_id":235,"minimum_f":NaN,"maximum_f":160,"validity_seconds":120}}}',
    '[]', 'invalid', 'x' * 8193,
])
def test_malformed_duplicate_or_oversized_configuration_is_refused(policy_file, text):
    policy_file.write_text(text)
    with pytest.raises(ValueError): load_temperature_policies(str(policy_file))


@pytest.mark.parametrize('mutation', ['symlink', 'directory', 'fifo', 'writable'])
def test_unsafe_file_types_and_permissions_are_refused(policy_file, tmp_path, mutation):
    path = policy_file
    if mutation == 'symlink':
        path = tmp_path / 'link'; path.symlink_to(policy_file)
    elif mutation == 'directory': path = tmp_path
    elif mutation == 'fifo':
        path = tmp_path / 'fifo'; os.mkfifo(path)
    else: policy_file.chmod(0o666)
    with pytest.raises((ValueError, OSError)): load_temperature_policies(str(path))


@pytest.mark.parametrize('flag', [None, '', '0', 'true', 'yes', True, 1])
def test_disabled_does_not_open_any_policy_or_modify_app(monkeypatch, flag):
    import weather_temperature_config as config
    def forbidden(_path): pytest.fail('disabled mode read a policy')
    monkeypatch.setattr(config, 'load_temperature_policies', forbidden)
    app = Flask(__name__)
    assert configure_temperature_receiver(app, {'WEATHER_TEMP_EVIDENCE_ENABLE': flag}) is None
    assert app.test_client().get('/temperature_evidence').status_code == 404
    assert not app.before_request_funcs


def test_invalid_enabled_policy_preserves_legacy_route_and_sanitizes_logs(caplog):
    app = Flask(__name__)
    app.add_url_rule('/weather', 'legacy', lambda: 'legacy')
    assert configure_temperature_receiver(app, {'WEATHER_TEMP_EVIDENCE_ENABLE': '1',
           'WEATHER_TEMP_EVIDENCE_POLICY': '/missing/SECRET'}) is None
    assert app.test_client().get('/weather').text == 'legacy'
    assert app.test_client().get('/temperature_evidence').status_code == 404
    assert 'SECRET' not in caplog.text


@pytest.mark.parametrize('enabled', [False, True])
def test_real_wsgi_entrypoint_preserves_app_and_only_opts_in_explicitly(monkeypatch, policy_file, enabled):
    app = Flask(__name__)
    app.add_url_rule('/weather', 'legacy', lambda: 'legacy')
    monkeypatch.setitem(sys.modules, 'weather', SimpleNamespace(app=app))
    monkeypatch.setenv('WEATHER_TEMP_EVIDENCE_ENABLE', '1' if enabled else '0')
    monkeypatch.setenv('WEATHER_TEMP_EVIDENCE_POLICY', str(policy_file))
    source = Path(__file__).with_name('weather_evidence_wsgi.py')
    spec = importlib.util.spec_from_file_location('isolated_weather_wsgi', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.app is app
    client = app.test_client()
    assert client.get('/weather').text == 'legacy'
    assert client.get('/temperature_evidence').status_code == (200 if enabled else 404)
    if enabled: assert module.temperature_evidence_collector.snapshot()['records']['indoor'] is None
