import fcntl
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
                "dynamics", "evaluation", "journal", "pipeline", "schema", "solar",
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


def test_prepare_private_directories_creates_all_receipt_roots(tmp_path):
    state_root = tmp_path / "state"
    evidence_root = tmp_path / "receipts/attended"
    item_receipt = evidence_root / "item"
    file_receipt = evidence_root / "files"

    thermal_model_files.prepare_private_directories(
        state_root, evidence_root, item_receipt, file_receipt
    )

    expected = (
        state_root,
        state_root / "models",
        state_root / "review",
        state_root / "evidence",
        evidence_root,
        item_receipt,
        evidence_root / "photosensor",
        file_receipt,
    )
    assert all(path.is_dir() and mode(path) == 0o700 for path in expected)


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


PRIOR_V3_ARCHIVE_FILES = {
    "candidate-v3.json",
    "backtest-report-v1.json",
    "prior-evidence-manifest.json",
}


def _prior_v3_payload(schema, *, eligible=False, marker):
    return thermal_model_files._canonical(
        {
            "fixture": marker,
            "metrics": {"promotion": {"eligible": eligible}},
            "schema": schema,
        }
    ) + b"\n"


def _prior_v3_fixture(tmp_path, monkeypatch):
    source_root = tmp_path / "models"
    attended_receipt = tmp_path / "receipts" / "attended-test"
    file_receipt = attended_receipt / "files"
    source_root.mkdir(mode=0o700)
    file_receipt.mkdir(parents=True, mode=0o700)
    attended_receipt.chmod(0o700)
    file_receipt.chmod(0o700)

    candidate = _prior_v3_payload(
        "earthship-thermal-model/v3", marker="candidate",
    )
    report = _prior_v3_payload(
        "earthship-thermal-backtest/v1", marker="report",
    )
    payloads = {
        "candidate.json": candidate,
        "backtest-report.json": report,
    }
    for name, data in payloads.items():
        path = source_root / name
        path.write_bytes(data)
        path.chmod(0o600)

    evidence = (
        {
            "sourceName": "candidate.json",
            "archivedName": "candidate-v3.json",
            "sourceSchema": "earthship-thermal-model/v3",
            "sha256": thermal_model_files._digest(candidate),
            "mode": "0600",
        },
        {
            "sourceName": "backtest-report.json",
            "archivedName": "backtest-report-v1.json",
            "sourceSchema": "earthship-thermal-backtest/v1",
            "sha256": thermal_model_files._digest(report),
            "mode": "0600",
        },
    )
    monkeypatch.setattr(
        thermal_model_files, "PRIOR_V3_SOURCE_ROOT", source_root, raising=False,
    )
    monkeypatch.setattr(
        thermal_model_files, "PRIOR_V3_EVIDENCE", evidence, raising=False,
    )
    return {
        "archive": attended_receipt / "prior-model-v3",
        "attended": attended_receipt,
        "evidence": evidence,
        "files": file_receipt,
        "payloads": payloads,
        "source_root": source_root,
    }


def _expected_prior_v3_manifest(fixture):
    return {
        "schema": "earthship-thermal-prior-evidence/v1",
        "records": [
            {
                "archivedName": record["archivedName"],
                "sourcePath": str(
                    fixture["source_root"] / record["sourceName"]
                ),
                "sourceSchema": record["sourceSchema"],
                "sha256": record["sha256"],
                "mode": "0600",
            }
            for record in fixture["evidence"]
        ],
    }


def _replace_prior_source(fixture, source_name, value):
    data = value if isinstance(value, bytes) else thermal_model_files._canonical(value) + b"\n"
    path = fixture["source_root"] / source_name
    path.write_bytes(data)
    path.chmod(0o600)
    for record in fixture["evidence"]:
        if record["sourceName"] == source_name:
            record["sha256"] = thermal_model_files._digest(data)
            break


def _assert_exact_prior_v3_archive(fixture):
    archive = fixture["archive"]
    assert archive.is_dir()
    assert mode(archive) == 0o700
    assert {path.name for path in archive.iterdir()} == PRIOR_V3_ARCHIVE_FILES
    assert (archive / "candidate-v3.json").read_bytes() == fixture["payloads"][
        "candidate.json"
    ]
    assert (archive / "backtest-report-v1.json").read_bytes() == fixture[
        "payloads"
    ]["backtest-report.json"]
    assert all(mode(path) == 0o600 for path in archive.iterdir())
    expected_manifest = _expected_prior_v3_manifest(fixture)
    assert json.loads(
        (archive / "prior-evidence-manifest.json").read_bytes()
    ) == expected_manifest
    assert (
        archive / "prior-evidence-manifest.json"
    ).read_bytes() == thermal_model_files._canonical(expected_manifest) + b"\n"


