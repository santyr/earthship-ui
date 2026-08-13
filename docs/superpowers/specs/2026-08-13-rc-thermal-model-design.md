# Earthship RC Thermal Model and Learned Thermal Policy

**Date:** 2026-08-13
**Status:** Approved in conversation; implementation not started
**Hexmem task:** 17, `RC thermal model of the Earthship mass (design pass)`

## Purpose

Build an inspectable, continuously learning thermal model for the Earthship.
The system should formalize the seasonal reasoning the household already uses,
predict room comfort and thermal-mass behavior, and learn the timing of manual
vent and shade actions. Its long-term output is a safe input to a separately
designed automation system, not a reminder system for humans.

The first implementation is observational and advisory only. It has no actuator
commands, control RPCs, or authority over vents, shades, or the Kiva fireplace.

## Operator context and established practice

The household's current manual thermal policy is:

- Spring, summer, and fall: vent every night, close indoor shades during sunny
  days, and open indoor shades at night.
- Winter: do not vent, leave indoor shades open during the day for passive solar
  gain, and close them at night. On cloudy cold days indoor shades remain closed
  to retain heat.
- During fall transition, remove outdoor shades and increasingly leave indoor
  shades open to charge the thermal mass ahead of winter.
- Winter heating is effectively passive solar plus ordinary internal gains.
  The Kiva fireplace is used only during very cold, cloudy conditions.

Warm-season venting is therefore a baseline behavior, not a yes/no decision.
Useful advice concerns when to open, when to close, how long the useful window
lasts, and the predicted effect on morning mass temperature and the next day's
hallway peak.

The initial warm-season elevated-comfort-risk reference is a predicted hallway
peak of 82 F. The initial winter shadow reference is 60 F, but indoor lows in
the 50s during the darkest and coldest part of winter are not automatically a
model or policy failure. Both references are reporting and evaluation anchors,
not universal comfort claims.

## Existing data and system boundary

OpenHAB JDBC already persists the required physical signals. The exact initial
sensor roles are:

| Role | OpenHAB item | Use |
| --- | --- | --- |
| Primary comfort state | `AmbientWeatherWS2902A_IndoorSensor_Temperature` | Hallway/room-air state and principal forecast target |
| Thermal-mass state | `AmbientWeatherWS2902A_WH31E_193_Temperature` | North-wall mass state |
| Solar-zone observation | `Shelly_HT1_Indoor_Temperature` | South-glazing response and auxiliary validation |
| Outdoor forcing | `AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature` | Envelope and ventilation heat exchange |
| Solar forcing | `AmbientWeatherWS2902A_SolarRadiation` | Measured incident solar radiation |

Forecast forcing comes from the existing Open-Meteo pipeline, including
temperature, solar radiation, cloud/weather state, and wind. The current
tracked and deployed `forecast_intel.py` copies were byte-identical during the
design pass.

Inverter, transformer, cabinet, and battery temperatures are excluded from the
initial model. They are self-heated equipment measurements, not representative
room zones. They may be reconsidered only if future evidence establishes a
useful and stable relationship to an occupied or envelope zone.

The design starts with the data currently available. It must remain valid as
additional seasons and optional sensors are added.

## Architecture

The system has two deliberately separate learning problems:

1. A constrained two-state thermal dynamics model predicts what the building
   will do under weather and action inputs.
2. A behavior model predicts what vent and shade actions the household is
   likely to take and when.

This separation prevents a correlation such as "shades are closed on hot sunny
days" from being misread as a physical claim that shade closure causes heat.
It also allows the system to compare the learned baseline schedule with nearby
candidate schedules without conflating behavior and building physics.

### 2R2C thermal core

The physical core has two latent/measured states:

- `T_air`: hallway room-air temperature, the primary comfort target.
- `T_mass`: north-wall thermal-mass temperature.

The effective model is a discretized, constrained 2R2C state-space system. It
learns effective conductances/capacitances or their equivalent discrete-time
coefficients; it does not claim separately measured construction R and C
values without heat-flow instrumentation.

Conceptually:

```text
C_air  dT_air/dt  = (T_out - T_air) / R_out
                   + (T_mass - T_air) / R_mass
                   + solar_gain
                   + ventilation_gain
                   + internal_gain
                   + exceptional_heat

C_mass dT_mass/dt = (T_air - T_mass) / R_mass
                   + absorbed_solar_gain
```

Inputs and modifiers are:

