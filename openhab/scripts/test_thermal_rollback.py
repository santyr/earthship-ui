"""Private recovery transactions, with no services, network or numerical fitting."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_thermal_runtime_bundle import inputs
from test_thermal_origin_capture import capture_inputs
from thermal_model.runtime_bundle import capture_runtime_bundle


def module():
    from thermal_model import rollback
    return rollback


def saved(tmp_path, monkeypatch):
    root, executable, archive, paths, binding = inputs(tmp_path, monkeypatch)
    bundle = capture_runtime_bundle(archive, root, paths, expected_binding=binding)
    previous = capture_inputs()
    snapshots = tmp_path/'snapshots'; snapshots.mkdir(mode=0o700)
    snapshot = module().retain_snapshot(snapshots, runtime_bundle=bundle,
        artifact=previous['artifact'], output=previous['output'])
    return snapshot, previous, binding


def test_restore_preserves_exact_pair_and_reason_without_active_publication(tmp_path, monkeypatch):
    snapshot, previous, binding = saved(tmp_path, monkeypatch)
    destination = tmp_path/'recovery'
    receipt = module().prepare_restore(snapshot, destination, reason='baseline_regression')
    assert receipt['reason'] == 'baseline_regression'
    assert receipt['automatic_actuation'] is False
    assert receipt['installed'] is False
    assert json.loads((destination/'last-shadow.json').read_text()) == previous['output']
    assert json.loads((destination/'models/accepted.json').read_text())['code_revision'] == previous['artifact'].code_revision
    assert (destination/'runtime/thermal_intel.py').read_bytes() == b'# fixture publication core\n'
    assert receipt['snapshot_sha256'] == module().read_snapshot(snapshot)['snapshot_sha256']


@pytest.mark.parametrize('damage', ['artifact', 'output', 'runtime', 'mode', 'extra'])
def test_corrupt_or_exposed_snapshot_refuses_restore(tmp_path, monkeypatch, damage):
    snapshot, _, binding = saved(tmp_path, monkeypatch)
    if damage == 'artifact': (snapshot/'artifact.json').write_text('{}')
    elif damage == 'output': (snapshot/'last-shadow.json').write_text('{}')
    elif damage == 'runtime': next((snapshot/'bundles').glob('*/sources/thermal_intel.py')).write_text('# changed')
    elif damage == 'mode': (snapshot/'artifact.json').chmod(0o644)
    else: (snapshot/'extra').write_text('unexpected')
    with pytest.raises(ValueError): module().prepare_restore(snapshot, tmp_path/'recovery', reason='artifact_corrupt')
    assert not (tmp_path/'recovery').exists()


def test_incompatible_artifact_and_last_publication_cannot_be_retained(tmp_path, monkeypatch):
    root, _, archive, paths, binding = inputs(tmp_path, monkeypatch)
    bundle = capture_runtime_bundle(archive, root, paths, expected_binding=binding)
    previous = capture_inputs(); artifact = deepcopy(previous['artifact'])
    from dataclasses import replace
    artifact = replace(artifact, code_revision='a'*40)
    snapshots = tmp_path/'snapshots'; snapshots.mkdir(mode=0o700)
    with pytest.raises(ValueError): module().retain_snapshot(snapshots, runtime_bundle=bundle,
        artifact=artifact, output=previous['output'])
    assert not any(path.is_dir() for path in snapshots.iterdir())


def test_changed_dependency_environment_refuses_restore(tmp_path, monkeypatch):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    import numpy
    monkeypatch.setattr(numpy, '__version__', 'changed-version')
    with pytest.raises(ValueError): module().prepare_restore(snapshot, tmp_path/'recovery', reason='operator_rollback')
    assert not (tmp_path/'recovery').exists()


def test_existing_target_and_interrupted_copy_preserve_previous_files(tmp_path, monkeypatch):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    destination = tmp_path/'recovery'; destination.mkdir(mode=0o700)
    previous = destination/'keep'; previous.write_text('untouched')
    with pytest.raises(ValueError): module().prepare_restore(snapshot, destination, reason='operator_rollback')
    assert previous.read_text() == 'untouched'
    def failed(*_): raise OSError('interrupted copy')
    monkeypatch.setattr(module(), '_copy_tree', failed)
    with pytest.raises(OSError): module().prepare_restore(snapshot, tmp_path/'new-recovery', reason='publication_invalid')
    assert not (tmp_path/'new-recovery').exists()
    assert not list(tmp_path.glob('.thermal-restore-*'))


def test_unknown_reason_cannot_prepare_recovery(tmp_path, monkeypatch):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    with pytest.raises(ValueError): module().prepare_restore(snapshot, tmp_path/'recovery', reason='active_override')


def cli():
    import importlib.util
    path = Path(__file__).resolve().parents[2]/'scripts/rollback-thermal-release.py'
    specification = importlib.util.spec_from_file_location('rollback_cli', path)
    result = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(result)
    return result


def test_preparation_cli_reports_uninstalled_recovery_files(tmp_path, monkeypatch, capsys):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    assert cli().main(['--snapshot', str(snapshot), '--destination', str(tmp_path/'recovery'),
        '--reason', 'operator_rollback']) == 0
    assert json.loads(capsys.readouterr().out)['installed'] is False


def test_preparation_cli_refuses_invalid_snapshot_without_success(tmp_path, capsys):
    assert cli().main(['--snapshot', str(tmp_path/'missing'), '--destination', str(tmp_path/'recovery'),
        '--reason', 'artifact_corrupt']) == 2
    captured = capsys.readouterr()
    assert captured.out == '' and 'refused' in captured.err


def test_prepared_generation_verifier_rechecks_retained_bytes(tmp_path, monkeypatch):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    target = tmp_path/'recovery'
    expected = module().prepare_restore(snapshot, target, reason='operator_rollback')
    assert module().verify_prepared_restore(snapshot, target) == expected


@pytest.mark.parametrize('damage', ['source', 'artifact', 'output', 'extra', 'true_flag', 'numeric_flag', 'symlink'])
def test_prepared_generation_changes_cannot_pass_verification(tmp_path, monkeypatch, damage):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    target = tmp_path/'recovery'
    module().prepare_restore(snapshot, target, reason='operator_rollback')
    if damage == 'source': (target/'runtime/thermal_intel.py').write_text('# changed')
    elif damage == 'artifact': (target/'models/accepted.json').write_text('{}')
    elif damage == 'output': (target/'last-shadow.json').write_text('{}')
    elif damage == 'extra': (target/'runtime/extra.py').write_text('# unexpected')
    elif damage in ('true_flag', 'numeric_flag'):
        path = target/'rollback.json'; value = json.loads(path.read_text())
        value['cold_runtime_qualified'] = True if damage == 'true_flag' else 0
        path.write_text(json.dumps(value))
    else:
        path = target/'models/accepted.json'; path.unlink(); path.symlink_to(snapshot/'artifact.json')
    with pytest.raises(ValueError): module().verify_prepared_restore(snapshot, target)


def test_cli_verify_only_reads_existing_prepared_generation(tmp_path, monkeypatch, capsys):
    snapshot, _, _ = saved(tmp_path, monkeypatch)
    target = tmp_path/'recovery'
    module().prepare_restore(snapshot, target, reason='operator_rollback')
    before = (target/'rollback.json').read_bytes()
    assert cli().main(['--snapshot', str(snapshot), '--destination', str(target),
        '--reason', 'operator_rollback', '--verify-only']) == 0
    assert (target/'rollback.json').read_bytes() == before
    assert json.loads(capsys.readouterr().out)['cold_runtime_qualified'] is False


def test_recovered_registry_read_preserves_prepared_generation_verification(tmp_path, monkeypatch):
    from thermal_model.artifacts import ArtifactRegistry
    snapshot, previous, _ = saved(tmp_path, monkeypatch)
    target = tmp_path/'recovery'
    expected = module().prepare_restore(snapshot, target, reason='operator_rollback')
    assert ArtifactRegistry(target/'models').load_accepted() == previous['artifact']
    assert module().verify_prepared_restore(snapshot, target) == expected
