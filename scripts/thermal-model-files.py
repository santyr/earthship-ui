#!/usr/bin/env python3
"""Durable, receipt-bound deployment of the fixed thermal runtime manifest."""

import argparse
import ctypes
import errno
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat


MANIFEST = (
    {
        "source": "openhab/scripts/forecast_intel.py",
        "target": "/home/sat/openhab/scripts/forecast_intel.py",
        "phase": "verify",
        "mode": 0o755,
    },
    {
        "source": "openhab/scripts/thermal_intel.py",
        "target": "/home/sat/openhab/scripts/thermal_intel.py",
        "phase": "code",
        "mode": 0o755,
    },
    *(
        {
            "source": f"openhab/scripts/thermal_model/{name}.py",
            "target": f"/home/sat/openhab/scripts/thermal_model/{name}.py",
            "phase": "code",
            "mode": 0o644,
        }
        for name in (
            "__init__",
            "actions",
            "artifacts",
            "behavior",
            "dataset",
            "dynamics",
            "evaluation",
            "journal",
            "pipeline",
            "schema",
            "solar",
        )
    ),
    {
        "source": "deploy/thermal-model-train.service",
        "target": "/home/sat/.config/systemd/user/thermal-model-train.service",
        "phase": "unit",
        "mode": 0o644,
    },
    {
        "source": "deploy/thermal-model-train.timer",
        "target": "/home/sat/.config/systemd/user/thermal-model-train.timer",
        "phase": "unit",
        "mode": 0o644,
    },
    {
        "source": "deploy/thermal-model-shadow.service",
        "target": "/home/sat/.config/systemd/user/thermal-model-shadow.service",
        "phase": "unit",
        "mode": 0o644,
    },
    {
        "source": "deploy/thermal-model-shadow.timer",
        "target": "/home/sat/.config/systemd/user/thermal-model-shadow.timer",
        "phase": "unit",
        "mode": 0o644,
    },
)

RECEIPT_SCHEMA = "earthship-thermal-file-deploy/v1"
RECEIPT_NAME = "file-manifest.json"
PHASE_STATE_SCHEMA = "earthship-thermal-file-phase/v1"
PHASE_STATE_NAME = "phase-state.json"
ALLOWED_REPO_ROOT = Path("/home/sat/earthship-ui")
ALLOWED_STATE_ROOT = Path("/home/sat/.local/state/thermal-intel")
ALLOWED_RECEIPT_ROOT = ALLOWED_STATE_ROOT / "deploy-receipts"
PRIOR_V3_SOURCE_ROOT = ALLOWED_STATE_ROOT / "models"
PRIOR_V3_ARCHIVE_NAME = "prior-model-v3"
PRIOR_V3_MANIFEST_NAME = "prior-evidence-manifest.json"
PRIOR_V3_EVIDENCE_SCHEMA = "earthship-thermal-prior-evidence/v1"
PRIOR_V3_INTENT_NAME = ".prior-model-v3-archive-intent.json"
PRIOR_V3_INTENT_SCHEMA = "earthship-thermal-prior-archive-intent/v1"
PRIOR_V3_EVIDENCE = (
    {
        "sourceName": "candidate.json",
        "archivedName": "candidate-v3.json",
        "sourceSchema": "earthship-thermal-model/v3",
        "sha256": "6d68639f426274d67a72d2ae45478f987af34dfdf0ae4675bc868c7f79f204fe",
        "mode": "0600",
    },
    {
        "sourceName": "backtest-report.json",
        "archivedName": "backtest-report-v1.json",
        "sourceSchema": "earthship-thermal-backtest/v1",
        "sha256": "1c504fc3b37c945af990a368d3483c5c5a69fc985e4d76ddcf6d3eaf277b211f",
        "mode": "0600",
    },
)

_DIR_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_WRITE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
_RECOVERY_STATUSES = {"applying", "recovering", "recovery-required"}
_ATTENDED_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PRIOR_V3_TEMP_NAME = re.compile(
    r"^\.prior-model-v3\.thermal-archive-[0-9a-f]{24}$"
)
_PRIOR_V3_TOKEN = re.compile(r"^[0-9a-f]{64}$")
_RENAME_NOREPLACE = 1
_RENAME_EXCHANGE = 2
_LIBC = ctypes.CDLL(None, use_errno=True)


class UnownedTargetDrift(RuntimeError):
    """The live target changed outside the receipt-owned state machine."""


class MissingPath(FileNotFoundError):
    """A no-follow path component or final name does not exist."""


def _digest(data):
    return sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _with_checksum(value):
    result = dict(value)
    result.pop("checksum", None)
    result["checksum"] = _digest(_canonical(result))
    return result


def _absolute_parts(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"path must be absolute: {path}")
    parts = path.parts[1:]
    if not parts or any(part in {"", ".", ".."} or "/" in part for part in parts):
        raise ValueError(f"unsafe absolute path: {path}")
    return parts


def _unsafe_component(path, exc):
    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
        raise RuntimeError(f"symlink or unsafe directory component: {path}") from exc
    if exc.errno == errno.ENOENT:
        raise MissingPath(str(path)) from exc
    raise RuntimeError(f"directory unavailable: {path}") from exc


def _open_directory(path, *, create=False, create_mode=0o755):
    path = Path(path)
    parts = _absolute_parts(path)
    current_fd = os.open("/", _DIR_FLAGS)
    walked = Path("/")
    try:
        for part in parts:
            child_path = walked / part
            try:
                child_fd = os.open(part, _DIR_FLAGS, dir_fd=current_fd)
            except OSError as exc:
                if exc.errno != errno.ENOENT or not create:
                    _unsafe_component(child_path, exc)
                try:
                    os.mkdir(part, create_mode, dir_fd=current_fd)
                except OSError as mkdir_exc:
                    _unsafe_component(child_path, mkdir_exc)
                os.fsync(current_fd)
                try:
                    child_fd = os.open(part, _DIR_FLAGS, dir_fd=current_fd)
                except OSError as open_exc:
                    _unsafe_component(child_path, open_exc)
                os.fchmod(child_fd, create_mode)
                os.fsync(child_fd)
            os.close(current_fd)
            current_fd = child_fd
            walked = child_path
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def secure_directory(path, mode, *, create, enforce_mode=False):
    """Walk an absolute directory without following links and optionally create it."""
    descriptor = _open_directory(path, create=create, create_mode=mode)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISDIR(details.st_mode):
            raise RuntimeError(f"unsafe directory: {path}")
        if enforce_mode:
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        elif stat.S_IMODE(details.st_mode) != mode and Path(path) in {
            ALLOWED_STATE_ROOT,
            ALLOWED_STATE_ROOT / "models",
            ALLOWED_STATE_ROOT / "review",
            ALLOWED_STATE_ROOT / "evidence",
        }:
            raise RuntimeError(f"unsafe private directory mode: {path}")
    finally:
        os.close(descriptor)
    return True


