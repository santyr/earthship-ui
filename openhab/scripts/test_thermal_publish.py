from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

import thermal_intel
from test_thermal_schema import valid_shadow_payload
from thermal_model.pipeline import build_unavailable_shadow
from thermal_model.schema import validate_shadow_output


NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
GOLDEN_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests/fixtures/thermal-shadow-v1-available.json"
)


def test_shared_cross_language_available_v1_golden_is_canonical():
    payload = json.loads(GOLDEN_PATH.read_text())

    assert validate_shadow_output(payload) is payload
    assert payload == valid_shadow_payload()


def test_publish_validates_and_puts_exactly_one_compact_shadow_state():
    payload = valid_shadow_payload()
    calls = []

    encoded = thermal_intel.publish_shadow_output(
        payload,
        put_state=lambda item, value: calls.append((item, value)),
    )

    assert calls == [
        (
            "Thermal_Model_JSON",
            json.dumps(payload, separators=(",", ":")),
        )
    ]
    assert encoded == calls[0][1]
    assert len(encoded.encode("utf-8")) < 16 * 1024
    assert "Thermal_Advisory" not in encoded


@pytest.mark.parametrize(
    "payload",
    [
        {**valid_shadow_payload(), "status": "live"},
        {**valid_shadow_payload(), "commands": ["OPEN"]},
        {**valid_shadow_payload(), "reasons": ["x" * (16 * 1024)]},
    ],
    ids=["invalid-status", "actuator-field", "over-16-kib"],
)
def test_publish_rejects_invalid_or_oversized_payload_before_transport(payload):
    calls = []

    with pytest.raises(ValueError):
        thermal_intel.publish_shadow_output(
            payload,
            put_state=lambda item, value: calls.append((item, value)),
        )

    assert calls == []


def test_publish_rejects_valid_unavailable_shadow_before_transport():
    unavailable = build_unavailable_shadow(now=NOW, reasons=("forecast unavailable",))
    calls = []

    with pytest.raises(ValueError, match="unavailable"):
        thermal_intel.publish_shadow_output(
            unavailable,
            put_state=lambda item, value: calls.append((item, value)),
        )

    assert calls == []


def test_publish_propagates_ambiguous_transport_failure_without_retry():
    calls = []

    def ambiguous(item, value):
        calls.append((item, value))
        raise RuntimeError("connection closed after request body")

    with pytest.raises(RuntimeError, match="connection closed"):
        thermal_intel.publish_shadow_output(
            valid_shadow_payload(),
            put_state=ambiguous,
        )

    assert len(calls) == 1
    assert calls[0][0] == "Thermal_Model_JSON"


def test_shadow_publish_keeps_valid_local_output_when_the_single_put_fails(
    tmp_path, monkeypatch
):
    payload = valid_shadow_payload()
    destination = tmp_path / "shadow.json"
    calls = []

    monkeypatch.setattr(thermal_intel.forecast_intel, "load_site_settings", lambda: {})
    monkeypatch.setattr(thermal_intel, "_current_states", lambda now: {})
    monkeypatch.setattr(thermal_intel.forecast_intel, "fetch_forecast", lambda: {})
    monkeypatch.setattr(thermal_intel, "_forecast_rows", lambda snapshot, now: [])
    monkeypatch.setattr(thermal_intel, "run_shadow", lambda **kwargs: deepcopy(payload))

    def ambiguous(item, value):
        calls.append((item, value))
        raise RuntimeError("ambiguous OpenHAB response")

    with pytest.raises(RuntimeError, match="ambiguous"):
        thermal_intel._shadow(
            SimpleNamespace(output=destination, publish=True),
            NOW,
            put_state=ambiguous,
        )

    assert len(calls) == 1
    assert calls[0][0] == "Thermal_Model_JSON"
    assert json.loads(destination.read_text()) == payload


def test_shadow_publish_flag_is_explicit_and_defaults_off():
    parser = thermal_intel._build_parser()

    assert parser.parse_args(["shadow"]).publish is False
    assert parser.parse_args(["shadow", "--publish"]).publish is True



def _copy_runtime_manifest(destination):
    source_root = Path(thermal_intel.__file__).resolve().parent
    for relative in thermal_intel.RUNTIME_REVISION_PATHS:
        source = source_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_runtime_revision_manifest_is_exact_and_complete():
    assert thermal_intel.RUNTIME_REVISION_PATHS == (
        "thermal_intel.py",
        "forecast_intel.py",
        "thermal_model/__init__.py",
        "thermal_model/actions.py",
        "thermal_model/artifacts.py",
        "thermal_model/behavior.py",
        "thermal_model/dataset.py",
        "thermal_model/dynamics.py",
        "thermal_model/evaluation.py",
        "thermal_model/journal.py",
        "thermal_model/pipeline.py",
        "thermal_model/schema.py",
    )


def test_runtime_revision_changes_for_entrypoint_and_shared_helper(tmp_path):
    _copy_runtime_manifest(tmp_path)
    original = thermal_intel._runtime_manifest_revision(tmp_path)
    assert len(original) == 64

    entrypoint = tmp_path / "thermal_intel.py"
    entrypoint.write_bytes(entrypoint.read_bytes() + b"\n# reviewed entrypoint change\n")
    assert thermal_intel._runtime_manifest_revision(tmp_path) != original

    _copy_runtime_manifest(tmp_path)
    shared = tmp_path / "forecast_intel.py"
    shared.write_bytes(shared.read_bytes() + b"\n# reviewed helper change\n")
    assert thermal_intel._runtime_manifest_revision(tmp_path) != original


def test_runtime_revision_ignores_unrelated_git_discovery(tmp_path):
    _copy_runtime_manifest(tmp_path)
    expected = thermal_intel._runtime_manifest_revision(tmp_path)
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/unrelated\n")
    assert thermal_intel._runtime_manifest_revision(tmp_path) == expected
    (git / "HEAD").write_text("deadbeef\n")
    assert thermal_intel._runtime_manifest_revision(tmp_path) == expected


def test_runtime_revision_fails_closed_when_manifest_file_is_missing(tmp_path):
    _copy_runtime_manifest(tmp_path)
    (tmp_path / "forecast_intel.py").unlink()
    with pytest.raises(RuntimeError, match="runtime revision file unavailable"):
        thermal_intel._runtime_manifest_revision(tmp_path)
