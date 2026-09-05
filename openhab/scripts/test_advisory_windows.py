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
