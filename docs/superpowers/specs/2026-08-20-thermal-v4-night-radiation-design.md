# Thermal v4 Astronomical-Night Radiation Design

**Date:** 2026-08-20
**Status:** Operator-approved design
**Scope:** Private RC thermal training and Gate A evidence only

## Background

The 400-day multihorizon v3 Gate A run remained fail-closed. The private
candidate was physically valid and reduced 24-hour hallway-temperature MAE
from the earlier v2 result, but it still lost to persistence:

- model 24-hour hallway MAE: `2.52077500770327 F`;
- persistence 24-hour hallway MAE: `1.6749999999999996 F`;
- scored 24-hour folds: `6`;
- fold distribution: one winter fold and five shoulder-season folds clustered
  from 2026-04-01 through 2026-04-05.

The backtest had 377 daily folds, but only 11 daily origins had a continuous
24-hour target and only six of those could be fitted and scored. The principal
continuity loss is a data-semantics error: OpenHAB JDBC persistence records
solar radiation on change, while the dataset treats a silence longer than 60
minutes as a missing source. Normal nighttime radiation therefore becomes a
source gap after one hour even when the persisted state is correctly unchanged
at zero.

A read-only characterization over the same 400-day OpenHAB history found:

| Evidence construction | Valid five-minute rows | Possible 24-hour daily origins | Possible 72-hour daily origins |
| --- | ---: | ---: | ---: |
| Existing 60-minute hold rule | 53,924 | 11 | 0 |
| Missing nighttime radiation reconstructed as zero | 99,744 | 179 | 28 |

These are continuity counts before model fitting, not a prediction-performance
claim. They justify repairing the evidence boundary before adding thermal
states, seasonal coefficients, or residual corrections.

## Goals

1. Interpret absent astronomical-night radiation as the physical value zero
   without inventing daylight weather.
2. Broaden chronological 24-hour evaluation across seasons.
3. Retain the existing 2R2C physics, coefficient constraints, multihorizon
   objective, and strict persistence comparison.
4. Require materially stronger evidence before a private candidate can become
   promotion-eligible.
5. Preserve the observational, non-actuating deployment boundary.

## Non-goals

- Do not fill daytime radiation gaps.
- Do not extend temperature interpolation or hold-forward limits.
- Do not infer temperature values from other channels.
- Do not add a solar-lag state, seasonal thermal coefficients, residual model,
  clamp, or baseline substitution in this iteration.
- Do not create or publish `Thermal_Model_JSON`.
- Do not install, start, or enable thermal systemd units.
- Do not change the public `earthship-thermal-shadow/v1` contract.
- Do not relax or remove any existing promotion gate.

## Architecture

### Shared solar calculation

One pure thermal-model component will own the deterministic solar-elevation
calculation. Dataset reconstruction and behavior features will both call this
component so the definition of astronomical night cannot drift between them.

The component will expose:

- rule identifier `earthship-solar-elevation/v1`;
- site latitude `38.3739919`;
- site longitude `-105.7744609`;
- a timezone-aware timestamp input;
- a finite solar-elevation result or its finite sine; and
- astronomical night defined as solar elevation less than or equal to zero.

It will preserve the existing deterministic approximation rather than
introducing a network ephemeris dependency.

### Dataset reconstruction

OpenHAB JDBC history remains the raw measurement authority. Existing bucketing,
range validation, jump rejection, interpolation through 20 minutes, and
hold-forward through 60 minutes remain unchanged.

After those ordinary operations, each five-minute bucket is handled as follows:

1. If a valid radiation bucket already exists from a raw observation, existing
   interpolation, or existing bounded hold-forward, retain it. Those sources
   take precedence over night-zero reconstruction, including an unusual
   nighttime observation.
2. If radiation is absent and solar elevation is less than or equal to zero,
   create a radiation value of exactly `0.0 W/m2` with provenance
   `astronomical_night_zero`.
