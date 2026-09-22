"""Local refusal-policy checks, not tests of the installed nak cryptography."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "nak_policy_thermal", ROOT / "openhab/scripts/thermal_confirmation.py"
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
REPORTED_SHA256 = "56a97dd08b2a21a7fe4989ebdf321af4ae1a34ec26c5aa195f9a386dfec0ef80"


def no_child(*args, **kwargs):
    pytest.fail("refused binary must not be executed")


@pytest.mark.parametrize("mode", [0o755, 0o775])
def test_reported_build_is_refused_even_after_permission_repair(tmp_path, mode):
    executable = tmp_path / "nak"
    executable.write_bytes(b"test placeholder, never executed")
    executable.chmod(mode)
    # Refuse the configured fingerprint before reading or executing the binary.
    with pytest.raises(m.Refused, match="build is not qualified"):
        m.NakDecoder(executable, REPORTED_SHA256, runner=no_child)


def test_different_configured_pin_does_not_bypass_hash_check(tmp_path):
    executable = tmp_path / "nak"
    executable.write_bytes(b"test placeholder, never executed")
    executable.chmod(0o755)
    decoder = m.NakDecoder(executable, "a" * 64, runner=no_child)
    with pytest.raises(m.Refused, match="hash mismatch"):
        decoder.decode(b"{}", "b" * 64)


def test_group_writable_binary_is_refused_with_matching_pin(tmp_path):
    executable = tmp_path / "nak"
    data = b"test placeholder, never executed"
    executable.write_bytes(data)
    executable.chmod(0o775)
    decoder = m.NakDecoder(executable, sha256(data).hexdigest(), runner=no_child)
    with pytest.raises(m.Refused, match="ownership or mode is unsafe"):
        decoder.decode(b"{}", "b" * 64)