- Outdoor temperature.
- Measured or forecast solar radiation.
- Cloud/sunny state and solar position where useful.
- Effective ventilation level, normalized to closed `0.0`, baseline open
  `1.0`, or door-assisted boosted `2.0`. Values outside `[0.0, 2.0]` are
  invalid rather than extrapolated beyond the operator-approved envelope.
- Indoor- and outdoor-shade state, which changes transmitted solar gain.
- Wind, which may modify ventilation effectiveness when vents are open.
- Kiva state, represented only as an exceptional exogenous heat episode.
- A bounded residual/internal-gain term for ordinary occupancy and appliance
  heat that is not separately instrumented.

All fitted coefficients have physically plausible sign and magnitude bounds.
For each supported ventilation level, the discrete two-state transition matrix
must have spectral radius below `1 - 1e-9`; neutral and unstable modes are
rejected before a separate 72-hour finite/range simulation. A candidate fit
with implausible dynamics, unstable free response, or worse held-out
performance than the accepted baselines is rejected.

Each explicit forcing row represents the end of its five-minute interval.
Training pairs use the left row for the starting air/mass state and the right
row for end forcing, action confidence, and targets. Prediction and simulation
result rows therefore contain end-of-step air, mass, and optional glazing.

### South-glazing auxiliary observation

The south-glazing temperature does not add a third physical state to the first
model. A small observation equation predicts it from co-temporal end-of-step
room air, outdoor air, radiation, solar position, and shade state. It is never
recursive. This signal provides:

- Direct evidence of solar-zone response.
- A validation target for transmitted-gain behavior.
- Additional information for shade-state inference.

Keeping it as an auxiliary observation preserves a comprehensible two-state
core while using the other relevant indoor temperature sensor.

### Learned behavior model

A separate model estimates the probability and timing of these transitions:

- Vent open and vent closed.
- Indoor shades open and indoor shades closed.
- Outdoor shades installed and outdoor shades removed.

Features may include season/day of year, local time, sunrise/sunset and solar
position, measured and forecast outdoor temperature, hallway/mass/glazing
temperatures, radiation, cloud state, wind, recent action state, and multi-day
thermal trajectory.

The behavior model initially learns household practice. It does not independently
invent action types or emit actuator commands. Its output is a shadow action
schedule with probability, confidence, and the observations that most strongly
support it.

## Thermal-action journal

Routine action data must not be stored as raw Hexmem memories. Store it in
append-only PostgreSQL tables in a dedicated `thermal_intel` schema in the
existing local OpenHAB `openhab` database. OpenHAB JDBC remains authoritative
for sensor measurements; the journal is application-owned and must not modify
or couple to OpenHAB-generated persistence tables.

The runtime uses a dedicated least-privilege role and an environment-supplied
`THERMAL_DATABASE_URL` DSN. Credentials are never hardcoded or printed. The
journal schema provides transactional message batches, unique receipt keys,
correction/supersession foreign keys, `TIMESTAMPTZ` timestamps, and
append-only privileges and guards. Development tests use an ephemeral
PostgreSQL 16 instance/schema and never write the production database.

OpenHAB Item time-series persistence alone cannot enforce atomic multi-event
message batches, idempotency keyed by receipt/payload, or relational
correction/supersession links, so it remains the sensor-history authority while
this application-owned journal supplies those semantics within the same
PostgreSQL storage and backup ecosystem.

Each journal record contains:

- Event ID and idempotency key.
- Received timestamp and effective timestamp as `TIMESTAMPTZ`.
- Action type: `vent`, `indoor_shade`, `outdoor_shade`, or `kiva`.
- State or transition.
- Optional interval linkage between start and stop records.
- Source: `nostr_confirmed`, `manual_dm`, `photosensor`,
  `historical_reconstruction`, or `model_inferred`.
- Confidence and optional operator note.
- Supersession/correction foreign key; original records are never destroyed.

Confirmed operator records outrank photosensor observations, which outrank
historical reconstruction and model inference. Missing confirmation produces
an `unknown` interval, never a fabricated action.

### Operator DM template

The compact input format is:

```text
THERMAL
effective: now
mode: fall-charge
outdoor_shades: removed
indoor_shades: open-day
vent: 20:30-07:00
kiva: off
note: charging mass ahead of winter
```

Unchanged fields may be omitted. The parser must reject ambiguous or invalid
values, write through one narrow journal-ingestion command, read the stored
record back, and return an exact receipt to the operator. Corrections append a
superseding record rather than editing history in place.

