"""Offline guards for the networkless display-rule provider/JVM rehearsal."""
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

import pytest

spec = importlib.util.spec_from_file_location('display_rule_qualifier',
    Path(__file__).with_name('qualify-season-rule-provider.py'))
q = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = q
spec.loader.exec_module(q)


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    source = tmp_path / 'display.js'
    source.write_text('// isolated source')
    monkeypatch.setattr(q, 'INSTALLED_RULE_DIRECTORY', tmp_path)
    script = 'synthetic managed display script'
    config = replace(q.RULES['season'], source=source, baseline=sha256(script.encode()).hexdigest())
    managed = {'uid': config.uid, 'editable': True, 'triggers': [
        {'type': kind, 'configuration': dict(fields)} for kind, fields in config.triggers],
        'conditions': [], 'actions': [{'configuration': {'script': script}}]}
    file_rule = {**managed, 'editable': False}
    backup = tmp_path / 'managed-rule.json'
    backup.write_text(json.dumps(managed)); backup.chmod(0o600)
    return config, managed, file_rule, backup


def test_existing_managed_baseline_still_requires_exact_action_hash(baseline):
    config, managed, _, _ = baseline
    assert q.managed_baseline(config, managed) == managed
    with pytest.raises(RuntimeError, match='script baseline'):
        q.managed_baseline(replace(config, baseline='0'*64), managed)


def test_managed_payload_preserves_absent_optional_description_and_drops_runtime(baseline):
    _, managed, _, _ = baseline
    original = {**managed, 'name': 'Actual name', 'tags': [],
                'status': {'status': 'IDLE'}}
    payload = q.managed_payload(original)
    assert 'description' not in payload
    assert 'editable' not in payload and 'status' not in payload
    assert payload == {key: value for key, value in original.items()
                       if key not in ('editable', 'status')}
    assert q.managed_payload({**original, 'description': ''}) == {**payload, 'description': ''}


def test_file_owned_baseline_requires_private_exact_preimage(baseline):
    config, managed, file_rule, backup = baseline
    assert q.managed_baseline(config, file_rule, backup) == managed
    with pytest.raises(RuntimeError, match='retained managed backup'):
        q.managed_baseline(config, file_rule)


@pytest.mark.parametrize('damage', ['public', 'symlink', 'oversized', 'script', 'uid', 'trigger', 'source'])
def test_unsafe_or_drifted_file_owned_preimage_is_refused(baseline, damage):
    config, managed, file_rule, backup = baseline
    if damage == 'public': backup.chmod(0o644)
    elif damage == 'symlink':
        link = backup.with_name('link.json'); link.symlink_to(backup); backup = link
    elif damage == 'oversized': backup.write_bytes(b'x'*65537)
    elif damage == 'script':
        managed['actions'][0]['configuration']['script'] = 'wrong source'
        backup.write_text(json.dumps(managed))
    elif damage == 'uid': file_rule = {**file_rule, 'uid': 'another_rule'}
    elif damage == 'trigger': file_rule = {**file_rule, 'triggers': []}
    else:
        directory = config.source.parent / 'candidate'; directory.mkdir()
        other = directory / config.source.name; other.write_text('// changed source')
        config = replace(config, source=other)
    with pytest.raises(RuntimeError):
        q.managed_baseline(config, file_rule, backup)


def test_file_rule_predicate_requires_exact_provider_identity_and_healthy_status():
    rule = {'uid': 'test', 'editable': False, 'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
    assert q._file_rule(lambda *_: (200, rule), 'test') == rule
    for changed in ({**rule, 'editable': True}, {**rule, 'uid': 'other'},
                    {**rule, 'status': {'status': 'UNINITIALIZED', 'statusDetail': 'HANDLER_MISSING_ERROR'}}):
        assert q._file_rule(lambda *_: (200, changed), 'test') is None


def test_jvm_identity_check_reports_only_java_pids(monkeypatch):
    monkeypatch.setattr(q.runtime, 'run', lambda *_:
        b'PID STAT COMMAND\n1 S sh\n22 Sl java\n23 Z java\n99 R ps\n')
    assert q.java_pids('isolated') == (22,)
