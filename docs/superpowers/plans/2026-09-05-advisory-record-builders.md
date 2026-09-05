# Immutable advisory record builders implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the exact advisory inputs, per-quantity targets, and observed publication/notification results into canonical immutable records for the approved outcome pipeline.

**Architecture:** Pure builders return canonical JSON strings. They accept explicit IDs and timestamps, perform no I/O, and reject unknown fields so message bodies, recipients and arbitrary subprocess output cannot be attached. Later storage owns idempotent insert/conflict handling and later producer integration supplies these builders with the actual values used; this task does not wire a live caller.

**Tech Stack:** Python standard library JSON, datetime, UUID, zoneinfo; pytest; the existing advisory_windows module.

## Global Constraints

- Threshold values, advisory selection, DM eligibility/deduplication/content, the 06:40 forecast schedule, household controls, BMS counters, and thermal model authority remain unchanged.
- Each record has a UUID decision ID, schema version, UTC issued time, site timezone, source revision, policy version and bank epoch.
- Record the exact finite inputs actually used; do not apply today's filter retrospectively.
- Preserve per-quantity target windows; today's PV and tomorrow's temperature are not the same target.
- HTTP acceptance does not prove display or human acknowledgement.
- Do not persist message bodies, recipients, secrets or raw subprocess output.
- A retry of a storage operation uses the same decision ID and exact payload; conflicting content for that ID fails explicitly.
- Never replay notifications or advisory writes to repair an observational record.
- Retain change-only persistence. No migration, activation, notification or control operation in this task. Task 82 remains on hold.

## Scope and boundary

Approved spec: `docs/superpowers/specs/2026-09-05-advisory-outcomes-design.md`.
Previous calendar task is complete at 33fb0f9 with reviewed branch at 34ea969.
This task produces the immutable wire representation. Database uniqueness,
result chronology, cross-record parent checks, cutover, capture failures and
actual delayed scoring remain required later storage/integration tasks, not
claims made by these pure builders.

The builder deliberately does not recalculate corrections, advisory category or
notification eligibility. Inputs and booleans are frozen from the caller's actual
decision path. Daily raw weather values refer to prediction_day; tomorrow values
refer to prediction_day+1. The three-day raw highs correspond to days+1,+2,+3.
Weather-today corrected residuals are unavailable: this current producer only uses
the captured corrected tomorrow values for the advisory. Do not invent corrected
today forecasts by applying the captured filter after the fact.

Strings returned by builders are immutable. Parsing them yields a fresh object,
not shared caller-owned mutable state. Storage will parse validated records into
JSONB and compare semantic canonical content on duplicate identity. It must not
use a hash alone as evidence of payload equality. Explicit result IDs permit a
storage retry to preserve the same result identity; a new observation uses a new
result ID. Missing result rows remain unknown, never inferred acceptance.

Install advisory_records.py beside advisory_windows.py and forecast_intel.py in
the later attended release; Solar_PV consumes the same installed pure modules,
not forecast_intel or a copied implementation. No installation occurs here.

### Task 2: Immutable decision and result builders

**Files:**
- Create: `openhab/scripts/advisory_records.py`
- Test: `openhab/scripts/test_advisory_records.py`

**Interfaces:**
- Consumes `local_day_window(date, str)` and `trough_window(date, str)` from advisory_windows; their returned start/end are UTC-aware datetimes.
- Produces `build_decision_record(*, decision_id, issued_at, site_timezone, source_revision, policy_version, bank_epoch, prediction_day, advisory, inputs, thresholds, notification_eligible, notification_suppressed) -> str`.
- Produces `build_result_record(*, result_id, decision_id, observed_at, kind, target, status) -> str`.
- Both outputs have integer schema_version=1. Result kind publication targets exactly Thermal_Advisory or Predicted_SoC_Trough_Tomorrow; notification targets exactly deep_cycle_dm.

- [ ] **Step 1: Write tests before creating the module.**

