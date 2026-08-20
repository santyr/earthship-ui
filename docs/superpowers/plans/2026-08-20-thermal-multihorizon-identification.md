# Earthship Thermal Multihorizon Identification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the RC model's five-minute-only identification objective with a bounded, deterministic multihorizon refinement that can pass the unchanged held-out 24-hour persistence gate without changing the two-state physics or any public automation surface.

**Architecture:** Keep the current bounded ordered-solar least-squares fit as the only initializer. Select strictly training-only daily rollout origins at 5 minutes, 1 hour, 6 hours, 12 hours, and 24 hours, then jointly refine the same seven air and five mass coefficients with analytic forward-sensitivity gradients. Carry exact optimizer evidence into a private v3 model artifact; retain the v1 backtest and shadow contracts and stop before Gate B.

**Tech Stack:** Python 3.12, NumPy 1.26, SciPy 1.11 SLSQP, pytest, PostgreSQL 16 journal, OpenHAB 5.2 JDBC persistence, Node.js/Vitest, Vite, Playwright, user-level systemd.

## Global Constraints

- Authoritative spec: `docs/superpowers/specs/2026-08-20-thermal-multihorizon-identification-design.md` at commit `eed8f9cb5d3c408d614466e59466dd3cdef0c1cf` or later.
- Preserve exactly two propagated states: hallway air and latent deep-mass charge; glazing remains a non-recursive observation.
- Preserve `AIR_NAMES`, `MASS_NAMES`, their current bounds, nonnegative ordered solar gains, explicit vent forcing, strict transition stability, output range, and 72-hour physics validation.
- Identification horizons are exactly `(5, 60, 360, 720, 1440)` minutes.
- Select at most one eligible origin per local day and at most 64 origins per horizon using sorted indices `floor(i * (count - 1) / 63)` for `i=0..63`, including first and last.
- Every rollout is consecutive, finite, action-known, mode-known, passive-fit-allowed, Kiva-free, gap-free, and inactive-forcing-safe.
- Rollout confidence is the minimum aggregate action confidence over its complete prefix.
- The objective is the equal sum of air and mass confidence-weighted mean squared endpoint errors for all five horizons.
- Use the current constrained fit as the sole start, SLSQP `ftol=1e-10`, `maxiter=500`, no random restart, and analytic forward-sensitivity gradients.
- Reject objective increases above `1e-9 * max(1, initial_objective)` and reject every non-finite, unsuccessful, bound-violating, solar-order-violating, unstable, or out-of-range result.
- Preserve the v2 `mass.outside_exchange` state equation and bounds. Advance only the private model artifact to `earthship-thermal-model/v3`; keep `earthship-thermal-backtest/v1` and `earthship-thermal-shadow/v1` unchanged.
- Do not add an OpenHAB Item, state write, rule, advisory write, systemd mutation, timer, or actuator authority during implementation.
- Gate A may install reviewed code and produce private artifacts only. Stop before Gate B even if promotion succeeds.

---

### Task 1: Deterministic training-only rollout selection

**Files:**
- Modify: `openhab/scripts/thermal_model/dynamics.py`
- Modify: `openhab/scripts/test_thermal_dynamics.py`

**Interfaces:**
- Consumes: `ThermalSample`, `STEP`, `SITE_TIMEZONE`, `evaluation_forcing_features(row)`.
- Produces: `IDENTIFICATION_HORIZON_STEPS`, `MAX_ORIGINS_PER_HORIZON`, frozen `RolloutEndpoint`, `_select_multihorizon_endpoints(samples, inactive_features=()) -> dict[int, tuple[RolloutEndpoint, ...]]`, and `_identification_origin_counts(endpoints) -> dict[str, int]`.

- [ ] **Step 1: Write RED tests for daily selection and the 64-origin bound**

Add tests using `_sample()` and the existing `synthetic_2r2c_days()` fixture:

