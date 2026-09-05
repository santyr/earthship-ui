# Transition-aware Sanity Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track repeated charging observations within a BMS basis episode without suppressing immediate runtime faults or falsely recovering faults after unavailable reads.

**Architecture:** Import the installed external checker into the repository unchanged, prove its current faults with isolated replay tests, then change its runtime consistency check and recovery bookkeeping. Persist pending evidence in its existing JSON state alongside existing alert history; the timer and notification transport remain unchanged.

**Tech Stack:** Python standard library, unittest, existing OpenHAB REST DTOs and systemd user timer.

## Global Constraints

- Approved design: `docs/superpowers/specs/2026-09-05-change-only-alerts-design.md`. Hexmem event 8668 records the operator's September 5 approval of all pending work and supersedes that document's older pending-defaults wording. Implementation is authorized; installation belongs to the later approved release workflow, not this planning task.
- Keep JDBC everyChange and restoreOnStartup unchanged. Do not alter estimator gates, advisory thresholds, household controls, the forecast schedule, or counters.
- Task 82 remains on hold. Never send test DMs or save decrypted DM archives.
- Dwell is exactly 480 seconds between two valid observations of the same `bms` episode; charging means finite current strictly greater than 0.5 A. Two samples never establish continuous charging.
- Keep `RATE_S = 30 * 60`, rule expectations, range and scaling checks, BMS heartbeat threshold 12 minutes, Schneider threshold 5 minutes, and the existing forecast-value check.
- Tests intercept REST and notifier calls and redirect all state and log writes into temporary directories. Never execute the installed checker during testing.
- Scope is this external checker only. The sibling UI plan and the remaining historical-algorithm audit are separate work.

## Verified source and release boundary

The complete installed source was read on September 5 (225 lines):

`/home/sat/openhab/scripts/openhab_sanity_check.py`

SHA-256: `d09cc41e144e158963ad782e7bec69394448a97e0ebfe89b96d444160863119e`

The installed source reads the token only under its main guard, but `get()` currently depends on the guard-created global `TOKEN`; make that dependency lazy and explicit. Its `finish()` currently treats every absent problem as recovery, including after a REST prerequisite failure. Its single `algo:basis` key currently represents both mismatch and invalid runtime.

Verified `/home/sat/.config/systemd/user/openhab-sanity.service` executes `/usr/bin/python3 /home/sat/openhab/scripts/openhab_sanity_check.py`, accepts exit codes 0 and 1, and has a 120-second timeout. `/home/sat/.config/systemd/user/openhab-sanity.timer` has `OnBootSec=3min`, `OnUnitActiveSec=10min`, and `RandomizedDelaySec=30`. Do not modify either unit.

Existing runtime targets are `/home/sat/.local/state/openhab-sanity/state.json` and `last_run.log` in that directory. Keep the state path and existing `active` / `last_alert` entries. Add only `pending_basis` (episode, first, last). Keep `algo:basis` as the charging/legacy key, add `algo:runtime` for immediate invalid-runtime faults, and add `data:runtime` for unavailable prerequisites. Because old `algo:basis` may mean either fault, retain an active legacy key until valid evidence establishes both runtime health and absence of a charging mismatch; never manufacture an upgrade recovery.

Later release must record the exact reviewed commit and recheck this source hash. A differing installed hash requires reconciling the installed change before replacing it. Back up the installed script and state together under an explicitly recorded release backup directory, preserving permissions; record hashes and the unit files as read-only deployment evidence. Deploy only the reviewed repository script to the exact installed script path. Do not change timer cadence, enable/start units, or run the checker manually as a deployment probe: a manual run can send DMs. Verify deployment by installed-vs-reviewed hashes and the next normal timer execution. Rollback restores that release's original script and matching pre-release state during an idle timer interval; restoring the matching state avoids false transition/recovery messages. Keep newer state/logs in the release backup before rollback. Do not restore or modify credentials. This document performs none of these runtime operations.

