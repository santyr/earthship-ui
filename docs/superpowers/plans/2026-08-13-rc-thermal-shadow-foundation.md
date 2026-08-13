# RC Thermal Shadow Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first reproducible, journal-backed Earthship thermal intelligence system: constrained 2R2C dynamics, a learned human-behavior baseline, 48–72 hour shadow forecasts, and an honest Earthship UI card.

**Architecture:** A focused Python package reads OpenHAB JDBC history plus an append-only PostgreSQL action journal in the `thermal_intel` schema of the existing OpenHAB `openhab` database, constructs confidence-weighted five-minute samples, fits constrained dynamics and behavior models, and atomically publishes versioned artifacts. A separate shadow runner consumes the accepted artifact and current weather, publishes one bounded observational JSON item, and never changes `Thermal_Advisory` or commands an actuator. Svelte parses and renders that JSON as a shadow-only card.

**Tech Stack:** Python 3.12 standard library, NumPy 1.26, SciPy 1.11, pytest, psycopg2, PostgreSQL 16, OpenHAB 5.2 REST/JDBC persistence, user-level systemd, Svelte 5, Vitest/jsdom, Playwright.

## Global Constraints

- Authoritative spec: `docs/superpowers/specs/2026-08-13-rc-thermal-model-design.md` at or after commit `142460d`.
- The physical core has exactly two states: hallway room air and north-wall thermal mass. South-glazing temperature is an auxiliary observation, not a third state.
- Exact physical items: `AmbientWeatherWS2902A_IndoorSensor_Temperature`, `AmbientWeatherWS2902A_WH31E_193_Temperature`, `Shelly_HT1_Indoor_Temperature`, `AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature`, and `AmbientWeatherWS2902A_SolarRadiation`.
- OpenHAB JDBC and the append-only action journal are authoritative. Derived datasets and artifacts must be reproducible.
- Prefer OpenHAB-backed persistence whenever it can preserve the required semantics; justify any local store.
- Historical action reconstruction is lower-confidence evidence. Confirmed records override photosensor observations, which override reconstruction and inference.
- Kiva or unexplained heat-input intervals are excluded from passive fitting.
- All evaluation splits are chronological. No future observations may affect an earlier prediction.
- Warm-season reference: hallway peak above 82 F. Winter shadow reference: 60 F, without classifying ordinary winter lows in the 50s as system failure.
- Warm-season nightly venting is the baseline throughout spring, summer, and fall. The scheduler may learn and compare timing/duration, but it must not turn the warm-season problem into a vent-or-do-not-vent choice.
- All outputs remain `shadow`. Do not modify `Thermal_Advisory`, notification policy, or existing forecast scoring.
- No actuator item, command path, generic tool-call path, or automation authority may be added.
- Nostr reply collection, photosensor ingestion, advisory graduation, actuator control, and local language-model training are separate follow-on projects.
- Tasks 1–9 are local/offline and may only prepare observational resources. Task 10 may apply the one observational OpenHAB Item and deploy services only after an attended snapshot/rollback review and explicit operator approval.
- Preserve the tracked/deployed `forecast_intel.py` byte-identity invariant whenever its shared helpers are touched.

### Deterministic test-fixture contract

Every helper name in the focused test excerpts below is defined in that same
test file; none is a hidden production dependency:

- Dataset fixtures use `START = 2026-08-13T00:00:00Z`, `END = START + 2h`,
  `HOUR = timedelta(hours=1)`, and five-minute sensor rows. `fixture_series()`
  supplies air `74 + 0.1*t`, mass `72 + 0.02*t`, optional glazing `76 + 0.1*t`,
  outdoor `68 + 0.05*t`, and radiation `max(0, 700*sin(pi*t/24))`; its gap
  variant removes every role for the same 35-minute interval.
- `action()` and `mode_event()` are thin constructors for the exact immutable
  records in Task 1. `reconstructed_warm_events()` uses only
  `historical_reconstruction` at `0.35` confidence.
- `synthetic_2r2c_days()` uses the Task 4 equations and coefficients
  `outside=0.015`, `mass=0.04`, `solar_unshaded=0.00008`,
  `solar_indoor_closed=0.00002`, `solar_outdoor=0.000035`, `vent=0.12`,
  `mass_air=0.005`, with seeded uniform noise bounded to `0.015 F` air and
  `0.005 F` mass. The first 18 days train and the last 3 days hold out.
  `initial_from()`, `forcings_from()`, and `mae()` are direct projections and
  arithmetic mean absolute error; `unphysical_model()` changes only the named
  coefficient.
- Behavior fixtures contain 21 complete local days. Warm fixtures confirm vent
  open at 20:30 and close at 07:00, daytime shade close/open transitions around
  sun exposure, and no Kiva interval. Winter fixtures contain no venting,
  daytime shade-open events only on sunny days, and closed shades on cold cloudy
  days and nights.
- Artifact fixtures use a Task 4 stable model, the Task 5 behavior model,
  `earthship-thermal-model/v1`, UTC ranges, exact item identities, finite
  metrics, and a real canonical-row digest. The 45-day evaluation fixture has
  one-day folds after a 14-day minimum train window and captures each fold
  boundary directly from the evaluator result.
- Pipeline fixtures use `NOW = 2026-08-13T12:00:00Z`, an accepted fixture
  artifact, timestamped current states, and exactly 72 hourly forecast rows.
- The JavaScript `fixture(overrides)` returns the exact Task 7 v1 shadow payload,
  deep-merges explicit overrides, and never fills malformed fields silently.

---

## File Structure

Create one importable package under `openhab/scripts/thermal_model/`:

- `schema.py`: immutable records, item names, artifact/output schemas, and validation.
- `journal.py`: append-only PostgreSQL schema and correction-aware reads.
- `actions.py`: `THERMAL` grammar, seasonal reconstruction, and interval projection.
- `dataset.py`: JDBC history alignment, quality gates, and five-minute samples.
- `dynamics.py`: constrained 2R2C fitting and simulation.
- `behavior.py`: weighted transition model and learned baseline schedule.
- `artifacts.py`: atomic model registry, quarantine, and versioned serialization.
- `evaluation.py`: chronological backtests, baselines, metrics, and acceptance report.
- `pipeline.py`: training and shadow orchestration with dependency injection.

Keep executable concerns in `openhab/scripts/thermal_intel.py`. It exposes only
`journal`, `train`, `backtest`, and `shadow` subcommands. It must not accept an
OpenHAB command or actuator target.

---

### Task 1: Lock the shared schemas and safety contract

**Files:**
- Create: `openhab/scripts/thermal_model/__init__.py`
- Create: `openhab/scripts/thermal_model/schema.py`
- Create: `openhab/scripts/test_thermal_schema.py`

**Interfaces:**
- Consumes: no earlier task.
- Produces: `ActionEvent`, `ModeEvent`, `ThermalSample`, `DynamicsModel`, `BehaviorModel`, `ThermalArtifact`, `ShadowOutput`, `validate_shadow_output()`, and exact item constants used by every later task.

