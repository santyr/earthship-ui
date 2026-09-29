"""Source-bound, private thermal replay bundle regression checks."""

import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/thermal-replay-bundle.py'
SPEC = importlib.util.spec_from_file_location('thermal_replay_bundle', SCRIPT)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


def fixture(tmp_path):
    runtime = tmp_path / 'runtime'
    state = tmp_path / 'state'
    models = state / 'models'
    month = state / 'forcing-captures' / '2026-09'
    output_dir = tmp_path / 'output'
    for directory in (state, state / 'forcing-captures', models, month, output_dir):
        directory.mkdir(parents=True, mode=0o700)
        directory.chmod(0o700)
    paths = bundle._paths((Path(__file__).resolve().parents[2]
                           / 'openhab/scripts/thermal_intel.py').read_bytes())
    entries = {}
    for name in paths:
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (f'RUNTIME_REVISION_PATHS = {paths!r}\n'.encode()
                if name == 'thermal_intel.py' else f'# {name}\n'.encode())
        path.write_bytes(data)
        entries['code/' + name] = data
    verifier = runtime / 'thermal_model/forcing_capture.py'
    verifier.write_bytes(b'# capture verifier\n')
    accepted = bundle._revision(paths, entries)
    artifact = models / 'accepted.json'
    artifact.write_text(json.dumps({'code_revision': accepted}))
    artifact.chmod(0o600)
    capture = month / '20260928T000000Z-0123456789abcdef.json.gz'
    capture.write_bytes(b'private capture bytes')
    capture.chmod(0o600)
    return runtime, state, output_dir / 'replay.tar.gz', accepted


def test_private_roundtrip_binds_accepted_runtime_and_captures(tmp_path):
    runtime, state, output, accepted = fixture(tmp_path)
    created = bundle.create(output, runtime_root=runtime, state_root=state)
    verified = bundle.verify(output)
    assert created == verified
    assert verified['accepted_code_revision'] == accepted
    assert verified['captures'] == 1
    assert output.stat().st_mode & 0o777 == 0o600
    with tarfile.open(output, 'r:gz') as archive:
        assert archive.getmember('code/thermal_model/forcing_capture.py').isfile()
    with pytest.raises(FileExistsError):
        bundle.create(output, runtime_root=runtime, state_root=state)


def test_mismatched_accepted_artifact_fails_without_output(tmp_path):
    runtime, state, output, _ = fixture(tmp_path)
    accepted = state / 'models/accepted.json'
    accepted.write_text(json.dumps({'code_revision': '0' * 64}))
    with pytest.raises(ValueError, match='does not match installed runtime'):
        bundle.create(output, runtime_root=runtime, state_root=state)
    assert not output.exists()
    assert not list(output.parent.glob('.thermal-replay-*'))


def test_verified_prior_bundle_can_preserve_accepted_code_after_runtime_change(tmp_path):
    runtime, state, prior, accepted = fixture(tmp_path)
    bundle.create(prior, runtime_root=runtime, state_root=state)
    old_dynamics = (runtime / 'thermal_model/dynamics.py').read_bytes()
    (runtime / 'thermal_model/dynamics.py').write_bytes(b'# training-only update\n')
    capture = state / 'forcing-captures/2026-09/20260928T020000Z-0123456789abcdef.json.gz'
    capture.write_bytes(b'new private capture bytes')
    capture.chmod(0o600)
    current = prior.parent / 'current.tar.gz'

    with pytest.raises(ValueError, match='does not match installed runtime'):
        bundle.create(current, runtime_root=runtime, state_root=state)
    assert not current.exists()
    created = bundle.create(current, runtime_root=runtime, state_root=state,
                            source_bundle=prior)
    assert created == bundle.verify(current)
    assert created['accepted_code_revision'] == accepted
    assert created['captures'] == 2
    with tarfile.open(current, 'r:gz') as archive:
        assert archive.extractfile('code/thermal_model/dynamics.py').read() == old_dynamics

    prior.chmod(0o644)
    assert bundle.verify(prior)['accepted_code_revision'] == accepted
    unprivate = prior.parent / 'unprivate.tar.gz'
    with pytest.raises(ValueError, match='unexpected source file'):
        bundle.create(unprivate, runtime_root=runtime, state_root=state,
                      source_bundle=prior)
    prior.chmod(0o600)

    (state / 'models/accepted.json').write_text(
        json.dumps({'code_revision': '0' * 64}))
    changed = prior.parent / 'changed.tar.gz'
    with pytest.raises(ValueError, match='does not match included runtime'):
        bundle.create(changed, runtime_root=runtime, state_root=state,
                      source_bundle=prior)
    assert not changed.exists()


def test_member_tampering_is_rejected(tmp_path):
    runtime, state, output, _ = fixture(tmp_path)
    bundle.create(output, runtime_root=runtime, state_root=state)
    altered = output.parent / 'altered.tar.gz'
    with tarfile.open(output, 'r:gz') as source, tarfile.open(altered, 'w:gz') as target:
        for member in source:
            data = source.extractfile(member).read()
            if member.name == 'state/models/accepted.json':
                data += b' '
            copied = tarfile.TarInfo(member.name)
            copied.size = len(data)
            target.addfile(copied, io.BytesIO(data))
    with pytest.raises(ValueError, match='digest mismatch'):
        bundle.verify(altered)
