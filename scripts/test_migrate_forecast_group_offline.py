"""Pure guards for the stopped-service forecast Group transfer."""
from importlib.util import module_from_spec, spec_from_file_location
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import pytest

spec = spec_from_file_location('forecast_group_offline',
    Path(__file__).with_name('migrate-forecast-group-offline.py'))
group = module_from_spec(spec)
spec.loader.exec_module(group)


def test_daily_gate_requires_both_item_and_link_verification(tmp_path, monkeypatch):
    manifest = tmp_path / 'ownership.json'
    rows = [{'kind': kind, 'id': name if kind == 'item' else name + ' -> channel',
             'provider': 'file', 'migration': 'verified'}
            for kind in ('item', 'link') for name in group.DAILY]
    manifest.write_text(json.dumps({'resources': rows}))
    monkeypatch.setattr(group, 'MANIFEST', manifest)
    assert group.daily_gate()
    rows[-1]['migration'] = 'provisional'
    manifest.write_text(json.dumps({'resources': rows}))
    assert not group.daily_gate()


def test_registry_record_requires_exact_managed_group():
    record = {'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
              'value': {'groupNames': [], 'itemType': 'Group',
                        'tags': ['forecast'], 'label': 'Forecast Items'}}
    rows, original = group.registry_record(json.dumps({group.GROUP: record}).encode())
    assert rows[group.GROUP] == original == record
    record['value']['tags'] = []
    try:
        group.registry_record(json.dumps({group.GROUP: record}).encode())
    except RuntimeError as error:
        assert 'changed' in str(error)
    else:
        raise AssertionError('changed managed Group was accepted')


def test_member_provider_guard_rejects_one_managed_link(monkeypatch):
    items = [{'name': name, 'editable': False, 'groupNames': [group.GROUP]}
             for name in group.MEMBERS]
    links = [{'itemName': name, 'editable': False, 'configuration': {}}
             for name in group.MEMBERS]
    monkeypatch.setattr(group.transfer.oh, 'get',
                        lambda path: items if path.startswith('/items') else links)
    assert group.member_providers_match()
    links[0]['editable'] = True
    assert not group.member_providers_match()


def test_maintenance_refuses_active_or_unknown_greywater_pump(monkeypatch):
    states = {name: 'OFF' for name in group.PUMP_ITEMS}
    monkeypatch.setattr(group.transfer.oh, 'get',
                        lambda path: {'state': states[path.split('/')[-1]]})
    assert group.pumps_off()
    states[group.PUMP_ITEMS[1]] = 'ON'
    assert not group.pumps_off()
    states[group.PUMP_ITEMS[1]] = 'NULL'
    assert not group.pumps_off()


