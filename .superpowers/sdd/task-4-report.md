# Task 4 report: constrained 2R2C dynamics

## Status

Initial implementation committed as `bcd9a44 feat: fit constrained Earthship thermal dynamics`; review corrections are documented below.

The implementation is limited to deterministic fitting, diagnostics, physical
validation, one-step prediction, and pure simulation. It adds no OpenHAB,
journal, database, network, advisory, command, or actuation surface.

## Files

- `openhab/scripts/thermal_model/dynamics.py`
- `openhab/scripts/test_thermal_dynamics.py`

The existing frozen `DynamicsModel` and `ThermalSample` schemas were not
changed. South glazing remains the optional
`glazing_observation_coefficients` equation and never becomes a third state.

## Implemented interfaces

- `fit_dynamics(samples) -> DynamicsModel`
- `fit_diagnostics(samples) -> dict[str, int | float]`
- `predict_step(model, sample) -> tuple[float, float, float | None]`
- `simulate(model, initial, forcings) -> list[dict]`
- `validate_physics(model) -> DynamicsModel`

`fit_diagnostics` was added as a separate pure reporting surface so the
binding model API and physical coefficient dictionaries remain unchanged.
It reports:

- total exact consecutive five-minute pairs;
- fitted core pairs;
- passive-disallowed endpoint exclusions;
- unknown action-input exclusions;
- auxiliary glazing fitted and skipped rows; and
- remaining action-label coverage fraction.

The diagnostics and fitter share the same row-selection and auxiliary-rank
logic. Auxiliary fitted rows are reported only when the observation design is
actually full-rank; otherwise every selected core row is an auxiliary skip.

## Equations, ordering, and bounds

The air coefficient order is exactly:

1. `outside_exchange`
2. `mass_exchange`
3. `solar_unshaded`
4. `solar_indoor_closed`
5. `solar_outdoor`
6. `vent_exchange`
7. `bias`

The mass coefficient order is exactly:

1. `air_exchange`
2. `solar_unshaded`
3. `solar_indoor_closed`
4. `solar_outdoor`

The glazing observation coefficient order is exactly:

1. `intercept`
2. `air`
3. `outdoor`
4. `solar_unshaded`
5. `solar_indoor_closed`
6. `solar_outdoor`

The implementation uses the approved five-minute `AIR_BOUNDS` and
`MASS_BOUNDS` verbatim and fits with
`scipy.optimize.lsq_linear(method="trf")`.

Each design row and target is multiplied by
`sqrt(sample.action_confidence)`. The per-action confidence fields from Task
3 are preserved unchanged. A deterministic test perturbs measurements and
shows low-confidence rows have less than 5% of the corresponding fully
weighted coefficient error.

The solar features are distinct:

- `unshaded = (1 - indoor_closed) * (1 - outdoor_present)`
- `indoor_closed = indoor_closed`
- `outdoor_shaded = (1 - indoor_closed) * outdoor_present`

A focused parameterized test proves that identical radiation produces the
three distinct fitted gains.

## Selection and optional-observation behavior

Only exact consecutive five-minute pairs are candidates. A pair is excluded
when either endpoint has `passive_fit_allowed=False`. It is also excluded
when the right/end forcing row has an unknown vent, indoor-shade, or
outdoor-shade state. This matches the regression inputs and avoids bridging
dataset gaps.

Core air and mass designs must contain enough rows and have full numerical
column rank. A rank-deficient physical design raises `ValueError` rather than
publishing arbitrary bounded coefficients.

Missing, non-finite, sparse, or rank-deficient glazing observations skip only
the auxiliary regression. Core fitting and simulation continue, and glazing
predictions are `None` when no auxiliary model exists.

## Physical validation and simulation

Validation enforces:

- model version 1 and five-minute steps;
- exact coefficient-key contracts;
- finite coefficients;
- nonnegative exchange coefficients;
- nonnegative solar gains;
- unshaded gain at least as large as both shaded gains; and
- transition spectral radius below `1 - 1e-9` for closed `0.0`, baseline
  `1.0`, and boosted `2.0` ventilation; and
- a separate 72-hour zero-radiation constant-forcing response at all three
  levels that remains finite and within `[-40, 140] F`.

The spectral and trajectory gates are independent: the first rejects neutral
or unstable dynamics, while the second rejects stable but physically
out-of-range forced responses.

`predict_step` and `simulate` never clamp. Non-finite or out-of-range air,
mass, or auxiliary results raise `ValueError`. Simulation accepts only an
explicit initial two-state value and explicit end-of-step forcing rows and is
repeatable. Returned air, mass, and optional glazing are aligned at the end of
each five-minute step.

