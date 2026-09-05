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
