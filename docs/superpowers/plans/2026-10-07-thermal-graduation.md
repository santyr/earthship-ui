# Thermal forecast graduation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify and graduate the existing thermal forecast only when a frozen candidate wins on qualified independent untouched and prospective evidence.

**Architecture:** A versioned release contract wraps the existing immutable fit artifact. Source-bound qualification evidence drives one deterministic forecast/advisory decision, version 2 publication and rollback to a compatible shadow pair.

**Tech Stack:** Existing Python/SciPy thermal stack, native receipt readers, Svelte/Vitest UI, existing guarded deployment tooling.

**Spec:** `docs/superpowers/specs/2026-10-07-thermal-graduation-design.md`

## Global constraints

- PR #2 is merged; PR #3 household-planner architecture remains deferred.
- No WeatherNext/provider migration, automatic actuation, unsolicited messages or safety-policy changes.
- PV/SoC/temperature hardening remains diagnostic; existing equations stay unchanged.
- Source-bound raw evidence is authoritative; no reconstructed action becomes confirmed.
- Final holdout cannot inform thresholds or candidate selection; already inspected outcomes remain development data.
- Legacy artifact/publication schemas remain exact. New release schema is `earthship-thermal-release/v1`; production output is version 2.
- Forecast graduation and action-advice graduation have separate gates.
- Preserve the November no-vent default until the operator changes it.
- Protect the household host: only one small local check in verified CPUQuota=25%, MemoryMax=768M, MemorySwapMax=0, TasksMax=48, IOWeight=10 and nice15 scope; numerical threads1. Run full suites in CI; no manual model fitting on the household host.

## Review focus

- Missing, duplicate or changing source epochs must refuse release evidence.
- Dense or overlapping observations cannot inflate independent support.
- Revised forcing or late origin inputs cannot repair an issued forecast.
- Good pooled scores cannot graduate an insufficient single candidate/regime.
- Caller-supplied active flags, stale proof or incompatible runtime cannot bypass qualification.

## Task 1: Freeze and re-evaluate current qualified evidence

**Files:** `docs/operations/2026-10-07-thermal-graduation-reassessment.md`, `scripts/thermal_qualification_evidence.py`, `scripts/test_thermal_qualification_evidence.py`.

**Interfaces:** `summarize_pairs(pairs, *, horizon_hours, artifact_sha256=None)` returns paired MAE/RMSE/bias/coverage, independent UTC windows, local-day/regime/revision/source support. `verify_capsule(directory)` verifies the immutable acquisition manifest and original receipts/captures. No network or mutable registry access in replay.

- [x] Write boundary tests for non-overlap, revision stratification, native epoch qualification and altered capture/outcome refusal; observe RED.
- [x] Implement pure evidence accounting and immutable source verification using existing capture/native receipt contracts.
- [x] Reproduce the frozen October 7 reassessment; classify each existing blocker as closed, still_blocked, not_required_for_forecast_stage or required_for_advisory_stage. Record development-only status.
- [ ] Run focused evidence tests and the tooling suite, then commit.

## Task 2: Preregister a versioned policy and deterministic qualification

**Files:** `openhab/scripts/thermal_model/graduation.py`, `openhab/scripts/test_thermal_graduation.py`, `scripts/qualify-thermal-graduation.py`.

**Interfaces:** `derive_policy(development, *, declared_at, intervals, candidate, regimes)` produces an exact versioned policy, numerical thresholds and derivation references. `qualify(policy, evidence, fit_evidence, *, now)` produces a versioned report with every gate and recommended stage. Unsupported or insufficient data is a refusal, never a fabricated pass.

