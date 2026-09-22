"""Actual boundary logic and actual provider-main orchestration, mocked Docker.

No real OpenHAB or PostgreSQL integration result is claimed by this suite.
"""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import re
import secrets
import sys
import tarfile
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("completion_boundary", ROOT / "scripts/persistence_boundary.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
START = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.seconds = 0.0
    def now(self):
        return START + timedelta(seconds=self.seconds)
    def tick(self):
        return self.seconds
    def sleep(self, seconds):
        self.seconds += seconds
    def millis(self):
        return int(self.now().timestamp() * 1000)


class Database:
    network = "container:synthetic-database"
    def __init__(self, clock):
        self.clock = clock
        self.previous = [{"time": clock.millis(), "state": "10"}]
        self.state = "10"
        self.fail_history = False
        self.persist_during_gap = False
        self.requests = []
        self.restart_failure = False
    def request(self, cid, header, path, method="GET", body=None, content_type="application/json"):
        self.requests.append((cid, path, method, body))
        assert cid == "synthetic-openhab"
        if path.startswith("/persistence/items/"):
            return (503, "private error") if self.fail_history else (200, json.dumps({"data": self.previous}))
        assert path == "/items/JDBC_Qualification_Probe/state"
        if method == "PUT":
            self.state = body
            if self.persist_during_gap:
                self.clock.sleep(0.01)
                self.previous.append({"time": self.clock.millis(), "state": body})
            return 202, ""
        return 200, self.state
    def stage(self, _cid):
        pass
    def checkpoint(self, _cid, _header, label):
        if label == "initial-file":
            self.previous = []
        self.clock.sleep(0.2)
        self.state = str(10 + len(self.previous))
        self.previous.append({"time": self.clock.millis(), "state": self.state})
    def restore(self, *_):
        pass
    def restart(self, *_):
        if self.restart_failure:
            raise RuntimeError("synthetic restart failed")


@pytest.fixture
def setup():
    clock = Clock()
    database = Database(clock)
    ledger = m.BoundaryLedger(now=clock.now, monotonic=clock.tick, sleep=clock.sleep)
    return SimpleNamespace(clock=clock, database=database, ledger=ledger)


def boundary(setup, label="file-to-managed-1"):
    setup.ledger.begin(label, setup.database.previous)
    setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"fixture header", 404)
    setup.database.checkpoint(None, None, "positive")
    return setup.ledger.finish(setup.database.previous)


def test_one_boundary_records_gap_without_source_continuity_claim(setup):
    row = boundary(setup)
    assert row["injected_updates_not_persisted"] == 1
    assert row["source_continuity_claimed"] is False
    assert row["status"] == "verified_with_collection_gap"
    assert row["unqualified_probe_window"]["end_ms"] > row["unqualified_probe_window"]["start_ms"]
    assert setup.ledger.report()["status"] == "incomplete"
    assert len(setup.database.previous) == 2
    assert all(r["state"] != "1000000" for r in setup.database.previous)


def test_four_roundtrip_boundaries_required_before_complete(setup):
    for label in ["file-to-managed-1", "managed-to-file-1", "file-to-managed-2", "managed-to-file-2"]:
        boundary(setup, label)
    setup.ledger.complete()
    report = setup.ledger.report()
    assert report["status"] == "verified_with_collection_gaps"
    assert report["injected_updates_not_persisted"] == 4
    assert report["production_migration_authorized"] is False
    for key in ["natural_source_continuity", "forecast_timeseries_behavior", "independently_written_power_restore"]:
        assert report[key] == "not_tested"


def test_configuration_only_or_partial_run_cannot_qualify(setup):
    with pytest.raises(RuntimeError):
        setup.ledger.complete()
    boundary(setup)
    with pytest.raises(RuntimeError):
        setup.ledger.complete()


def test_overlap_and_duplicate_labels_refused(setup):
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    with pytest.raises(RuntimeError):
        setup.ledger.begin("other", setup.database.previous)
    setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", 404)
    setup.database.checkpoint(None, None, "positive")
    setup.ledger.finish(setup.database.previous)
    with pytest.raises(RuntimeError):
        setup.ledger.begin("file-to-managed-1", setup.database.previous)


