# Thermal v4 Astronomical-Night Radiation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair every-change solar-radiation evidence by reconstructing only absent astronomical-night buckets as zero, broaden chronological 24-hour evidence, and produce a private fail-closed v4 Gate A candidate without publishing or activating automation.

**Architecture:** One pure module owns the existing deterministic solar calculation. Dataset construction retains observed/interpolated/held radiation first, reconstructs only otherwise-missing night buckets, and carries exact provenance through private v4 model and v2 backtest artifacts. Promotion keeps every existing physics and persistence gate and adds fold-count and seasonal-coverage gates. Before a later attended Gate A install, the rejected v3 evidence is copied into the private receipt with pinned hashes.

**Tech Stack:** Python 3, NumPy/SciPy, psycopg2/OpenHAB JDBC history, pytest, Node/Vitest, Bash/systemd verification, Git.

## Global constraints

- Preserve `earthship-thermal-shadow/v1`, the current 2R2C equations, coefficient bounds, observer, optimizer, hybrid behavior model, and action-confidence rules.
- Never fill daylight radiation or any temperature gap. Never replace an explicit non-finite radiation observation with night zero.
- Exact validators reject missing/unknown keys, booleans as counts, negative counts, non-finite values, and inconsistent totals.
- This plan changes and verifies code only. Do not train against live data, publish, write an OpenHAB Item, install/start services, enable timers, or activate automation.
- Use one focused commit per task and stage only paths changed by that task.

---

### Task 1: Establish one shared solar-elevation authority

**Files:**

- Create: `openhab/scripts/thermal_model/solar.py`
- Create: `openhab/scripts/test_thermal_solar.py`
- Modify: `openhab/scripts/thermal_model/dataset.py`
- Modify: `openhab/scripts/thermal_model/behavior.py`
- Modify: `openhab/scripts/thermal_intel.py`
- Modify: `scripts/thermal-model-files.py`
- Modify: `openhab/scripts/test_thermal_behavior.py`
- Modify: `openhab/scripts/test_thermal_publish.py`
- Modify: `openhab/scripts/test_thermal_deploy_files.py`
- Modify: `docs/operations/thermal-model-shadow.md`

- [ ] **Write failing tests** for exact coordinates/rule, timezone-aware input, finite output, the elevation-sine zero boundary, dataset/behavior agreement, and both exact runtime manifests.

```python
def test_solar_contract_is_exact():
    assert solar.solar_contract() == {
        "rule": "earthship-solar-elevation/v1",
        "latitude": 38.3739919,
        "longitude": -105.7744609,
        "night_when_elevation_sin_lte": 0.0,
    }

def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        solar.solar_elevation_sin(datetime(2026, 8, 20, 3, 0))
```

- [ ] **Confirm RED.**

```bash
pytest -q openhab/scripts/test_thermal_solar.py openhab/scripts/test_thermal_behavior.py openhab/scripts/test_thermal_publish.py openhab/scripts/test_thermal_deploy_files.py
```

Expected: missing module and runtime-manifest failures.

- [ ] **Implement the authority.** Move, rather than rederive, the deterministic NOAA-style calculation duplicated in `dataset.py` and `behavior.py`.

```python
SOLAR_ELEVATION_RULE = "earthship-solar-elevation/v1"
SITE_LATITUDE = 38.3739919
SITE_LONGITUDE = -105.7744609

def is_astronomical_night(at):
    return solar_elevation_sin(at) <= 0.0
```

Reject naive timestamps and non-finite results. Delete the duplicate formulas, import the shared functions, add `thermal_model/solar.py` to both exact runtime manifests, and update the runbook runtime-file table.

- [ ] **Confirm GREEN** with the RED command, then commit.

```bash
git add openhab/scripts/thermal_model/solar.py openhab/scripts/test_thermal_solar.py openhab/scripts/thermal_model/dataset.py openhab/scripts/thermal_model/behavior.py openhab/scripts/thermal_intel.py scripts/thermal-model-files.py openhab/scripts/test_thermal_behavior.py openhab/scripts/test_thermal_publish.py openhab/scripts/test_thermal_deploy_files.py docs/operations/thermal-model-shadow.md
git commit -m "refactor: share thermal solar elevation authority"
```

---

### Task 2: Reconstruct only absent astronomical-night radiation

**Files:**