- [ ] Test missing policy, predeclaration after holdout, candidate/runtime/epoch mismatch, baseline loss, overlapping support, failed conditioning/stability and unqualified action evidence; observe RED.
- [ ] Derive numerical caps/support from independent development baselines and declared statistical precision. Require paired skill against both baselines; record all assumptions before final evaluation.
- [ ] Implement exact validation and deterministic per-horizon/regime qualification, separating forecast and advisory gates. Add forecast-qualified/advisory-ineligible and qualified confirmed-action cases.
- [ ] Generate matching machine/human reports; run focused tests and commit.

## Task 3: Improve and freeze the actual thermal candidate

**Files:** Existing `thermal_model/dynamics.py`, `pipeline.py`, `evaluation.py` and focused thermal tests only if a demonstrated development defect warrants a change; versioned candidate fit evidence and private source-bound development snapshots.

**Interfaces:** A frozen artifact/runtime and explicit independent-day conditioning/stability report consumed by Task 2. No final holdout outcomes enter fitting or selection.

- [ ] Trace current errors using original forcing/origin state and native outcomes; keep action assumptions as issued.
- [ ] If development evidence identifies a useful change, add a meaningful failing test, implement the narrow change and evaluate chronologically on development data.
- [ ] Freeze candidate, runtime and policy before untouched evaluation. Persist all identified sensor/hardware epochs.
- [ ] Run dynamics/artifacts/pipeline/replay suites; commit any source change with development evidence. If support is insufficient, record it and continue remaining engineering.

## Task 4: Versioned production publication and honest UI

**Files:** `thermal_model/release.py`, `thermal_intel.py`, production-output tests, `src/lib/thermal/modelResult.js`, `src/lib/ui/ThermalModelCard.svelte` and their existing tests.

**Interfaces:** `build_release_output(shadow, release, *, now, runtime_revision, sensor_epochs)` returns validated version 2 output. Production modes derive from Task 2 gates. Original v1 validation remains unchanged.

- [ ] Test invalid shadow-to-active transitions and old-reader refusal, explicit unavailable output, stale model/sensors/proof, missing forcing, physical/finite failures and action-ineligible forecast mode; observe RED.
- [ ] Implement version 2 validation and bounded publication with independent baseline/prospective capture continuing. No actuator calls.
- [ ] Update the UI to show validated mode, forecast/action confidence, revision, freshness and intervals; test truthful badges and stale/invalid fallback.
- [ ] Run publication/UI suites and build, then commit.

## Task 5: Tested rollback and prospective withdrawal

**Files:** Existing guarded thermal deployment tooling, compatible runtime/artifact inventory tests, `scripts/rollback-thermal-release.py`, rollback tests and graduation runbook.

**Interfaces:** An immutable receipt binds prior compatible shadow runtime/artifact/output and release reasons. Withdrawal uses current prospective baseline/calibration evidence and source compatibility, independent of household safety alerts.

- [ ] Test active-to-shadow rollback, incompatible pairs, corrupt artifact/proof, source epoch drift, prospective baseline regression and interrupted restore; observe RED.
- [ ] Implement deterministic guarded rollback and release withdrawal. Preserve credentials and prior shadow behavior.
- [ ] Rehearse in private staging with real file transactions/restored journal, run deployment and rollback suites, then commit.

## Task 6: Qualification, CI and staged production decision

**Files:** Final JSON/Markdown qualification report, runbook, PR/merge record and private rollout receipts.

**Interfaces:** All Tasks 1–5 feed the same deterministic decision. Neither a UI badge nor an artifact file enables production.

- [ ] Run normal CI, ML hardening, thermal delivery, dynamics/artifacts/pipeline, qualification, prospective scoring, restored-journal, deployment/UI/rollback checks.
- [ ] Review the complete branch; correct material findings with RED/GREEN evidence. Merge only with passing required checks.
- [ ] If real release gates pass, deploy Stage A with parallel baseline scoring and verify natural publication; Stage B only if separate action gates pass.
- [ ] If physical evidence is insufficient, keep activation closed and state exact missing independent frozen-candidate/regime/action observations. Do not claim this goal achieved merely from code/CI completion.
