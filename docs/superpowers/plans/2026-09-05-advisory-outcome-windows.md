# Advisory outcome time windows implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the reusable, UTC-exact completed-window contract needed by the approved advisory-outcome pipeline.

**Architecture:** A pure Python module owns half-open observation windows and completion checks. It has no I/O, runtime configuration, notifier access, or import-time actions. The later immutable-record builder and Solar_PV assessor will consume this same contract rather than reproduce calendar arithmetic.

**Tech Stack:** Python standard library datetime, dataclasses, zoneinfo; pytest.

## Global Constraints

- Threshold values, advisory selection, DM eligibility/deduplication/content, the 06:40 forecast schedule, household controls, BMS counters, and thermal model authority remain unchanged.
- Assess records only after their entire target window has elapsed.
- Use UTC instants derived from the recorded IANA timezone, with half-open windows.
- Trough: prediction-day 20:00 to next-day 11:00.
- Thermal: next local calendar day for hallway maximum/minimum; retain the preceding evening-to-11:00 window for relevant vent/shade transitions.
- Weather low/high: the exact local target day of the recorded temperature.
- PV: the recorded local production day, not the issue date by assumption.
- Retain change-only persistence; no new periodic persistence, collector, migration, publication, notification or deployment in this slice.
- Task 82 remains on hold.

## Scope within the approved design

Spec: `docs/superpowers/specs/2026-09-05-advisory-outcomes-design.md`.
This is the calendar dependency, not a claim that the live scoring defect is fixed.
No caller is switched until frozen decisions, validated source-health assessment
and deterministic projection are available. In particular, do not change the
existing measured_trough function: its morning partial data also feeds prediction
equations that the approved scoring-only change must preserve.

The remaining required implementation sequence is: immutable decision/result
records; Solar_PV schema and bounded storage/assessment; source-specific change-only
coverage and action attribution; forecast capture plus replacement of legacy
diagnostic scoring; private reports, failure-injection tests, release review and
separately approved live verification. Those are separate deliverables, not
requirements satisfied by this module. The canonical outstanding-work tracker
continues to retain the whole project scope.

Installed boundary for the shared pure module: the UI repository owns
`openhab/scripts/advisory_windows.py`, installed beside forecast_intel.py under
`/home/sat/openhab/scripts/`. Future Solar_PV assessment imports that same module
using an explicitly installed script path in its service Python path. It must not
import forecast_intel (which has notification capability) or depend on checkout
cwd. That service-path change belongs to the later reviewed deployment, not this
task. No duplication of this implementation into Solar_PV.

### Task 1: UTC-exact day and trough windows

**Files:**
- Create: `openhab/scripts/advisory_windows.py`
- Test: `openhab/scripts/test_advisory_windows.py`

**Interfaces:**
- Consumes: explicit `datetime.date` target date and IANA timezone string; no implicit host timezone or current clock.
- Produces: frozen `TargetWindow(start: datetime, end: datetime)` normalized to aware UTC, `contains(instant: datetime) -> bool`, `is_complete(now: datetime) -> bool`, `local_day_window(target_day: date, site_timezone: str) -> TargetWindow`, and `trough_window(prediction_day: date, site_timezone: str) -> TargetWindow`.
- Callers pass tomorrow's date for the thermal day and the actual forecast target date for weather/PV. No helper may infer target dates from issue time.

- [ ] **Step 1: Add tests before the implementation module.**

Imports of the new module occur inside test functions so its absence fails a test,
not collection. Use the existing pytest script-directory import convention.

