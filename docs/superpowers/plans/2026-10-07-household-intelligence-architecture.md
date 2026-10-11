# Earthship household intelligence architecture plan

**Date:** 2026-10-07  
**Repository:** `santyr/earthship-ui`  
**Status:** planning only; no actuator or production-authority change  
**Depends on:** completion of PR #2 forecast-ML hardening / thermal identifiability work  
**WeatherNext:** may be integrated later as a weather-forcing source, but this plan does not require or unblock WeatherNext deployment.

## 1. Goal

Evolve the Earthship project from a collection of strong domain-specific sensing,
forecasting, qualification, and OpenHAB automation paths into a coherent household
intelligence architecture with:

1. one immutable, time-consistent household state snapshot;
2. one shared evidence/provenance vocabulary across energy, thermal, weather, water,
   and actuator outcomes;
3. pure domain models that consume the same frozen state rather than independently
   rereading mutable live state;
4. a shadow-only household planner that reasons over predicted trajectories;
5. explicit hard safety/authority constraints separated from optimization objectives;
6. typed household intents and a central conflict arbiter;
7. OpenHAB owner rules remaining the final deterministic execution/safety authority;
8. deterministic replay and chronological outcome scoring before any planner-generated
   intent is allowed to influence physical equipment;
9. one machine-readable OpenHAB capability registry and a common correlated
   request/result protocol so UI, schedules and a future planner share the same
   owner-rule safety path.

The architectural target is:

```text
qualified evidence
        ↓
canonical HouseholdSnapshot
        ↓
domain digital twins / predictors
  energy   thermal   water   weather
        ↓
predicted household trajectories
        ↓
constrained household planner
        ↓
typed intents
        ↓
household arbiter
        ↓
existing OpenHAB owner rules
        ↓
hardware / provider integrations
        ↓
outcome evidence
        └──────────────→ replay / qualification
```

The planner is not a replacement for OpenHAB, hardware protection, or deterministic
owner rules. Models may become more intelligent without automatically becoming more
authoritative.

---

## 2. Why this architectural change is timely

The repository is no longer only a UI. It now contains or coordinates:

- immutable / source-bound weather observations;
- BMS and PV evidence;
- SoC trough forecasts and scoring;
- daily and hourly temperature learning;
- thermal identification, artifacts, evaluation and shadow publication;
- action / shade / ventilation history;
- advisory outcome capture;
- qualified OpenHAB request/result control paths;
- operational qualification and rollback tooling;
- local home-automation engineering-agent procedures.

These subsystems are individually careful, but many still construct their own view of
household state from mutable Items, persisted rows, files, or receipts. That is correct
for their current isolated roles, but it becomes a source of ambiguity once one
decision layer must combine energy, thermal, water, weather, and actuator constraints.

The next architectural problem is therefore not "add a larger ML model." It is:

> make the household state, evidence, predictions, decisions, authority and outcomes
> explicit and replayable across domains.

---

## 3. Math-informed design principles

The recent OpenAI math results motivate architectural principles, not direct theorem
transplants. No theorem below should be claimed to model the real Earthship exactly.

### 3.1 Safety / viability before optimization — result family #104

The mean-payoff / stochastic / parity-game results reinforce separating:

```text
hard invariants
    from
long-run optimization objectives
```

For the Earthship, constraints such as emergency battery reserve, stale evidence,
device ownership, pump cooldowns, actuator conflicts, hardware protection and water
reserve must define the feasible action set. They must not become weighted penalties
that can be traded away for comfort or efficiency.

Architectural rule:

```text
safe_actions = actions satisfying every hard constraint
best_action   = optimizer(safe_actions, predicted value)
```

The project should use a practical constrained optimizer / rolling-horizon planner,
not attempt to deploy the theoretical game solver.

### 3.2 Online constrained action selection — result family #111

Household actions arrive over time and compete for limited resources:

- greywater circulation;
- future pump / well work;
- shade movement;
- ventilation;
- optional flexible loads;
- surplus-solar use;
- future storage or thermal interventions.

The prophet/matroid result motivates representing compatibility constraints explicitly
instead of allowing independent rules to race. In practice this should become a small
deterministic constrained optimization problem, not a direct prophet implementation.

### 3.3 Evidence count is not independent information — result family #140

The memory/sample lower-bound work reinforces the project's current evidence-hardening
direction:

