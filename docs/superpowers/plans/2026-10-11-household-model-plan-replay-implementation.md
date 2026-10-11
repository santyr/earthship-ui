# Household model-to-plan replay implementation plan

> **For agentic workers:** use superpowers:executing-plans inline. No implementer delegation. One whole-stage review after focused verification.

**Goal:** Rederive domain projections, model-derived shadow candidates and the complete coordinated plan from one bounded sealed receipt.
**Architecture:** Preserve exact production daily energy inputs as additive diagnostic state. Immutable numerical energy inputs and the existing verified prepared thermal context feed a pure shared-snapshot pipeline. The pipeline generates only existing-owner shadow proposals; unknown counterfactual effects remain unknown and cannot pass reserve gates. Replay recomputes projections and candidate generation before sealed decision replay.
**Tech stack:** Existing Python standard library and installed numerical runtime; no dependencies.
**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, phases 3, 4, 6, 7 and initial milestone. This stage advances that scope; live source qualification, outcomes and authority migration remain required separately.

## Global constraints

- Preserve exact existing energy equations and thermal trajectories; no refit or vent-effect calculations.
- One common frozen snapshot; model measurements must match its original rows and clocks. Measured mass is separate from latent model state.
- Missing models/sources stay unknown. Numerical replay does not certify bank epochs, calibration, causal effects or owner availability.
- No OpenHAB requests, provider commands, notifications, live installation or owner migration.
- All local verification serial, CPU20%, memory256MiB, swap0, tasks24, idle IO and numerical threads1; hosted broad tests.

## Review focus

- Cross-snapshot or different-SoC model input must refuse rather than blend decision states.
- Newly stale source/model cannot create eligible candidates from a previously valid prepared object.
- Modified trajectory or candidate set must fail rederivation even when the outer receipt is resealed.
- Unqualified model effects must not inherit baseline numerical confidence or acquire authority.
- Prepared thermal runtime must match the actual executing closure at CLI collection boundaries; pure replay performs no live reads.

## Task 1: Exact frozen daily energy inputs

Files: household/energy_model.py, forecast_intel.py, test_household_pipeline.py.
Interface: FrozenEnergyInputs(content:bytes), freeze_energy_inputs(**daily_energy_projection_arguments), project_energy(inputs).
- [ ] Write missing-API tests for all 72 golden cases and mutable/malformed input refusal; verify RED.
- [ ] Add closed finite bounded immutable mathematical input record. Preserve unknown SoC/cloud, up to three existing drop samples and positive capacity/efficiency. Qualification remains caller-owned and explicitly not assessed.
- [ ] Production caller freezes the same inputs, delegates the same equations, and retains the exact input record in its existing prediction state. Additive diagnostics only, no additional publication or file.
- [ ] Verify golden parity and existing forecast tests under caps; commit.

## Task 2: Shared model projections and generated shadow plan

Files: household/pipeline.py, test_household_pipeline.py.
Interface: seal_pipeline(snapshot,registry,energy_inputs,thermal_inputs,thermal_runtime,coordination,config,now,runtime_manifest), replay_pipeline(receipt,runtime_manifest,thermal_runtime).
- [ ] Write shared-state mismatch, original thermal parity, model-generated candidate, missing-source, unknown-effects and resealed-output refusal tests; verify RED.
- [ ] Closed config: horizon_hours6/12/24, reserve_soc10..100, low_trough_threshold_soc_pct10..100, surplus_weight0..100, reserve_weight0..100, comfort_min_f/comfort_max_f finite ordered within-50..150. Retain explicit objective units.
- [ ] Recompute frozen energy and thermal models, compare measured inputs to shared snapshot, generate existing greywater surplus and night-load OFF shadow proposals only from available current battery evidence. Effects remain all unknown; model baseline cannot qualify action response. Typed NO_ACTION retained separately as baseline.
- [ ] Recompute trajectories, candidate set, hard constraints and selected plan for complete receipt equality. Bounded1MiB, closed schema, source/runtime IDs sealed. Pure functions perform no file/DB/live reads.
- [ ] Verify focused and household suites; commit.

## Task 3: Private bounded CLI and actual retained evidence

Files: household_pipeline.py, test_household_pipeline.py, docs/operations/household-model-plan-replay.md, canonical progress tracker.
- [ ] Write special-file/private-file/runtime mismatch CLI tests; verify RED.
- [ ] CLI --receipt reads owned0600 regular file <=1MiB, computes actual runtime and thermal closure when present, rederives and rechecks before stdout; sanitized errors and no writes.
- [ ] Run retained original thermal context through shared-snapshot model/plan replay. Missing energy remains unavailable; do not invent historical battery evidence. Keep private originals/receipts outside Git.
- [ ] Focused caps, final immutable stage review, publish hosted CI. Full goal remains active until original scope is evidenced.
