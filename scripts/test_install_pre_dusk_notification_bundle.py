"""Real temporary filesystem pointer-switch/rollback checks; no host install."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-pre-dusk-notification-bundle.py'))
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def fixture(tmp_path):
    source = tmp_path / 'bundle'
    source.mkdir(mode=0o700)
    receipt = installer.bundle.build(source)
    return source, receipt['manifest_sha256'], tmp_path / 'runtime'


def test_inactive_first_install_and_exact_initial_rollback(tmp_path):
    source, digest, root = fixture(tmp_path)
    result = installer.install(source, digest, root=root)
    assert result['status'] == 'installed_inactive_code'
    assert result['units_installed'] == result['messages_published'] == 0
    assert installer.current(root) == digest
    assert installer.bundle.verify(root / 'releases' / digest, digest)['files'] == 12
    assert installer.rollback(digest, None, root=root)['manifest_sha256'] is None
    assert not (root / 'current').is_symlink()
    assert (root / 'releases' / digest).is_dir()  # Retained operational recovery release.


def test_post_switch_failure_restores_prior_pointer(tmp_path):
    source, digest, root = fixture(tmp_path)
    def failing_probe(*args):
        raise ValueError('simulated post-switch failure')
    with pytest.raises(ValueError, match='simulated'):
        installer.install(source, digest, root=root, probe=failing_probe)
    assert installer.current(root) is None
    assert not list(root.glob('.pointer-*'))
    assert not list((root / 'releases').glob('.staging-*'))


def test_wrong_preimage_preserves_current_pointer(tmp_path):
    source, digest, root = fixture(tmp_path)
    installer.install(source, digest, root=root)
    with pytest.raises(ValueError, match='preimage'):
        installer.install(source, digest, expected_current=None, root=root)
    assert installer.current(root) == digest
    assert installer.install(source, digest, expected_current=digest, root=root)['status'] == 'installed_inactive_code'


def test_public_or_unknown_namespace_refuses(tmp_path):
    source, digest, root = fixture(tmp_path)
    root.mkdir(mode=0o700)
    foreign = root / 'user-file'
    foreign.write_bytes(b'preserve')
    with pytest.raises(ValueError, match='unknown'):
        installer.install(source, digest, root=root)
    assert foreign.read_bytes() == b'preserve'


def test_existing_bundle_corruption_refuses_without_pointer_replacement(tmp_path):
    source, digest, root = fixture(tmp_path)
    installer.install(source, digest, root=root)
    (root / 'releases' / digest / 'manifest.json').write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        installer.install(source, digest, expected_current=digest, root=root)
    assert (root / 'current').readlink() == Path('releases') / digest


def test_post_switch_corrupt_candidate_restores_empty_preimage(tmp_path):
    source, digest, root = fixture(tmp_path)
    def corrupt_probe(path, expected):
        (path / 'manifest.json').write_bytes(b'corrupt')
        installer.bundle.verify(path, expected)
    with pytest.raises(ValueError):
        installer.install(source, digest, root=root, probe=corrupt_probe)
    assert installer.current(root) is None


def test_failed_upgrade_restores_exact_previous_release(tmp_path):
    source, old_digest, root = fixture(tmp_path)
    installer.install(source, old_digest, root=root)
    # A harmless source-only revision creates a distinct inactive candidate.
    changed = source / 'pre_dusk_notification_cli.py'
    changed.write_bytes(changed.read_bytes() + b'\n# isolated upgrade fixture\n')
    next_bundle = tmp_path / 'next'
    next_bundle.mkdir(mode=0o700)
    next_digest = installer.bundle.build(next_bundle, source)['manifest_sha256']
    def fail(*args):
        raise ValueError('post-switch verification refused')
    with pytest.raises(ValueError):
        installer.install(next_bundle, next_digest, expected_current=old_digest, root=root, probe=fail)
    assert installer.current(root) == old_digest
    assert installer.bundle.verify(root / 'releases' / old_digest, old_digest)['files'] == 12


def test_concurrent_pointer_change_is_not_overwritten_by_error_rollback(tmp_path):
    source, digest, root = fixture(tmp_path)
    def concurrent_change(path, expected):
        installer.switch(root, digest, None)
        raise ValueError('another writer withdrew the pointer')
    with pytest.raises(ValueError, match='another writer'):
        installer.install(source, digest, root=root, probe=concurrent_change)
    assert installer.current(root) is None


def test_overlapping_installer_refuses_before_release_or_pointer_creation(tmp_path):
    source, digest, root = fixture(tmp_path)
    with installer.lock(root):
        with pytest.raises(BlockingIOError):
            installer.install(source, digest, root=root)
    assert installer.current(root) is None
    assert not (root / 'releases').exists()