def _open_parent(path, *, create=False, create_mode=0o755):
    path = Path(path)
    parts = _absolute_parts(path)
    parent = path.parent
    descriptor = _open_directory(parent, create=create, create_mode=create_mode)
    return descriptor, parts[-1]


def _read_from_fd(descriptor):
    chunks = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_regular_at(parent_fd, name, path, label, *, allow_missing=False):
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno == errno.ENOENT and allow_missing:
            return None
        if exc.errno == errno.ELOOP:
            raise RuntimeError(f"{label} symlink rejected: {path}") from exc
        if exc.errno == errno.ENOENT:
            raise MissingPath(str(path)) from exc
        raise RuntimeError(f"{label} unavailable: {path}") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise RuntimeError(f"{label} is not a regular file: {path}")
        return _read_from_fd(descriptor), stat.S_IMODE(details.st_mode)
    finally:
        os.close(descriptor)


def _read_regular(path, label, *, allow_missing=False):
    path = Path(path)
    try:
        parent_fd, name = _open_parent(path)
    except MissingPath:
        if allow_missing:
            return None
        raise RuntimeError(f"{label} unavailable: {path}") from None
    try:
        return _read_regular_at(
            parent_fd, name, path, label, allow_missing=allow_missing
        )
    except MissingPath:
        if allow_missing:
            return None
        raise RuntimeError(f"{label} unavailable: {path}") from None
    finally:
        os.close(parent_fd)


def _assert_mode(actual, expected, label, path):
    if actual != expected:
        raise RuntimeError(f"unsafe {label} mode {actual:o}: {path}")


def _hit(fault, event, index):
    if fault is not None:
        fault(event, index)