3. If radiation is absent while solar elevation is positive, reject the sample
   under the existing required-source policy.
4. A gap in air, mass, or outdoor temperature continues to reject the sample.

Raw observed buckets remain distinct from reconstructed buckets. A reconstructed
night bucket is exempt only from the radiation source-gap rejection that its
own every-change silence caused. It does not clear a simultaneous gap in any
other required role.

### Metadata and provenance

`ThermalDataset` will carry deterministic reconstruction metadata and a
timestamp-keyed radiation-provenance sidecar without adding a provenance field
to every `ThermalSample`. The private v4 artifact manifest will record:

- the solar rule identifier and coordinates;
- the exact night-zero rule;
- total accepted `astronomical_night_zero` sample count;
- accepted-sample radiation counts partitioned as `observed`, `interpolated`,
  `held`, and `astronomical_night_zero`, summing exactly to `sample_count`;
- existing interpolation, hold, rejection, and auxiliary-exclusion counts;
- the canonical sample digest; and
- all existing model constraints and fit evidence.

Each walk-forward fold will report `observed`, `interpolated`, `held`, and
`astronomical_night_zero` radiation counts separately for its training prefix
and longest evaluation target. These counts are diagnostic provenance;
reconstructed nighttime zeros remain valid physical forcing rather than action
evidence.

## Model and evaluation

Thermal v4 keeps the current dynamics version and equations:

- two states: hallway air and latent thermal mass;
- current air, mass, outside, solar, shade, vent, and bias coefficients;
- current coefficient bounds and stability checks;
- current causal 120-minute mass observer;
- current five-minute, 1-hour, 6-hour, 12-hour, and 24-hour multihorizon
  objective;
- current deterministic daily-origin selection and bounded sampling;
- current analytic sensitivities, rank test, and SLSQP optimizer; and
- current hybrid behavior model and action-confidence rules.

Walk-forward evaluation remains strictly chronological. Every fold is fitted
only from samples before its origin. The evaluator continues to simulate with
the actual held-out outdoor, radiation, and reconstructed action forcing and to
score against actual future indoor observations. No held-out residual may feed
training, initialization, or candidate selection.

The evaluator continues to report:

- model, persistence, and recent-cycle errors by horizon;
- errors by seasonal regime and action provenance;
- daily hallway high, hallway low, peak-time, and morning-mass errors;
- prediction-interval coverage;
- behavior classification and timing metrics; and
- inactive forcing features and fit failures.

The recent-cycle baseline remains diagnostic. It is never substituted for the
physical model and does not conceal a failed physical forecast.

## Promotion gates

All existing gates remain mandatory and retain their current semantics,
including:

- finite metrics;
- valid physics;
- at least two scored folds; and
- strict 24-hour hallway-air MAE improvement over persistence on the same
  scored records.

Thermal v4 adds both of these gates:

1. `at_least_30_scored_24h_folds`: model 24-hour hallway-air count is at least
   30.
2. `at_least_two_24h_regimes`: at least two of `warm`, `winter`, and `shoulder`
   have five or more scored 24-hour folds each.

The second gate prevents a nominal two-regime result in which one regime is
represented by only one incidental fold. Spring and fall charging retain the
existing evaluation grouping as `shoulder`; this design does not redefine
regime labels.

Promotion eligibility is the conjunction of every old and new gate. A result
with better MAE but insufficient coverage remains refused. A result with broad
coverage but MAE equal to or worse than persistence also remains refused.

## Artifact contracts

- The private artifact schema advances from `earthship-thermal-model/v3` to
  `earthship-thermal-model/v4` to make the new evidence and gates exact and
  fail-closed.
- The private backtest schema advances from `earthship-thermal-backtest/v1` to
  `earthship-thermal-backtest/v2` to carry exact fold radiation provenance and
  the two new gate results.
