# Thermal Training and Photosensor Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a promotable year-round RC thermal artifact with exact ordered solar-gain constraints and begin receipt-bound OpenHAB/JDBC collection from the hallway Philips SML003.

**Architecture:** Keep the two-state model and immutable shadow schema. Add exact coupled solar-gain inequalities to the existing weighted regressions, change the default training window to 400 days, and add closed per-mode dataset evidence. Provision three observational Philips Items and their exact links through a separate receipt-bound tool; rely on the already-verified JDBC wildcard policy and emit no shade labels yet.

**Tech Stack:** Python 3.12, NumPy 1.26, SciPy 1.11, pytest, Node.js ESM, Vitest, OpenHAB 5.2 REST/JDBC, PostgreSQL 16, user-level systemd.

## Global Constraints

- Authoritative repair spec: `docs/superpowers/specs/2026-08-20-thermal-training-photosensor-repair-design.md` at commit `00394ccf71dc4459bce587da494788171eb0c25a` or later.
- The physical model remains exactly two-state: hallway air plus north-wall mass; glazing remains auxiliary.
- The default training window is exactly 400 days.
- Solar gains must satisfy `unshaded >= indoor_closed >= 0` and `unshaded >= outdoor_shaded >= 0` during fitting and independent validation.
- Rank-deficient, non-finite, infeasible, unsuccessful, unstable, or unphysical fits fail closed. Never clamp or invent coefficients.
- Dataset mode counts use the exact keys `unknown`, `fall_charge`, `winter`, `spring`, and `warm`; counts are nonnegative exact integers and sum to `sample_count`.
- The Philips Thing is `zigbee:device:a7351eb531:001788011024c307` and represents the living-room/office windows from its hallway position.
- Provision exactly three Items and links: `LivingOffice_Shade_Illuminance`, `LivingOffice_Shade_Occupancy`, and `LivingOffice_Shade_Temperature`.
- The photosensor tool cannot mutate Things, channels, persistence policy, metadata, rules, Item states, unrelated Items, or unrelated links.
- The current JDBC `*` / `everyChange` / `restoreOnStartup` contract is verified read-only and never written.
- This implementation emits no photosensor-derived shade label and has no actuator, rule, `Thermal_Advisory`, or physical-automation authority.
- Gate B publication and Gate C systemd activation remain blocked until private Gate A evidence is presented.

---

### Task 1: Ordered constrained thermal identification

**Files:**
- Modify: `openhab/scripts/thermal_model/dynamics.py`
- Modify: `openhab/scripts/test_thermal_dynamics.py`

**Interfaces:**
- Consumes: the existing weighted design matrix, target, box bounds, and ordered coefficient names.
- Produces: `_fit(design, target, bounds, names, *, ordered_solar=False) -> dict[str, float]` and unchanged `fit_dynamics(samples) -> DynamicsModel`.

- [ ] **Step 1: Add a regression dataset whose box-only optimum violates gain order**

Add a deterministic helper and test that exercises the public fitter:

```python
def test_fit_enforces_ordered_solar_gains_during_optimization():
    samples = synthetic_full_rank_samples_with_shaded_gain_pressure()
    model = fit_dynamics(samples)
    for coefficients in (
        model.air_coefficients,
        model.mass_coefficients,
        model.glazing_observation_coefficients,
    ):
        assert coefficients["solar_unshaded"] >= coefficients["solar_indoor_closed"]
        assert coefficients["solar_unshaded"] >= coefficients["solar_outdoor"]
        assert coefficients["solar_indoor_closed"] >= 0.0
        assert coefficients["solar_outdoor"] >= 0.0
```

The fixture must be full rank and must demonstrate that direct `lsq_linear`
with the same box bounds produces at least one shaded gain above unshaded.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q openhab/scripts/test_thermal_dynamics.py::test_fit_enforces_ordered_solar_gains_during_optimization
```

Expected: FAIL with `shade gain exceeds unshaded gain` from the current fitter.

- [ ] **Step 3: Add exact linear constraints to the weighted least-squares fit**

Use SciPy's deterministic constrained minimization over the same quadratic:

```python
from scipy.optimize import Bounds, LinearConstraint, lsq_linear, minimize