```python
def test_multihorizon_selector_is_daily_bounded_and_spans_training_range():
    training, _ = synthetic_2r2c_days(days=90, seed=101)
    training = [replace(row, mode="warm") for row in training]
    endpoints = dynamics._select_multihorizon_endpoints(training)

    assert tuple(endpoints) == (1, 12, 72, 144, 288)
    for steps, rows in endpoints.items():
        assert len(rows) <= 64
        assert len({row.origin.at.astimezone(dynamics.SITE_TIMEZONE).date() for row in rows}) == len(rows)
        assert all(len(row.forcings) == steps for row in rows)
        assert rows[0].origin.at < rows[-1].origin.at
    eligible_24h = dynamics._eligible_daily_endpoints(training, 288, ())
    assert endpoints[288][0] == eligible_24h[0]
    assert endpoints[288][-1] == eligible_24h[-1]


def test_uniform_origin_indices_are_exact_and_include_boundaries():
    assert dynamics._uniform_origin_indices(5, 64) == (0, 1, 2, 3, 4)
    indices = dynamics._uniform_origin_indices(100, 64)
    assert len(indices) == 64
    assert indices[0] == 0
    assert indices[-1] == 99
    assert indices == tuple((index * 99) // 63 for index in range(64))
```

- [ ] **Step 2: Run the selector tests and verify RED**

Run:

```bash
pytest -q \
  openhab/scripts/test_thermal_dynamics.py::test_multihorizon_selector_is_daily_bounded_and_spans_training_range \
  openhab/scripts/test_thermal_dynamics.py::test_uniform_origin_indices_are_exact_and_include_boundaries
```

Expected: collection or attribute failures for the absent selector interfaces.

- [ ] **Step 3: Implement the exact rollout data types and uniform bound**

Add to `dynamics.py`:

```python
from zoneinfo import ZoneInfo

SITE_TIMEZONE = ZoneInfo("America/Denver")
IDENTIFICATION_HORIZON_STEPS = (1, 12, 72, 144, 288)
MAX_ORIGINS_PER_HORIZON = 64


@dataclass(frozen=True)
class RolloutEndpoint:
    origin: object
    forcings: tuple
    target: object
    confidence: float


def _uniform_origin_indices(count, limit=MAX_ORIGINS_PER_HORIZON):
    if count < 0 or limit < 2:
        raise ValueError("origin count and limit are invalid")
    if count <= limit:
        return tuple(range(count))
    return tuple(index * (count - 1) // (limit - 1) for index in range(limit))
```

Implement `_eligible_daily_endpoints()` so it scans UTC-sorted unique samples,
builds an endpoint only when the complete prefix satisfies every Global
Constraint, keeps the longest eligible future per local day, breaks equal-length
ties by earliest UTC origin, and returns canonical chronological order. Implement
`_select_multihorizon_endpoints()` by selecting each exact horizon independently
and applying `_uniform_origin_indices()`.

- [ ] **Step 4: Write RED exclusion and confidence tests**

```python
@pytest.mark.parametrize("mutation", ("gap", "unknown_action", "unknown_mode", "kiva"))
def test_multihorizon_selector_rejects_invalid_interior_rows(mutation):
    training, _ = synthetic_2r2c_days(days=4, seed=103)
    training = [replace(row, mode="warm") for row in training]
    damaged = list(training)
    index = 150
    invalid_at = damaged[index].at
    if mutation == "gap":
        damaged.pop(index)
    elif mutation == "unknown_action":
        damaged[index] = replace(damaged[index], vent_open=None)
    elif mutation == "unknown_mode":
        damaged[index] = replace(damaged[index], mode=None)
    else:
        damaged[index] = replace(damaged[index], passive_fit_allowed=False)

    endpoints = dynamics._select_multihorizon_endpoints(damaged)
    assert all(
        not (endpoint.origin.at < invalid_at <= endpoint.target.at)
        for rows in endpoints.values()
        for endpoint in rows
    )


def test_rollout_confidence_is_minimum_over_complete_prefix():
    training, _ = synthetic_2r2c_days(days=4, seed=107)
    training = [replace(row, mode="warm") for row in training]
    training[10] = replace(training[10], action_confidence=0.35)
    endpoint = next(row for row in dynamics._eligible_daily_endpoints(training, 12, ()) if row.origin.at < training[10].at <= row.target.at)
    assert endpoint.confidence == 0.35


def test_inactive_forcing_activation_excludes_only_affected_horizon():
    training, _ = synthetic_2r2c_days(days=4, seed=109)
    training = [replace(row, mode="warm") for row in training]
    activation = training[20].at
    training = [replace(row, outdoor_shade_present=float(row.at >= activation)) for row in training]
    endpoints = dynamics._select_multihorizon_endpoints(training, ("solar_outdoor",))
    assert all(all(dynamics.evaluation_forcing_features(row)["solar_outdoor"] == 0.0 for row in endpoint.forcings) for rows in endpoints.values() for endpoint in rows)
```