- dense five-minute rows are not independent experiments;
- compact learned state is not a substitute for authoritative observations;
- repeated overlapping windows must not inflate confidence.

The canonical snapshot and models must preserve references to underlying qualified
evidence. State caches and model summaries remain derived products.

### 3.4 Scheduling drift / transient excursions — result family #097

Represent optional actions by their predicted resource-effect vectors and measure
cumulative drift across energy, thermal, water and equipment-wear dimensions.

This result is useful as inspiration for offline scheduling/oracle comparisons; it
does not supply the live controller.

### 3.5 Viability region / homeostasis — result family #149

Do not claim the household is a mass-action reaction network. Borrow only the useful
architectural concept:

```text
viability region = states the household should remain within
```

Examples include battery reserve, acceptable temperature ranges, minimum usable water,
fresh-enough sensing and hardware-safe operating states.

---

## 4. Non-negotiable authority boundaries

### 4.1 Hardware protection remains authoritative

Battery BMS protection, inverter/charger protection, pump/device protection and other
hardware-native limits remain outside planner authority.

### 4.2 OpenHAB remains the live automation/execution authority

OpenHAB continues to own:

- physical integrations;
- deterministic automation;
- owner rules;
- request validation;
- cooldowns;
- command execution;
- existing fail-safe behavior.

### 4.3 The planner emits requests/intents, never provider commands

Protected automation must follow the established request/result pattern.

The planner must never directly command:

- physical switch Items;
- pump outlets;
- shades;
- inverter/charger settings;
- other provider Items.

### 4.4 The UI remains presentation plus existing bounded requests

The browser must not become the decision authority.

### 4.5 Missing/stale/invalid evidence fails closed

For a decision-critical input:

```text
missing != zero
stale != current
unknown != safe
```

A planner may degrade to "no recommendation" or a deterministic existing rule, but may
not synthesize evidence.

### 4.6 No automatic actuator expansion in the initial program

Initial implementation is shadow-only. Existing live OpenHAB automations continue
unchanged.

### 4.7 OpenHAB Item roles are explicit

Treat OpenHAB Items as belonging to explicit architectural roles:

```text
1. physical/provider state
2. qualified evidence
3. forecast/model output
4. intent/request ingress
5. owner result / execution evidence
6. protected actuator
```

A planner may consume roles 1–3, may eventually write only through an explicitly
qualified role-4 request contract, observes role 5, and never writes role 6.

Authority must not be inferred from Item names, semantic tags, group membership or
UI visibility. Use the versioned capability/ownership contract instead.

### 4.8 A snapshot explains a request; live owner checks authorize it

A future planner request may reference the `HouseholdSnapshot` and planner intent
that produced it. That reference is provenance, not authorization.

Every owner rule must independently reread decision-critical current state immediately
before execution. Examples include current BMS communications, SoC, voltage, device
availability, cooldowns, lockouts and busy state.

```text
snapshot = rationale / replay identity
live owner state = execution authority
```

---

# PHASE 0 — Finish the current ML foundation

**Dependency:** complete the in-flight forecast-ML hardening and thermal graduation
work before beginning behavioral planner work.

Required outcomes:

- independent-day/non-overlap evidence utilities are merged;
- thermal identifiability / stability guards are merged;
- current forecast equations are still behaviorally unchanged unless separately
  qualified;
- thermal forecast/advisory graduation contracts are explicit;
- full CI and restore/replay qualification pass.

The new architecture must consume those foundations rather than recreate them.

Do not mix this plan into the current ML-hardening PR.

---

# PHASE 1 — Shared evidence/provenance contract

## 1.1 Create a common evidence reference type

Introduce a pure schema/module such as:

```text
household/evidence.py
```

or an equivalent package location chosen during implementation.

Conceptual contract:

```json
{
  "schema": "earthship-evidence-ref/v1",
  "sourceRole": "battery_soc",
  "sourceIdentity": "...",
  "observedAt": "...",
  "receivedAt": "...",
  "validUntil": "...",
  "sourceEpoch": "...",
  "quality": "qualified",
  "digest": "...",
  "reason": null
}
```

Not every source must have every timestamp, but absence must be explicit.

## 1.2 Adapter, not rewrite

Existing BMS, PV, weather and thermal receipts remain authoritative. Build adapters
from existing contracts into the common reference form.

Do not replace mature source-specific validation with a generic weaker parser.

## 1.3 Required invariants