- [ ] **Step 1: Write the failing schema tests**

Create `openhab/scripts/test_thermal_schema.py`:

```python
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from thermal_model.schema import (
    ACTION_KINDS,
    SOURCE_WEIGHTS,
    THERMAL_ITEMS,
    ShadowOutput,
    ThermalSample,
    validate_shadow_output,
)


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


def test_thermal_sample_preserves_each_action_confidence():
    names = {item.name for item in fields(ThermalSample)}
    assert {
        "vent_confidence",
        "indoor_shade_confidence",
        "outdoor_shade_confidence",
    } <= names


def test_shadow_output_rejects_live_or_actuator_fields():
    output = ShadowOutput.empty(datetime(2026, 8, 13, tzinfo=timezone.utc))
    assert validate_shadow_output(output.to_dict())["status"] == "shadow"
    payload = output.to_dict() | {"status": "advisory"}
    with pytest.raises(ValueError, match="shadow"):
        validate_shadow_output(payload)
    payload = output.to_dict() | {"commands": [{"item": "Anything", "state": "ON"}]}
    with pytest.raises(ValueError, match="unknown fields"):
        validate_shadow_output(payload)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_schema.py`

Expected: collection fails because `thermal_model.schema` does not exist.

- [ ] **Step 3: Implement the immutable schema**

Create an empty `openhab/scripts/thermal_model/__init__.py`. Create
`openhab/scripts/thermal_model/schema.py` with these public definitions:

```python
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
```

- [ ] **Step 4: Run the schema tests**

Run: `pytest -q openhab/scripts/test_thermal_schema.py`

Expected: `2 passed`.

- [ ] **Step 5: Commit the schema contract**

```bash
git add openhab/scripts/thermal_model/__init__.py \
  openhab/scripts/thermal_model/schema.py \
  openhab/scripts/test_thermal_schema.py
git commit -m "feat: define thermal model data contracts"
```

---

### Task 2: Add the append-only PostgreSQL action journal and local `THERMAL` ingestion

**Files:**
- Create: `openhab/scripts/thermal_model/journal.py`
- Create: `openhab/scripts/thermal_model/actions.py`
- Create: `openhab/scripts/test_thermal_journal.py`
- Create: `openhab/scripts/test_thermal_actions.py`
- Create: `openhab/scripts/thermal_intel.py`

**Interfaces:**
- Consumes: `ActionEvent`, `ModeEvent`, `ACTION_KINDS`, and `SOURCE_WEIGHTS` from Task 1.
- Produces: `ActionJournal.append(event)`, `ActionJournal.append_batch(actions, modes)`, `ActionJournal.effective_events(start, end)`, `ActionJournal.effective_modes(start, end)`, `parse_thermal_message(text, received_at, idempotency_key)`, and CLI `thermal_intel.py journal --message-file PATH --idempotency-key KEY`.

Storage contract: use Python `psycopg2` against PostgreSQL 16, with DSN from
`THERMAL_DATABASE_URL`; never hardcode or print credentials. The application
owns only a dedicated `thermal_intel` schema in the existing OpenHAB `openhab`
database and must not modify OpenHAB-generated persistence tables. Use a
least-privilege runtime role. Deployment-time schema/role setup is deferred to the later explicit live-approval gate. Development and CI tests use an
ephemeral PostgreSQL instance/schema and never write production.

OpenHAB Item time-series persistence cannot provide atomic multi-event batches,
receipt-key idempotency, or foreign-key correction/supersession links. That is
why the journal is application-owned PostgreSQL while OpenHAB remains the
authority for sensor history; this keeps the journal inside the existing
storage and backup ecosystem without coupling its schema to generated tables.

- [ ] **Step 1: Write failing journal and parser tests**

Create tests against an ephemeral PostgreSQL 16 schema and never the production database. The tests must verify transactional batch insertion,
unique receipt keys, correction foreign keys, `TIMESTAMPTZ` round trips,
append-only guards, and correction-aware reads. A representative event uses
`event_id`, `idempotency_key`, timezone-aware received/effective timestamps,
`action="vent"`, `source="manual_dm"`, and confidence `1.0`; appending it twice
must return true then false, while a superseding correction preserves both rows
and only the correction appears in effective reads. Parser tests retain the
exact `THERMAL` grammar and receipt behavior below.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_journal.py openhab/scripts/test_thermal_actions.py`

Expected: import failures for `journal` and `actions`.

- [ ] **Step 3: Implement the PostgreSQL journal schema and correction-aware reads**

`journal.py` must create the dedicated `thermal_intel` schema and application
 tables through an explicit migration/setup path, then use one PostgreSQL
 transaction for schema creation and one for each append. `append_batch()`
 inserts one `message_receipts` row and all action/mode rows in one transaction;
 a replay with the same key and payload digest is an idempotent no-op, while
 reuse with different bytes is rejected. `effective_events()` and
 `effective_modes()` exclude superseded IDs, never delete originals, and order
 by `(effective_at, received_at, event_id)`. A bounded mode query also returns
 the last effective mode before `start`.

Use `TIMESTAMPTZ` columns, unique receipt constraints, stream-specific
supersession foreign keys, and database privileges/triggers that reject UPDATE
and DELETE on journal rows. Keep message batches transactional and preserve
correction links as relational foreign keys.

- [ ] **Step 4: Implement the closed `THERMAL` grammar**

In `actions.py`, accept only the header `THERMAL` and fields `effective`,
`mode`, `vent`, `indoor_shades`, `outdoor_shades`, `kiva`, and `note`. Normalize
`fall-charge` to `fall_charge`; accept `spring`, `warm`, and `winter`. `vent`
accepts only `open`, `closed`, or `HH:MM-HH:MM`; resolve local times against the
received date in `America/Denver`, moving a non-later stop to the next local
day. Create deterministic event IDs as
`sha256(f"{idempotency_key}:{action}:{state}:{effective_at.isoformat()}")[:24]`.
Reject duplicate fields, unknown fields/states, missing timezone information,
and messages larger than 4096 UTF-8 bytes. Return a frozen
`ParsedThermalMessage` with action/mode tuples. A mode-only message is valid.
Both events from an overnight interval share a deterministic `interval_id`;
standalone transitions leave it `None`. `ActionJournal.append_batch()` stores
both tuples atomically.

- [ ] **Step 5: Add the journal CLI without transport logic**

`thermal_intel.py journal` reads the entire `--message-file`, parses it, appends
all events in one PostgreSQL transaction, reads them back, and prints a compact
JSON receipt. The default DSN comes only from `THERMAL_DATABASE_URL`; tests may
use a separate ephemeral test-only DSN/environment override. Required arguments
are `--message-file` and `--idempotency-key`; optional `--received-at` is an ISO
timestamp for deterministic tests. Do not add relay, Nostr-key, shell-command,
or OpenHAB-command arguments.

- [ ] **Step 6: Run tests and a receipt smoke test**

Run the focused schema/journal/actions tests against an ephemeral PostgreSQL
instance and a CLI smoke test with a temporary schema. A repeated command must
report `inserted: 0`; no test may connect to the production DSN.

- [ ] **Step 7: Commit the journal slice**

```bash
git add openhab/scripts/thermal_model/journal.py \
  openhab/scripts/thermal_model/actions.py \
  openhab/scripts/thermal_intel.py \
  openhab/scripts/test_thermal_journal.py \
  openhab/scripts/test_thermal_actions.py
