import importlib.util
import json
import os
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


class SimulatedCrash(BaseException):
    pass


@pytest.mark.parametrize(
    ("event", "failure_index"),
    (
        ("before-replace", 1),
        ("before-parent-fsync", 1),
        ("before-final-verify", -1),
    ),
)
def test_install_failure_automatically_restores_completed_targets(
    tmp_path, event, failure_index,
):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def fail(observed, index):
        if observed == event and index == failure_index:
            raise RuntimeError(f"injected {event}")

    with pytest.raises(RuntimeError, match=f"injected {event}"):
        thermal_model_files.install_phase(
            repo, receipt, "code", manifest=manifest, fault=fail,
        )

    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert mode(tmp_path / "live/one.py") == 0o640
    assert not (tmp_path / "live/pkg/two.py").exists()
    phase = json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())
    assert phase["status"] == "rolled-back"


@pytest.mark.parametrize("crash_event", ("before-replace", "after-replace"))
def test_crash_requires_explicit_recovery_and_reconciles_intent(
    tmp_path, crash_event,
):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def crash(event, index):
        if event == crash_event and index == 0:
            raise SimulatedCrash(event)

    with pytest.raises(SimulatedCrash):
        thermal_model_files.install_phase(
            repo, receipt, "code", manifest=manifest, fault=crash,
        )

    with pytest.raises(RuntimeError, match="explicit recovery required"):
        thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    assert thermal_model_files.recover(repo, receipt, manifest=manifest)
    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert mode(tmp_path / "live/one.py") == 0o640
    assert not (tmp_path / "live/pkg/two.py").exists()
    phase = json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())
    assert phase["status"] == "rolled-back"


def test_restore_refuses_unowned_drift_before_changing_any_target(tmp_path):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)
    (tmp_path / "live/pkg/two.py").write_bytes(b"unowned-drift")

    with pytest.raises(RuntimeError, match="unowned target drift"):
        thermal_model_files.restore(repo, receipt, manifest=manifest)

    assert (tmp_path / "live/one.py").read_bytes() == b"one-new"
    assert (tmp_path / "live/pkg/two.py").read_bytes() == b"unowned-drift"