def test_archive_prior_v3_has_exact_pinned_production_manifest():
    assert thermal_model_files.PRIOR_V3_SOURCE_ROOT == Path(
        "/home/sat/.local/state/thermal-intel/models"
    )
    assert thermal_model_files.PRIOR_V3_ARCHIVE_NAME == "prior-model-v3"
    assert (
        thermal_model_files.PRIOR_V3_MANIFEST_NAME
        == "prior-evidence-manifest.json"
    )
    assert thermal_model_files._prior_v3_manifest() == {
        "schema": "earthship-thermal-prior-evidence/v1",
        "records": [
            {
                "archivedName": "candidate-v3.json",
                "sourcePath": "/home/sat/.local/state/thermal-intel/models/candidate.json",
                "sourceSchema": "earthship-thermal-model/v3",
                "sha256": "6d68639f426274d67a72d2ae45478f987af34dfdf0ae4675bc868c7f79f204fe",
                "mode": "0600",
            },
            {
                "archivedName": "backtest-report-v1.json",
                "sourcePath": "/home/sat/.local/state/thermal-intel/models/backtest-report.json",
                "sourceSchema": "earthship-thermal-backtest/v1",
                "sha256": "1c504fc3b37c945af990a368d3483c5c5a69fc985e4d76ddcf6d3eaf277b211f",
                "mode": "0600",
            },
        ],
    }