```python
import json
from datetime import date, datetime, timezone, timedelta
from uuid import UUID

import pytest


def arguments():
    return dict(
        decision_id=UUID("00000000-0000-4000-8000-000000000001"),
        issued_at=datetime(2026, 9, 5, 12, 40, tzinfo=timezone.utc),
        site_timezone="America/Denver", source_revision="34ea969",
        policy_version="forecast-v3", bank_epoch="discover_4_module_2026",
        prediction_day=date(2026, 9, 5), advisory="vent_tonight",
        notification_eligible=False, notification_suppressed=False,
        inputs={
            "weather_today_high_raw_f": 91, "weather_today_low_raw_f": 49,
            "tomorrow_high_raw_f": 94, "tomorrow_low_raw_f": 48,
            "tomorrow_high_corrected_f": 90.25,
            "tomorrow_low_corrected_f": 40.125,
            "high_bias_f": 3.75, "low_bias_f": 7.875,
            "next_three_highs_raw_f": [94, 93, 92],
            "three_day_high_mean_corrected_f": 89.25,
            "pv_today_kwh": 6.3, "trough_tomorrow_pct": 86,
        },
        thresholds={"close_up_high_f": 95, "close_up_streak_f": 92,
                    "vent_high_f": 90, "trough_dm_pct": 30},
    )


def test_freezes_exact_inputs_and_separate_target_windows():
    from advisory_records import build_decision_record
    args = arguments()
    encoded = build_decision_record(**args)
    payload = json.loads(encoded)
    assert payload["schema_version"] == 1
    assert payload["record_type"] == "advisory_decision"
    assert payload["issued_at"] == "2026-09-05T12:40:00Z"
    assert payload["inputs"]["tomorrow_high_corrected_f"] == 90.25
    assert payload["inputs"]["tomorrow_low_corrected_f"] == 40.125
    assert payload["thresholds"] == args["thresholds"]
    targets = payload["targets"]
    assert targets["pv_today"]["start"] == "2026-09-05T06:00:00Z"
    assert targets["trough"]["start"] == "2026-09-06T02:00:00Z"
    assert targets["trough"]["end"] == "2026-09-06T17:00:00Z"
    assert targets["weather_tomorrow"]["start"] == "2026-09-06T06:00:00Z"
    assert targets["thermal_tomorrow"] == targets["weather_tomorrow"]
    assert targets["action_transition"] == targets["trough"]
    assert targets["weather_today"] == targets["pv_today"]
    assert payload["notification"] == {"eligible": False, "suppressed": False}
    args["inputs"]["next_three_highs_raw_f"][0] = 200
    args["thresholds"]["vent_high_f"] = 200
    payload["inputs"]["tomorrow_high_corrected_f"] = 200
    assert json.loads(encoded)["inputs"]["next_three_highs_raw_f"][0] == 94
    assert json.loads(encoded)["thresholds"]["vent_high_f"] == 90
    assert json.loads(encoded)["inputs"]["tomorrow_high_corrected_f"] == 90.25


def test_retry_is_canonical_but_new_invocation_has_new_identity():
    from advisory_records import build_decision_record
    args = arguments()
    original = build_decision_record(**args)
    args["inputs"] = dict(reversed(list(args["inputs"].items())))
    args["issued_at"] = args["issued_at"].astimezone(timezone(timedelta(hours=-6)))
    assert build_decision_record(**args) == original
    args["decision_id"] = UUID("00000000-0000-4000-8000-000000000002")
    assert build_decision_record(**args) != original


@pytest.mark.parametrize("key", ["tomorrow_high_corrected_f", "pv_today_kwh", "trough_tomorrow_pct"])
@pytest.mark.parametrize("bad", [None, True, "90", float("nan"), float("inf"), 10**1000])
def test_inputs_must_be_finite_numbers(key, bad):
    from advisory_records import build_decision_record
    args = arguments(); args["inputs"][key] = bad
    with pytest.raises(ValueError):
        build_decision_record(**args)


@pytest.mark.parametrize("container", ["inputs", "thresholds"])
def test_unknown_fields_are_not_a_freeform_private_data_channel(container):
    from advisory_records import build_decision_record
    args = arguments(); args[container]["message_body"] = "do not persist"
    with pytest.raises(ValueError):
        build_decision_record(**args)
    args = arguments(); args[container].pop(next(iter(args[container])))
    with pytest.raises(ValueError):
        build_decision_record(**args)


@pytest.mark.parametrize("bad", [[], [90, 91], [90, 91, 92, 93], [90, None, 92], [90, True, 92]])
def test_three_day_summary_requires_three_finite_inputs(bad):
    from advisory_records import build_decision_record
    args = arguments(); args["inputs"]["next_three_highs_raw_f"] = bad
    with pytest.raises(ValueError):
        build_decision_record(**args)


@pytest.mark.parametrize("field,bad", [
    ("decision_id", "not-a-uuid"), ("issued_at", datetime(2026, 9, 5)),
    ("prediction_day", datetime(2026, 9, 5, tzinfo=timezone.utc)),
    ("source_revision", ""), ("policy_version", "raw message text"),
    ("bank_epoch", ""), ("advisory", "invented_policy"),
    ("notification_eligible", 1), ("notification_suppressed", "false"),
])
def test_invalid_identity_and_policy_metadata_is_rejected(field, bad):
    from advisory_records import build_decision_record
    args = arguments(); args[field] = bad
    with pytest.raises(ValueError):
        build_decision_record(**args)


def test_suppression_requires_eligibility_and_never_recomputes_category():
    from advisory_records import build_decision_record
    args = arguments(); args["notification_suppressed"] = True
    with pytest.raises(ValueError):
        build_decision_record(**args)
    args["notification_eligible"] = True
    args["advisory"] = "none"
    result = json.loads(build_decision_record(**args))
    assert result["advisory"] == "none"
    assert result["notification"] == {"eligible": True, "suppressed": True}


@pytest.mark.parametrize("kind,target,status", [
    ("publication", "Thermal_Advisory", "accepted"),
    ("publication", "Predicted_SoC_Trough_Tomorrow", "failed"),
    ("publication", "Predicted_SoC_Trough_Tomorrow", "unknown"),
    *[("notification", "deep_cycle_dm", s) for s in (
        "not_eligible", "suppressed", "attempted_reported_success",
        "attempted_failed", "attempted_unknown", "unknown")],
])
def test_result_states_preserve_observed_semantics(kind, target, status):
    from advisory_records import build_result_record
    args = dict(result_id=UUID("00000000-0000-4000-8000-000000000003"),
                decision_id=arguments()["decision_id"],
                observed_at=arguments()["issued_at"], kind=kind,
                target=target, status=status)
    encoded = build_result_record(**args)
    assert build_result_record(**args) == encoded
    payload = json.loads(encoded)
    assert payload["status"] == status
    assert payload["target"] == target
    assert set(payload) == {"schema_version", "record_type", "result_id",
                            "decision_id", "observed_at", "kind", "target", "status"}


@pytest.mark.parametrize("kind,target,status", [
    ("publication", "Thermal_Advisory", "delivered"),
    ("notification", "recipient-key", "attempted_reported_success"),
    ("notification", "deep_cycle_dm", "accepted"),
    ("actuator", "ShurefloPump_Power", "accepted"),
])
def test_results_reject_unapproved_targets_and_delivery_claims(kind, target, status):
    from advisory_records import build_result_record
    with pytest.raises(ValueError):
        build_result_record(result_id=arguments()["decision_id"],
                            decision_id=arguments()["decision_id"],
                            observed_at=arguments()["issued_at"],
                            kind=kind, target=target, status=status)
```

