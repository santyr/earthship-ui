"""Isolated exact-runtime delta and original-replay preservation checks."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location('thermal_radiation_qualification',
    Path(__file__).with_name('qualify-thermal-radiation-runtime.py'))
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


def fixture(tmp_path):
    installed, repo = tmp_path/'installed', tmp_path/'repo'
    paths = q.bundle.LEGACY_RUNTIME_PATHS
    baseline = {}
    for name in (*paths, q.CAPTURE_HELPER):
        data = (f'RUNTIME_REVISION_PATHS = {paths!r}\n'.encode() if name == 'thermal_intel.py'
                else f'# original installed {name}\n'.encode())
        baseline[name] = data
    q._write_tree(installed, baseline)
    delta = {name: (f'RUNTIME_REVISION_PATHS = {q.bundle.RADIATION_RUNTIME_PATHS!r}\n'.encode()
                   if name == 'thermal_intel.py' else f'# candidate {name}\n'.encode())
             for name in q.DELTA}
    q._write_tree(repo/'openhab/scripts', delta)
    # These unrelated repository changes must never enter the frozen candidate.
    q._write_tree(repo/'openhab/scripts', {
        name: b'# unrelated unqualified candidate\n' for name in (
            'thermal_model/artifacts.py', 'thermal_model/dynamics.py',
            'thermal_model/evaluation.py', 'thermal_model/journal.py', 'thermal_model/schema.py')})
    capture = tmp_path/'original.json.gz'
    capture.write_bytes(b'private original capture fixture'); capture.chmod(0o600)
    return dict(repo_root=repo, installed_root=installed,
                expected_revision=q._revision(baseline, paths), captures=[capture]), baseline


def fake_replay(runtime, capture, revision):
    paths = q.bundle._paths((runtime/'thermal_intel.py').read_bytes())
    values = {name: (runtime/name).read_bytes() for name in paths}
    assert q._revision(values, paths) == revision
    return dict(capture_output_sha256=sha256(capture.read_bytes()).hexdigest(), artifact_code_revision='a'*64)


def test_exact_delta_replay_rollback_and_production_sources_unchanged(tmp_path):
    args, baseline = fixture(tmp_path)
    roots = []
    def replay(runtime, capture, revision):
        roots.append(runtime)
        for name in ('thermal_model/artifacts.py', 'thermal_model/dynamics.py',
                     'thermal_model/evaluation.py', 'thermal_model/journal.py', 'thermal_model/schema.py'):
            assert (runtime/name).read_bytes() == baseline[name]
        return fake_replay(runtime, capture, revision)
    result = q.qualify(**args, replay_runner=replay)
    assert result['installed_revision'] == args['expected_revision']
    assert result['candidate_revision'] != result['installed_revision']
    assert set(result['delta_sha256']) == set(q.DELTA)
    assert result['interrupted_rollback'] and result['candidate_install_restore']
    assert result['production_writes'] == 0 and not result['controls_enabled']
    assert len(result['replays']) == 1 and len(roots) == 3
    assert all(not root.exists() for root in roots)
    for name, data in baseline.items():
        assert (args['installed_root']/name).read_bytes() == data
    assert not any((args['installed_root']/name).exists() for name in q.DELTA[1:])


def test_actual_input_probe_is_explicit_and_candidate_only(tmp_path):
    args, _ = fixture(tmp_path)
    calls = []
    def read(runtime):
        calls.append(runtime)
        assert q.bundle._paths((runtime/'thermal_intel.py').read_bytes()) == q.bundle.RADIATION_RUNTIME_PATHS
        return {'scope': 'unit-test-current-inputs'}
    assert 'current_inputs' not in q.qualify(**args, replay_runner=fake_replay, current_reader=read)
    assert calls == []
    result = q.qualify(**args, replay_runner=fake_replay, check_current=True, current_reader=read)
    assert result['current_inputs'] == {'scope': 'unit-test-current-inputs'}
    assert len(calls) == 1 and not calls[0].exists()


def test_current_probe_failure_refuses_and_cleans_isolated_runtime(tmp_path):
    args, _ = fixture(tmp_path)
    calls = []
    def read(runtime):
        calls.append(runtime)
        raise ValueError('current receipt unavailable')
    with pytest.raises(ValueError, match='current receipt unavailable'):
        q.qualify(**args, replay_runner=fake_replay, check_current=True, current_reader=read)
    assert len(calls) == 1 and not calls[0].exists()


@pytest.mark.parametrize('damage', ['pin', 'installed', 'existing_destination', 'inventory', 'capture_permissions'])
def test_preflight_refuses_before_allocating_runtime(tmp_path, monkeypatch, damage):
    args, _ = fixture(tmp_path)
    if damage == 'pin': args['expected_revision'] = '0'*64
    elif damage == 'installed': (args['installed_root']/'thermal_model/dynamics.py').write_bytes(b'changed')
    elif damage == 'existing_destination': (args['installed_root']/q.DELTA[1]).write_bytes(b'existing')
    elif damage == 'inventory':
        (args['repo_root']/'openhab/scripts/thermal_intel.py').write_bytes(
            f'RUNTIME_REVISION_PATHS = {q.bundle.LEGACY_RUNTIME_PATHS!r}\n'.encode())
    elif damage == 'capture_permissions': args['captures'][0].chmod(0o644)
    monkeypatch.setattr(q.tempfile, 'TemporaryDirectory', lambda **kwargs: pytest.fail('runtime allocated'))
    with pytest.raises(ValueError): q.qualify(**args, replay_runner=fake_replay)


@pytest.mark.parametrize('damage', ['installed', 'source', 'capture'])
def test_concurrent_input_drift_refuses_and_removes_candidate(tmp_path, damage):
    args, _ = fixture(tmp_path)
    roots = []
    def replay(runtime, capture, revision):
        roots.append(runtime)
        result = fake_replay(runtime, capture, revision)
        if len(roots) == 3:
            if damage == 'installed': path = args['installed_root']/'thermal_model/dynamics.py'
            elif damage == 'source': path = args['repo_root']/'openhab/scripts/thermal_radiation_runtime.py'
            else: path = capture
            path.write_bytes(path.read_bytes()+b' drift')
        return result
    with pytest.raises(ValueError, match='changed during qualification'):
        q.qualify(**args, replay_runner=replay)
    assert roots and all(not root.exists() for root in roots)


def test_replay_identity_divergence_refuses_without_production_install(tmp_path):
    args, baseline = fixture(tmp_path)
    roots = []
    def replay(runtime, capture, revision):
        roots.append(runtime)
        result = fake_replay(runtime, capture, revision)
        if len(roots) == 2: result['capture_output_sha256'] = 'b'*64
        return result
    with pytest.raises(ValueError, match='changed original replay identity'):
        q.qualify(**args, replay_runner=replay)
    assert all(not root.exists() for root in roots)
    assert (args['installed_root']/'thermal_intel.py').read_bytes() == baseline['thermal_intel.py']


@pytest.mark.parametrize('field', ['scope', 'exact_as_issued', 'runtime_manifest_revision',
    'counterfactual_is_action_evidence', 'capture_output_sha256', 'artifact_code_revision'])
def test_subprocess_result_requires_exact_source_and_original_identity(monkeypatch, field):
    result = dict(scope='read_only_exact_thermal_replay', exact_as_issued=True,
        runtime_manifest_revision='a'*64, counterfactual_is_action_evidence=False,
        capture_output_sha256='b'*64, artifact_code_revision='c'*64)
    result[field] = 'wrong'
    monkeypatch.setattr(q.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(result)))
    with pytest.raises(ValueError): q._replay(Path('/runtime'), Path('/capture'), 'a'*64)


def test_cli_help_does_not_allocate_or_qualify(monkeypatch):
    monkeypatch.setattr(q, 'qualify', lambda **kwargs: pytest.fail('qualification ran'))
    with pytest.raises(SystemExit) as result: q.main(['--help'])
    assert result.value.code == 0


def test_cli_error_does_not_print_private_exception(monkeypatch, capsys):
    def failed(**kwargs): raise RuntimeError('PRIVATE-TEST-DSN')
    monkeypatch.setattr(q, 'qualify', failed)
    assert q.main(['--repo-root', '/repo', '--installed-root', '/installed',
                   '--expected-runtime-revision', 'a'*64, '--capture', '/capture']) == 1
    out = capsys.readouterr()
    assert out.out == '' and out.err == 'isolated thermal radiation qualification unavailable\n'
