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
