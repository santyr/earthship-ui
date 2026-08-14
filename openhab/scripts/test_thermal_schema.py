from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, fields
from datetime import datetime, timezone
import pytest


def valid_shadow_payload():
    return {
        "version": 1,
        "status": "shadow",
        "generatedAt": "2026-08-13T12:00:00+00:00",
        "model": {
            "createdAt": "2026-08-13T10:00:00+00:00",
            "trainedThrough": "2026-08-13T09:00:00+00:00",
            "codeRevision": "0123456789abcdef",
        },
        "current": {"hallwayF": 74.0, "massF": 72.0, "glazingF": None},
        "forecast": {
            "availableHours": 24,
            "hallwayHighF": 80.0,
            "hallwayHighAt": "2026-08-13T07:00:00-06:00",
            "hallwayLowF": 68.0,
            "hallwayLowAt": "2026-08-13T06:00:00-06:00",
            "morningMassF": 70.0,
            "intervalLowF": 66.0,
            "intervalHighF": 82.0,
            "trajectory": [
                {
                    "at": "2026-08-13T06:00:00-06:00",
                    "hallwayF": 74.0, "massF": 72.0,
                    "lowF": 72.0, "highF": 76.0, "actions": [],
                },
                {
                    "at": "2026-08-13T07:00:00-06:00",
                    "hallwayF": 75.0, "massF": 72.2,
                    "lowF": 73.0, "highF": 77.0,
                    "actions": ["vent_close"],
                },
            ],
            "observed": [
                {
                    "at": "2026-08-13T11:55:00+00:00",
                    "hallwayF": 73.9, "massF": 71.9,
                }
            ],
        },
        "schedule": {
            "baseline": {
                "ventOpenAt": "2026-08-14T02:30:00+00:00",
                "ventCloseAt": "2026-08-14T11:00:00+00:00",
            },
            "candidate": None,
            "effect": {"morningMassDeltaF": 0.0, "hallwayPeakDeltaF": 0.0},
        },
        "confidence": {"grade": "low", "actionLabels": "reconstructed"},
        "provenance": {
            "sensorItems": dict(THERMAL_ITEMS),
            "actions": "historical_reconstruction",
            "currentAgeMinutes": {
                "air": 2.0, "mass": 2.0, "glazing": None,
                "outdoor": 2.0, "radiation": 2.0,
            },
            "modelAgeHours": 2.0,
            "trainingDataAgeHours": 3.0,
        },
        "reasons": ["minimum modeled improvement not met; no candidate emitted"],
    }

