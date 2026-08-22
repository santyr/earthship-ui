from datetime import datetime, timedelta, timezone
import importlib
import math

import pytest

from thermal_model import behavior, dataset


def _solar():
    return importlib.import_module("thermal_model.solar")


def test_solar_contract_is_exact():
    assert _solar().solar_contract() == {
        "rule": "earthship-solar-elevation/v1",
        "latitude": 38.3739919,
        "longitude": -105.7744609,
        "night_when_elevation_sin_lte": 0.0,
    }


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        _solar().solar_elevation_sin(datetime(2026, 8, 20, 3, 0))


@pytest.mark.parametrize(
    "at",
    (
        datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 20, 3, 0, tzinfo=timezone(timedelta(hours=-6))),
    ),
)
def test_solar_elevation_sin_is_finite_for_timezone_aware_input(at):
    assert math.isfinite(_solar().solar_elevation_sin(at))


def test_solar_elevation_sin_rejects_non_finite_result(monkeypatch):
    solar = _solar()
    monkeypatch.setattr(solar.math, "sin", lambda value: math.nan)

    with pytest.raises(ValueError, match="finite"):
        solar.solar_elevation_sin(datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc))


def test_astronomical_night_includes_zero_elevation_sine(monkeypatch):
    solar = _solar()
    at = datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(solar, "solar_elevation_sin", lambda value: 0.0)

    assert solar.is_astronomical_night(at) is True


@pytest.mark.parametrize(
    "at",
    (
        datetime(2026, 1, 20, 3, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 20, 18, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 20, 3, 0, tzinfo=timezone.utc),
    ),
)
def test_dataset_and_behavior_share_the_solar_authority(at):
    solar = _solar()
    assert dataset.is_astronomical_night is solar.is_astronomical_night
    assert behavior.solar_elevation_sin is solar.solar_elevation_sin
    assert dataset.is_astronomical_night(at) is (
        behavior.solar_elevation_sin(at) <= 0.0
    )
