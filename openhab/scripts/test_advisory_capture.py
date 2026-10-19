import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from test_advisory_records import arguments


class Store:
    def __init__(self, fail=None):
        self.records = []
        self.fail = fail

    def put_decision(self, encoded):
        if self.fail == "decision":
            raise RuntimeError("PRIVATE-CREDENTIAL-SENTINEL")
        self.records.append(json.loads(encoded))
        return True

    def put_result(self, encoded):
        if self.fail == "result":
            raise RuntimeError("PRIVATE-CREDENTIAL-SENTINEL")
        self.records.append(json.loads(encoded))
        return True


def decision():
    values = arguments()
    for key in ("decision_id", "issued_at", "source_revision", "policy_version", "bank_epoch"):
        values.pop(key)
    return values


def enabled():
    return {"ADVISORY_CAPTURE_ENABLED": "1", "ADVISORY_CAPTURE_DSN": "test-only",
            "ADVISORY_CAPTURE_BANK_EPOCH": "discover_4_module_2026"}


def start(store, diagnostics, **changes):
    from advisory_capture import start_capture
    options = dict(decision=decision(), diagnostics=diagnostics,
                   source_path=__file__, environ=enabled(), store_factory=lambda dsn: store,
                   clock=lambda: datetime(2026, 9, 5, 12, 40, tzinfo=timezone.utc))
    options.update(changes)
    return start_capture(**options)


@pytest.mark.parametrize("flag", [None, "", "0", "true"])
def test_disabled_capture_touches_no_dependencies(flag):
    def forbidden(*args):
        raise AssertionError("disabled dependency touched")
    diagnostics = []
    env = {} if flag is None else {"ADVISORY_CAPTURE_ENABLED": flag}
    assert start(Store(), diagnostics, environ=env, source_path="/missing/source",
                 store_factory=forbidden, clock=forbidden, identity_factory=forbidden) is None
    assert diagnostics == []


def test_decision_precedes_results_and_freezes_inputs():
    store, diagnostics = Store(), []
    values = decision()
    capture = start(store, diagnostics, decision=values)
    assert len(store.records) == 1
    values["inputs"]["next_three_highs_raw_f"][0] = 999
    capture.publication("Thermal_Advisory", "accepted")
    capture.publication("Predicted_SoC_Trough_Tomorrow", "unknown")
    capture.notification("not_eligible")
    assert [r["record_type"] for r in store.records] == ["advisory_decision"] + ["advisory_result"] * 3
    origin = store.records[0]
    assert origin["inputs"]["next_three_highs_raw_f"][0] == 94
    assert origin["policy_version"] == "forecast-intel-thermal-v1"
    assert origin["source_revision"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert all(r["decision_id"] == origin["decision_id"] for r in store.records)
    assert len({r["result_id"] for r in store.records[1:]}) == 3
    assert diagnostics == []


def test_new_natural_run_has_fresh_identity():
    store = Store()
    start(store, [])
    start(store, [])
    assert store.records[0]["decision_id"] != store.records[1]["decision_id"]


@pytest.mark.parametrize("fault", ["decision", "result", "missing_config", "invalid_input", "clock", "source"])
def test_capture_failures_are_bounded_and_secret_safe(fault):
    store, diagnostics = Store(fault), []
    changes = {}
    if fault == "missing_config": changes["environ"] = {"ADVISORY_CAPTURE_ENABLED": "1"}
    if fault == "invalid_input":
        changes["decision"] = decision()
        changes["decision"]["inputs"]["pv_today_kwh"] = float("nan")
    if fault == "clock": changes["clock"] = lambda: datetime(2026, 9, 5)
    if fault == "source": changes["source_path"] = "/missing/source"
    capture = start(store, diagnostics, **changes)
    if fault == "result":
        capture.notification("attempted_unknown")
        assert len(store.records) == 1
    else:
        assert capture is None
        assert store.records == []
    assert len(diagnostics) == 1
    assert diagnostics[0].startswith("advisory capture gap:")
    assert "PRIVATE" not in diagnostics[0]