git commit -m "feat: add append-only thermal action journal"
```

### Task 3: Build quality-gated five-minute training samples

**Files:**
- Create: `openhab/scripts/thermal_model/dataset.py`
- Create: `openhab/scripts/test_thermal_dataset.py`
- Modify: `openhab/scripts/thermal_model/actions.py`

**Interfaces:**
- Consumes: `forecast_intel.series()`, `forecast_intel.local_day_window_utc()`, effective `ActionEvent` records, and effective `ModeEvent` records.
- Produces: `build_samples(series_by_role, events, modes, start, end) -> list[ThermalSample]`, `reconstruct_events(start, end, modes)`, and `dataset_manifest(samples, events, modes)`.

- [ ] **Step 1: Write failing alignment, confidence, and exclusion tests**

Use a synthetic two-hour fixture with irregular timestamps. Assert:

```python
def test_five_minute_alignment_does_not_bridge_large_gaps():
    samples = build_samples(
        series_by_role=fixture_series(gap_minutes=35),
        events=[],
        modes=[],
        start=START,
        end=END,
    )
    assert all(sample.at.minute % 5 == 0 for sample in samples)
    assert not any(GAP_START <= sample.at <= GAP_END for sample in samples)


def test_confirmed_actions_override_reconstruction_and_kiva_excludes_passive_fit():
    events = reconstructed_warm_events(START, END) + [
        action("confirmed-vent", "vent", "closed", START, "manual_dm", 1.0),
        action("kiva-on", "kiva", "on", START + HOUR, "manual_dm", 1.0),
    ]
    samples = build_samples(
        fixture_series(), events, [mode_event("warm", START)], START, END
    )
    assert samples[0].vent_open == 0.0
    assert samples[0].vent_confidence == 1.0
    assert samples[0].indoor_shade_confidence == 0.35
    assert samples[0].action_confidence == 0.35
    assert next(sample for sample in samples if sample.at == START + HOUR).passive_fit_allowed is False
```

Also test winter reconstruction: sunny daytime indoor shades open; cold cloudy
daytime and nighttime shades closed; no winter vent intervals.

- [ ] **Step 2: Run the dataset tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_dataset.py`

Expected: import failure for `thermal_model.dataset`.

- [ ] **Step 3: Implement seasonal reconstruction**

Add pure helpers in `actions.py`:

```python
def reconstruct_state(regime, *, is_daylight, sunny, cold_cloudy):
    if regime == "winter":
        return {
            "vent_open": 0.0,
            "indoor_shade_closed": float((not is_daylight) or cold_cloudy),
        }
    if regime == "fall_charge":
        return {
            "vent_open": float(not is_daylight),
            "indoor_shade_closed": None,
        }
    return {
        "vent_open": float(not is_daylight),
        "indoor_shade_closed": float(is_daylight and sunny),
    }
```

`reconstruct_events()` derives regime intervals only from effective `ModeEvent`
records. Before the first mode event, or across a correction gap, action state
is `unknown`; it must not guess a season from day-of-year. Historical backfill
therefore begins by journaling operator-reviewed mode transitions with their
approximate effective dates. Those approximate transitions retain source and
confidence and can later be superseded without editing history.

`sunny` is measured radiation above 150 W/m2 while solar elevation is positive.
`cold_cloudy` is daylight, radiation below 100 W/m2, and outdoor temperature
below 40 F. These are reconstruction labels only, stored with source
`historical_reconstruction` and confidence `0.35`; they are not control rules.

- [ ] **Step 4: Implement five-minute alignment and quality gates**

`dataset.py` must:

- Convert all timestamps to aware UTC.
- Bucket by floor-to-five-minute timestamp and retain the median finite value.
- Require air, mass, outdoor, and radiation within each bucket. Glazing remains
  optional: missing, non-finite, out-of-range, excessive-jump, and gap-invalid
  glazing becomes `None` for that bucket and is counted by auxiliary exclusion
  reason without rejecting an otherwise valid core sample.
- Reject required temperatures outside `[-40, 140] F`, radiation outside
  `[0, 1600] W/m2`, required-temperature jumps above `10 F` per five minutes,
  and required-source gaps above 20 minutes.
- Project action intervals using source precedence and use the minimum joined
  confidence among action states whose value is non-`None` as
  `action_confidence`. Preserve `vent_confidence`, `indoor_shade_confidence`,
  and `outdoor_shade_confidence` separately. An explicit unknown state remains
  `None` with per-action confidence zero but does not reduce the aggregate for
  other known states; when every action state is unknown, the aggregate is zero.
- Set `passive_fit_allowed=False` while Kiva is on and for two hours after its
  confirmed stop; also exclude intervals tagged `exceptional_heat_unknown`.
  Derive Kiva transitions and cooldowns from precedence-resolved effective
  state so a losing same-time event cannot fabricate an interval.
- Emit no interpolated sample across a rejected gap.

The manifest includes UTC start/end, sample count, rejected counts by reason,
auxiliary exclusion counts by reason, event counts by source, exact item names,
and a SHA-256 digest over canonical JSON rows.

- [ ] **Step 5: Run dataset and existing timezone tests**

Run:

```bash
pytest -q openhab/scripts/test_thermal_dataset.py \
  openhab/scripts/test_forecast_intel.py -k 'timezone or window or series'
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the dataset slice**

```bash
git add openhab/scripts/thermal_model/actions.py \
  openhab/scripts/thermal_model/dataset.py \
  openhab/scripts/test_thermal_dataset.py
git commit -m "feat: build thermal training samples"
```

---

### Task 4: Fit and simulate the constrained 2R2C dynamics

**Files:**
- Create: `openhab/scripts/thermal_model/dynamics.py`
- Create: `openhab/scripts/test_thermal_dynamics.py`

**Interfaces:**
- Consumes: consecutive `ThermalSample` values from Task 3.
- Produces: `fit_dynamics(samples) -> DynamicsModel`, `predict_step(model, sample) -> tuple[float, float, float | None]`, and `simulate(model, initial, forcings) -> list[dict]`.

- [ ] **Step 1: Write synthetic identification and physical-rejection tests**

Generate 21 days from known stable coefficients, add deterministic bounded
noise, and assert held-out recovery:

```python
def test_fit_recovers_stable_synthetic_2r2c():
    training, holdout = synthetic_2r2c_days(days=21, seed=7)
    model = fit_dynamics(training)
    predicted = simulate(model, initial_from(holdout[0]), forcings_from(holdout))
    assert mae([row["air_f"] for row in predicted], [s.air_f for s in holdout[1:]]) < 0.45
    assert mae([row["mass_f"] for row in predicted], [s.mass_f for s in holdout[1:]]) < 0.25
    assert model.air_coefficients["outside_exchange"] >= 0
    assert model.air_coefficients["mass_exchange"] >= 0
    assert model.mass_coefficients["air_exchange"] >= 0


