from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask
from weather_temperature_evidence import TemperaturePolicy
from weather_temperature_receiver import TemperatureCollector, install_temperature_evidence

POLICIES = {'indoor': TemperaturePolicy('Fineoffset-WH32B', 235, -80, 160, 120)}
PACKET = {'model': 'Fineoffset-WH32B', 'id': '235', 'tempinf': '70'}


@pytest.fixture
def setup():
    clock = {'at': datetime(2026, 9, 10, 12, tzinfo=timezone.utc), 'tick': 1000, 'pid': 1}
    kwargs = {'clock': lambda: clock['at'], 'monotonic': lambda: clock['tick'], 'process_id': lambda: clock['pid']}
    app = Flask(__name__)
    @app.get('/weather')
    def weather(): return 'legacy response', 200
    collector = install_temperature_evidence(app, enabled=True, policies=POLICIES, **kwargs)
    return app, collector, clock, kwargs


def test_disabled_installs_no_route_or_hook_and_does_not_read_policy():
    app = Flask(__name__)
    before = list(app.url_map.iter_rules())
    assert install_temperature_evidence(app, policies=object()) is None
    assert install_temperature_evidence(app, enabled='1', policies=object()) is None
    assert list(app.url_map.iter_rules()) == before
    assert not app.before_request_funcs


def test_existing_endpoint_is_not_shadowed_or_modified():
    app = Flask(__name__)
    app.add_url_rule('/temperature_evidence', 'existing', lambda: 'existing response')
    with pytest.raises(ValueError): install_temperature_evidence(app, enabled=True, policies=POLICIES)
    assert not app.before_request_funcs
    assert app.test_client().get('/temperature_evidence').text == 'existing response'


def test_initial_state_unknown_and_raw_capture_does_not_change_response(setup):
    app, collector, _, _ = setup
    client = app.test_client()
    assert client.get('/temperature_evidence').get_json()['records'] == {'indoor': None}
    response = client.get('/weather', query_string=PACKET)
    assert (response.status_code, response.text) == (200, 'legacy response')
    evidence = client.get('/temperature_evidence')
    assert evidence.headers['Cache-Control'] == 'no-store'
    assert evidence.get_json()['records']['indoor']['temperatureF'] == 70
    assert collector.snapshot()['records']['indoor']['sensorId'] == 235


@pytest.mark.parametrize('elapsed', [119, 120, 121])
def test_exact_monotonic_expiry_even_if_wall_clock_stalls(setup, elapsed):
    _, collector, clock, _ = setup
    collector.observe(PACKET)
    clock['tick'] += elapsed
    record = collector.snapshot()['records']['indoor']
    assert record['status'] == ('valid' if elapsed < 120 else 'invalid')
    if elapsed >= 120:
        assert record['reason'] == 'expired'
        assert record['temperatureF'] is None


def test_poll_does_not_renew_receipt_or_revive_expiry(setup):
    _, collector, clock, _ = setup
    collector.observe(PACKET)
    old = collector.snapshot()
    clock['at'] += timedelta(seconds=60); clock['tick'] += 60
    assert collector.snapshot() == old
    clock['at'] += timedelta(seconds=60); clock['tick'] += 60
    expired = collector.snapshot()
    clock['tick'] += 1
    assert collector.snapshot() == expired
    collector.observe(PACKET)
    assert collector.snapshot()['records']['indoor']['status'] == 'valid'


@pytest.mark.parametrize('change', ['wall', 'monotonic', 'process'])
def test_clock_rollback_or_worker_fork_clears_epoch_and_requires_new_packet(setup, change):
    _, collector, clock, _ = setup
    collector.observe(PACKET); old = collector.snapshot()
    if change == 'wall': clock['at'] -= timedelta(seconds=1)
    if change == 'monotonic': clock['tick'] -= 1
    if change == 'process': clock['pid'] = 2
    fresh = collector.snapshot()
    assert fresh['streamEpoch'] != old['streamEpoch']
    assert fresh['records'] == {'indoor': None}
    collector.observe(PACKET)
    assert collector.snapshot()['records']['indoor']['streamEpoch'] == fresh['streamEpoch']


def test_restart_instance_does_not_restore_old_value(setup):
    _, collector, _, kwargs = setup
    collector.observe(PACKET)
    fresh = TemperatureCollector(POLICIES, **kwargs).snapshot()
    assert fresh['streamEpoch'] != collector.snapshot()['streamEpoch']
    assert fresh['records']['indoor'] is None


def test_capture_failure_cannot_break_legacy_handler_or_return_stale_evidence(setup, monkeypatch):
    app, collector, _, _ = setup
    collector.observe(PACKET)
    def fail(*args): raise RuntimeError('SECRET payload')
    monkeypatch.setattr(collector, 'observe', fail)
    response = app.test_client().get('/weather', query_string=PACKET)
    assert response.text == 'legacy response'
    assert collector.snapshot()['records']['indoor'] is None


def test_clock_failure_endpoint_is_unavailable_not_stale_or_secret(setup):
    app, collector, clock, _ = setup
    collector.observe(PACKET)
    clock['tick'] = float('nan')
    response = app.test_client().get('/temperature_evidence')
    assert response.status_code == 503
    assert response.get_json() == {'error': 'temperature evidence unavailable'}


def test_foreign_packet_does_not_renew_expected_source(setup):
    _, collector, clock, _ = setup
    collector.observe(PACKET); old = collector.snapshot()
    clock['at'] += timedelta(seconds=60); clock['tick'] += 60
    collector.observe({**PACKET, 'id': '193'})
    assert collector.snapshot() == old


def test_snapshot_cannot_mutate_internal_state(setup):
    _, collector, _, _ = setup
    collector.observe(PACKET)
    collector.snapshot()['records']['indoor']['temperatureF'] = 999
    assert collector.snapshot()['records']['indoor']['temperatureF'] == 70


@pytest.mark.parametrize('policies', [{}, {'a': object()}, {'a': POLICIES['indoor'], 'b': POLICIES['indoor']}, {'../bad': POLICIES['indoor']}])
def test_policy_registry_refuses_implicit_or_ambiguous_streams(policies):
    with pytest.raises(ValueError): TemperatureCollector(policies)
