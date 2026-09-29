"""Rain evidence must never change the existing weather receiver result."""
from datetime import datetime, timedelta, timezone
import json

from test_weather_receiver_characterization import load_isolated_receiver
from test_weather_temperature_receiver_integration import FrozenDateTime
from weather_rain_evidence import RainPolicy
from weather_rain_receiver import RainCollector, install_rain_evidence


AT = datetime(2026, 9, 29, 1, tzinfo=timezone.utc)
POLICY = RainPolicy(sensor_id=206)


def test_real_receiver_behavior_is_identical_with_rain_capture(monkeypatch, tmp_path):
    modules = []
    for name in ('base', 'rain'):
        directory = tmp_path / name
        directory.mkdir()
        modules.append(load_isolated_receiver(monkeypatch, directory))
    base, rain = modules
    monkeypatch.setattr(base, 'datetime', FrozenDateTime)
    monkeypatch.setattr(rain, 'datetime', FrozenDateTime)
    collector = install_rain_evidence(rain.app, enabled=True, policy=POLICY,
                                      clock=lambda: AT, monotonic=lambda: 1000)
    clients = [module.app.test_client() for module in modules]
    packets = [
        {'model': 'Fineoffset-WH65B', 'id': '206', 'tempf': '72',
         'totalrainin': '0.1'},
        {'model': 'Fineoffset-WH65B', 'id': '206', 'tempf': '73'},
        {'model': 'Fineoffset-WH32B', 'id': '235', 'tempinf': '75'},
    ]
    for packet in packets:
        responses = [client.get('/weather', query_string=packet) for client in clients]
        assert (responses[0].status_code, responses[0].data) == (
            responses[1].status_code, responses[1].data)
        assert clients[0].get('/get_received_data').get_json() == (
            clients[1].get('/get_received_data').get_json())
        assert json.dumps(base.previous_data, sort_keys=True, default=str) == (
            json.dumps(rain.previous_data, sort_keys=True, default=str))
    assert collector.snapshot()['record']['reason'] == 'counter_missing_or_ambiguous'
    assert clients[0].get('/rain_evidence').status_code == 404
    assert clients[1].get('/rain_evidence').get_json()['record']['totalRainIn'] is None
    assert clients[1].get('/rain_evidence', environ_base={
        'REMOTE_ADDR': '192.0.2.1'}).status_code == 404


def test_expiry_and_process_restart_are_unavailable_barriers():
    now = [AT]
    ticks = [100.0]
    pid = [123]
    collector = RainCollector(POLICY, clock=lambda: now[0],
                              monotonic=lambda: ticks[0], process_id=lambda: pid[0])
    collector.observe({'model': 'Fineoffset-WH65B', 'id': '206',
                       'totalrainin': '0'})
    first = collector.snapshot()
    assert first['record']['totalRainIn'] == 0
    now[0] += timedelta(seconds=121)
    ticks[0] += 121
    expired = collector.snapshot()
    assert expired['record']['status'] == 'invalid'
    assert expired['record']['reason'] == 'expired'
    assert expired['record']['totalRainIn'] is None
    pid[0] = 124
    restarted = collector.snapshot()
    assert restarted['streamEpoch'] != first['streamEpoch']
    assert restarted['record'] is None


def test_capture_failure_does_not_break_legacy_receiver(monkeypatch, tmp_path):
    receiver = load_isolated_receiver(monkeypatch, tmp_path)
    collector = install_rain_evidence(receiver.app, enabled=True,
                                      policy=POLICY, clock=lambda: AT)

    def fail(_packet):
        raise RuntimeError('test-only payload')

    monkeypatch.setattr(collector, 'observe', fail)
    response = receiver.app.test_client().get('/weather', query_string={
        'model': 'Fineoffset-WH65B', 'id': '206', 'totalrainin': '1'})
    assert response.status_code == 200
    assert collector.snapshot()['record'] is None


def test_disabled_install_adds_no_hook_or_route(monkeypatch, tmp_path):
    receiver = load_isolated_receiver(monkeypatch, tmp_path)
    before = len(receiver.app.before_request_funcs.get(None, []))
    assert install_rain_evidence(receiver.app, enabled=False, policy=POLICY) is None
    assert len(receiver.app.before_request_funcs.get(None, [])) == before
    assert receiver.app.test_client().get('/rain_evidence').status_code == 404