- [ ] **Step 5: Run all Task 1 tests and verify GREEN**

Run: `pytest -q openhab/scripts/test_thermal_dynamics.py -k 'multihorizon_selector or uniform_origin or rollout_confidence or inactive_forcing'`

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add openhab/scripts/thermal_model/dynamics.py openhab/scripts/test_thermal_dynamics.py
git commit -m "feat: select bounded thermal rollout evidence"
```

---

### Task 2: Analytic multihorizon objective and constrained refinement

**Files:**
- Modify: `openhab/scripts/thermal_model/dynamics.py`
- Modify: `openhab/scripts/test_thermal_dynamics.py`

**Interfaces:**
- Consumes: Task 1 endpoint groups plus existing `_fit()`, coefficient names/bounds, `DynamicsModel`, `simulate()`, and `validate_physics()`.
- Produces: frozen `MultihorizonEvidence`, frozen `MultihorizonDynamicsFit`, `_multihorizon_objective_and_gradient(vector, endpoints) -> tuple[float, np.ndarray]`, `fit_dynamics_with_evidence(samples) -> MultihorizonDynamicsFit`, unchanged `fit_dynamics(samples) -> DynamicsModel`, and `fit_dynamics_for_evaluation(samples) -> EvaluationDynamicsFit` with evidence.

- [ ] **Step 1: Write the analytic-gradient RED test**

```python
def test_multihorizon_gradient_matches_centered_difference():
    training, _ = synthetic_2r2c_days(days=8, seed=113)
    training = [replace(row, mode="warm") for row in training]
    initial = dynamics._fit_five_minute_dynamics(training, False)
    vector = dynamics._coefficient_vector(initial)
    endpoints = dynamics._select_multihorizon_endpoints(training)
    _, analytic = dynamics._multihorizon_objective_and_gradient(vector, endpoints)
    numeric = []
    epsilon = 1e-7
    for index in range(len(vector)):
        plus = vector.copy()
        minus = vector.copy()
        plus[index] += epsilon
        minus[index] -= epsilon
        plus_loss, _ = dynamics._multihorizon_objective_and_gradient(plus, endpoints)
        minus_loss, _ = dynamics._multihorizon_objective_and_gradient(minus, endpoints)
        numeric.append((plus_loss - minus_loss) / (2.0 * epsilon))
    assert np.asarray(analytic) == pytest.approx(np.asarray(numeric), rel=2e-5, abs=2e-6)
```

- [ ] **Step 2: Run the gradient test and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_dynamics.py::test_multihorizon_gradient_matches_centered_difference`

Expected: failure for absent objective interfaces.

- [ ] **Step 3: Implement coefficient packing and forward sensitivities**

Use the exact vector order `AIR_NAMES + MASS_NAMES`. At every simulated step,
propagate state sensitivity with:

```python
state_jacobian = np.asarray((
    (
        1.0 - air["outside_exchange"] - air["mass_exchange"] - air["vent_exchange"] * vent,
        air["mass_exchange"],
    ),
    (mass["air_exchange"], 1.0 - mass["air_exchange"] - mass["outside_exchange"]),
))
direct = np.zeros((2, len(AIR_NAMES) + len(MASS_NAMES)))
direct[0, :] = (
    outdoor - state[0],
    state[1] - state[0],
    solar[0], solar[1], solar[2],
    vent * (outdoor - state[0]),
    1.0,
    0.0, 0.0, 0.0, 0.0, 0.0,
)
direct[1, len(AIR_NAMES):] = (
    state[0] - state[1], outdoor - state[1], solar[0], solar[1], solar[2]
)
next_sensitivity = state_jacobian @ sensitivity + direct
```

For each state/horizon group, accumulate `confidence * error**2 / count` and
`2 * confidence * error * sensitivity / count`. Reject missing groups and every
non-finite state, sensitivity, residual, loss, or gradient.

- [ ] **Step 4: Write the synthetic drift and optimizer-contract RED tests**

Add this deterministic helper; it preserves the observer across the train/holdout boundary and uses the final two days as untouched holdout:

