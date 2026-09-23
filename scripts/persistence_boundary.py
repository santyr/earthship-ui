"""Conservative collection-gap accounting for the DISPOSABLE JDBC rehearsal.

Called only by qualify-persistence-file-provider.py after isolation checks. Each
handoff injects one synthetic Number update while the provider is absent, then
requires an exact history prefix and a positive persisted write after recovery.
It does not backfill, bridge, or claim continuity for real sensor observations.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import time

PROBE = "JDBC_Qualification_Probe"


def rows_checked(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise RuntimeError("boundary requires a bounded nonempty verified history")
    previous = -1
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"time", "state"}:
            raise RuntimeError("unexpected synthetic history row")
        if type(row["time"]) is not int or row["time"] <= previous:
            raise RuntimeError("synthetic history timestamps must be increasing integers")
        if not isinstance(row["state"], str):
            raise RuntimeError("synthetic history state must be text")
        try:
            number = Decimal(row["state"])
            if not number.is_finite():
                raise InvalidOperation()
        except InvalidOperation as exc:
            raise RuntimeError("synthetic history state is nonnumeric") from exc
        previous = row["time"]
    return deepcopy(rows)


def utc(value):
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None):
        raise RuntimeError("boundary clock must be timezone-aware")
    return value.astimezone(timezone.utc)


class BoundaryLedger:
    def __init__(self, *, now=None, monotonic=None, sleep=None):
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.sleep = sleep or time.sleep
        self.completed = []
        self.pending = None
        self.suite_complete = False
        self.forecast_timeseries_behavior = "not_tested"
        self.independently_written_power_restore = "not_tested"

    def begin(self, label, before):
        if self.pending is not None or self.suite_complete:
            raise RuntimeError("overlapping or already completed boundary ledger")
        if not isinstance(label, str) or not label or label in {r["label"] for r in self.completed}:
            raise RuntimeError("invalid or duplicate boundary label")
        rows = rows_checked(before)
        started = utc(self.now())
        if rows[-1]["time"] > int(started.timestamp() * 1000):
            raise RuntimeError("pre-cutover history is future-dated")
        tick = self.monotonic()
        if not isinstance(tick, (int, float)) or not math.isfinite(tick):
            raise RuntimeError("invalid monotonic boundary clock")
        self.pending = {"label": label, "before": rows, "started": started,
                        "tick": tick, "absent_at": None, "missed_state": None}

    def exercise_absence(self, database, cid, header, observed_status):
        if self.pending is None or self.pending["absent_at"] is not None:
            raise RuntimeError("absent-provider probe is out of sequence")
        if type(observed_status) is not int or observed_status != 404:
            raise RuntimeError("provider absence must be observed before injecting the test update")
        pending = self.pending
        pending["absent_at"] = utc(self.now())
        value = str(1000000 + len(self.completed))
        status, _ = database.request(cid, header, "/items/" + PROBE + "/state",
                                     "PUT", value, "text/plain")
        if status != 202:
            raise RuntimeError("isolated gap probe update was not accepted")
        for _ in range(10):
            status, body = database.request(cid, header, "/items/" + PROBE + "/state")
            if status == 200 and body == value:
                break
            self.sleep(0.1)
        else:
            raise RuntimeError("isolated gap probe never reached the test Item")
        # Repetition is a bounded negative observation, not timeless proof.
        # The subsequent exact post-cutover prefix catches delayed writes too.
        for _ in range(3):
            self.sleep(1)
            status, body = database.request(cid, header,
                "/persistence/items/" + PROBE + "?serviceId=jdbc")
            try:
                actual = json.loads(body)["data"] if status == 200 else None
            except (ValueError, TypeError, KeyError) as exc:
                raise RuntimeError("gap probe history could not be verified") from exc
            if actual != pending["before"]:
                raise RuntimeError("absent-provider update altered history; handoff remains unqualified")
        pending["missed_state"] = value

    def finish(self, after):
        if self.pending is None or self.pending["missed_state"] is None:
            raise RuntimeError("positive recovery cannot precede a verified absent-provider probe")
        pending = self.pending
        rows = rows_checked(after)
        before = pending["before"]
        if rows[:-1] != before or len(rows) != len(before) + 1:
            raise RuntimeError("recovery must preserve the exact prefix and append one positive control")
        if any(Decimal(row["state"]) == Decimal(pending["missed_state"]) for row in rows):
            raise RuntimeError("a provider-gap update was unexpectedly persisted or backfilled")
        ended = utc(self.now())
        duration = self.monotonic() - pending["tick"]
        if (not math.isfinite(duration) or duration < 0
                or not pending["started"] <= pending["absent_at"] <= ended):
            raise RuntimeError("clock discontinuity prevents collection-boundary qualification")
        wall_duration = (ended - pending["started"]).total_seconds()
        # Clock skew is not silently converted into negative/optimistic coverage.
        if abs(wall_duration - duration) > 1:
            raise RuntimeError("wall/monotonic clocks diverged during provider handoff")
        if not int(pending["absent_at"].timestamp() * 1000) <= rows[-1]["time"] <= int(ended.timestamp() * 1000):
            raise RuntimeError("positive recovery timestamp is outside the observed handoff window")
        record = {"label": pending["label"], "status": "verified_with_collection_gap",
                  "started_at": pending["started"].isoformat(),
                  "provider_absent_observed_at": pending["absent_at"].isoformat(),
                  "positive_write_verified_at": ended.isoformat(),
                  "elapsed_seconds": round(duration, 6),
                  "last_verified_before_ms": before[-1]["time"],
                  "first_verified_after_ms": rows[-1]["time"],
                  "unqualified_probe_window": {"start_ms": before[-1]["time"], "end_ms": rows[-1]["time"]},
                  "injected_updates_not_persisted": 1,
                  "history_prefix_preserved": True,
                  "source_continuity_claimed": False}
        self.completed.append(record)
        self.pending = None
        return deepcopy(record)

    def complete(self):
        expected = ["file-to-managed-1", "managed-to-file-1",
                    "file-to-managed-2", "managed-to-file-2"]
        if self.pending is not None or [r["label"] for r in self.completed] != expected:
            raise RuntimeError("all four ordered provider boundaries must be qualified")
        self.suite_complete = True

    def report(self):
        return {"version": 1, "scope": "isolated_synthetic_probe_provider_handoffs",
                "status": "verified_with_collection_gaps" if self.suite_complete else "incomplete",
                "boundaries": deepcopy(self.completed),
                "unfinished_boundary": self.pending["label"] if self.pending else None,
                "injected_updates_not_persisted": len(self.completed),
                "production_migration_authorized": False,
                "natural_source_continuity": "not_tested",
                "forecast_timeseries_behavior": self.forecast_timeseries_behavior,
                "independently_written_power_restore": self.independently_written_power_restore,
                "whole_host_recovery": "not_tested"}
