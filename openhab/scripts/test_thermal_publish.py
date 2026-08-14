from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
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
