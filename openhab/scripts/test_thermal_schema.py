from dataclasses import fields
from datetime import datetime, timezone
import pytest

from thermal_model.schema import (
    ACTION_KINDS,
    SOURCE_WEIGHTS,
    THERMAL_ITEMS,
    ShadowOutput,
    validate_shadow_output,
    DynamicsModel,
    ThermalSample,
)


def test_glazing_coefficients_are_observation_contract():
    names = {item.name for item in fields(DynamicsModel)}
    assert "glazing_observation_coefficients" in names
    assert "glazing_coefficients" not in names


def test_thermal_sample_preserves_each_action_confidence():
    names = {item.name for item in fields(ThermalSample)}
    assert {
        "vent_confidence",
        "indoor_shade_confidence",
        "outdoor_shade_confidence",
    } <= names


def test_exact_sensor_contract_and_source_precedence():
    assert THERMAL_ITEMS == {
        "air": "AmbientWeatherWS2902A_IndoorSensor_Temperature",
        "mass": "AmbientWeatherWS2902A_WH31E_193_Temperature",
        "glazing": "Shelly_HT1_Indoor_Temperature",
        "outdoor": "AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature",
        "radiation": "AmbientWeatherWS2902A_SolarRadiation",
    }
    assert ACTION_KINDS == ("vent", "indoor_shade", "outdoor_shade", "kiva")
    assert SOURCE_WEIGHTS["nostr_confirmed"] > SOURCE_WEIGHTS["photosensor"]
    assert SOURCE_WEIGHTS["photosensor"] > SOURCE_WEIGHTS["historical_reconstruction"]
    assert SOURCE_WEIGHTS["historical_reconstruction"] > SOURCE_WEIGHTS["model_inferred"]


def test_shadow_output_rejects_live_or_actuator_fields():
    output = ShadowOutput.empty(datetime(2026, 8, 13, tzinfo=timezone.utc))
    assert validate_shadow_output(output.to_dict())["status"] == "shadow"
    payload = output.to_dict() | {"status": "advisory"}
    with pytest.raises(ValueError, match="shadow"):
        validate_shadow_output(payload)
    payload = output.to_dict() | {"commands": [{"item": "Anything", "state": "ON"}]}
    with pytest.raises(ValueError, match="unknown fields"):
        validate_shadow_output(payload)