### Temporary Nostr instrumentation

Nostr questions are temporary measurement prompts, not reminders that teach
the household what to do.

During warm seasons, the data collector may ask for:

- An evening confirmation that venting started and indoor shades opened.
- A morning confirmation that venting stopped and indoor shades closed.

Replies accept compact states such as `yes`, `not yet`, `skip`, or an explicit
time such as `yes 21:30`. The reply timestamp is the default effective time;
an explicit time overrides it after timezone-safe validation.

On very cold, cloudy days, Hex may ask whether the Kiva was lit and for its
approximate start and stop times. Confirmed Kiva intervals are excluded from
passive-only fitting unless a later model explicitly estimates their heat
input.

The existing Nostr notification path is outbound-only. Implementation therefore
requires a separate, narrowly scoped inbound reply collector with sender
authentication, event replay/idempotency protection, bounded accepted syntax,
and journal readback. It must not expose general command execution.

### Historical reconstruction

The initial warm-season dataset may reconstruct action state from the approved
household protocol:

- Nighttime during the warm-season regime: vent open, indoor shades open.
- Sunny/hot daytime: indoor shades closed.
- Outdoor shades present until a confirmed seasonal removal transition.

Reconstructed labels carry lower confidence than confirmed records. They are
used for initial identification and sensitivity analysis, not represented as
ground truth. Fits must report how results change when reconstructed action
labels are excluded.

## Optional indoor photosensors

The design supports future indoor illuminance sensors without requiring them.
For each independently operated shade bank, one suitably placed sensor can
estimate shade state from the relationship between indoor illuminance and the
existing outdoor radiation signal.

The classifier uses the indoor-light/outdoor-radiation ratio together with
solar elevation, cloud state, and south-glazing temperature. Abrupt ratio
drops support a closing transition and abrupt rises support an opening
transition. A small set of operator-confirmed events bootstraps labels.

The observation output is probabilistic: `open`, `closed`, or `uncertain`, with
confidence. Artificial-light contamination, sensor saturation, darkness, and
rapid cloud transients produce `uncertain` rather than a forced state. The
thermal model continues to operate without photosensors.

## Training pipeline

A daily training job performs these stages:

1. Read required JDBC histories and action-journal records.
2. Normalize timestamps to the configured OpenHAB site timezone and align data
   to a five-minute timeline without interpolating across large gaps.
3. Apply per-sensor freshness, range, jump, and coverage checks.
4. Join confirmed, reconstructed, photosensor, and inferred action intervals
   while preserving source and confidence.
5. Exclude or separately flag Kiva intervals and other unexplained exceptional
   heat episodes during passive-only fitting.
6. Fit constrained thermal dynamics on the training window.
7. Fit the behavior model only on sufficiently labeled transitions.
8. Perform chronological walk-forward validation so future samples cannot leak
   into training.
9. Compare the candidate with the accepted model and simple baselines.
10. Atomically publish a versioned artifact only if every acceptance gate passes.

The raw JDBC history and append-only journal are authoritative. Derived joined
datasets and model artifacts are reproducible and may be regenerated.

Each model artifact records:

- Schema and model versions.
- Training and validation time ranges.
- Exact OpenHAB item identities and units.
- Action-label counts by source and confidence.
- Fitted parameters and constraints.
- Evaluation metrics by season, horizon, and operating regime.
- Baseline comparisons.
- Artifact creation time and code revision.
- Rejection or acceptance decision.

## Forecasting and candidate schedule search

The daily forecast job initializes `T_air` and `T_mass` from the latest valid
hallway and north-wall readings. It simulates measured-to-forecast weather over
the next 48 to 72 hours.

The behavior model supplies the schedule the household would probably choose.
The scheduler then evaluates nearby, bounded alternatives that remain within
confirmed household practice:

- Vent opening near the time outdoor air becomes usefully cooler than room air.
- Morning vent closing before outdoor air becomes counterproductive.
- Indoor-shade transitions based on useful solar gain, outdoor heat, season,
  and mass-charging needs.
- Outdoor-shade installation/removal as a slow seasonal configuration, not a
  daily optimization variable.

The search reports the expected difference between the learned baseline and a
candidate schedule. It must not call that difference causal certainty. The
claim is a model counterfactual with an uncertainty interval and data-quality
grade.

Seasonal objectives are:

