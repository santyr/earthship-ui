# Native model verification receipt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user already chose inline execution; do not dispatch an implementer or reviewer for each task.

**Goal:** Deploy the provisional native ML model for monitoring within the existing local limits by admitting its numerical validation once and freshly checking its exact dependencies on each serving cycle.

**Architecture:** An externally pinned, owned verification receipt binds one fully replayed candidate, its four originals and its executing source/runtime closure. An opaque serving context reuses only that numerical admission; explicit serving APIs still rederive current forecasts, deliveries, household projections and mature outcomes. The owned stage and effective service commands select the receipt; original full-replay APIs and historical selections remain independent.

**Tech Stack:** Existing Python3/NumPy/SciPy, native Astro Java collector, JSON evidence, pytest, OpenHAB read/persisted-receipt transport and systemd user units. No new dependency, credential or database table.

**Spec:** `docs/superpowers/specs/2026-10-13-native-model-serving-receipt-design.md` (written design approved October13).

## Global Constraints

- CPU at most20%; memory256MiB; swap0; tasks24; nice15; idleIO/IOWeight10; one numerical thread (`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`). Scientific jobs serialize with the original shared lock.
- Preserve five-second headroom admission, PSI/OOM/swap-out checks, trailing-one-second1MiB native-inference swap-read allowance,75-second preparation limit,90-second service limit and all issue/availability/publication deadlines. Fitting policy stays unchanged.
- Preserve all72 fitted sources and all nine `native_thermal_artifact.REQUIRED_SOURCES` byte-for-byte. Modify only OPTIONAL native adapters and outside-fitted integration code; bind the new helper through literal SHA256 pins in all three OPTIONAL sources and the stage manifest.
- Receipt schema is `earthship-native-model-verification-receipt/v1`; files0600/directories0700, closed bounded JSON, atomic create-without-replacement. Candidate cap131072bytes; receipt cap131072bytes; original caps remain `native_thermal_artifact.LIMITS`.
- No cached forecast, action state, outcome, geometry for another issue, permission, kernel reading, acquisition timestamp or source-freshness decision. Never substitute current model selection for historical selection.
- Original candidate/origin/forecast/delivery/score schemas, numerical outputs and capture identities remain unchanged. Receipt-to-cycle association is a separate audit record.
- No confidence graduation, notification, live owner migration or device authority. Retain the signed-off root UI overlay, original source archives and legacy pending queues. Recovery/backup work stays deferred.
- Existing v1 and v2 configuration callers retain full replay. Add explicit `earthship-provisional-thermal-live-config/v3` for receipt serving; no implicit fallback after a receipt refusal.
- Final deployment digest is outside the receipt. Owned effective service commands carry `--deployment-sha256`; final stage binds the receipt's exact external digest. Do not put the final deployment digest inside its own hashed record/config.
- The broader goal scope and GitHub publication-payload questions remain pending. This plan neither reduces the canonical goal nor grants external publication.

## Review Focus

- A resealed receipt/config/stage selected through an arbitrary caller digest must not replace the independently pinned effective selection (Task1/4).
- A dependency replaced with same-size bytes and restored mtime, or swapped during publication, must withhold serving despite earlier admission (Task1/2).
- A historical capture from a different model, source archive or sensor epoch must use its own retained selection; the active receipt must not qualify it (Task3).
- A legacy queue backlog must remain scheduled after native activation; native refusal must not silently become another model's forecast/score (Task3/4).
- Partial delivery or changed original bytes between the two receipt readbacks must not qualify a household cache, score or successful activation proof (Task2/5).

---

## Verification runner and source map

At execution start resolve this plan's workspace with the existing `sdd-workspace` helper. Its expected path is `.superpowers/sdd/2026-10-13-native-model-serving-receipt`; refer to it as `QA` below. Initialize its ledger with this plan path. Retain earlier plan evidence in its existing directories.

Create `QA/run_receipt_tests.py` as a stdlib-only launcher. It launches one child in a CPU20%/Mem256MiB/swap0/tasks24/nice15/idleIO/IOWeight10 systemd scope with one numerical thread, the existing test venv, an85second test-worker deadline, the real sharedML lock and the existing quiet-host guard. Admission is bounded240seconds and requires both original workers' MainPID0 and at least130seconds before their next issue. Save exact exit/output and cgroup memory/OOM evidence in this workspace. A guard refusal is not a failing assertion and does not justify relaxing a limit. Commands below use this runner, never bare numerical pytest.