Vent forcing is bounded: `0.0` is closed, `1.0` is baseline open, and
`2.0` is the operator-approved door-assisted boosted level. A focused test
proves `2.0` produces proportionally stronger outdoor exchange. Values above
`2.0`, negative values, and non-finite forcing are rejected. No
vent-state inference was added; later out-of-fold/prior-model inference can
evaluate explicit closed-vent counterfactual rows through this API.

## Strict TDD evidence

The production module did not exist when the first tests were written.

1. RED: `pytest -q openhab/scripts/test_thermal_dynamics.py`
   - collection failed with
     `ModuleNotFoundError: No module named 'thermal_model.dynamics'`.
2. GREEN: initial synthetic 21-day recovery and shaded-gain rejection:
   - `2 passed`.
3. RED: diagnostics import failed because `fit_diagnostics` did not exist.
   GREEN after shared selection implementation:
   - `4 passed`.
4. RED: non-finite glazing poisoned the auxiliary target with
   `ValueError: fit inputs must be finite`.
   GREEN:
   - `2 passed, 4 deselected`.
5. RED: five glazing rows aborted core fitting with
   `insufficient fitted pairs for 6 coefficients`.
   GREEN after optional sparse-fit skip:
   - `1 passed, 6 deselected`.
6. RED: negative vent forcing did not raise.
   GREEN for both boosted and negative paths:
   - `2 passed, 6 deselected`.
7. RED: rank-deficient core data did not raise.
   GREEN after full-rank gate:
   - `1 passed, 8 deselected`.
8. RED: rank-deficient glazing design raised from the optional fit.
   GREEN after shared optional-rank gating:
   - `1 passed, 9 deselected`.
9. RED: open-vent validation masked an unstable 72-hour free response.
   GREEN after changing validation forcing to closed vent:
   - `1 passed, 10 deselected`.
10. RED: ordered all-negative solar gains passed validation.
    GREEN after explicit nonnegative solar checks:
    - `1 passed, 11 deselected`.
11. Final focused dynamics suite:
    - `18 passed in 0.44s`.
12. Required combined dynamics and dataset suite:
    - `41 passed in 0.48s`.
13. Fresh final full OpenHAB Python baseline after the last refactor:
    - `110 passed in 3.23s`.
14. Additional gates:
    - `python3 -m py_compile ...`: exit 0;
    - `pyflakes ...`: exit 0;
    - staged `git diff --cached --check`: exit 0;
    - no lines over 88 characters;
    - purity scan found no wall-clock, filesystem, network, database, OpenHAB,
      command, advisory, or actuation reference.

## Self-review

- Numerical conditioning: core regressions reject insufficient or
  rank-deficient designs; optional rank failure skips only glazing.
- Coefficient ordering: named tuples are the single source for bounds-to-dict
  mapping and validation; focused tests assert exact bounds and keys.
- Missing/action exclusions: exact five-minute continuity, passive endpoint
  exclusion, unknown forcing exclusion, and diagnostics are tested together.
- Free response: spectral validation plus 72-hour, zero-radiation,
  closed/baseline/boosted constant forcing; no output clamp.
- Optional observation: missing, non-finite, sparse, and rank-deficient cases
  are all tested and do not add state.
- Purity: explicit inputs only; no external reads or writes.
- Scope: two planned source/test files in the commit; no schema mutation and no
  inference, command, advisory, or actuation implementation.

## Concerns

No blocking concerns. SciPy 1.11.4 and NumPy 1.26.4 are installed in the
verified environment; this repository currently has no Python dependency
manifest in which to declare them, so no unrelated packaging file was added.


## Review correction round

The initial `bcd9a44` implementation was reopened after review identified two
blocking behaviors and one synthetic-fixture defect. The correction commit uses
the subject `fix: harden thermal dynamics stability and alignment`.

### Root causes

1. The 72-hour gate checked only finite/range output. A unit eigenvalue with a
   small bias could remain in range for 72 hours while still drifting without
   bound, and an unstable boosted transition could be hidden by validating only
   closed ventilation.
2. The auxiliary observation used the start-of-step air state, so
   `predict_step` returned end air/mass beside start glazing. The fit likewise
   used the left observation row.
3. The synthetic fixture mutated `air` before calculating the mass update, so
   its supposedly known mass equation did not match production's simultaneous
   two-state step.

### Corrected stability and ventilation contract