- digest refers to exact original evidence where available;
- source epoch is preserved;
- source-specific qualification result is retained;
- future timestamps fail closed;
- expired evidence cannot become current through snapshot construction;
- derived values link to their parent evidence;
- compact references do not delete authoritative history.

## 1.4 Tests

Add contract tests for:

- valid adapters from BMS/PV/weather/thermal evidence;
- stale and expired sources;
- wrong epoch;
- wrong digest;
- malformed optional metadata;
- missing evidence;
- independent evidence counting.

---

# PHASE 2 — Canonical immutable HouseholdSnapshot

## 2.1 Purpose

All cross-domain models and planning decisions must consume one frozen,
time-consistent state instead of independently rereading live mutable sources.

## 2.2 Initial domains

### Energy

At minimum:

- battery SoC;
- usable battery energy / bank epoch;
- instantaneous charge/discharge power;
- PV power;
- predicted PV;
- current/estimated load;
- predicted overnight trough;
- curtailment state where qualified;
- generator state if/when represented.

### Thermal

- room / hallway air state;
- north-wall mass state;
- outdoor temperature;
- solar radiation;
- relevant humidity;
- shade state when qualified;
- ventilation/window/skylight state when qualified;
- accepted thermal artifact identity and confidence.

### Water

Start only with sources already trustworthy enough to represent.

Potential fields:

- greywater circulation state;
- pump state;
- future cistern level / pressure / well information as those sensors become
  qualified.

Unknown water inventory must remain unknown; do not invent a tank estimate solely to
complete the schema.

### Weather/environment

- forecast issue identity;
- outdoor trajectory;
- radiation trajectory;
- precipitation/rain information when qualified;
- wind as available;
- daylight / solar geometry;
- season/mode.

### Authority/status

- OpenHAB source freshness;
- owner-rule availability;
- release/safety mode;
- hardware/source epochs;
- known disabled capabilities;
- planner mode.

## 2.3 Snapshot identity

Each snapshot should carry:

```text
snapshot_id
created_at
as_of
schema_version
source evidence refs
domain freshness
code revision
configuration revision
```

Prefer a deterministic digest of normalized content where practical.

## 2.4 Snapshot construction must be pure at the decision boundary

Live readers may gather evidence, but the resulting snapshot is immutable.

Models must receive the snapshot as an argument rather than silently consulting
OpenHAB again during the same planning cycle.

## 2.5 Temporal consistency

Declare explicit maximum age/skew per source class.

A snapshot must state whether it is:

```text
complete_for_forecast
complete_for_shadow_planning
incomplete
```

Completeness is capability-specific. Missing shade position should not invalidate an
unrelated battery display, but it should invalidate a shade-action counterfactual that
requires it.

---


# PHASE 2B — OpenHAB capability and owner-rule contract

**Priority:** HIGH  
**Behavioral change:** NONE initially

The current feeder, greywater and night-load implementations already establish the
correct execution pattern:

```text
request Item
    ↓
sole owner rule
    ↓
validation + durable acceptance + safety + serialization
    ↓
protected actuator
    ↓
correlated result Item
```

Preserve this pattern and standardize it so a future planner does not create a second
control path.

## 2B.1 Make the OpenHAB control topology machine-readable

Extend the existing tracked ownership/resource manifests into a canonical capability
registry. Reuse `openhab/file-config/ownership.json` and/or
`openhab/managed-resources.json`; do not create a competing source of truth without
a migration plan.

Each actionable capability should eventually describe, at minimum:

```json
{
  "schema": "earthship-control-capability/v1",
  "capability": "greywater-cycle",
  "ownerRule": "hex_southoutlet_cycle",
  "requestItem": "SouthOutlet_ManualRequest",
  "resultItem": "SouthOutlet_ManualResult",
  "ledgerItem": null,
  "intentTypes": ["RUN_GREYWATER_CYCLE"],
  "protectedActuators": ["SouthOutlet_Outlet2_Switch"],
  "safetyInputs": [
    "BMS_SOC",
    "BMS_Comms_Status",
    "DCData_Voltage"
  ],
  "manualAuthority": "request",
  "plannerAuthority": "shadow",
  "contractVersion": "earthship-control-request/v1"
}
```

The manifest is descriptive and testable. It does not grant authority by itself.
The owner rule remains authoritative.

## 2B.2 Standardize Item roles