Use the existing branch `feat/household-common-cycle-20261012`, starting at `ce91b3b`; verify its clean status and preserve other branches/root edits. Source map:

- New `openhab/scripts/native_model_serving_receipt.py`: admission, owned selection, receipt readback, immutable serving context and fresh binding rechecks.
- OPTIONAL `native_thermal_forecast.py`, `native_thermal_live.py`, `native_thermal_score.py`: additive serving APIs using shared numerical and source-validation cores; existing full APIs keep their contract.
- `household_cycle.py`, `household/thermal_model.py`, `household/weather_context.py`: explicit serving-context propagation through delivered-forecast/household preparation; offline APIs retain full replay.
- `household_forecast_score.py`: explicit native receipt and retained legacy/historical score selection and bounded scheduling.
- `household_cycle_deploy.py`, `household_native_family.py`, `household_native_handoff.py`, `household_native_install.py`, `household_native_geometry_prepare.py`: externally pinned source-backed packaging, effective selection and existing transactional handoff.

Fixture setup for Tasks1–3 reuses `test_native_thermal_artifact.originals`, its `fixture`/`candidate` builders and `test_native_thermal_forecast.context`; serving fixtures add a fully sealed owned fixture stage and admitted receipt. Assertion snippets below belong to their named test steps. Existing independent validation remains the fixture oracle, not a mocked replacement.

### Task 1: Numerical admission and immutable serving selection

**Files:** Create `openhab/scripts/native_model_serving_receipt.py` and `openhab/scripts/test_native_model_serving_receipt.py`; modify literal helper pins in the three OPTIONAL adapters and receipt-profile reading in `household_cycle_deploy.verify_stage`. Task4 adds package construction and effective-command rendering. Do not edit the fitted artifact validator.

**Interfaces:** `admit_model(candidate_path: Path, *, runtime: dict, expected_artifact_sha256: str, directory: Path, clock: Callable[[], datetime], guard: Callable) -> Path`; `load_serving_selection(stage: Path, *, expected_deployment_sha256: str, assessed_at: datetime, guard: Callable) -> OwnedServingSelection`; `read_serving_model(selection: OwnedServingSelection, *, assessed_at: datetime, guard: Callable) -> ServingModel`. Context exposes copied `candidate`/`runtime` properties and `verify_bindings(*, assessed_at, guard) -> None`. Public constructors refuse; neither caller dictionaries nor serialized receipt fields create these types.

- [x] Write `test_receipt_admission_requires_full_replay_and_stable_originals`, `test_unchanged_receipt_reads_all_dependencies_without_numerical_replay` and parametrized refusal cases. Assert full `read_native_candidate` is called during admission; serving omits numerical replay but reads the candidate, all four originals, interpreter/dependencies and source/helper bindings freshly. Mutating an original during admission produces no receipt.
```python
assert model.candidate == independently_validated_candidate
assert full_validator_calls_after_serving == full_validator_calls_after_admission
assert set(fresh_original_roles) == {"snapshot", "dataset", "geometry", "fit_evidence"}
with pytest.raises(TypeError):
    ServingModel()
```
- [x] Run `python3 QA/run_receipt_tests.py openhab/scripts/test_native_model_serving_receipt.py`; require genuine missing-interface/assertion RED, not resource admission refusal.
- [x] Add receipt-profile stage reading for the selection factory: preserve existing v1/v2 stage fields, and define v3 as v2 plus closed `model_verification` (receipt path/SHA, helper path/SHA) and `score_dispatch` (owned record path/SHA). The external deployment SHA pins the entire closed stage; validate the current source manifest, originals/config/candidate and those new references. Task1 tests create complete owned fixture stages directly; Task4 constructs them operationally. Require the complete staged source closure to match freshly read bytes before minting a selection.
- [x] Implement the interfaces. Receipt fields bind verified time, validator profile, candidate path/exact bytes/artifact/runtime, the four paths/digests/caps, model rule/fit/sensor epochs and complete executing source/helper/interpreter binding. Check closed schema, exact externally pinned SHA, bounded owned reads, chronology (`candidate.created_at <= verified_at <= assessed_at`), finite physical coefficients and unchanged false-authority flags. Mint a context only after every fresh comparison succeeds. Receipt issuance uses full replay once plus before/after byte/runtime comparisons; set `verified_at` from the fresh completion clock after successful replay, then perform atomic0600 readback, with no self-issued final-stage authority.
- [x] Add and run tamper/refusal tests for resealing against the original pin, duplicate/nonfinite fields, future time, helper/interpreter/source drift, missing originals, restored-mtime/same-size replacement, symlink/hardlink/permission changes and fabricated constructors/dictionaries. Assert both binding rechecks reject drift. Run the unchanged original `test_native_thermal_artifact.py` numerical-tampering regressions in a separate capped batch.
- [x] Commit the helper, its tests and literal pins only; ledger exact RED/GREEN results and verify72+9 source hashes against the retained admitted model.