def _atomic_write_private_at(
    parent_fd, name, path, data, mode, *, fault=None, index=-2,
):
    """Atomically write a private artifact relative to an already pinned dirfd."""
    temporary_name = f".{name}.thermal-stage-{secrets.token_hex(12)}"
    temporary_exists = False
    try:
        _read_regular_at(
            parent_fd, name, path, "target", allow_missing=True
        )
        descriptor = os.open(
            temporary_name, _WRITE_FLAGS, mode, dir_fd=parent_fd
        )
        temporary_exists = True
        try:
            os.fchmod(descriptor, mode)
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        staged = _read_regular_at(
            parent_fd,
            temporary_name,
            path.parent / temporary_name,
            "staged file",
        )
        if staged is None or _digest(staged[0]) != _digest(data) or staged[1] != mode:
            raise RuntimeError(f"staged digest or mode mismatch: {path}")
        _hit(fault, "before-replace", index)
        os.replace(
            temporary_name,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_exists = False
        _hit(fault, "after-replace", index)
        _hit(fault, "before-parent-fsync", index)
        os.fsync(parent_fd)
    finally:
        if temporary_exists:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except FileNotFoundError:
                pass


def _atomic_write_private(path, data, mode, *, parent_mode=0o755, fault=None, index=-2):
    """Write only private receipt/backup artifacts, never a live manifest target."""
    path = Path(path)
    parent_fd, name = _open_parent(path, create=True, create_mode=parent_mode)
    try:
        _atomic_write_private_at(
            parent_fd,
            name,
            path,
            data,
            mode,
            fault=fault,
            index=index,
        )
    finally:
        os.close(parent_fd)


def _unlink(path):
    path = Path(path)
    parent_fd, name = _open_parent(path)
    try:
        current = _read_regular_at(parent_fd, name, path, "target", allow_missing=True)
        if current is not None:
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _receipt_path(receipt_dir, name):
    return Path(receipt_dir) / name


def _read_json(path, label, *, allow_missing=False):
    result = _read_regular(path, label, allow_missing=allow_missing)
    if result is None:
        return None
    data, actual_mode = result
    _assert_mode(actual_mode, 0o600, label, path)
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not valid JSON: {path}") from exc


def _write_json(path, value):
    _atomic_write_private(
        path,
        _canonical(_with_checksum(value)) + b"\n",
        0o600,
        parent_mode=0o700,
    )


def _secure_empty_receipt(receipt_dir):
    receipt_dir = Path(receipt_dir)
    try:
        descriptor = _open_directory(receipt_dir)
    except MissingPath:
        secure_directory(receipt_dir, 0o700, create=True, enforce_mode=True)
        descriptor = _open_directory(receipt_dir)
    try:
        _assert_mode(
            stat.S_IMODE(os.fstat(descriptor).st_mode),
            0o700,
            "receipt directory",
            receipt_dir,
        )
        if os.listdir(descriptor):
            raise RuntimeError(f"file deployment receipt is not empty: {receipt_dir}")
    finally:
        os.close(descriptor)


def _source_path(repo_root, record):
    relative = Path(record["source"])
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe source path: {relative}")
    return Path(repo_root) / relative


def capture_backup(repo_root, receipt_dir, *, manifest=MANIFEST):
    os.umask(0o077)
    repo_root = Path(repo_root)
    repo_fd = _open_directory(repo_root)
    os.close(repo_fd)
    receipt_dir = Path(receipt_dir)
    _secure_empty_receipt(receipt_dir)
    backups = receipt_dir / "backups"
    secure_directory(backups, 0o700, create=True, enforce_mode=True)

    prepared = []
    for entry in manifest:
        source = _source_path(repo_root, entry)
        source_data, _ = _read_regular(source, "source")
        target = Path(entry["target"])
        target_state = _read_regular(target, "target", allow_missing=True)
        record = {
            **entry,
            "mode": int(entry["mode"]),
            "source_sha256": _digest(source_data),
        }
        if entry["phase"] == "verify":
            if target_state is None:
                raise RuntimeError(f"verify target unavailable: {target}")
            target_data, _ = target_state
            if _digest(target_data) != record["source_sha256"]:
                raise RuntimeError(f"verify target digest mismatch: {target}")
            record.update(prior="verify-only", prior_sha256=_digest(target_data))
        elif target_state is not None:
            target_data, target_mode = target_state
            record.update(
                prior="present",
                prior_sha256=_digest(target_data),
                prior_mode=target_mode,
            )
        else:
            record.update(prior="absent")
        prepared.append((record, target_state))

    records = []
    for index, (record, target_state) in enumerate(prepared):
        if record["phase"] == "verify":
            records.append(record)
            continue
        if target_state is not None:
            backup_name = f"{index:02d}.bin"
            _atomic_write_private(
                backups / backup_name,
                target_state[0],
                0o600,
                parent_mode=0o700,
            )
            record["backup"] = backup_name
        else:
            marker = f"{index:02d}.absent"
            _atomic_write_private(
                backups / marker,
                (record["target"] + "\n").encode(),
                0o600,
                parent_mode=0o700,
            )
            record["marker"] = marker
        records.append(record)

    receipt = _with_checksum({"schema": RECEIPT_SCHEMA, "entries": records})
    _atomic_write_private(
        receipt_dir / RECEIPT_NAME,
        _canonical(receipt) + b"\n",
        0o600,
        parent_mode=0o700,
    )
    receipt_fd = _open_directory(receipt_dir)
    try:
        os.fsync(receipt_fd)
    finally:
        os.close(receipt_fd)
    return receipt


def _load_receipt(receipt_dir, manifest):
    receipt_dir = Path(receipt_dir)
    descriptor = _open_directory(receipt_dir)
    try:
        _assert_mode(
            stat.S_IMODE(os.fstat(descriptor).st_mode),
            0o700,
            "receipt directory",
            receipt_dir,
        )
    finally:
        os.close(descriptor)
    backups = receipt_dir / "backups"
    backup_fd = _open_directory(backups)
    try:
        _assert_mode(
            stat.S_IMODE(os.fstat(backup_fd).st_mode),
            0o700,
            "backup directory",
            backups,
        )
    finally:
        os.close(backup_fd)

    receipt = _read_json(receipt_dir / RECEIPT_NAME, "receipt")
    checksum = receipt.pop("checksum", None)
    if (
        receipt.get("schema") != RECEIPT_SCHEMA
        or checksum != _digest(_canonical(receipt))
    ):
        raise RuntimeError("file deployment receipt checksum mismatch")
    receipt["checksum"] = checksum
    expected = [{**entry, "mode": int(entry["mode"])} for entry in manifest]
    try:
        actual = [
            {
                key: record[key]
                for key in ("source", "target", "phase", "mode")
            }
            for record in receipt.get("entries", [])
        ]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("file deployment manifest identity mismatch") from exc
    if actual != expected:
        raise RuntimeError("file deployment manifest identity mismatch")

    for record in receipt["entries"]:
        target = Path(record["target"])
        if not target.is_absolute():
            raise RuntimeError(f"non-absolute manifest target: {target}")
        if record["phase"] == "verify":
            continue
        artifact_name = record.get("backup") or record.get("marker")
        if (
            not artifact_name
            or Path(artifact_name).name != artifact_name
            or "/" in artifact_name
        ):
            raise RuntimeError("file deployment receipt lacks rollback evidence")
        artifact = backups / artifact_name
        artifact_data, artifact_mode = _read_regular(
            artifact, "rollback evidence"
        )
        _assert_mode(
            artifact_mode, 0o600, "rollback evidence", artifact
        )
        if record["prior"] == "present":
            if _digest(artifact_data) != record.get("prior_sha256"):
                raise RuntimeError(f"backup digest mismatch: {artifact}")
        elif (
            record["prior"] != "absent"
            or artifact_data != (record["target"] + "\n").encode()
        ):
            raise RuntimeError(f"absent marker mismatch: {artifact}")
    return receipt


def _load_phase_state(receipt_dir, receipt, *, allow_missing=True):
    path = _receipt_path(receipt_dir, PHASE_STATE_NAME)
    state_value = _read_json(
        path, "phase state", allow_missing=allow_missing
    )
    if state_value is None:
        return None
    checksum = state_value.pop("checksum", None)
    if (
        state_value.get("schema") != PHASE_STATE_SCHEMA
        or state_value.get("receipt_checksum") != receipt["checksum"]
        or checksum != _digest(_canonical(state_value))
    ):
        raise RuntimeError("phase state checksum or receipt identity mismatch")
    state_value["checksum"] = checksum
    return state_value


def _write_phase_state(receipt_dir, state_value):
    _write_json(_receipt_path(receipt_dir, PHASE_STATE_NAME), state_value)


def _assert_no_recovery(receipt_dir, receipt):
    state_value = _load_phase_state(receipt_dir, receipt)
    if state_value is not None and state_value.get("status") in _RECOVERY_STATUSES:
        raise RuntimeError("explicit recovery required before next operation")
    return state_value


def _expected_metadata(record, state_name):
    if state_name == "desired":
        return record["source_sha256"], record["mode"]
    if state_name != "original":
        raise ValueError(f"unknown target state: {state_name}")
    if record["prior"] == "absent":
        return None
    return record["prior_sha256"], record["prior_mode"]


def _verify_dependency_matches(record):
    current = _read_regular(
        Path(record["target"]), "verify target", allow_missing=True
    )
    return current is not None and _digest(current[0]) == record["source_sha256"]


def _target_matches(record, state_name):
    expected = _expected_metadata(record, state_name)
    current = _read_regular(
        Path(record["target"]), "live target", allow_missing=True
    )
    if expected is None:
        return current is None
    if current is None:
        return False
    data, actual_mode = current
    return _digest(data) == expected[0] and actual_mode == expected[1]


def _owned_state(record, allowed):
    for state_name in allowed:
        if _target_matches(record, state_name):
            return state_name
    raise UnownedTargetDrift(f"unowned target drift: {record['target']}")


def _validated_sources(repo_root, receipt, phase):
    prepared = []
    required = {phase, "verify"} if phase == "code" else {phase}
    for record in receipt["entries"]:
        if record["phase"] not in required:
            continue
        source = _source_path(repo_root, record)
        data, _ = _read_regular(source, "source")
        if _digest(data) != record["source_sha256"]:
            raise RuntimeError(f"source digest changed: {source}")
        if record["phase"] == "verify":
            if not _verify_dependency_matches(record):
                raise RuntimeError(
                    f"verify target digest mismatch: {record['target']}"
                )
        else:
            prepared.append((record, data))
    return prepared


def _state_bytes(repo_root, receipt_dir, record, state_name):
    if state_name == "desired":
        source = _source_path(repo_root, record)
        data, _ = _read_regular(source, "source")
        if _digest(data) != record["source_sha256"]:
            raise RuntimeError(f"source digest changed: {source}")
        return data, record["mode"]
    if state_name == "original":
        if record["prior"] == "absent":
            return None
        backup = Path(receipt_dir) / "backups" / record["backup"]
        data, actual_mode = _read_regular(backup, "backup")
        _assert_mode(actual_mode, 0o600, "backup", backup)
        if _digest(data) != record["prior_sha256"]:
            raise RuntimeError(f"backup digest mismatch: {backup}")
        return data, record["prior_mode"]
    raise ValueError(f"unknown target state: {state_name}")


def _renameat2(old_dir_fd, old_name, new_dir_fd, new_name, flags):
    try:
        function = _LIBC.renameat2
    except AttributeError as exc:
        raise RuntimeError("renameat2 capability unavailable") from exc
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    result = function(
        old_dir_fd,
        os.fsencode(old_name),
        new_dir_fd,
        os.fsencode(new_name),
        flags,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        raise RuntimeError("renameat2 capability unavailable")
    raise OSError(error, os.strerror(error), old_name, new_name)


def _matches_at(parent_fd, name, path, record, state_name):
    expected = _expected_metadata(record, state_name)
    current = _read_regular_at(
        parent_fd, name, path, "live target", allow_missing=True
    )
    if expected is None:
        return current is None
    return (
        current is not None
        and _digest(current[0]) == expected[0]
        and current[1] == expected[1]
    )


def _stage_at(parent_fd, name, path, data, mode):
    descriptor = os.open(name, _WRITE_FLAGS, mode, dir_fd=parent_fd)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    staged = _read_regular_at(parent_fd, name, path, "staged file")
    if staged is None or _digest(staged[0]) != _digest(data) or staged[1] != mode:
        raise RuntimeError(f"staged digest or mode mismatch: {path}")


def _remove_owned_at(parent_fd, name, path, record, allowed_states):
    current = _read_regular_at(
        parent_fd, name, path, "exchange file", allow_missing=True
    )
    if current is None:
        return
    if not any(_matches_at(parent_fd, name, path, record, state) for state in allowed_states):
        raise RuntimeError(f"unowned exchange drift: {path}")
    os.unlink(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _reverse_mismatched_exchange(
    parent_fd, target_name, exchange_name, target_path, record, after,
):
    if not _matches_at(parent_fd, target_name, target_path, record, after):
        raise RuntimeError(
            f"unowned target drift after exchange; recovery required: {target_path}"
        )
    _renameat2(
        parent_fd, exchange_name, parent_fd, target_name, _RENAME_EXCHANGE
    )
    os.fsync(parent_fd)
    _remove_owned_at(
        parent_fd,
        exchange_name,
        target_path.parent / exchange_name,
        record,
        (after,),
    )


def _cas_apply(
    repo_root,
    receipt_dir,
    record,
    before,
    after,
    exchange_name,
    *,
    fault=None,
    index=-2,
):
    payload = _state_bytes(repo_root, receipt_dir, record, after)
    target = Path(record["target"])
    parent_fd, target_name = _open_parent(target, create=True, create_mode=0o755)
    exchange_path = target.parent / exchange_name
    staged = False
    try:
        if not _matches_at(parent_fd, target_name, target, record, before):
            raise UnownedTargetDrift(f"unowned target drift: {target}")
        exchange_current = _read_regular_at(
            parent_fd,
            exchange_name,
            exchange_path,
            "exchange file",
            allow_missing=True,
        )
        if exchange_current is not None:
            raise RuntimeError(f"explicit recovery required: {exchange_path}")
        if payload is not None:
            _stage_at(parent_fd, exchange_name, exchange_path, payload[0], payload[1])
            staged = True

        _hit(fault, "before-replace", index)
        _hit(fault, "before-exchange", index)
        try:
            if payload is None:
                _renameat2(
                    parent_fd,
                    target_name,
                    parent_fd,
                    exchange_name,
                    _RENAME_NOREPLACE,
                )
            elif _expected_metadata(record, before) is None:
                _renameat2(
                    parent_fd,
                    exchange_name,
                    parent_fd,
                    target_name,
                    _RENAME_NOREPLACE,
                )
                staged = False
            else:
                _renameat2(
                    parent_fd,
                    exchange_name,
                    parent_fd,
                    target_name,
                    _RENAME_EXCHANGE,
                )
        except FileNotFoundError as exc:
            current_target = _read_regular_at(
                parent_fd,
                target_name,
                target,
                "live target",
                allow_missing=True,
            )
            if (
                _expected_metadata(record, before) is not None
                and current_target is None
            ):
                raise UnownedTargetDrift(
                    f"unowned target drift: externally absent {target}"
                ) from exc
            raise RuntimeError(
                f"exchange input disappeared before atomic transition: {target}"
            ) from exc
        except FileExistsError as exc:
            if staged:
                _remove_owned_at(
                    parent_fd, exchange_name, exchange_path, record, (after,)
                )
                staged = False
            raise UnownedTargetDrift(f"unowned target drift: {target}") from exc

        _hit(fault, "after-replace", index)
        _hit(fault, "after-exchange", index)

        if not _matches_at(parent_fd, target_name, target, record, after):
            raise RuntimeError(f"incomplete atomic target transition: {target}")
        if _expected_metadata(record, before) is not None:
            if not _matches_at(
                parent_fd, exchange_name, exchange_path, record, before
            ):
                if payload is not None:
                    _reverse_mismatched_exchange(
                        parent_fd,
                        target_name,
                        exchange_name,
                        target,
                        record,
                        after,
                    )
                    staged = False
                else:
                    if _read_regular_at(
                        parent_fd,
                        target_name,
                        target,
                        "live target",
                        allow_missing=True,
                    ) is not None:
                        raise RuntimeError(
                            f"unowned target drift after capture; recovery required: {target}"
                        )
                    _renameat2(
                        parent_fd,
                        exchange_name,
                        parent_fd,
                        target_name,
                        _RENAME_NOREPLACE,
                    )
                    os.fsync(parent_fd)
                raise UnownedTargetDrift(f"unowned target drift: {target}")
        _hit(fault, "before-parent-fsync", index)
        os.fsync(parent_fd)
    except Exception:
        if staged:
            try:
                _remove_owned_at(
                    parent_fd, exchange_name, exchange_path, record, (after,)
                )
            except Exception:
                pass
        raise
    finally:
        os.close(parent_fd)


def _cleanup_exchange(record, entry, *, allowed_states):
    target = Path(record["target"])
    parent_fd, _ = _open_parent(target)
    try:
        _remove_owned_at(
            parent_fd,
            entry["exchange_name"],
            target.parent / entry["exchange_name"],
            record,
            allowed_states,
        )
    finally:
        os.close(parent_fd)


def _restore_entry_before(repo_root, receipt_dir, record, entry):
    before = entry["before"]
    after = entry["after"]
    target = Path(record["target"])
    parent_fd, target_name = _open_parent(target, create=True, create_mode=0o755)
    exchange_name = entry["exchange_name"]
    exchange_path = target.parent / exchange_name
    try:
        if _matches_at(parent_fd, target_name, target, record, before):
            _remove_owned_at(
                parent_fd, exchange_name, exchange_path, record, (after, before)
            )
            return
        if not _matches_at(parent_fd, target_name, target, record, after):
            raise UnownedTargetDrift(f"unowned target drift: {target}")
        exchange = _read_regular_at(
            parent_fd,
            exchange_name,
            exchange_path,
            "exchange file",
            allow_missing=True,
        )
        before_expected = _expected_metadata(record, before)
        after_expected = _expected_metadata(record, after)
        if exchange is not None:
            if before_expected is None:
                raise RuntimeError(f"unowned exchange drift: {exchange_path}")
            if not _matches_at(parent_fd, exchange_name, exchange_path, record, before):
                raise RuntimeError(f"unowned exchange drift: {exchange_path}")
            if after_expected is None:
                _renameat2(
                    parent_fd,
                    exchange_name,
                    parent_fd,
                    target_name,
                    _RENAME_NOREPLACE,
                )
            else:
                _renameat2(
                    parent_fd,
                    exchange_name,
                    parent_fd,
                    target_name,
                    _RENAME_EXCHANGE,
                )
            os.fsync(parent_fd)
            _remove_owned_at(
                parent_fd, exchange_name, exchange_path, record, (after,)
            )
            return
    finally:
        os.close(parent_fd)

    recovery_name = entry["exchange_name"]
    _cas_apply(
        repo_root,
        receipt_dir,
        record,
        after,
        before,
        recovery_name,
    )
    _cleanup_exchange(record, entry, allowed_states=(after, before))


def _new_phase_state(receipt, operation, entries):
    return {
        "schema": PHASE_STATE_SCHEMA,
        "receipt_checksum": receipt["checksum"],
        "operation": operation,
        "status": "applying",
        "entries": entries,
    }


def _record_for_target(receipt, target):
    for record in receipt["entries"]:
        if record["target"] == target:
            return record
    raise RuntimeError(f"phase state target absent from receipt: {target}")


def _rollback_transaction(repo_root, receipt_dir, receipt, state_value):
    state_value["status"] = "recovering"
    _write_phase_state(receipt_dir, state_value)
    preserved_unowned = False
    try:
        for entry in reversed(state_value["entries"]):
            record = _record_for_target(receipt, entry["target"])
            if entry.get("status") in {
                "refused-unowned-drift",
                "rolled-back-unowned-preserved",
            }:
                entry["status"] = "refused-unowned-drift"
                preserved_unowned = True
                _write_phase_state(receipt_dir, state_value)
                continue
            _restore_entry_before(repo_root, receipt_dir, record, entry)
            entry["status"] = "rolled-back"
            entry["exchange_cleaned"] = True
            _write_phase_state(receipt_dir, state_value)
        state_value["status"] = (
            "recovery-required" if preserved_unowned else "rolled-back"
        )
        _write_phase_state(receipt_dir, state_value)
        return not preserved_unowned
    except Exception:
        state_value["status"] = "recovery-required"
        _write_phase_state(receipt_dir, state_value)
        raise


def _execute_transaction(
    repo_root,
    receipt_dir,
    receipt,
    operation,
    transitions,
    *,
    fault=None,
    final_verify,
):
    entries = [
        {
            "target": record["target"],
            "before": before,
            "after": after,
            "exchange_name": (
                f".{Path(record['target']).name}.thermal-exchange-"
                f"{secrets.token_hex(12)}"
            ),
            "status": "pending",
        }
        for record, before, after in transitions
        if before != after
    ]
    state_value = _new_phase_state(receipt, operation, entries)
    _write_phase_state(receipt_dir, state_value)
    try:
        for index, entry in enumerate(state_value["entries"]):
            record = _record_for_target(receipt, entry["target"])
            try:
                if _owned_state(record, (entry["before"],)) != entry["before"]:
                    raise UnownedTargetDrift(
                        f"unowned target drift: {entry['target']}"
                    )
            except UnownedTargetDrift:
                entry["status"] = "refused-unowned-drift"
                _write_phase_state(receipt_dir, state_value)
                raise
            entry["status"] = "intent"
            _write_phase_state(receipt_dir, state_value)
            try:
                _cas_apply(
                    repo_root,
                    receipt_dir,
                    record,
                    entry["before"],
                    entry["after"],
                    entry["exchange_name"],
                    fault=fault,
                    index=index,
                )
            except UnownedTargetDrift:
                entry["status"] = "refused-unowned-drift"
                _write_phase_state(receipt_dir, state_value)
                raise
            entry["status"] = "completed"
            _write_phase_state(receipt_dir, state_value)
            _cleanup_exchange(
                record, entry, allowed_states=(entry["before"], entry["after"])
            )
            entry["exchange_cleaned"] = True
            _write_phase_state(receipt_dir, state_value)
        _hit(fault, "before-final-verify", -1)
        if not final_verify():
            raise RuntimeError(f"incomplete {operation} manifest equality")
        state_value["status"] = "complete"
        _write_phase_state(receipt_dir, state_value)
        return True
    except Exception:
        try:
            _rollback_transaction(
                repo_root, receipt_dir, receipt, state_value
            )
        except Exception as rollback_error:
            raise RuntimeError(
                "automatic rollback failed; explicit recovery required"
            ) from rollback_error
        raise


def install_phase(
    repo_root,
    receipt_dir,
    phase,
    *,
    manifest=MANIFEST,
    fault=None,
):
    if phase not in {"code", "unit"}:
        raise ValueError("phase must be code or unit")
    os.umask(0o077)
    repo_root = Path(repo_root)
    receipt = _load_receipt(receipt_dir, manifest)
    _assert_no_recovery(receipt_dir, receipt)
    prepared = _validated_sources(repo_root, receipt, phase)
    transitions = []
    for record, _ in prepared:
        current = _owned_state(record, ("desired", "original"))
        transitions.append((record, current, "desired"))
    return _execute_transaction(
        repo_root,
        receipt_dir,
        receipt,
        f"install-{phase}",
        transitions,
        fault=fault,
        final_verify=lambda: verify_phase(
            repo_root,
            receipt_dir,
            phase,
            manifest=manifest,
            check_recovery=False,
        ),
    )


def verify_phase(
    repo_root,
    receipt_dir,
    phase,
    *,
    manifest=MANIFEST,
    check_recovery=True,
):
    if phase not in {"code", "unit"}:
        raise ValueError("phase must be code or unit")
    receipt = _load_receipt(receipt_dir, manifest)
    if check_recovery:
        _assert_no_recovery(receipt_dir, receipt)
    _validated_sources(Path(repo_root), receipt, phase)
    required = {phase, "verify"} if phase == "code" else {phase}
    return all(
        _verify_dependency_matches(record)
        if record["phase"] == "verify"
        else _target_matches(record, "desired")
        for record in receipt["entries"]
        if record["phase"] in required
    )


def restore(repo_root, receipt_dir=None, *, manifest=MANIFEST, fault=None):
    if receipt_dir is None:
        receipt_dir = repo_root
        repo_root = Path.cwd()
    os.umask(0o077)
    repo_root = Path(repo_root)
    receipt = _load_receipt(receipt_dir, manifest)
    _assert_no_recovery(receipt_dir, receipt)
    transitions = []
    for record in receipt["entries"]:
        if record["phase"] == "verify":
            if not _verify_dependency_matches(record):
                raise UnownedTargetDrift(f"unowned target drift: {record['target']}")
            continue
        current = _owned_state(record, ("original", "desired"))
        transitions.append((record, current, "original"))
    return _execute_transaction(
        repo_root,
        receipt_dir,
        receipt,
        "restore",
        transitions,
        fault=fault,
        final_verify=lambda: all(
            _target_matches(record, "original")
            for record in receipt["entries"]
            if record["phase"] != "verify"
        ),
    )


def recover(repo_root, receipt_dir, *, manifest=MANIFEST):
    os.umask(0o077)
    repo_root = Path(repo_root)
    receipt = _load_receipt(receipt_dir, manifest)
    state_value = _load_phase_state(receipt_dir, receipt, allow_missing=False)
    if state_value.get("status") not in _RECOVERY_STATUSES:
        return state_value.get("status") in {"complete", "rolled-back"}
    return _rollback_transaction(repo_root, receipt_dir, receipt, state_value)


def _prior_v3_manifest():
    source_root = Path(PRIOR_V3_SOURCE_ROOT)
    return {
        "schema": PRIOR_V3_EVIDENCE_SCHEMA,
        "records": [
            {
                "archivedName": record["archivedName"],
                "sourcePath": str(source_root / record["sourceName"]),
                "sourceSchema": record["sourceSchema"],
                "sha256": record["sha256"],
                "mode": record["mode"],
            }
            for record in PRIOR_V3_EVIDENCE
        ],
    }


def _validated_prior_v3_files():
    manifest = _prior_v3_manifest()
    prepared = {}
    for evidence, record in zip(PRIOR_V3_EVIDENCE, manifest["records"]):
        source = Path(record["sourcePath"])
        data, actual_mode = _read_regular(source, "prior v3 source")
        _assert_mode(actual_mode, 0o600, "prior v3 source", source)
        if evidence["mode"] != "0600" or _digest(data) != evidence["sha256"]:
            raise RuntimeError(f"prior v3 source digest mismatch: {source}")
        try:
            document = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"prior v3 source is not valid JSON: {source}") from exc
        if not isinstance(document, dict) or document.get("schema") != evidence[
            "sourceSchema"
        ]:
            raise RuntimeError(f"prior v3 source schema mismatch: {source}")
        try:
            eligible = document["metrics"]["promotion"]["eligible"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                f"prior v3 source lacks promotion refusal: {source}"
            ) from exc
        if eligible is not False:
            raise RuntimeError(f"prior v3 source is promotion eligible: {source}")
        prepared[evidence["archivedName"]] = data
    prepared[PRIOR_V3_MANIFEST_NAME] = _canonical(manifest) + b"\n"
    return prepared


def _prior_v3_parent(receipt_dir):
    receipt_dir = Path(receipt_dir)
    _absolute_parts(receipt_dir)
    if receipt_dir.name != "files":
        raise ValueError("prior v3 archive requires the attended files receipt")
    attended = receipt_dir.parent
    parent_fd = _open_directory(attended)
    files_fd = None
    try:
        _assert_mode(
            stat.S_IMODE(os.fstat(parent_fd).st_mode),
            0o700,
            "attended receipt directory",
            attended,
        )
        try:
            files_fd = os.open("files", _DIR_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            _unsafe_component(receipt_dir, exc)
        try:
            _assert_mode(
                stat.S_IMODE(os.fstat(files_fd).st_mode),
                0o700,
                "file receipt directory",
                receipt_dir,
            )
            try:
                fcntl.flock(files_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    f"prior v3 archive receipt is locked: {receipt_dir}"
                ) from exc
        except BaseException:
            os.close(files_fd)
            files_fd = None
            raise
        return parent_fd, files_fd, attended
    except BaseException:
        if files_fd is not None:
            os.close(files_fd)
        os.close(parent_fd)
        raise


def _prior_v3_intent_value(parent_fd, files_fd, temporary_fd, temporary_name):
    attended_stat = os.fstat(parent_fd)
    files_stat = os.fstat(files_fd)
    temporary_stat = os.fstat(temporary_fd)
    return {
        "schema": PRIOR_V3_INTENT_SCHEMA,
        "token": secrets.token_hex(32),
        "temporaryName": temporary_name,
        "temporaryDevice": temporary_stat.st_dev,
        "temporaryInode": temporary_stat.st_ino,
        "attendedDevice": attended_stat.st_dev,
        "attendedInode": attended_stat.st_ino,
        "filesDevice": files_stat.st_dev,
        "filesInode": files_stat.st_ino,
    }


def _prior_v3_intent_bytes(intent):
    return _canonical(intent) + b"\n"


def _validate_prior_v3_intent(intent, parent_fd, files_fd, path):
    expected_keys = {
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
    if not isinstance(intent, dict) or set(intent) != expected_keys:
        raise RuntimeError(f"unverifiable prior archive intent: {path}")
    numeric_keys = expected_keys - {"schema", "temporaryName", "token"}
    if (
        intent["schema"] != PRIOR_V3_INTENT_SCHEMA
        or not _PRIOR_V3_TOKEN.fullmatch(intent["token"])
        or not _PRIOR_V3_TEMP_NAME.fullmatch(intent["temporaryName"])
        or any(type(intent[key]) is not int or intent[key] < 0 for key in numeric_keys)
    ):
        raise RuntimeError(f"unverifiable prior archive intent: {path}")
    attended_stat = os.fstat(parent_fd)
    files_stat = os.fstat(files_fd)
    if (
        (intent["attendedDevice"], intent["attendedInode"])
        != (attended_stat.st_dev, attended_stat.st_ino)
        or (intent["filesDevice"], intent["filesInode"])
        != (files_stat.st_dev, files_stat.st_ino)
    ):
        raise RuntimeError(f"unverifiable prior archive intent: {path}")
    return intent


def _load_prior_v3_intent(files_fd, receipt_dir, parent_fd):
    path = receipt_dir / PRIOR_V3_INTENT_NAME
    result = _read_regular_at(
        files_fd,
        PRIOR_V3_INTENT_NAME,
        path,
        "prior archive intent",
        allow_missing=True,
    )
    if result is None:
        return None
    data, actual_mode = result
    _assert_mode(actual_mode, 0o600, "prior archive intent", path)
    try:
        intent = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unverifiable prior archive intent: {path}") from exc
    return _validate_prior_v3_intent(intent, parent_fd, files_fd, path)


def _assert_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent):
    current = _load_prior_v3_intent(files_fd, receipt_dir, parent_fd)
    if current != intent:
        raise RuntimeError(
            f"prior archive intent changed: {receipt_dir / PRIOR_V3_INTENT_NAME}"
        )


def _write_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent):
    if _load_prior_v3_intent(files_fd, receipt_dir, parent_fd) is not None:
        raise RuntimeError(
            f"prior archive intent already exists: "
            f"{receipt_dir / PRIOR_V3_INTENT_NAME}"
        )
    _atomic_write_private_at(
        files_fd,
        PRIOR_V3_INTENT_NAME,
        receipt_dir / PRIOR_V3_INTENT_NAME,
        _prior_v3_intent_bytes(intent),
        0o600,
    )
    _assert_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)


def _remove_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent):
    _assert_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)
    os.unlink(PRIOR_V3_INTENT_NAME, dir_fd=files_fd)
    os.fsync(files_fd)