def test_archive_prior_v3_writes_exact_private_bytes_and_never_fallbacks(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    registry = fixture["source_root"] / "registry.json"
    registry.write_bytes(b"registry-must-not-change\n")
    registry.chmod(0o600)

    assert thermal_model_files.archive_prior_v3(fixture["files"])

    _assert_exact_prior_v3_archive(fixture)
    assert registry.read_bytes() == b"registry-must-not-change\n"
    manifest = json.loads(
        (fixture["archive"] / "prior-evidence-manifest.json").read_text()
    )
    assert "fallback" not in manifest


@pytest.mark.parametrize(
    "corruption",
    (
        "missing",
        "non-regular",
        "source-final-symlink",
        "source-ancestor-symlink",
        "wrong-mode",
        "wrong-hash",
        "invalid-json",
        "wrong-schema",
        "eligible-true",
        "eligible-missing",
        "eligible-zero",
    ),
)
@pytest.mark.parametrize("source_name", ("candidate.json", "backtest-report.json"))
def test_archive_prior_v3_prevalidates_both_sources_before_destination_mutation(
    tmp_path, monkeypatch, corruption, source_name,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    source = fixture["source_root"] / source_name

    if corruption == "missing":
        source.unlink()
    elif corruption == "non-regular":
        source.unlink()
        source.mkdir()
    elif corruption == "source-final-symlink":
        real = fixture["source_root"] / f"real-{source_name}"
        real.write_bytes(fixture["payloads"][source_name])
        real.chmod(0o600)
        source.unlink()
        source.symlink_to(real)
    elif corruption == "source-ancestor-symlink":
        real_root = tmp_path / "real-models"
        fixture["source_root"].rename(real_root)
        fixture["source_root"].symlink_to(real_root, target_is_directory=True)
    elif corruption == "wrong-mode":
        source.chmod(0o640)
    elif corruption == "wrong-hash":
        source.write_bytes(b"changed after evidence pin\n")
        source.chmod(0o600)
    elif corruption == "invalid-json":
        _replace_prior_source(fixture, source_name, b"not-json\n")
    else:
        document = json.loads(source.read_bytes())
        if corruption == "wrong-schema":
            document["schema"] = "wrong-thermal-schema/v0"
        elif corruption == "eligible-true":
            document["metrics"]["promotion"]["eligible"] = True
        elif corruption == "eligible-missing":
            del document["metrics"]["promotion"]["eligible"]
        else:
            document["metrics"]["promotion"]["eligible"] = 0
        _replace_prior_source(fixture, source_name, document)

    with pytest.raises((RuntimeError, ValueError)):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert not fixture["archive"].exists()
    assert not list(fixture["attended"].glob(".prior-model-v3.thermal-archive-*"))


@pytest.mark.parametrize("link_kind", ("files", "attended"))
def test_archive_prior_v3_rejects_symlink_receipt_components(
    tmp_path, monkeypatch, link_kind,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    if link_kind == "files":
        real_files = tmp_path / "real-files"
        fixture["files"].rename(real_files)
        fixture["files"].symlink_to(real_files, target_is_directory=True)
    else:
        real_attended = tmp_path / "real-attended"
        fixture["attended"].rename(real_attended)
        fixture["attended"].symlink_to(real_attended, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink"):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert not fixture["archive"].exists()


@pytest.mark.parametrize("existing_shape", ("missing-file", "unknown-extra"))
def test_prior_model_existing_incomplete_or_extended_archive_is_never_accepted(
    tmp_path, monkeypatch, existing_shape,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    archive = fixture["archive"]
    archive.mkdir(mode=0o700)
    sentinel = archive / "candidate-v3.json"
    sentinel.write_bytes(b"existing-must-survive\n")
    sentinel.chmod(0o600)
    if existing_shape == "unknown-extra":
        extra = archive / "unexpected.json"
        extra.write_bytes(b"foreign\n")
        extra.chmod(0o600)
    before = {path.name: path.read_bytes() for path in archive.iterdir()}

    with pytest.raises(RuntimeError, match="archive already exists"):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert {path.name: path.read_bytes() for path in archive.iterdir()} == before


@pytest.mark.parametrize(
    ("event", "failure_index"),
    (
        ("after-file-write", 0),
        ("after-file-write", 1),
        ("after-file-write", 2),
        ("after-directory-fsync", -1),
    ),
)
def test_archive_prior_v3_ordinary_failure_cleans_only_owned_temporary(
    tmp_path, monkeypatch, event, failure_index,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)

    def fail(observed, index):
        if observed == event and index == failure_index:
            raise RuntimeError(f"injected {event} {index}")

    with pytest.raises(RuntimeError, match=f"injected {event}"):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=fail)

    assert not fixture["archive"].exists()
    assert not list(fixture["attended"].glob(".prior-model-v3.thermal-archive-*"))


@pytest.mark.parametrize(
    ("event", "failure_index"),
    (
        ("after-file-write", 0),
        ("after-file-write", 1),
        ("after-file-write", 2),
        ("after-directory-fsync", -1),
    ),
)
def test_archive_prior_v3_crash_recovers_only_verifiable_owned_temporary(
    tmp_path, monkeypatch, event, failure_index,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)

    def crash(observed, index):
        if observed == event and index == failure_index:
            raise SimulatedCrash(f"{event} {index}")

    with pytest.raises(SimulatedCrash):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=crash)

    assert not fixture["archive"].exists()
    assert len(
        list(fixture["attended"].glob(".prior-model-v3.thermal-archive-*"))
    ) == 1

    assert thermal_model_files.archive_prior_v3(fixture["files"])
    _assert_exact_prior_v3_archive(fixture)
    assert not list(fixture["attended"].glob(".prior-model-v3.thermal-archive-*"))


def test_prior_model_recovery_refuses_unverifiable_foreign_temporary(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    foreign = fixture["attended"] / (
        ".prior-model-v3.thermal-archive-" + "0" * 24
    )
    foreign.mkdir(mode=0o700)
    unknown = foreign / "unknown"
    unknown.write_bytes(b"not helper owned\n")
    unknown.chmod(0o600)

    with pytest.raises(RuntimeError, match="unverifiable prior archive temporary"):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert unknown.read_bytes() == b"not helper owned\n"
    assert not fixture["archive"].exists()


def test_archive_prior_v3_uses_confined_noreplace_and_fsyncs_parent(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    real_renameat2 = thermal_model_files._renameat2
    real_fsync = os.fsync
    renames = []
    parent_fsync_after_publish = []

    def recording_rename(old_fd, old_name, new_fd, new_name, flags):
        renames.append((old_fd, old_name, new_fd, new_name, flags))
        return real_renameat2(old_fd, old_name, new_fd, new_name, flags)

    def recording_fsync(descriptor):
        if fixture["archive"].exists():
            parent_fsync_after_publish.append(
                os.fstat(descriptor).st_ino == fixture["attended"].stat().st_ino
            )
        return real_fsync(descriptor)

    monkeypatch.setattr(thermal_model_files, "_renameat2", recording_rename)
    monkeypatch.setattr(thermal_model_files.os, "fsync", recording_fsync)

    assert thermal_model_files.archive_prior_v3(fixture["files"])

    assert len(renames) == 1
    old_fd, old_name, new_fd, new_name, flags = renames[0]
    assert old_fd == new_fd
    assert old_name.startswith(".prior-model-v3.thermal-archive-")
    assert new_name == "prior-model-v3"
    assert flags == thermal_model_files._RENAME_NOREPLACE
    assert any(parent_fsync_after_publish)


def test_archive_prior_v3_noreplace_race_preserves_existing_destination(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    real_renameat2 = thermal_model_files._renameat2

    def race(old_fd, old_name, new_fd, new_name, flags):
        fixture["archive"].mkdir(mode=0o700)
        sentinel = fixture["archive"] / "foreign"
        sentinel.write_bytes(b"unowned-race\n")
        sentinel.chmod(0o600)
        return real_renameat2(old_fd, old_name, new_fd, new_name, flags)

    monkeypatch.setattr(thermal_model_files, "_renameat2", race)
    with pytest.raises(RuntimeError, match="archive already exists"):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert (fixture["archive"] / "foreign").read_bytes() == b"unowned-race\n"
    assert not list(fixture["attended"].glob(".prior-model-v3.thermal-archive-*"))


def test_archive_prior_v3_failure_after_rename_exposes_only_complete_archive(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)

    def fail(observed, index):
        if observed == "after-rename" and index == -1:
            raise RuntimeError("injected after rename")

    with pytest.raises(RuntimeError, match="injected after rename"):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=fail)

    _assert_exact_prior_v3_archive(fixture)
    before = {
        path.name: path.read_bytes() for path in fixture["archive"].iterdir()
    }
    with pytest.raises(RuntimeError, match="archive already exists"):
        thermal_model_files.archive_prior_v3(fixture["files"])
    assert {
        path.name: path.read_bytes() for path in fixture["archive"].iterdir()
    } == before


def test_prior_model_crash_after_rename_exposes_only_complete_archive(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)

    def crash(observed, index):
        if observed == "after-rename" and index == -1:
            raise SimulatedCrash("after rename")

    with pytest.raises(SimulatedCrash):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=crash)

    _assert_exact_prior_v3_archive(fixture)
    assert not list(fixture["attended"].glob(".prior-model-v3.thermal-archive-*"))
    with pytest.raises(RuntimeError, match="archive already exists"):
        thermal_model_files.archive_prior_v3(fixture["files"])


def test_archive_prior_v3_cli_dispatch_has_no_generic_source_option(monkeypatch):
    receipt = thermal_model_files.ALLOWED_RECEIPT_ROOT / "attended-test" / "files"
    observed = []
    monkeypatch.setattr(
        thermal_model_files,
        "archive_prior_v3",
        lambda receipt_dir: observed.append(receipt_dir) or True,
        raising=False,
    )

    thermal_model_files.main(
        ["archive-prior-v3", "--receipt-dir", str(receipt)]
    )
    assert observed == [receipt]

    with pytest.raises(SystemExit):
        thermal_model_files.main(
            [
                "archive-prior-v3",
                "--receipt-dir",
                str(receipt),
                "--source-root",
                "/tmp/not-allowed",
            ]
        )


def _write_complete_prior_v3_temporary(fixture, temporary):
    temporary.mkdir(mode=0o700)
    for archived_name, source_name in (
        ("candidate-v3.json", "candidate.json"),
        ("backtest-report-v1.json", "backtest-report.json"),
    ):
        path = temporary / archived_name
        path.write_bytes(fixture["payloads"][source_name])
        path.chmod(0o600)
    manifest = temporary / "prior-evidence-manifest.json"
    manifest.write_bytes(
        thermal_model_files._canonical(_expected_prior_v3_manifest(fixture))
        + b"\n"
    )
    manifest.chmod(0o600)


def test_prior_model_byte_identical_marker_free_foreign_temp_is_preserved(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    foreign = fixture["attended"] / (
        ".prior-model-v3.thermal-archive-" + "1" * 24
    )
    _write_complete_prior_v3_temporary(fixture, foreign)
    before = {path.name: path.read_bytes() for path in foreign.iterdir()}

    with pytest.raises(RuntimeError, match="unverifiable prior archive temporary"):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert foreign.is_dir()
    assert {path.name: path.read_bytes() for path in foreign.iterdir()} == before
    assert not fixture["archive"].exists()


def test_prior_model_deterministic_marker_without_receipt_proof_is_preserved(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    temporary_name = ".prior-model-v3.thermal-archive-" + "2" * 24
    foreign = fixture["attended"] / temporary_name
    foreign.mkdir(mode=0o700)
    marker = foreign / ".thermal-archive-owner"
    marker.write_bytes(
        thermal_model_files._canonical(
            {
                "schema": "earthship-thermal-prior-archive-temp/v1",
                "temporaryName": temporary_name,
            }
        )
        + b"\n"
    )
    marker.chmod(0o600)

    with pytest.raises(RuntimeError, match="unverifiable prior archive temporary"):
        thermal_model_files.archive_prior_v3(fixture["files"])

    assert marker.is_file()
    assert not fixture["archive"].exists()


def test_archive_prior_v3_attended_path_substitution_cannot_redirect_writes(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    moved_attended = tmp_path / "moved-attended"
    substituted = {"value": False}

    def substitute(event, index):
        if event == "after-file-write" and index == 0:
            fixture["attended"].rename(moved_attended)
            replacement_files = fixture["attended"] / "files"
            replacement_files.mkdir(parents=True, mode=0o700)
            fixture["attended"].chmod(0o700)
            replacement_files.chmod(0o700)
            substituted["value"] = True

    assert thermal_model_files.archive_prior_v3(
        fixture["files"], fault=substitute,
    )

    assert substituted["value"]
    moved_fixture = {**fixture, "archive": moved_attended / "prior-model-v3"}
    _assert_exact_prior_v3_archive(moved_fixture)
    assert list(fixture["attended"].iterdir()) == [fixture["files"]]


def test_archive_prior_v3_temp_substitution_cannot_redirect_later_writes(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    paths = {}

    def substitute(event, index):
        if event == "after-file-write" and index == 0:
            temporary = next(
                fixture["attended"].glob(".prior-model-v3.thermal-archive-*")
            )
            moved = fixture["attended"] / f"moved-{temporary.name}"
            temporary.rename(moved)
            temporary.mkdir(mode=0o700)
            paths.update(moved=moved, replacement=temporary)

    with pytest.raises(RuntimeError, match="temporary identity changed"):
        thermal_model_files.archive_prior_v3(
            fixture["files"], fault=substitute,
        )

    assert paths["replacement"].is_dir()
    assert not list(paths["replacement"].iterdir())
    assert {
        path.name for path in paths["moved"].iterdir()
    } == PRIOR_V3_ARCHIVE_FILES
    assert not fixture["archive"].exists()


def test_archive_prior_v3_temp_substitution_cannot_redirect_cleanup(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    paths = {}

    def substitute_and_fail(event, index):
        if event == "after-file-write" and index == 0:
            temporary = next(
                fixture["attended"].glob(".prior-model-v3.thermal-archive-*")
            )
            moved = fixture["attended"] / f"moved-{temporary.name}"
            temporary.rename(moved)
            temporary.mkdir(mode=0o700)
            paths.update(moved=moved, replacement=temporary)
            raise RuntimeError("injected after substitution")

    with pytest.raises(RuntimeError):
        thermal_model_files.archive_prior_v3(
            fixture["files"], fault=substitute_and_fail,
        )

    assert paths["replacement"].is_dir()
    assert not list(paths["replacement"].iterdir())
    assert (paths["moved"] / "candidate-v3.json").is_file()
    assert not fixture["archive"].exists()


def test_prior_model_crash_before_receipt_ownership_proof_is_preserved(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)

    def crash(event, index):
        if event == "after-temporary-open" and index == -1:
            raise SimulatedCrash("before receipt ownership proof")

    with pytest.raises(SimulatedCrash):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=crash)

    temporaries = list(
        fixture["attended"].glob(".prior-model-v3.thermal-archive-*")
    )
    assert len(temporaries) == 1
    assert not (
        fixture["files"] / ".prior-model-v3-archive-intent.json"
    ).exists()
    with pytest.raises(RuntimeError, match="unverifiable prior archive temporary"):
        thermal_model_files.archive_prior_v3(fixture["files"])
    assert temporaries[0].is_dir()


def test_prior_model_crash_records_random_receipt_bound_ownership_proof(
    tmp_path, monkeypatch,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)

    def crash(event, index):
        if event == "after-file-write" and index == 0:
            raise SimulatedCrash("after first file")

    with pytest.raises(SimulatedCrash):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=crash)

    temporary = next(
        fixture["attended"].glob(".prior-model-v3.thermal-archive-*")
    )
    intent_path = fixture["files"] / thermal_model_files.PRIOR_V3_INTENT_NAME
    intent = json.loads(intent_path.read_bytes())
    assert set(intent) == {
        "attendedDevice",
        "attendedInode",
        "filesDevice",
        "filesInode",
        "schema",
        "temporaryDevice",
        "temporaryInode",
        "temporaryName",
        "token",
    }
    assert intent["schema"] == "earthship-thermal-prior-archive-intent/v1"
    assert len(intent["token"]) == 64
    assert all(character in "0123456789abcdef" for character in intent["token"])
    assert intent["token"] not in temporary.name
    assert (intent["temporaryDevice"], intent["temporaryInode"]) == (
        temporary.stat().st_dev,
        temporary.stat().st_ino,
    )
    assert (intent["attendedDevice"], intent["attendedInode"]) == (
        fixture["attended"].stat().st_dev,
        fixture["attended"].stat().st_ino,
    )
    assert (intent["filesDevice"], intent["filesInode"]) == (
        fixture["files"].stat().st_dev,
        fixture["files"].stat().st_ino,
    )
    assert mode(intent_path) == 0o600

    assert thermal_model_files.archive_prior_v3(fixture["files"])
    _assert_exact_prior_v3_archive(fixture)
    assert not intent_path.exists()


@pytest.mark.parametrize("mutation", ("content", "mode", "extra"))
def test_archive_prior_v3_reverifies_held_temp_immediately_before_rename(
    tmp_path, monkeypatch, mutation,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    mutated = {}

    def mutate(event, index):
        if event != "before-final-archive-verify" or index != -1:
            return
        temporary = next(
            fixture["attended"].glob(".prior-model-v3.thermal-archive-*")
        )
        if mutation == "extra":
            target = temporary / "unexpected"
            target.write_bytes(b"unowned extra\n")
            target.chmod(0o600)
        else:
            target = temporary / "candidate-v3.json"
            if mutation == "content":
                target.write_bytes(b"mutated candidate\n")
                target.chmod(0o600)
            else:
                target.chmod(0o640)
        mutated["temporary"] = temporary

    with pytest.raises(RuntimeError, match="final prior archive temporary"):
        thermal_model_files.archive_prior_v3(fixture["files"], fault=mutate)

    assert not fixture["archive"].exists()
    assert mutated["temporary"].is_dir()


def test_archive_prior_v3_holds_receipt_lock_through_rename_and_parent_fsync(
    monkeypatch, tmp_path,
):
    fixture = _prior_v3_fixture(tmp_path, monkeypatch)
    real_renameat2 = thermal_model_files._renameat2
    real_fsync = os.fsync
    lock_was_held = {"rename": False, "parent-fsync": False}

    def assert_receipt_locked():
        contender = os.open(fixture["files"], os.O_RDONLY)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(contender)

    def assert_locked(old_fd, old_name, new_fd, new_name, flags):
        assert_receipt_locked()
        lock_was_held["rename"] = True
        return real_renameat2(old_fd, old_name, new_fd, new_name, flags)

    def assert_locked_during_fsync(descriptor):
        if (
            fixture["archive"].exists()
            and os.fstat(descriptor).st_ino == fixture["attended"].stat().st_ino
        ):
            assert_receipt_locked()
            lock_was_held["parent-fsync"] = True
        return real_fsync(descriptor)

    monkeypatch.setattr(thermal_model_files, "_renameat2", assert_locked)
    monkeypatch.setattr(thermal_model_files.os, "fsync", assert_locked_during_fsync)
    assert thermal_model_files.archive_prior_v3(fixture["files"])
    assert lock_was_held == {"rename": True, "parent-fsync": True}
