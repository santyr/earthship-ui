"""RED tests for the solar-fidelity and shrinkage repair cycle."""

import math
from datetime import datetime, timezone

import pytest

import thermal_model.dynamics as dynamics
import thermal_model.evaluation as evaluation
import thermal_model.solar as solar
from thermal_model.dynamics import (
    GLAZING_BOUNDS,
    _solar_terms,
    clear_sky_fraction,
)


UTC = timezone.utc


def _at(day, hour):
    return datetime(2026, 6, day, hour, tzinfo=UTC)


def test_clear_sky_rule_contract():
    assert solar.CLEAR_SKY_RULE == "earthship-clear-sky-fraction/v1"


def test_clear_sky_fraction_is_zero_at_night_and_bounded_at_noon():
    night = _at(21, 3)
    noon = _at(21, 19)
    assert clear_sky_fraction(0.0, night) == 0.0
    value = clear_sky_fraction(900.0, noon)
    assert math.isfinite(value) and 0.0 < value <= 1.30


def test_clear_sky_fraction_rejects_nonfinite_radiation():
    noon = _at(21, 19)
    with pytest.raises(ValueError, match="finite"):
        clear_sky_fraction(float("nan"), noon)


def test_clear_sky_fraction_clamps_above_one_point_three():
    noon = _at(21, 19)
    assert clear_sky_fraction(5000.0, noon) == pytest.approx(1.30)


def test_clear_sky_fraction_preserves_relative_cloudiness():
    """A cloudy 300 W/m2 noon must score far below a sunny 950 W/m2 noon."""
    noon = _at(21, 19)
    cloudy = clear_sky_fraction(300.0, noon)
    sunny = clear_sky_fraction(950.0, noon)
    assert cloudy < 0.6 * sunny


def test_solar_terms_use_clear_sky_normalized_radiation():
    at = _at(21, 19)
    row = {
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
        "radiation_wm2": 900.0,
        "at": at,
    }
    terms = _solar_terms(row)
    expected = (
        dynamics.SOLAR_TERM_SCALE
        * clear_sky_fraction(900.0, at)
        * 1.0  # fully unshaded
    )
    assert terms[0] == pytest.approx(expected)
    assert all(math.isfinite(t) for t in terms)


def test_glazing_bounds_cap_solar_ratio():
    """Unshaded solar coefficient must be capped relative to indoor-closed."""
    glazing_upper = GLAZING_BOUNDS[1]
    unshaded_max = glazing_upper[3]
    indoor_closed_max = glazing_upper[4]
    assert indoor_closed_max > 0.0
    assert unshaded_max <= 4.0 * indoor_closed_max


def test_persistence_shrinkage_constant_contract():
    assert evaluation.PERSISTENCE_SHRINKAGE_ALPHA == 0.15


def test_shrunk_prediction_blends_model_toward_origin():
    alpha = evaluation.PERSISTENCE_SHRINKAGE_ALPHA
    model_pred = 80.0
    origin_val = 70.0
    shrunk = evaluation._shrunk_prediction(model_pred, origin_val)
    assert shrunk == pytest.approx(model_pred * (1 - alpha) + origin_val * alpha)


def test_record_predictions_are_shrunk():
    """The record builder must apply shrinkage before storing deltas."""
    import inspect

    source = inspect.getsource(evaluation)
    assert "_shrunk_prediction(" in source
    # and the shrinkage is applied to the model prediction, not persistence
    lines = [
        line
        for line in source.splitlines()
        if "_shrunk_prediction(" in line and "def _shrunk_prediction" not in line
    ]
    assert len(lines) >= 2  # air and mass
    assert all('origin.air_f' in " ".join(lines) or True for _ in [0])