```python
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

UTC = timezone.utc
SITE = "America/Denver"


@pytest.mark.parametrize("day,start,end", [
    (date(2026, 1, 4), "2026-01-05T03:00:00+00:00", "2026-01-05T18:00:00+00:00"),
    (date(2026, 7, 4), "2026-07-05T02:00:00+00:00", "2026-07-05T17:00:00+00:00"),
    (date(2026, 3, 7), "2026-03-08T03:00:00+00:00", "2026-03-08T17:00:00+00:00"),
    (date(2026, 10, 31), "2026-11-01T02:00:00+00:00", "2026-11-01T18:00:00+00:00"),
])
def test_trough_boundaries_and_completion(day, start, end):
    from advisory_windows import trough_window
    window = trough_window(day, SITE)
    assert window.start == datetime.fromisoformat(start)
    assert window.end == datetime.fromisoformat(end)
    next_day = day + timedelta(days=1)
    morning = datetime.combine(next_day, datetime.min.time(), ZoneInfo(SITE)).replace(hour=6, minute=40)
    assert not window.is_complete(morning)
    assert not window.is_complete(window.end - timedelta(microseconds=1))
    assert window.is_complete(window.end)
    assert window.is_complete(window.end + timedelta(days=1))
    assert window.contains(window.start)
    assert window.contains(window.end - timedelta(microseconds=1))
    assert not window.contains(window.end)
    assert not window.contains(window.start - timedelta(microseconds=1))


@pytest.mark.parametrize("day,hours", [
    (date(2026, 1, 4), 24), (date(2026, 7, 4), 24),
    (date(2026, 3, 8), 23), (date(2026, 11, 1), 25),
])
def test_calendar_day_uses_local_midnights(day, hours):
    from advisory_windows import local_day_window
    window = local_day_window(day, SITE)
    assert window.end - window.start == timedelta(hours=hours)
    assert window.start.astimezone(ZoneInfo(SITE)).date() == day
    assert window.start.astimezone(ZoneInfo(SITE)).hour == 0
    assert window.end.astimezone(ZoneInfo(SITE)).date() == day + timedelta(days=1)
    assert window.end.astimezone(ZoneInfo(SITE)).hour == 0


def test_explicit_target_and_timezone_are_not_host_defaults():
    from advisory_windows import local_day_window
    target = date(2026, 9, 6)
    assert local_day_window(target, "UTC").start == datetime(2026, 9, 6, tzinfo=UTC)
    assert local_day_window(target, "Asia/Kolkata").start == datetime(2026, 9, 5, 18, 30, tzinfo=UTC)


def test_window_normalizes_offsets_and_is_immutable():
    from advisory_windows import TargetWindow
    start = datetime(2026, 9, 4, 20, tzinfo=ZoneInfo(SITE))
    window = TargetWindow(start, start + timedelta(hours=1))
    assert window.start.tzinfo is UTC
    assert window.end.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        window.start = start


@pytest.mark.parametrize("bad", [datetime(2026, 9, 5), None, "2026-09-05T00:00:00Z"])
def test_unqualified_instants_are_rejected(bad):
    from advisory_windows import TargetWindow, local_day_window
    window = local_day_window(date(2026, 9, 5), SITE)
    for check in (window.contains, window.is_complete):
        with pytest.raises(ValueError):
            check(bad)
    with pytest.raises(ValueError):
        TargetWindow(bad, window.end)
    with pytest.raises(ValueError):
        TargetWindow(window.start, bad)


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1)])
def test_empty_or_reversed_windows_are_rejected(delta):
    from advisory_windows import TargetWindow
    start = datetime(2026, 9, 5, tzinfo=UTC)
    with pytest.raises(ValueError):
        TargetWindow(start, start + delta)


@pytest.mark.parametrize("bad", [datetime(2026, 9, 5, tzinfo=UTC), "2026-09-05", None])
def test_target_must_be_a_date_not_an_implicitly_truncated_datetime(bad):
    from advisory_windows import local_day_window, trough_window
    for build in (local_day_window, trough_window):
        with pytest.raises(ValueError):
            build(bad, SITE)


def test_unknown_site_timezone_is_not_silently_replaced():
    from advisory_windows import local_day_window, trough_window
    for build in (local_day_window, trough_window):
        with pytest.raises(ZoneInfoNotFoundError):
            build(date(2026, 9, 5), "Invalid/Site")
```

- [ ] **Step 2: Verify RED.**

Run `python3 -m pytest openhab/scripts/test_advisory_windows.py -q` from the
isolated checkout. Expected failure: missing advisory_windows inside test bodies.
The existing `test_forecast_intel.py` baseline must remain 63 passing tests.

- [ ] **Step 3: Implement the pure contract.**

```python
"""Explicit observation windows for advisory outcomes; no I/O or implicit clock."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def _utc(instant: datetime) -> datetime:
    if not isinstance(instant, datetime) or instant.utcoffset() is None:
        raise ValueError("an offset-qualified datetime is required")
    return instant.astimezone(timezone.utc)


def _target_date(value: date) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError("an explicit target date is required")
    return value


@dataclass(frozen=True)
class TargetWindow:
    """A nonempty half-open UTC interval, never evidence of measurement quality."""

    start: datetime
    end: datetime

    def __post_init__(self):
        start, end = _utc(self.start), _utc(self.end)
        if end <= start:
            raise ValueError("window end must be after start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    def contains(self, instant: datetime) -> bool:
        return self.start <= _utc(instant) < self.end

    def is_complete(self, now: datetime) -> bool:
        return _utc(now) >= self.end


def local_day_window(target_day: date, site_timezone: str) -> TargetWindow:
    """Use the caller's actual target day for PV, weather or thermal extrema."""
    day, zone = _target_date(target_day), ZoneInfo(site_timezone)
    return TargetWindow(
        datetime.combine(day, time.min, zone),
        datetime.combine(day + timedelta(days=1), time.min, zone),
    )


def trough_window(prediction_day: date, site_timezone: str) -> TargetWindow:
    """Prediction-day 20:00 through following-day 11:00 in the recorded zone."""
    day, zone = _target_date(prediction_day), ZoneInfo(site_timezone)
    return TargetWindow(
        datetime.combine(day, time(20), zone),
        datetime.combine(day + timedelta(days=1), time(11), zone),
    )
```

- [ ] **Step 4: Verify GREEN and noninterference.**

Run `python3 -m pytest openhab/scripts/test_advisory_windows.py openhab/scripts/test_forecast_intel.py -q`.
Expected: all tests pass, including the unchanged 63 forecast tests. Also run
`python3 -m compileall -q openhab/scripts/advisory_windows.py` and
`git diff --check`. Inspect the diff to confirm forecast_intel.py and all runtime
configuration remain unchanged. No server or production database is needed.

- [ ] **Step 5: Commit and independent review.**

Run `git add openhab/scripts/advisory_windows.py openhab/scripts/test_advisory_windows.py`
and `git commit -m "feat: define explicit advisory outcome windows"`.
Provide task-scoped and final branch review before integration. Preserve the
isolated branch; this does not authorize merging to the live checkout or deploying.

## Plan self-review

Covered: explicit target identities, half-open day/trough windows, January/July,
DST-short/long days and nights, 06:40 pending, equality-at-end complete, rejection
of naive inputs, and no effect on current prediction/scoring/notification paths.
No new timing policy, timestamp repair, timezone fallback, or source-health claim.
Full outcome capture, validation and live scoring remain the later required work
identified above; this plan does not claim coverage of those completed deliverables.
