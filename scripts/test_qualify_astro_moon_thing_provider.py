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


def semantic_fixture():
    return {'Moon': {'name': 'Moon', 'type': 'Group', 'tags': ['Equipment'],
                    'members': [{'name': 'Moon_A'}, {'name': 'Moon_B'}],
                    'metadata': {'semantics': {'value': 'Equipment', 'editable': False,
                                              'config': {'hasPoint': 'Moon_A'}}}},
            **{name: {'name': name, 'type': 'Number', 'tags': ['Point'],
                      'groupNames': ['Moon'], 'metadata': {'semantics': {
                          'value': 'Point', 'editable': False, 'config': {'isPointOf': 'Moon'}}}}
               for name in ('Moon_A', 'Moon_B')}}


def test_semantic_contract_keeps_all_members_and_point_edges_not_set_representative():
    original = semantic_fixture(); other = deepcopy(original)
    other['Moon']['metadata']['semantics']['config']['hasPoint'] = 'Moon_B'
    other['Moon']['members'].reverse()
    assert m.dependent_definitions(original) == m.dependent_definitions(other)
    assert original['Moon']['metadata']['semantics']['config']['hasPoint'] == 'Moon_A'
    assert m.dependent_definitions(original)['Moon']['members'] == ['Moon_A', 'Moon_B']


@pytest.mark.parametrize('fault', ['unknown_reference', 'missing_reference', 'wrong_parent',
                                  'missing_member', 'extra_member', 'duplicate_member', 'wrong_group'])
def test_semantic_contract_refuses_broken_membership_or_reference(fault):
    items = semantic_fixture()
    config = items['Moon']['metadata']['semantics']['config']
    if fault == 'unknown_reference': config['hasPoint'] = 'Other'
    elif fault == 'missing_reference': config.pop('hasPoint')
    elif fault == 'wrong_parent': items['Moon_A']['metadata']['semantics']['config']['isPointOf'] = 'Other'
    elif fault == 'missing_member': items['Moon']['members'].pop()
    elif fault == 'extra_member': items['Moon']['members'].append({'name': 'Other'})
    elif fault == 'duplicate_member': items['Moon']['members'].append({'name': 'Moon_A'})
    elif fault == 'wrong_group': items['Moon_A']['groupNames'] = []
    with pytest.raises(RuntimeError, match='semantic'): m.dependent_definitions(items)


def test_semantic_contract_preserves_other_metadata_and_item_fields():
    original = semantic_fixture()
    for target in ('config', 'label', 'tags'):
        other = deepcopy(original)
        if target == 'config': other['Moon']['metadata']['semantics']['config']['hasLocation'] = 'Changed'
        elif target == 'label': other['Moon_A']['label'] = 'Changed'
        else: other['Moon_A']['tags'] = ['Point', 'Measurement']
        assert m.dependent_definitions(original) != m.dependent_definitions(other)


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


class HistoryDB:
    def __init__(self):
        self.calls = []
        self.mapping = sorted(m.HISTORY_IDS.items())
        self.stats = (2, AFTER, NOW)
        self.body = b'original first row\noriginal second row\n'
        self.closed = False
        self.transaction_read_only = 'on'
        self.transaction_isolation = 'repeatable read'

    def set_session(self, **kwargs): self.calls.append(('session', kwargs))
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self
    def execute(self, query, args=()):
        self.query = query
        self.calls.append(('execute', query, args))
    def fetchall(self): return self.mapping
    def fetchone(self):
        if self.query == 'SHOW transaction_read_only': return (self.transaction_read_only,)
        if self.query == 'SHOW transaction_isolation': return (self.transaction_isolation,)
        return self.stats
    def mogrify(self, query, args):
        self.calls.append(('mogrify', query, args))
        return query.encode()
    def copy_expert(self, query, writer):
        self.calls.append(('copy', query))
        writer.write(self.body)
    def close(self): self.closed = True


def test_history_check_pins_every_linked_item_and_exact_read_only_snapshot():
    db = HistoryDB()
    proof = m.history_prefixes(db)
    assert len(proof) == 28
    assert set(proof) == set(m.HISTORY_IDS)
    assert db.calls[0] == ('session', {'readonly': True, 'autocommit': False,
                                     'isolation_level': 'REPEATABLE READ'})
    assert all(row['count'] == 2 and row['cutoff'] == NOW for row in proof.values())
    assert all(row['sha256'] == m.sha256(db.body).hexdigest() for row in proof.values())
    assert len([call for call in db.calls if call[0] == 'copy']) == 28
    assert all('ORDER BY time,value' in call[1] and 'TO STDOUT' in call[1]
               for call in db.calls if call[0] == 'copy')


def test_mapping_database_collation_order_is_not_an_identity_change():
    db = HistoryDB(); db.mapping.reverse()
    assert len(m.history_prefixes(db)) == 28


@pytest.mark.parametrize('field,value', [('transaction_read_only', 'off'),
                                      ('transaction_isolation', 'read committed')])
def test_server_must_confirm_read_only_repeatable_snapshot_before_history(field, value):
    db = HistoryDB(); setattr(db, field, value)
    with pytest.raises(RuntimeError, match='transaction'): m.history_prefixes(db)
    assert not any(call[0] == 'copy' or call[0] == 'execute' and 'public.' in call[1]
                   for call in db.calls)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'remapped', 'alias'])