- **Warm season:** reduce hallway peak exposure above 82 F, cool the mass, and
  avoid admitting warmer outdoor air. Venting is assumed to occur; timing and
  duration are optimized.
- **Winter shadow:** preserve hallway warmth, charge the mass from useful solar
  gain, and report duration below the initial 60 F reference. Winter output
  remains shadow-only until cold-season validation is sufficient.
- **Shoulder seasons:** trade off next-day comfort risk and multi-day mass
  charging rather than optimizing a single day's extreme.

Kiva use is never automatically recommended in the first version.

## Outputs and UI

Every prediction includes:

- Forecast hallway and mass traces with uncertainty bands.
- Predicted hallway high/low and their times.
- Predicted morning mass temperature.
- Learned baseline action schedule.
- Candidate schedule, if meaningfully different.
- Predicted effect relative to baseline.
- Confidence/data-quality grade.
- Model version, training-data end time, and action provenance.
- `shadow` or `advisory` status.

Example warm-season output:

> Open vents at 20:42 and close at 07:06. Outdoor air should remain useful for
> 10 h 24 m. Model effect versus the learned baseline: morning mass 1.7 F
> cooler and next-day hallway peak 1.2 F lower. Medium confidence; last night's
> action was operator-confirmed.

The Earthship screen gains a compact thermal-model card containing current
mass state, next hallway high/low, action window, modeled benefit, confidence,
model age, and shadow/advisory badge. A detail view plots predicted versus
measured hallway and mass temperatures with action markers and uncertainty.

Existing alerts and `Thermal_Advisory` behavior remain unchanged while the new
model is shadow-only. A model output can replace the generic warm-season
`vent_tonight` text only after its graduation gate passes. The rollout must not
silently change alert codes or consumers.

## Evaluation and graduation

Evaluation is chronological and regime-aware. At minimum, score:

- Hallway and mass MAE, RMSE, and signed bias by forecast horizon.
- Hallway daily high/low error and peak-time error.
- Mass morning-temperature error.
- Prediction-interval empirical coverage.
- Action-transition precision/recall and median timing error.
- Metrics split by warm, winter, and shoulder regimes; vent/shade states;
  sunny/cloudy conditions; and confirmed versus reconstructed labels.
- Counterfactual calibration on comparable confirmed nights where the observed
  schedule differs sufficiently from the model baseline.

Baselines include:

- Persistence/current-temperature forecast.
- Seasonal or recent-hour average trajectory.
- The existing fixed outdoor-high threshold advisory.

Graduation is deliberately staged:

1. Fit and review the reconstructed-history baseline.
2. Run all temperature and action predictions in shadow.
3. Accumulate confirmed warm-season action transitions and outcome scores.
4. Permit warm-season timing advice only when the accepted model consistently
   beats the baselines on held-out data, has no material seasonal/regime bias,
   has calibrated uncertainty, and passes operator review of example advice.
5. Continue year-round learning.
6. Keep winter recommendations shadow-only through sufficient cold-season data
   and an explicit later graduation review.

No metric threshold is invented before the first backtest establishes realistic
error distributions. The implementation plan must define a baseline report and
then turn its evidence into exact numerical graduation thresholds before any
advisory cutover.

## Failure behavior

- Missing or stale critical state: retain the last accepted artifact but emit
  no new model-based advice.
- Incomplete forecast forcing: shorten the prediction horizon or remain
  unavailable; do not fill critical inputs with silent constants.
- Missing action label: dynamics may run with wider uncertainty, while behavior
  training skips the unlabeled transition.
- Photosensor ambiguity: record `uncertain`, never force `open` or `closed`.
- Kiva ambiguity or unexplained winter heat pulse: exclude the affected interval
  from passive fitting and report the exclusion.
- Implausible or unstable candidate coefficients: reject the artifact.
- Candidate regression against baselines or accepted model: retain the prior
  accepted artifact.
- Nostr send/receive outage: do not create an action record; retry only within
  a bounded collection window and then mark the interval unknown.
- Journal parse or write failure: return no success receipt and leave prior
  records intact.
- Model artifact corruption: quarantine it, fall back to the prior verified
  artifact if available, and remain shadow/unavailable rather than using
  defaults as accepted predictions.

## Security and authority boundary

- Nostr inbound handling accepts only the authenticated paired operator and a
  closed thermal-message grammar.
- The collector exposes no shell, OpenHAB command, generic RPC, or actuator
  path.
