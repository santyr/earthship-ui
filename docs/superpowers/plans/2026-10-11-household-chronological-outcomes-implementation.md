# Household chronological outcomes implementation plan

> **For agentic workers:** use superpowers:executing-plans inline, TDD and one whole-stage read-only review.

**Goal:** Score retained delivered thermal forecasts in household plan receipts against later native source-qualified outcomes and replay every score offline.
**Architecture:** A preparation boundary verifies original archive plus exact numeric/main persisted receipts. The pure scorer binds that origin to rederived household model/plan state, selects exact later native-v2 targets with the existing strict reader, and retains all original outcome packets. Summaries count conservative daily evidence units without claiming independence or causal effects.
**Tech stack:** Existing Python, native-v2 reader, provisional origin/delivery validators; no new dependencies.
**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, phase7 outcome scoring and phase10 chronological evidence. Energy night-minimum scoring, policy/action outcomes and release qualification remain required later.

## Global constraints

- Preserve original issue/artifact/runtime/sensor identities; no revised UI forecast may replace an original delivered forecast.
- Five-minute maturity delay; wrong/future/unsupported targets or sensor epochs refuse, missing source remains unavailable.
- Thermal air outcomes only; measured mass cannot score latent model state. A single SoC point cannot score a predicted overnight minimum.
- Model and persistence errors are diagnostics under actual household behavior, not action benefit or deterministic-policy advantage. No causal effect/graduation/actuation claim.
- Serial CPU20%, memory256MiB, swap0, tasks24, idle IO, numerical threads1; broad hosted CI.
- No new live transport, production service, write/notification/owner migration or recovery work.

## Review focus

- Changed persisted delivery must refuse even if the preparation envelope is resealed.
- Model/receipt/sensor phase mismatches must never enter a scored cohort.
- Missing/native null barriers must not become zero errors or empty successful samples.
- Repeated rolling forecasts or duplicate reassessments must not inflate evidence counts.
- New scoring code must verify the exact retained plan closure; it cannot accept an incomplete source manifest merely to replay an old plan.

## Task 1: Delivered origin and source-qualified score

Files: household/outcome_origin.py, household/outcomes.py, test_household_outcomes.py.
Interfaces: PreparedOutcomeOrigin(content), prepare_outcome_origin(capture,receipts,code_revision); seal_outcomes(plan_receipt,origin,outcome_sources,assessed_at,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime); replay_outcomes(...).
- [ ] Write failing tests for unchanged original delivery, mature native truth, wrong epoch/stream/policy/clock/target, future/missing/barrier inputs and changed derived scores.
- [ ] Preparation verifies originals using existing prepare_projection and validate_delivery. Pure immutable envelope retains numeric/main raw persisted receipts and expected publication, checks exact output and bounded original delivery clocks.
- [ ] Recompute plan then model/target binding. Fixed supported1/6/12/24h within planner horizon. Per-target native packets <=128KiB, <=128 rows, one exact target, strict source policy and original sensor epoch; assessed clock exact. Missing or not-yet-mature states remain explicit.
- [ ] Retain model/persistence predictions, source truth, signed/absolute errors and hourly comfort diagnostics. Energy/owner-policy/action-feasibility/counterfactual outcomes explicitly unavailable. Sealed complete receipt <=4MiB, no reads inside scoring/replay.
- [ ] Focused caps and commit.

## Task 2: Conservative chronological summaries

Files: household/outcomes.py, test_household_outcomes.py.
Interface: summarize_outcomes(receipts,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime).
- [ ] Test duplicate original issue/horizon rejection, reassessment duplication, changed score refusal and mixed artifact/sensor revision rejection.
- [ ] Max32 receipts/8MiB; replay each. Group thermal errors by original issue local date, model/runtime and sensor epoch. Report raw pair count, unique daily units, daily-unit MAE/bias, observation target coverage and explicit independence_assessed=false. No confidence intervals or release gate inferred from count.
- [ ] Focused caps and commit.

## Task 3: Private CLI and actual archived outcome proof

Files: household_outcomes.py, test_household_outcomes.py, docs/operations/household-chronological-outcomes.md, canonical progress tracker.
- [ ] Test owned0600/special-file/refreshed-runtime refusal and complete score replay with actual source closure.
- [ ] CLI --receipt reads bounded private original score, checks full scoring and original planning dependencies plus thermal closure, rederives and rechecks before stdout; sanitized errors, no reads inside pure boundary.
- [ ] Verify one actual archived delivered forecast and acquire only fixed mature native endpoints through existing bounded read-only readers. Retain private originals and score receipt. Current household-plan evaluation is retrospective from the original delivered forecast; do not call it an as-issued production planner decision.
- [ ] Household/forecast focused suite, immutable final review, hosted validation/publish; full goal remains active for all outstanding original-scope requirements.