def test_history_mapping_drift_refuses_before_value_reads(fault):
    db = HistoryDB()
    if fault == 'missing': db.mapping.pop()
    elif fault == 'duplicate': db.mapping.append(db.mapping[0])
    elif fault == 'remapped': db.mapping[0] = (db.mapping[0][0], 9999)
    else: db.mapping.append(('NotMoon', db.mapping[0][1]))
    with pytest.raises(RuntimeError, match='identity'): m.history_prefixes(db)
    assert not any(call[0] == 'copy' for call in db.calls)


@pytest.mark.parametrize('stats', [(0, None, None), (2, AFTER, None),
                                  (2, NOW, AFTER), (2, AFTER.replace(tzinfo=None), NOW)])
def test_empty_or_ambiguous_history_does_not_qualify(stats):
    db = HistoryDB(); db.stats = stats
    with pytest.raises(RuntimeError, match='history'): m.history_prefixes(db)
    assert not any(call[0] == 'copy' for call in db.calls)


def test_later_append_does_not_expand_original_history_prefix():
    db = HistoryDB(); before = m.history_prefixes(db)
    db.calls.clear()
    assert m.history_prefixes(db, before=before) == before
    counts = [call for call in db.calls if call[0] == 'execute' and 'count(*)' in call[1]]
    assert len(counts) == 28
    assert all('WHERE time<=%s' in call[1] and call[2] == (NOW,) for call in counts)
    assert all(call[2] == (NOW,) for call in db.calls if call[0] == 'mogrify')


@pytest.mark.parametrize('field,value', [('id', 9999), ('cutoff', None)])
def test_invalid_original_prefix_refuses_before_database_access(field, value):
    db = HistoryDB(); before = m.history_prefixes(db)
    before[next(iter(before))][field] = value
    db.calls.clear()
    with pytest.raises(RuntimeError, match='prefix'): m.history_prefixes(db, before=before)
    assert not db.calls


@pytest.mark.parametrize('bound', ['table', 'total'])
def test_history_stream_resource_bound_is_enforced(monkeypatch, bound):
    db = HistoryDB()
    monkeypatch.setattr(m, 'MAX_TABLE_HISTORY_BYTES' if bound == 'table'
                        else 'MAX_TOTAL_HISTORY_BYTES', len(db.body) - 1)
    with pytest.raises(RuntimeError, match='bound'): m.history_prefixes(db)


def test_read_only_history_mode_does_not_allocate_provider_fixture(monkeypatch):
    calls = []
    monkeypatch.setattr(m, 'check_history', lambda: calls.append('history'))
    monkeypatch.setattr(m, 'main', lambda: pytest.fail('fixture allocation'))
    m.command(['--check-history'])
    assert calls == ['history']


def test_existing_no_argument_provider_interface_remains_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr(m, 'main', lambda: calls.append('fixture'))
    monkeypatch.setattr(m, 'check_history', lambda: pytest.fail('history mode'))
    m.command([])
    assert calls == ['fixture']


@pytest.mark.parametrize('args', [['--apply'], ['--check-history', 'other'], ['--target', 'other']])
def test_history_mode_has_no_arbitrary_target_or_mutator(args):
    with pytest.raises(RuntimeError, match='interface'): m.command(args)


def test_read_only_check_rechecks_prefix_and_definitions_and_closes_database(monkeypatch, capsys):
    db = HistoryDB()
    thing = {'UID': m.UID, 'editable': True, 'channels': []}
    links = [{'itemName': name} for name in m.HISTORY_IDS]
    items = semantic_fixture()
    monkeypatch.setattr(m, 'preflight', lambda: (thing, links, items))
    transport = m.load('test_moon_history_transport', 'migrate-astro-icon-items.py')
    monkeypatch.setattr(transport.psycopg2, 'connect', lambda **_: db)
    monkeypatch.setattr(transport, 'parse_openhab_jdbc_config',
                        lambda _: type('Settings', (), {'connect_kwargs': {}})())
    monkeypatch.setattr(m, 'load', lambda *_: transport)
    m.check_history()
    import json
    result = json.loads(capsys.readouterr().out)
    assert result['items'] == 28 and result['rows'] == 56
    assert result['production_writes'] == 0
    assert result['production_history_recovery'] == 'not_tested'
    assert result['provider_handoff'] == 'not_tested'
    assert db.closed
    assert len([call for call in db.calls if call[0] == 'session']) == 2
    assert 'original first row' not in json.dumps(result)


@pytest.mark.parametrize('fault', ['history', 'definition'])
def test_read_only_check_refuses_changed_prefix_or_definition(monkeypatch, fault):
    db = HistoryDB()
    thing = {'UID': m.UID, 'editable': True, 'channels': []}
    links = [{'itemName': name} for name in m.HISTORY_IDS]
    items = semantic_fixture()
    calls = []
    def preflight():
        calls.append('preflight')
        row = deepcopy(thing)
        if fault == 'definition' and len(calls) > 1: row['label'] = 'changed'
        return row, links, items
    monkeypatch.setattr(m, 'preflight', preflight)
    transport = m.load('test_moon_changed_history_transport', 'migrate-astro-icon-items.py')
    monkeypatch.setattr(transport.psycopg2, 'connect', lambda **_: db)
    monkeypatch.setattr(transport, 'parse_openhab_jdbc_config',
                        lambda _: type('Settings', (), {'connect_kwargs': {}})())
    monkeypatch.setattr(m, 'load', lambda *_: transport)
    original_copy = db.copy_expert
    copied = []
    def copy(query, writer):
        copied.append(query)
        if fault == 'history' and len(copied) > 28: db.body = b'changed original row\n'
        original_copy(query, writer)
    monkeypatch.setattr(db, 'copy_expert', copy)
    with pytest.raises(RuntimeError, match='changed'): m.check_history()
    assert db.closed
