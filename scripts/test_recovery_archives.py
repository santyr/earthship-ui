"""Offline regression checks for the recovery archive verifier."""
import importlib.util
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('rehearse-openhab-recovery.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
runtime_spec = importlib.util.spec_from_file_location('runtime', Path(__file__).with_name('rehearse-openhab-runtime.py'))
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)


def test_unordered_item_collections_do_not_mutate_input():
    entry = {'tags': ['b', 'a'], 'groupNames': ['z', 'c']}
    assert runtime.canonical_definition('items', entry, ('tags', 'groupNames')) == {'tags': ['a', 'b'], 'groupNames': ['c', 'z']}
    assert entry['tags'] == ['b', 'a']


def test_rule_action_order_is_preserved():
    first = {'actions': [{'id': 'a'}, {'id': 'b'}], 'tags': ['z', 'a']}
    second = {'actions': list(reversed(first['actions'])), 'tags': ['a', 'z']}
    assert runtime.canonical_definition('rules', first, ('actions', 'tags')) != runtime.canonical_definition('rules', second, ('actions', 'tags'))


def test_channel_order_is_not_configuration_drift():
    channels = [{'uid': 'b', 'configuration': {'x': 1}}, {'uid': 'a'}]
    assert runtime.canonical_definition('things', {'channels': channels}, ('channels',)) == runtime.canonical_definition('things', {'channels': list(reversed(channels))}, ('channels',))


def test_expected_host_channel_metadata_is_explicit_and_narrow():
    host = 'systeminfo:computer:ogsatoth'
    bulb = 'tplinksmarthome:kl125:E62B6D'
    source = {
        host: {'UID': host, 'configuration': {'same': True}, 'channels': [
            {'uid': host + ':network0#mac', 'label': 'host', 'description': 'host'},
            {'uid': host + ':sensors#cpuTemp', 'description': 'sensor'}]},
        bulb: {'UID': bulb, 'configuration': {'same': True}, 'channels': [
            {'uid': bulb + ':colorTemperature', 'defaultTags': ['old'], 'label': 'color'}]},
    }
    restored = {
        host: {'UID': host, 'configuration': {'same': True}, 'channels': [
            {'uid': host + ':network0#mac', 'label': 'clone', 'description': 'clone'},
            {'uid': host + ':sensors#cpuTemp', 'description': 'clone sensor'}]},
        bulb: {'UID': bulb, 'configuration': {'same': True}, 'channels': [
            {'uid': bulb + ':colorTemperature', 'defaultTags': ['new'], 'label': 'color'}]},
    }
    material, dynamic = runtime.classify_thing_drift(source, restored)
    assert material == []
    assert len(dynamic) == 3
    assert {field for row in dynamic for field in row['fields']} == {
        'label', 'description', 'defaultTags'}

    restored[host]['channels'].append({'uid': host + ':storage10#used', 'type': 'Number'})
    material, dynamic = runtime.classify_thing_drift(source, restored)
    assert material == []
    assert any(row['channel'] == host + ':storage10#used'
               and row['fields'] == ['clone_only_storage_channel'] for row in dynamic)
    restored[host]['channels'].append({'uid': host + ':network99#mac', 'type': 'String'})
    assert runtime.classify_thing_drift(source, restored)[0] == [host]
    restored[host]['channels'].pop()
    restored[host]['channels'] = restored[host]['channels'][1:]
    assert runtime.classify_thing_drift(source, restored)[0] == [host]
    restored[host]['channels'].insert(0, {'uid': host + ':network0#mac',
                                          'label': 'clone', 'description': 'clone'})

    restored[bulb]['channels'][0]['label'] = 'changed'
    assert runtime.classify_thing_drift(source, restored)[0] == [bulb]
    restored[bulb]['channels'][0]['label'] = 'color'
    restored[bulb]['configuration']['same'] = False
    assert runtime.classify_thing_drift(source, restored)[0] == [bulb]
    restored[bulb]['configuration']['same'] = True
    restored[bulb]['channels'].append(dict(restored[bulb]['channels'][0]))
    assert runtime.classify_thing_drift(source, restored)[0] == [bulb]


def test_integrated_boot_requires_material_definition_and_rule_gates():
    result = {'observational_state_matches_backup': True,
              'persistence_services': ['jdbc'],
              'numeric_undef_publication_verified': True,
              'unexpected_uninitialized_rules': [],
              **{endpoint + '_material_definition_mismatches': []
                 for endpoint in ('items', 'things', 'rules', 'links')}}
    assert runtime.integrated_boot_qualified(result)
    assert not runtime.integrated_boot_qualified({
        **result, 'things_material_definition_mismatches': ['changed Thing']})
    assert not runtime.integrated_boot_qualified({
        **result, 'unexpected_uninitialized_rules': ['active Rule']})
    assert not runtime.integrated_boot_qualified({
        **result, 'numeric_undef_publication_verified': False})
    missing = dict(result)
    del missing['items_material_definition_mismatches']
    assert not runtime.integrated_boot_qualified(missing)


def test_sparse_round_trip_and_mutation(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    sparse = source / 'sparse'
    with sparse.open('wb') as f:
        f.write(b'first')
        f.seek(1024**3)
        f.write(b'last')
    archive = tmp_path / 'source.tar'
    subprocess.run(['tar', '--sparse', '-cf', str(archive), '-C', str(source), '.'], check=True)
    assert archive.stat().st_size < 1024**2
    expected = recovery.archive_fingerprints(archive)
    assert expected['sparse'][0] == 1024**3 + 4
    restored = tmp_path / 'restored'
    restored.mkdir()
    subprocess.run(['tar', '-xf', str(archive), '-C', str(restored)], check=True)
    actual = tmp_path / 'actual.tar'
    subprocess.run(['tar', '--sparse', '-cf', str(actual), '-C', str(restored), '.'], check=True)
    assert recovery.archive_fingerprints(actual) == expected
    with (restored / 'sparse').open('r+b') as f:
        f.seek(512 * 100)
        f.write(b'changed hole')
    subprocess.run(['tar', '--sparse', '-cf', str(actual), '-C', str(restored), '.'], check=True)
    assert recovery.archive_fingerprints(actual) != expected


def test_regular_files_and_symlinks(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'content').write_bytes(b'example\x00')
    (source / 'alias').symlink_to('content')
    archive = tmp_path / 'source.tar'
    subprocess.run(['tar', '--sparse', '-cf', str(archive), '-C', str(source), '.'], check=True)
    result = recovery.archive_fingerprints(archive)
    assert result['content'][0] == 8
    assert result['alias'] == ['link', 'content']
