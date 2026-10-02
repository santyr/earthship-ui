"""Durable candidate replay, never household publication or control evidence."""
from copy import deepcopy
import gzip
from hashlib import sha256
import json
import os

import pytest

from thermal_model import airflow_capture as archive
from thermal_model.airflow_artifact import canonical
from thermal_model.airflow_forecast import forecast_at_origin
import thermal_model.airflow_artifact as artifacts
from test_thermal_airflow_forecast import candidate, origin, rehash, run, weather, temperatures, actions


@pytest.fixture
def capture(candidate, origin):
    return run(candidate, origin)['capture']


@pytest.fixture
def root(tmp_path):
    path = tmp_path / 'captures'
    path.mkdir(mode=0o700)
    return path


def test_real_candidate_roundtrip_is_private_immutable_and_not_publication(root, capture):
    before = deepcopy(capture)
    ref = archive.archive_capture(root, capture)
    assert ref['scope'] == 'candidate_replay_not_publication_or_action_evidence'
    path = root / ref['relative_path']
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert archive.read_capture(root, ref) == json.loads(canonical(capture))
    assert capture == before
    at = path.stat().st_mtime_ns
    assert archive.archive_capture(root, capture) == ref
    assert path.stat().st_mtime_ns == at
    assert not list(root.rglob('.capture-*'))


def test_maximum_72_hour_capture_archives_and_replays_within_bounds(root, candidate, origin):
    value = forecast_at_origin(candidate, origin, horizon_hours=72,
        forecast_reader=weather, temperature_reader=temperatures, action_reader=actions)['capture']
    ref = archive.archive_capture(root, value)
    path = root / ref['relative_path']
    assert path.stat().st_size <= archive.MAX_COMPRESSED_BYTES
    assert len(canonical(value)) <= archive.MAX_DECODED_BYTES
    assert len(archive.read_capture(root, ref)['output']['trajectory']) == 864


def test_missing_root_is_not_implicitly_created(tmp_path, capture):
    path = tmp_path / 'missing'
    with pytest.raises(FileNotFoundError):
        archive.archive_capture(path, capture)
    assert not path.exists()


def test_invalid_output_with_recomputed_digest_refuses_before_archive_mutation(root, capture):
    capture['output']['trajectory'][0]['air_f'] += 1
    rehash(capture)
    with pytest.raises(ValueError, match='replay differs'):
        archive.archive_capture(root, capture)
    assert not list(root.iterdir())


@pytest.mark.parametrize('mode', [0o755, 0o770])
def test_public_root_refused_before_mutation(root, capture, mode):
    root.chmod(mode)
    with pytest.raises(ValueError, match='directory'):
        archive.archive_capture(root, capture)
    assert not list(root.iterdir())


def test_symlink_root_and_month_refused(tmp_path, root, capture):
    link = tmp_path / 'link'
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='directory'):
        archive.archive_capture(link, capture)
    month = root / capture['output']['origin'][:7]
    month.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='directory'):
        archive.archive_capture(root, capture)


@pytest.mark.parametrize('damage', ['path', 'origin', 'digest', 'archive_digest', 'scope', 'extra'])
def test_closed_reference_identity_rejects_substitution(root, capture, damage):
    ref = archive.archive_capture(root, capture)
    if damage == 'path': ref['relative_path'] = '../outside.json.gz'
    elif damage == 'origin': ref['origin'] = '2025-01-01T00:00:00+00:00'
    elif damage == 'digest': ref['capture_sha256'] = 'A' * 64
    elif damage == 'archive_digest': ref['archive_sha256'] = '0' * 64
    elif damage == 'scope': ref['scope'] = 'published'
    else: ref['published'] = True
    with pytest.raises(ValueError):
        archive.read_capture(root, ref)


@pytest.mark.parametrize('damage', ['symlink', 'public', 'hardlink', 'corrupt'])
def test_unsafe_existing_file_is_not_overwritten(root, capture, tmp_path, damage):
    ref = archive.archive_capture(root, capture)
    path = root / ref['relative_path']
    original = path.read_bytes()
    if damage == 'symlink':
        outside = tmp_path / 'outside'
        outside.write_bytes(original); outside.chmod(0o600)
        path.unlink(); path.symlink_to(outside)
    elif damage == 'public': path.chmod(0o644)
    elif damage == 'hardlink': os.link(path, tmp_path / 'alias')
    else: path.write_bytes(b'corrupt')
    with pytest.raises((ValueError, OSError)):
        archive.archive_capture(root, capture)
    with pytest.raises((ValueError, OSError)):
        archive.read_capture(root, ref)
    assert path.read_bytes() == (b'corrupt' if damage == 'corrupt' else original)
    assert not list(root.rglob('.capture-*'))