@pytest.mark.parametrize("status", [200, 405, 500, None, True, "404"])
def test_absence_is_observed_not_assumed(setup, status):
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    with pytest.raises(RuntimeError, match="absence"):
        setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", status)
    assert setup.database.requests == []


def test_provider_still_writing_during_absence_fails_qualification(setup):
    setup.database.persist_during_gap = True
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    with pytest.raises(RuntimeError, match="altered history"):
        setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", 404)
    assert setup.ledger.report()["status"] == "incomplete"
    assert setup.ledger.report()["unfinished_boundary"] == "file-to-managed-1"


def test_history_error_not_treated_as_an_empty_or_verified_gap(setup):
    setup.database.fail_history = True
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    with pytest.raises(RuntimeError):
        setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", 404)


@pytest.mark.parametrize("change", ["missing", "extra", "changed_prefix", "backfill", "future"])
def test_positive_recovery_rejects_invalid_history(setup, change):
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", 404)
    setup.database.checkpoint(None, None, "positive")
    rows = deepcopy(setup.database.previous)
    if change == "missing": rows.pop()
    if change == "extra": rows.append({"time": rows[-1]["time"] + 1, "state": "12"})
    if change == "changed_prefix": rows[0]["state"] = "9"
    if change == "backfill": rows[-1]["state"] = "1000000"
    if change == "future": rows[-1]["time"] += 10000
    with pytest.raises(RuntimeError):
        setup.ledger.finish(rows)
    assert setup.ledger.report()["status"] == "incomplete"


def test_clock_discontinuity_is_not_false_positive_coverage(setup):
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", 404)
    setup.database.checkpoint(None, None, "positive")
    setup.ledger.now = lambda: START - timedelta(hours=1)
    with pytest.raises(RuntimeError, match="clock"):
        setup.ledger.finish(setup.database.previous)


def test_wall_and_monotonic_divergence_fails(setup):
    setup.ledger.begin("file-to-managed-1", setup.database.previous)
    setup.ledger.exercise_absence(setup.database, "synthetic-openhab", b"", 404)
    setup.database.checkpoint(None, None, "positive")
    setup.ledger.monotonic = lambda: 1000
    with pytest.raises(RuntimeError, match="clocks diverged"):
        setup.ledger.finish(setup.database.previous)


@pytest.mark.parametrize("rows", [[], [{"time": True, "state": "10"}],
                                  [{"time": 1, "state": "NaN"}],
                                  [{"time": 1, "state": "Infinity"}],
                                  [{"time": 1, "state": 10}],
                                  [{"time": 1, "state": "10"}, {"time": 1, "state": "11"}],
                                  [{"time": 1, "state": "10", "extra": 2}]])
def test_bad_history_cannot_create_a_boundary(rows):
    with pytest.raises(RuntimeError):
        m.rows_checked(rows)


class Docker:
    """Small stateful double for the ACTUAL checked-in provider main function."""
    def __init__(self, database, expected):
        self.database = database
        self.expected = expected
        self.provider = "file"
        self.marker = None
        self.removed = False
        self.calls = []
    def run(self, args, payload=None):
        self.calls.append(args)
        if args[:2] == ["docker", "run"]:
            self.marker = next(x.split("=", 1)[1] for x in args if x.startswith("hex.persistence.qualification="))
            assert "--network" in args and args[args.index("--network") + 1] == self.database.network
            assert not any(x in args for x in ["--publish", "-p", "--privileged", "-v"])
            return b"synthetic-openhab"
        if args[:2] == ["docker", "inspect"]:
            if "--format" in args: return self.marker.encode()
            return json.dumps([{"HostConfig": {"NetworkMode": self.database.network, "Privileged": False},
                                "AppArmorProfile": "docker-default"}]).encode()
        if args[:2] == ["docker", "rm"]:
            self.removed = True
            return b""
        if "mv" in args:
            self.provider = None if args[-2].endswith("jdbc.persist") else "file"
            return b""
        if "curl" in args:
            url = next(x for x in args if x.startswith("http://"))
            if url.endswith("/rest/"): return b"{}"
            assert url == "http://127.0.0.1:8080/rest/persistence/jdbc"
            method = args[args.index("-X") + 1] if "-X" in args else "GET"
            status, body = 200, ""
            if method == "DELETE":
                if self.provider == "file": status = 405
                elif self.provider == "managed": self.provider = None
                else: status = 404
            elif method == "PUT":
                assert self.provider is None
                self.provider = "managed"
                status = 201
            elif self.provider is None:
                status = 404
            else:
                body = json.dumps({**self.expected, "editable": self.provider == "managed"})
            return (body + "\n" + str(status)).encode() if "-w" in args else body.encode()
        if "addApiToken" in args[-1]: return b"oh.synthetic-test-token"
        return b""