## Task 1: Version, test, and correct the external checker

**Files:**
- Create: `openhab/scripts/openhab_sanity_check.py` (initially byte-identical installed source, then the exact edits below).
- Create: `openhab/scripts/test_openhab_sanity_check.py` (complete test file below).

**Interfaces:**
- `runtime_checks(st, now, snapshot, problems, unresolved) -> None`: observes bulk DTOs including `lastStateChange`, updates pending evidence, reports independent faults, and marks faults whose prerequisites were not evaluated.
- `finish(st, now, problems, unresolved=None) -> None`: preserves unresolved active faults, handles valid recoveries, retains per-key notification throttling, saves state, and exits with 0/1 as before.
- `pending_basis = {"episode": <finite epoch milliseconds>, "first": <epoch seconds>, "last": <epoch seconds>}`. A changed identity, noncharging/non-bms observation, unavailable input, backwards clock, or REST outage drops the old pending pair. A valid observation after a break may start a new pair immediately. No arbitrary maximum sampling gap is introduced; an observed REST outage explicitly breaks continuity.

- [ ] **Step 1: Verify and import the baseline without executing it.**

Run in the isolated implementation worktree:

```bash
sha256sum /home/sat/openhab/scripts/openhab_sanity_check.py
```

Expected hash is the value above. Read the full installed source and use `apply_patch` to add its byte-identical contents as `openhab/scripts/openhab_sanity_check.py`, following workspace editing constraints. Then run `cmp /home/sat/openhab/scripts/openhab_sanity_check.py openhab/scripts/openhab_sanity_check.py`; it must exit 0. Stop and reconcile source drift on a mismatch. Importing an unchanged baseline is setup for this task, not an implementation checkpoint or separate release.

- [ ] **Step 2: Add this complete test file before modifying checker behavior.**

