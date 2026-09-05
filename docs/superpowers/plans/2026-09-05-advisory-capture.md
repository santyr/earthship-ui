# Default-Off Advisory Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking. Execute the single integrated task with genuine tests-first evidence, task review, and final whole-branch review.

**Goal:** Record each natural forecast decision and its existing publication/notification results without changing forecast behavior.

**Architecture:** A lazy, default-off capture helper delegates canonical records to the existing Solar_PV append-only store. Forecast integration freezes the actual decision inputs immediately before publication and observes existing calls; capture never owns or retries those calls. One decision and at most three result insert attempts per run, with no queue or retries.

**Tech Stack:** Existing Python, pytest, immutable advisory builders, Solar_PV AdvisoryStore. No new dependency.

## Global constraints

- Approved spec: docs/superpowers/specs/2026-09-05-advisory-outcomes-design.md. Task82 remains held.
- Threshold values, advisory selection, DM eligibility/deduplication/content, the06:40 schedule, household controls, BMS counters and thermal authority remain unchanged.
- No producer activation, runtime grant, service/configuration change, production database write, test DM or deployment in this implementation task.
- Preserve everyChange/restoreOnStartup. Outcome assessment, change-aware measurements, delayed scoring and bandit tuning remain separate unfinished work.
- Capture uses only exact enabled value ADVISORY_CAPTURE_ENABLED=1. Disabled operation never imports the Solar_PV storage package, reads source/configuration files for capture, generates capture IDs or opens a connection.
- Enabled configuration requires ADVISORY_CAPTURE_DSN and ADVISORY_CAPTURE_BANK_EPOCH. The existing strict store validates DSN; no JDBC/ambient credential discovery, fallback DB, retry queue or new local store.
- Keep source revision tied to the actual forecast source bytes (SHA-256), policy version forecast-intel-thermal-v1, recorded IANA timezone SITE_TZ_NAME and actual prediction day used by the existing invocation.
- Setup, validation, clock and storage exceptions become constant capture-gap diagnostics; never persist exception text, secrets, message content, recipients or raw notifier output.
- Publication accepted means the existing PUT returned; failed means HTTPError was reported; other exceptions mean unknown. None proves display or hardware effect.
- Notification reported-success uses the existing DM sent marker regardless of return code. Without that marker, nonzero return code means attempted_failed; zero or exceptions mean attempted_unknown. Missing records remain unknown after crashes; never infer success.
- Runtime writes only immutable decisions/results via the existing bounded adapter. No automatic retries. A new natural invocation gets a fresh UUID; storage idempotency remains the adapter's existing exact-record contract.

## Context and boundaries

Worktree /home/sat/earthship-ui/.worktrees/advisory-capture, branch feat/advisory-capture, base54b8ca3fc568c24c4d3353ebdef98f2ad05cb07d. Baseline132tests pass0.19s for forecast_intel, advisory_records and advisory_windows.

Schema0002 is already installed; Solar_PV main3b82b94 owns AdvisoryStore. That does not enable this producer. Runtime activation later requires installing advisory_capture.py plus advisory_records.py and advisory_windows.py beside the installed forecast script, installing Solar_PV analytics on its explicit Python path, a least-privilege role and protected DSN environment, and the approved assessors before enabling capture. Do not assume repository paths are runtime paths. Do not change the installed script now.

### Task 1: Default-off helper and existing side-effect observers

**Files:** Create openhab/scripts/advisory_capture.py and openhab/scripts/test_advisory_capture.py; modify openhab/scripts/forecast_intel.py. Existing covering tests: openhab/scripts/test_forecast_intel.py, test_advisory_records.py, test_advisory_windows.py.

**Interfaces:** start_capture(*, decision, diagnostics, source_path, environ=None, store_factory=None, clock=None, identity_factory=None) returns None or a session exposing publication(target,status) and notification(status). Decision is the existing builder arguments except generated identity/time/source_revision/policy_version/bank_epoch. diagnostics is the existing run's list of strings. safe_put retains its positional API and boolean result; adds optional keyword-only observer receiving a closed publication status.

- [ ] Add regression tests before implementation. Use imports inside tests so the missing helper is a test failure rather than hiding all test collection. Start with this complete helper test body:

```python
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
```

- [ ] Run the new file and record actual RED failures before writing production code:

```bash
PYTHONPATH=$PWD/openhab/scripts python3 -m pytest openhab/scripts/test_advisory_capture.py -q
```

- [ ] Create the helper with this implementation:

```python
"""Default-off, bounded observational capture; never owns forecast side effects."""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from advisory_records import build_decision_record, build_result_record

POLICY_VERSION = "forecast-intel-thermal-v1"


def _make_store(dsn):
    from earthship_energy.advisory_store import AdvisoryStore
    return AdvisoryStore(dsn)


class _Capture:
    def __init__(self, store, decision_id, diagnostics, clock, identity_factory):
        self.store, self.decision_id = store, decision_id
        self.diagnostics, self.clock = diagnostics, clock
        self.identity_factory = identity_factory

    def _result(self, kind, target, status):
        try:
            encoded = build_result_record(result_id=self.identity_factory(),
                decision_id=self.decision_id, observed_at=self.clock(),
                kind=kind, target=target, status=status)
            self.store.put_result(encoded)
        except Exception:
            self.diagnostics.append("advisory capture gap: result")

    def publication(self, target, status):
        self._result("publication", target, status)

    def notification(self, status):
        self._result("notification", "deep_cycle_dm", status)


def start_capture(*, decision, diagnostics, source_path, environ=None,
                  store_factory=None, clock=None, identity_factory=None):
    env = os.environ if environ is None else environ
    if env.get("ADVISORY_CAPTURE_ENABLED") != "1":
        return None
    try:
        clock = clock or (lambda: datetime.now(timezone.utc))
        identity_factory = identity_factory or uuid4
        decision_id = identity_factory()
        encoded = build_decision_record(**decision, decision_id=decision_id,
            issued_at=clock(), source_revision=hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
            policy_version=POLICY_VERSION, bank_epoch=env["ADVISORY_CAPTURE_BANK_EPOCH"])
        store = (store_factory or _make_store)(env["ADVISORY_CAPTURE_DSN"])
        store.put_decision(encoded)
        return _Capture(store, decision_id, diagnostics, clock, identity_factory)
    except Exception:
        diagnostics.append("advisory capture gap: decision")
        return None
```

