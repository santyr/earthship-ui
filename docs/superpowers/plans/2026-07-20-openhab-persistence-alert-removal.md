# openHAB Persistence Alert Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the external openHAB sanity checker from sending any notification derived from item persistence queries while preserving all non-persistence safety alerts.

**Architecture:** Remove persistence history from the checker's decision path rather than trying to infer health from change-only row cadence. Migrate the old `persist` state key at load time so neither an alert nor a recovery notification can escape after deployment. Exercise the real `main()` and `finish()` paths with controlled boundary responses.

**Tech Stack:** Python 3 standard library, pytest, openHAB REST boundary

## Global Constraints

- Do not query `/persistence/items/...` for notification decisions.
- Do not notify based on persisted row counts for any openHAB item.
- Do not notify when an item persistence query fails.
- Silently discard saved `persist` entries from both `active` and `last_alert`.
- Keep REST availability, rule health, current-value ranges, source freshness, and algorithm cross-verification unchanged.
- `/home/sat/openhab` is an operational directory, not a Git repository. Do not initialize Git there or copy its runtime files into `earthship-ui`.

---

## File Structure

- Create `/home/sat/openhab/tests/test_openhab_sanity_check.py`: focused regression tests for persistence-query exclusion, retained safety checks, and silent legacy-state migration.
- Modify `/home/sat/openhab/scripts/openhab_sanity_check.py`: remove persistence-derived checks and silently discard legacy persistence alert state.

### Task 1: Remove Persistence-Derived Item Notifications

**Files:**
- Create: `/home/sat/openhab/tests/test_openhab_sanity_check.py`
- Modify: `/home/sat/openhab/scripts/openhab_sanity_check.py:1-21`
- Modify: `/home/sat/openhab/scripts/openhab_sanity_check.py:87-94`
- Modify: `/home/sat/openhab/scripts/openhab_sanity_check.py:211-219`

**Interfaces:**
- Consumes: `main()`, `load_state()`, and `finish(st: dict, now: float, problems: dict)` from `openhab_sanity_check.py`.
- Produces: `load_state() -> dict` with legacy `persist` entries removed; `main()` with no `/persistence/items/...` requests or `persist` problems.

- [ ] **Step 1: Write the failing regression tests**

Create `/home/sat/openhab/tests/test_openhab_sanity_check.py`:

```python
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "openhab_sanity_check.py"


@pytest.fixture
def sanity():
    spec = importlib.util.spec_from_file_location("openhab_sanity_check_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_never_queries_item_persistence_and_keeps_safety_checks(monkeypatch, sanity):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    item_states = {
        "BMS_SOC": "101",
        "BMS_SOC_190": "75",
        "DCData_Voltage": "52",
        "BMS_Temperature": "72",
        "BMS_Capacity_Remaining_Ah": "300",
        "ConextGateway_ACPowerValue": "1000",
        "BMS_Runtime_Basis": "idle",
        "DCData_Current": "0",
        "BMS_SOC_LastUpdate": now,
        "Schneider_DCData_LastUpdate": now,
        "Forecast_Temp": "50",
    }
    calls = []

    def fake_get(path, timeout=10):
        calls.append(path)
        if path == "/items/BMS_SOC":
            return {}
        if path == "/items?fields=name,state":
            return [
                {"name": name, "state": state}
                for name, state in item_states.items()
            ]
        if path.startswith("/rules/"):
            return {"status": {"status": "IDLE", "statusDetail": "NONE"}}
        if path.startswith("/persistence/items/"):
            raise RuntimeError("persistence unavailable")
        raise AssertionError(f"unexpected REST path: {path}")

    captured = {}
    monkeypatch.setattr(sanity, "get", fake_get)
    monkeypatch.setattr(
        sanity,
        "load_state",
        lambda: {"last_alert": {}, "active": {}},
    )
    monkeypatch.setattr(
        sanity,
        "finish",
        lambda st, current, problems: captured.update(problems=dict(problems)),
    )

    sanity.main()

    assert not any(path.startswith("/persistence/items/") for path in calls)
    assert "persist" not in captured["problems"]
    assert "range:BMS_SOC" in captured["problems"]


def test_legacy_persist_state_is_discarded_without_notification(
    monkeypatch, tmp_path, sanity
):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "last_alert": {"persist": 900, "range:BMS_SOC": 900},
                "active": {"persist": True, "range:BMS_SOC": True},
            }
        )
    )
    monkeypatch.setattr(sanity, "STATE_FILE", str(state_file))

    state = sanity.load_state()

    assert state == {
        "last_alert": {"range:BMS_SOC": 900},
        "active": {"range:BMS_SOC": True},
    }

    messages = []
    monkeypatch.setattr(sanity, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(sanity, "save_state", lambda st: None)
    monkeypatch.setattr(
        sanity,
        "notify",
        lambda message: messages.append(message) or True,
    )

    with pytest.raises(SystemExit) as exited:
        sanity.finish(
            state,
            1_000,
            {"range:BMS_SOC": "BMS_SOC out of range"},
        )

    assert exited.value.code == 1
    assert messages == []
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest /home/sat/openhab/tests/test_openhab_sanity_check.py -v
```

Expected: two failures. The first reports that a `/persistence/items/...`
request occurred; the second reports that the loaded state still contains
`persist`.

- [ ] **Step 3: Implement silent state migration and remove persistence checks**

In `/home/sat/openhab/scripts/openhab_sanity_check.py`:

1. Remove `timedelta` from the `datetime` import.
2. Remove the persistence-flow entry from the module docstring.
3. Replace `load_state()` with:

```python
def load_state():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {"last_alert": {}, "active": {}}
    for bucket in ("last_alert", "active"):
        st.setdefault(bucket, {}).pop("persist", None)
    return st
```

4. Delete the complete block beginning with
   `# 7. persistence writing (DCData_Voltage changes near-continuously)` and
   ending after its `except` handler.

Do not change any other check, threshold, problem key, notification text, or
rate limit.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
pytest /home/sat/openhab/tests/test_openhab_sanity_check.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Run the existing openHAB Python test suite**

Run:

```bash
pytest /home/sat/openhab/tests -v
```

Expected: all collected Python tests pass. The JavaScript file in this
directory is not collected by pytest.

- [ ] **Step 6: Verify Python syntax**

Run:

```bash
python3 -m py_compile \
  /home/sat/openhab/scripts/openhab_sanity_check.py \
  /home/sat/openhab/tests/test_openhab_sanity_check.py
```

Expected: exit code `0` with no output.

- [ ] **Step 7: Verify the all-items boundary and preserved safety behavior**

Run:

```bash
pytest \
  /home/sat/openhab/tests/test_openhab_sanity_check.py::test_main_never_queries_item_persistence_and_keeps_safety_checks \
  -v
```

Expected: `1 passed`. This is the notification-disabled harness: it exercises
the real `main()` decision path, fails on any item-persistence request, and
proves the non-persistence `range:BMS_SOC` safety problem is still generated.

- [ ] **Step 8: Record the verified operational outcome**

After all verification passes, record in Hexmem that persistence-derived
openHAB item notifications were removed, legacy `persist` state is discarded
silently, and non-persistence safety notifications remain. Do not store
credentials, tokens, runtime logs, or temporary test progress.