```python
def synthetic_latent_observer_days(days, seed):
    physical_training, physical_holdout = synthetic_2r2c_days(days=days, seed=seed)
    physical = physical_training + physical_holdout
    alpha = 1.0 - math.exp(-5.0 / 120.0)
    latent = physical[0].mass_f
    observed = []
    for row in physical:
        north_wall = row.mass_f
        latent += alpha * (north_wall - latent)
        observed.append(
            replace(row, mass_f=latent, north_wall_f=north_wall, mode="warm")
        )
    split = (days - 2) * 288
    return observed[:split], observed[split:]



def test_multihorizon_refinement_reduces_latent_observer_open_loop_drift():
    training, holdout = synthetic_latent_observer_days(days=28, seed=127)
    initial = dynamics._fit_five_minute_dynamics(training, False)
    refined = fit_dynamics_with_evidence(training)
    initial_prediction = simulate(initial, holdout[0], holdout[1:289])[-1]
    refined_prediction = simulate(refined.dynamics, holdout[0], holdout[1:289])[-1]
    initial_error = abs(initial_prediction["air_f"] - holdout[288].air_f)
    refined_error = abs(refined_prediction["air_f"] - holdout[288].air_f)
    assert refined_error < initial_error
    assert refined.evidence.final_objective <= refined.evidence.initial_objective
    validate_physics(refined.dynamics)


def test_multihorizon_fit_is_byte_deterministic():
    training, _ = synthetic_latent_observer_days(days=28, seed=131)
    first = fit_dynamics_with_evidence(training)
    second = fit_dynamics_with_evidence(training)
    assert first == second


@pytest.mark.parametrize("probe", ("unsuccessful", "nonfinite"))
def test_multihorizon_optimizer_failures_refuse(monkeypatch, probe):
    training, _ = synthetic_latent_observer_days(days=28, seed=137)

    def failed_minimize(fun, initial, **kwargs):
        del fun, kwargs
        return SimpleNamespace(success=False, x=np.asarray(initial), message="injected failure")

    def nonfinite_minimize(fun, initial, **kwargs):
        del fun, kwargs
        return SimpleNamespace(success=True, x=np.full_like(np.asarray(initial), np.nan), message="injected nonfinite result")

    monkeypatch.setattr(
        dynamics,
        "minimize",
        failed_minimize if probe == "unsuccessful" else nonfinite_minimize,
    )
    with pytest.raises(ValueError, match="multihorizon"):
        fit_dynamics_with_evidence(training)
```

- [ ] **Step 5: Run the new fit tests and verify RED**

Run: `pytest -q openhab/scripts/test_thermal_dynamics.py -k 'multihorizon_refinement or multihorizon_fit_is_byte or multihorizon_optimizer'`

Expected: failures for absent refinement and evidence types.

- [ ] **Step 6: Implement the constrained second-stage optimizer**

Add exact evidence types:

```python
@dataclass(frozen=True)
class MultihorizonEvidence:
    origin_counts: tuple[tuple[str, int], ...]
    initial_objective: float
    final_objective: float


@dataclass(frozen=True)
class MultihorizonDynamicsFit:
    dynamics: DynamicsModel
    inactive_forcing_features: tuple[str, ...]
    evidence: MultihorizonEvidence
```

Rename the present `_fit_dynamics()` initializer to
`_fit_five_minute_dynamics()` without changing its equations. Implement
`_refine_multihorizon(initial, endpoints, inactive_features)` with one SLSQP
call, active-vector projection for fold-only inactive features, the existing
bounds, and ordered-solar constraints for both air and mass. Reconstruct the
full model with unchanged glazing coefficients, apply the objective-regression
tolerance, then call `validate_physics()`.

`fit_dynamics_with_evidence()` returns the full result. `fit_dynamics()` returns
only `.dynamics`. `fit_dynamics_for_evaluation()` returns its existing wrapper
with the new evidence field so evaluation consumers remain explicit.

- [ ] **Step 7: Add refusal tests for insufficient horizons and final physics**

```python
def test_multihorizon_fit_requires_two_origins_at_every_horizon():
    training, _ = synthetic_2r2c_days(days=2, seed=139)
    with pytest.raises(ValueError, match="insufficient multihorizon.*1440"):
        fit_dynamics_with_evidence(training)


def test_multihorizon_fit_rejects_final_unstable_model(monkeypatch):
    training, _ = synthetic_latent_observer_days(days=28, seed=149)
    original = dynamics.validate_physics
    calls = 0

    def reject_final(model):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("transition eigenvalue reaches the unit circle")
        return original(model)

    monkeypatch.setattr(dynamics, "validate_physics", reject_final)
    with pytest.raises(ValueError, match="unit circle"):
        fit_dynamics_with_evidence(training)
```

