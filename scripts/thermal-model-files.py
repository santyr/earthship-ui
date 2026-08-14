#!/usr/bin/env python3
"""Durable, receipt-bound deployment of the fixed thermal runtime manifest."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile


MANIFEST = (
    {"source": "openhab/scripts/forecast_intel.py", "target": "/home/sat/openhab/scripts/forecast_intel.py", "phase": "verify", "mode": 0o755},
    {"source": "openhab/scripts/thermal_intel.py", "target": "/home/sat/openhab/scripts/thermal_intel.py", "phase": "code", "mode": 0o755},
    *(
        {
            "source": f"openhab/scripts/thermal_model/{name}.py",
            "target": f"/home/sat/openhab/scripts/thermal_model/{name}.py",
            "phase": "code",
            "mode": 0o644,
        }
        for name in (
            "__init__", "actions", "artifacts", "behavior", "dataset",
            "dynamics", "evaluation", "journal", "pipeline", "schema",
        )
    ),
    {"source": "deploy/thermal-model-train.service", "target": "/home/sat/.config/systemd/user/thermal-model-train.service", "phase": "unit", "mode": 0o644},
    {"source": "deploy/thermal-model-train.timer", "target": "/home/sat/.config/systemd/user/thermal-model-train.timer", "phase": "unit", "mode": 0o644},
    {"source": "deploy/thermal-model-shadow.service", "target": "/home/sat/.config/systemd/user/thermal-model-shadow.service", "phase": "unit", "mode": 0o644},
    {"source": "deploy/thermal-model-shadow.timer", "target": "/home/sat/.config/systemd/user/thermal-model-shadow.timer", "phase": "unit", "mode": 0o644},
)
RECEIPT_SCHEMA = "earthship-thermal-file-deploy/v1"
RECEIPT_NAME = "file-manifest.json"


def _digest(data):
    return sha256(data).hexdigest()


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_directory(path, mode, *, enforce_existing=True):
    existed = path.exists() or path.is_symlink()
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    if not path.is_dir() or path.is_symlink():
        raise RuntimeError(f"unsafe directory: {path}")
    if enforce_existing or not existed:
        os.chmod(path, mode)
    _fsync_directory(path)


def _assert_mode(path, expected, label):
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise RuntimeError(f"unsafe {label} mode {actual:o}: {path}")


def _atomic_write(path, data, mode, *, parent_mode=None):
    _ensure_directory(
        path.parent,
        parent_mode if parent_mode is not None else 0o755,
        enforce_existing=parent_mode is not None,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.thermal-stage-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if _digest(temporary.read_bytes()) != _digest(data):
            raise RuntimeError(f"staged digest mismatch: {path}")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _with_checksum(value):
    value = dict(value)
    value.pop("checksum", None)
    value["checksum"] = _digest(_canonical(value))
    return value


def _assert_regular(path, label):
    try:
        details = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"{label} unavailable: {path}") from exc
    if not stat.S_ISREG(details.st_mode):
        raise RuntimeError(f"{label} is not a regular file: {path}")
    return details


def capture_backup(repo_root, receipt_dir, *, manifest=MANIFEST):
    os.umask(0o077)
    repo_root = Path(repo_root).resolve()
    receipt_dir = Path(receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(receipt_dir, 0o700)
    backups = receipt_dir / "backups"
    _ensure_directory(backups, 0o700)
    records = []
    for index, entry in enumerate(manifest):
        source = repo_root / entry["source"]
        _assert_regular(source, "source")
        source_data = source.read_bytes()
        target = Path(entry["target"])
        record = {
            **entry,
            "mode": int(entry["mode"]),
            "source_sha256": _digest(source_data),
        }
        if entry["phase"] == "verify":
            _assert_regular(target, "verify target")
            target_data = target.read_bytes()
            if _digest(target_data) != record["source_sha256"]:
                raise RuntimeError(f"verify target digest mismatch: {target}")
            record.update(prior="verify-only", prior_sha256=_digest(target_data))
        elif target.exists() or target.is_symlink():
            details = _assert_regular(target, "target")
            target_data = target.read_bytes()
            backup_name = f"{index:02d}.bin"
            _atomic_write(backups / backup_name, target_data, 0o600, parent_mode=0o700)
            record.update(
                prior="present",
                prior_sha256=_digest(target_data),
                prior_mode=stat.S_IMODE(details.st_mode),
                backup=backup_name,
            )
        else:
            marker = f"{index:02d}.absent"
            _atomic_write(
                backups / marker,
                (str(target) + "\n").encode(),
                0o600,
                parent_mode=0o700,
            )
            record.update(prior="absent", marker=marker)
        records.append(record)
    receipt = _with_checksum({"schema": RECEIPT_SCHEMA, "entries": records})
    _atomic_write(
        receipt_dir / RECEIPT_NAME,
        _canonical(receipt) + b"\n",
        0o600,
        parent_mode=0o700,
    )
    _fsync_directory(receipt_dir)
    return receipt


def _load_receipt(receipt_dir, manifest):
    receipt_dir = Path(receipt_dir)
    if not receipt_dir.is_dir() or receipt_dir.is_symlink():
        raise RuntimeError(f"unsafe receipt directory: {receipt_dir}")
    _assert_mode(receipt_dir, 0o700, "receipt directory")
    backups = receipt_dir / "backups"
    if not backups.is_dir() or backups.is_symlink():
        raise RuntimeError(f"unsafe backup directory: {backups}")
    _assert_mode(backups, 0o700, "backup directory")
    path = receipt_dir / RECEIPT_NAME
    _assert_regular(path, "receipt")
    _assert_mode(path, 0o600, "receipt")
    receipt = json.loads(path.read_text())
    checksum = receipt.pop("checksum", None)
    if receipt.get("schema") != RECEIPT_SCHEMA or checksum != _digest(_canonical(receipt)):
        raise RuntimeError("file deployment receipt checksum mismatch")
    receipt["checksum"] = checksum
    expected = [
        {**entry, "mode": int(entry["mode"])} for entry in manifest
    ]
    actual = [
        {key: record[key] for key in ("source", "target", "phase", "mode")}
        for record in receipt.get("entries", [])
    ]
    if actual != expected:
        raise RuntimeError("file deployment manifest identity mismatch")
    for record in receipt["entries"]:
        if record["phase"] == "verify":
            continue
        artifact_name = record.get("backup") or record.get("marker")
        if not artifact_name:
            raise RuntimeError("file deployment receipt lacks rollback evidence")
        artifact = backups / artifact_name
        _assert_regular(artifact, "rollback evidence")
        _assert_mode(artifact, 0o600, "rollback evidence")
    return receipt


def _validated_sources(repo_root, receipt, phase):
    prepared = []
    for record in receipt["entries"]:
        if record["phase"] not in ({phase, "verify"} if phase == "code" else {phase}):
            continue
        source = Path(repo_root) / record["source"]
        _assert_regular(source, "source")
        data = source.read_bytes()
        if _digest(data) != record["source_sha256"]:
            raise RuntimeError(f"source digest changed: {source}")
        if record["phase"] == "verify":
            target = Path(record["target"])
            _assert_regular(target, "verify target")
            if _digest(target.read_bytes()) != record["source_sha256"]:
                raise RuntimeError(f"verify target digest mismatch: {target}")
        else:
            prepared.append((record, data))
    return prepared


def install_phase(repo_root, receipt_dir, phase, *, manifest=MANIFEST):
    if phase not in {"code", "unit"}:
        raise ValueError("phase must be code or unit")
    os.umask(0o077)
    receipt = _load_receipt(receipt_dir, manifest)
    prepared = _validated_sources(Path(repo_root).resolve(), receipt, phase)
    for record, data in prepared:
        _atomic_write(Path(record["target"]), data, record["mode"])
    if not verify_phase(repo_root, receipt_dir, phase, manifest=manifest):
        raise RuntimeError(f"incomplete {phase} manifest equality")
    return True


def verify_phase(repo_root, receipt_dir, phase, *, manifest=MANIFEST):
    receipt = _load_receipt(receipt_dir, manifest)
    _validated_sources(Path(repo_root).resolve(), receipt, phase)
    required = {phase, "verify"} if phase == "code" else {phase}
    for record in receipt["entries"]:
        if record["phase"] not in required:
            continue
        target = Path(record["target"])
        _assert_regular(target, "live target")
        if _digest(target.read_bytes()) != record["source_sha256"]:
            return False
        if record["phase"] != "verify" and stat.S_IMODE(target.stat().st_mode) != record["mode"]:
            return False
    return True


def restore(receipt_dir, *, manifest=MANIFEST):
    os.umask(0o077)
    receipt_dir = Path(receipt_dir)
    receipt = _load_receipt(receipt_dir, manifest)
    prepared = []
    for record in receipt["entries"]:
        if record["phase"] == "verify":
            continue
        if record["prior"] == "present":
            backup = receipt_dir / "backups" / record["backup"]
            _assert_regular(backup, "backup")
            data = backup.read_bytes()
            if _digest(data) != record["prior_sha256"]:
                raise RuntimeError(f"backup digest mismatch: {backup}")
            prepared.append((record, data))
        else:
            marker = receipt_dir / "backups" / record["marker"]
            _assert_regular(marker, "absent marker")
            if marker.read_text() != record["target"] + "\n":
                raise RuntimeError(f"absent marker mismatch: {marker}")
            prepared.append((record, None))
    for record, data in prepared:
        target = Path(record["target"])
        if data is None:
            if target.exists() or target.is_symlink():
                _assert_regular(target, "restore target")
                target.unlink()
                _fsync_directory(target.parent)
        else:
            _atomic_write(target, data, record["prior_mode"])
    for record, data in prepared:
        target = Path(record["target"])
        if data is None:
            if target.exists() or target.is_symlink():
                raise RuntimeError(f"absent target restore failed: {target}")
        elif _digest(target.read_bytes()) != record["prior_sha256"]:
            raise RuntimeError(f"target restore digest mismatch: {target}")
        elif stat.S_IMODE(target.stat().st_mode) != record["prior_mode"]:
            raise RuntimeError(f"target restore mode mismatch: {target}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "install-code", "verify-code", "install-units", "verify-units", "restore"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--receipt-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        capture_backup(args.repo_root, args.receipt_dir)
    elif args.command == "install-code":
        install_phase(args.repo_root, args.receipt_dir, "code")
    elif args.command == "verify-code":
        if not verify_phase(args.repo_root, args.receipt_dir, "code"):
            raise SystemExit(1)
    elif args.command == "install-units":
        install_phase(args.repo_root, args.receipt_dir, "unit")
    elif args.command == "verify-units":
        if not verify_phase(args.repo_root, args.receipt_dir, "unit"):
            raise SystemExit(1)
    else:
        restore(args.receipt_dir)


if __name__ == "__main__":
    main()
