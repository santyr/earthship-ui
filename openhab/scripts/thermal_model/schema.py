from dataclasses import asdict, dataclass, field
from datetime import datetime
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


@dataclass(frozen=True)
class DynamicsModel:
    version: int
    step_minutes: int
    air_coefficients: dict[str, float]
    mass_coefficients: dict[str, float]
    glazing_observation_coefficients: dict[str, float]


@dataclass(frozen=True)
class BehaviorModel:
    version: int
    feature_names: tuple[str, ...]
    transitions: dict[str, tuple[float, ...]]


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
        return cls(version=1, status="shadow", generatedAt=at.isoformat())

    def to_dict(self):
        return asdict(self)


def validate_shadow_output(payload):
    unknown = set(payload) - SHADOW_OUTPUT_FIELDS
    if unknown:
        raise ValueError(f"unknown fields: {sorted(unknown)}")
    if payload.get("version") != 1 or payload.get("status") != "shadow":
        raise ValueError("thermal output must be version 1 shadow")
    return payload