- Modify: `openhab/scripts/thermal_model/dataset.py`
- Modify: `openhab/scripts/thermal_model/pipeline.py`
- Modify: `openhab/scripts/thermal_model/artifacts.py`
- Modify: `openhab/scripts/test_thermal_dataset.py`
- Modify: `openhab/scripts/test_thermal_pipeline.py`
- Modify: `openhab/scripts/test_thermal_artifacts.py`

- [ ] **Write failing precedence tests** proving observed/interpolated/held night values win; absent night radiation becomes exactly zero; absent daylight radiation remains rejected; explicit non-finite night radiation remains rejected; and simultaneous temperature gaps remain rejected.

```python
assert dataset.radiation_provenance_by_at[NIGHT_AT] == "astronomical_night_zero"
assert sample.radiation_wm2 == 0.0
assert DAY_AT not in {sample.at for sample in daylight_gap_dataset}
```

Add exact manifest mutations proving the four provenance counts sum to `sample_count` and provenance changes the canonical sample digest.

- [ ] **Confirm RED.**

```bash
pytest -q openhab/scripts/test_thermal_dataset.py openhab/scripts/test_thermal_pipeline.py openhab/scripts/test_thermal_artifacts.py
```

- [ ] **Implement provenance and reconstruction.** Extend `_bucket_series` to return radiation provenance, then fill only absent, non-nonfinite night buckets after normal bucketing/interpolation/hold processing.

```python
RADIATION_PROVENANCE_LABELS = (
    "observed", "interpolated", "held", "astronomical_night_zero",
)

def radiation_reconstruction_contract():
    return {
        "rule": "missing_at_solar_elevation_lte_zero_becomes_zero",
        "night_value_wm2": 0.0,
        "solar": solar.solar_contract(),
        "provenance_labels": list(RADIATION_PROVENANCE_LABELS),
    }
```

Add `radiation_provenance_by_at` to `ThermalDataset`, not `ThermalSample`. Do not clear another role's source-gap rejection.

- [ ] **Advance the private model to v4.** Set `MODEL_SCHEMA = "earthship-thermal-model/v4"`; add exact reconstruction and count fields to the manifest/constraints; bind `_radiation_provenance` into digest-only canonical rows; update reconstruction/type/mutation validation. Keep public shadow v1 unchanged.

- [ ] **Confirm GREEN and determinism.** Run the RED command twice and compare canonical bytes/digests, then commit.

```bash
git add openhab/scripts/thermal_model/dataset.py openhab/scripts/thermal_model/pipeline.py openhab/scripts/thermal_model/artifacts.py openhab/scripts/test_thermal_dataset.py openhab/scripts/test_thermal_pipeline.py openhab/scripts/test_thermal_artifacts.py
git commit -m "feat: reconstruct astronomical-night radiation evidence"
```

---

### Task 3: Advance private backtesting to v2 and add coverage gates

**Files:**

- Modify: `openhab/scripts/thermal_model/evaluation.py`
- Modify: `openhab/scripts/thermal_model/artifacts.py`
- Modify: `openhab/scripts/test_thermal_evaluation.py`
- Modify: `openhab/scripts/test_thermal_artifacts.py`
- Modify: `openhab/scripts/test_thermal_pipeline.py`

- [ ] **Write failing fold and threshold tests.** Each fold must carry `training_row_count`, `evaluation_target_row_count`, and exact four-category radiation splits for training and the longest evaluation target. Each split must sum to its local row count; overlapping training prefixes must not be summed into the dataset manifest.

```python
def test_29_scored_24h_folds_fail_count_gate():
    gates = provisional_promotion_gates(
        physics_valid=True,
        finite_metrics=True,
        scored_fold_count=29,
        model_24={"count": 29, "mae": 1.0},
        persistence_24={"count": 29, "mae": 2.0},
        scored_24h_by_regime={"warm": 15, "winter": 14, "shoulder": 0},
    )
    assert gates["at_least_30_scored_24h_folds"] is False

def test_two_regimes_need_five_folds_each():
    common = {
        "physics_valid": True, "finite_metrics": True,
        "scored_fold_count": 30,
        "model_24": {"count": 30, "mae": 1.0},
        "persistence_24": {"count": 30, "mae": 2.0},
    }
    assert provisional_promotion_gates(
        **common, scored_24h_by_regime={"warm": 25, "winter": 4, "shoulder": 1}
    )["at_least_two_24h_regimes"] is False
    assert provisional_promotion_gates(
        **common, scored_24h_by_regime={"warm": 25, "winter": 5, "shoulder": 0}
    )["at_least_two_24h_regimes"] is True
```

