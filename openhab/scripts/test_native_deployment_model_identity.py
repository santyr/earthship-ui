"""Deployment-only changes must not reset a verified model's score lineage."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import pytest
from test_native_thermal_artifact import candidate, originals, api


def build(previous, paths, runtime, now):
    import household_native_training as training
    return training.build_deployment_candidate(originals=paths, runtime=runtime,
        previous=previous, created_at=now, guard=lambda: None)


def test_unchanged_model_and_runtime_keep_original_identity(tmp_path, originals):
    previous, paths, runtime, now = candidate(tmp_path, originals)
    assert build(previous, paths, runtime, now+timedelta(days=1)) == previous


def test_changed_runtime_gets_new_model_identity(tmp_path, originals):
    previous, paths, runtime, now = candidate(tmp_path, originals)
    runtime = deepcopy(runtime)
    runtime['native_source_manifest']['openhab/scripts/native_thermal_live.py'] = 'e'*64
    runtime['native_code_revision'] = api().digest(runtime['native_source_manifest'])
    result = build(previous, paths, runtime, now+timedelta(days=1))
    assert result['artifact_sha256'] != previous['artifact_sha256']
    assert result['created_at'] != previous['created_at']


def test_new_original_evidence_gets_new_model_identity(tmp_path, originals):
    previous, paths, runtime, now = candidate(tmp_path, originals)
    evidence = tmp_path/'new-fit.json'; evidence.write_bytes(paths['fit_evidence'].read_bytes()); evidence.chmod(0o600)
    result = build(previous, dict(paths, fit_evidence=evidence), runtime, now+timedelta(days=1))
    assert result['artifact_sha256'] != previous['artifact_sha256']


def test_prior_model_corruption_is_not_reused(tmp_path, originals):
    previous, paths, runtime, now = candidate(tmp_path, originals)
    previous['artifact_sha256'] = '0'*64
    with pytest.raises(ValueError, match='previous model'):
        build(previous, paths, runtime, now+timedelta(days=1))