- [ ] **Step 8: Run the complete dynamics suite**

Run: `pytest -q openhab/scripts/test_thermal_dynamics.py`

Expected: all tests pass with no warning or collection error.

- [ ] **Step 9: Commit Task 2**

```bash
git add openhab/scripts/thermal_model/dynamics.py openhab/scripts/test_thermal_dynamics.py
git commit -m "fix: fit thermal dynamics across forecast horizons"
```

---

### Task 3: Chronology, artifact v3 evidence, and pipeline wiring

**Files:**
- Modify: `openhab/scripts/thermal_model/artifacts.py`
- Modify: `openhab/scripts/thermal_model/pipeline.py`
- Modify: `openhab/scripts/test_thermal_artifacts.py`
- Modify: `openhab/scripts/test_thermal_pipeline.py`
- Modify: `openhab/scripts/test_thermal_evaluation.py`

**Interfaces:**
- Consumes: `MultihorizonDynamicsFit` and `MultihorizonEvidence` from Task 2.
- Produces: `MODEL_SCHEMA = "earthship-thermal-model/v3"`, exact `MULTIHORIZON_CONTRACT`, exact multihorizon fit diagnostics, and a `run_training()` artifact whose dynamics and evidence come from the same fit result.

- [ ] **Step 1: Write RED tests for v3 and exact evidence**

Update `valid_artifact()` to expect v3, then add:

```python
def test_model_artifact_v3_requires_exact_multihorizon_contract(tmp_path):
    artifact = valid_artifact()
    ArtifactRegistry(tmp_path).save_candidate(artifact)
    for field in ("multihorizon_origin_counts", "multihorizon_initial_objective", "multihorizon_final_objective"):
        broken = deepcopy(artifact.data_manifest)
        broken["fit_diagnostics"].pop(field)
        with pytest.raises(ArtifactValidationError, match="fit diagnostics"):
            ArtifactRegistry(tmp_path / field).save_candidate(replace(artifact, data_manifest=broken))


def artifact_with_multihorizon_mutation(mutation):
    artifact = valid_artifact()
    manifest = deepcopy(artifact.data_manifest)
    diagnostics = manifest["fit_diagnostics"]
    if mutation == "extra_horizon":
        diagnostics["multihorizon_origin_counts"]["999"] = 2
    elif mutation == "boolean_count":
        diagnostics["multihorizon_origin_counts"]["5"] = True
    elif mutation == "too_few_24h":
        diagnostics["multihorizon_origin_counts"]["1440"] = 1
    elif mutation == "objective_increase":
        diagnostics["multihorizon_final_objective"] = (
            diagnostics["multihorizon_initial_objective"] + 1.0
        )
    else:
        diagnostics["multihorizon_final_objective"] = math.inf
    return replace(artifact, data_manifest=manifest)


@pytest.mark.parametrize("mutation", ("extra_horizon", "boolean_count", "too_few_24h", "objective_increase", "nonfinite"))
def test_multihorizon_evidence_semantics_fail_closed(tmp_path, mutation):
    artifact = artifact_with_multihorizon_mutation(mutation)
    with pytest.raises(ArtifactValidationError, match="multihorizon|objective"):
        ArtifactRegistry(tmp_path).save_candidate(artifact)


def test_v2_private_model_artifact_is_rejected(tmp_path):
    with pytest.raises(ArtifactValidationError, match="earthship-thermal-model/v3"):
        ArtifactRegistry(tmp_path).save_candidate(valid_artifact(schema="earthship-thermal-model/v2"))
```

- [ ] **Step 2: Run artifact RED tests**

Run: `pytest -q openhab/scripts/test_thermal_artifacts.py -k 'multihorizon or v2_private'`

Expected: failures because v2 and the old exact diagnostic/constraint sets remain active.

- [ ] **Step 3: Implement exact static and run evidence validation**

Set `MODEL_SCHEMA` to v3. Add this exact static value to both
`pipeline._constraints_manifest()` and `artifacts._expected_constraints()`:

