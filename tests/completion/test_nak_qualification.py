"""Qualification harness unit tests; these do not execute nak cryptography."""
from hashlib import sha256
import importlib.util
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('nak_qualification', ROOT / 'scripts/qualify-thermal-nak.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def executable(tmp_path, mode=0o755):
    path = tmp_path / 'nak'
    path.write_bytes(b'test fixture -- never execute')
    path.chmod(mode)
    return path, sha256(path.read_bytes()).hexdigest()


def test_default_path_is_operator_selected_path():
    assert str(m.DEFAULT_NAK) == '/home/sat/.local/bin/nak'


def test_safe_binary_matches_explicit_pin(tmp_path):
    path, digest = executable(tmp_path)
    m.inspect_binary(path, digest)


@pytest.mark.parametrize('mode', [0o775, 0o777, 0o757, 0o644])
def test_unsafe_binary_modes_rejected(tmp_path, mode):
    path, digest = executable(tmp_path, mode)
    with pytest.raises(m.QualificationFailed, match='permissions'):
        m.inspect_binary(path, digest)


def test_symlink_rejected(tmp_path):
    path, digest = executable(tmp_path)
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(m.QualificationFailed, match='non-symlink'):
        m.inspect_binary(link, digest)


def test_changed_bytes_rejected(tmp_path):
    path, digest = executable(tmp_path)
    path.write_bytes(b'different binary')
    with pytest.raises(m.QualificationFailed, match='pin'):
        m.inspect_binary(path, digest)


def test_old_build_rejected_before_file_access():
    old = next(iter(m.thermal.UNQUALIFIED_NAK_SHA256))
    with pytest.raises(m.QualificationFailed, match='old nak'):
        m.inspect_binary(Path('/does-not-exist'), old)


def test_relative_path_rejected():
    with pytest.raises(m.QualificationFailed, match='absolute'):
        m.inspect_binary(Path('nak'), 'a' * 64)


def test_environment_excludes_household_secrets(monkeypatch):
    monkeypatch.setenv('THERMAL_DATABASE_URL', 'PRIVATE_DB')
    monkeypatch.setenv('NOSTR_SECRET_KEY', 'PRIVATE_NOSTR')
    monkeypatch.setenv('NOSTR_CLIENT_KEY', 'PRIVATE_CLIENT')
    monkeypatch.setenv('HTTP_PROXY', 'PRIVATE_PROXY')
    env = m.isolated_environment('/tmp/disposable')
    assert set(env) == {'PATH', 'HOME', 'XDG_CONFIG_HOME', 'LANG', 'NOSTR_SECRET_KEY'}
    assert env['NOSTR_SECRET_KEY'] == m.RECIPIENT_KEY
    assert not any('PRIVATE' in v for v in env.values())
    assert os.environ['NOSTR_SECRET_KEY'] == 'PRIVATE_NOSTR'


def test_timeout_is_not_a_successful_negative_crypto_check():
    def unavailable():
        raise m.thermal.Retryable('timeout')
    with pytest.raises(m.thermal.Retryable):
        m.expect_refused(unavailable, 'not refused')


def test_acceptance_is_a_failed_negative_check():
    with pytest.raises(m.QualificationFailed, match='not refused'):
        m.expect_refused(lambda: {}, 'not refused')


def test_actual_refusal_is_required():
    def refusal():
        raise m.thermal.Refused('invalid signature')
    m.expect_refused(refusal, 'not refused')


def test_cli_failure_does_not_claim_qualification(monkeypatch, capsys):
    def failed(*args):
        raise m.QualificationFailed('pin mismatch')
    monkeypatch.setattr(m, 'qualify', failed)
    assert m.main(['--sha256', 'a' * 64]) == 1
    assert '"status": "failed"' in capsys.readouterr().out


def test_cli_operational_failure_is_sanitized(monkeypatch, capsys):
    def failed(*args):
        raise OSError('PRIVATE_SENTINEL')
    monkeypatch.setattr(m, 'qualify', failed)
    assert m.main(['--sha256', 'a' * 64]) == 2
    output = capsys.readouterr().out
    assert 'PRIVATE_SENTINEL' not in output
    assert '"status": "incomplete"' in output


def test_reviewed_pins_are_fixed_not_discovered_from_host(monkeypatch):
    monkeypatch.setattr(m.sys, 'platform', 'linux')
    monkeypatch.setattr(m.platform, 'machine', lambda: 'x86_64')
    assert m.release_digest() == 'ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e'
    monkeypatch.setattr(m.platform, 'machine', lambda: 'unknown')
    with pytest.raises(m.QualificationFailed, match='architecture'):
        m.release_digest()