def _prior_v3_archive_exists(parent_fd, attended):
    try:
        os.stat(PRIOR_V3_ARCHIVE_NAME, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise RuntimeError(
            f"prior v3 archive unavailable: {attended / PRIOR_V3_ARCHIVE_NAME}"
        ) from exc
    return True


def _open_prior_v3_temporary(parent_fd, attended, temporary_name):
    temporary_path = attended / temporary_name
    try:
        descriptor = os.open(temporary_name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(
            f"unverifiable prior archive temporary: {temporary_path}"
        ) from exc
    try:
        _assert_mode(
            stat.S_IMODE(os.fstat(descriptor).st_mode),
            0o700,
            "prior archive temporary directory",
            temporary_path,
        )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _assert_prior_v3_temporary_identity(
    parent_fd, temporary_fd, attended, temporary_name,
):
    temporary_path = attended / temporary_name
    try:
        name_stat = os.stat(
            temporary_name, dir_fd=parent_fd, follow_symlinks=False
        )
    except OSError as exc:
        raise RuntimeError(
            f"prior archive temporary identity changed: {temporary_path}"
        ) from exc
    descriptor_stat = os.fstat(temporary_fd)
    if (
        not stat.S_ISDIR(name_stat.st_mode)
        or (name_stat.st_dev, name_stat.st_ino)
        != (descriptor_stat.st_dev, descriptor_stat.st_ino)
    ):
        raise RuntimeError(
            f"prior archive temporary identity changed: {temporary_path}"
        )


def _assert_prior_v3_intent_owns_temporary(intent, temporary_fd, path):
    details = os.fstat(temporary_fd)
    if (intent["temporaryDevice"], intent["temporaryInode"]) != (
        details.st_dev,
        details.st_ino,
    ):
        raise RuntimeError(f"unverifiable prior archive temporary: {path}")


def _validate_prior_v3_temporary(
    temporary_fd, temporary_path, expected_files, *, final,
):
    label = (
        "final prior archive temporary"
        if final
        else "unverifiable prior archive temporary"
    )
    try:
        details = os.fstat(temporary_fd)
        if stat.S_IMODE(details.st_mode) != 0o700:
            raise RuntimeError("unsafe temporary directory mode")
        names = set(os.listdir(temporary_fd))
        if final:
            if names != set(expected_files):
                raise RuntimeError("inventory mismatch")
        elif not names <= set(expected_files):
            raise RuntimeError("unexpected entry")
        for name in names:
            current = _read_regular_at(
                temporary_fd,
                name,
                temporary_path / name,
                "prior archive temporary file",
            )
            if current != (expected_files[name], 0o600):
                raise RuntimeError("content or mode mismatch")
        return names
    except Exception as exc:
        raise RuntimeError(f"{label} invalid: {temporary_path}") from exc


def _remove_owned_prior_v3_temporary(
    parent_fd,
    files_fd,
    receipt_dir,
    attended,
    temporary_fd,
    temporary_name,
    expected_files,
    intent,
):
    temporary_path = attended / temporary_name
    _assert_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)
    _assert_prior_v3_intent_owns_temporary(intent, temporary_fd, temporary_path)
    _assert_prior_v3_temporary_identity(
        parent_fd, temporary_fd, attended, temporary_name
    )
    names = _validate_prior_v3_temporary(
        temporary_fd, temporary_path, expected_files, final=False
    )
    for name in sorted(names):
        os.unlink(name, dir_fd=temporary_fd)
    os.fsync(temporary_fd)
    _assert_prior_v3_temporary_identity(
        parent_fd, temporary_fd, attended, temporary_name
    )
    os.rmdir(temporary_name, dir_fd=parent_fd)
    os.fsync(parent_fd)
    _remove_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)