```python
MULTIHORIZON_CONTRACT = {
    "horizons_minutes": [5, 60, 360, 720, 1440],
    "daily_origin_selector": "longest_valid_future_then_earliest_utc",
    "max_origins_per_horizon": 64,
    "bounded_index_rule": "floor(i*(count-1)/63), i=0..63",
    "confidence_rule": "minimum_aggregate_action_confidence_over_prefix",
    "objective": "equal_air_mass_confidence_weighted_group_mse",
    "optimizer": {
        "method": "SLSQP",
        "ftol": 1e-10,
        "maxiter": 500,
        "random_restarts": 0,
        "gradient": "analytic_forward_sensitivity",
        "objective_regression_relative_tolerance": 1e-9,
    },
}
```

Extend `_DIAGNOSTIC_KEYS` with the three exact fields. Validate origin-count
keys as `{"5", "60", "360", "720", "1440"}`, exact non-boolean integers,
and counts from 2 through 64. Validate both objective values as finite and
nonnegative, with final no larger than the specified tolerance.

- [ ] **Step 4: Write RED pipeline identity and leakage tests**

```python
def multihorizon_fit_result():
    return MultihorizonDynamicsFit(
        dynamics=stable_dynamics(),
        inactive_forcing_features=(),
        evidence=MultihorizonEvidence(
            origin_counts=(("5", 64), ("60", 64), ("360", 64), ("720", 64), ("1440", 32)),
            initial_objective=3.0,
            final_objective=2.0,
        ),
    )


def test_training_uses_one_dynamics_result_for_model_and_manifest():
    fit = multihorizon_fit_result()
    dependencies = orchestration_dependencies([], eligible=True)
    dependencies["dynamics_fitter"] = lambda rows: fit
    result = run_training(start=NOW - timedelta(days=400), end=NOW, registry=RecordingRegistry(), journal=FakeJournal([]), **dependencies)
    assert result.artifact.dynamics is fit.dynamics
    diagnostics = result.artifact.data_manifest["fit_diagnostics"]
    assert diagnostics["multihorizon_origin_counts"] == dict(fit.evidence.origin_counts)
    assert diagnostics["multihorizon_initial_objective"] == fit.evidence.initial_objective
    assert diagnostics["multihorizon_final_objective"] == fit.evidence.final_objective


def test_walk_forward_fit_cannot_observe_held_out_target_or_action_mutation():
    samples = samples_45_days()
    first_origin = samples[14 * 24 * 12].at
    baseline_seen = []
    mutated_seen = []

    def fingerprint(train):
        return tuple(
            (row.at, row.air_f, row.mass_f, row.vent_open,
             row.indoor_shade_closed, row.outdoor_shade_present)
            for row in train
        )

    walk_forward_evaluate(
        samples,
        fit=lambda train: baseline_seen.append(fingerprint(train)) or fixed_model(),
    )
    mutated = [
        replace(row, air_f=row.air_f + 10.0, vent_open=1.0)
        if row.at >= first_origin else row
        for row in samples
    ]
    walk_forward_evaluate(
        mutated,
        fit=lambda train: mutated_seen.append(fingerprint(train)) or fixed_model(),
    )
    assert baseline_seen[0] == mutated_seen[0]
```

- [ ] **Step 5: Run pipeline/evaluation RED tests**

Run:

```bash
pytest -q \
  openhab/scripts/test_thermal_pipeline.py -k multihorizon \
  openhab/scripts/test_thermal_evaluation.py -k multihorizon
```

Expected: pipeline failure because it currently expects a bare `DynamicsModel`, plus absent chronology test helpers.

- [ ] **Step 6: Wire the fit result through training only once**

Change `run_training()` default `dynamics_fitter` to
`fit_dynamics_with_evidence`. Normalize only the exact Task 2 result:

```python
fitted_dynamics = dynamics_fitter(samples)
if not isinstance(fitted_dynamics, MultihorizonDynamicsFit):
    raise ValueError("training dynamics fitter must return multihorizon evidence")
dynamics = fitted_dynamics.dynamics
manifest = _complete_manifest(samples, events, modes, fitted_dynamics.evidence)
```

Extend `_complete_manifest()` by merging the three evidence values into the
existing selection diagnostics. Keep `run_backtest()` on
`fit_dynamics_for_evaluation`; fold-local evidence remains private to the fit
and does not alter the v1 report shape. Ensure every fitter receives only the
existing `train = rows where row.at < origin.at` slice.