def _solar_order_constraint(names):
    rows = np.zeros((2, len(names)), dtype=float)
    unshaded = names.index("solar_unshaded")
    rows[0, unshaded] = rows[1, unshaded] = 1.0
    rows[0, names.index("solar_indoor_closed")] = -1.0
    rows[1, names.index("solar_outdoor")] = -1.0
    return LinearConstraint(rows, np.zeros(2), np.full(2, np.inf))

def _objective(matrix, values, coefficients):
    residual = matrix @ coefficients - values
    return 0.5 * float(residual @ residual)

def _gradient(matrix, values, coefficients):
    return matrix.T @ (matrix @ coefficients - values)
```

Start from the bounded `lsq_linear` solution projected only to a feasible
starting point, then run `minimize(..., method="SLSQP", jac=..., bounds=Bounds,
constraints=(_solar_order_constraint(names),), options={"ftol": 1e-12,
"maxiter": 2000})`. Reject unsuccessful, non-finite, bound-violating, or
constraint-violating results. Never return the projected starting point unless
the optimizer itself succeeds.

Air and mass keep their existing bounds. Add glazing bounds with unbounded
intercept/air/outdoor coefficients and nonnegative solar coefficients:

```python
GLAZING_BOUNDS = (
    [-np.inf, -np.inf, -np.inf, 0.0, 0.0, 0.0],
    [ np.inf,  np.inf,  np.inf, np.inf, np.inf, np.inf],
)
```

Call the ordered fit for air, mass, and glazing. Keep the independent
`validate_physics()` call unchanged.

- [ ] **Step 4: Add failure-contract tests**

Add tests proving:

```python
def test_ordered_fit_still_rejects_rank_deficiency(): ...
def test_ordered_fit_rejects_unsuccessful_optimizer(monkeypatch): ...
def test_ordered_fit_rejects_nonfinite_or_infeasible_result(monkeypatch): ...
def test_known_synthetic_coefficients_remain_within_existing_tolerances(): ...
```

The monkeypatch tests must target the optimizer boundary and assert bounded,
sanitized `ValueError` reasons.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest -q openhab/scripts/test_thermal_dynamics.py
```

Expected: all dynamics tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add openhab/scripts/thermal_model/dynamics.py openhab/scripts/test_thermal_dynamics.py
git commit -m "fix: constrain thermal solar gains during fitting"
```

---

### Task 2: Rolling 400-day training and exact per-mode evidence

**Files:**
- Modify: `openhab/scripts/thermal_intel.py`
- Modify: `openhab/scripts/thermal_model/dataset.py`
- Modify: `openhab/scripts/thermal_model/artifacts.py`
- Modify: `openhab/scripts/thermal_model/pipeline.py`
- Modify: `openhab/scripts/test_thermal_pipeline.py`
- Modify: `openhab/scripts/test_thermal_dataset.py`
- Modify: `openhab/scripts/test_thermal_artifacts.py`

**Interfaces:**
- Consumes: existing `_date_range(args, now)`, `dataset_manifest(samples, events, modes)`, typed and raw artifact validators.
- Produces: `DEFAULT_TRAINING_DAYS = 400` and `data_manifest.sample_counts_by_mode` with a closed five-key vocabulary.

- [ ] **Step 1: Write the 400-day RED test**

```python
def test_default_training_range_is_rolling_400_days():
    args = SimpleNamespace(start=None, end=None)
    start, end = thermal_intel._date_range(args, NOW)
    assert end == NOW
    assert start == NOW - timedelta(days=400)
```

Run the single test and expect the current 90-day assertion mismatch.

- [ ] **Step 2: Write per-mode manifest RED tests**

Extend the canonical dataset fixture with all modes plus one `None` sample and
assert:

```python
assert manifest["sample_counts_by_mode"] == {
    "unknown": 1,
    "fall_charge": expected_fall,
    "winter": expected_winter,
    "spring": expected_spring,
    "warm": expected_warm,
}
assert sum(manifest["sample_counts_by_mode"].values()) == manifest["sample_count"]
```

Extend typed and raw artifact tests to reject missing/extra mode keys, booleans,
negative/noninteger counts, sum mismatches, and any year-round candidate with a
zero evidence-backed seasonal count.

- [ ] **Step 3: Verify RED**

```bash
pytest -q \
  openhab/scripts/test_thermal_pipeline.py -k default_training_range \
  openhab/scripts/test_thermal_dataset.py -k sample_counts_by_mode \
  openhab/scripts/test_thermal_artifacts.py -k sample_counts_by_mode
