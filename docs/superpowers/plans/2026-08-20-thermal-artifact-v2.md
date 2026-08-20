# Thermal Artifact v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fit an evidence-backed mass-to-outdoor exchange and produce a strictly stable, version-2 thermal artifact without weakening any promotion gate.

**Architecture:** Add one physical forcing column to the existing two-state regression and transition matrix. Make the artifact/version/constraint boundary exact and fail closed on v1, then retrain through the existing private Gate A pipeline. The public shadow payload remains version 1 and observational.

**Tech Stack:** Python 3.12, NumPy 1.26, SciPy 1.11, pytest, PostgreSQL 16, OpenHAB observational history.

## Global Constraints

- Approved design: `docs/superpowers/specs/2026-08-20-thermal-artifact-v2-design.md`.
- Dynamic states remain exactly hallway air and north-wall mass; glazing remains auxiliary.
- Add exact mass coefficient `outside_exchange` with bounds `[0.0, 0.20]`.
- Artifact schema is exactly `earthship-thermal-model/v2`; dynamics version is exactly integer `2`.
- Do not add mass bias, clamp coefficients, substitute prior values, or relax stability/backtest/promotion gates.
- V1 artifacts fail closed and require retraining; no synthetic migration is permitted.
- Shadow output remains the exact existing version-1, below-16-KiB, non-actuating contract.
- Gate B publication and Gate C timer activation remain blocked until their separate evidence/approval boundaries.

---

### Task 1: Mass-to-outdoor fit and simulation

**Files:**
- Modify: `openhab/scripts/thermal_model/dynamics.py`
- Modify: `openhab/scripts/test_thermal_dynamics.py`

**Interfaces:**
- Consumes: consecutive `ThermalSample` pairs with outdoor forcing.
- Produces: mass coefficients ordered as `air_exchange`, `outside_exchange`, `solar_unshaded`, `solar_indoor_closed`, `solar_outdoor`; `DynamicsModel(version=2, ...)`; unchanged `predict_step`, `simulate`, and `validate_physics` call shapes.

- [ ] **Step 1: Write synthetic recovery RED tests**

Extend the deterministic full-rank fixture with a known positive
`outside_exchange`. Assert the fitted coefficient is recovered within `2e-5`,
that `predict_step` cools warm mass toward cooler outdoors with air held equal,
and that the same forcing is applied throughout `simulate`.

```python
assert model.version == 2
assert model.mass_coefficients["outside_exchange"] == pytest.approx(
    TRUE_MASS_COEFFICIENTS["outside_exchange"], abs=2e-5
)
assert next_mass < initial_mass
```

- [ ] **Step 2: Run RED**

Run `pytest -q openhab/scripts/test_thermal_dynamics.py -k 'outside_exchange or synthetic_fixture_recovers_known_mass'`.
Expected: missing key/version mismatch failures.

- [ ] **Step 3: Implement the new design column and state update**

Set:

```python
MASS_NAMES = (
    "air_exchange", "outside_exchange", "solar_unshaded",
    "solar_indoor_closed", "solar_outdoor",
)
MASS_BOUNDS = (
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.20, 0.20, 0.008, 0.004, 0.006],
)
```

Add `right.outdoor_f - left.mass_f` to the weighted mass design immediately
after air exchange. Add the corresponding forcing in `predict_step`, and emit
`DynamicsModel(version=2, ...)`.

- [ ] **Step 4: Run GREEN and commit**

Run `pytest -q openhab/scripts/test_thermal_dynamics.py`.
Expected: all dynamics tests pass.

```bash
git add openhab/scripts/thermal_model/dynamics.py openhab/scripts/test_thermal_dynamics.py
git commit -m "feat: fit thermal mass exchange with outdoors"
```

### Task 2: Independent v2 physics gate

**Files:**
- Modify: `openhab/scripts/thermal_model/dynamics.py`
- Modify: `openhab/scripts/test_thermal_dynamics.py`

**Interfaces:**
- Produces: exact v2 transition matrix and strict `validate_physics(DynamicsModel) -> DynamicsModel`.

- [ ] **Step 1: Write transition/stability RED tests**

Assert the second diagonal is `1 - air_exchange - outside_exchange`, v1 is
rejected, negative/out-of-bound outdoor exchange is rejected, a positive
outdoor exchange removes the neutral mass mode when air exchange is zero, and
both exchange paths at zero still fail spectral stability.

- [ ] **Step 2: Run RED**

Run `pytest -q openhab/scripts/test_thermal_dynamics.py -k 'transition or stability or version'`.
Expected: version/transition assertions fail against v1 behavior.

- [ ] **Step 3: Implement the exact independent gate**

Update `_transition_matrix` and require version 2 at five-minute steps. Include
both mass exchanges in the nonnegative exchange set and validate every
coefficient against its declared lower/upper bound before spectral checks. Keep
`spectral_radius < 1.0 - 1e-9` at every declared ventilation level and retain
the 72-hour range simulations.

- [ ] **Step 4: Run GREEN and commit**