- [ ] **Step 7: Update all canonical fixtures and run the focused suites**

Run:

```bash
pytest -q \
  openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_pipeline.py \
  openhab/scripts/test_thermal_evaluation.py \
  openhab/scripts/test_thermal_dynamics.py
```

Expected: all focused tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add \
  openhab/scripts/thermal_model/artifacts.py \
  openhab/scripts/thermal_model/pipeline.py \
  openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_pipeline.py \
  openhab/scripts/test_thermal_evaluation.py
git commit -m "feat: persist exact multihorizon fit evidence"
```

---

### Task 4: Runbook, authority scan, and repository acceptance

**Files:**
- Modify: `docs/operations/thermal-model-shadow.md`
- Modify: `tests/deployment-service.test.js`

**Interfaces:**
- Consumes: private v3 artifact and unchanged v1 backtest/shadow contracts.
- Produces: reviewed deployment evidence commands that display the exact multihorizon contract and still stop before Gate B.

- [ ] **Step 1: Write the runbook/static RED assertion**

Add a Vitest assertion that the Gate A artifact review names
`earthship-thermal-model/v3`, reads all five origin counts, compares final and
initial objectives, and still places the Gate B heading after the explicit stop.

```javascript
expect(runbook).toContain('earthship-thermal-model/v3');
expect(runbook).toContain('multihorizon_origin_counts');
expect(runbook).toContain('multihorizon_initial_objective');
expect(runbook).toContain('multihorizon_final_objective');
expect(runbook.indexOf('Stop and present this evidence before Gate B')).toBeLessThan(runbook.indexOf('## 5. Gate B'));
```

- [ ] **Step 2: Run the static test and verify RED**

Run: `npm test -- --run tests/deployment-service.test.js`

Expected: failure for absent v3/multihorizon runbook evidence.

- [ ] **Step 3: Update only the Gate A evidence readback**

Extend the existing accepted-artifact `jq` projection with:

```jq
select(.schema == "earthship-thermal-model/v3")
| .data_manifest.fit_diagnostics as $fit
| select(($fit.multihorizon_origin_counts | keys | sort) == ["1440","360","5","60","720"])
| select(all($fit.multihorizon_origin_counts[]; . >= 2 and . <= 64))
| select($fit.multihorizon_final_objective <= ($fit.multihorizon_initial_objective + (1e-9 * ([1,$fit.multihorizon_initial_objective] | max))))
```

Do not alter any Gate B/C command, Item manifest, service unit, timer, or
authority statement.

- [ ] **Step 4: Run fresh repository verification**

Run every command and retain exact totals:

```bash
pytest -q openhab/scripts/test_forecast_intel.py openhab/scripts/test_thermal_*.py
npm test -- --run
npm run build
npx playwright test
pyflakes openhab/scripts/thermal_intel.py openhab/scripts/thermal_model
python3 -m py_compile openhab/scripts/thermal_intel.py openhab/scripts/thermal_model/*.py
npm test -- --run tests/deployment-service.test.js
systemd-analyze verify deploy/thermal-model-train.service deploy/thermal-model-train.timer deploy/thermal-model-shadow.service deploy/thermal-model-shadow.timer
git diff --check
```

- [ ] **Step 5: Run closed authority and schema scans**

```bash
rg -n "Thermal_Advisory|sendCommand|postUpdate|/rest/items/.*/state|systemctl.*(enable|start)|earthship-thermal-shadow/v2" \
  openhab/scripts/thermal_model openhab/scripts/thermal_intel.py