Document and test the role of every control-relevant Item.

### Physical/provider state

Examples:

- BMS SoC / voltage / comms;
- provider switch state;
- temperatures;
- pump state;
- future shade position.

### Qualified evidence

Examples:

- BMS evidence receipts;
- PV-day evidence;
- qualified weather evidence.

These are observation sources, not command channels.

### Forecast/model output

Examples:

- thermal shadow/model output;
- prediction receipts;
- predicted SoC/PV Items.

These are not execution authorization.

### Request ingress

Examples already in production:

- `SouthOutlet_ManualRequest`;
- `GoatFeeder_ManualRequest`;
- `NightLoadOverride_Request`;
- `NightLoadDevice_Request`.

### Owner result / execution evidence

Examples:

- `SouthOutlet_ManualResult`;
- `GoatFeeder_ManualResult`;
- night-load Result Items;
- durable owner ledgers and completion records.

### Protected actuators

Examples:

- `SouthOutlet_Outlet2_Switch`;
- `Goat_Plugs_Outlet2_Switch`;
- owner-controlled night-load devices.

No planner or browser path may write these directly.

## 2B.3 Define a common correlated request v2 contract

The existing owner rules already share `requestId` and `requestedAt` concepts.
Standardize the next contract while retaining v1 compatibility during migration.

Conceptual request:

```json
{
  "schema": "earthship-control-request/v2",
  "requestId": "req-...",
  "intentId": "intent-...",
  "intentType": "RUN_GREYWATER_CYCLE",
  "source": "ui",
  "requestedAt": "2026-10-07T15:00:00Z",
  "expiresAt": "2026-10-07T15:02:00Z",
  "snapshotId": null,
  "plannerVersion": null,
  "parameters": {}
}
```

Requirements:

- `requestId` remains unique and idempotency-safe;
- `requestedAt` remains mandatory;
- `expiresAt` is mandatory in v2;
- each owner retains a local hard maximum request age;
- a planner cannot extend validity beyond the owner's maximum;
- `intentId`, `snapshotId` and `plannerVersion` are nullable for manual/UI
  requests but required for future planner-originated requests;
- parameters are capability-specific and strictly validated;
- payload size is bounded;
- malformed/unknown schema versions fail closed.

## 2B.4 Define one result vocabulary

Standardize future result status values:

```text
accepted
running
completed
denied
failed
```

Retire the feeder-specific `complete` spelling only through a backwards-compatible
contract migration. Existing UI readers may temporarily accept both.

Conceptual result:

```json
{
  "schema": "earthship-control-result/v2",
  "requestId": "req-...",
  "intentId": "intent-...",
  "status": "completed",
  "reasonCode": "completed",
  "ownerVersion": "greywater-owner-v2",
  "at": "2026-10-07T15:05:00Z",
  "snapshotId": "snapshot-..."
}
```

The result must distinguish transport acceptance, owner acceptance, physical running,
confirmed completion, denial, failure and outcome-unknown at the consumer.

## 2B.5 Create a shared reason-code catalog

Existing owner rules already emit useful stable concepts such as:

```text
low_soc
cooldown
after_dark
busy
provider_offline
request_stale
ledger_restore_missing
ledger_readback_failed
restart_uncertain
duplicate
execution_error
```

Create a versioned reason-code catalog used by:

- owner-rule tests;
- UI result rendering;
- planner shadow evaluation;
- replay;
- later outcome analysis.

Keep human-readable detail separate from the stable code.

A key planner metric becomes:

> how often did the planner propose something that the real owner would have denied,
> and why?

## 2B.6 Record request origin but never trust it for safety

Allow a bounded origin such as:

```text
ui
schedule
planner
operator
recovery
```

This is provenance only.

Safety gates must not be weakened because `source=planner`, `source=operator`, or
any other origin was supplied.

Existing owner rules that deliberately do not branch on requester identity establish
the preferred precedent.

## 2B.7 Bind planner requests to snapshot and intent identity

Future planner-originated requests must carry:

```text
snapshotId
intentId
plannerVersion
```

This allows an end-to-end chain:

```text
qualified evidence
→ HouseholdSnapshot
→ planner decision
→ typed intent
→ owner request
→ owner acceptance/denial
→ physical outcome
→ qualified outcome evidence
```

The owner must not trust the referenced snapshot for current safety. It rereads
critical current Items and provider state before actuation.