- [ ] Add explicit urllib.error import and shared threshold constants to forecast_intel.py:

```python
import urllib.error
CLOSE_UP_HIGH_F, CLOSE_UP_STREAK_F, VENT_HIGH_F = 95, 92, 90
```

Replace safe_put with the exact preserved interface plus observer:

```python
def safe_put(item, value, failures=None, *, observer=None):
    """PUT once, preserve boolean/failure-list behavior, optionally observe result."""
    status, succeeded = "unknown", False
    try:
        oh_put_state(item, value)
        status, succeeded = "accepted", True
    except Exception as e:
        status = "failed" if isinstance(e, urllib.error.HTTPError) else "unknown"
        print(f"PUT failed for {item}: {e}", file=sys.stderr)
        if failures is not None:
            failures.append(item)
    if observer is not None:
        try:
            observer(status)
        except Exception:
            print("advisory capture gap: publication observer", file=sys.stderr)
    return succeeded
```

Immediately after put_failed initialization add capture=None; replace nested put:

```python
    capture = None
    def put(item, value):
        if capture is not None and item in {"Thermal_Advisory", "Predicted_SoC_Trough_Tomorrow"}:
            return safe_put(item, value, put_failed,
                            observer=lambda status: capture.publication(item, status))
        return safe_put(item, value, put_failed)
```

Use the new constants in the existing advisory comparisons and streak suffix test, preserving all f-string text:

```python
    if t_high >= CLOSE_UP_HIGH_F or streak3 >= CLOSE_UP_STREAK_F:
        advisory = f"close_up_tomorrow|Close up tomorrow — {t_high:.0f}° forecast" + (f", {streak3:.0f}° 3-day streak" if streak3 >= CLOSE_UP_STREAK_F else "")
    elif t_high >= VENT_HIGH_F:
        advisory = f"vent_tonight|Vent tonight — {t_high:.0f}° tomorrow, pre-cool the mass"
    else:
        advisory = "none|No thermal action needed"
```

Immediately before the existing publication loop add:

```python
    notification_eligible = trough_pred < TROUGH_DM_THRESHOLD
    notification_suppressed = notification_eligible and st["dm_sent"].get(today.isoformat()) == True
    if os.environ.get("ADVISORY_CAPTURE_ENABLED") == "1":
        try:
            from advisory_capture import start_capture
            capture = start_capture(diagnostics=log, source_path=__file__, decision={
                "site_timezone": SITE_TZ_NAME, "prediction_day": today,
                "advisory": advisory.split("|")[0],
                "notification_eligible": notification_eligible,
                "notification_suppressed": notification_suppressed,
                "inputs": {
                    "weather_today_high_raw_f": highs[0], "weather_today_low_raw_f": lows[0],
                    "tomorrow_high_raw_f": highs[1], "tomorrow_low_raw_f": lows[1],
                    "tomorrow_high_corrected_f": t_high, "tomorrow_low_corrected_f": lows[1] - b_lo,
                    "high_bias_f": b_hi, "low_bias_f": b_lo, "next_three_highs_raw_f": highs[1:4],
                    "three_day_high_mean_corrected_f": streak3,
                    "pv_today_kwh": pv_pred, "trough_tomorrow_pct": trough_pred,
                },
                "thresholds": {"close_up_high_f": CLOSE_UP_HIGH_F, "close_up_streak_f": CLOSE_UP_STREAK_F,
                               "vent_high_f": VENT_HIGH_F, "trough_dm_pct": TROUGH_DM_THRESHOLD},
            })
        except Exception:
            log.append("advisory capture gap: setup")
```

Keep the existing DM condition, subprocess arguments/content/timeout and marker update unchanged. Add status initialization before it, result assignments inside it, and one observation after it:

```python
    notification_status = ("not_eligible" if not notification_eligible else
                           "suppressed" if notification_suppressed else "attempted_unknown")
```

Inside the existing DM sent branch, after the unchanged marker assignment:

```python
                notification_status = "attempted_reported_success"
            else:
                notification_status = "attempted_failed" if out.returncode != 0 else "attempted_unknown"
```

After the existing exception handler and before PV-days work:

```python
    if capture is not None:
        capture.notification(notification_status)
```

- [ ] Run the focused new tests, then all covering files. Preserve actual warnings and results:

```bash
PYTHONPATH=$PWD/openhab/scripts python3 -m pytest openhab/scripts/test_advisory_capture.py openhab/scripts/test_forecast_intel.py openhab/scripts/test_advisory_records.py openhab/scripts/test_advisory_windows.py -q
git diff --check
```

- [ ] Self-review exact preserved notification text and PUT order against base54b8ca3. Commit only the three implementation/test files. Write .superpowers/sdd/advisory-capture-task-1-report.md with exact RED/GREEN commands, results, warning text, commit and concerns. No production invocation or activation. Coordinator packages the full pre-dispatch-base range for independent task review, then final whole-branch review.
