"""Synthetic guarded deployment tests. No production writes or connections."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import stat

import pytest

spec = importlib.util.spec_from_file_location('estimator_deploy',
    Path(__file__).with_name('deploy-bms-runtime-estimator-evidence.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def baseline(monkeypatch):
    monkeypatch.setattr(m, 'OLD_SHA', sha256(b'old synthetic').hexdigest())
    monkeypatch.setattr(m, 'NEW_SHA', sha256(b'new synthetic').hexdigest())
    return {'uid': m.UID, 'editable': True, 'name': 'runtime', 'conditions': [],
            'configuration': {}, 'tags': ['preserve'], 'triggers': deepcopy(m.OLD_TRIGGERS),
            'actions': [{'id': '2', 'type': 'script.ScriptAction', 'inputs': {},
                         'configuration': {'type': 'application/javascript', 'script': 'old synthetic'}}]}


def test_exact_delta_preserves_metadata_and_changes_only_source_and_triggers(monkeypatch):
    raw = baseline(monkeypatch)
    original = deepcopy(raw)
    desired = m.plan(raw, 'new synthetic', m.descriptor())
    expected = m.common.rule_body(raw)
    expected['triggers'] = m.descriptor()['triggers']
    expected['actions'][0]['configuration']['script'] = 'new synthetic'
    assert desired == expected and raw == original


@pytest.mark.parametrize('change', [
    lambda r: r.update(uid='hex_southoutlet_cycle'),
    lambda r: r.update(editable=False),
    lambda r: r.update(triggers=[]),
    lambda r: r.update(conditions=[{}]),
    lambda r: r['actions'][0].update(inputs={'event': 'foreign.output'}),
    lambda r: r['actions'][0]['configuration'].update(script='foreign source'),
])
def test_baseline_drift_refused(monkeypatch, change):
    raw = baseline(monkeypatch); change(raw)
    with pytest.raises(RuntimeError): m.plan(raw, 'new synthetic', m.descriptor())


def test_candidate_and_descriptor_drift_refused(monkeypatch):
    raw = baseline(monkeypatch)
    with pytest.raises(RuntimeError): m.plan(raw, 'foreign source', m.descriptor())
    d = m.descriptor(); d['enabled'] = True
    with pytest.raises(RuntimeError): m.plan(raw, 'new synthetic', d)


def test_preflight_refuses_unqualified_runtime_before_other_host_reads(monkeypatch):
    reads = []
    def get(path):
        reads.append(path)
        assert path == '/'
        return {'runtimeInfo': {'version': '5.2.2'}}
    monkeypatch.setattr(m.common.oh, 'get', get)
    with pytest.raises(RuntimeError, match='qualified JVM version'): m.inspect()
    assert reads == ['/']


def transaction(monkeypatch, tmp_path, failure=None):
    raw = baseline(monkeypatch)
    old = m.common.rule_body(raw); new = m.plan(raw, 'new synthetic', m.descriptor())
    state = {'rule': deepcopy(old)}; writes = []
    monkeypatch.setattr(m, 'RELEASE_READY', True)
    monkeypatch.setattr(m, 'PRIVATE_ROOT', tmp_path / 'private')
    monkeypatch.setattr(m, 'inspect', lambda: (deepcopy(state['rule']), new, 'guard'))
    monkeypatch.setattr(m, 'guard_digest', lambda: 'guard')
    monkeypatch.setattr(m, 'read_definition', lambda: deepcopy(state['rule']))
    monkeypatch.setattr(m, 'verify_ready', lambda expected: None)
    def put(body):
        writes.append(deepcopy(body)); state['rule'] = deepcopy(body)
        if len(writes) == 1 and failure:
            if failure == 'concurrent': state['rule']['name'] = 'foreign edit'
            raise OSError('private server detail must never be printed')
    monkeypatch.setattr(m, 'put_definition', put)
    return old, new, state, writes


def test_closed_gate_and_unattended_apply_do_no_io(monkeypatch):
    monkeypatch.setattr(m, 'RELEASE_READY', False)
    monkeypatch.setattr(m, 'inspect', lambda: pytest.fail('read before closed gate'))
    with pytest.raises(RuntimeError): m.apply({}, {}, 'guard', attended=True)
    assert m.main(['--apply', '--attended']) == 1
    monkeypatch.setattr(m, 'RELEASE_READY', True)
    with pytest.raises(RuntimeError): m.apply({}, {}, 'guard', attended=False)
    assert m.main(['--apply']) == 1


def test_success_is_provisional_definition_only(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path)
    result = m.apply(old, new, 'guard', attended=True)
    assert result['status'] == 'definition_updated_natural_evidence_pending'
    assert writes == [new] and state['rule'] == new
    backup = Path(result['private_backup']) / 'preimage.json'
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.parent.stat().st_mode) == 0o700
    assert json.loads(backup.read_text())['original'] == old


def test_ambiguous_put_failure_rolls_back_owned_candidate(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path, 'ambiguous')
    with pytest.raises(m.ApplyFailure) as error: m.apply(old, new, 'guard', attended=True)
    assert error.value.status == 'apply_failed_rollback_verified'
    assert state['rule'] == old and writes == [new, old]


def test_unknown_concurrent_edit_is_never_overwritten(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path, 'concurrent')
    with pytest.raises(m.ApplyFailure) as error: m.apply(old, new, 'guard', attended=True)
    assert error.value.status == 'apply_failed_rollback_unverified'
    assert state['rule']['name'] == 'foreign edit' and writes == [new]


def test_recheck_refuses_drift_before_put(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path)
    state['rule']['name'] = 'new operator metadata'
    with pytest.raises(RuntimeError): m.apply(old, new, 'guard', attended=True)
    assert writes == []


def test_late_target_change_stops_without_rollback_over_foreign_edit(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path)
    foreign = deepcopy(old); foreign['name'] = 'late operator edit'
    monkeypatch.setattr(m, 'read_definition', lambda: foreign)
    with pytest.raises(RuntimeError, match='immediately before PUT'):
        m.apply(old, new, 'guard', attended=True)
    assert writes == []


def test_unrelated_drift_rolls_back_only_estimator(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path)
    monkeypatch.setattr(m, 'guard_digest', lambda: 'changed protected config')
    with pytest.raises(m.ApplyFailure) as error: m.apply(old, new, 'guard', attended=True)
    assert error.value.status == 'apply_failed_rollback_verified'
    assert writes == [new, old] and state['rule'] == old


def test_readiness_failure_rolls_back_and_verifies_original(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path)
    checks = []
    def ready(expected):
        checks.append(deepcopy(expected))
        if expected == new: raise OSError('unready candidate')
        assert state['rule'] == old
    monkeypatch.setattr(m, 'verify_ready', ready)
    with pytest.raises(m.ApplyFailure) as error: m.apply(old, new, 'guard', attended=True)
    assert error.value.status == 'apply_failed_rollback_verified'
    assert checks == [new, old] and writes == [new, old]


def test_backup_failure_never_puts(monkeypatch, tmp_path):
    old, new, state, writes = transaction(monkeypatch, tmp_path)
    def fail(*_): raise OSError('backup failed')
    monkeypatch.setattr(m, 'save_backup', fail)
    with pytest.raises(OSError): m.apply(old, new, 'guard', attended=True)
    assert writes == [] and state['rule'] == old


def test_put_scope_refuses_foreign_rule_or_unknown_source(monkeypatch):
    monkeypatch.setattr(m.common, 'request', lambda *_: pytest.fail('foreign mutation'))
    for body in [{'uid': 'hex_southoutlet_cycle'}, {'uid': m.UID}]:
        with pytest.raises(RuntimeError): m.put_definition(body)


def test_put_rejects_extra_action_inputs_config_and_triggers(monkeypatch):
    original = baseline(monkeypatch)
    monkeypatch.setattr(m.common, 'request', lambda *_: pytest.fail('foreign mutation'))
    for mutation in [lambda r: r['actions'][0].update(type='exec.Execute'),
                     lambda r: r['actions'][0]['configuration'].update(command='foreign'),
                     lambda r: r['actions'][0].update(inputs={'event': 'foreign.output'}),
                     lambda r: r.update(triggers=[])]:
        bad = deepcopy(original); mutation(bad)
        with pytest.raises(RuntimeError): m.put_definition(bad)


def test_main_never_prints_private_server_errors(monkeypatch, capsys):
    def fail(): raise OSError('private server response body')
    monkeypatch.setattr(m, 'inspect', fail)
    assert m.main(['--check']) == 1
    output = capsys.readouterr().out
    assert 'private server' not in output and json.loads(output)['error_type'] == 'OSError'


def test_guard_excludes_natural_states_but_detects_definition_drift(monkeypatch):
    rules = [{'uid': uid, 'actions': [], 'triggers': [],
              'status': {'status': 'IDLE', 'statusDetail': 'NONE'}} for uid in m.PROTECTED]
    collector = next(r for r in rules if r['uid'] == 'hex_bms_runtime_input_evidence')
    collector['actions'] = [{'configuration': {'script': 'synthetic collector'}}]
    monkeypatch.setattr(m, 'COLLECTOR_SHA', sha256(b'synthetic collector').hexdigest())
    state = {'natural': 'first'}
    def get(path):
        if path == '/rules': return deepcopy(rules)
        if path.startswith('/things/'):
            return {'UID': path, 'configuration': {}, 'channels': [], 'statusInfo': {'status': 'ONLINE'}}
        if path.startswith('/items/'):
            name = path.rsplit('/', 1)[-1]
            return {'name': name, 'type': m.OUTPUTS.get(name, 'String'),
                    'editable': True, 'state': state['natural']}
        if path == '/links': return []
        if path == '/persistence/jdbc': return {'configs': []}
        pytest.fail('unexpected read')
    monkeypatch.setattr(m.common.oh, 'get', get)
    original = m.guard_digest()
    state['natural'] = 'new native observation'
    rules[0]['status']['status'] = 'RUNNING'
    assert m.guard_digest() == original
    rules[0]['triggers'] = [{'id': 'foreign change'}]
    assert m.guard_digest() != original
    rules[0]['status'] = {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'}
    with pytest.raises(RuntimeError): m.guard_digest()


def test_process_lock_refuses_overlap_and_symlink(monkeypatch, tmp_path):
    monkeypatch.setattr(m, 'PRIVATE_ROOT', tmp_path / 'private')
    with m.apply_lock():
        with pytest.raises(RuntimeError):
            with m.apply_lock(): pytest.fail('overlapping lock')
    lock = m.PRIVATE_ROOT / 'bms-estimator.lock'
    lock.unlink(); target = tmp_path / 'untouched'; target.write_text('keep')
    lock.symlink_to(target)
    with pytest.raises(OSError):
        with m.apply_lock(): pytest.fail('symlink lock')
    assert target.read_text() == 'keep'


def test_private_root_must_be_owned_0700_directory(monkeypatch, tmp_path):
    root = tmp_path / 'private'; root.mkdir(mode=0o755)
    root.chmod(0o755)  # Exercise unsafe permissions even under a private umask.
    monkeypatch.setattr(m, 'PRIVATE_ROOT', root)
    with pytest.raises(RuntimeError):
        with m.apply_lock(): pytest.fail('unsafe lock root')


def test_native_field_requires_original_freshness_and_exact_units():
    now = 1800000000000
    row = {'version': 1, 'basis': 'native_runtime_inputs_v1',
           'streamEpoch': '12345678-1234-4234-8234-123456789abc', 'sequence': 1,
           'recordedAt': now, 'fields': {'battery.dc_voltage_cv': {'status': 'valid',
           'reason': 'ok', 'observedAt': now, 'validUntil': now + 90000, 'value': 5300}}}
    def valid(r, at=now):
        return m.native_field(json.dumps(r), at, 'native_runtime_inputs_v1',
                              'battery.dc_voltage_cv', 90000, 'value', 4000, 6500)
    assert valid(row)
    assert not valid(row, now + 90000)
    for mutation in [lambda r: r.update(basis='held'),
                     lambda r: r.update(recordedAt=now+1),
                     lambda r: r['fields']['battery.dc_voltage_cv'].update(value=53),
                     lambda r: r['fields']['battery.dc_voltage_cv'].update(validUntil=now+90001),
                     lambda r: r.update(sequence=True)]:
        bad = deepcopy(row); mutation(bad); assert not valid(bad)