- [ ] **Confirm RED.**

```bash
pytest -q openhab/scripts/test_thermal_evaluation.py openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_pipeline.py
```

- [ ] **Emit exact fold evidence.** Look up provenance by sample timestamp. Include diagnostics on error folds, but count a fold toward aggregate scored evidence only when it has neither `fit_error` nor `model_error` and has a valid same-record model/persistence pair. Make producer and validator share that predicate.

- [ ] **Add v2 and the two new gates without changing old semantics.**

```python
BACKTEST_SCHEMA = "earthship-thermal-backtest/v2"
MIN_SCORED_24H_FOLDS = 30
MIN_REGIME_24H_FOLDS = 5
MIN_24H_REGIMES = 2
```

Extend the existing keyword-only `provisional_promotion_gates` interface with `scored_24h_by_regime`; do not replace it with a report-shaped argument. Extend `_PROMOTION_GATES` with `at_least_30_scored_24h_folds` and `at_least_two_24h_regimes`. Preserve the exact old gate keys and semantics: `physics_valid`, `finite_metrics`, `at_least_two_folds`, and `air_24h_beats_persistence`.

Derive regime counts only from valid scored 24-hour prediction records. Exact validation and mutation tests must enforce:

```text
metrics.overall.model.air.24.count
== metrics.overall.persistence.air.24.count
== sum(metrics.by_regime[*].model.air.24.count)
== sum(metrics.by_regime[*].persistence.air.24.count)
== number of valid paired 24-hour prediction records
```

Reject any contradictory aggregate, regime, record, or fold evidence before computing eligibility. Keep recent-cycle diagnostic only. Validate exact top-level/fold keys, including only the producer's intentional optional error keys.

- [ ] **Confirm GREEN** with the RED command, then commit.

```bash
git add openhab/scripts/thermal_model/evaluation.py openhab/scripts/thermal_model/artifacts.py openhab/scripts/test_thermal_evaluation.py openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_pipeline.py
git commit -m "feat: require broad 24-hour thermal evidence"
```

---

### Task 4: Prove continuity with synthetic every-change history

**Files:**

- Modify: `openhab/scripts/test_thermal_dataset.py`
- Modify: `openhab/scripts/test_thermal_evaluation.py`
- Modify: `openhab/scripts/test_thermal_pipeline.py`

- [ ] **Create a deterministic 45-day fixture.** Persist air/mass/outdoor every five minutes, but radiation only when its value changes: daylight changes plus one sunset zero and normal overnight silence. Use explicit mode events, not calendar inference, to give at least 15 warm and 15 winter 24-hour targets.

```python
def every_change_radiation(start, end):
    rows, previous = [], None
    for at in five_minute_range(start, end):
        value = synthetic_radiation(at)
        if value != previous:
            rows.append((at, value))
            previous = value
    return rows
```

- [ ] **Assert the intended end-to-end evidence.** The pipeline must recover continuous 24-hour targets, produce at least 30 scored 24-hour folds, and pass the two-regime gate. It need not pass the strict MAE gate merely because coverage is present.

```python
assert report["metrics"]["overall"]["model"]["air"]["24"]["count"] >= 30
assert report["metrics"]["promotion"]["gates"]["at_least_two_24h_regimes"] is True
```

- [ ] **Add negative mutations.** Remove one required daylight-radiation span beyond the old limit, then one mass-temperature span. Both remain gaps. Build/serialize twice and assert byte-stable manifests, digests, fold order, counts, and gates.

- [ ] **Run the affected suite.**

```bash
pytest -q openhab/scripts/test_thermal_dataset.py openhab/scripts/test_thermal_evaluation.py openhab/scripts/test_thermal_pipeline.py openhab/scripts/test_thermal_artifacts.py
```

Expected: all collected tests pass.

- [ ] **Commit the regression.**

```bash
git add openhab/scripts/test_thermal_dataset.py openhab/scripts/test_thermal_evaluation.py openhab/scripts/test_thermal_pipeline.py
git commit -m "test: prove thermal every-change night continuity"
```

---

### Task 5: Archive rejected v3 evidence in the attended receipt

**Files:**