Run `pytest -q openhab/scripts/test_thermal_dynamics.py`.
Expected: all dynamics tests pass.

```bash
git add openhab/scripts/thermal_model/dynamics.py openhab/scripts/test_thermal_dynamics.py
git commit -m "fix: validate thermal v2 transition stability"
```

### Task 3: Exact artifact v2 boundary

**Files:**
- Modify: `openhab/scripts/thermal_model/artifacts.py`
- Modify: `openhab/scripts/test_thermal_artifacts.py`
- Modify: `openhab/scripts/thermal_model/pipeline.py`
- Modify: `openhab/scripts/test_thermal_pipeline.py`
- Modify: `openhab/scripts/test_thermal_evaluation.py`
- Modify: `openhab/scripts/test_thermal_behavior.py`

**Interfaces:**
- Produces: exact schema `earthship-thermal-model/v2`, dynamics version 2, v2 constraints evidence, and strict typed/raw registry parsing.

- [ ] **Step 1: Write schema/registry RED tests**

Update valid fixtures to v2 and assert accepted save/load/promotion. Add tests
that mutate only schema to v1, dynamics version to 1, omit/add/reorder the mass
name, omit/add/mistype the coefficient, or retain old bounds; every case must be
rejected before write and leave the prior accepted generation intact.

- [ ] **Step 2: Run RED**

Run `pytest -q openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_pipeline.py`.
Expected: fixtures fail against the current exact v1 boundary.

- [ ] **Step 3: Implement schema and manifest v2**

Set `MODEL_SCHEMA = "earthship-thermal-model/v2"`, require dynamics version 2
in typed/raw validators and parsers, and let `_expected_constraints()` derive
the exact five-name mass vocabulary/bounds. Do not accept both versions.

- [ ] **Step 4: Update all model fixtures without changing gates**

Every test fixture that constructs `DynamicsModel` must use version 2 and an
explicit `outside_exchange`. Preserve its original physical intent: stable
fixtures use a small positive value; tests targeting a neutral mode use zero.

- [ ] **Step 5: Run GREEN and commit**

Run all `openhab/scripts/test_thermal_*.py` files.
Expected: all thermal tests pass.

```bash
git add openhab/scripts/thermal_model openhab/scripts/test_thermal_*.py
git commit -m "feat: version thermal artifacts for mass outdoor exchange"
```

### Task 4: Documentation and private Gate A verification

**Files:**
- Modify: `docs/operations/thermal-model-shadow.md`
- Modify: `docs/superpowers/specs/2026-08-13-rc-thermal-model-design.md`
- Modify: `docs/superpowers/specs/2026-08-20-thermal-training-photosensor-repair-design.md`
- Modify: `docs/superpowers/plans/2026-08-20-thermal-training-photosensor-repair.md`

**Interfaces:**
- Produces: accurate v2 equations, migration/runbook instructions, and a private Gate A evidence bundle.

- [ ] **Step 1: Update model and runbook documentation**

Record the exact equation, bounds, transition matrix, schema/version boundary,
no-synthetic-migration rule, unchanged gates, photosensor collection boundary,
Kiva-event exclusion, and Gate B/C stop conditions.

- [ ] **Step 2: Run full offline verification**

Run all thermal and forecast pytest files, full Vitest, `npm run build`, Python
syntax compilation, and shell/systemd static checks. Expected: all pass with no
tracked generated files.

- [ ] **Step 3: Install reviewed private runtime atomically**

Back up the exact deployed thermal runtime manifest and state directory, verify
source hashes, install only reviewed Python/runtime files, and prove the live
installed manifest matches the commit. Do not create or update
`Thermal_Model_JSON`.

- [ ] **Step 4: Run private Gate A**

Run schema audit, 400-day training, chronological backtest, candidate validation
and promotion, then local shadow generation. Capture exact revision, seasonal
counts, Kiva exclusions, coefficient/bounds evidence, spectral radii, fold
metrics, persistence comparison, artifact hashes, and shadow validation/size.
If any gate fails, retain the prior accepted artifact and stop with the exact
evidence; never weaken the gate.

- [ ] **Step 5: Commit documentation**

```bash
git add docs openhab/scripts
git commit -m "docs: operate thermal artifact v2"
```

- [ ] **Step 6: Stop at Gate B**

Present the complete private Gate A evidence. Do not create or publish
`Thermal_Model_JSON`, and do not enable thermal timers, without their separate
approval boundary.

### Task 5: Branch verification and publication

**Files:**
- No source additions; branch/integration operations only.

**Interfaces:**
- Produces: verified earthship-ui `main` and `origin/main` containing the v2 implementation while live publication remains gated.

- [ ] **Step 1: Verify branch cleanliness and fresh tests**

Run the full verification matrix again from the exact branch head and record
commit hashes plus test counts.

- [ ] **Step 2: Merge and publish**

Merge the feature branch into local `main`, push `main` to `origin`, fetch, and
prove local/remote commit equality. Preserve the dirty pre-existing
`latent-mass-redesign` worktree untouched.