### Task 2: Receipt serving for preparation, publication and household completion

**Files:** Modify `native_thermal_forecast.py`, `native_thermal_live.py`, `household_native_geometry_prepare.py`, `household_cycle.py`, `household/thermal_model.py`, `household/weather_context.py`; extend their existing native tests and create `test_native_serving_forecast.py`.

**Interfaces:** Add `build_serving_capture(model: ServingModel, inputs: dict, *, geometry, expected_geometry_sha256, issue, available, published, check_budget, monitoring_report=None) -> dict`, `validate_serving_capture(value: dict, model: ServingModel, *, expected_capture_sha256, check_budget) -> dict`, and `read_serving_capture(path: Path, model: ServingModel, *, expected_capture_sha256, check_budget) -> dict`. Add keyword `serving_model=None` only to outside-fitted cycle/preparation orchestration; explicit v3 must supply a verified context. Add `prepare_serving_native_projection(capture, model, *, code_revision, expected_capture_sha256, check_budget) -> PreparedProjection` and `prepare_serving_native_cycle_contexts(capture, model, *, code_revision, expected_capture_sha256, check_budget) -> (PreparedProjection, PreparedWeatherContext)`.

- [x] Write `test_serving_and_full_forecasts_and_household_replay_are_identical`, `test_serving_drift_between_persisted_receipts_withholds_completion` and `test_v2_public_replay_still_rejects_resealed_numerical_damage`. Assert complete trajectories, compressed source binding, geometry, publication, captured bytes/identity and household outputs equal the existing full path.
```python
assert serving_capture == full_capture
assert serving_household_output == full_household_output
assert serving_capture["output"]["automatic_actuation"] is False
assert writes_after_dependency_drift == []
```
- [x] Run the new tests through the capped runner and observe genuine RED.
- [x] Extract private shared capture/validation cores so existing full APIs always use `_candidate`/full validation, while additive serving APIs accept only the opaque context and match its exact candidate/runtime. Reuse `_numeric`, geometry replay, compressed temperature lineage, delivery checks and existing projection equations. In explicit v3, admit one fresh context at each preparer/forecast cycle; retain fresh kernel/source guards throughout and recheck full selected bindings before each write and after delivery. Never expose a boolean/dict bypass in public replay APIs.
- [x] Add v3 loader fields `model_receipt_path` and `model_receipt_sha256` to the original native fields; receipt path must be resolved owned private storage. The externally pinned stage creates the selection; caller configuration alone does not. Pass that context through full household completion, including fresh source/runtime checks, rather than reintroducing candidate replay after delivery. Keep receipt audit association outside the capture body. Refusal and withdrawal use the current bounded logic with no stale context or fallback.
- [x] Run `test_native_serving_forecast.py`, native forecast/publication/geometry tests, `test_household_native_cycle.py`, `test_household_native_cycle_driver.py`, `test_household_native_thermal.py` and `test_household_native_weather.py` in serial batches <=85seconds. Verify original independent replay still catches altered predictions/geometry/inputs and November vent defaults remain unchanged. Commit; ledger exact comparisons and72+9 hash evidence.

### Task 3: Historical and mature outcome scoring without reselecting a model

**Files:** Modify `native_thermal_score.py`, native scoring sections of `native_thermal_live.py`, `household_forecast_score.py`; create `test_native_serving_score.py` and extend existing source/completion/report/coordinator tests.

