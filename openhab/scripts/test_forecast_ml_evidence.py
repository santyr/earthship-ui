from datetime import date, datetime, timedelta, timezone

import pytest

from forecast_ml_evidence import (
    summarize_day_evidence,
    summarize_nonoverlapping_origins,
)


def test_day_evidence_counts_unique_days_not_dense_rows():
    values = [
        datetime(2026, 10, 1, 7, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 18, tzinfo=timezone.utc),
        date(2026, 10, 2),
        "2026-10-03",
    ]
    result = summarize_day_evidence(
        values, active_parameter_count=2, minimum_unique_days=3
    )
    assert result["reported_unit_count"] == 4
    assert result["unique_unit_count"] == 3
    assert result["duplicate_unit_count"] == 1
    assert result["units_per_active_parameter"] == 1.5
    assert result["minimum_unique_units_met"] is True


def test_day_evidence_uses_site_day_and_rejects_naive_timestamps():
    # 05:30Z is still the prior local day during MDT.
    result = summarize_day_evidence(
        ["2026-10-02T05:30:00+00:00", "2026-10-01"],
        timezone_name="America/Denver",
    )
    assert result["unique_unit_count"] == 1
    with pytest.raises(ValueError, match="offset"):
        summarize_day_evidence(["2026-10-01T12:00:00"])
    with pytest.raises(ValueError):
        summarize_day_evidence([], active_parameter_count=True)


def test_nonoverlapping_origins_do_not_inflate_overlapping_forecasts():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    origins = [start + timedelta(hours=hours) for hours in (0, 2, 4, 24, 26, 48)]
    result = summarize_nonoverlapping_origins(origins, timedelta(hours=24))
    assert result["reported_origin_count"] == 6
    assert result["independent_origin_count"] == 3


def test_nonoverlapping_origins_refuse_duplicates_and_bad_horizon():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="unique"):
        summarize_nonoverlapping_origins([start, start], timedelta(hours=1))
    with pytest.raises(ValueError, match="positive"):
        summarize_nonoverlapping_origins([start], timedelta(0))


def test_spring_dst_uses_elapsed_horizon_and_excludes_overlapping_day():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo('America/Denver')
    origins = [datetime(2026, 3, day, 8, 45, tzinfo=zone) for day in (7, 8, 9)]
    result = summarize_nonoverlapping_origins(origins, timedelta(hours=24))
    # March8 is only23 elapsed hours after March7; March9 is47 hours after it.
    assert result['reported_origin_count'] == 3
    assert result['independent_origin_count'] == 2
    assert result['last_origin'] == '2026-03-09T08:45:00-06:00'


def test_fall_dst_repeated_local_hour_has_two_distinct_elapsed_windows():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo('America/Denver')
    origins = [datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=fold) for fold in (1, 0)]
    result = summarize_nonoverlapping_origins(origins, timedelta(hours=1))
    assert result['reported_origin_count'] == result['independent_origin_count'] == 2
    assert result['first_origin'] == '2026-11-01T01:30:00-06:00'
    assert result['last_origin'] == '2026-11-01T01:30:00-07:00'


def test_nonoverlapping_summary_preserves_declared_fractional_horizon():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    result = summarize_nonoverlapping_origins(
        [start, start + timedelta(milliseconds=400), start + timedelta(milliseconds=500)],
        timedelta(milliseconds=500))
    assert result['independent_origin_count'] == 2
    assert result['horizon_seconds'] == 0.5
