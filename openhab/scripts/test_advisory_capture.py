import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
import forecast_intel as fi
from test_advisory_records import arguments
from test_forecast_intel import _snapshot


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


@pytest.mark.parametrize("failure,status", [(None, "accepted"), (HTTPError("redacted", 503, "error", {}, None), "failed"), (TimeoutError(), "unknown")])
def test_safe_put_observes_reported_result_without_replay(monkeypatch, failure, status):
    attempts, states, failed = [], [], []
    def put(item, value):
        attempts.append((item, value))
        if failure: raise failure
    monkeypatch.setattr(fi, "oh_put_state", put)
    assert fi.safe_put("Thermal_Advisory", "none", failed, observer=states.append) is (failure is None)
    assert attempts == [("Thermal_Advisory", "none")]
    assert states == [status]
    assert failed == ([] if failure is None else ["Thermal_Advisory"])


def test_observer_failure_does_not_change_put_result(monkeypatch, capsys):
    monkeypatch.setattr(fi, "oh_put_state", lambda *args: None)
    def bad(status): raise RuntimeError("PRIVATE-CREDENTIAL-SENTINEL")
    assert fi.safe_put("Thermal_Advisory", "none", observer=bad) is True
    assert "PRIVATE" not in capsys.readouterr().err


def run_main(monkeypatch, tmp_path, *, active, highs, low_resource=False,
             suppressed=False, notifier="success", fail_store=None):
    import advisory_capture as ac
    store = Store(fail_store)
    state = {"k_res": 1.0, "d_direct": 4.0, "predictions": {}, "pv_errors": [],
             "trough_errors": [], "dm_sent": {fi.date.today().isoformat(): True} if suppressed else {},
             "kalman": {"hi": {"b": 3.0, "P": 1.0}, "lo": {"b": 7.0, "P": 1.0}}}
    puts, notifications = [], []
    snapshot = _snapshot()
    snapshot["daily"]["temperature_2m_max"][1:4] = highs
    snapshot["daily"]["shortwave_radiation_sum"][0] = 0 if low_resource else 25
    monkeypatch.setenv("ADVISORY_CAPTURE_ENABLED", "1" if active else "0")
    monkeypatch.setenv("ADVISORY_CAPTURE_DSN", "test-only")
    monkeypatch.setenv("ADVISORY_CAPTURE_BANK_EPOCH", "discover_4_module_2026")
    monkeypatch.setattr(ac, "_make_store", lambda dsn: store)
    monkeypatch.setattr(fi, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fi, "load_state", lambda: state)
    monkeypatch.setattr(fi, "save_state", lambda value: None)
    monkeypatch.setattr(fi, "score_hourly_targets", lambda *args: 0)
    monkeypatch.setattr(fi, "capture_next_day_hourly", lambda *args: {})
    monkeypatch.setattr(fi, "measured_day_weather", lambda *args: (None, None, None))
    monkeypatch.setattr(fi, "measured_trough", lambda *args: None if low_resource else 85)
    monkeypatch.setattr(fi, "oh_get", lambda *args: {"state": "20" if low_resource else "82"})
    monkeypatch.setattr(fi, "oh_put_state", lambda item, value: puts.append((item, value)))
    monkeypatch.setattr(fi, "fetch_forecast", lambda: snapshot)
    monkeypatch.setattr(fi, "build_json_items", lambda **kwargs: None)
    def notify(args, **kwargs):
        notifications.append((args, kwargs))
        if notifier == "exception": raise TimeoutError("PRIVATE-CREDENTIAL-SENTINEL")
        return SimpleNamespace(stdout="DM sent" if notifier == "success" else "",
                               stderr="", returncode=1 if notifier == "failure" else 0)
    monkeypatch.setattr(fi.subprocess, "run", notify)
    fi.main()
    return copy.deepcopy(state), puts, notifications, store.records


@pytest.mark.parametrize("highs,advisory", [([98,83,83], "close_up_tomorrow"), ([95,95,95], "close_up_tomorrow"), ([93,83,83], "vent_tonight"), ([92,83,83], "none")])
def test_main_golden_behavior_and_exact_learned_inputs(monkeypatch, tmp_path, highs, advisory):
    off = run_main(monkeypatch, tmp_path, active=False, highs=highs)
    on = run_main(monkeypatch, tmp_path, active=True, highs=highs)
    assert off[:3] == on[:3]
    assert off[3] == []
    origin, *results = on[3]
    assert origin["advisory"] == advisory
    assert origin["inputs"]["tomorrow_high_corrected_f"] == highs[0] - 3
    assert origin["inputs"]["tomorrow_low_corrected_f"] == 53
    assert origin["inputs"]["high_bias_f"] == 3
    assert origin["inputs"]["low_bias_f"] == 7
    assert origin["thresholds"] == {"close_up_high_f": 95, "close_up_streak_f": 92, "vent_high_f": 90, "trough_dm_pct": 30}
    assert [(r["target"],r["status"]) for r in results] == [("Predicted_SoC_Trough_Tomorrow","accepted"),("Thermal_Advisory","accepted"),("deep_cycle_dm","not_eligible")]


@pytest.mark.parametrize("suppressed,notifier,status", [(True,"success","suppressed"),(False,"success","attempted_reported_success"),(False,"failure","attempted_failed"),(False,"unknown","attempted_unknown"),(False,"exception","attempted_unknown")])
def test_notification_capture_never_changes_calls_or_markers(monkeypatch,tmp_path,suppressed,notifier,status):
    args=dict(highs=[92,83,83],low_resource=True,suppressed=suppressed,notifier=notifier)
    off=run_main(monkeypatch,tmp_path,active=False,**args)
    on=run_main(monkeypatch,tmp_path,active=True,**args)
    assert off[:3] == on[:3]
    assert len(on[2]) == (0 if suppressed else 1)
    assert on[3][-1]["status"] == status
    assert "PRIVATE-CREDENTIAL-SENTINEL" not in json.dumps(on[3])


@pytest.mark.parametrize("failure", ["decision","result"])
def test_store_failure_preserves_existing_main_behavior(monkeypatch,tmp_path,failure):
    args=dict(highs=[93,83,83],low_resource=True)
    off=run_main(monkeypatch,tmp_path,active=False,**args)
    on=run_main(monkeypatch,tmp_path,active=True,fail_store=failure,**args)
    assert off[:3] == on[:3]
    assert "advisory capture gap:" in (tmp_path / "log").read_text()
