from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('moon_consumers', Path(__file__).with_name('preflight-astro-moon-consumers.py'))
m = module_from_spec(spec)
spec.loader.exec_module(m)


def setup(monkeypatch):
    body = 'fixed reviewed source'
    monkeypatch.setattr(m, 'MANAGED_SCRIPTS', {'managed': m.sha256(body.encode()).hexdigest()})
    monkeypatch.setattr(m, 'CANONICAL_MANAGED', {})
    monkeypatch.setattr(m, 'FILE_RULES', {'file': ('file.js', 'pinned')})
    monkeypatch.setattr(m, 'FILE_PINS', ())
    monkeypatch.setattr(m, 'file_pin', lambda path, expected, canonical=None: expected)
    rows = [{'uid': 'managed', 'editable': True, 'actions': [{'type': 'script.ScriptAction',
             'configuration': {'script': body, 'type': 'application/javascript'}}]},
            {'uid': 'file', 'editable': False, 'actions': [{'type': 'jsr223.ScriptedAction'}]}]
    sun = {'UID': 'astro:sun:local', 'thingTypeUID': 'astro:sun', 'editable': True,
           'statusInfo': {'status': 'ONLINE', 'statusDetail': 'NONE'}, 'configuration': {'interval': 300}}
    return rows, sun


def test_read_only_contract_and_no_dependency_closure_claim(monkeypatch):
    rows, sun = setup(monkeypatch)
    calls = []
    def get(path):
        calls.append(path)
        return deepcopy(rows if path == '/rules' else sun)
    result = m.check(get)
    assert calls == ['/rules', '/things/astro:sun:local', '/rules', '/things/astro:sun:local']
    assert result['status'] == 'passed'
    assert result['production_writes'] == 0 and result['apply_available'] is False
    assert result['all_consumer_closure'] is False and result['atomic_snapshot'] is False
    assert 'fixed reviewed source' not in str(result)


@pytest.mark.parametrize('fault', ['absent', 'duplicate', 'provider', 'source', 'extra_action',
                                  'opaque_type', 'managed_type', 'language'])
def test_named_rule_drift_refused(monkeypatch, fault):
    rows, _ = setup(monkeypatch)
    if fault == 'absent': rows.pop(0)
    elif fault == 'duplicate': rows.append(deepcopy(rows[0]))
    elif fault == 'provider': rows[0]['editable'] = False
    elif fault == 'source': rows[0]['actions'][0]['configuration']['script'] += ' changed'
    elif fault == 'extra_action': rows[0]['actions'].append({})
    elif fault == 'opaque_type': rows[1]['actions'][0]['type'] = 'script.ScriptAction'
    elif fault == 'managed_type': rows[0]['actions'][0]['type'] = 'other.Action'
    else: rows[0]['actions'][0]['configuration']['type'] = 'other-language'
    with pytest.raises(RuntimeError): m.verify_rules(rows)


@pytest.mark.parametrize('fault', ['rules', 'sun', 'sun_offline'])
def test_second_snapshot_drift_refused(monkeypatch, fault):
    rows, sun = setup(monkeypatch)
    counts = {}
    def get(path):
        counts[path] = counts.get(path, 0) + 1
        result = deepcopy(rows if path == '/rules' else sun)
        if counts[path] == 2:
            if fault == 'rules' and path == '/rules': result[0]['new_unknown_field'] = 'must retain'
            if fault == 'sun' and path != '/rules': result['configuration']['interval'] = 600
            if fault == 'sun_offline' and path != '/rules': result['statusInfo']['status'] = 'OFFLINE'
        return result
    with pytest.raises(RuntimeError): m.check(get)


def test_only_rule_execution_status_excluded_from_definition():
    rows = [{'uid': 'test', 'status': {'status': 'RUNNING'}, 'unknown_definition': {'exact': 1}}]
    before = deepcopy(rows)
    result = m.rule_graph(rows)
    assert rows == before
    assert result == [{'uid': 'test', 'unknown_definition': {'exact': 1}}]


@pytest.mark.parametrize('fault', ['source', 'canonical', 'symlink', 'missing', 'oversized'])
def test_file_pin_refuses_drift(monkeypatch, tmp_path, fault):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    body = b'reviewed'
    expected = m.sha256(body).hexdigest()
    path = tmp_path / 'installed'; path.write_bytes(body)
    canonical = tmp_path / 'canonical'; canonical.write_bytes(body)
    if fault == 'source': path.write_bytes(b'changed')
    elif fault == 'canonical': canonical.write_bytes(b'changed')
    elif fault == 'symlink': path.unlink(); path.symlink_to(canonical)
    elif fault == 'missing': path.unlink()
    elif fault == 'oversized':
        with path.open('r+b') as stream: stream.truncate(16 * 1024**2 + 1)
    with pytest.raises(RuntimeError): m.file_pin(path, expected, 'canonical')


def test_valid_source_and_canonical_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    path = tmp_path / 'source'; path.write_bytes(b'reviewed')
    expected = m.sha256(b'reviewed').hexdigest()
    assert m.file_pin(path, expected, 'source') == expected


@pytest.mark.parametrize('args', [['--apply'], ['--target', '/other'], ['--check']])
def test_no_mutation_or_target_interface(monkeypatch, args):
    monkeypatch.setattr(m, 'check', lambda: pytest.fail('check must not run'))
    with pytest.raises(RuntimeError): m.command(args)
