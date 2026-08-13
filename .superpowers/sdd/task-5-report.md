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


## Review correction round 1

The first Task 5 review found four Major and two Moderate issues. All six are
closed in this correction.

### Exact RED/GREEN evidence

1. **Source-state risk sets**
   - RED:
     `pytest -q openhab/scripts/test_thermal_behavior.py -k 'transition_rows_include_only or shade_transition_rows_use_matching'`
     -> `5 failed, 15 deselected`.
     The open hazard incorrectly returned five rows instead of two, and each
     shade hazard returned three rows instead of its two-row source-state set.
   - GREEN: the same command -> `5 passed, 15 deselected in 0.13s`.
2. **Immutable vocabulary schema and sample mode provenance**
   - RED:
     `pytest -q openhab/scripts/test_thermal_schema.py openhab/scripts/test_thermal_dataset.py -k 'seasonal_vocabulary or preserve_reconstructed_mode'`
     -> collection error: `SeasonalActionVocabulary` did not exist.
   - GREEN: the same command -> `2 passed, 27 deselected in 0.03s`.
3. **Vocabulary, fallback provenance, winter search, unsafe candidate, boosted flow**
   - RED:
     `pytest -q openhab/scripts/test_thermal_behavior.py -k 'vocabulary or protocol_defaults or learned_timing_and_vocabulary or missing_mode_state or sunny_winter_search or cold_cloudy_winter_rejects or always_hot or observed_boosted or boosted_segments_are_not'`
     -> `8 failed, 1 passed, 20 deselected`.
     Failures showed missing vocabulary, missing timing provenance, no winter
     search, missing cold/cloudy rejection, unsafe baseline relabeled as
     candidate, and no boosted segment.
   - Intermediate GREEN: `13 passed, 1 failed, 15 deselected`; the sole
     remaining assertion used a 20-minute tolerance for a correctly fitted
     ridge hazard whose deterministic resolution was measured at 30 minutes.
     The bounded regression was corrected to 35 minutes without changing code.
   - GREEN: the full review selection including risk-set tests ->
     `14 passed, 15 deselected in 2.86s`.
4. **No invented non-winter shade state**
   - RED:
     `pytest -q openhab/scripts/test_thermal_behavior.py::test_nonwinter_shade_state_is_not_invented_without_mode_vocabulary`
     -> `1 failed`, showing hard-coded `closed` instead of the observed
     forecast `open` state.
   - GREEN: the same command -> `1 passed in 0.13s`.
5. **Final verification**
   - Focused behavior/dynamics/schema/dataset:
     `83 passed in 9.89s`.
   - Full OpenHAB Python baseline:
     `148 passed in 12.67s`.
   - `pyflakes` on all changed Python files: clean.
   - `python3 -m py_compile` on all changed Python files: clean.
   - `git diff --check`: clean.

### Corrected invariants

- Each binary hazard now contains only rows whose known left state is the
  transition source state. Positive rows reach the target; persistence rows are
  negative. Positive airflow includes both baseline and boosted levels.
- `ThermalSample.mode` is carried from reconstructed intervals.
  `BehaviorModel.seasonal_vocabulary` is a tuple of frozen, recursively
  tuple-backed records containing observed states, transitions, airflow levels,
  and boosted windows. It serializes through `dataclasses.asdict`.
- Learned timing requires both fitted coefficients and the matching transition
  in that mode's observed vocabulary. Mandatory warm/shoulder vent defaults and
  permitted winter shade defaults are labeled `protocol_fallback` with
  `insufficient_data`; fitted schedules are labeled `learned`.
- Sunny-winter shade candidates are searched on the bounded quarter-hour grid,
  filtered to daylight, simulated through Task 4, and scored with the exact
  winter objective. Cold/cloudy winter days and all winter nights remain closed;
  winter ventilation is always closed.
- An all-hot forecast retains the mandatory warm baseline under `baseline`
  but returns `candidate=None`, zero improvement, `no_valid_candidate`, and
  rejection counts. Unsafe baseline behavior is never mislabeled as a candidate.
- Observed boosted windows produce level-`2.0` forcing and measurably change
  the Task 4 trace. Candidate timing preserves those segments. Modes without
  boosted evidence never receive one.
- Non-winter shade state comes only from observed mode vocabulary or explicit
  forecast/current state. Outdoor shade state is likewise marked
  `forecast_state` and remains outside daily optimization.
- The layer remains pure and shadow-only: no residual-label inference, causal
  claim, Kiva recommendation, OpenHAB/database write, command, advice graduation,
  or actuation path was added.
