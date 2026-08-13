from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import math
from typing import Literal

THERMAL_ITEMS = {
    "air": "AmbientWeatherWS2902A_IndoorSensor_Temperature",
    "mass": "AmbientWeatherWS2902A_WH31E_193_Temperature",
    "glazing": "Shelly_HT1_Indoor_Temperature",
    "outdoor": "AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature",
    "radiation": "AmbientWeatherWS2902A_SolarRadiation",
}
ACTION_KINDS = ("vent", "indoor_shade", "outdoor_shade", "kiva")
SOURCE_WEIGHTS = {
    "nostr_confirmed": 1.0,
    "manual_dm": 1.0,
    "photosensor": 0.8,
    "historical_reconstruction": 0.35,
    "model_inferred": 0.15,
}
SHADOW_OUTPUT_FIELDS = {
    "version", "status", "generatedAt", "model", "current", "forecast",
    "schedule", "confidence", "provenance", "reasons",
}


@dataclass(frozen=True)
class ActionEvent:
    event_id: str
    idempotency_key: str
    received_at: datetime
    effective_at: datetime
    action: Literal["vent", "indoor_shade", "outdoor_shade", "kiva"]
    state: str
    source: str
    confidence: float
    interval_id: str | None = None
    note: str = ""
    supersedes: str | None = None


@dataclass(frozen=True)
class ModeEvent:
    event_id: str
    idempotency_key: str
    received_at: datetime
    effective_at: datetime
    mode: Literal["spring", "warm", "fall_charge", "winter"]
    source: str
    confidence: float
    note: str = ""
    supersedes: str | None = None


@dataclass(frozen=True)
class ThermalSample:
    at: datetime
    air_f: float
    mass_f: float
    glazing_f: float | None
    outdoor_f: float
    radiation_wm2: float
    vent_open: float | None
    vent_confidence: float
    indoor_shade_closed: float | None
    indoor_shade_confidence: float
    outdoor_shade_present: float | None
    outdoor_shade_confidence: float
    action_confidence: float
    passive_fit_allowed: bool
    mode: Literal["spring", "warm", "fall_charge", "winter"] | None = None


@dataclass(frozen=True)
class DynamicsModel:
    version: int
    step_minutes: int
    air_coefficients: dict[str, float]
    mass_coefficients: dict[str, float]
    glazing_observation_coefficients: dict[str, float]


@dataclass(frozen=True)
class SeasonalActionVocabulary:
    mode: Literal["spring", "warm", "fall_charge", "winter"]
    action_states: tuple[tuple[str, tuple[str, ...]], ...] = ()
    transitions: tuple[str, ...] = ()
    airflow_levels: tuple[str, ...] = ()
    boosted_windows: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class BehaviorModel:
    version: int
    feature_names: tuple[str, ...]
    transitions: dict[str, tuple[float, ...]]
    seasonal_vocabulary: tuple[SeasonalActionVocabulary, ...] = ()


@dataclass(frozen=True)
class ThermalArtifact:
    schema: str
    created_at: str
    trained_from: str
    trained_through: str
    code_revision: str
    dynamics: DynamicsModel
    behavior: BehaviorModel
    metrics: dict[str, float]
    data_manifest: dict[str, object]


@dataclass(frozen=True)
class ShadowOutput:
    version: int
    status: Literal["shadow"]
    generatedAt: str
    model: dict[str, object] = field(default_factory=dict)
    current: dict[str, float | None] = field(default_factory=dict)
    forecast: dict[str, object] = field(default_factory=dict)
    schedule: dict[str, object] = field(default_factory=dict)
    confidence: dict[str, object] = field(default_factory=dict)
    provenance: dict[str, object] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    @classmethod
    def empty(cls, at: datetime):
        generated = _aware_timestamp(at.isoformat(), "generatedAt").isoformat()
        return cls(
            version=1,
            status="shadow",
            generatedAt=generated,
            current={"hallwayF": None, "massF": None, "glazingF": None},
            forecast={
                "availableHours": 0,
                "hallwayHighF": None,
                "hallwayHighAt": None,
                "hallwayLowF": None,
                "hallwayLowAt": None,
                "morningMassF": None,
                "intervalLowF": None,
                "intervalHighF": None,
                "trajectory": [],
                "observed": [],
            },
            confidence={"grade": "unavailable", "actionLabels": "unknown"},
            provenance={
                "sensorItems": dict(THERMAL_ITEMS),
                "actions": "unknown",
                "currentAgeMinutes": {
                    role: None for role in THERMAL_ITEMS
                },
                "modelAgeHours": None,
                "trainingDataAgeHours": None,
            },
            reasons=["unavailable"],
        )

    def to_dict(self):
        return asdict(self)