```

Expected: failures for 90 days and the absent manifest field.

- [ ] **Step 4: Implement the exact producer and validators**

In `thermal_intel.py`:

```python
DEFAULT_TRAINING_DAYS = 400
```

In `dataset.py`:

```python
MODE_COUNT_KEYS = ("unknown", "fall_charge", "winter", "spring", "warm")
mode_counts = {key: 0 for key in MODE_COUNT_KEYS}
for sample in ordered:
    mode_counts[sample.mode or "unknown"] += 1
```

Add `sample_counts_by_mode` to the returned manifest. In `artifacts.py`, add
the key to `_MANIFEST_KEYS`, exact-check its vocabulary in raw payloads, validate
all values through `_integer(..., minimum=0)`, and require the sum to equal
`sample_count`. Generic artifact parsing must continue to accept valid
partial-season evidence. At the `require_eligible=True` promotion boundary,
refuse candidates unless every non-`unknown` seasonal count is positive.

Because the glazing solar coefficients become bounded, add exact
`glazing_observation_bounds` evidence to `_constraints_manifest()` and
`_expected_constraints()`. Extend typed and raw exact-schema tests so missing,
extra, reordered, or mistyped glazing bounds fail closed.

- [ ] **Step 5: Update all exact manifest fixtures and run GREEN**

Update helper artifacts and exact-key assertions throughout the focused tests.
Run:

```bash
pytest -q openhab/scripts/test_thermal_dataset.py \
  openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_pipeline.py
```

- [ ] **Step 6: Commit Task 2**

```bash
git add openhab/scripts/thermal_intel.py \
  openhab/scripts/thermal_model/dataset.py \
  openhab/scripts/thermal_model/artifacts.py \
  openhab/scripts/thermal_model/pipeline.py \
  openhab/scripts/test_thermal_pipeline.py \
  openhab/scripts/test_thermal_dataset.py \
  openhab/scripts/test_thermal_artifacts.py
