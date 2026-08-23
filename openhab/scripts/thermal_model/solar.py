"""Shared deterministic solar-elevation authority for the thermal model."""

from datetime import datetime, timezone
import math


SOLAR_ELEVATION_RULE = "earthship-solar-elevation/v1"
SITE_LATITUDE = 38.3739919
SITE_LONGITUDE = -105.7744609
NIGHT_WHEN_ELEVATION_SIN_LTE = 0.0
CLEAR_SKY_RULE = "earthship-clear-sky-fraction/v1"
CLEAR_SKY_IRRADIANCE_WM2 = 1050.0
CLEAR_SKY_EXPONENT = 1.15
CLEAR_SKY_MAX_FRACTION = 1.30


def _aware(at):
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("solar timestamp must be timezone-aware")
    return at


def solar_contract():
    """Return the exact deterministic solar-elevation contract."""
    return {
        "rule": SOLAR_ELEVATION_RULE,
        "latitude": SITE_LATITUDE,
        "longitude": SITE_LONGITUDE,
        "night_when_elevation_sin_lte": NIGHT_WHEN_ELEVATION_SIN_LTE,
    }


def solar_elevation_sin(at):
    """NOAA fractional-year approximation, returned as sin(elevation)."""
    at = _aware(at).astimezone(timezone.utc)
    day = at.timetuple().tm_yday
    hour = at.hour + at.minute / 60.0 + at.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (day - 1 + (hour - 12.0) / 24.0)
    equation_minutes = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )
    solar_minutes = hour * 60.0 + equation_minutes + 4.0 * SITE_LONGITUDE
    hour_angle = math.radians(solar_minutes / 4.0 - 180.0)
    latitude = math.radians(SITE_LATITUDE)
    result = float(
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    if not math.isfinite(result):
        raise ValueError("solar elevation sine must be finite")
    return result


def is_astronomical_night(at):
    """Return whether an aware timestamp is at or below the solar horizon."""
    return solar_elevation_sin(at) <= NIGHT_WHEN_ELEVATION_SIN_LTE


def clear_sky_expected_wm2(at):
    """Deterministic site clear-sky global horizontal irradiance estimate."""
    elevation_sin = solar_elevation_sin(at)
    if elevation_sin <= 0.0:
        return 0.0
    return CLEAR_SKY_IRRADIANCE_WM2 * elevation_sin**CLEAR_SKY_EXPONENT


def clear_sky_fraction(radiation_wm2, at):
    """Return measured irradiance divided by the clear-sky expectation.

    Zero at night, clamped to [0, CLEAR_SKY_MAX_FRACTION] so sensor spikes
    cannot inject unbounded forcing. Cloud transients become fractions of a
    sunny reference instead of absolute energy.
    """
    radiation = float(radiation_wm2)
    if not math.isfinite(radiation):
        raise ValueError("radiation must be finite")
    if radiation <= 0.0:
        return 0.0
    expected = clear_sky_expected_wm2(at)
    if expected <= 0.0:
        return 0.0
    fraction = radiation / expected
    if fraction > CLEAR_SKY_MAX_FRACTION:
        return CLEAR_SKY_MAX_FRACTION
    return float(fraction)