- Training and forecast services read sensor history and the action journal;
  they write only their own state/artifacts and explicitly allowed prediction
  Items.
- Every future actuation project requires a separate design, threat review,
  fail-safe state model, manual override, capability boundary, and operator
  approval. A high-confidence prediction does not itself authorize action.

## Future in-house household model

The histories produced by this project should also support a future small,
locally hosted household model, such as a suitable Gemma-family checkpoint.
The durable interface is model-agnostic so a particular model name, size, or
runtime can be replaced without changing the thermal or control contracts.
Initial planning assumes parameter-efficient adaptation or supervised fine-tuning
of an existing small open-weight model, not training a foundation model from
scratch. Checkpoint selection happens later against actual household hardware,
privacy, licensing, latency, and evaluation requirements.

The future model may:

- Learn and explain seasonal household strategy from curated sensor, action,
  forecast, and outcome histories.
- Predict likely human vent and shade transitions as an additional behavior
  model candidate.
- Propose a typed schedule containing action, target, proposed time, confidence,
  reasons, and the evidence window used.
- Answer household questions and summarize why the physical model expects a
  particular thermal outcome.

It must not:

- Replace the constrained RC model as the numerical source of thermal-state
  forecasts or counterfactual effects.
- Train directly on uncurated raw messages, credentials, private keys, or other
  unrelated household data.
- Produce free-form tool calls or actuator commands.
- Bypass deterministic state validation, weather/sensor freshness checks,
  physical limits, seasonal policy constraints, manual overrides, or the
  separately authorized control owner.
- Treat a plausible natural-language explanation as proof that an action is
  safe.

Training examples are derived reproducibly from the authoritative JDBC history,
thermal-action journal, forecasts, RC-model outputs, and measured outcomes.
Every example retains timestamps, provenance, confidence, and whether the action
was confirmed, reconstructed, inferred, or merely proposed. Training,
validation, and evaluation splits are chronological and include complete
seasonal holdouts. A model artifact records its base-model identity, license,
data-manifest digest, training code revision, evaluation results, and resource
requirements.

Initial evaluation is offline and shadow-only. It must compare against the
explicit behavior model and simple seasonal rules, including transition timing,
calibration, abstention on unfamiliar conditions, explanation faithfulness, and
structured-output validity. The model is useful only if it adds measurable
value beyond those smaller deterministic/statistical components.

Any later use in automation follows a proposal/validation/execution split:

```text
local model proposal
        -> schema validation
        -> RC counterfactual simulation
        -> deterministic safety and authority owner
        -> optional actuator command
```

The final step is outside this project and remains impossible until a separate
automation design grants narrow authority and proves fail-safe behavior.

## Testing strategy

The implementation plan must cover:

- Unit tests for time alignment, DST transitions, interval reconstruction,
  provenance precedence, correction history, and DM parsing.
- Synthetic-system identification tests with known 2R2C parameters, bounded
  noise, missing data, and action-state changes.
- Sign/constraint and unstable-model rejection tests.
- Walk-forward split and no-future-leakage tests.
- Behavior-model tests for seasonal transitions, unknown labels, and confidence.
- Photosensor classifier tests for clouds, artificial light, darkness, and
  saturation.
- Nostr authentication, replay, idempotency, invalid syntax, and exact receipt
  tests without live outbound messages.
- Golden backtest reports comparing candidate and baseline metrics.
- Forecast failure tests for stale sensors, partial weather, corrupt artifacts,
  journal failure, and unknown Kiva intervals.
- UI unit and exact target-viewport tests for shadow, advisory, stale,
  unavailable, and low-confidence states.
- Deployment verification that the tracked and live scripts/artifacts match,
  existing forecasts remain healthy, and no actuator surface was added.

## Explicitly deferred

- Any automatic vent, indoor-shade, or outdoor-shade actuation.
- Automated Kiva recommendations or control.
- Adding more thermal states without evidence that 2R2C is inadequate.
- Treating reconstructed actions as confirmed truth.
- Bandit/Thompson tuning of action thresholds before outcome measurement and
  model validation exist.
- Winter advisory graduation before a later cold-season evidence review.
- Training, deploying, or granting tool access to an in-house language model;
  this specification only preserves the future data and interface boundary.

## Completion boundary for Task 17

Task 17's design pass is complete when this specification is approved and a
separate implementation plan has been written. Implementation, shadow
operation, data collection, model graduation, and future automation are
subsequent work and require their own verification evidence.