def _remove_current_unowned_empty_prior_v3_temporary(
    parent_fd, attended, temporary_fd, temporary_name,
):
    temporary_path = attended / temporary_name
    _assert_prior_v3_temporary_identity(
        parent_fd, temporary_fd, attended, temporary_name
    )
    if os.listdir(temporary_fd):
        raise RuntimeError(
            f"unverifiable prior archive temporary: {temporary_path}"
        )
    _assert_prior_v3_temporary_identity(
        parent_fd, temporary_fd, attended, temporary_name
    )
    os.rmdir(temporary_name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _prior_v3_temporary_names(parent_fd):
    return sorted(
        name
        for name in os.listdir(parent_fd)
        if _PRIOR_V3_TEMP_NAME.fullmatch(name)
    )


def _recover_prior_v3_temporaries(
    parent_fd, files_fd, receipt_dir, attended, expected_files,
):
    intent = _load_prior_v3_intent(files_fd, receipt_dir, parent_fd)
    temporary_names = _prior_v3_temporary_names(parent_fd)
    if intent is None:
        if temporary_names:
            raise RuntimeError(
                f"unverifiable prior archive temporary: "
                f"{attended / temporary_names[0]}"
            )
        return
    if not temporary_names:
        _remove_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)
        return
    if temporary_names != [intent["temporaryName"]]:
        raise RuntimeError(
            f"unverifiable prior archive temporary: "
            f"{attended / temporary_names[0]}"
        )
    temporary_name = temporary_names[0]
    temporary_fd = _open_prior_v3_temporary(
        parent_fd, attended, temporary_name
    )
    try:
        _remove_owned_prior_v3_temporary(
            parent_fd,
            files_fd,
            receipt_dir,
            attended,
            temporary_fd,
            temporary_name,
            expected_files,
            intent,
        )
    finally:
        os.close(temporary_fd)