```python
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("openhab_sanity_check.py")
T = 2_000_000_000.0


def load_checker():
    spec = importlib.util.spec_from_file_location("checker_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Reading credentials, network access, or notifications during import is a bug.
    with patch("builtins.open", side_effect=AssertionError("import I/O")), \
         patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
         patch("subprocess.run", side_effect=AssertionError("notifier")):
        spec.loader.exec_module(module)
    return module


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = load_checker()
        self.c.STATE_DIR = self.tmp.name
        self.c.STATE_FILE = str(Path(self.tmp.name) / "state.json")
        self.messages = []
        self.calls = []
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("live REST"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.transport = patch("subprocess.run", side_effect=AssertionError("live notifier"))
        self.transport.start()
        self.addCleanup(self.transport.stop)

    def snapshot(self, **changes):
        stamp = datetime.now(timezone.utc).isoformat()
        values = {
            "BMS_SOC": "50", "BMS_SOC_190": "50", "DCData_Voltage": "52",
            "BMS_Temperature": "68", "BMS_Temperature_Raw": "29300",
            "BMS_Capacity_Remaining_Ah": "200", "ConextGateway_ACPowerValue": "200",
            "BMS_SOC_Raw": "50", "BMS_SOC_ScaleFactor_Raw": "0",
            "BMS_Runtime_Basis": "bms", "BMS_TimeToDischarge_Smoothed": "420",
            "DCData_Current": "16.85 A", "BMS_SOC_LastUpdate": stamp,
            "Schneider_DCData_LastUpdate": stamp, "Forecast_Temp": "20",
        }
        values.update(changes)
        return [dict(name=k, state=v, lastStateChange=(T - 60) * 1000)
                for k, v in values.items()]

    def tick(self, now=T, snapshot=None, fail=None):
        rows = self.snapshot() if snapshot is None else snapshot
        def get(path, timeout=10):
            self.calls.append(path)
            if fail == "probe" and path == "/items/BMS_SOC":
                raise OSError("probe failed")
            if path.startswith("/items?"):
                if fail == "bulk":
                    raise OSError("bulk failed")
                return rows
            if path.startswith("/rules/"):
                return {"status": {"status": "IDLE", "statusDetail": "NONE"}}
            if path == "/items/BMS_SOC":
                return {"name": "BMS_SOC", "state": "50"}
            raise AssertionError(path)
        def notify(message):
            self.messages.append(message)
            return True
        with patch.object(self.c, "get", side_effect=get), \
             patch.object(self.c, "notify", side_effect=notify), \
             patch.object(self.c.time, "time", return_value=now), \
             patch("builtins.print"):
            with self.assertRaises(SystemExit) as result:
                self.c.main()
        return result.exception.code, json.loads(Path(self.c.STATE_FILE).read_text())

    def active(self, st, key):
        return bool(st["active"].get(key))

    def test_first_mismatch_waits(self):
        code, st = self.tick()
        self.assertEqual(code, 0)
        self.assertFalse(self.active(st, "algo:basis"))
        self.assertEqual(self.messages, [])
        self.assertEqual(st["pending_basis"]["first"], T)
        self.assertIn("/items?fields=name,state,lastStateChange", self.calls)

    def test_before_at_after_dwell_and_rate(self):
        self.tick()
        self.assertFalse(self.active(self.tick(T + 479)[1], "algo:basis"))
        self.assertTrue(self.active(self.tick(T + 480)[1], "algo:basis"))
        count = len(self.messages)
        self.tick(T + 600)
        self.assertEqual(len(self.messages), count)
        self.tick(T + 480 + 1800)
        self.assertEqual(len(self.messages), count + 1)
        self.assertIn("repeated charging checks", self.messages[0])
        self.assertNotIn("gate stuck", self.messages[0])

    def test_persisted_pair_survives_module_reload(self):
        self.tick()
        self.c = load_checker()
        self.c.STATE_DIR = self.tmp.name
        self.c.STATE_FILE = str(Path(self.tmp.name) / "state.json")
        self.assertTrue(self.active(self.tick(T + 600)[1], "algo:basis"))

    def test_changed_episode_and_clock_reversal_start_new_pair(self):
        self.tick()
        rows = self.snapshot()
        for row in rows:
            if row["name"] == "BMS_Runtime_Basis":
                row["lastStateChange"] += 1000
        st = self.tick(T + 600, rows)[1]
        self.assertFalse(self.active(st, "algo:basis"))
        self.assertEqual(st["pending_basis"]["first"], T + 600)
        st = self.tick(T + 500, rows)[1]
        self.assertFalse(self.active(st, "algo:basis"))
        self.assertEqual(st["pending_basis"]["first"], T + 500)

    def test_noncharging_and_non_bms_reset_and_recover(self):
        for change in ({"DCData_Current": "0.5"}, {"BMS_Runtime_Basis": "now"}):
            with self.subTest(change=change):
                self.tick(T)
                self.tick(T + 600)
                st = self.tick(T + 601, self.snapshot(**change))[1]
                self.assertFalse(self.active(st, "algo:basis"))
                self.assertNotIn("pending_basis", st)
                self.assertFalse(self.active(self.tick(T + 602)[1], "algo:basis"))

    def test_rest_gap_preserves_all_active_faults_and_breaks_pair(self):
        for failure in ("probe", "bulk"):
            with self.subTest(failure=failure):
                self.tick(T)
                st = self.tick(T + 600)[1]
                st["active"]["range:BMS_SOC"] = True
                Path(self.c.STATE_FILE).write_text(json.dumps(st))
                count = len(self.messages)
                code, st = self.tick(T + 601, fail=failure)
                self.assertEqual(code, 1)
                self.assertTrue(self.active(st, "algo:basis"))
                self.assertTrue(self.active(st, "range:BMS_SOC"))
                self.assertNotIn("pending_basis", st)
                self.assertFalse(any("recovered" in m for m in self.messages[count:]))
                count = len(self.messages)
                st = self.tick(T + 1200)[1]
                self.assertEqual(st["pending_basis"]["first"], T + 1200)
                self.assertFalse(any("recovered [algo:basis]" in m for m in self.messages[count:]))

    def test_unavailable_current_breaks_pair_and_never_recovers_active_fault(self):
        self.tick()
        self.tick(T + 600)
        for value in (None, "NULL", "UNDEF", "bad", "nan", "inf", "-inf"):
            with self.subTest(value=value):
                count = len(self.messages)
                st = self.tick(T + 601, self.snapshot(DCData_Current=value))[1]
                self.assertTrue(self.active(st, "data:runtime"))
                self.assertTrue(self.active(st, "algo:basis"))
                self.assertNotIn("pending_basis", st)
                self.assertFalse(any("recovered [algo:basis]" in m for m in self.messages[count:]))
        self.assertEqual(self.tick(T + 1200)[1]["pending_basis"]["first"], T + 1200)

    def test_missing_and_invalid_identity_are_diagnostic(self):
        for identity in (None, 0, -1, "bad", float("nan"), float("inf"), (T + 1) * 1000):
            with self.subTest(identity=identity):
                rows = self.snapshot()
                for row in rows:
                    if row["name"] == "BMS_Runtime_Basis":
                        row["lastStateChange"] = identity
                st = self.tick(T, rows)[1]
                self.assertTrue(self.active(st, "data:runtime"))
                self.assertNotIn("pending_basis", st)

    def test_invalid_runtime_is_independent_and_immediate(self):
        for basis in ("bms", "now", "evening"):
            for value in (None, "UNDEF", "bad", "nan", "inf", "-inf", "0", "-1"):
                with self.subTest(basis=basis, value=value):
                    st = self.tick(T, self.snapshot(BMS_Runtime_Basis=basis,
                                  BMS_TimeToDischarge_Smoothed=value))[1]
                    self.assertTrue(self.active(st, "algo:runtime"))
        st = self.tick(T + 600)[1]
        self.assertFalse(self.active(st, "algo:runtime"))

    def test_missing_basis_preserves_runtime_fault(self):
        self.tick(T, self.snapshot(BMS_TimeToDischarge_Smoothed="0"))
        st = self.tick(T + 600, self.snapshot(BMS_Runtime_Basis="UNDEF"))[1]
        self.assertTrue(self.active(st, "algo:runtime"))
        self.assertTrue(self.active(st, "data:runtime"))

    def test_active_basis_survives_identity_gap_and_new_episode(self):
        self.tick()
        self.tick(T + 600)
        rows = self.snapshot()
        for row in rows:
            if row["name"] == "BMS_Runtime_Basis":
                row.pop("lastStateChange")
        count = len(self.messages)
        st = self.tick(T + 601, rows)[1]
        self.assertTrue(self.active(st, "algo:basis"))
        self.assertTrue(self.active(st, "data:runtime"))
        self.assertNotIn("pending_basis", st)
        for row in rows:
            if row["name"] == "BMS_Runtime_Basis":
                row["lastStateChange"] = (T + 602) * 1000
        st = self.tick(T + 603, rows)[1]
        self.assertTrue(self.active(st, "algo:basis"))
        self.assertEqual(st["pending_basis"]["first"], T + 603)
        self.assertFalse(any("recovered [algo:basis]" in m for m in self.messages[count:]))

    def test_scale_prerequisites_do_not_recover_active_faults(self):
        self.tick(T, self.snapshot(BMS_Temperature="80", BMS_SOC="60"))
        count = len(self.messages)
        st = self.tick(T + 600, self.snapshot(BMS_Temperature_Raw="NULL",
                       BMS_SOC_Raw="NULL"))[1]
        self.assertTrue(self.active(st, "algo:temp"))
        self.assertTrue(self.active(st, "algo:soc"))
        self.assertFalse(any("recovered [algo:temp]" in m or "recovered [algo:soc]" in m
                             for m in self.messages[count:]))

    def test_legacy_key_does_not_recover_while_runtime_is_bad(self):
        Path(self.c.STATE_FILE).write_text(json.dumps({
            "active": {"algo:basis": True}, "last_alert": {"algo:basis": T - 100}}))
        st = self.tick(T, self.snapshot(DCData_Current="0", BMS_TimeToDischarge_Smoothed="0"))[1]
        self.assertTrue(self.active(st, "algo:basis"))
        self.assertTrue(self.active(st, "algo:runtime"))
        self.assertFalse(any("recovered" in m for m in self.messages))
        st = self.tick(T + 600, self.snapshot(DCData_Current="0"))[1]
        self.assertFalse(self.active(st, "algo:basis"))
        self.assertFalse(self.active(st, "algo:runtime"))

    def test_heartbeat_thresholds_and_other_checks_remain(self):
        stamp = lambda seconds: datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - seconds, timezone.utc).isoformat()
        st = self.tick(T, self.snapshot(DCData_Current="0",
                       BMS_SOC_LastUpdate=stamp(11 * 60),
                       Schneider_DCData_LastUpdate=stamp(4 * 60)))[1]
        self.assertFalse(self.active(st, "fresh:bms"))
        self.assertFalse(self.active(st, "fresh:schneider"))
        st = self.tick(T + 600, self.snapshot(DCData_Current="0", BMS_SOC="101",
                       BMS_Temperature="80", Forecast_Temp="NULL",
                       BMS_SOC_LastUpdate=stamp(13 * 60),
                       Schneider_DCData_LastUpdate=stamp(6 * 60)))[1]
        for key in ("fresh:bms", "fresh:schneider", "range:BMS_SOC",
                    "algo:temp", "algo:soc", "fresh:forecast"):
            self.assertTrue(self.active(st, key), key)
        self.assertEqual(self.c.RATE_S, 1800)
        self.assertEqual(len([p for p in self.calls if p.startswith("/rules/")]),
                         2 * len(self.c.RULES_EXPECTED))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run replay against the unchanged imported baseline and inspect meaningful RED.**

```bash
python3 -m unittest discover -s openhab/scripts -p test_openhab_sanity_check.py -v
```

Expected failures include `test_first_mismatch_waits` reporting exit 1 instead of 0 and `test_rest_gap_preserves_all_active_faults_and_breaks_pair` observing recovered active keys. These exercise the existing `main()` path with no real REST, notifier, credentials, or production state I/O; do not accept only missing-helper failures as the regression evidence.

- [ ] **Step 4: Add the following complete runtime helper code immediately before `main()`. Add `math` to the standard-library imports.**

```python
DWELL_S = 8 * 60