- [ ] **Step 2: Verify RED.**

Run `python3 -m pytest openhab/scripts/test_advisory_records.py -q`.
Expected missing advisory_records failures inside test bodies, not collection.

- [ ] **Step 3: Implement the exact pure builders.**

```python
"""Canonical immutable advisory evidence records; no storage or side effects."""
import json
import math
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from advisory_windows import local_day_window, trough_window

INPUT_FIELDS = frozenset({
    "weather_today_high_raw_f", "weather_today_low_raw_f",
    "tomorrow_high_raw_f", "tomorrow_low_raw_f",
    "tomorrow_high_corrected_f", "tomorrow_low_corrected_f",
    "high_bias_f", "low_bias_f", "next_three_highs_raw_f",
    "three_day_high_mean_corrected_f", "pv_today_kwh", "trough_tomorrow_pct",
})
THRESHOLD_FIELDS = frozenset({
    "close_up_high_f", "close_up_streak_f", "vent_high_f", "trough_dm_pct",
})
ADVISORIES = frozenset({"none", "vent_tonight", "close_up_tomorrow"})
PUBLICATION_TARGETS = frozenset({"Thermal_Advisory", "Predicted_SoC_Trough_Tomorrow"})
PUBLICATION_STATES = frozenset({"accepted", "failed", "unknown"})
NOTIFICATION_STATES = frozenset({
    "not_eligible", "suppressed", "attempted_reported_success",
    "attempted_failed", "attempted_unknown", "unknown",
})
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/+\-]{0,95}\Z")


def _id(value):
    if not isinstance(value, (str, UUID)):
        raise ValueError("UUID identity required")
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise ValueError("UUID identity required") from exc


def _stamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("offset-qualified timestamp required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _token(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ValueError("bounded version/epoch token required")
    return value


def _number(value):
    if type(value) not in (int, float):
        raise ValueError("finite numeric input required")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("finite numeric input required") from exc
    if not math.isfinite(number):
        raise ValueError("finite numeric input required")
    return number


def _fields(values, expected):
    if not isinstance(values, dict) or set(values) != expected:
        raise ValueError("record fields do not match the schema")


def _window(window):
    return {"start": _stamp(window.start), "end": _stamp(window.end)}


def _encode(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_decision_record(*, decision_id, issued_at, site_timezone,
                          source_revision, policy_version, bank_epoch,
                          prediction_day, advisory, inputs, thresholds,
                          notification_eligible, notification_suppressed):
    """Freeze caller-used values; never recalculate policy or generate a clock/ID."""
    _fields(inputs, INPUT_FIELDS)
    _fields(thresholds, THRESHOLD_FIELDS)
    sequence = inputs["next_three_highs_raw_f"]
    if not isinstance(sequence, (list, tuple)) or len(sequence) != 3:
        raise ValueError("three raw high forecasts required")
    frozen_inputs = {
        key: ([_number(value) for value in sequence]
              if key == "next_three_highs_raw_f" else _number(value))
        for key, value in inputs.items()
    }
    frozen_thresholds = {key: _number(value) for key, value in thresholds.items()}
    if advisory not in ADVISORIES:
        raise ValueError("unknown advisory category")
    if type(notification_eligible) is not bool or type(notification_suppressed) is not bool:
        raise ValueError("notification intent requires explicit booleans")
    if notification_suppressed and not notification_eligible:
        raise ValueError("only eligible notifications can be suppressed")
    if not isinstance(site_timezone, str):
        raise ValueError("IANA site timezone required")
    ZoneInfo(site_timezone)
    today = local_day_window(prediction_day, site_timezone)
    tomorrow = local_day_window(prediction_day + timedelta(days=1), site_timezone)
    night = trough_window(prediction_day, site_timezone)
    return _encode({
        "schema_version": 1, "record_type": "advisory_decision",
        "decision_id": _id(decision_id), "issued_at": _stamp(issued_at),
        "site_timezone": site_timezone, "source_revision": _token(source_revision),
        "policy_version": _token(policy_version), "bank_epoch": _token(bank_epoch),
        "prediction_day": prediction_day.isoformat(), "advisory": advisory,
        "inputs": frozen_inputs, "thresholds": frozen_thresholds,
        "notification": {"eligible": notification_eligible, "suppressed": notification_suppressed},
        "targets": {
            "pv_today": _window(today), "trough": _window(night),
            "weather_today": _window(today), "weather_tomorrow": _window(tomorrow),
            "thermal_tomorrow": _window(tomorrow), "action_transition": _window(night),
        },
    })


def build_result_record(*, result_id, decision_id, observed_at, kind, target, status):
    """Freeze a reported result; success is neither delivery nor human action."""
    if kind == "publication":
        valid = target in PUBLICATION_TARGETS and status in PUBLICATION_STATES
    elif kind == "notification":
        valid = target == "deep_cycle_dm" and status in NOTIFICATION_STATES
    else:
        valid = False
    if not valid:
        raise ValueError("unknown result kind, target or status")
    return _encode({
        "schema_version": 1, "record_type": "advisory_result",
        "result_id": _id(result_id), "decision_id": _id(decision_id),
        "observed_at": _stamp(observed_at), "kind": kind,
        "target": target, "status": status,
    })
```