## 2B.8 Normalize schedule, UI and planner origins through one owner path

Where an owner currently has cron plus manual request triggers, converge internally
toward:

```text
schedule trigger
UI request
future planner request
       │
       ▼
normalized internal owner request
       │
       ▼
same gate evaluation
       │
       ▼
same execution function
       │
       ▼
same execution/result vocabulary
```

Do not create duplicate schedule, UI and planner execution code.

Automatic schedules may remain native rule triggers; the requirement is shared gate
and execution semantics, not necessarily forcing every cron event through a public
String Item.

## 2B.9 Separate request transport from durable ledger only when justified

Several current owners intentionally use the request Item as both ingress and bounded
durable ledger. That design is carefully tested and must not be rewritten merely for
aesthetic consistency.

The preferred long-term v2 shape is:

```text
<Capability>_Request
<Capability>_Result
<Capability>_Ledger_JSON
```

but create a separate ledger Item only when a reviewed migration demonstrates a real
operational/replay benefit and preserves commit-before-command semantics.

Never weaken the existing guarantees:

- accepted work is durable before actuation;
- readback is verified;
- duplicate IDs are rejected;
- interrupted work is restart-uncertain and never replayed blindly;
- ledger corruption fails closed.

## 2B.10 Add compact planner/snapshot observability Items later

After the read-only snapshot/planner contracts stabilize, add compact observational
Items such as:

```text
Household_Snapshot_Status_JSON
Household_Planner_Status_JSON
Household_Planner_Shadow_JSON
```

These may expose:

- snapshot ID and age;
- completeness class;
- planner mode;
- selected shadow intent;
- hard-block reason;
- planner version.

Do not make one giant OpenHAB Item the authoritative full household snapshot. Full
snapshot/replay artifacts belong in bounded planning/runtime storage with references
to their source evidence.

## 2B.11 Tags/groups are organizational metadata, not authority

Groups such as:

```text
gEarthshipEvidence
gEarthshipForecasts
gEarthshipControlRequests
gEarthshipControlResults
```

may improve MainUI/discovery.

The planner must never derive execution authority from a group or semantic tag.

## 2B.12 Reference migration order

Do not rewrite every owner at once.

Recommended order:

1. machine-readable capability registry only — behavior neutral;
2. shared request/result/reason-code schemas and test helpers;
3. **greywater** as the first v2 owner reference because it already has:
   - manual and automatic origins;
   - BMS/SoC/voltage safety gates;
   - cooldown;
   - long-running execution;
   - persistence and restart handling;
4. night-load owners;
5. feeder protocol normalization where useful;
6. shades only after hardware commissioning;
7. future well/cistern/flexible-load capabilities only after their evidence and owner
   contracts exist.

Every owner migration must retain a v1 compatibility/rollback path until its v2
consumer and persistence behavior are qualified.

## 2B.13 Required OpenHAB tests

Add static and behavioral tests proving:

- the capability registry names one owner per protected capability;
- protected actuators are absent from browser/planner direct-write allowlists;
- every planner-capable control has request/result Items;
- request v2 rejects unknown schema, stale/future/expired requests and oversized data;
- owner hard maximum age overrides a later `expiresAt`;
- `source` never weakens safety;
- snapshot/intent identifiers are provenance only;
- owner rules reread live safety-critical state;
- result status and reason codes are from the common catalog;
- scheduled/manual/planner origins hit the same safety/execution semantics;
- commit-before-command remains mandatory;
- restart-uncertain work is not replayed;
- direct provider-item writes remain impossible from the planner and UI.

---

# PHASE 3 — Refactor model boundaries around pure functions

## 3.1 Follow the thermal-model pattern

The thermal subsystem's separation into datasets, dynamics, behavior, evaluation,
artifacts and pipeline is the preferred direction.

Refactor forecast/energy intelligence incrementally so calculations can run as pure
functions over frozen input.

Do not perform a large one-shot rewrite.

## 3.2 Extract from forecast_intel.py over time

Candidate future modules:

```text
household/
  evidence.py
  snapshot.py

energy/
  observations.py
  battery.py
  pv.py
  soc.py
  evaluation.py

weather/
  forcing.py
  corrections.py

planning/
  trajectories.py
  intents.py
  constraints.py
  arbiter.py
  replay.py
```

Exact packaging can follow repository conventions, but domain logic and live
OpenHAB I/O should become separable.