git commit -m "feat: retain year-round thermal training evidence"
```

---

### Task 3: Receipt-bound Philips Item and link configuration

**Files:**
- Create: `scripts/thermal-photosensor-config.mjs`
- Create: `tests/thermal-photosensor-config.test.js`

**Interfaces:**
- Produces CLI commands `snapshot`, `plan`, `rehearse`, `apply`, `verify`, `close`, `rollback`, and `settle`, each requiring `--receipt-dir` except pure help.
- Owns exactly three Item paths and three link paths. GET additionally allows the exact Thing, JDBC configuration, and explicit per-Item JDBC history paths.

- [ ] **Step 1: Write manifest and allowlist RED tests**

Import the wished-for module and assert exact frozen resources:

```javascript
expect(PHOTOSENSOR_ITEMS.map(({ name, type }) => ({ name, type }))).toEqual([
  { name: 'LivingOffice_Shade_Illuminance', type: 'Number' },
  { name: 'LivingOffice_Shade_Occupancy', type: 'Switch' },
  { name: 'LivingOffice_Shade_Temperature', type: 'Number:Temperature' },
]);
expect(PHOTOSENSOR_LINKS.map(({ itemName, channelUID }))).toEqual([
  { itemName: 'LivingOffice_Shade_Illuminance', channelUID: `${THING}:001788011024C307_2_illuminance` },
  { itemName: 'LivingOffice_Shade_Occupancy', channelUID: `${THING}:001788011024C307_2_occupancy` },
  { itemName: 'LivingOffice_Shade_Temperature', channelUID: `${THING}:001788011024C307_2_temperature` },
]);
```

Assert denial of Thing PUT/DELETE, persistence PUT, metadata/rule/state paths,
unrelated Item/link paths, unknown body keys, wrong types, and nonempty link
configuration.

- [ ] **Step 2: Verify RED**

```bash
npm test -- --run tests/thermal-photosensor-config.test.js
```

Expected: module-not-found failure.

- [ ] **Step 3: Implement pure resource and request validation**

The module exports frozen manifests, canonical digest/checksum helpers, exact
Item/link normalizers, `authorizePhotosensorRequest`, `buildApplyPlan`, and
`buildRollbackPlan`. Desired Item DTOs have exact keys:

```javascript
{ name, type, label, category: '', tags: [], groupNames: [] }
```

Desired link DTOs are exact:

```javascript
{ itemName, channelUID, configuration: {} }
```

Apply creates Items first and links second. Rollback reverses links first and
then Items, restoring captured DTOs or deleting only receipt-owned absent
resources.

- [ ] **Step 4: Add receipt/state-machine RED tests**

Tests cover 0700 receipt directories, 0600 atomic JSON, unique sibling temp
files, checksum integrity, exclusive lock ownership, snapshot drift refusal,
one-write accounting per resource, exact GET settlement, idempotent close,
closed-desired rollback reopening, and recovery after injected interruption at
every write boundary. Rehearsal must use an in-memory transport and prove real
receipt/snapshot bytes are unchanged.

- [ ] **Step 5: Implement the receipt transaction**

Follow `scripts/thermal-model-config.mjs` receipt conventions but use a distinct
schema `earthship-thermal-photosensor-config-receipt/v1`. Snapshot captures:

```javascript
{
  items: { [itemName]: ItemDTO | null },
  links: { [itemName]: LinkDTO | null },
  thing: sanitizedThingEvidence,
  jdbc: sanitizedJdbcEvidence,
}
```

Reject any Thing that is not ONLINE, any missing/wrong channel, or JDBC without
editable wildcard `*` coverage containing both `everyChange` and
`restoreOnStartup`. Do not store tokens, URLs, Thing configuration, or unrelated
live resources in receipts.

- [ ] **Step 6: Add executable CLI tests and GREEN**

Test exact HTTP method/path/body packets, sanitized errors, no retry of writes,
no authorization loading for rehearsal, byte/mode durability, and help output.
Run:

```bash
npm test -- --run tests/thermal-photosensor-config.test.js
```

- [ ] **Step 7: Commit Task 3**

```bash
git add scripts/thermal-photosensor-config.mjs tests/thermal-photosensor-config.test.js
git commit -m "feat: provision thermal photosensor observations"
```

---

### Task 4: Runbook, deployment contracts, and no-label boundary

**Files:**
- Modify: `docs/operations/thermal-model-shadow.md`
- Modify: `tests/deployment-service.test.js`
- Modify: `README.md`
- Modify: `openhab/scripts/test_thermal_pipeline.py`

**Interfaces:**
- Documents and statically verifies the photosensor configuration gate before private Gate A.
- Proves current thermal training never requests or emits a photosensor shade label.

- [ ] **Step 1: Write static RED tests**

Add tests requiring the runbook to contain:

```text
thermal-photosensor-config.mjs snapshot
thermal-photosensor-config.mjs plan
thermal-photosensor-config.mjs rehearse
thermal-photosensor-config.mjs apply
thermal-photosensor-config.mjs verify
thermal-photosensor-config.mjs close
```

Require an explicit JDBC read-only check, exact three Item/link inventory,
pending-first-acquisition language, 400-day training evidence, and a stop before
Gate B. Reject any photosensor persistence PUT, rule path, state PUT, or actuator
name in the photosensor mutation block.

- [ ] **Step 2: Write the no-label RED test**

Instrument the pipeline's authority reads and assert that adding arbitrary
photosensor histories cannot change action labels, behavior transitions, or
the immutable shadow schema in this change.

- [ ] **Step 3: Verify RED**

```bash
npm test -- --run tests/deployment-service.test.js
pytest -q openhab/scripts/test_thermal_pipeline.py -k photosensor
```

- [ ] **Step 4: Update the attended runbook and README**

Document preliminary read-only inventory, the dedicated receipt path, snapshot,
plan, rehearsal, explicit three-Item/three-link mutation, exact readback/close,
pending acquisition, rollback, and the existing no-actuation gates. Update Gate
A evidence commands to show `sample_counts_by_mode` and exactly 400 days.

- [ ] **Step 5: GREEN and commit Task 4**

```bash
npm test -- --run tests/deployment-service.test.js
pytest -q openhab/scripts/test_thermal_pipeline.py
git add docs/operations/thermal-model-shadow.md README.md \
  tests/deployment-service.test.js openhab/scripts/test_thermal_pipeline.py
