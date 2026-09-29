"""Paired private-state snapshot tests; no production state or journal access."""

from pathlib import Path
import sqlite3
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_confirmation as confirmation
import thermal_messaging as messaging
import thermal_state_backup as backup


def seeded_state(path):
    spool = confirmation.Spool(path)
    outbox = messaging.Outbox(path)
    try:
        for db, value in ((spool.db, 'private confirmation'),
                          (outbox.db, 'private delivery')):
            db.execute('CREATE TABLE backup_marker(value TEXT NOT NULL)')
            db.execute('INSERT INTO backup_marker VALUES (?)', (value,))
            db.commit()
    finally:
        outbox.close()
        spool.close()


def test_paired_snapshot_restores_both_sqlite_files(tmp_path, capsys):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    assert backup.main(['--snapshot', '--source-dir', str(source),
                        '--snapshot-dir', str(destination)]) == 0
    assert 'thermal_sqlite_pair_only_no_postgresql_journal' in capsys.readouterr().out
    assert backup.verify_snapshot(destination)['verified_files'] == 2
    for name, value in zip(backup.DATABASES, ('private confirmation', 'private delivery')):
        assert (destination / name).stat().st_mode & 0o077 == 0
        with sqlite3.connect(destination / name) as restored:
            assert restored.execute('SELECT value FROM backup_marker').fetchone() == (value,)
    assert (destination / 'manifest.json').stat().st_mode & 0o077 == 0
    restored_spool = confirmation.Spool(destination)
    restored_outbox = messaging.Outbox(destination)
    try:
        assert restored_spool.db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert restored_outbox.db.execute('PRAGMA user_version').fetchone()[0] == 3
    finally:
        restored_outbox.close()
        restored_spool.close()