def test_fit_rejects_shaded_gain_above_unshaded_gain():
    with pytest.raises(ValueError, match="shade gain"):
        validate_physics(
            unphysical_model(indoor_closed_gain=0.02, unshaded_gain=0.01)
        )
```

- [ ] **Step 2: Run the dynamics tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_dynamics.py`

Expected: import failure for `thermal_model.dynamics`.

- [ ] **Step 3: Implement weighted bounded least squares**

For each consecutive five-minute pair, treat the left row as the starting
air/mass state and the right row as the end-of-step forcing, action-confidence,
and target row. Build these regressions:

```text
unshaded = (1-indoor_shade_closed)*(1-outdoor_shade_present)
indoor_closed = indoor_shade_closed
outdoor_shaded = (1-indoor_shade_closed)*outdoor_shade_present

delta_air = outside_exchange*(outdoor-air)
          + mass_exchange*(mass-air)
          + solar_unshaded*radiation*unshaded
          + solar_indoor_closed*radiation*indoor_closed
          + solar_outdoor*radiation*outdoor_shaded
          + vent_exchange*vent_open*(outdoor-air)
          + bias

delta_mass = air_exchange*(air-mass)
           + solar_unshaded*radiation*unshaded
           + solar_indoor_closed*radiation*indoor_closed
           + solar_outdoor*radiation*outdoor_shaded

glazing = intercept + air*air + outdoor*outdoor
        + solar_unshaded*radiation*unshaded
        + solar_indoor_closed*radiation*indoor_closed
        + solar_outdoor*radiation*outdoor_shaded
```

Multiply every design row and target by `sqrt(action_confidence)`. Exclude rows
where either endpoint has `passive_fit_allowed=False`. Fit with
`scipy.optimize.lsq_linear` and these bounds per five-minute step:

```python
AIR_BOUNDS = (
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.20],
    [0.50, 0.50, 0.020, 0.010, 0.015, 0.80, 0.20],
)
MASS_BOUNDS = (
    [0.0, 0.0, 0.0, 0.0],
    [0.20, 0.008, 0.004, 0.006],
)
```

Skip regression rows whose vent, indoor-shade, or outdoor-shade input is
unknown; report those exclusions and widen artifact uncertainty according to
the remaining action-label coverage. Fit the glazing equation only where the
right/end auxiliary observation is present, using co-temporal right/end air,
outdoor, radiation, and shade features.

Normalize effective ventilation forcing to closed `0.0`, baseline `1.0`,
and door-assisted boosted `2.0`; reject values outside `[0.0, 2.0]`.
Reject a model unless unshaded solar gain is at least both shaded gains and all
exchange coefficients are nonnegative. For closed, baseline, and boosted
ventilation, require the two-state transition matrix spectral radius to be
strictly below `1 - 1e-9`, then separately require a 72-hour
constant-forcing simulation to stay within `[-40, 140] F` without divergence.

- [ ] **Step 4: Implement deterministic simulation**

`predict_step()` applies the fitted equations once and returns end-of-step
`(air, mass, glazing)`; glazing uses returned air plus the same end forcing and
is never recursive. `simulate()` must accept explicit end-of-step five-minute
forcing rows and never read wall-clock time, files, network, or OpenHAB.
Clamp nothing during normal simulation; non-finite or out-of-range results
raise `ValueError` so an unstable
artifact cannot appear plausible.

- [ ] **Step 5: Run dynamics and dataset tests**

Run: `pytest -q openhab/scripts/test_thermal_dynamics.py openhab/scripts/test_thermal_dataset.py`

Expected: all tests pass.

- [ ] **Step 6: Commit the physical model**

```bash
git add openhab/scripts/thermal_model/dynamics.py \
  openhab/scripts/test_thermal_dynamics.py
git commit -m "feat: fit constrained Earthship thermal dynamics"
```

---

### Task 5: Learn household transitions and search bounded schedules

**Files:**
- Create: `openhab/scripts/thermal_model/behavior.py`
- Create: `openhab/scripts/test_thermal_behavior.py`

**Interfaces:**
- Consumes: labeled `ThermalSample` rows and `DynamicsModel`.
- Produces: `fit_behavior(samples) -> BehaviorModel`, `transition_probability(model, transition, features)`, `baseline_schedule()`, and `search_candidate_schedule()`.

- [ ] **Step 1: Write failing behavior and schedule tests**

Create deterministic fixtures covering warm nights and winter shade choices:

```python
def test_learned_warm_schedule_tracks_confirmed_transition_times():
    model = fit_behavior(confirmed_warm_samples(open_minute=1230, close_minute=420))
    schedule = baseline_schedule(model, warm_forecast())
    assert abs(schedule["ventOpenMinute"] - 1230) <= 20
    assert abs(schedule["ventCloseMinute"] - 420) <= 20


def test_candidate_never_vents_while_outdoor_is_warmer():
    candidate = search_candidate_schedule(
        behavior=warm_behavior(), dynamics=stable_model(), forecast=hot_night_forecast()
    )
    for row in hot_night_forecast():
        if row.at >= candidate.vent_open_at and row.at < candidate.vent_close_at:
            assert row.outdoor_f < row.air_baseline_f


def test_winter_cold_cloudy_schedule_keeps_shades_closed():
    schedule = baseline_schedule(winter_behavior(), cold_cloudy_winter_forecast())
    assert schedule["indoorShadeDay"] == "closed"
    assert schedule["vent"] == "closed"
```