git commit -m "docs: stage year-round thermal retraining"
```

---

### Task 5: Complete implementation verification and branch integration

**Files:**
- Verify all modified files from Tasks 1-4.

- [ ] **Step 1: Run focused Python**

```bash
pytest -q openhab/scripts/test_thermal_dynamics.py \
  openhab/scripts/test_thermal_dataset.py \
  openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_pipeline.py
```

- [ ] **Step 2: Run full thermal/forecast Python and static checks**

```bash
pytest -q openhab/scripts/test_forecast_intel.py openhab/scripts/test_thermal_*.py
python3 -m py_compile openhab/scripts/thermal_intel.py openhab/scripts/thermal_model/*.py
pyflakes openhab/scripts/thermal_intel.py openhab/scripts/thermal_model
```

- [ ] **Step 3: Run JavaScript, build, browser, and deployment checks**

```bash
npm test
npm run build
npx playwright test
systemd-analyze verify deploy/thermal-model-train.service \
  deploy/thermal-model-train.timer deploy/thermal-model-shadow.service \
  deploy/thermal-model-shadow.timer
git diff --check
```

- [ ] **Step 4: Verify scope and clean branch**

Confirm no shadow schema field, action authority, protected Item, rule, or unit
ExecStart changed beyond the approved 400-day runtime default. Commit any
verification-driven correction only after its own RED/GREEN cycle.

- [ ] **Step 5: Integrate the verified implementation into `main`**

Use the finishing workflow, merge the isolated branch non-destructively, rerun
the focused suites on `main`, and confirm `git status --short` is empty.

---

### Task 6: Attended photosensor deployment and private Gate A retraining

**Files/state:**
- Runtime: `/home/sat/openhab/scripts`
- Photosensor receipt: protected 0700 directory under `/home/sat/.local/state/thermal-intel/deploy-receipts/`
- Model state: `/home/sat/.local/state/thermal-intel/models`
- No Gate B/C mutation.

- [ ] **Step 1: Re-run live read-only preflight**

Verify exact runtime revision, OpenHAB version, Thing/channel inventory, absent
three Items/links or exact captured state, wildcard JDBC coverage, exact thermal
PostgreSQL schema, current mode/action journal, `Thermal_Model_JSON` absence,
first-install systemd posture, protected Item states, and secrets file mode
without printing credentials.

- [ ] **Step 2: Atomically install the reviewed runtime**

Use the existing `thermal-model-files.py` prepare/install/verify/recover receipt
flow. Only the reviewed runtime manifest may change.

- [ ] **Step 3: Apply and close the photosensor receipt**

Run `snapshot`, `plan`, `rehearse`, review the exact six-write packet, then
`apply`, `verify`, and `close`. Read back the three Items and links. Query each
Item through `serviceId=jdbc`; record either its first point or pending first
acquisition. Never retry an ambiguous write; use receipt settlement.

- [ ] **Step 4: Run private Gate A**

Load the runtime DSN without printing it, verify the exact schema fingerprint,
run `thermal_intel.py train`, `backtest`, and local `shadow`. Require:

```text
sample_counts_by_mode: every fall_charge/winter/spring/warm count > 0
Kiva exclusions: present
promotion.eligible: true
promotion.at_least_two_folds: true
model air 24h MAE < persistence air 24h MAE
artifact code revision == installed runtime revision
local shadow: available, canonical, < 16384 bytes, mode 0600
```

- [ ] **Step 5: Stop before Gate B and report evidence**

Record the verified implementation/deployment outcome in private Hexmem. Do not
create `Thermal_Model_JSON`, publish state, install/enable thermal units, or
write any actuator/advisory surface. Present exact evidence and request the
separate Gate B decision.