**Interfaces:** Add `score_serving(capture, model: ServingModel, receipts, outcome, *, expected_capture_sha256, horizon_hours, assessed_at, recent, check_budget) -> dict`. Add `build_serving_source_score(*, model, capture_path, receipts, outcome, recent_cycle_grid, source_paths, horizon_hours, assessed_at, expected_capture_sha256, check_budget) -> dict` and `validate_serving_source_score(record, *, model, expected_capture_sha256, expected_source_score_sha256, check_budget) -> dict`. Add `build_serving_source_completion(source_score_path, *, model, expected_capture_sha256, expected_source_score_sha256, completed_at, check_budget) -> dict`, `validate_serving_source_completion(completion, *, model, expected_capture_sha256, expected_completion_sha256, check_budget) -> dict` and `reconcile_serving_source_report(entries, *, selections, artifact_sha256, assessed_at, check_budget) -> dict`; `selections` is a tuple of externally verified owned historical selections. Readback functions retain the existing byte reader and call these explicit validators. Original source-score/completion schemas remain unchanged. `read_serving_model` is reused for each explicitly retained historical selection; it cannot validate another candidate's capture.

- [x] Write `test_serving_score_source_completion_and_report_equal_full_replay`, `test_old_capture_cannot_use_active_receipt`, `test_missing_historical_receipt_qualifies_no_outcome` and `test_legacy_backlog_keeps_explicit_scheduled_opportunities`. Assert unchanged scores/identities, retained raw outcome and persisted-delivery provenance, exact target clocks, sensor epochs, maturity and baselines; fake receipts and missing outcomes qualify nothing.
```python
assert serving_pair == full_pair
assert serving_source_score == full_source_score
assert serving_completion == full_completion
assert old_capture_with_active_receipt_qualified is False
assert legacy_scheduled_slots == (1, 3)
```
- [x] Run those tests and observe genuine RED.
- [x] Share existing arithmetic and per-issue/source/query/completion reconciliation cores; use serving capture replay only with that capture's exact retained context. Keep original `score`, source-score, completion and independent offline readers on full replay. Retain bounded inventories, missing-outcome retries and old original archives; never score an old capture using current selection.
- [x] Add a closed owned score-dispatch record to the family, binding the retained legacy stage/config and explicit historical native selections. The current native role is the literal `current` and inherits the effective command's external deployment pin; its record does not contain its own final deployment digest. Assign original score timer slots minute%5 in(0,2) to native and(1,3) to the retained v1 worker. Each invocation runs at most one original job under its existing lock/guard/deadline; no parallel job and no timeout increase. A refused native receipt never triggers a legacy fallback in that invocation. Keep retained historical native selections explicit and source-pinned; absence withholds their job.
- [x] Run new tests plus existing native score/source/completion/paired-reader and both native/legacy queue/coordinator regressions in bounded serial batches. Verify full source-backed replay and source drift refusal remain independent. Commit and ledger the scheduling/parity results.

### Task 4: Final stage, external pins and transactional handoff

**Files:** Modify `household_cycle_deploy.py`, `household_native_family.py`, `household_native_handoff.py`, `household_native_install.py`, CLI entry points in preparer/cycle/scorer; extend native deployment/family/handoff/install tests and create `test_native_serving_selection.py`.

**Interfaces:** Extend `stage_deployment(..., model_receipt_path: Path | None=None, model_receipt_sha256: str | None=None)` with explicit receipt profile; `verify_stage(stage, *, expected_deployment_sha256: str | None=None) -> dict` preserves old profiles but requires the external pin for receipt serving. Render all v3 effective commands in the family's unit files, outside the final deployment manifest, with `--deployment-sha256 <final SHA256>`; cycle/preparer/scorer CLIs pass this pin to `load_serving_selection`. The final stage hashes an inert command template without that final digest; a v3 command cannot serve without the external pin. The family produces its own `forecast.conf` from the sealed template after the deployment digest exists. The handoff installs that family file instead of executing the unpinned stage template. Final family/handoff/installer records bind the receipt and explicit score-dispatch record in addition to existing source/config/library/previous-selection refs.

