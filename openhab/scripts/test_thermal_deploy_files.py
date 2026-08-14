import importlib.util
from pathlib import Path
import stat

import pytest

import thermal_intel


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/thermal-model-files.py"
SPEC = importlib.util.spec_from_file_location("thermal_model_files", SCRIPT)
thermal_model_files = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(thermal_model_files)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def fixture_manifest(root):
    return (
        {"source": "verify.py", "target": str(root / "live/verify.py"), "phase": "verify", "mode": 0o644},
        {"source": "one.py", "target": str(root / "live/one.py"), "phase": "code", "mode": 0o755},
        {"source": "pkg/two.py", "target": str(root / "live/pkg/two.py"), "phase": "code", "mode": 0o644},
        {"source": "unit.service", "target": str(root / "units/unit.service"), "phase": "unit", "mode": 0o644},
    )


def prepare(root):
    repo = root / "repo"
    for relative, content in (
        ("verify.py", b"verify"),
        ("one.py", b"one-new"),
        ("pkg/two.py", b"two-new"),
        ("unit.service", b"unit-new"),
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "live").mkdir()
    (root / "live/verify.py").write_bytes(b"verify")
    (root / "live/one.py").write_bytes(b"one-old")
    (root / "live/one.py").chmod(0o640)
    return repo


def test_exact_manifest_contains_complete_runtime_and_four_units():
    entries = thermal_model_files.MANIFEST
    assert [entry["source"] for entry in entries if entry["phase"] == "verify"] == [
        "openhab/scripts/forecast_intel.py"
    ]
    assert [entry["source"] for entry in entries if entry["phase"] == "code"] == [
        "openhab/scripts/thermal_intel.py",
        *[
            f"openhab/scripts/thermal_model/{name}.py"
            for name in (
                "__init__", "actions", "artifacts", "behavior", "dataset",
                "dynamics", "evaluation", "journal", "pipeline", "schema",
            )
        ],
    ]
    deployed_runtime = tuple(
        entry["source"].removeprefix("openhab/scripts/")
        for entry in entries
        if entry["phase"] in {"verify", "code"}
    )
    assert len(deployed_runtime) == len(thermal_intel.RUNTIME_REVISION_PATHS)
    assert set(deployed_runtime) == set(thermal_intel.RUNTIME_REVISION_PATHS)
    assert [entry["source"] for entry in entries if entry["phase"] == "unit"] == [
        "deploy/thermal-model-train.service",
        "deploy/thermal-model-train.timer",
        "deploy/thermal-model-shadow.service",
        "deploy/thermal-model-shadow.timer",
    ]


def test_snapshot_install_and_restore_are_durable_exact_and_private(tmp_path):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)

    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    assert mode(receipt) == 0o700
    assert mode(receipt / "file-manifest.json") == 0o600
    assert all(mode(path) == 0o600 for path in (receipt / "backups").iterdir())
    assert list((receipt / "backups").glob("*.absent"))

    thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)
    assert (tmp_path / "live/one.py").read_bytes() == b"one-new"
    assert (tmp_path / "live/pkg/two.py").read_bytes() == b"two-new"
    assert mode(tmp_path / "live/one.py") == 0o755
    assert mode(tmp_path / "live/pkg/two.py") == 0o644
    assert thermal_model_files.verify_phase(repo, receipt, "code", manifest=manifest)
    assert not list((tmp_path / "live").rglob("*.thermal-stage-*"))

    thermal_model_files.install_phase(repo, receipt, "unit", manifest=manifest)
    assert thermal_model_files.verify_phase(repo, receipt, "unit", manifest=manifest)

    thermal_model_files.restore(receipt, manifest=manifest)
    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert mode(tmp_path / "live/one.py") == 0o640
    assert not (tmp_path / "live/pkg/two.py").exists()
    assert not (tmp_path / "units/unit.service").exists()
    assert (tmp_path / "live/verify.py").read_bytes() == b"verify"


def test_install_prevalidates_complete_phase_before_first_write(tmp_path):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    (repo / "pkg/two.py").unlink()

    with pytest.raises(RuntimeError, match="source unavailable"):
        thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert not (tmp_path / "live/pkg/two.py").exists()
