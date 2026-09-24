"""Pure guards for the stopped-service forecast Group transfer."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

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