- Modify: `scripts/thermal-model-files.py`
- Modify: `openhab/scripts/test_thermal_deploy_files.py`

**Pinned source evidence:**
- `candidate.json`: schema `earthship-thermal-model/v3`, mode `0600`, SHA-256 `6d68639f426274d67a72d2ae45478f987af34dfdf0ae4675bc868c7f79f204fe`.
- `backtest-report.json`: schema `earthship-thermal-backtest/v1`, mode `0600`, SHA-256 `1c504fc3b37c945af990a368d3483c5c5a69fc985e4d76ddcf6d3eaf277b211f`.
- Fixed source root: `/home/sat/.local/state/thermal-intel/models`.

- [ ] **Write failing safety tests** for a confined `archive-prior-v3` command. It must derive `<attended-receipt>/prior-model-v3` from the validated `<attended-receipt>/files` argument; reject symlink components; prevalidate both regular sources, modes, hashes, JSON, exact schemas, and `metrics.promotion.eligible == false` before writing; refuse an existing archive; write directory `0700` and files `0600`; preserve exact bytes; and never register v3 as a fallback.

- [ ] **Confirm RED.**

```bash
pytest -q openhab/scripts/test_thermal_deploy_files.py -k 'archive_prior_v3 or prior_model'
```

- [ ] **Implement the fixed-scope command.** Reuse the descriptor-based `_open_directory`, `secure_directory`, `_read_regular`, and `_atomic_write_private` paths. Do not create a generic copy primitive. Write an exact deterministic manifest:

```json
{
  "schema": "earthship-thermal-prior-evidence/v1",
  "records": [
    {"archivedName":"candidate-v3.json","sourcePath":"/home/sat/.local/state/thermal-intel/models/candidate.json","sourceSchema":"earthship-thermal-model/v3","sha256":"6d68639f426274d67a72d2ae45478f987af34dfdf0ae4675bc868c7f79f204fe","mode":"0600"},
    {"archivedName":"backtest-report-v1.json","sourcePath":"/home/sat/.local/state/thermal-intel/models/backtest-report.json","sourceSchema":"earthship-thermal-backtest/v1","sha256":"1c504fc3b37c945af990a368d3483c5c5a69fc985e4d76ddcf6d3eaf277b211f","mode":"0600"}
  ]
}
```

The displayed object is the full exact key set. Build all three files inside a confined mode-`0700` sibling temporary directory, fsync every file and the completed directory, then publish the directory with the existing `renameat2(RENAME_NOREPLACE)` capability and fsync its parent. On an ordinary exception, remove only the helper-owned temporary directory; on crash, a later invocation may recover or safely remove only a verifiably helper-owned incomplete sibling. Never create the final archive directory before the no-replace publication. Mutation tests must inject failures after each file write, directory fsync, and final rename and prove no partial final archive is accepted or overwritten.

- [ ] **Confirm GREEN and static validity.**

```bash
pytest -q openhab/scripts/test_thermal_deploy_files.py
pyflakes scripts/thermal-model-files.py openhab/scripts/test_thermal_deploy_files.py
python3 -m py_compile scripts/thermal-model-files.py
```

- [ ] **Commit receipt archival.**

```bash
git add scripts/thermal-model-files.py openhab/scripts/test_thermal_deploy_files.py
git commit -m "feat: archive rejected thermal evidence in receipts"
```

---

### Task 6: Make the attended Gate A runbook v4-exact

**Files:**

- Modify: `docs/operations/thermal-model-shadow.md`
- Modify: `tests/deployment-service.test.js`

- [ ] **Write failing static contracts** for this exact order: prepare receipt; archive/read back v3; audit DB/role/runtime; install reviewed code; train/backtest privately; validate v4/v2 and every gate; stop before all publication/systemd actions unless separately approved.

- [ ] **Confirm RED.**

```bash
npx vitest run tests/deployment-service.test.js
```

- [ ] **Update the runbook.** Add before `install-code`:

```bash
python3 scripts/thermal-model-files.py \
  --receipt-dir "$FILE_RECEIPT" \
  archive-prior-v3
```

Read back `$FILE_RECEIPT/../prior-model-v3`. Update private checks for model v4, backtest v2, both new gates, equal model/persistence 24-hour counts of at least 30, at least two regime counts of at least five, manifest/fold provenance sums, and every old gate. Print reconstruction, valid-row, fold/regime, MAE, extrema, coverage, physics, and digest evidence.