from thermal_model.schema import (
    ACTION_KINDS,
    SOURCE_WEIGHTS,
    THERMAL_ITEMS,
    ShadowOutput,
    validate_shadow_output,
    DynamicsModel,
    BehaviorModel,
    SeasonalActionVocabulary,
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


def test_behavior_model_persists_immutable_serializable_seasonal_vocabulary():
    vocabulary = SeasonalActionVocabulary(
        mode="warm",
        action_states=(("vent", ("closed", "open")),),
        transitions=("vent_open", "vent_close"),
        airflow_levels=("closed", "baseline", "boosted"),
        boosted_windows=((390, 420),),
    )
    model = BehaviorModel(
        version=1,
        feature_names=("intercept",),
        transitions={"vent_open": (0.0,)},
        seasonal_vocabulary=(vocabulary,),
    )

    assert asdict(model)["seasonal_vocabulary"][0]["mode"] == "warm"
    assert model.seasonal_vocabulary[0].boosted_windows == ((390, 420),)
    with pytest.raises(FrozenInstanceError):
        vocabulary.mode = "winter"



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


def test_deep_shadow_schema_accepts_exact_available_payload():
    assert validate_shadow_output(valid_shadow_payload())["status"] == "shadow"


@pytest.mark.parametrize(
    "case",
    [
        "missing_top", "unknown_model", "missing_forecast", "bool_numeric",
        "naive_time", "command_marker", "too_many_trajectory",
        "too_many_observed", "nonmonotonic_trajectory", "invalid_confidence",
        "invalid_provenance", "null_candidate_nonzero_effect",
        "identical_candidate_fake_effect", "reversed_schedule_window",
        "available_null_high", "incomplete_schedule_window",
        "summary_excludes_trajectory",
        "stale_available_age", "future_observation", "high_outside_horizon",
        "trajectory_outside_horizon", "control_reason", "too_many_reasons",
        "reversed_interval", "unknown_observed",
        "oversize",
    ],
)
def test_deep_shadow_schema_rejects_malformed_nested_payloads(case):
    payload = deepcopy(valid_shadow_payload())
    if case == "missing_top":
        del payload["current"]
    elif case == "unknown_model":
        payload["model"]["extra"] = 1
    elif case == "missing_forecast":
        del payload["forecast"]["availableHours"]
    elif case == "bool_numeric":
        payload["current"]["hallwayF"] = True
    elif case == "naive_time":
        payload["generatedAt"] = "2026-08-13T12:00:00"
    elif case == "command_marker":
        payload["forecast"]["trajectory"][0]["actions"] = ["COMMAND"]
    elif case == "too_many_trajectory":
        payload["forecast"]["trajectory"] = [
            {**payload["forecast"]["trajectory"][0], "at": f"2026-08-{day:02d}T06:00:00-06:00"}
            for day in range(1, 75)
        ]
    elif case == "too_many_observed":
        payload["forecast"]["observed"] *= 26
    elif case == "nonmonotonic_trajectory":
        payload["forecast"]["trajectory"].reverse()
    elif case == "invalid_confidence":
        payload["confidence"]["grade"] = "high"
    elif case == "invalid_provenance":
        payload["provenance"]["actions"] = "invented"
    elif case == "null_candidate_nonzero_effect":
        payload["schedule"]["effect"]["hallwayPeakDeltaF"] = -1.0
    elif case == "identical_candidate_fake_effect":
        payload["schedule"]["candidate"] = deepcopy(
            payload["schedule"]["baseline"]
        )
        payload["schedule"]["effect"]["hallwayPeakDeltaF"] = -2.0
    elif case == "reversed_schedule_window":
        payload["schedule"]["baseline"]["ventOpenAt"] = (
            payload["schedule"]["baseline"]["ventCloseAt"]
        )
    elif case == "available_null_high":
        payload["forecast"]["hallwayHighF"] = None
    elif case == "incomplete_schedule_window":
        payload["schedule"]["baseline"]["ventCloseAt"] = None
    elif case == "summary_excludes_trajectory":
        payload["forecast"]["hallwayHighF"] = 74.5
    elif case == "stale_available_age":
        payload["provenance"]["currentAgeMinutes"]["radiation"] = 21.0
    elif case == "future_observation":
        payload["forecast"]["observed"][0]["at"] = "2026-08-13T12:01:00+00:00"
    elif case == "high_outside_horizon":
        payload["forecast"]["hallwayHighAt"] = "2026-08-14T12:01:00+00:00"
    elif case == "trajectory_outside_horizon":
        payload["forecast"]["trajectory"][-1]["at"] = (
            "2026-08-14T07:00:00-06:00"
        )
    elif case == "control_reason":
        payload["reasons"] = ["jdbc failed\nsecret"]
    elif case == "too_many_reasons":
        payload["reasons"] = [str(index) for index in range(9)]
    elif case == "reversed_interval":
        payload["forecast"]["intervalLowF"] = 90.0
    elif case == "unknown_observed":
        payload["forecast"]["observed"][0]["commands"] = []
    elif case == "oversize":
        payload["reasons"] = ["x" * (16 * 1024)]

    with pytest.raises(ValueError):
        validate_shadow_output(payload)


def test_shadow_output_rejects_live_or_actuator_fields():
    output = ShadowOutput.empty(datetime(2026, 8, 13, tzinfo=timezone.utc))
    assert validate_shadow_output(output.to_dict())["status"] == "shadow"
    payload = output.to_dict() | {"status": "advisory"}
    with pytest.raises(ValueError, match="shadow"):
        validate_shadow_output(payload)
    payload = output.to_dict() | {"commands": [{"item": "Anything", "state": "ON"}]}
    with pytest.raises(ValueError, match="unknown fields"):
        validate_shadow_output(payload)
