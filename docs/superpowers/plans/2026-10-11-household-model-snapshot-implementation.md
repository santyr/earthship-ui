# Source-bound expanded model snapshot implementation plan

> Use superpowers:executing-plans inline, then one independent whole-branch review.

**Goal:** Connect the expanded original-source snapshot to pure energy/thermal projections, typed shadow intents and deterministic plan replay, with explicit retained thermal artifact/confidence metadata.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, Phases2/3/4/7.

**Architecture:** An explicit model-bound snapshot wraps the unchanged original power snapshot and, when present, an existing strongly prepared original thermal projection. The common clock is the thermal origin; original source facts must have been available before that clock and are reassessed under retained age/skew bounds. Original thermal measurements come from the verified prepared capture, not a later mutable source or numerical equality alone. Retained artifact identity/confidence are metadata, not physical-source or causal qualification. All models/intents/plan use the same new immutable identity. V1 output and replay branches stay byte-compatible.

## Constraints

Serial CPU20%, memory256MiB, swap0, tasks24, nice15, idle I/O, threads1. No fitting, forecast/actuator publication, owner migration, new grants, credential/vent calculation/recovery changes. Source/context and pipeline receipts bounded1MiB; snapshot content bounded256KiB. No past clock is invented for a later source snapshot. Physical bank/load/weather/owner qualification remains full-scope required work.

## Task1: Immutable source/model binding

Create household/model_snapshot.py and tests. Replay the original power receipt, retain its snapshot/receipt identities, derive exact original provisional thermal context from PreparedProjection, overlay its three original temperature evidence rows at its origin, and reassess other sources at that common clock. Snapshot creation follows all actual context availability. Expose retained artifact hash and low confidence, explicitly unavailable when no model. Source/model descriptors and derived root reconstruct deterministically. Unknown or expired sources stay unknown; no source epoch or causal confidence is inferred.

- [ ] RED then GREEN: available-model metadata, missing model, future source/context refusal, original measurement provenance/clock binding, expired source handling, immutable content, forged/resealed descriptor refusal and numerical thermal parity.

## Task2: Pure model/intent/plan replay integration

Update version dispatch in pipeline/intents/planning and original CLI closure validation. New model-bound snapshots are explicitly supported; original v1 behavior is unchanged. Energy SoC and thermal context must match the same identity/clock/source rows. Plan replay restores the correct snapshot type. Metadata cannot be used as a qualified physical-source action reference. Private pipeline replay verifies original complete source context and executing model code; no mutable reads inside projection/planning.

- [ ] RED then GREEN: expanded energy proposals/replay, unavailable model path, original thermal parity and same-snapshot rederivation, stale source rejection, identity/runtime/resealed output tampering, unchanged v1 receipt outputs and disabled translator.
- [ ] Run full affected suite under serial caps.
- [ ] Actual current original source/model capture/replay using normal publisher evidence and retained packets, without starting any publisher. Record incomplete source/owner facts honestly.
- [ ] Commit, one independent review and one Important/Critical TDD fix pass. Hosted checks gate merge; full PR #3 remains active.

## Review focus

Later power data cannot be backdated to an earlier thermal origin; original measured mass cannot replace latent model mass; original measurement provenance must survive overlay; metadata confidence cannot qualify action effects or physical source references; snapshot identity/version must restore through both nested plan and pipeline; original v1 branch output must remain identical; model-bound context must not silently claim full energy/owner readiness.