def test_snapshot_refuses_busy_cli_state_before_creating_destination(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    with backup.state_lock(source):
        with pytest.raises(ValueError, match='busy'):
            backup.snapshot_state(source, destination)
    assert not destination.exists()
    backup.snapshot_state(source, destination)
    assert backup.verify_snapshot(destination)['verified_files'] == 2


def test_snapshot_detects_modified_copy_and_never_reuses_destination(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    backup.snapshot_state(source, destination)
    with pytest.raises(FileExistsError):
        backup.snapshot_state(source, destination)
    with (destination / 'delivery.sqlite3').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='digest mismatch'):
        backup.verify_snapshot(destination)


def test_state_lock_rejects_symlink_and_public_directory(tmp_path):
    source = tmp_path / 'state'
    source.mkdir(mode=0o700)
    outside = tmp_path / 'outside'
    outside.write_bytes(b'untouched')
    (source / 'state.lock').symlink_to(outside)
    with pytest.raises(OSError):
        with backup.state_lock(source):
            pass
    assert outside.read_bytes() == b'untouched'
    (source / 'state.lock').unlink()
    source.chmod(0o755)
    with pytest.raises(ValueError, match='private'):
        with backup.state_lock(source):
            pass


def test_snapshot_does_not_create_mistyped_source(tmp_path):
    source, destination = tmp_path / 'missing', tmp_path / 'snapshot'
    with pytest.raises(FileNotFoundError):
        backup.snapshot_state(source, destination)
    assert not source.exists() and not destination.exists()


def test_snapshot_does_not_leave_directory_for_missing_database(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    source.mkdir(mode=0o700)
    with pytest.raises(FileNotFoundError):
        backup.snapshot_state(source, destination)
    assert not destination.exists()


def test_snapshot_verifier_bounds_manifest_before_parsing(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    backup.snapshot_state(source, destination)
    (destination / 'manifest.json').write_bytes(b'x' * 4097)
    with pytest.raises(ValueError, match='exceeds bound'):
        backup.verify_snapshot(destination)


def test_snapshot_binds_private_policy_and_routes_without_exposing_contents(tmp_path, capsys):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    config = tmp_path / 'config'
    config.mkdir(mode=0o700)
    policy, routes = config / 'approved-policy.json', config / 'signed-routes.json'
    policy.write_bytes(b'{"operator":"fixture-private"}')
    routes.write_bytes(b'{"routes":"fixture-private"}')
    policy.chmod(0o600)
    routes.chmod(0o600)
    assert backup.main(['--snapshot', '--source-dir', str(source),
                        '--snapshot-dir', str(destination), '--policy', str(policy),
                        '--routes', str(routes)]) == 0
    output = capsys.readouterr().out
    assert 'fixture-private' not in output
    assert 'thermal_sqlite_pair_and_config_no_postgresql_journal' in output
    assert backup.verify_snapshot(destination)['verified_files'] == 4
    assert (destination / 'policy.json').read_bytes() == policy.read_bytes()
    assert (destination / 'routes.json').read_bytes() == routes.read_bytes()
    assert (destination / 'policy.json').stat().st_mode & 0o077 == 0
    with (destination / 'routes.json').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='digest mismatch'):
        backup.verify_snapshot(destination)


def test_config_snapshot_refuses_missing_pair_before_creating_destination(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    with pytest.raises(ValueError, match='together'):
        backup.snapshot_state(source, destination, policy=tmp_path / 'policy')
    assert not destination.exists()


@pytest.mark.parametrize('invalid', ['symlink', 'public', 'oversize'])
def test_config_snapshot_refuses_unsafe_source_before_creating_destination(tmp_path, invalid):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    config = tmp_path / 'config'
    config.mkdir(mode=0o700)
    policy, routes = config / 'policy.json', config / 'routes.json'
    policy.write_bytes(b'{"policy":"fixture"}')
    routes.write_bytes(b'{"routes":"fixture"}')
    policy.chmod(0o600)
    routes.chmod(0o600)
    if invalid == 'symlink':
        policy.unlink()
        policy.symlink_to(routes)
    elif invalid == 'public':
        policy.chmod(0o644)
    else:
        policy.write_bytes(b'x' * (backup.MAX_CONFIG_BYTES + 1))
    with pytest.raises(ValueError):
        backup.snapshot_state(source, destination, policy=policy, routes=routes)
    assert not destination.exists()


def test_journal_bundle_refuses_invalid_archive_without_manifest(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    config = tmp_path / 'config'
    config.mkdir(mode=0o700)
    policy, routes = config / 'policy.json', config / 'routes.json'
    policy.write_bytes(b'{"policy":"fixture"}')
    routes.write_bytes(b'{"routes":"fixture"}')
    policy.chmod(0o600)
    routes.chmod(0o600)

    def invalid_exporter(target):
        target.write_bytes(b'not a PostgreSQL custom archive')
        target.chmod(0o600)

    with pytest.raises(ValueError, match='archive structure invalid'):
        backup.snapshot_state(source, destination, policy=policy, routes=routes,
                              journal_exporter=invalid_exporter)
    assert destination.exists()  # Private failed snapshot is retained for inspection.
    assert not (destination / 'manifest.json').exists()
    with pytest.raises(FileNotFoundError):
        backup.verify_snapshot(destination)


def test_journal_bundle_requires_config_and_refuses_busy_state(tmp_path):
    source, destination = tmp_path / 'state', tmp_path / 'snapshot'
    seeded_state(source)
    with pytest.raises(ValueError, match='both config files'):
        backup.snapshot_state(source, destination, journal_exporter=lambda _: None)
    assert not destination.exists()
    config = tmp_path / 'config'
    config.mkdir(mode=0o700)
    policy, routes = config / 'policy.json', config / 'routes.json'
    policy.write_bytes(b'policy')
    routes.write_bytes(b'routes')
    policy.chmod(0o600)
    routes.chmod(0o600)
    called = False

    def exporter(_):
        nonlocal called
        called = True

    with backup.state_lock(source):
        with pytest.raises(ValueError, match='busy'):
            backup.snapshot_state(source, destination, policy=policy, routes=routes,
                                  journal_exporter=exporter)
    assert not called and not destination.exists()