def provider_main_environment(tmp_path, setup):
    """Compile main's unchanged AST, avoiding import of unavailable host-only deps."""
    source = (ROOT / "scripts/qualify-persistence-file-provider.py").read_text()
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    expected = {"serviceId": "jdbc", "editable": True, "configs": []}
    path = tmp_path / "openhab/file-config/persistence/jdbc.persist"
    path.parent.mkdir(parents=True)
    path.write_text("synthetic exact config")
    docker = Docker(setup.database, expected)
    namespace = {"ROOT": tmp_path, "oh": SimpleNamespace(get=lambda _: expected),
                 "render": lambda _: "synthetic exact config", "uuid": uuid,
                 "isolated": SimpleNamespace(IMAGE="synthetic-isolated-image"),
                 "run": docker.run, "io": io, "tarfile": tarfile, "json": json,
                 "time": SimpleNamespace(sleep=setup.clock.sleep), "secrets": secrets, "re": re,
                 "BoundaryLedger": lambda: setup.ledger}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(ROOT / "scripts/qualify-persistence-file-provider.py"), "exec"), namespace)
    return namespace["main"], docker


def parse_report(output):
    line = next(line for line in output.splitlines() if line.startswith("persistence_collection_boundary_report="))
    return json.loads(line.split("=", 1)[1])


def test_actual_provider_main_exercises_four_gaps_and_cleans_up(tmp_path, setup, capsys):
    main, docker = provider_main_environment(tmp_path, setup)
    main(setup.database)
    report = parse_report(capsys.readouterr().out)
    assert report["status"] == "verified_with_collection_gaps"
    assert len(report["boundaries"]) == 4
    assert docker.removed and docker.provider == "file"
    assert len(setup.database.previous) == 5  # Existing JDBC roundtrip contract preserved.
    updates = [row for row in setup.database.requests if row[2] == "PUT"]
    assert len(updates) == 4
    assert all(row[1] == "/items/JDBC_Qualification_Probe/state" for row in updates)


def test_actual_provider_main_retains_incomplete_report_on_restart_failure(tmp_path, setup, capsys):
    setup.database.restart_failure = True
    main, docker = provider_main_environment(tmp_path, setup)
    with pytest.raises(RuntimeError, match="restart"):
        main(setup.database)
    report = parse_report(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert len(report["boundaries"]) == 4
    assert docker.removed


def test_actual_provider_main_fails_closed_and_cleans_up_on_leaking_provider(tmp_path, setup, capsys):
    setup.database.persist_during_gap = True
    main, docker = provider_main_environment(tmp_path, setup)
    with pytest.raises(RuntimeError, match="altered history"):
        main(setup.database)
    report = parse_report(capsys.readouterr().out)
    assert report["status"] == "incomplete"
    assert report["unfinished_boundary"] == "file-to-managed-1"
    assert docker.removed


def test_actual_provider_main_reports_incomplete_if_owned_cleanup_fails(tmp_path, setup, capsys):
    main, docker = provider_main_environment(tmp_path, setup)
    original = docker.run
    def fail_remove(args, payload=None):
        if args[:2] == ["docker", "rm"]:
            raise RuntimeError("synthetic cleanup failure")
        return original(args, payload)
    main.__globals__["run"] = fail_remove
    with pytest.raises(RuntimeError, match="cleanup"):
        main(setup.database)
    assert parse_report(capsys.readouterr().out)["status"] == "incomplete"
    assert not docker.removed
