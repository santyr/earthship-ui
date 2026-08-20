# Earthship Thermal Multihorizon Identification

**Date:** 2026-08-20

**Status:** Approved for implementation; amended after the private v2 Gate A rerun

**Extends:** `2026-08-20-thermal-training-photosensor-repair-design.md`

## Purpose

Correct the RC model's verified open-loop warm drift without weakening its
physics, chronology, promotion, or deployment gates. The physical core remains
the approved two-state model: hallway air plus latent deep-mass charge. The
behavior model, seasonal modes, action evidence, Kiva exclusions, OpenHAB Item
surface, shadow JSON schema, and non-actuating authority remain unchanged.

## Verified failure

The first latent-mass Gate A candidate was physically valid and covered all
four evidence-backed seasonal modes, but promotion correctly refused it. Its
24-hour hallway-air MAE was 6.601 F versus 1.301 F for persistence. All eight
scored 24-hour forecasts were warm-biased by 3.27 F to 13.80 F.

Private reproduction showed that the five-minute teacher-forced regressions
learn large cancelling terms. Across those eight forecasts, accumulated solar
terms added roughly 23 F to 58 F while mass exchange removed roughly 9 F to
43 F. Fold envelope coefficients were frequently near zero. Those cancellations
fit observed one-step state transitions but do not remain balanced when the
model recursively supplies its own air and mass states. A diagnostic joint
five-minute regression changed the 24-hour MAE only from 6.601 F to 6.318 F,
so the split envelope regression is not the primary cause. The failure is the
identification objective: it does not constrain open-loop behavior at the
horizon used by promotion.

After this design was first approved, the separately approved thermal artifact
v2 change added bounded `mass.outside_exchange` to remove the neutral deep-mass
mode. A fresh private 400-day v2 Gate A run on 2026-08-20 passed the exact
database and physics contracts but was still refused by
`air_24h_beats_persistence`: model MAE was 4.070 F across nine scored forecasts
versus 1.287 F for persistence, with +4.070 F model bias. The structural loss
term improved the earlier v1 result but did not repair recursive warm drift.
This multihorizon design therefore starts from the current v2 dynamics, retains
`mass.outside_exchange`, and advances only the private artifact contract to v3.

## Selected approach

Retain the existing constrained five-minute fit as a deterministic feasible
initializer, then refine the same air and mass coefficients against strictly
training-only open-loop trajectories. The refinement changes identification,
not the state equations or promotion threshold.

Rejected alternatives are:

- Adding a third solar-lag state. This would abandon the approved 2R2C core and
  require a larger physical-model redesign.
- Applying a recent-cycle or empirical residual correction after simulation.
  That could conceal a defective physical trajectory and optimize around the
  promotion gate instead of repairing identification.
- Scaling or clamping solar coefficients after fitting. Such a correction is
  not an identified constrained optimum and would hide failure evidence.

## Model and coefficient boundary

The current v2 five-minute state equations, coefficient names, coefficient bounds,
ordered nonnegative solar gains, vent forcing, and glazing observation equation
remain unchanged. The second-stage optimizer refines all seven air coefficients
and all five mass coefficients jointly because their recursive trajectories are
coupled. Glazing coefficients remain a separate one-step observation fit and do
not participate in state propagation.

The starting point is the current full-rank, bounded, ordered-solar fit. The
refinement may not introduce a coefficient, substitute a prior artifact, or
relax a bound. The final model must independently pass the existing gain,
transition-stability, output-range, and 72-hour simulation validation.

## Chronological rollout selection

Rollout origins are selected only from the fitter's supplied training slice.
The selector groups rows by local calendar day and chooses at most one origin
per day: the row with the longest valid future run, breaking ties by earliest
UTC timestamp. This matches the walk-forward evaluator's deterministic
anti-cherry-picking rule.

The identification horizons are exactly 5 minutes, 1 hour, 6 hours, 12 hours,
and 24 hours. A rollout contributes to a horizon only when every intervening
five-minute row:

- is present and strictly consecutive;
- has finite core observations and known vent, indoor-shade, and outdoor-shade
  states;
- is allowed for passive fitting, so inferred or confirmed Kiva intervals and
  cooldown exclusions cannot enter;
- does not cross a dataset rejection or mode-evidence gap; and
- does not activate a forcing column that the fold training fit identified as
  absent.

For each horizon, uniformly retain at most 64 eligible daily origins across the
entire training interval, always including the first and last eligible origin.
When more than 64 exist, select canonical sorted indices
`floor(i * (count - 1) / 63)` for `i=0..63`. This bounds every fold's optimizer
cost without selecting from held-out error. The cap and index rule are exact
artifact constraints.

The rollout weight is the minimum aggregate action confidence across its
intervening rows. This is conservative and prevents a long reconstructed window
from inheriting the confidence of only its strongest endpoint. The full fit
requires at least two valid origins at every non-five-minute horizon. Historical
walk-forward folds with insufficient origins are recorded as unscored fit
refusals; they do not abort the complete report.