def archive_prior_v3(receipt_dir, *, fault=None):
    """Archive only the pinned rejected v3 evidence beside an attended receipt."""
    os.umask(0o077)
    receipt_dir = Path(receipt_dir)
    parent_fd, files_fd, attended = _prior_v3_parent(receipt_dir)
    temporary_name = None
    temporary_exists = False
    temporary_fd = None
    intent = None
    try:
        expected_files = _validated_prior_v3_files()
        if _prior_v3_archive_exists(parent_fd, attended):
            raise RuntimeError(
                f"prior v3 archive already exists: "
                f"{attended / PRIOR_V3_ARCHIVE_NAME}"
            )
        _recover_prior_v3_temporaries(
            parent_fd, files_fd, receipt_dir, attended, expected_files
        )

        temporary_name = (
            f".{PRIOR_V3_ARCHIVE_NAME}.thermal-archive-"
            f"{secrets.token_hex(12)}"
        )
        os.mkdir(temporary_name, 0o700, dir_fd=parent_fd)
        temporary_exists = True
        temporary_path = attended / temporary_name
        temporary_fd = _open_prior_v3_temporary(
            parent_fd, attended, temporary_name
        )
        os.fchmod(temporary_fd, 0o700)
        os.fsync(temporary_fd)
        _hit(fault, "after-temporary-open", -1)
        intent = _prior_v3_intent_value(
            parent_fd, files_fd, temporary_fd, temporary_name
        )
        _write_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)

        for index, (name, data) in enumerate(expected_files.items()):
            _atomic_write_private_at(
                temporary_fd,
                name,
                temporary_path / name,
                data,
                0o600,
            )
            _hit(fault, "after-file-write", index)

        os.fsync(temporary_fd)
        _hit(fault, "after-directory-fsync", -1)
        _hit(fault, "before-final-archive-verify", -1)
        _assert_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)
        _assert_prior_v3_intent_owns_temporary(
            intent, temporary_fd, temporary_path
        )
        _assert_prior_v3_temporary_identity(
            parent_fd, temporary_fd, attended, temporary_name
        )
        _validate_prior_v3_temporary(
            temporary_fd, temporary_path, expected_files, final=True
        )
        _assert_prior_v3_temporary_identity(
            parent_fd, temporary_fd, attended, temporary_name
        )

        try:
            _renameat2(
                parent_fd,
                temporary_name,
                parent_fd,
                PRIOR_V3_ARCHIVE_NAME,
                _RENAME_NOREPLACE,
            )
        except FileExistsError as exc:
            raise RuntimeError(
                f"prior v3 archive already exists: "
                f"{attended / PRIOR_V3_ARCHIVE_NAME}"
            ) from exc
        temporary_exists = False
        _hit(fault, "after-rename", -1)
        os.fsync(parent_fd)
        _remove_prior_v3_intent(files_fd, receipt_dir, parent_fd, intent)
        return True
    except Exception as operation_error:
        if temporary_exists and temporary_fd is not None:
            try:
                if intent is None:
                    _remove_current_unowned_empty_prior_v3_temporary(
                        parent_fd, attended, temporary_fd, temporary_name
                    )
                else:
                    _remove_owned_prior_v3_temporary(
                        parent_fd,
                        files_fd,
                        receipt_dir,
                        attended,
                        temporary_fd,
                        temporary_name,
                        expected_files,
                        intent,
                    )
            except Exception as cleanup_error:
                operation_error.add_note(
                    f"prior archive cleanup refused: {cleanup_error}"
                )
        raise
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        os.close(files_fd)
        os.close(parent_fd)