## 3.3 Preserve numerical parity

Every extraction requires golden/parity tests proving existing production forecast
values are unchanged unless the change is separately qualified.

---

# PHASE 4 — Typed household intents

## 4.1 Define intent semantics before building an optimizer

Initial intent vocabulary should be small.

Candidate types:

```text
RUN_GREYWATER_CYCLE
REQUEST_SHADE_POSITION
REQUEST_VENTILATION_STATE
DEFER_FLEXIBLE_LOAD
USE_SURPLUS_SOLAR
PRESERVE_BATTERY
NO_ACTION
```

Only include an intent type once a real owner/executor contract exists or a clearly
shadow-only representation is useful.

## 4.2 Intent fields

Conceptual schema:

```json
{
  "schema": "earthship-household-intent/v1",
  "intentId": "...",
  "type": "...",
  "createdAt": "...",
  "expiresAt": "...",
  "snapshotId": "...",
  "evidenceRefs": [],
  "predictedEffects": {
    "batteryKwh": null,
    "socPct": null,
    "thermalF": null,
    "water": null,
    "wearCost": null
  },
  "confidence": "...",
  "reasonCodes": [],
  "shadowOnly": true
}
```

## 4.3 Intents are not authorization

An intent cannot directly become a provider command.

## 4.4 Intent-to-OpenHAB translation is a separate adapter

Keep the planner's domain intent schema independent from OpenHAB transport.

A future adapter may translate a graduated intent into one capability-specific
`earthship-control-request/v2` payload only when:

- the intent type is admitted by the capability registry;
- the intent has passed the household arbiter;
- the capability is explicitly graduated beyond shadow;
- its snapshot/intent identities are preserved;
- the request has a bounded validity interval.

This adapter still does not authorize execution. The OpenHAB owner rule can deny it.

---

# PHASE 5 — Household constraint registry and arbiter

## 5.1 Centralize cross-domain constraints

Domain owner rules stay in OpenHAB, but a shadow planner needs a consistent model of
known constraints so it does not routinely propose impossible/conflicting actions.

Examples:

- emergency SoC reserve;
- pump curfew;
- pump cooldown;
- mutually exclusive pump operation if applicable;
- minimum water reserve once qualified;
- shade capability/commissioning;
- source freshness;
- operator lockouts;
- manual override;
- actuator cooldown/rate limit;
- incompatible thermal actions.

## 5.2 Hard constraint versus objective

Every rule must be classified as one of:

```text
HARD_CONSTRAINT
SOFT_OBJECTIVE
DIAGNOSTIC_ONLY
```

A hard constraint can never be outweighed by an optimizer score.

## 5.3 Arbiter

The arbiter should resolve conflicting typed intents deterministically and explain:

```text
accepted
rejected
deferred
superseded
unknown
```

with stable reason codes.

Do not duplicate detailed device safety logic from OpenHAB. The arbiter is an economic/
coordination guard; OpenHAB remains the execution gate.

---

# PHASE 6 — Shadow household planner v1

## 6.1 Initial mode

```text
SHADOW ONLY
NO OPENHAB ACTION REQUESTS
NO NOTIFICATIONS
NO ACTUATOR WRITES
```

The first planner answers only:

> Given this frozen state and forecast, what optional household action set would have
> been preferred under the declared constraints/objectives?

## 6.2 Start with transparent deterministic value functions

Do not begin with RL, a neural network, or an LLM policy.

Example objectives:

- avoid violating battery reserve;
- reduce expected deep discharge;
- use otherwise-curtailed solar where a qualified flexible load exists;
- reduce avoidable thermal discomfort;
- minimize unnecessary pump/device cycles;
- preserve future water availability;
- avoid mutually harmful actions.

Use explicit units wherever possible.

## 6.3 Rolling horizon

Use a bounded horizon appropriate to available forecasts, for example:

```text
next 6h / 12h / 24h
```

The exact horizon is a versioned planner input.

## 6.4 Solver

First implementation may use:

- exhaustive search over a deliberately tiny action set;
- a small MILP/CP-SAT formulation;
- another deterministic solver justified by the actual constraint structure.

Do not introduce a heavy dependency before the shadow problem is proven useful.

## 6.5 Baselines

Every planner evaluation should compare against:

1. actual household behavior;
2. current deterministic OpenHAB policy;
3. "do nothing" for optional actions;
4. a simple greedy heuristic where useful.

