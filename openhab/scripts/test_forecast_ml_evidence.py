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