def finite_num(value):
    value = num(value)
    return value if value is not None and math.isfinite(value) else None


def runtime_checks(st, now, snapshot, problems, unresolved):
    basis = str(snapshot.get("BMS_Runtime_Basis", {}).get("state") or "")
    active_estimate = basis in ("bms", "now", "evening")
    basis_available = basis not in ("", "NULL", "UNDEF", "None")
    ttd = finite_num(snapshot.get("BMS_TimeToDischarge_Smoothed", {}).get("state"))
    runtime_bad = active_estimate and (ttd is None or ttd <= 0)
    if runtime_bad:
        problems["algo:runtime"] = (
            f"runtime basis '{basis}' but smoothed value is {ttd} — estimator inconsistent")
    if not basis_available:
        unresolved.add("algo:runtime")

    # Old algo:basis alerts may represent invalid runtime. Preserve that active
    # key while either old meaning is still unresolved or demonstrably faulty.
    if runtime_bad:
        unresolved.add("algo:basis")

    cur = finite_num(snapshot.get("DCData_Current", {}).get("state"))
    raw_episode = snapshot.get("BMS_Runtime_Basis", {}).get("lastStateChange")
    # OpenHAB bulk DTO lastStateChange is epoch milliseconds. Do not substitute
    # receipt time or lastStateUpdate for a missing transition identity.
    episode = None
    if isinstance(raw_episode, (int, float)) and not isinstance(raw_episode, bool):
        if math.isfinite(raw_episode) and 0 < raw_episode <= now * 1000:
            episode = raw_episode
    missing = []
    if not basis_available:
        missing.append("BMS_Runtime_Basis unavailable")
    if cur is None:
        missing.append("DCData_Current unavailable or non-finite")
    if basis == "bms" and episode is None:
        missing.append("BMS_Runtime_Basis.lastStateChange unavailable or invalid")
    if missing:
        st.pop("pending_basis", None)
        problems["data:runtime"] = "; ".join(missing)
        unresolved.add("algo:basis")
        return
    if basis != "bms" or cur <= 0.5:
        st.pop("pending_basis", None)
        return

    pending = st.get("pending_basis")
    valid_pending = isinstance(pending, dict)
    if valid_pending:
        first, last = pending.get("first"), pending.get("last")
        valid_pending = (
            pending.get("episode") == episode
            and isinstance(first, (int, float)) and not isinstance(first, bool)
            and isinstance(last, (int, float)) and not isinstance(last, bool)
            and math.isfinite(first) and math.isfinite(last)
            and 0 < first <= last <= now)
    if not valid_pending:
        st["pending_basis"] = {"episode": episode, "first": now, "last": now}
        unresolved.add("algo:basis")
        return
    pending["last"] = now
    if now > pending["first"] and now - pending["first"] >= DWELL_S:
        problems["algo:basis"] = (
            f"runtime basis remains bms during repeated charging checks "
            f"({now - pending['first']:.0f} s apart; current {cur} A)")
    else:
        unresolved.add("algo:basis")