---

# PHASE 7 — Deterministic household replay

## 7.1 Goal

Given:

```text
snapshot
forecast / forcing
model artifacts
planner config
code revision
```

reproduce:

```text
domain trajectories
candidate intents
constraint decisions
selected shadow plan
```

without live mutation RPCs.

## 7.2 Replay evidence

Store bounded planner receipts containing:

- snapshot identity;
- input artifact identities;
- forecast issue identity;
- candidate intent set;
- constraint results;
- objective decomposition;
- selected shadow plan;
- planner version/config;
- digest.

## 7.3 Outcome scoring

When later source-qualified outcomes mature, score:

- predicted vs actual energy state;
- predicted vs actual thermal state;
- whether the proposed action remained feasible;
- whether actual deterministic policy performed better/worse;
- counterfactual uncertainty.

Never claim causal benefit simply because an action was followed by a favorable
outcome.

---

# PHASE 8 — Resource-effect vectors and household drift

Represent candidate actions by a normalized multi-resource effect vector such as:

```text
Δbattery
Δthermal
Δwater
Δcomfort
Δequipment_wear
Δcurtailment
```

This supports:

- transparent objective decomposition;
- conflict analysis;
- cumulative drift metrics;
- offline scheduling-order experiments;
- detecting plans that achieve one goal by causing unacceptable transient excursions.

Do not collapse every dimension into one unexplained scalar.

---

# PHASE 9 — UI / operator observability

The UI should gain a read-only planner panel only after the shadow contract stabilizes.

Display:

- planner mode: unavailable / shadow / advisory / active-request;
- snapshot age;
- model/artifact identities;
- suggested action;
- expected effects;
- blocking hard constraints;
- confidence/evidence quality;
- whether existing OpenHAB policy agrees/disagrees.

Do not render "AI recommends" without the underlying reason/evidence state.

The planner should be inspectable even when no action is suggested.

---

# PHASE 10 — Qualification gates before any live planner request

A planner-generated intent may leave shadow only through a separate reviewed release.

Minimum gates:

1. deterministic replay passes;
2. evidence/source contracts pass;
3. no hard-constraint bypass exists;
4. stale/unknown evidence fails closed;
5. shadow planning has enough independent chronological windows;
6. selected actions are stable under modest input uncertainty;
7. model error is included in decision uncertainty;
8. planner beats or usefully complements the deterministic baseline;
9. operator can understand the reason codes;
10. rollback to no-planner mode is tested;
11. no direct provider-item write path exists;
12. OpenHAB owner rule independently rechecks all physical safety conditions.

Graduation is per intent family, not global.

Example:

```text
greywater request planner: active
shade planner: shadow
ventilation planner: unavailable
```

---

# PHASE 11 — Staged live integration

## 11.1 Stage A — shadow

No live request.

## 11.2 Stage B — operator-visible advisory

Show what the planner would request. Operator decides.

## 11.3 Stage C — planner request to one existing owner rule

Only after qualification, allow one intent family to submit the same bounded request
that an operator/UI can already submit.

The OpenHAB owner rule remains authoritative and can deny it.

## 11.4 Stage D — additional intent families

Qualify independently.

No global "autonomous house" switch.

---

## 5. Water-system sequencing

Do not delay the architecture until every cistern/well sensor exists.

Implement the water domain incrementally:

1. existing greywater/pump state;
2. qualified pressure / flow observations when available;
3. qualified cistern inventory once sensing is installed and calibrated;
4. well pumping / refill planning only after reliable state and execution contracts exist.

Unknown water state remains unknown.

---

## 6. WeatherNext relationship

WeatherNext should eventually appear as a qualified weather-forcing provider feeding
the same snapshot/forecast interface.

The planner must not care whether forcing originated from Open-Meteo or WeatherNext.

Provider-specific acquisition and qualification belong below:

```text
WeatherForecast / Forcing contract
```

This separation will make the later WeatherNext migration safer.

---

## 7. Local AI agent role

The local home-automation agent remains an engineering/operations agent, not the
household controller.

It may:

- inspect evidence;
- run replay;
- generate qualification reports;
- diagnose planner disagreement;
- prepare reviewed changes.

It must not gain planner or physical authority merely because this architecture exists.

---

## 8. Testing strategy

### Pure/unit tests

