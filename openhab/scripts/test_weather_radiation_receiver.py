"""Exercise real Flask capture and raw-packet identity/expiry, without RF/HTTP."""
from datetime import timedelta
import json

import pytest

from test_weather_radiation_evidence import AT, POLICY, packet
from test_weather_receiver_characterization import load_isolated_receiver
from test_weather_temperature_receiver_integration import FrozenDateTime
from weather_radiation_receiver import RadiationCollector, install_radiation_evidence


def collector_fixture():
    now, ticks, pid = [AT], [100.0], [123]
    collector = RadiationCollector(POLICY, clock=lambda: now[0],
                                   monotonic=lambda: ticks[0], process_id=lambda: pid[0])
    return collector, now, ticks, pid


def test_duplicate_packets_and_getters_never_renew_expiry():
    collector, now, ticks, _ = collector_fixture()
    collector.observe(packet(light_lux='0', solarradiation='0'))
    first = collector.snapshot()
    now[0] += timedelta(seconds=60)
    ticks[0] += 60
    collector.observe(packet(light_lux='0', solarradiation='0'))
    assert collector.snapshot()['record'] == first['record']
    assert collector.snapshot()['sequence'] == first['sequence'] == 1
    now[0] += timedelta(seconds=60)
    ticks[0] += 60
    expired = collector.snapshot()['record']
    assert expired['reason'] == 'expired'
    assert expired['irradianceWm2'] is None
    # A cached duplicate cannot recover an expired record.
    collector.observe(packet(light_lux='0', solarradiation='0'))
    assert collector.snapshot()['record']['reason'] == 'expired'


def test_new_same_value_packet_advances_original_receipt_not_cached_value():
    collector, now, ticks, _ = collector_fixture()
    collector.observe(packet())
    now[0] += timedelta(seconds=60)
    ticks[0] += 60
    collector.observe(packet(radio_decode_utc='2026-10-01 12:01:00'))
    state = collector.snapshot()
    assert state['sequence'] == 2
    assert state['record']['validUntil'] == '2026-10-01T12:03:00+00:00'
    assert state['record']['irradianceWm2'] == 100


@pytest.mark.parametrize('changes,reason', [
    ({'radio_decode_utc': '2026-10-01 11:59:59'}, 'source_time_regressed'),
    ({'light_lux': '25340', 'solarradiation': '200'}, 'source_time_conflict'),
    ({'light_lux': None}, 'lux_invalid'),
])
def test_source_fault_barrier_cannot_recover_from_old_duplicate(changes, reason):
    collector, _, _, _ = collector_fixture()
    collector.observe(packet())
    collector.observe(packet(**changes))
    assert collector.snapshot()['record']['reason'] == reason
    collector.observe(packet())
    assert collector.snapshot()['record']['status'] == 'invalid'


def test_foreign_packet_does_not_poison_original_receipt():
    collector, _, _, _ = collector_fixture()
    collector.observe(packet())
    original = collector.snapshot()
    collector.observe(packet(id='999', light_lux='nan'))
    assert collector.snapshot() == original


@pytest.mark.parametrize('change', ['wall_clock', 'monotonic', 'pid'])
def test_clock_or_process_reset_withholds_old_values_and_changes_epoch(change):
    collector, now, ticks, pid = collector_fixture()
    collector.observe(packet())
    original = collector.snapshot()
    if change == 'wall_clock':
        now[0] -= timedelta(seconds=1)
    elif change == 'monotonic':
        ticks[0] -= 1
    else:
        pid[0] += 1
    state = collector.snapshot()
    assert state['streamEpoch'] != original['streamEpoch']
    assert state['record'] is None


def test_monotonic_expiry_is_not_extended_by_a_slow_wall_clock():
    collector, _, ticks, _ = collector_fixture()
    collector.observe(packet())
    ticks[0] += 120
    assert collector.snapshot()['record']['reason'] == 'expired'


def test_transport_delay_reduces_monotonic_lifetime_too():
    collector, _, ticks, _ = collector_fixture()
    collector.observe(packet(radio_decode_utc='2026-10-01 11:58:10'))
    assert collector.snapshot()['record']['status'] == 'valid'
    ticks[0] += 10
    assert collector.snapshot()['record']['reason'] == 'expired'


def test_real_receiver_readings_responses_and_fallback_are_unchanged(monkeypatch, tmp_path):
    modules = []
    for name in ('base', 'radiation'):
        directory = tmp_path / name
        directory.mkdir()
        modules.append(load_isolated_receiver(monkeypatch, directory))
    base, extended = modules
    for module in modules:
        monkeypatch.setattr(module, 'datetime', FrozenDateTime)
    collector = install_radiation_evidence(extended.app, enabled=True, policy=POLICY,
                                           clock=lambda: AT, monotonic=lambda: 100)
    clients = [module.app.test_client() for module in modules]
    for value in (packet(), packet(light_lux=None),
                  {'model': 'Fineoffset-WH32B', 'id': '235', 'tempinf': '75'}):
        responses = [client.get('/weather', query_string=value) for client in clients]
        assert (responses[0].status_code, responses[0].data) == (
            responses[1].status_code, responses[1].data)
        assert clients[0].get('/get_received_data').get_json() == (
            clients[1].get('/get_received_data').get_json())
        assert json.dumps(base.previous_data, sort_keys=True, default=str) == (
            json.dumps(extended.previous_data, sort_keys=True, default=str))
    assert collector.snapshot()['record']['status'] == 'invalid'
    assert clients[0].get('/radiation_evidence').status_code == 404
    response = clients[1].get('/radiation_evidence')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert clients[1].get('/radiation_evidence', environ_base={
        'REMOTE_ADDR': '192.0.2.1'}).status_code == 404
    before = collector.snapshot()
    clients[1].get('/weather', query_string=packet(), environ_base={
        'REMOTE_ADDR': '192.0.2.1'})
    assert collector.snapshot() == before


def test_observer_failure_is_sanitized_and_does_not_break_legacy(monkeypatch, tmp_path, caplog):
    receiver = load_isolated_receiver(monkeypatch, tmp_path)
    collector = install_radiation_evidence(receiver.app, enabled=True, policy=POLICY)
    def fail(_packet):
        raise RuntimeError('PRIVATE_PAYLOAD')
    monkeypatch.setattr(collector, 'observe', fail)
    assert receiver.app.test_client().get('/weather', query_string=packet()).status_code == 200
    assert collector.snapshot()['record'] is None
    assert 'PRIVATE_PAYLOAD' not in caplog.text


def test_install_is_default_off_and_duplicate_install_is_refused(monkeypatch, tmp_path):
    receiver = load_isolated_receiver(monkeypatch, tmp_path)
    assert install_radiation_evidence(receiver.app, policy=POLICY) is None
    assert receiver.app.test_client().get('/radiation_evidence').status_code == 404
    configured_dir = tmp_path / 'configured'
    configured_dir.mkdir()
    configured = load_isolated_receiver(monkeypatch, configured_dir)
    install_radiation_evidence(configured.app, enabled=True, policy=POLICY)
    with pytest.raises(ValueError):
        install_radiation_evidence(configured.app, enabled=True, policy=POLICY)
