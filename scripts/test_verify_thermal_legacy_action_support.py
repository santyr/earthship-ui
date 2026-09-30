"""Read-only verifier CLI; no live services or household artifact fixtures."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/verify-thermal-legacy-action-support.py'
RUNTIME = ROOT/'openhab/scripts'


def invoke(digest, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), '--scripts-root', str(RUNTIME),
        '--expected-sha256', digest, *extra], capture_output=True, text=True, timeout=15)


def test_exact_source_tree_has_no_unsupported_legacy_support():
    digest = sha256((RUNTIME/'thermal_model/dataset.py').read_bytes()).hexdigest()
    result = invoke(digest, '--require-safe')
    assert result.returncode == 0
    proof = json.loads(result.stdout)
    assert proof['status'] == 'safe'
    assert proof['baseline_support_rows'] == proof['combined_support_rows'] == 1
    assert proof['unsupported_only_support_rows'] == 0
    assert proof['legacy_forcing_unchanged'] is True
    assert proof['dataset_sha256'] == digest
    assert len(proof['runtime_revision']) == len(proof['legacy_fixture_sha256']) == 64
    assert not result.stderr


def test_wrong_preimage_refuses_before_any_runtime_work():
    result = invoke('0'*64, '--require-safe')
    assert result.returncode == 1
    assert json.loads(result.stdout) == {'status': 'failed', 'error_type': 'ValueError'}
    assert not result.stderr


def test_missing_artifact_is_not_recovered_or_created(tmp_path):
    target = tmp_path/'accepted.json'
    digest = sha256((RUNTIME/'thermal_model/dataset.py').read_bytes()).hexdigest()
    result = invoke(digest, '--accepted', str(target))
    assert result.returncode == 1
    assert json.loads(result.stdout) == {'status': 'failed', 'error_type': 'FileNotFoundError'}
    assert list(tmp_path.iterdir()) == []
    assert not result.stderr