def test_protected_controls_require_healthy_rules_and_fresh_independent_telemetry(monkeypatch):
    now = datetime.fromtimestamp(2_000_000_000, timezone.utc)
    stamp = int(now.timestamp() * 1000)
    evidence = json.dumps(dict(
        version=1, streamEpoch='4bb09d80-9b62-41ed-87a5-3fcc5164ac1e',
        recordedAt=stamp, status='valid', reason='ok', observedAt=stamp-5000,
        scaleObservedAt=stamp-5000, validUntil=stamp+115000, soc=50))
    states = {
        '/items/BMS_SOC_Evidence_JSON': {'state': evidence},
        '/items/Schneider_DCData_LastUpdate': {'state': now.isoformat()},
    }
    states.update({'/rules/' + uid: {'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
                   for uid in group.SAFETY_RULES})
    monkeypatch.setattr(group.transfer.oh, 'get', lambda path: states[path])
    assert group.protected_controls_healthy(now)
    states['/rules/hex_schneider_safety']['status']['statusDetail'] = 'HANDLER_ERROR'
    with pytest.raises(RuntimeError, match='protected rule unhealthy'):
        group.protected_controls_healthy(now)
    states['/rules/hex_schneider_safety']['status']['statusDetail'] = 'NONE'
    states['/items/BMS_SOC_Evidence_JSON']['state'] = 'NULL'
    with pytest.raises(RuntimeError, match='atomic BMS SoC'):
        group.protected_controls_healthy(now)
    states['/items/BMS_SOC_Evidence_JSON']['state'] = evidence
    states['/items/Schneider_DCData_LastUpdate']['state'] = (
        now - timedelta(minutes=6)).isoformat()
    with pytest.raises(RuntimeError, match='Schneider DC telemetry'):
        group.protected_controls_healthy(now)


def test_apply_refuses_pending_daily_gate_before_service_stop(tmp_path, monkeypatch):
    source = tmp_path / 'forecast-group.items'
    source.write_text('Group gForecast "Forecast Items" ["forecast"]\n')
    registry = tmp_path / 'items.json'
    registry.write_text(json.dumps({group.GROUP: {
        'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
        'value': {'groupNames': [], 'itemType': 'Group',
                  'tags': ['forecast'], 'label': 'Forecast Items'}}}))
    monkeypatch.setattr(group, 'SOURCE', source)
    monkeypatch.setattr(group, 'SOURCE_SHA256', sha256(source.read_bytes()).hexdigest())
    monkeypatch.setattr(group, 'TARGET', tmp_path / 'target.items')
    monkeypatch.setattr(group, 'REGISTRY', registry)
    monkeypatch.setattr(group, 'active', lambda: True)
    monkeypatch.setattr(group, 'group_matches', lambda **kwargs: True)
    monkeypatch.setattr(group, 'member_providers_match', lambda: True)
    monkeypatch.setattr(group.transfer, 'healthy_thing', lambda: True)
    monkeypatch.setattr(group, 'jdbc_baseline', lambda: {})
    monkeypatch.setattr(group, 'daily_gate', lambda: False)
    monkeypatch.setattr(group, 'command', lambda *args, **kwargs:
                        pytest.fail('service command ran despite pending gate'))
    with pytest.raises(RuntimeError, match='daily natural writer gate'):
        group.main(apply=True)
    assert not (tmp_path / 'target.items').exists()


def test_apply_refuses_unreleased_live_restart_before_pump_or_service_work(
        tmp_path, monkeypatch):
    source = tmp_path / 'forecast-group.items'
    source.write_text('Group gForecast "Forecast Items" ["forecast"]\n')
    registry = tmp_path / 'items.json'
    registry.write_text(json.dumps({group.GROUP: {
        'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
        'value': {'groupNames': [], 'itemType': 'Group',
                  'tags': ['forecast'], 'label': 'Forecast Items'}}}))
    monkeypatch.setattr(group, 'SOURCE', source)
    monkeypatch.setattr(group, 'SOURCE_SHA256', sha256(source.read_bytes()).hexdigest())
    monkeypatch.setattr(group, 'TARGET', tmp_path / 'target.items')
    monkeypatch.setattr(group, 'REGISTRY', registry)
    monkeypatch.setattr(group, 'active', lambda: True)
    monkeypatch.setattr(group, 'group_matches', lambda **kwargs: True)
    monkeypatch.setattr(group, 'member_providers_match', lambda: True)
    monkeypatch.setattr(group.transfer, 'healthy_thing', lambda: True)
    monkeypatch.setattr(group, 'jdbc_baseline', lambda: {})
    monkeypatch.setattr(group, 'daily_gate', lambda: True)
    monkeypatch.setattr(group, 'RELEASE_READY', False)
    monkeypatch.setattr(group, 'pumps_off', lambda:
                        pytest.fail('pump gate reached despite unreleased restart'))
    monkeypatch.setattr(group, 'command', lambda *args, **kwargs:
                        pytest.fail('service command ran despite unreleased restart'))
    with pytest.raises(RuntimeError, match='not release-qualified'):
        group.main(apply=True)
    assert not (tmp_path / 'target.items').exists()


def test_apply_refuses_unhealthy_protected_controls_before_backup_or_stop(
        tmp_path, monkeypatch):
    source = tmp_path / 'forecast-group.items'
    source.write_text('Group gForecast "Forecast Items" ["forecast"]\n')
    registry = tmp_path / 'items.json'
    registry.write_text(json.dumps({group.GROUP: {
        'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
        'value': {'groupNames': [], 'itemType': 'Group',
                  'tags': ['forecast'], 'label': 'Forecast Items'}}}))
    monkeypatch.setattr(group, 'SOURCE', source)
    monkeypatch.setattr(group, 'SOURCE_SHA256', sha256(source.read_bytes()).hexdigest())
    monkeypatch.setattr(group, 'TARGET', tmp_path / 'target.items')
    monkeypatch.setattr(group, 'REGISTRY', registry)
    monkeypatch.setattr(group, 'RELEASE_READY', True)
    monkeypatch.setattr(group, 'active', lambda: True)
    monkeypatch.setattr(group, 'group_matches', lambda **kwargs: True)
    monkeypatch.setattr(group, 'member_providers_match', lambda: True)
    monkeypatch.setattr(group.transfer, 'healthy_thing', lambda: True)
    monkeypatch.setattr(group, 'jdbc_baseline', lambda: {})
    monkeypatch.setattr(group, 'daily_gate', lambda: True)
    monkeypatch.setattr(group, 'pumps_off', lambda: True)
    monkeypatch.setattr(group, 'protected_controls_healthy', lambda: (
        group.require(False, 'protected controls unhealthy')))
    monkeypatch.setattr(group, 'command', lambda *args, **kwargs:
                        pytest.fail('service command ran despite unhealthy controls'))
    with pytest.raises(RuntimeError, match='protected controls unhealthy'):
        group.main(apply=True)
    assert not (tmp_path / 'target.items').exists()


def test_history_verifier_preserves_past_but_allows_future_revisions(monkeypatch):
    cutover = datetime(2026, 9, 24, 3, tzinfo=timezone.utc)
    old = [(cutover - timedelta(hours=1), 1.0),
           (cutover + timedelta(hours=1), 2.0)]
    monkeypatch.setattr(group, 'jdbc_baseline', lambda: {
        'Forecast_Temp': (563, [(old[0][0], 1.0), (old[1][0], 3.0)])})
    group.verify_history({'Forecast_Temp': (563, old)}, cutover)
    monkeypatch.setattr(group, 'jdbc_baseline', lambda: {
        'Forecast_Temp': (563, [(old[1][0], 3.0)])})
    with pytest.raises(RuntimeError, match='historical forecast JDBC rows lost'):
        group.verify_history({'Forecast_Temp': (563, old)}, cutover)


def test_rollback_restores_group_without_replacing_other_registry_rows(
        tmp_path, monkeypatch):
    record = {'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
              'value': {'groupNames': [], 'itemType': 'Group',
                        'tags': ['forecast'], 'label': 'Forecast Items'}}
    registry = tmp_path / 'items.json'
    registry.write_text(json.dumps({'unrelated_live_item': {'value': 42}}))
    source = b'Group gForecast "Forecast Items" ["forecast"]\n'
    target = tmp_path / 'forecast-group.items'
    target.write_bytes(source)
    monkeypatch.setattr(group, 'REGISTRY', registry)
    monkeypatch.setattr(group, 'TARGET', target)
    monkeypatch.setattr(group, 'SOURCE_SHA256', sha256(source).hexdigest())
    state = {'active': True}

    def command(*args, **kwargs):
        if args[2] == 'systemctl':
            state['active'] = args[3] == 'start'
        elif args[2] == 'rm':
            target.unlink()
        else:
            pytest.fail('unexpected rollback command')

    def install_registry(directory, items, name):
        registry.write_text(json.dumps(items))

    monkeypatch.setattr(group, 'command', command)
    monkeypatch.setattr(group, 'active', lambda: state['active'])
    monkeypatch.setattr(group, 'install_registry', install_registry)
    monkeypatch.setattr(group, 'wait_group', lambda **kwargs: True)
    group.rollback(tmp_path, record)
    assert state['active']
    assert not target.exists()
    assert json.loads(registry.read_text()) == {
        'unrelated_live_item': {'value': 42}, group.GROUP: record}