def validate_cli_paths(repo_root, receipt_dir):
    repo_root = Path(repo_root)
    receipt_dir = Path(receipt_dir)
    if repo_root != ALLOWED_REPO_ROOT:
        raise ValueError("CLI is confined to the fixed reviewed repository")
    root_parts = ALLOWED_RECEIPT_ROOT.parts
    parts = receipt_dir.parts
    remainder = parts[len(root_parts):]
    if (
        parts[: len(root_parts)] != root_parts
        or len(remainder) != 2
        or remainder[1] != "files"
        or not _ATTENDED_ID.fullmatch(remainder[0])
    ):
        raise ValueError("CLI receipt must be below the fixed private receipt root")
    return True


def prepare_private_directories(
    state_root,
    evidence_root,
    item_receipt,
    file_receipt,
):
    for path in (
        Path(state_root),
        Path(state_root) / "models",
        Path(state_root) / "review",
        Path(state_root) / "evidence",
        Path(evidence_root),
        Path(item_receipt),
        Path(evidence_root) / "photosensor",
        Path(file_receipt),
    ):
        secure_directory(path, 0o700, create=True, enforce_mode=True)
    return True


def _cli_paths(args):
    validate_cli_paths(args.repo_root, args.receipt_dir)
    evidence_root = args.receipt_dir.parent
    item_receipt = evidence_root / "item"
    return evidence_root, item_receipt


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "prepare",
            "archive-prior-v3",
            "snapshot",
            "install-code",
            "verify-code",
            "install-units",
            "verify-units",
            "restore",
            "recover",
        ),
    )
    parser.add_argument("--repo-root", type=Path, default=ALLOWED_REPO_ROOT)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence_root, item_receipt = _cli_paths(args)

    if args.command == "prepare":
        prepare_private_directories(
            ALLOWED_STATE_ROOT,
            evidence_root,
            item_receipt,
            args.receipt_dir,
        )
    elif args.command == "archive-prior-v3":
        archive_prior_v3(args.receipt_dir)
    elif args.command == "snapshot":
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
    elif args.command == "restore":
        restore(args.repo_root, args.receipt_dir)
    else:
        if not recover(args.repo_root, args.receipt_dir):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