git diff --name-only HEAD~3..HEAD
git status --short
```

Expected: no new advisory/actuator/systemd authority, no shadow-v2 string, and
only planned implementation/test/runbook paths.

- [ ] **Step 6: Commit the runbook evidence update**

```bash
git add docs/operations/thermal-model-shadow.md tests/deployment-service.test.js
git commit -m "docs: review multihorizon Gate A evidence"
```

- [ ] **Step 7: Request code review, fix findings test-first, and reverify**

Invoke `superpowers:requesting-code-review`, review the full implementation diff
against the approved spec, and use `superpowers:receiving-code-review` before
any correction. Every accepted correction gets a failing regression test before
production changes. Repeat Step 4 after the final correction.

- [ ] **Step 8: Push and prove exact upstream parity**

```bash
git push origin main
git fetch --prune origin
git rev-list --left-right --count origin/main...HEAD
git rev-parse HEAD
git rev-parse origin/main
```

Expected: `0 0` and identical hashes.

---

### Task 5: Attended private Gate A rerun and stop boundary

**Files:**
- No repository file changes expected.
- Private receipts under `/home/sat/.local/state/thermal-intel/deploy-receipts/<ATTENDED-ID>/`.
- Private artifacts under `/home/sat/.local/state/thermal-intel/models/` and `/home/sat/.local/state/thermal-intel/review/`.

**Interfaces:**
- Consumes: reviewed/pushed runtime manifest, existing exact PostgreSQL schema, protected runtime DSN, OpenHAB JDBC history, and action/mode journal.
- Produces: either a fail-closed private refusal packet or a promoted v3 accepted artifact plus valid local v1 shadow. It never crosses Gate B.

- [ ] **Step 1: Re-run the runbook preliminary read-only inventory and Gate A file preparation**

Follow `docs/operations/thermal-model-shadow.md` sections 1 through 3 using a
new explicit `ATTENDED-ID`. Reconfirm `Thermal_Model_JSON` is absent and
`python3 scripts/thermal-systemd-state.py first-install` prints `first-install`.
Prepare a new 0700 file receipt, capture exact absent/present backups, install
the reviewed runtime atomically, and verify the runtime-manifest SHA-256 equals
the reviewed repository revision.

- [ ] **Step 2: Re-run exact PostgreSQL authority/schema audit**

In the attended shell, load the protected runtime DSN without printing it and
run:

```bash
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py schema-audit \
  | jq -e 'select(.schema == "thermal_intel" and .status == "exact" and .fingerprint == "786e9b7bf3ca5587f08bcdcd960239a88bf887a8b31c4ea5eddcbc808c496efb")'
```

Stop immediately on any fingerprint, role, owner, ACL, trigger, or connection
failure.

- [ ] **Step 3: Run private 400-day train, independent backtest, and local shadow**

```bash
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py train
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py backtest
/usr/bin/python3 /home/sat/openhab/scripts/thermal_intel.py shadow \
  --output /home/sat/.local/state/thermal-intel/review/shadow-local.json
```

Do not use `--publish`.

- [ ] **Step 4: Evaluate the unchanged promotion gate**

```bash
jq -e 'select(.schema == "earthship-thermal-model/v3")
  | select(.metrics.promotion.eligible == true)
  | select(.metrics.promotion.gates.air_24h_beats_persistence == true)
  | {created_at,trained_from,trained_through,code_revision,
     promotion:.metrics.promotion,
     model_24h:.metrics.overall.model.air["24"],
     persistence_24h:.metrics.overall.persistence.air["24"],
     multihorizon:.data_manifest.fit_diagnostics}' \
  /home/sat/.local/state/thermal-intel/models/accepted.json
```

If `accepted.json` is absent or this command fails, report the candidate and
backtest metrics and stop. Do not alter horizons, weights, thresholds, labels,
or coefficients from the held-out result.

- [ ] **Step 5: Validate local shadow and operational invariants**

```bash
/usr/bin/python3 /home/sat/earthship-ui/openhab/scripts/validate_thermal_shadow.py \
  < /home/sat/.local/state/thermal-intel/review/shadow-local.json
test "$(wc -c < /home/sat/.local/state/thermal-intel/review/shadow-local.json)" -lt 16384
curl --silent --show-error --output /tmp/thermal-model-item-gate-check.json \
  --write-out '%{http_code}\n' http://127.0.0.1:5190/rest/items/Thermal_Model_JSON
python3 /home/sat/earthship-ui/scripts/thermal-systemd-state.py first-install
```

Expected invariant outputs remain OpenHAB `404` and systemd `first-install`.

- [ ] **Step 6: Stop and present Gate A evidence**

Present the pushed commit, runtime digest, exact schema fingerprint, v3
coefficient/constraint evidence, origin counts/objectives, all fold and baseline
metrics, Kiva exclusions, local shadow validation/size, absent Item, and
first-install systemd state. Request separate explicit Gate B approval. Do not
create `Thermal_Model_JSON`, publish state, install units, enable timers, or
perform physical automation in this task.