- [ ] Write `test_resealed_stage_or_config_cannot_replace_effective_selection`, `test_all_three_effective_commands_pin_one_final_stage`, `test_helper_and_receipt_in_complete_source_closure`, `test_handoff_retains_legacy_score_selection` and existing partial-install/source-drift cases extended to v3. Assert the untrusted caller's newly computed digest is never accepted as an already installed effective pin.
```python
with pytest.raises(ValueError):
    verify_stage(resealed_stage, expected_deployment_sha256=original_effective_pin)
assert set(effective_command_deployment_pins) == {final_deployment_sha256}
assert all(digest == retained_digest for digest, retained_digest in protected_hash_pairs)
```
- [ ] Run new and affected deployment/family/handoff/install cases and observe RED.
- [ ] Implement two-phase packaging: commit exact code and construct a runtime-bound candidate from retained fit; perform guarded production-interpreter full admission using a bootstrap v2 package; issue the receipt; then build final v3 config/stage/family using identical code/candidate/original bytes. Final deployment includes the externally pinned receipt digest and dispatch record; family-rendered effective commands pin final deployment after sealing. Neither the manifest's hashed command template nor the dispatch record contains the final digest, so the stage digest does not depend on itself. Do not insert final-stage identity into the receipt or hashed record itself. Verify before/after source and original bytes at admission, staging and activation.
- [ ] Update runtime qualification to verify the receipt path explicitly under the production interpreter. Keep full admission and original independent verifier available; every receipt-backed runtime check still freshly rehashes its complete dependencies. Extend effective-family checks to exact pins and both explicit scorer selections. Preserve existing inactive-service admission, timer quiescence, owned file replacement, reload/enable reconciliation and rollback semantics; no new recovery project.
- [ ] Run affected deployment/family/handoff/install/preparer/coordinator cases through the capped runner. Verify all effective limits and source pins, refusal before timer quiescence on failed qualification and unchanged72+9 hashes. Commit and ledger exact head/results.

### Task 5: Exact timing, natural production evidence and final review

**Files:** Update `docs/operations/2026-10-13-native-preparer-deadline-diagnosis.md` and `docs/operations/household-program-progress.json`; create only private `QA` scripts/receipts/logs for source-backed timing and activation. Product changes belong to Tasks1–4.

**Interfaces:** Use the existing staged preparer/cycle driver and transactional handoff APIs with the qualified v3 family and effective external pins. Every probe records exact commit/artifact/runtime/stage/receipt SHA, terminal exit, cold wall time, completed native batches, guard/cgroup evidence and whether any live write occurred.

- [ ] Produce actual production-interpreter full receipt admission and fresh serving readback from the four retained originals; verify numerical candidate equality and source closure. Run one final fresh-context whole-branch review under executing-plans, address Important/Critical findings in one RED-to-GREEN correction pass and rerun the affected suite; refresh literal pins/stage/receipt for changed bytes. Do not skip review or reuse a receipt from older code.
- [ ] Run the exact staged preparer from cold startup under75seconds, original caps/guards/issue margin and actual lock. Record genuine288-point geometry completed before collection. A failed guard/deadline retains diagnostics and withholds activation; no speculative extra path optimizations or longer budget.
- [ ] Run the actual staged production driver at the original30-second warm window with a barrier intercepting every telemetry write, including withdrawal, before transport. Verify source collection completes by issue and serving forecast computation reaches the first intercepted write within the original publication deadline. Stop before transport; retain the frozen proposal and measured clocks. Full household completion timing is qualified on the later natural persisted delivery, since the read-only probe cannot create its required receipts. A private successful calculation does not fabricate deliveries, a cache publication or operational success.
- [ ] Use the already authorized owned transactional shadow handoff only after all exact-stage proofs pass. Keep full caps/effective pins, existing forecast/score timer opportunities and explicit legacy scoring selection. Observe a natural forecast, independently persisted numeric/main receipts, source/capture delivery readback and household/cache replay. Verify live UI fresh/expired handling without changing the root overlay. Wait for mature natural as-issued outcomes and qualify retained source-score/completion/report parity; do not treat horizon counts as independent days or claim native accuracy improvement from training rows.
- [ ] Update canonical evidence from actual terminal results. Audit this spec requirement-by-requirement; receipt deployment is complete only after actual timing, activation, natural delivery/household/UI and mature scoring proofs. Keep all other PR3 requirements and scope questions visible. Commit intended source/evidence locally. Do not push or alter shared PRs without the separately pending exact-publication approval.

## Plan self-review

Spec coverage: receipt/authority/closure and fresh bindings are Task1/4; unchanged independent model replay, forecast/source/household parity and current input guards are Task2; historical selections, raw outcomes and legacy backlog are Task3; all caps/timing/activation/natural delivery/mature scoring are Task5. All five Review Focus conditions have named regression tests. Serving APIs accept `ServingModel` consistently; owned selection is the only model reader input. New profile and helper are outside the72+9 fitted closure. Final digest never self-binds: pinned commands are family outputs outside the stage manifest, and the current score-dispatch role inherits the external pin rather than embedding it. Existing inline execution remains selected. Written implementation plan approved October13; execute inline under the retained constraints.
