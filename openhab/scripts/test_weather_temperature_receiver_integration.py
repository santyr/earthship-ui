"""Execute the installed receiver with only disposable state and blocked network."""
from datetime import datetime, timezone
import json

import pytest
from test_weather_receiver_characterization import load_isolated_receiver
from weather_temperature_evidence import TemperaturePolicy
from weather_temperature_receiver import install_temperature_evidence

AT = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return AT.astimezone(tz) if tz is not None else AT.replace(tzinfo=None)


@pytest.mark.parametrize('mode', ['disabled', 'enabled', 'capture_failure'])
def test_actual_receiver_legacy_results_and_saved_state_are_identical(monkeypatch, tmp_path, mode):
    modules = []
    for label in ['baseline', 'extended']:
        directory = tmp_path / label
        directory.mkdir()
        module = load_isolated_receiver(monkeypatch, directory)
        monkeypatch.setattr(module, 'datetime', FrozenDateTime)
        modules.append(module)
    baseline, extended = modules
    policies = {
        'outdoor': TemperaturePolicy('Fineoffset-WH65B', 206, -80, 160, 120),
        'indoor': TemperaturePolicy('Fineoffset-WH32B', 235, -80, 160, 120),
        'north_wall': TemperaturePolicy('AmbientWeather-WH31E', 193, -80, 160, 120),
    }
    collector = install_temperature_evidence(extended.app, enabled=mode != 'disabled', policies=policies,
                                             clock=lambda: AT, monotonic=lambda: 1000)
    if mode == 'capture_failure':
        def fail(_packet): raise RuntimeError('fixture SECRET payload')
        monkeypatch.setattr(collector, 'observe', fail)
    clients = [module.app.test_client() for module in modules]
    packets = [
        {'model': 'Fineoffset-WH65B', 'id': '206', 'tempf': '72', 'humidity': '45', 'totalrainin': '0.1', 'windgustmph': '3'},
        {'model': 'Fineoffset-WH65B', 'id': '206', 'humidity': '46', 'totalrainin': '0.2', 'windgustmph': '4'},
        {'model': 'Fineoffset-WH65B', 'id': '206', 'tempf': 'invalid'},
        {'model': 'Fineoffset-WH32B', 'id': '235', 'tempinf': '75', 'humidityin': '50', 'baromrelin': '29.9'},
        {'model': 'AmbientWeather-WH31E', 'id': '193', 'tempinf': '74', 'humidityin': '40'},
        {'model': 'Fineoffset-WH32B', 'id': '999', 'tempinf': '85', 'humidityin': '50'},
    ]
    for index, packet in enumerate(packets):
        responses = [client.get('/weather', query_string=packet) for client in clients]
        assert [(r.status_code, r.data) for r in responses][0] == [(r.status_code, r.data) for r in responses][1]
        assert responses[0].status_code == 200
        for path in ['/get_received_data', '/health']:
            assert clients[0].get(path).get_json() == clients[1].get(path).get_json()
        assert json.dumps(baseline.previous_data, sort_keys=True, default=str) == json.dumps(extended.previous_data, sort_keys=True, default=str)
        assert (tmp_path / 'baseline/previous_data.json').read_bytes() == (tmp_path / 'extended/previous_data.json').read_bytes()
        if mode == 'enabled' and index in [0, 1, 2]:
            record = collector.snapshot()['records']['outdoor']
            if index == 0:
                assert record['status'] == 'valid' and record['temperatureF'] == 72
            else:
                assert record['status'] == 'invalid' and record['temperatureF'] is None
                assert extended.previous_data['WH65B_tempf'] == 72
    if mode == 'enabled':
        records = clients[1].get('/temperature_evidence').get_json()['records']
        assert records['indoor']['temperatureF'] == 75  # foreign999 does not replace evidence
        assert records['north_wall']['temperatureF'] == 74
        assert extended.previous_data['WH32B_tempinf'] == 85  # legacy behavior deliberately preserved
    elif mode == 'disabled':
        assert clients[1].get('/temperature_evidence').status_code == 404
    else:
        assert all(record is None for record in collector.snapshot()['records'].values())
