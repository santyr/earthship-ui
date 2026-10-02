from copy import deepcopy
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('moon_provider_probe', Path(__file__).with_name('qualify-astro-moon-thing-provider.py'))
m = module_from_spec(spec)
spec.loader.exec_module(m)


def container():
    return {'Config': {'Labels': {m.LABEL: 'marker'}, 'User': '9001:9001'},
            'HostConfig': {'NetworkMode': 'none', 'Privileged': False,
                           'ReadonlyRootfs': True, 'Binds': None, 'Devices': [],
                           'PortBindings': {}, 'Memory': 1536 * 1024**2,
                           'MemorySwap': 1536 * 1024**2, 'NanoCpus': 1_000_000_000},
            'AppArmorProfile': 'docker-default'}


def test_contained_fixture_accepted():
    m.validate_container(container(), 'marker')


@pytest.mark.parametrize('key,value', [
    ('NetworkMode', 'host'), ('Privileged', True), ('ReadonlyRootfs', False),
    ('Binds', ['/etc:/host']), ('Devices', ['hardware']),
    ('PortBindings', {'8080': []}), ('Memory', 0), ('MemorySwap', -1), ('NanoCpus', 0),
])
def test_containment_drift_refused(key, value):
    row = container(); row['HostConfig'][key] = value
    with pytest.raises(RuntimeError, match='containment'): m.validate_container(row, 'marker')


@pytest.mark.parametrize('change', ['label', 'user', 'apparmor'])
def test_owner_or_privilege_drift_refused(change):
    row = container()
    if change == 'label': row['Config']['Labels'][m.LABEL] = 'other'
    elif change == 'user': row['Config']['User'] = 'root'
    else: row['AppArmorProfile'] = 'unconfined'
    with pytest.raises(RuntimeError, match='containment'): m.validate_container(row, 'marker')


def test_item_projection_preserves_provider_metadata_and_units_not_observations():
    item = {'name': 'Moon_Test', 'type': 'Number:Angle', 'metadata': {'semantics': {}},
            'unitSymbol': '°', 'stateDescription': {'readOnly': True}, 'editable': True,
            'state': '30', 'lastStateUpdate': 'later'}
    after = {**item, 'state': '31', 'lastStateUpdate': 'later-again'}
    assert m.item_definition(item) == m.item_definition(after)
    for key in ('editable', 'metadata', 'unitSymbol', 'stateDescription'):
        after = deepcopy(item); after[key] = None
        assert m.item_definition(item) != m.item_definition(after)


def test_managed_creation_does_not_publish_a_state_or_derived_metadata():
    item = {'name': 'Moon_Test', 'type': 'String', 'label': 'Test',
            'state': 'FULL', 'editable': True, 'stateDescription': {'readOnly': True}}
    assert m.managed_item(item) == {'name': 'Moon_Test', 'type': 'String', 'label': 'Test'}


def test_managed_thing_recovery_retains_full_original_channel_definitions():
    row = {'UID': m.UID, 'thingTypeUID': 'astro:moon', 'label': 'Moon',
           'configuration': {'interval': 300}, 'bridgeUID': None, 'location': None,
           'properties': {}, 'channels': [{'uid': m.UID + ':phase#name',
              'defaultTags': [], 'description': 'retained descriptor',
              'configuration': {'offset': 0}}], 'editable': True,
           'statusInfo': {'status': 'ONLINE'}}
    restored = m.managed_thing(row)
    assert restored['channels'] == row['channels']
    assert restored['channels'] is not row['channels']
    assert restored['configuration'] == row['configuration']
    assert 'editable' not in restored and 'statusInfo' not in restored


def test_recovery_removes_only_readonly_link_enrichment():
    channel = {'uid': m.UID + ':phase#name', 'linkedItems': ['Moon_MoonPhaseName'],
               'defaultTags': [], 'configuration': {'offset': 0}, 'properties': {}}
    row = {'UID': m.UID, 'channels': [channel]}
    result = m.managed_thing(row)
    assert result['channels'] == [{key: value for key, value in channel.items()
                                  if key != 'linkedItems'}]
    assert row['channels'][0]['linkedItems'] == ['Moon_MoonPhaseName']