Effective ventilation is bounded and normalized:

- closed: `0.0`;
- baseline open: `1.0`;
- door-assisted boosted: `2.0`;
- named maximum: `MAX_VENT_FORCING = 2.0`.

Values below zero, above 2.0, or non-finite values raise `ValueError`.

For each supported level `v`, validation constructs:

```text
A(v) = [[1 - outside_exchange - mass_exchange - vent_exchange*v,
          mass_exchange],
        [air_exchange,
          1 - air_exchange]]
```

The spectral radius must be below `1 - STABILITY_TOLERANCE`, where
`STABILITY_TOLERANCE = 1e-9`. This rejects neutral modes as well as divergent
or oscillatory modes. Validation then independently performs the original
72-hour finite/range simulation at closed, baseline, and boosted forcing.
Neither gate clamps output.

### Corrected end-of-step convention

Each forcing row is the end forcing for its five-minute interval. For a
consecutive `(left, right)` training pair:

- left air and mass are the starting two-state value;
- right outdoor, radiation, action states, and action confidence are the
  forcing/weight;
- right air and mass are the state targets; and
- right glazing plus right air/outdoor/radiation/shades form the optional
  co-temporal observation regression.

`predict_step` first calculates `next_air` and `next_mass`, then evaluates
the non-recursive glazing equation from `next_air` and that same explicit end
forcing. Every simulation result row is therefore aligned at the end of the
step. Glazing remains optional and never enters either state update.

### Corrected synthetic fixture

The fixture now precomputes forcing by timestamp, saves `pre_air` and
`pre_mass`, and computes both next states exclusively from those immutable
values plus the right/end forcing. Bounded deterministic noise is added only
after the exact equation terms. The recovery test now asserts all known air,
mass, and glazing coefficients within fixed tolerances in addition to held-out
forecast MAE.

### Correction TDD evidence

Initial review RED command:

`pytest -q openhab/scripts/test_thermal_dynamics.py -k 'slow_neutral or oscillatory_boosted or bounded_at_operator or aligned_with_end or end_of_step_observation or recovers_known_mass'`

Result: `6 failed, 18 deselected`.

Exact failures:

- slow neutral bias drift did not raise;
- oscillatory boosted validation did not raise;
- `MAX_VENT_FORCING` did not exist;
- a 70 F to 80 F air step returned glazing 70 F instead of 80 F;
- removing the final glazing observation did not reduce fitted auxiliary rows;
- recovered mass `air_exchange=0.008056972...` missed the fixed
  `0.008 +/- 0.00002` bound.

Stability GREEN development evidence:

- first matrix run: `1 failed, 2 passed, 21 deselected`; the remaining test
  fixture was proven stable (spectral radius about 0.81), not an implementation
  failure;
- after correcting the fixture to an actually oscillatory in-bounds matrix:
  `3 passed, 21 deselected`.

End-of-step glazing GREEN:

- `2 passed, 22 deselected`.

Corrected pre-step synthetic recovery GREEN:

- `2 passed, 22 deselected`.

Full dynamics integration initially exposed an old second-gate fixture with a
neutral mass mode:

- `1 failed, 23 passed`, correctly rejected by the new spectral gate before
  its intended range assertion;
- after making that fixture strictly stable while retaining its out-of-range
  equilibrium: `24 passed`.

Fresh final verification:

- focused dynamics + dataset + schema:
  `51 passed in 0.65s`;
- full `openhab/scripts` Python baseline:
  `116 passed in 3.37s`;
- Pyflakes: exit 0;
- `py_compile`: exit 0;
- Python line-length check: no lines above 88;
- purity scan: no wall-clock, filesystem, network, database, OpenHAB, command,
  advisory, or actuation dependency.

### Correction self-review

- Transition matrix coefficient placement matches the two production state
  equations and is evaluated at all three supported ventilation levels.
- The named tolerance rejects unit-circle numerical ambiguity; the separate
  trajectory gate still catches stable systems whose forced equilibrium leaves
  the physical output range.
- The maximum vent forcing is enforced in every prediction/simulation path.
- Fitting, weighting, diagnostics, prediction, simulation, plan, and design all
  use the same right/end forcing convention.
- Glazing is co-temporal, optional, non-recursive, and never a third state.
- The synthetic fixture reads no post-update state during either state update.
- Existing coefficient bounds/order, square-root confidence weighting,
  passive/unknown exclusions, no-clamp behavior, purity, and no-actuation
  boundary remain intact.

No blocking concerns remain.