## Objective and optimization

For each valid origin, simulation starts from the observed hallway-air and
latent-mass state and recursively applies the observed held-in-training
forcings. Residuals are computed only at the exact five-minute, 1-hour, 6-hour,
12-hour, and 24-hour endpoints.

The objective is the sum of ten group means: air and mass mean squared error at
each of the five horizons. Each squared residual is multiplied by its rollout
confidence. Equal group means prevent the dense five-minute group or a horizon
with more continuous origins from dominating solely through row count. All
temperatures share Fahrenheit units, so no data-derived held-out scale enters
the objective.

Use deterministic SLSQP with analytic forward-sensitivity gradients, the
existing coefficient bounds, and the existing ordered-solar linear constraints.
The current constrained five-minute result is the sole starting point. Use
`ftol=1e-10`, `maxiter=500`, and no random restart. Refuse a reported objective
increase greater than `1e-9 * max(1, initial_objective)`. The optimizer
configuration is fixed in code and exact artifact evidence. Refuse the fit when
the objective inputs are insufficient,
rank-deficient, or non-finite; when optimization is unsuccessful or
non-finite; when the final objective exceeds the starting objective beyond
numerical tolerance; or when final independent physics validation fails.

Rank is evaluated locally at the five-minute initializer over the complete
confidence-weighted endpoint-sensitivity matrix, restricted to active
coefficients. Normalize each nonzero active column before the rank test so
coefficient units do not hide structural dependence; reject zero columns or
less than full active-column rank before invoking SLSQP.

This is training, not evaluation. In every walk-forward fold the optimizer sees
only rows before that fold's origin. Held-out targets and future action evidence
cannot affect its coefficients, origin selection, convergence, or objective.

## Evidence and compatibility

The private constraints manifest gains exact closed static evidence for:

- the five identification horizons;
- the daily-origin selection rule;
- the minimum-window confidence rule;
- the equal state-and-horizon group-mean objective; and
- the fixed optimizer method and tolerances.

The fit diagnostics gain exact closed run evidence for valid rollout-origin
counts at each horizon and finite initial and final objective values.

Typed and raw artifact validation reject missing, extra, mistyped, non-finite,
or semantically inconsistent multihorizon evidence. Dictionary key insertion
order is non-semantic because canonical registry JSON sorts object keys; ordered
arrays such as `horizons_minutes` reject reordering. Because this
changes the exact private artifact contract, the model artifact schema advances
from `earthship-thermal-model/v2` to `earthship-thermal-model/v3`. The registry
has no accepted v2 generation to migrate; the refused private v2 candidate is
evidence, not a fallback generation. The backtest report shape remains v1, and the immutable
`earthship-thermal-shadow/v1` payload does not gain a field.

The backtest report retains its existing shape and promotion rules. Gate A
still requires finite physics-valid evidence, at least two scored folds, and a
24-hour hallway-air MAE strictly better than persistence. No training-objective
metric can substitute for that held-out result.

## Failure and authority boundaries

If a full multihorizon fit fails before an artifact exists, persist no candidate.
Chronological evaluation records fold-local fit refusals and persists the
backtest report when evaluation can complete. A completed but promotion-ineligible
fit persists the private candidate and refusal report as currently defined.
Retain any prior verified accepted artifact and publish nothing. Never tune a
coefficient, horizon weight, origin, or gate from held-out Gate A outcomes
without another reviewed design amendment.

Implementation and verification authorize repository and private Gate A work
only. They do not authorize creation or publication of `Thermal_Model_JSON`,
systemd installation, timer activation, changes to `Thermal_Advisory`, or any
vent, shade, Kiva, or other actuator command. Stop with evidence before Gate B.

## Testing and acceptance

Test-driven implementation must include:

- a deterministic synthetic 2R2C dataset where the existing one-step optimum
  has verified 24-hour warm drift and multihorizon refinement reduces it;
- exact horizon/origin selection, local-day tie breaking, confidence weighting,
  gap/action/Kiva refusal, and inactive-forcing tests;
- a leakage test proving held-out target or action mutations cannot change a
  fitted fold;
- optimizer unsuccessful, non-finite, objective-regression, bound, solar-order,
  instability, and output-range refusals;
- byte-for-byte deterministic coefficients and evidence across repeated fits;
- exact typed and raw artifact evidence validation;
- unchanged shadow schema and no new OpenHAB or actuator surface;
- focused dynamics, evaluation, artifact, and pipeline suites followed by the
  complete thermal/forecast Python suite, Vitest, build, Playwright, static
  checks, and clean-diff checks; and
- a new attended private 400-day train, independent backtest, and local shadow.

Passing repository tests is not Gate A completion. Gate A completes only if the
fresh live candidate is promoted through the unchanged 24-hour persistence
comparison and all other runbook evidence is green.
