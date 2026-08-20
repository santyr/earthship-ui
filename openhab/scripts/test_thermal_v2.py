from types import SimpleNamespace

import numpy as np
import pytest

from thermal_model.dynamics import (
    MASS_BOUNDS,
    MASS_NAMES,
    _transition_matrix,
    predict_step,
    validate_physics,
)
from thermal_model.schema import DynamicsModel


def model(*, version=2, mass_air=0.01, mass_outside=0.01):
    return DynamicsModel(
        version=version,
        step_minutes=5,
        air_coefficients={
            "outside_exchange": 0.02,
            "mass_exchange": 0.03,
            "solar_unshaded": 0.0001,
            "solar_indoor_closed": 0.00005,
            "solar_outdoor": 0.00002,
            "vent_exchange": 0.05,
            "bias": 0.0,
        },
        mass_coefficients={
            "air_exchange": mass_air,
            "outside_exchange": mass_outside,
            "solar_unshaded": 0.00004,
            "solar_indoor_closed": 0.00002,
            "solar_outdoor": 0.00001,
        },
        glazing_observation_coefficients={},
    )


def forcing(**changes):
    values = {
        "air_f": 80.0,
        "mass_f": 80.0,
        "outdoor_f": 60.0,
        "radiation_wm2": 0.0,
        "vent_open": 0.0,
        "indoor_shade_closed": 0.0,
        "outdoor_shade_present": 0.0,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_v2_mass_contract_adds_bounded_outdoor_exchange():
    assert MASS_NAMES == (
        "air_exchange", "outside_exchange", "solar_unshaded",
        "solar_indoor_closed", "solar_outdoor",
    )
    assert MASS_BOUNDS == (
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [0.20, 0.20, 0.008, 0.004, 0.006],
    )


def test_predict_step_applies_mass_outdoor_forcing_without_bias_or_clamp():
    next_air, next_mass, glazing = predict_step(
        model(mass_air=0.0, mass_outside=0.1), forcing()
    )

    assert next_air == pytest.approx(79.6)
    assert next_mass == pytest.approx(78.0)
    assert glazing is None


def test_transition_matrix_includes_mass_outdoor_loss_on_second_diagonal():
    matrix = _transition_matrix(model(mass_air=0.01, mass_outside=0.10), 0.0)

    np.testing.assert_allclose(matrix, [
        [0.95, 0.03],
        [0.01, 0.89],
    ])


def test_positive_mass_outdoor_exchange_removes_neutral_mode_but_zero_paths_fail():
    assert validate_physics(model(mass_air=0.0, mass_outside=0.01)).version == 2

    with pytest.raises(ValueError, match="spectral radius"):
        validate_physics(model(mass_air=0.0, mass_outside=0.0))


@pytest.mark.parametrize(
    ("outside", "message"),
    [(-0.01, "nonnegative"), (0.21, "bounds")],
)
def test_mass_outdoor_exchange_must_stay_within_declared_bounds(outside, message):
    with pytest.raises(ValueError, match=message):
        validate_physics(model(mass_outside=outside))


def test_v1_dynamics_fail_closed_instead_of_synthetic_migration():
    with pytest.raises(ValueError, match="version 2"):
        validate_physics(model(version=1))
