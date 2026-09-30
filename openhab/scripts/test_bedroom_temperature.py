"""Fourth stream remains independent and compatible with the existing three."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest

from weather_temperature_config import load_temperature_policies
from weather_temperature_receiver import TemperatureCollector
from weather_temperature_reader import select_temperature_at


def test_four_stream_source_identity_history_and_expiry(tmp_path):
    source = Path(__file__).parents[1] / 'weather-temperature-policy.json'
    path = tmp_path / 'policy.json'
    path.write_bytes(source.read_bytes()); path.chmod(0o600)
    policies = load_temperature_policies(str(path))
    at = datetime(2026, 9, 30, 23, tzinfo=timezone.utc)
    clock = {'tick': 0}
    collector = TemperatureCollector(policies, clock=lambda: at,
                                     monotonic=lambda: clock['tick'])
    for name, value in [('outdoor', 52), ('indoor', 69), ('north_wall', 70), ('bedroom', 71.4)]:
        policy = policies[name]
        field = 'tempf' if name == 'outdoor' else 'tempinf'
        collector.observe({'model': policy.model, 'id': str(policy.sensor_id), field: str(value)})
    snapshot = collector.snapshot()
    assert len(snapshot['records']) == 4
    for name, policy in policies.items():
        selected = select_temperature_at([(at, json.dumps(snapshot))], target=at,
            assessed_at=at + timedelta(seconds=1), history_start=at - timedelta(seconds=120),
            stream=name, policy=policy)
        assert selected['temperatureF'] == snapshot['records'][name]['temperatureF']
    collector.observe({'model': 'AmbientWeather-WH31E', 'id': '224', 'tempinf': '95'})
    assert collector.snapshot() == snapshot
    clock['tick'] = 120
    assert all(r['status'] == 'invalid' and r['temperatureF'] is None
               for r in collector.snapshot()['records'].values())


def test_missing_bedroom_does_not_claim_hallway(tmp_path):
    source = Path(__file__).parents[1] / 'weather-temperature-policy.json'
    path = tmp_path / 'policy.json'; path.write_bytes(source.read_bytes()); path.chmod(0o600)
    collector = TemperatureCollector(load_temperature_policies(str(path)))
    collector.observe({'model': 'Fineoffset-WH32B', 'id': '235', 'tempinf': '69'})
    assert collector.snapshot()['records']['bedroom'] is None
    assert collector.snapshot()['records']['indoor']['temperatureF'] == 69


def test_registry_matches_physical_policy_without_enabling_zone_training():
    root = Path(__file__).parents[1]
    registry = json.loads((root / 'thermal-zone-sensors.json').read_text())
    policy = json.loads((root / 'weather-temperature-policy.json').read_text())['streams']['bedroom']
    zone = registry['zones']['office_hallway']
    assert (zone['model'], zone['sensor_id']) == (policy['model'], policy['sensor_id'])
    assert zone['location_verified'] is True
    assert zone['learning_enabled'] is False
    assert zone['observations_valid_from'] == '2026-09-30T23:15:00Z'
    assert zone['stream'] == 'bedroom'  # original receipts and JDBC history retained
    assert registry['zones']['bedroom']['item'] is None
    assert registry['zones']['bathroom']['item'] is None


def test_fifth_stream_remains_outside_the_explicit_bound(tmp_path):
    source = Path(__file__).parents[1] / 'weather-temperature-policy.json'
    document = json.loads(source.read_text())
    document['streams']['extra'] = {**document['streams']['bedroom'], 'sensor_id': 224}
    path = tmp_path / 'policy.json'; path.write_text(json.dumps(document)); path.chmod(0o600)
    with pytest.raises(ValueError): load_temperature_policies(str(path))
