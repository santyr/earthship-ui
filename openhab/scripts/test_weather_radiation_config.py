import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from flask import Flask
import pytest

from weather_radiation_config import configure_radiation_receiver, load_radiation_policy


@pytest.fixture
def policy_file(tmp_path):
    path = tmp_path / 'radiation.json'
    path.write_text('{"version":1,"sensor_id":206,"validity_seconds":120}')
    path.chmod(0o600)
    return path


def test_explicit_policy_load_and_enable_opt_in(policy_file):
    assert load_radiation_policy(str(policy_file)).sensor_id == 206
    app = Flask(__name__)
    collector = configure_radiation_receiver(app, {
        'WEATHER_RADIATION_EVIDENCE_ENABLE': '1',
        'WEATHER_RADIATION_EVIDENCE_POLICY': str(policy_file)})
    assert collector is not None
    assert app.test_client().get('/radiation_evidence').get_json()['record'] is None


@pytest.mark.parametrize('flag', [None, '', '0', 'true', True, 1])
def test_disabled_configuration_does_not_open_a_policy(monkeypatch, flag):
    import weather_radiation_config as config
    def forbidden(_path):
        pytest.fail('disabled collector read policy')
    monkeypatch.setattr(config, 'load_radiation_policy', forbidden)
    app = Flask(__name__)
    assert configure_radiation_receiver(app, {'WEATHER_RADIATION_EVIDENCE_ENABLE': flag}) is None
    assert not app.before_request_funcs
    assert app.test_client().get('/radiation_evidence').status_code == 404


@pytest.mark.parametrize('contents', ['{}', '[]', 'x' * 4097,
    '{"version":1,"sensor_id":206,"sensor_id":207,"validity_seconds":120}',
    '{"version":1,"sensor_id":206,"validity_seconds":NaN}',
    '{"version":true,"sensor_id":206,"validity_seconds":120}',
    '{"version":1,"sensor_id":206,"validity_seconds":120,"extra":1}'])
def test_malformed_or_oversized_policy_is_refused(policy_file, contents):
    policy_file.write_text(contents)
    with pytest.raises(ValueError):
        load_radiation_policy(str(policy_file))


@pytest.mark.parametrize('mutation', ['symlink', 'directory', 'fifo', 'writable'])
def test_unsafe_policy_file_is_refused(policy_file, tmp_path, mutation):
    path = policy_file
    if mutation == 'symlink':
        path = tmp_path / 'link'
        path.symlink_to(policy_file)
    elif mutation == 'directory':
        path = tmp_path
    elif mutation == 'fifo':
        path = tmp_path / 'fifo'
        os.mkfifo(path)
    else:
        policy_file.chmod(0o666)
    with pytest.raises((ValueError, OSError)):
        load_radiation_policy(str(path))


def test_bad_config_leaves_legacy_working_without_private_log_details(caplog):
    app = Flask(__name__)
    app.add_url_rule('/weather', 'legacy', lambda: 'legacy')
    assert configure_radiation_receiver(app, {
        'WEATHER_RADIATION_EVIDENCE_ENABLE': '1',
        'WEATHER_RADIATION_EVIDENCE_POLICY': '/missing/PRIVATE'}) is None
    assert app.test_client().get('/weather').text == 'legacy'
    assert 'PRIVATE' not in caplog.text


@pytest.mark.parametrize('enabled', [False, True])
def test_wsgi_hook_is_default_off_and_only_explicitly_enabled(monkeypatch, policy_file, enabled):
    app = Flask('radiation-wsgi')
    app.add_url_rule('/weather', 'legacy', lambda: 'legacy')
    monkeypatch.setitem(sys.modules, 'weather', SimpleNamespace(app=app))
    monkeypatch.setenv('WEATHER_TEMP_EVIDENCE_ENABLE', '0')
    monkeypatch.setenv('WEATHER_RAIN_EVIDENCE_ENABLE', '0')
    monkeypatch.delenv('WEATHER_RADIATION_EVIDENCE_ENABLE', raising=False)
    if enabled:
        monkeypatch.setenv('WEATHER_RADIATION_EVIDENCE_ENABLE', '1')
    monkeypatch.setenv('WEATHER_RADIATION_EVIDENCE_POLICY', str(policy_file))
    spec = importlib.util.spec_from_file_location('isolated_radiation_wsgi',
        Path(__file__).with_name('weather_evidence_wsgi.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app is app
    assert app.test_client().get('/weather').text == 'legacy'
    assert app.test_client().get('/radiation_evidence').status_code == (200 if enabled else 404)