_MODEL_FIELDS = {"createdAt", "trainedThrough", "codeRevision"}
_CURRENT_FIELDS = {"hallwayF", "massF", "glazingF"}
_FORECAST_FIELDS = {
    "availableHours", "hallwayHighF", "hallwayHighAt", "hallwayLowF",
    "hallwayLowAt", "morningMassF", "intervalLowF", "intervalHighF",
    "trajectory", "observed",
}
_SCHEDULE_FIELDS = {"baseline", "candidate", "effect"}
_SCHEDULE_TIME_FIELDS = {"ventOpenAt", "ventCloseAt"}
_EFFECT_FIELDS = {"morningMassDeltaF", "hallwayPeakDeltaF"}
_TRAJECTORY_FIELDS = {"at", "hallwayF", "massF", "lowF", "highF", "actions"}
_OBSERVED_FIELDS = {"at", "hallwayF", "massF"}
_CONFIDENCE_FIELDS = {"grade", "actionLabels"}
_PROVENANCE_FIELDS = {
    "sensorItems", "actions", "currentAgeMinutes", "modelAgeHours",
    "trainingDataAgeHours",
}
_ACTION_MARKERS = {
    "vent_open", "vent_close", "indoor_shade_open", "indoor_shade_close",
    "outdoor_shade_installed", "outdoor_shade_removed",
}
_ACTION_LABELS = {
    "unknown", "model_inferred", "reconstructed", "photosensor", "confirmed",
}
_ACTION_PROVENANCE = {
    "unknown", "model_inferred", "historical_reconstruction", "photosensor",
    "operator_confirmed",
}
_MAX_SHADOW_BYTES = 16 * 1024


def _exact_object(value, fields, path):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{path} has missing or unknown fields")
    return value


def _number(value, path, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{path} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{path} must be at least {minimum}")
    return number


def _optional_number(value, path, *, minimum=None):
    return None if value is None else _number(value, path, minimum=minimum)


def _aware_timestamp(value, path):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be an aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path} must be an aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{path} must be an aware ISO-8601 timestamp")
    return parsed


def _validate_times(rows, path, fields, limit, *, local_hour=False):
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError(f"{path} must contain at most {limit} rows")
    prior = None
    for index, row in enumerate(rows):
        _exact_object(row, fields, f"{path}[{index}]")
        at = _aware_timestamp(row["at"], f"{path}[{index}].at")
        if local_hour and (at.minute or at.second or at.microsecond):
            raise ValueError(f"{path}[{index}].at must be an exact local hour")
        if prior is not None and at <= prior:
            raise ValueError(f"{path} timestamps must be strictly increasing")
        prior = at
    return rows


def _validate_schedule_time(value, path):
    if value is None:
        return
    _aware_timestamp(value, path)