- [ ] **Step 2: Run behavior tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_behavior.py`

Expected: import failure for `thermal_model.behavior`.

- [ ] **Step 3: Implement the weighted transition model**

Fit six binary transition hazards: `vent_open`, `vent_close`,
`indoor_shade_open`, `indoor_shade_close`, `outdoor_shade_installed`, and
`outdoor_shade_removed`. The outdoor-shade hazards will normally return
`insufficient_data` until several seasonal transitions exist. Feature order is
fixed:

```python
FEATURE_NAMES = (
    "intercept", "sin_time", "cos_time", "sin_year", "cos_year",
    "outdoor_minus_air", "mass_minus_air", "radiation_norm",
    "solar_elevation_sin", "is_daylight",
)
```

Use weighted ridge logistic loss with `scipy.optimize.minimize(method="L-BFGS-B")`.
Sample weights are `action_confidence`; regularize non-intercept coefficients
with `lambda=1.0`. If a transition has fewer than 10 positive confirmed-or-
reconstructed examples or only one class, omit its coefficients and return an
explicit `insufficient_data` baseline for that transition.

Each hazard uses only its source-state risk set: open/install hazards admit a
known closed/absent left state, and close/remove hazards admit a known
open/present left state. Positive rows transition to the target state; persistence
rows are negative. The feature vector comes only from the left row. The right row
supplies only the transition label and `action_confidence`. Unknown action states
and same-fold `model_inferred` labels are excluded.

`fit_behavior()` also derives immutable, serializable per-mode action vocabulary
from labeled samples: observed action states, observed transitions, airflow levels,
and confirmed boosted-airflow windows. `ThermalSample.mode` comes from the
reconstructed mode interval; schedule generation must not infer a mode from date.

- [ ] **Step 4: Implement constrained schedule search**

Generate candidate transitions at 15-minute increments within plus/minus two
hours of the learned baseline. Apply these hard filters before simulation:

- Never open warm-season vents until forecast outdoor temperature is at least
  1 F below predicted hallway air and expected to stay lower for 60 minutes.
- Close vents before outdoor temperature becomes equal to predicted hallway air.
- Winter vent state is always closed.
- Cold/cloudy winter daytime indoor shades stay closed.
- Sunny winter daytime shades may open for mass charging and close by sunset.
- Candidate transitions remain within the observed seasonal action vocabulary.

Baseline timing comes from the applicable fitted hazards only when that mode's
vocabulary contains the transition evidence. Otherwise the approved warm-night
vent or winter-shade protocol is an explicit `protocol_fallback` with
`insufficient_data`; it is never presented as learned evidence. Warm, spring, and
fall nightly venting remains mandatory baseline behavior. If every bounded warm
candidate fails the physical filters, retain the learned/protocol baseline under
`baseline` but return an explicit `candidate=None` / `no_valid_candidate` outcome.
Never relabel an unsafe baseline as a candidate.

For sunny winter forecasts, enumerate indoor-shade open/close transitions on the
same 15-minute, plus/minus-two-hour grid, reject nighttime or cold/cloudy openings,
simulate surviving schedules with the Task 4 simulator, and apply the winter
objective. Winter ventilation remains closed in every baseline and candidate.
Outdoor shades remain slow seasonal state and are never a daily search variable.

Airflow segments carry `closed=0`, `baseline=1`, or `boosted=2`. Preserve and
simulate morning/evening boosted segments only when the mode vocabulary contains
observed boosted evidence; never manufacture boosted history from residuals.

Score surviving simulations with transparent seasonal objectives:

```python
warm_score = max(0.0, hallway_peak_f - 82.0) * 4.0 + morning_mass_f
winter_score = hours_below_60f * 4.0 - morning_mass_f
shoulder_score = hallway_discomfort_degree_hours - 0.5 * next_morning_mass_f
```

Return the baseline if no candidate improves the appropriate score by at least
`0.25` while staying within physical and behavioral constraints. Always return
the baseline, candidate, modeled difference, and rejected-candidate counts by
reason.

- [ ] **Step 5: Run behavior and dynamics tests**

Run: `pytest -q openhab/scripts/test_thermal_behavior.py openhab/scripts/test_thermal_dynamics.py`

Expected: all tests pass.

- [ ] **Step 6: Commit the learned behavior slice**

```bash
git add openhab/scripts/thermal_model/behavior.py \
  openhab/scripts/test_thermal_behavior.py