- Validators reject missing keys, unknown keys, booleans masquerading as
  counts, negative counts, inconsistent totals, invalid coordinates, unknown
  solar rule identifiers, and contradictions between aggregate and fold
  evidence.
- Canonical JSON remains deterministic and dictionary insertion order remains
  non-semantic.
- The public shadow contract remains `earthship-thermal-shadow/v1`.

Before the attended v4 Gate A run, the validated rejected v3 candidate and
backtest report will be copied into the new private deployment receipt with
mode `0600` and recorded SHA-256 digests. They are historical evidence only and
must never be used as an accepted-artifact fallback. The ordinary registry then
writes the v4 candidate and report through its existing atomic validation path.

## Failure behavior

Authority reading or dataset construction aborts the run when:

- a timestamp is naive or invalid;
- the shared solar calculation returns a non-finite value;

Sample construction rejects the affected bucket when:

- radiation is absent during astronomical day;
- any required temperature role is absent;
- an observed value violates existing range or jump checks.

Training, validation, or evaluation refuses the candidate when:

- the configured solar rule or coordinates do not match the v4 contract;
- evidence counts or digests are inconsistent;
- the optimizer, rank test, or physics validation fails; or
- any existing or new promotion gate fails.

On refusal, the system retains the private candidate and report, emits bounded
reasons, and stops. It does not create the OpenHAB Item, publish a shadow,
install services, or enable timers.

## Verification

Implementation will be test-driven. Required tests include:

1. Missing radiation at astronomical night becomes exactly zero.
2. Missing radiation during daylight remains rejected.
3. A persisted nighttime radiation value wins over reconstruction.
4. Exact horizon-boundary, timezone-offset, naive-time, and non-finite cases
   fail or succeed according to the contract.
5. Dataset and behavior code use the same solar calculation.
6. Radiation reconstruction counts and canonical manifests are byte-stable.
7. A synthetic every-change nighttime-silence fixture regains continuous
   24-hour folds without filling daylight or temperature gaps.
8. Each fold's provenance categories sum exactly to its training and evaluation
   row counts; the manifest's accepted-sample categories sum exactly to
   `sample_count`. Fold training prefixes overlap and therefore are not summed
   into the manifest total.
9. Twenty-nine scored 24-hour folds fail the new count gate; 30 pass it.
10. A second regime with fewer than five folds fails; two regimes with at least
    five folds each pass that gate.
11. Every pre-existing persistence and physics gate remains mandatory.
12. Candidate, report, and public-shadow schema validators remain fail-closed.

Before any live installation, verification includes focused dataset, dynamics,
evaluation, artifact, pipeline, and CLI tests; the complete thermal Python
suite; complete frontend tests; production build; browser viewport tests;
static analysis; compilation checks; deterministic-output checks; clean diff
checks; and an independent code review.

## Attended Gate A

Gate A remains private and non-actuating:

1. Confirm a clean, reviewed, pushed repository revision.
2. Create a new mode-`0700` receipt and preserve the rejected v3 candidate and
   report with mode-`0600`, hashes, and validation readback.
3. Re-audit the exact PostgreSQL schema and least-privilege runtime role.
4. Verify the pre-install runtime digest and systemd first-install state.
5. Atomically install only the reviewed runtime manifest and verify its digest.
6. Train and backtest the same 400-day window.
7. Report reconstruction counts, valid rows, fold counts by regime, model and
   baseline errors, daily extrema, interval coverage, physics evidence,
   artifact digests, and every promotion-gate result.
8. Stop if any gate fails.

A fully eligible private v4 candidate permits only a separate Gate B review.
It does not authorize Item creation, shadow publication, service installation,
timer enablement, or household automation.

## Decision after Gate A

If v4 passes every gate, present the exact private evidence and request Gate B
approval. If it fails, use the expanded residual population to determine
whether the remaining error follows solar timing, state initialization,
seasonal behavior, or missing thermal physics. Any such model change requires a
new approved design rather than being bundled into this evidence repair.
