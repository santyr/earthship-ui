# Task 5 report: learned household transitions and bounded schedules

## Status

Implemented and verified the shadow-only household behavior model and bounded
schedule search in `openhab/scripts/thermal_model/behavior.py`, with deterministic
coverage in `openhab/scripts/test_thermal_behavior.py`.

## TDD evidence

1. RED: `pytest -q openhab/scripts/test_thermal_behavior.py`
   - Collection failed with `ModuleNotFoundError: thermal_model.behavior`.
2. Initial GREEN: focused behavior+dynamics run reached 36 passing tests and
   exposed two schedule-timing failures.
3. Root-cause regression cycle:
   - Transition classification originally omitted known non-transition intervals,
     allowing a one-sided hazard to extrapolate beyond observed transition time.
   - Corrected labels include every consecutive known pair and mark positive only
     for the requested state change.
   - Self-review found that UTC-normalized samples were feeding UTC clock features.
     A new local-time test failed at `sin_time=-1.0` for noon MDT, then passed after
     all minute consumers were routed through `America/Denver`.
   - A broad logistic hazard's pointwise maximum locked onto sunrise. The
     probability-weighted expected minute recovered the confirmed transition and
     became the deterministic schedule summary.
4. Final GREEN:
   - `pytest -q openhab/scripts/test_thermal_behavior.py openhab/scripts/test_thermal_dynamics.py`
     -> `39 passed in 7.49s`.
   - `pytest -q openhab/scripts`
     -> `131 passed in 10.21s`.

## Implemented behavior fit

- Fixed feature order exactly matches the plan, with cyclic local time/year,
  raw physical temperature differences, normalized radiation, solar elevation,
  and daylight.
- Fits all six requested transitions using weighted ridge logistic loss through
  `scipy.optimize.minimize(method="L-BFGS-B")`.
- Uses `action_confidence` as the likelihood weight and `lambda=1.0` only on
  non-intercept coefficients.
- Requires at least ten positive confirmed-or-reconstructed transitions and both
  classes. Otherwise stores an empty coefficient tuple and returns the explicit
  `insufficient_data` sentinel.
- Uses the left sample for every feature and the right sample only for the label
  and label confidence. Unknown states are skipped. Confidence below historical
  reconstruction (`0.35`) is excluded, so same-fold `model_inferred` labels do not
  contaminate Task 5.
- Optimizer success and finite coefficients are mandatory; failure rejects the fit.

## Implemented schedule protocol

- Warm baseline always contains an overnight vent window. Search changes only
  timing/duration on 15-minute boundaries within plus/minus two hours.
- Candidate opening requires outdoor air at least 1 F below predicted baseline
  hallway air for the first full hour; the entire open window must remain cooler.
- Effective airflow vocabulary is explicit: closed `0`, baseline `1`, boosted `2`.
  Task 5 emits baseline vent flow and preserves boosted representation without
  inferring historical door-opening labels.
- Winter ventilation is always closed. Cold/cloudy winter shades stay closed;
  sunny winter daytime may open for mass charging and closes when useful sun ends,
  with all winter nights closed.
- Outdoor shades are copied from seasonal configuration and never varied by the
  candidate generator.
- Every surviving candidate is evaluated through Task 4 `simulate()` with the
  exact seasonal objectives. No RC equation is duplicated.
- A candidate replaces baseline only with at least `0.25` modeled score improvement,
  except that an unsafe baseline may only be replaced by a physically valid bounded
  candidate.
- Results always report learned baseline, selected candidate, modeled comparison,
  and deterministic rejection counts. Wording is explicitly a modeled
  counterfactual/simulation comparison, never a causal claim.

## Boundary review

- Pure functions only; no OpenHAB, PostgreSQL, filesystem, network, or command writes.
- No Kiva path, recommendations, commands, advice graduation, or actuation.
- Deterministic sort order and candidate tie-breaking.
- Task 5 does not create model-inferred historical labels; any future residual
  inference remains a separate low-confidence, abstaining, precedence-bounded,
  strictly out-of-fold/prior-model task.

## Concerns

No blocking concerns. The behavior API intentionally represents an insufficient
transition with empty coefficients plus `insufficient_data`; later artifact/UI work
should preserve that abstention rather than manufacturing a fallback probability.