def validate_shadow_output(payload):
    """Validate the exact bounded, non-actuating thermal shadow v1 contract."""
    _exact_object(payload, SHADOW_OUTPUT_FIELDS, "shadow output")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("thermal output version must be exact integer 1")
    if payload["status"] != "shadow":
        raise ValueError("thermal output must be version 1 shadow")
    generated_at = _aware_timestamp(payload["generatedAt"], "generatedAt")

    model = payload["model"]
    if model:
        _exact_object(model, _MODEL_FIELDS, "model")
        created_at = _aware_timestamp(model["createdAt"], "model.createdAt")
        trained_through = _aware_timestamp(
            model["trainedThrough"], "model.trainedThrough"
        )
        if not trained_through <= created_at <= generated_at:
            raise ValueError("model timestamps must be chronological")
        revision = model["codeRevision"]
        if (
            not isinstance(revision, str)
            or not 7 <= len(revision) <= 64
            or any(character not in "0123456789abcdef" for character in revision)
        ):
            raise ValueError("model.codeRevision must be a hexadecimal revision")
    elif model != {}:
        raise ValueError("model must be an exact object")

    current = _exact_object(payload["current"], _CURRENT_FIELDS, "current")
    for field_name in _CURRENT_FIELDS:
        _optional_number(current[field_name], f"current.{field_name}")

    forecast = _exact_object(payload["forecast"], _FORECAST_FIELDS, "forecast")
    hours = forecast["availableHours"]
    if type(hours) is not int or not 0 <= hours <= 72:
        raise ValueError("forecast.availableHours must be an integer within [0, 72]")
    numeric_forecast = (
        "hallwayHighF", "hallwayLowF", "morningMassF", "intervalLowF",
        "intervalHighF",
    )
    for field_name in numeric_forecast:
        _optional_number(forecast[field_name], f"forecast.{field_name}")
    for field_name in ("hallwayHighAt", "hallwayLowAt"):
        if forecast[field_name] is not None:
            _aware_timestamp(forecast[field_name], f"forecast.{field_name}")
    low = forecast["intervalLowF"]
    high = forecast["intervalHighF"]
    if (low is None) != (high is None) or (
        low is not None and float(low) > float(high)
    ):
        raise ValueError("forecast interval must be complete and ordered")

    trajectory = _validate_times(
        forecast["trajectory"], "forecast.trajectory", _TRAJECTORY_FIELDS, 73,
        local_hour=True,
    )
    for index, row in enumerate(trajectory):
        hallway = _number(row["hallwayF"], f"forecast.trajectory[{index}].hallwayF")
        _number(row["massF"], f"forecast.trajectory[{index}].massF")
        row_low = _number(row["lowF"], f"forecast.trajectory[{index}].lowF")
        row_high = _number(row["highF"], f"forecast.trajectory[{index}].highF")
        if not row_low <= hallway <= row_high:
            raise ValueError("trajectory interval must contain hallway temperature")
        actions = row["actions"]
        if (
            not isinstance(actions, list)
            or any(not isinstance(action, str) or action not in _ACTION_MARKERS for action in actions)
            or len(actions) != len(set(actions))
        ):
            raise ValueError("trajectory actions violate the closed vocabulary")

    observed = _validate_times(
        forecast["observed"], "forecast.observed", _OBSERVED_FIELDS, 25
    )
    for index, row in enumerate(observed):
        _number(row["hallwayF"], f"forecast.observed[{index}].hallwayF")
        _number(row["massF"], f"forecast.observed[{index}].massF")

    schedule = payload["schedule"]
    if schedule:
        _exact_object(schedule, _SCHEDULE_FIELDS, "schedule")
        baseline = _exact_object(
            schedule["baseline"], _SCHEDULE_TIME_FIELDS, "schedule.baseline"
        )
        for field_name in _SCHEDULE_TIME_FIELDS:
            _validate_schedule_time(
                baseline[field_name], f"schedule.baseline.{field_name}"
            )
        candidate = schedule["candidate"]
        if candidate is not None:
            _exact_object(candidate, _SCHEDULE_TIME_FIELDS, "schedule.candidate")
            for field_name in _SCHEDULE_TIME_FIELDS:
                _validate_schedule_time(
                    candidate[field_name], f"schedule.candidate.{field_name}"
                )
        effect = _exact_object(schedule["effect"], _EFFECT_FIELDS, "schedule.effect")
        effects = [
            _number(effect[field_name], f"schedule.effect.{field_name}")
            for field_name in _EFFECT_FIELDS
        ]
        if candidate is None and any(value != 0.0 for value in effects):
            raise ValueError("null candidate requires zero modeled effect")
        if candidate is not None and candidate == baseline and all(value == 0.0 for value in effects):
            raise ValueError("candidate must differ from the baseline")
    elif schedule != {}:
        raise ValueError("schedule must be an exact object")

    confidence = _exact_object(payload["confidence"], _CONFIDENCE_FIELDS, "confidence")
    if confidence["grade"] not in {"low", "unavailable"}:
        raise ValueError("confidence grade must be low or unavailable")
    if confidence["actionLabels"] not in _ACTION_LABELS:
        raise ValueError("confidence action labels are invalid")

    provenance = _exact_object(payload["provenance"], _PROVENANCE_FIELDS, "provenance")
    if provenance["sensorItems"] != THERMAL_ITEMS:
        raise ValueError("provenance sensor items do not match the contract")
    if provenance["actions"] not in _ACTION_PROVENANCE:
        raise ValueError("provenance actions are invalid")
    expected_action_source = {
        "unknown": "unknown",
        "model_inferred": "model_inferred",
        "reconstructed": "historical_reconstruction",
        "photosensor": "photosensor",
        "confirmed": "operator_confirmed",
    }[confidence["actionLabels"]]
    if provenance["actions"] != expected_action_source:
        raise ValueError("confidence and provenance action labels disagree")
    ages = _exact_object(
        provenance["currentAgeMinutes"], set(THERMAL_ITEMS),
        "provenance.currentAgeMinutes",
    )
    for role, age in ages.items():
        _optional_number(age, f"provenance.currentAgeMinutes.{role}", minimum=0.0)
    _optional_number(provenance["modelAgeHours"], "provenance.modelAgeHours", minimum=0.0)
    _optional_number(
        provenance["trainingDataAgeHours"],
        "provenance.trainingDataAgeHours", minimum=0.0,
    )

    reasons = payload["reasons"]
    if not isinstance(reasons, list) or not reasons or any(
        not isinstance(reason, str) or not reason for reason in reasons
    ):
        raise ValueError("reasons must contain nonempty strings")

    unavailable = confidence["grade"] == "unavailable"
    if unavailable and confidence["actionLabels"] != "unknown":
        raise ValueError("unavailable shadow action labels must be unknown")
    if unavailable and (schedule != {} or hours != 0 or trajectory):
        raise ValueError("unavailable shadow must have no schedule or trajectory")
    if unavailable and any(forecast[field_name] is not None for field_name in numeric_forecast):
        raise ValueError("unavailable shadow forecast summaries must be null")
    if not unavailable and (
        not model
        or not 24 <= hours <= 72
        or schedule == {}
        or current["hallwayF"] is None
        or current["massF"] is None
        or any(forecast[field_name] is None for field_name in numeric_forecast)
        or forecast["hallwayHighAt"] is None
        or forecast["hallwayLowAt"] is None
    ):
        raise ValueError("available shadow requires model, schedule, and 24-72 hours")

    try:
        encoded = json.dumps(
            payload, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("shadow output must be finite JSON") from exc
    if len(encoded) >= _MAX_SHADOW_BYTES:
        raise ValueError("shadow output exceeds the 16 KiB bound")
    return payload