```

- [ ] **Step 5: Apply these exact integration edits to the imported baseline.**

```diff
@@
-import json, os, subprocess, sys, time, urllib.request, urllib.error
+import json, math, os, subprocess, sys, time, urllib.request, urllib.error
@@
-    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + TOKEN})
+    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token()})
@@
     problems = {}  # key -> message
+    unresolved = set()
@@
         problems["rest"] = "openHAB REST unreachable: " + str(e)[:120]
-        finish(st, now, problems)
+        st.pop("pending_basis", None)
+        finish(st, now, problems, set(st["active"]) - {"rest"})
         return
@@
-        items = {i["name"]: i.get("state") for i in get("/items?fields=name,state")}
+        snapshot = {i["name"]: i for i in get("/items?fields=name,state,lastStateChange")}
+        items = {name: dto.get("state") for name, dto in snapshot.items()}
@@
         problems["rest"] = "items query failed: " + str(e)[:120]
-        finish(st, now, problems)
+        st.pop("pending_basis", None)
+        finish(st, now, problems, set(st["active"]) - {"rest"})
         return
@@
-    basis = str(items.get("BMS_Runtime_Basis"))
-    ttd = num(items.get("BMS_TimeToDischarge_Smoothed"))
-    cur = num(items.get("DCData_Current"))
-    if basis == "bms" and cur is not None and cur > 0.5:
-        problems["algo:basis"] = f"runtime basis 'bms' while charging at {cur} A — gate stuck?"
-    if basis in ("bms", "now", "evening") and (ttd is None or ttd <= 0):
-        problems["algo:basis"] = f"runtime basis '{basis}' but smoothed value is {ttd} — estimator inconsistent"
+    runtime_checks(st, now, snapshot, problems, unresolved)
@@
-    finish(st, now, problems)
+    finish(st, now, problems, unresolved)
@@
 if __name__ == "__main__":