def test_isolated_recovery_creates_then_replaces_factory_descriptors():
    calls = []
    original = {'UID': m.UID, 'configuration': {'interval': 300},
                'channels': [{'uid': m.UID + ':phase#name', 'defaultTags': []}]}
    def rest(method, path, body):
        calls.append((method, path, body))
        return (201 if method == 'POST' else 200), None
    m.restore_managed(rest, original)
    assert calls == [('POST', '/things', {'UID': m.UID, 'configuration': {'interval': 300}}),
                     ('PUT', '/things/' + m.UID, original)]


@pytest.mark.parametrize('failure', ['create', 'replace'])
def test_failed_isolated_restore_refuses(failure):
    calls = []
    def rest(method, path, body):
        calls.append(method)
        return (400 if (method == 'POST') == (failure == 'create') else 201), None
    with pytest.raises(RuntimeError, match='refused'):
        m.restore_managed(rest, {'UID': m.UID, 'channels': []})
    assert calls == (['POST'] if failure == 'create' else ['POST', 'PUT'])


NATIVE = ("2026-10-02 16:30:00.123 [INFO] Item 'Moon_MoonIllumination' changed from 0.5 to 0.4 "
          '(source: org.openhab.core.thing$astro:moon:local:phase#illumination)')
AFTER = datetime(2026, 10, 2, 22, 29, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 2, 22, 31, tzinfo=timezone.utc)


def test_only_new_source_attributed_natural_event_accepted():
    assert m.native_update_after(NATIVE, AFTER, NOW)
    assert not m.native_update_after(NATIVE, NOW, NOW)
    assert not m.native_update_after(NATIVE, AFTER, AFTER)


@pytest.mark.parametrize('line', [
    NATIVE.replace('changed', 'updated'),
    NATIVE.replace('core.thing$astro:moon:local:phase#illumination', 'automation$test'),
    NATIVE.replace('Moon_MoonIllumination', 'Other'),
    NATIVE.replace('2026-10-02 16:30:00.123', 'invalid timestamp'), '',
])
def test_synthetic_or_unattributed_or_invalid_receipt_refused(line):
    assert not m.native_update_after(line, AFTER, NOW)


def test_present_target_refuses_before_production_access(monkeypatch, tmp_path):
    target = tmp_path / 'existing.things'; target.write_bytes(b'user source')
    monkeypatch.setattr(m, 'TARGET', target)
    monkeypatch.setattr(m.runtime.oh, 'get', lambda *_: pytest.fail('production read'))
    with pytest.raises(RuntimeError, match='already present'): m.preflight()


def test_dangling_target_symlink_refuses_before_production_access(monkeypatch, tmp_path):
    target = tmp_path / 'link.things'; target.symlink_to(tmp_path / 'absent')
    monkeypatch.setattr(m, 'TARGET', target)
    monkeypatch.setattr(m.runtime.oh, 'get', lambda *_: pytest.fail('production read'))
    with pytest.raises(RuntimeError, match='already present'): m.preflight()


def test_source_is_pinned():
    assert m.sha256(m.SOURCE.read_bytes()).hexdigest() == m.SOURCE_SHA


def test_difference_diagnostics_emit_paths_not_values():
    before = {'configuration': {'sensitive': 'not-for-output'}, 'channels': [{'label': 'one'}]}
    after = {'configuration': {'sensitive': 'different-private-value'}, 'channels': [{'label': 'two'}]}
    assert m.difference_paths(before, after) == ['channels.0.label', 'configuration.sensitive']
    assert m.difference_paths(before, before) == []


def test_channel_fragment_is_encoded_in_isolated_link_path():
    assert m.link_path({'itemName': 'Moon_Rise_Start', 'channelUID': 'astro:moon:local:rise#start'}) == (
        '/links/Moon_Rise_Start/astro%3Amoon%3Alocal%3Arise%23start')


@pytest.mark.parametrize('link', [
    {'itemName': 'SouthOutlet', 'channelUID': 'astro:moon:local:rise#start'},
    {'itemName': 'Moon_Rise_Start', 'channelUID': 'astro:sun:local:rise#start'},
    {'itemName': '../Moon_Rise_Start', 'channelUID': 'astro:moon:local:rise#start'},
])
def test_link_url_scope_refuses_unrelated_target(link):
    with pytest.raises(RuntimeError, match='scope'): m.link_path(link)