def test_secure_directory_rejects_symlink_ancestors_and_finals(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    ancestor = tmp_path / "ancestor"
    ancestor.symlink_to(real, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink"):
        thermal_model_files.secure_directory(ancestor / "child", 0o700, create=True)

    final_target = tmp_path / "final-target"
    final_target.mkdir()
    final_link = tmp_path / "final-link"
    final_link.symlink_to(final_target, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        thermal_model_files.secure_directory(final_link, 0o700, create=False)


def test_secure_directory_fsyncs_each_new_parent_and_directory(
    tmp_path, monkeypatch,
):
    events = []
    real_mkdir = os.mkdir
    real_fsync = os.fsync

    def recording_mkdir(path, mode=0o777, *, dir_fd=None):
        events.append(("mkdir", str(path)))
        return real_mkdir(path, mode, dir_fd=dir_fd)

    def recording_fsync(fd):
        events.append(("fsync", fd))
        return real_fsync(fd)

    monkeypatch.setattr(thermal_model_files.os, "mkdir", recording_mkdir)
    monkeypatch.setattr(thermal_model_files.os, "fsync", recording_fsync)
    thermal_model_files.secure_directory(
        tmp_path / "nested/receipt/files", 0o700, create=True,
    )

    mkdir_positions = [index for index, item in enumerate(events) if item[0] == "mkdir"]
    assert len(mkdir_positions) == 3
    for offset, position in enumerate(mkdir_positions):
        next_position = (
            mkdir_positions[offset + 1]
            if offset + 1 < len(mkdir_positions)
            else len(events)
        )
        assert sum(item[0] == "fsync" for item in events[position:next_position]) >= 2


def test_secure_directory_stops_after_directory_fsync_failure(
    tmp_path, monkeypatch,
):
    real_mkdir = os.mkdir
    real_fsync = os.fsync
    created = {"value": False}

    def recording_mkdir(path, mode=0o777, *, dir_fd=None):
        created["value"] = True
        return real_mkdir(path, mode, dir_fd=dir_fd)

    def failing_fsync(fd):
        if created["value"]:
            raise OSError("injected directory fsync")
        return real_fsync(fd)

    monkeypatch.setattr(thermal_model_files.os, "mkdir", recording_mkdir)
    monkeypatch.setattr(thermal_model_files.os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="injected directory fsync"):
        thermal_model_files.secure_directory(
            tmp_path / "first/second", 0o700, create=True,
        )
    assert not (tmp_path / "first/second").exists()


@pytest.mark.parametrize("link_kind", ("source-final", "source-ancestor", "target-final"))
def test_snapshot_rejects_symlink_sources_ancestors_and_targets(
    tmp_path, link_kind,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    live = tmp_path / "live"
    live.mkdir()
    source_name = "one.py"
    target = live / "one.py"

    if link_kind == "source-final":
        real_source = repo / "real.py"
        real_source.write_bytes(b"new")
        (repo / source_name).symlink_to(real_source)
    elif link_kind == "source-ancestor":
        source_root = tmp_path / "source-root"
        source_root.mkdir()
        (source_root / "one.py").write_bytes(b"new")
        (repo / "linked").symlink_to(source_root, target_is_directory=True)
        source_name = "linked/one.py"
    else:
        (repo / source_name).write_bytes(b"new")
        real_target = live / "real.py"
        real_target.write_bytes(b"old")
        target.symlink_to(real_target)

    manifest = (
        {"source": source_name, "target": str(target), "phase": "code", "mode": 0o644},
    )
    with pytest.raises(RuntimeError, match="symlink"):
        thermal_model_files.capture_backup(
            repo, tmp_path / f"receipt-{link_kind}", manifest=manifest,
        )



def test_later_real_exchange_failure_automatically_rolls_back(tmp_path, monkeypatch):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    real_renameat2 = thermal_model_files._renameat2

    def failing_exchange(old_fd, old_name, new_fd, new_name, flags):
        if new_name == "two.py":
            raise OSError("injected later exchange")
        return real_renameat2(old_fd, old_name, new_fd, new_name, flags)

    monkeypatch.setattr(thermal_model_files, "_renameat2", failing_exchange)
    with pytest.raises(OSError, match="injected later exchange"):
        thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert mode(tmp_path / "live/one.py") == 0o640
    assert not (tmp_path / "live/pkg/two.py").exists()
    assert json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())["status"] == "rolled-back"


def test_later_real_parent_fsync_failure_automatically_rolls_back(tmp_path, monkeypatch):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    real_renameat2 = thermal_model_files._renameat2
    real_fsync = os.fsync
    fail_next_target_parent_fsync = {"value": False}

    def recording_exchange(old_fd, old_name, new_fd, new_name, flags):
        result = real_renameat2(old_fd, old_name, new_fd, new_name, flags)
        if new_name == "two.py":
            fail_next_target_parent_fsync["value"] = True
        return result

    def failing_fsync(descriptor):
        if fail_next_target_parent_fsync["value"]:
            fail_next_target_parent_fsync["value"] = False
            raise OSError("injected later parent fsync")
        return real_fsync(descriptor)

    monkeypatch.setattr(thermal_model_files, "_renameat2", recording_exchange)
    monkeypatch.setattr(thermal_model_files.os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="injected later parent fsync"):
        thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert mode(tmp_path / "live/one.py") == 0o640
    assert not (tmp_path / "live/pkg/two.py").exists()
    assert json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())["status"] == "rolled-back"


def test_source_swap_to_symlink_after_prevalidation_is_refused(tmp_path, monkeypatch):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    real_state_bytes = thermal_model_files._state_bytes
    swapped = {"value": False}

    def swap_then_read(repo_root, receipt_dir, record, state_name):
        if state_name == "desired" and record["source"] == "one.py" and not swapped["value"]:
            source = repo / "one.py"
            source.unlink()
            source.symlink_to(repo / "pkg/two.py")
            swapped["value"] = True
        return real_state_bytes(repo_root, receipt_dir, record, state_name)

    monkeypatch.setattr(thermal_model_files, "_state_bytes", swap_then_read)
    with pytest.raises(RuntimeError, match="symlink"):
        thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"
    assert not (tmp_path / "live/pkg/two.py").exists()


def test_exchange_cas_refuses_existing_target_race_without_losing_drift(tmp_path):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / "live/one.py"
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def race(event, index):
        if event == "before-exchange" and index == 0:
            target.write_bytes(b"unowned-race")
            target.chmod(0o600)

    with pytest.raises(RuntimeError, match="unowned target drift"):
        thermal_model_files.install_phase(
            repo, receipt, "code", manifest=manifest, fault=race,
        )

    assert target.read_bytes() == b"unowned-race"
    assert mode(target) == 0o600


def test_noreplace_cas_refuses_absent_target_race_without_losing_drift(tmp_path):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / "live/pkg/two.py"
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def race(event, index):
        if event == "before-exchange" and index == 1:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"unowned-created-race")
            target.chmod(0o600)

    with pytest.raises(RuntimeError, match="unowned target drift"):
        thermal_model_files.install_phase(
            repo, receipt, "code", manifest=manifest, fault=race,
        )

    assert target.read_bytes() == b"unowned-created-race"
    assert mode(target) == 0o600
    assert (tmp_path / "live/one.py").read_bytes() == b"one-old"


@pytest.mark.parametrize(
    ("target_relative", "failure_index"),
    (("live/one.py", 0), ("live/pkg/two.py", 1)),
)
def test_restore_cas_refuses_replace_or_delete_race_without_losing_drift(
    tmp_path, target_relative, failure_index,
):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / target_relative
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    def race(event, index):
        if event == "before-exchange" and index == failure_index:
            target.write_bytes(b"unowned-restore-race")
            target.chmod(0o600)

    with pytest.raises(RuntimeError, match="unowned target drift"):
        thermal_model_files.restore(
            repo, receipt, manifest=manifest, fault=race,
        )

    assert target.read_bytes() == b"unowned-restore-race"
    assert mode(target) == 0o600


@pytest.mark.parametrize("crash_event", ("before-exchange", "after-exchange"))
def test_exchange_crash_journal_recovers_without_losing_original(
    tmp_path, crash_event,
):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / "live/one.py"
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def crash(event, index):
        if event == crash_event and index == 0:
            raise SimulatedCrash(event)

    with pytest.raises(SimulatedCrash):
        thermal_model_files.install_phase(
            repo, receipt, "code", manifest=manifest, fault=crash,
        )

    phase = json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())
    assert phase["entries"][0]["status"] == "intent"
    assert phase["entries"][0]["exchange_name"].startswith(
        ".one.py.thermal-exchange-"
    )
    assert thermal_model_files.recover(repo, receipt, manifest=manifest)
    assert target.read_bytes() == b"one-old"
    assert mode(target) == 0o640
    assert not list((tmp_path / "live").rglob("*.thermal-exchange-*"))