git commit -m "feat: learn thermal action timing in shadow"
```

---

### Task 6: Add atomic artifacts and chronological evaluation

**Files:**
- Create: `openhab/scripts/thermal_model/artifacts.py`
- Create: `openhab/scripts/thermal_model/evaluation.py`
- Create: `openhab/scripts/test_thermal_artifacts.py`
- Create: `openhab/scripts/test_thermal_evaluation.py`

**Interfaces:**
- Consumes: fitted dynamics/behavior models and `ThermalSample` data.
- Produces: `save_candidate()`, `promote_candidate()`, `load_accepted()`, `walk_forward_evaluate()`, and canonical `backtest-report.json`.

- [ ] **Step 1: Write failing atomicity, quarantine, and leakage tests**

```python
def test_artifact_write_is_atomic_and_corruption_is_quarantined(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    registry.save_candidate(valid_artifact())
    registry.promote_candidate()
    assert registry.load_accepted().schema == "earthship-thermal-model/v1"
    registry.accepted_path.write_text("{broken")
    with pytest.raises(ArtifactUnavailable):
        registry.load_accepted()
    assert len(list(tmp_path.glob("accepted.json.corrupt-*"))) == 1


def test_walk_forward_never_trains_on_or_after_prediction_day():
    seen = []
    walk_forward_evaluate(samples_45_days(), fit=lambda train: seen.append(train[-1].at) or fixed_model())
    assert all(train_end < prediction_start for train_end, prediction_start in captured_windows())
```

- [ ] **Step 2: Run artifact/evaluation tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_evaluation.py`

Expected: import failures for both modules.

- [ ] **Step 3: Implement artifact serialization and promotion**

Use state directory `~/.local/state/thermal-intel/models/` with:

```text
candidate.json
accepted.json
backtest-report.json
```

Write to a sibling `.tmp`, flush, `os.fsync()`, then `os.replace()`. Validate
schema, finite coefficients, physical constraints, exact sensor identities,
training range, code revision, and dataset digest before accepting. Promotion
copies the validated candidate through the same atomic-write path; it never
renames an unvalidated file. A corrupt accepted artifact is renamed to
`accepted.json.corrupt-YYYYMMDD-HHMMSS` and produces `ArtifactUnavailable`.

- [ ] **Step 4: Implement chronological backtesting and baselines**

Use a minimum 14-day training window and one-day prediction folds. Report:

- Air and mass MAE/RMSE/bias at 1, 6, 12, 24, 48, and 72 hours where covered.
- Hallway high/low error, peak-time error, and morning mass error.
- Metrics by `warm`, `winter`, and `shoulder` regime and by action provenance.
- Persistence baseline: hold initial air/mass temperatures constant.
- Recent-cycle baseline: median trajectory for the previous seven local days.
- Existing threshold baseline: preserve the exact 90/95 F outdoor-high decision
  logic for classification comparison; do not publish or call it.

The report contains fold boundaries and proves `train_end < prediction_start`
for every fold. Candidate promotion in this phase requires only: valid physics,
finite metrics, at least two folds, and air 24-hour MAE better than persistence.
It remains a shadow artifact regardless of score.

- [ ] **Step 5: Run artifact and evaluation tests**

Run:

```bash
pytest -q openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_evaluation.py \
  openhab/scripts/test_thermal_dynamics.py \
  openhab/scripts/test_thermal_behavior.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit the registry and evidence layer**

```bash
git add openhab/scripts/thermal_model/artifacts.py \
  openhab/scripts/thermal_model/evaluation.py \
  openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_evaluation.py
git commit -m "feat: validate and register thermal model artifacts"
```

---

### Task 7: Orchestrate offline training and shadow prediction

**Files:**
- Create: `openhab/scripts/thermal_model/pipeline.py`
- Create: `openhab/scripts/test_thermal_pipeline.py`
- Modify: `openhab/scripts/thermal_intel.py`

**Interfaces:**
- Consumes: Tasks 2–6 and read-only helpers from `forecast_intel.py`.
- Produces: CLI `train`, `backtest`, and `shadow`; `build_shadow_output()`; no OpenHAB publication yet.

- [ ] **Step 1: Write failing orchestration and fail-soft tests**

Use injected readers, clocks, and forecast snapshots:

```python
def test_shadow_output_is_bounded_versioned_and_never_advisory(tmp_path):
    output = run_shadow(
        registry=accepted_registry(tmp_path),
        current=current_states(),
        forecast=forecast_72h(),
        now=NOW,
    )
    assert output["status"] == "shadow"
    assert output["version"] == 1
    assert len(json.dumps(output).encode()) < 16 * 1024
    assert "commands" not in output
    assert output["forecast"]["hallwayHighF"] is not None


def test_stale_critical_input_emits_unavailable_without_candidate_schedule(tmp_path):
    output = run_shadow(
        registry=accepted_registry(tmp_path),
        current=current_states(air_age_minutes=31),
        forecast=forecast_72h(),
        now=NOW,
    )
    assert output["confidence"]["grade"] == "unavailable"
    assert output["schedule"] == {}
    assert "stale hallway temperature" in output["reasons"]
```

- [ ] **Step 2: Run pipeline tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_pipeline.py`

Expected: import failure for `thermal_model.pipeline`.

- [ ] **Step 3: Implement training orchestration**

`train` performs: exact-site settings load, JDBC reads, journal effective-event
read, sample build, model fits, backtest, candidate save, validation, and shadow
promotion. It writes `backtest-report.json` even when promotion is refused and
exits nonzero with the refusal reasons. Provide injected `series_reader`,
`forecast_reader`, `clock`, and `revision_reader` arguments for tests.

- [ ] **Step 4: Implement bounded shadow output**

`shadow` requires an accepted artifact, critical current readings no older than
20 minutes, and a forecast horizon of at least 24 hours. It may shorten a 72-hour
horizon when later weather is absent but must report `availableHours`. Convert
hourly forecast temperature and radiation into explicit five-minute forcings by
piecewise-linear interpolation between adjacent timestamped rows; hold categorical
cloud state and wind within their source hour. Never extrapolate past the final
forecast timestamp or replace a missing critical field with a constant.

Populate `ShadowOutput` with:

```python
{
  "version": 1,
  "status": "shadow",
  "generatedAt": "ISO-8601",
  "model": {"createdAt": "ISO-8601", "trainedThrough": "ISO-8601", "codeRevision": "sha"},
  "current": {"hallwayF": 74.1, "massF": 72.8, "glazingF": 75.0},
  "forecast": {
    "availableHours": 72,
    "hallwayHighF": 82.4,
    "hallwayHighAt": "ISO-8601",
    "hallwayLowF": 68.2,
    "hallwayLowAt": "ISO-8601",
    "morningMassF": 70.9,
    "intervalLowF": 67.0,
    "intervalHighF": 84.0,
    "trajectory": [
      {
        "at": "ISO-8601", "hallwayF": 74.1, "massF": 72.8,
        "lowF": 73.4, "highF": 74.8, "actions": []
      }
    ],
    "observed": [
      {"at": "ISO-8601", "hallwayF": 74.0, "massF": 72.7}
    ]
  },
  "schedule": {
    "baseline": {"ventOpenAt": "ISO-8601", "ventCloseAt": "ISO-8601"},
    "candidate": {"ventOpenAt": "ISO-8601", "ventCloseAt": "ISO-8601"},
    "effect": {"morningMassDeltaF": -1.7, "hallwayPeakDeltaF": -1.2}
  },
  "confidence": {"grade": "low", "actionLabels": "reconstructed"},
  "provenance": {"sensorItems": THERMAL_ITEMS, "actions": "historical_reconstruction"},
  "reasons": ["outdoor air becomes cooler than hallway at 20:42"]
}
```

Values in the implementation come from simulation; the literal example above
is the exact schema fixture. Emit trajectory points on exact local-hour
boundaries with at most 73 forecast points and 25 recent observed points.
`actions` contains only typed markers (`vent_open`, `vent_close`,
`indoor_shade_open`, `indoor_shade_close`, `outdoor_shade_installed`, or
`outdoor_shade_removed`), never commands. Confidence cannot exceed `low` until
confirmed actions exist in both training and evaluation folds.

- [ ] **Step 5: Add CLI subcommands and offline outputs**

`thermal_intel.py train` and `backtest` accept `--start`, `--end`, and
`--state-dir`; `shadow` accepts `--output PATH` and writes atomically. A plain
`shadow` invocation writes only local state. Do not add `--publish` in this
task.

- [ ] **Step 6: Run all Python tests and offline smoke commands**

Run: `pytest -q openhab/scripts/test_thermal_*.py`

Expected: all thermal tests pass.

Run `python3 openhab/scripts/thermal_intel.py --help`.
Expected subcommands: `journal`, `train`, `backtest`, `shadow`; no actuator or
generic-command subcommand.

- [ ] **Step 7: Commit the offline product**

```bash
git add openhab/scripts/thermal_model/pipeline.py \
  openhab/scripts/test_thermal_pipeline.py \
  openhab/scripts/thermal_intel.py
git commit -m "feat: produce offline thermal shadow forecasts"
```

---

### Task 8: Add a receipt-bound observational OpenHAB output

**Files:**
- Create: `openhab/thermal-model-items.json`
- Create: `scripts/thermal-model-config.mjs`
- Create: `tests/openhab/thermal-model-config.test.js`
- Create: `openhab/scripts/test_thermal_publish.py`
- Modify: `openhab/scripts/thermal_intel.py`

**Interfaces:**
- Consumes: validated `ShadowOutput` from Task 7 and existing OpenHAB token helper.
- Produces: one state-only `Thermal_Model_JSON` String item and CLI publication that can PUT only that item's state.

- [ ] **Step 1: Write failing manifest and allowlist tests**

```js
import { describe, expect, it } from 'vitest';
import manifest from '../../openhab/thermal-model-items.json';
import { buildApplyPlan, buildRollbackPlan, assertThermalOutputRequest } from '../../scripts/thermal-model-config.mjs';

describe('thermal observational resources', () => {
  it('contains one String item and no rule, command, or actuator', () => {
    expect(manifest).toEqual({
      schema: 'earthship-thermal-observations/v1',
      items: [{
        name: 'Thermal_Model_JSON', type: 'String',
        label: 'Thermal model shadow output', category: '', tags: [], groupNames: [],
      }],
    });
    expect(JSON.stringify(manifest)).not.toMatch(/Switch|command|rule|actuator/i);
  });

  it('allows only item creation and state publication', () => {
    expect(() => assertThermalOutputRequest('PUT', '/rest/items/Thermal_Model_JSON/state')).not.toThrow();
    expect(() => assertThermalOutputRequest('POST', '/rest/items/Thermal_Model_JSON')).toThrow(/denied/i);
    expect(() => assertThermalOutputRequest('PUT', '/rest/items/SouthOutlet_Outlet2_Switch/state')).toThrow(/denied/i);
  });
});
```

- [ ] **Step 2: Run config tests and verify RED**

Run: `npm test -- tests/openhab/thermal-model-config.test.js`

Expected: module and manifest imports fail.

- [ ] **Step 3: Implement the observational manifest and transaction planner**

Create exactly the manifest asserted above. `thermal-model-config.mjs` exposes
pure `buildApplyPlan(original)`, `buildRollbackPlan(original)`, and
`assertThermalOutputRequest(method, path)`. Apply plan creates/replaces only
`Thermal_Model_JSON`; rollback restores the captured original item or deletes
the newly created item. The executable commands are `snapshot`, `plan`,
`apply`, `verify`, and `rollback`. `apply` requires a receipt directory
containing the pre-write item snapshot and digest. It never lists or mutates
rules, links, Things, services, metadata, persistence, or any other Item.

- [ ] **Step 4: Add fail-closed publication**

In `thermal_intel.py`, add `shadow --publish`. It first builds and validates the
entire payload, enforces `< 16384` UTF-8 bytes, and then calls only:

```python
oh_put_state("Thermal_Model_JSON", json.dumps(payload, separators=(",", ":")))
```

A PUT failure exits nonzero and leaves the local shadow output/artifact intact.
It never writes `Thermal_Advisory` or retries after an ambiguous response.

- [ ] **Step 5: Test exact publication behavior**

In `test_thermal_publish.py`, inject a recording `put_state` and assert one
call to `Thermal_Model_JSON`, rejection above 16 KiB, no call for invalid or
unavailable output, and propagation of transport ambiguity.

Run:

```bash
npm test -- tests/openhab/thermal-model-config.test.js
pytest -q openhab/scripts/test_thermal_publish.py openhab/scripts/test_thermal_pipeline.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the observational output boundary**

```bash
git add openhab/thermal-model-items.json scripts/thermal-model-config.mjs \
  tests/openhab/thermal-model-config.test.js \
  openhab/scripts/thermal_intel.py openhab/scripts/test_thermal_publish.py
git commit -m "feat: publish bounded thermal shadow output"
```

---

### Task 9: Render the shadow model honestly on the Earthship screen

**Files:**
- Create: `src/lib/thermal/modelResult.js`
- Create: `src/lib/ui/ThermalModelCard.svelte`
- Create: `src/lib/ui/ThermalModelPlot.svelte`
- Create: `tests/thermal-model-result.test.js`
- Create: `tests/ui/ThermalModelCard.test.js`
- Create: `tests/ui/ThermalModelPlot.test.js`
- Modify: `src/screens/Earthship.svelte`
- Modify: `tests/ui/Earthship.test.js`
- Modify: `tests/e2e/weather-earthship-layout.spec.js`

**Interfaces:**
- Consumes: `Thermal_Model_JSON` v1 from Task 8.
- Produces: `parseThermalModelResult(raw, nowMs)` and a non-interactive shadow card.

- [ ] **Step 1: Write failing parser tests**

Test complete, stale, unavailable, invalid, low-confidence, and partial payloads:

```js
import { describe, expect, it } from 'vitest';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';

it('parses a fresh v1 shadow result and preserves zero effects', () => {
  const result = parseThermalModelResult(JSON.stringify(fixture({
    generatedAt: '2026-08-13T12:00:00Z',
    effect: { morningMassDeltaF: 0, hallwayPeakDeltaF: 0 },
  })), Date.parse('2026-08-13T12:10:00Z'));
  expect(result.state).toBe('ready');
  expect(result.badge).toBe('SHADOW');
  expect(result.effect.hallwayPeakDeltaF).toBe(0);
});

it.each(['', 'NULL', 'UNDEF', '{bad', '{"version":2}'])('fails closed for %s', (raw) => {
  expect(parseThermalModelResult(raw, Date.now()).state).toBe('unavailable');
});
```

Freshness is `fresh <= 3h`, `stale > 3h`, and `unavailable > 26h` or invalid.
The parser accepts only version 1 and status `shadow`; it never interprets an
unknown status as advice.

- [ ] **Step 2: Run parser tests and verify RED**

Run: `npm test -- tests/thermal-model-result.test.js`

Expected: module import failure.

- [ ] **Step 3: Implement the pure parser and view model**

Return:

```js
{
  state: 'ready' | 'stale' | 'unavailable',
  badge: 'SHADOW',
  generatedAtMs: number | null,
  hallwayHigh: number | null,
  hallwayLow: number | null,
  morningMass: number | null,
  ventWindow: string | null,
  effect: { morningMassDeltaF: number | null, hallwayPeakDeltaF: number | null },
  confidence: 'low' | 'medium' | 'high' | 'unavailable',
  trajectory: Array<{
    atMs: number, hallwayF: number, massF: number,
    lowF: number | null, highF: number | null, actions: string[],
  }>,
  observed: Array<{ atMs: number, hallwayF: number, massF: number }>,
  reasons: string[],
}
```

Use strict finite-number parsing; do not reuse `parseFloat` for structured JSON.
Format times in the browser's configured local timezone. Missing schedule data
renders as absent, never as `0:00`.

- [ ] **Step 4: Write and implement the component tests**

`ThermalModelCard.svelte` renders:

- `SHADOW` badge always.
- Next hallway high/low and morning mass.
- Candidate vent window when present.
- Modeled peak/mass deltas labeled `modeled`, not `saved` or `will`.
- Confidence and stale/model-age text.
- An unavailable state with no recommendation copy.
- A native `<details>` disclosure labeled `Model details` containing the plot.

`ThermalModelPlot.svelte` draws observed hallway/mass temperatures, forecast
hallway/mass temperatures, the forecast interval, and typed action markers from
the bounded hourly arrays. It must use accessible SVG labels and preserve gaps;
it must not invent points or connect across missing data. Assert that the card
and plot have no actuator button, command target, automation language, or event
handler outside the disclosure itself. Add them to `Earthship.svelte` without
changing the existing Thermal Advisory card or its alert interpretation.

- [ ] **Step 5: Extend exact viewport tests**

Add a valid `Thermal_Model_JSON` fixture to
`tests/e2e/weather-earthship-layout.spec.js`. At 1340x800 and 1280x720 assert
the model card, all existing cards, and navigation remain fully within the
viewport with no document/card scroll. Keep the existing physical zone order.

Run:

```bash
npm test -- tests/thermal-model-result.test.js tests/ui/ThermalModelCard.test.js \
  tests/ui/ThermalModelPlot.test.js tests/ui/Earthship.test.js
npx playwright test tests/e2e/weather-earthship-layout.spec.js
```

Expected: all selected unit and viewport tests pass.

- [ ] **Step 6: Commit the shadow UI**

```bash
git add src/lib/thermal/modelResult.js src/lib/ui/ThermalModelCard.svelte \
  src/lib/ui/ThermalModelPlot.svelte src/screens/Earthship.svelte \
  tests/thermal-model-result.test.js tests/ui/ThermalModelCard.test.js \
  tests/ui/ThermalModelPlot.test.js tests/ui/Earthship.test.js \
  tests/e2e/weather-earthship-layout.spec.js
git commit -m "feat: show thermal model shadow forecast"
```

---

### Task 10: Add user services, deploy safely, and open the shadow evidence window

**Files:**
- Create: `deploy/thermal-model-train.service`
- Create: `deploy/thermal-model-train.timer`
- Create: `deploy/thermal-model-shadow.service`
- Create: `deploy/thermal-model-shadow.timer`
- Modify: `tests/deployment-service.test.js`
- Modify: `README.md`
- Create: `docs/operations/thermal-model-shadow.md`

**Interfaces:**
- Consumes: accepted artifacts, shadow CLI, observational Item, and UI from Tasks 1–9.
- Produces: reviewed user-level timers and a reproducible shadow-evidence runbook.

- [ ] **Step 1: Write failing service-contract tests**

Extend `tests/deployment-service.test.js` to assert:

```js
const train = readFileSync('deploy/thermal-model-train.service', 'utf8');
const shadow = readFileSync('deploy/thermal-model-shadow.service', 'utf8');
expect(train).toMatch(/^ExecStart=\/usr\/bin\/python3 \/home\/sat\/openhab\/scripts\/thermal_intel.py train$/m);
expect(shadow).toMatch(/^ExecStart=\/usr\/bin\/python3 \/home\/sat\/openhab\/scripts\/thermal_intel.py shadow --publish$/m);
expect(train + shadow).not.toMatch(/Thermal_Advisory|sendCommand|\/rest\/rules/i);
```

Timer contracts:

- Train daily at `06:50` after the existing `06:40` forecast job.
- Shadow first runs 15 minutes after boot, then every two hours.
- Both are persistent user timers with bounded service timeouts.

- [ ] **Step 2: Run service tests and verify RED**

Run: `npm test -- tests/deployment-service.test.js`

Expected: failure because the four unit files do not exist.

- [ ] **Step 3: Add exact user units and operations runbook**

Services use `/usr/bin/python3` because current host verification found NumPy
1.26.4 and SciPy 1.11.4 in that interpreter. Set `Type=oneshot`,
`WorkingDirectory=/home/sat/openhab/scripts`,
`EnvironmentFile=/home/sat/.config/hex/openhab.env`, and
`TimeoutStartSec=900` for training / `180` for shadow prediction.

The runbook contains:

1. Exact tracked-to-live file manifest and SHA-256 verification.
2. Read-only current Item/persistence inventory.
3. Observational Item snapshot, apply-plan review, rollback rehearsal, apply,
   verify, and receipt closure.
4. Manual one-shot `train`, `backtest`, and local-only `shadow` commands.
5. Review of model parameters, data exclusions, folds, and baseline metrics.
6. Manual `shadow --publish`, exact Item readback, UI observation, and log check.
7. Timer installation/enable commands only after steps 1–6 are green.
8. Rollback: disable timers first, restore/remove the observational Item from
   its receipt, retain journal/artifacts as evidence, and restore prior tracked
   scripts.

State explicitly that implementation completion does not graduate advice.

- [ ] **Step 4: Run complete repository verification before live work**

Run:

```bash
pytest -q openhab/scripts/test_forecast_intel.py openhab/scripts/test_thermal_*.py
npm test
npm run build
npx playwright test
git diff --check
```

Expected: zero failures; production build exits 0; no whitespace errors.

- [ ] **Step 5: Obtain operator approval and execute the attended deployment**

Stop before any OpenHAB Item write, live script copy, service installation, or
timer enable. Present the snapshot, dry-run apply plan, rollback receipt, test
totals, artifact metrics, and exact commands. After explicit approval, follow
`docs/operations/thermal-model-shadow.md` exactly.

Acceptance evidence:

- Tracked/live hashes match.
- `Thermal_Model_JSON` is the only new/changed OpenHAB resource.
- Payload reads back as valid v1 `shadow`, below 16 KiB.
- Existing `Thermal_Advisory` value and behavior remain unchanged.
- No protected actuator Item state changes during the attended window.
- Both services exit 0 and timers show the intended next run.
- Earthship UI renders current, stale, and unavailable states honestly.
- Backtest report and accepted artifact identify exact code/data ranges.

- [ ] **Step 6: Commit deployment artifacts and evidence pointers**

```bash
git add deploy/thermal-model-train.service deploy/thermal-model-train.timer \
  deploy/thermal-model-shadow.service deploy/thermal-model-shadow.timer \
  tests/deployment-service.test.js README.md docs/operations/thermal-model-shadow.md
git commit -m "chore: stage thermal shadow services and runbook"
```

Do not commit private receipts, tokens, raw household histories, journal state,
or learned artifacts.

---

## Follow-on Plans Required After the Shadow Foundation

These are not tasks in this plan:

1. **Nostr action collection:** authenticated paired-operator reply ingestion,
   replay protection, bounded prompt windows, and exact journal receipts.
2. **Photosensor shade observation:** hardware inventory, placement/calibration,
   indoor/outdoor light-ratio classifier, and uncertainty handling.
3. **Warm-season advisory graduation:** evidence-derived numeric gates, operator
   review, compatibility with existing alert consumers, and reversible cutover.
4. **Winter graduation:** a full cold-season holdout and explicit review after
   sufficient winter evidence exists.
5. **Actuator automation:** independent threat model, capability boundary,
   manual override, state reconciliation, fail-safe behavior, and operator arm.
6. **In-house household model:** hardware/license selection, curated training
   manifest, parameter-efficient adaptation, structured proposal schema, and
   offline/shadow comparison against the explicit behavior model. It remains
   upstream of RC simulation and deterministic authority validation.

## Implementation Completion Gate

This document completes Hexmem Task 17's approved design-and-planning boundary
once it is reviewed and committed; implementation has not started. The future
implementation project is complete only when Tasks 1–10 have independent green
commits, full repository verification passes, the attended shadow deployment
receipt is closed, and the system has begun collecting shadow evidence without
changing advice or actuation. Model graduation remains separate.