def test_failed_atomic_install_removes_only_owned_temporary_file(root, capture, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError('injected install failure')
    monkeypatch.setattr(archive.os, 'link', refuse)
    with pytest.raises(OSError, match='injected'):
        archive.archive_capture(root, capture)
    assert not list(root.rglob('*.gz'))
    assert not list(root.rglob('.capture-*'))


def test_final_directory_sync_follows_temporary_link_removal(root, capture, monkeypatch):
    sync = archive._sync_directory
    seen = []
    def track(path):
        seen.append((path, bool(list(path.glob('.capture-*')))))
        return sync(path)
    monkeypatch.setattr(archive, '_sync_directory', track)
    ref = archive.archive_capture(root, capture)
    assert seen[-1] == ((root / ref['relative_path']).parent, False)


def test_retry_after_failed_month_sync_reflushes_root(root, capture, monkeypatch):
    sync = archive._sync_directory
    seen = []
    def failing(path):
        raise OSError('injected root flush failure')
    monkeypatch.setattr(archive, '_sync_directory', failing)
    with pytest.raises(OSError, match='root flush'):
        archive.archive_capture(root, capture)
    assert not list(root.rglob('*.gz'))
    def track(path):
        seen.append(path)
        return sync(path)
    monkeypatch.setattr(archive, '_sync_directory', track)
    ref = archive.archive_capture(root, capture)
    assert root in seen
    assert archive.read_capture(root, ref)['sha256'] == capture['sha256']


def test_external_input_mutation_during_replay_cannot_change_archived_snapshot(root, capture, monkeypatch):
    before = json.loads(canonical(capture))
    replay = archive.replay_capture
    def changing(value, **kwargs):
        output = replay(value, **kwargs)
        capture['output']['trajectory'][0]['air_f'] += 1
        rehash(capture)
        return output
    monkeypatch.setattr(archive, 'replay_capture', changing)
    ref = archive.archive_capture(root, capture)
    assert archive.read_capture(root, ref) == before


def test_runtime_drift_during_replay_refuses_before_directory_creation(root, capture, monkeypatch):
    replay = archive.replay_capture
    manifest = artifacts.runtime_manifest
    def changing(value, **kwargs):
        output = replay(value, **kwargs)
        def changed(*args, **kwargs):
            result = manifest(*args, **kwargs)
            result['sha256'] = '0' * 64
            return result
        monkeypatch.setattr(artifacts, 'runtime_manifest', changed)
        return output
    monkeypatch.setattr(archive, 'replay_capture', changing)
    with pytest.raises(ValueError, match='runtime binding'):
        archive.archive_capture(root, capture)
    assert not list(root.iterdir())


@pytest.mark.parametrize('damage', ['duplicate', 'nonfinite', 'decoded_size', 'compressed_size', 'rehash_output'])
def test_bounded_strict_read_and_exact_replay(root, capture, damage):
    ref = archive.archive_capture(root, capture)
    path = root / ref['relative_path']
    if damage == 'duplicate':
        raw = canonical(capture)
        raw = b'{"schema":"duplicate",' + raw[1:]
    elif damage == 'nonfinite': raw = b'{"value":NaN}'
    elif damage == 'decoded_size': raw = b' ' * (archive.MAX_DECODED_BYTES + 1)
    elif damage == 'compressed_size':
        path.write_bytes(b' ' * (archive.MAX_COMPRESSED_BYTES + 1))
        ref['archive_sha256'] = sha256(path.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match='bounded'):
            archive.read_capture(root, ref)
        return
    else:
        capture['output']['trajectory'][0]['air_f'] += 1
        rehash(capture)
        raw = canonical(capture)
        ref['capture_sha256'] = capture['sha256']
        ref['relative_path'] = archive.relative_path(ref['origin'], ref['capture_sha256'])
        path = root / ref['relative_path']
    compressed = gzip.compress(raw, mtime=0)
    path.write_bytes(compressed); path.chmod(0o600)
    ref['archive_sha256'] = sha256(compressed).hexdigest()
    with pytest.raises(ValueError):
        archive.read_capture(root, ref)