-    TOKEN = token()
     main()
```

There is one import edit (Step 4's instruction and Step 5's diff describe the same edit). Also insert this complete block immediately before the existing `# 4. algorithm cross-verification` comment, so unavailable scaling prerequisites cannot falsely recover active scale faults. Preserve the existing calculations and thresholds unchanged.

```python
    temp_raw = finite_num(items.get("BMS_Temperature_Raw"))
    temp_value = finite_num(items.get("BMS_Temperature"))
    if temp_raw is None or temp_value is None or temp_raw <= 0:
        unresolved.add("algo:temp")
    soc_raw = finite_num(items.get("BMS_SOC_Raw"))
    soc_value = finite_num(items.get("BMS_SOC"))
    if soc_raw is None or soc_value is None or soc_raw == 65535:
        unresolved.add("algo:soc")
```

Preserve the rest of `main()` unchanged. A token read failure is now classified as REST unavailable and can report through the existing notifier without importing credentials during tests.

- [ ] **Step 6: Replace `finish()` with this complete implementation.**

```python
def finish(st, now, problems, unresolved=None):
    unresolved = set() if unresolved is None else unresolved
    for key in [k for k, v in st["active"].items()
                if v and k not in problems and k not in unresolved]:
        st["active"][key] = False
        st["last_alert"].pop(key, None)
        notify(f"✅ openHAB sanity: recovered [{key}]")
    for key, msg in problems.items():
        st["active"][key] = True
        last = st["last_alert"].get(key, 0)
        if now - last >= RATE_S:
            if notify("\U0001f50e openHAB sanity: " + msg):
                st["last_alert"][key] = now
    held = sorted(key for key in unresolved if st["active"].get(key) and key not in problems)
    save_state(st)
    details = list(problems.values())
    if held:
        details.append("active faults awaiting valid clearing evidence: " + ", ".join(held))
    line = datetime.now().isoformat(timespec="seconds") + " " + (
        "OK (all checks passed)" if not details else "PROBLEMS: " + "; ".join(details))
    with open(os.path.join(STATE_DIR, "last_run.log"), "a") as f:
        f.write(line + "\n")
    print(line)
    sys.exit(1 if details else 0)
```