```bash
jq -e '.schema == "earthship-thermal-model/v4" and .metrics.promotion.eligible == true' "$CANDIDATE"
jq -e '.schema == "earthship-thermal-backtest/v2"' "$BACKTEST"
jq -e '.metrics.promotion.gates.at_least_30_scored_24h_folds == true' "$BACKTEST"
jq -e '.metrics.promotion.gates.at_least_two_24h_regimes == true' "$BACKTEST"
```

Every shell fence remains `set -euo pipefail`. A false gate must terminate before shadow publication, OpenHAB Item writes, unit installation/start, or timer enablement. A pass requests Gate B; it does not authorize Gate B.

- [ ] **Validate static contracts and every Bash fence.**

```bash
npx vitest run tests/deployment-service.test.js
python3 - <<'PY'
from pathlib import Path
import re, subprocess, tempfile
text = Path("docs/operations/thermal-model-shadow.md").read_text()
blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.S)
for block in blocks:
    with tempfile.NamedTemporaryFile("w", suffix=".sh") as handle:
        handle.write(block); handle.flush()
        subprocess.run(["bash", "-n", handle.name], check=True)
print(f"validated {len(blocks)} bash fences")
PY
```

- [ ] **Commit the runbook contract.**

```bash
git add docs/operations/thermal-model-shadow.md tests/deployment-service.test.js
git commit -m "docs: stage private thermal v4 Gate A"
```

---

### Task 7: Complete verification and independent review

**Files:**

- Review: every path changed in Tasks 1-6
- Create: `.superpowers/sdd/thermal-v4-implementation-report.md` (ignored evidence only)

- [ ] **Run focused Python verification.**

```bash
pytest -q \
  openhab/scripts/test_thermal_solar.py \
  openhab/scripts/test_thermal_dataset.py \
  openhab/scripts/test_thermal_behavior.py \
  openhab/scripts/test_thermal_evaluation.py \
  openhab/scripts/test_thermal_artifacts.py \
  openhab/scripts/test_thermal_pipeline.py \
  openhab/scripts/test_thermal_publish.py \
  openhab/scripts/test_thermal_deploy_files.py
```

- [ ] **Run full project verification.**

```bash
pytest -q openhab/scripts/test_forecast_intel.py openhab/scripts/test_thermal_*.py
npm test
npm run build
npm run test:e2e
```

Expected: all suites pass; only already-known non-fatal build advisories may remain.

- [ ] **Run static/unit/repository checks.**

```bash
python3 -m py_compile openhab/scripts/thermal_intel.py openhab/scripts/thermal_model/*.py scripts/thermal-model-files.py
pyflakes openhab/scripts/thermal_intel.py openhab/scripts/thermal_model/*.py scripts/thermal-model-files.py
systemd-analyze verify deploy/thermal-model-train.service deploy/thermal-model-train.timer deploy/thermal-model-shadow.service deploy/thermal-model-shadow.timer
git diff --check
git status --short
```

- [ ] **Request an independent findings-first review** against the approved spec, this plan, and the exact branch diff. The reviewer must examine night/day/non-finite precedence, shared solar authority, digest/schema closure, scored-fold/regime reconciliation, preservation of old gates, receipt confinement/atomicity/modes/digests/no-fallback behavior, public v1 compatibility, and the no-actuation boundary.

- [ ] **Repair any Critical or Important finding test-first.** Reproduce it, patch narrowly, rerun affected and full verification, then request re-review until READY YES.

- [ ] **Write the ignored implementation report** with commits, paths, RED/GREEN evidence, final totals, reviewer verdict, private schema versions, and an explicit no-live/no-publish/no-systemd/no-automation attestation.

- [ ] **Verify final branch state.**

```bash
git status --short
git log --oneline --decorate -7
```

Expected: implementation commits are present and the tracked worktree is clean. Present the reviewed branch for integration. After integration and push, request fresh attended approval before executing private Gate A.

---

## Execution boundary

Completing this plan produces reviewed code and an attended Gate A procedure; it does not execute Gate A. A later attended run must reverify the repository revision, live PostgreSQL schema/role, current private artifact hashes, systemd state, runtime digests, and 400-day authority before mutation. Gate A may write only private training/backtest artifacts. Even a fully eligible v4 result stops for a separate Gate B decision.