- [ ] **Step 4: Verify GREEN and noninterference.**

Run `python3 -m pytest openhab/scripts/test_advisory_records.py openhab/scripts/test_advisory_windows.py openhab/scripts/test_forecast_intel.py -q`,
`python3 -m compileall -q openhab/scripts/advisory_records.py`, and `git diff --check`.
All tests must pass. Inspect the diff: no live producer, SQL, service or notification
code may change. No tests use the real network or production database.

- [ ] **Step 5: Commit and review.**

Run `git add openhab/scripts/advisory_records.py openhab/scripts/test_advisory_records.py`
and `git commit -m "feat: freeze advisory decisions and observed results"`.
Write the implementation report to `.superpowers/sdd/advisory-records-task-2-report.md`;
do not overwrite the historical task-2-report.md. Task and whole-branch reviews
must precede integration. Keep this branch isolated; live integration is unfinished.

## Self-review against the approved spec

This contract covers origin metadata, frozen raw/corrected inputs and biases,
thresholds/category/notification intent, separate target windows, canonical retry
payloads, immutable result identity, per-Item results and honest notification
states. No freeform payload fields or automatic ID/clock generation exists.
Database conflict enforcement, source-health coverage, deterministic revisions,
advisory capture wiring and live completed-night scoring remain mandatory subsequent
deliverables. No claim is made that pure construction proves those system behaviors.