def test_install_external_delete_before_exchange_is_preserved_as_unowned_drift(
    tmp_path,
):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / "live/one.py"
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def delete_target(event, index):
        if event == "before-exchange" and index == 0:
            target.unlink()

    with pytest.raises(thermal_model_files.UnownedTargetDrift):
        thermal_model_files.install_phase(
            repo, receipt, "code", manifest=manifest, fault=delete_target,
        )

    assert not target.exists()
    phase = json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())
    assert phase["status"] == "recovery-required"
    assert phase["entries"][0]["status"] == "refused-unowned-drift"
    assert not thermal_model_files.recover(repo, receipt, manifest=manifest)
    assert not target.exists()


@pytest.mark.parametrize(
    ("target_relative", "failure_index"),
    (("live/one.py", 0), ("live/pkg/two.py", 1)),
)
def test_restore_external_delete_before_exchange_never_recreates_absence(
    tmp_path, target_relative, failure_index,
):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / target_relative
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)
    thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)

    def delete_target(event, index):
        if event == "before-exchange" and index == failure_index:
            target.unlink()

    with pytest.raises(thermal_model_files.UnownedTargetDrift):
        thermal_model_files.restore(
            repo, receipt, manifest=manifest, fault=delete_target,
        )

    assert not target.exists()
    phase = json.loads((receipt / thermal_model_files.PHASE_STATE_NAME).read_text())
    assert phase["status"] == "recovery-required"
    refused = phase["entries"][failure_index]
    assert refused["status"] == "refused-unowned-drift"
    assert not thermal_model_files.recover(repo, receipt, manifest=manifest)
    assert not target.exists()
    if failure_index == 1:
        assert (tmp_path / "live/one.py").read_bytes() == b"one-new"
        assert mode(tmp_path / "live/one.py") == 0o755
        recovered_phase = json.loads(
            (receipt / thermal_model_files.PHASE_STATE_NAME).read_text()
        )
        assert recovered_phase["entries"][0]["status"] == "rolled-back"


def test_install_fails_closed_when_renameat2_is_unavailable(tmp_path, monkeypatch):
    repo = prepare(tmp_path)
    receipt = tmp_path / "private/files"
    manifest = fixture_manifest(tmp_path)
    target = tmp_path / "live/one.py"
    thermal_model_files.capture_backup(repo, receipt, manifest=manifest)

    def unavailable(*args, **kwargs):
        raise RuntimeError("renameat2 capability unavailable")

    monkeypatch.setattr(thermal_model_files, "_renameat2", unavailable, raising=False)
    with pytest.raises(RuntimeError, match="renameat2 capability unavailable"):
        thermal_model_files.install_phase(repo, receipt, "code", manifest=manifest)
    assert target.read_bytes() == b"one-old"
    assert mode(target) == 0o640

def test_cli_paths_are_fixed_to_reviewed_repo_and_private_receipt_root(tmp_path):
    valid_receipt = (
        thermal_model_files.ALLOWED_RECEIPT_ROOT / "attended-20260813" / "files"
    )
    thermal_model_files.validate_cli_paths(
        thermal_model_files.ALLOWED_REPO_ROOT, valid_receipt,
    )
    with pytest.raises(ValueError, match="fixed reviewed repository"):
        thermal_model_files.validate_cli_paths(tmp_path, valid_receipt)
    with pytest.raises(ValueError, match="private receipt root"):
        thermal_model_files.validate_cli_paths(
            thermal_model_files.ALLOWED_REPO_ROOT, tmp_path / "files",
        )