- evidence adapters;
- snapshot normalization/digests;
- temporal skew/freshness;
- domain trajectory functions;
- constraint evaluation;
- arbiter conflict matrix;
- planner determinism;
- typed intent schema;
- replay identity.

### Property/invariant tests

- hard constraints are never converted to soft penalties;
- stale evidence cannot increase authority;
- adding an unavailable optional domain cannot fabricate a value;
- planner never writes OpenHAB/provider state;
- identical snapshot/config produces identical plan;
- a rejected intent has a stable reason;
- no action path bypasses the existing owner rule.

### Historical replay

Use qualified chronological evidence only.

Keep training/tuning windows separate from final evaluation windows.

### Runtime shadow qualification

Collect:

```text
snapshot count
independent planning windows
planner availability
baseline agreement
hard-block counts
proposed action counts
objective decomposition
later outcome qualification
```

---

## 9. Repository / implementation strategy

Avoid a large branch that rewrites forecasting, controls and UI simultaneously.

Recommended sequence:

1. evidence reference types/adapters;
2. HouseholdSnapshot v1;
3. machine-readable OpenHAB capability registry;
4. read-only snapshot publication/debug tool;
5. pure model adapters;
6. common request/result/reason-code contract definitions and test helpers;
7. typed intents plus intent-to-request adapter kept disabled;
8. constraints + arbiter;
9. replay;
10. shadow planner;
11. shadow UI;
12. greywater v2 owner-contract qualification as the first control reference;
13. only then any separately approved live planner request integration.

Each step should be independently mergeable and behavior-neutral until the shadow
planner exists.

---

## 10. Initial milestone definition

The first milestone is complete when the project can perform this command-equivalent
operation entirely read-only:

```text
capture qualified evidence
        ↓
build one HouseholdSnapshot
        ↓
load the declared OpenHAB capability/ownership registry
        ↓
run existing energy + thermal projections
        ↓
generate a bounded set of typed shadow intents
        ↓
apply hard constraints
        ↓
choose one deterministic shadow plan
        ↓
write a sealed local planner receipt
```

and rerun the same receipt offline to the identical result.

No physical action is part of Milestone 1.

---

## 11. Success criteria for the architectural program

The program succeeds when:

- cross-domain decisions use one frozen household state;
- evidence provenance is consistent across domains;
- domain models are independently testable and replayable;
- safety/authority constraints cannot be traded for optimizer reward;
- optional actions are coordinated rather than racing independently;
- OpenHAB remains the final deterministic authority;
- actionable capabilities have one explicit machine-readable owner/request/result
  contract;
- planner/UI/schedule origins converge on the same owner-rule safety semantics;
- protected actuator Items remain unreachable from planner/browser direct-write paths;
- planner decisions are explainable through effect decomposition and reason codes;
- shadow results can be scored against actual household outcomes;
- each actuator family has an independent graduation and rollback path;
- no new model or planner can gain physical authority merely by being installed.

---

## 12. Explicit non-goals

Do not use this program to:

- replace OpenHAB;
- bypass hardware protections;
- make an LLM the live control policy;
- combine all household prediction into one opaque ML model;
- automatically graduate the thermal model;
- change existing forecast equations without separate evidence;
- enable uncommissioned shades;
- invent water/cistern state;
- enable WeatherNext before its own qualification;
- broaden the local engineering agent's authority;
- remove manual override;
- create a second competing automation owner;
- rewrite working owner rules merely to make their storage aesthetically uniform;
- infer control authority from Item names, tags or group membership.

---

## 13. Coding-agent sequencing

The in-flight coding agent should finish the current forecast-ML/thermal graduation
goal first.

Reason:

- the current work is already deeply implemented;
- it establishes evidence and identifiability primitives required here;
- focused workflows are already green;
- interrupting now would strand a large partially qualified change and increase merge
  and scope risk.

After the current PR is merge-ready and merged, give the coding agent a **new goal**
derived from this plan, beginning only with the behavior-neutral foundation:

1. shared evidence reference/adapters;
2. HouseholdSnapshot v1;
3. machine-readable OpenHAB capability/ownership registry;
4. read-only snapshot/replay foundation.

The next goal may define the common request/result/reason-code schemas as pure contracts
and test helpers, but it should not migrate live owner rules or create planner request
authority yet.

Do not ask the next goal to implement live planner authority.

The planner itself should be a later bounded goal after the snapshot foundation has
merged and accumulated enough replay fixtures.
