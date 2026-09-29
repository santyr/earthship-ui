import json

import pytest
from flask import Flask

from weather_rain_config import configure_rain_receiver, load_rain_policy


def test_policy_is_explicit_and_configuration_is_default_off(tmp_path):
    path = tmp_path / 'rain.json'
    path.write_text(json.dumps({'version': 1, 'sensor_id': 206,
                                'validity_seconds': 120,
                                'maximum_counter_in': 100000.0}))
    path.chmod(0o600)
    assert load_rain_policy(str(path)).sensor_id == 206
    app = Flask(__name__)
    assert configure_rain_receiver(app, {}) is None
    assert app.test_client().get('/rain_evidence').status_code == 404
    configured_app = Flask('rain-configured')
    collector = configure_rain_receiver(configured_app, {
        'WEATHER_RAIN_EVIDENCE_ENABLE': '1',
        'WEATHER_RAIN_EVIDENCE_POLICY': str(path)})
    assert collector.policy.sensor_id == 206


@pytest.mark.parametrize('contents', [
    '{"version":1,"sensor_id":206,"sensor_id":207,"validity_seconds":120,"maximum_counter_in":100000}',
    '{"version":1,"sensor_id":206,"validity_seconds":120,"maximum_counter_in":NaN}',
    '{"version":1,"sensor_id":206,"validity_seconds":120}',
])
def test_invalid_policy_fails_closed(tmp_path, contents):
    path = tmp_path / 'rain.json'
    path.write_text(contents)
    with pytest.raises(ValueError):
        load_rain_policy(str(path))


def test_bad_config_preserves_legacy_receiver(tmp_path):
    app = Flask(__name__)
    collector = configure_rain_receiver(app, {
        'WEATHER_RAIN_EVIDENCE_ENABLE': '1',
        'WEATHER_RAIN_EVIDENCE_POLICY': str(tmp_path / 'missing')})
    assert collector is None
    assert app.test_client().get('/rain_evidence').status_code == 404