This does not repeat stale fault messages when prerequisites fail; it retains the active record and logs that valid clearing evidence is required. REST failure holds every previously active dependent key. Runtime input failure holds the runtime keys whose clearing conditions cannot be evaluated. A missing/invalid smoothed estimate is itself a positive consistency fault, not a reason to suppress its independent alert.

- [ ] **Step 7: Run the focused tests and repository Python regression suite.**

```bash
python3 -m unittest discover -s openhab/scripts -p test_openhab_sanity_check.py -v
python3 -m unittest discover -s openhab/scripts -p 'test_*.py'
git diff --check
```

Expected: all focused tests pass, the existing Python regression suite has no new failures, and the whitespace check exits 0. Identify existing environment/dependency failures separately with the unchanged baseline if needed; do not claim a complete regression pass while failures remain unexplained. The sibling UI plan owns its production build and browser tests. Do not run the installed script or real notification transport to obtain validation.

- [ ] **Step 8: Review the exact scope and commit only the two task files.**

Review the code against the source hash and this contract: the first mismatch is silent; a valid second observation at 480 seconds may warn; episode/gap/clock/input resets discard pending evidence; active faults cannot recover on unavailable prerequisites; immediate smoothed-runtime faults retain their own key; existing heartbeat/rule/range/scale/forecast checks remain. Review test interception before running any additional replay. Review the concrete diff and test evidence independently before release.

```bash
git add openhab/scripts/openhab_sanity_check.py openhab/scripts/test_openhab_sanity_check.py
git diff --cached --check
git diff --cached --stat
git commit -m "fix: make external runtime sanity checks transition-aware"
git rev-parse HEAD
```

Record the resulting commit in the later release artifact with the source hash and backup/rollback targets above. No deployment or service change is part of this task's implementation commit.

## Self-review and decisions

The checker requirements in the approved design map to Task 1's tests and runtime/recovery changes. Existing `algo:basis` state is preserved conservatively across the split; it is not renamed or dropped. Pending evidence has no control authority and changes no estimator gates. The two-sample wording explicitly avoids claiming continuous current. No unresolved operator decisions remain for implementation; release installation follows the already approved release workflow after review and verification.
