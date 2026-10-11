# Expanded household power snapshot implementation plan

> Use superpowers:executing-plans inline and one final independent whole-branch review.

**Goal:** Advance Phase 2's canonical snapshot with original atomic battery/PV power and separately labeled inverter-output evidence, preserving original v1 receipts.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, Phases 1, 2 and 7.

**Architecture:** Add an immutable v2 snapshot and sealed source-bundle compiler without changing existing v1 source, snapshot or planner contracts. Recompile original v1 inputs at the final shared collection clock, reuse mature companion power/AC parsers for four new numeric roles, and carry every remaining required domain role as explicitly unavailable. Physical bank identity, whole-household load, forecast trajectories and owner availability are never inferred from power values. Model/planner adoption of v2 remains a subsequent required integration step; full PR #3 stays active.

## Constraints

Local work serial CPU20%, memory256MiB, swap0, tasks24, nice15, idle I/O and threads1. Fixed source Items only; 4096 original bytes per power receipt;15-second common collection deadline; read-only stable SQL and2-second statement/1-second lock deadlines. No actuation, new grants, owner migrations, training, vent calculations, credential changes or recovery work. Existing v1 bytes/identities remain reproducible.

## Task 1: Mature power adapters and immutable expanded snapshot

Create household/power_snapshot.py and test_household_power_snapshot.py. Compile original base inputs through the existing compiler. Source entries have fixed kind/Item identity, exact raw digest, original persistence clock and independently supplied software epoch. Preserve per-field observed/recorded/available/expiry clocks and units; field-specific unavailable/stale values remain unavailable. Expanded roles include energy, thermal, water, weather and authority/status requirements; unknown metadata/state/trajectories remain unknown. Completeness is capability-specific under explicit combined age/skew policies. Source bundle and complete snapshot seal/rederive deterministically with no I/O inside compiler/replay.

- [ ] RED then GREEN tests: qualified four-role power, partial fields, wrong epoch/digest/identity, NULL barrier, stale/expired/future clocks, capability skew, unavailable bank/load/authority, immutable originals, bounded inputs and resealed replay tampering.

## Task 2: Bounded source collector and actual qualification

Create household/power_capture.py. Read only fixed Power_Evidence_JSON and Inverter_AC_Evidence_JSON in dedicated read-only REPEATABLE READ transactions, unique Item mapping and latest-two bounded originals; newest NULL is retained, ambiguous ties refused. Compose the original collector with an outer15-second common deadline and finalize all roles at one shared clock.

- [ ] RED then GREEN fixed-query/deadline/invalid-row/closure tests and whole affected suite.
- [ ] Private actual capture using existing restricted credentials, independent current owner epoch receipts and existing native policies; exact original digest/readback and pure sealed replay. If actual roles withhold, retain that result without inferring qualification or granting new permissions.
- [ ] Update canonical progress, document v2 integration still required, commit and one final review. One Important/Critical TDD fix pass; Minor findings recorded.

## Review focus

Per-field age/expiry cannot be renewed by receipt persistence; software epochs cannot become physical bank epochs; inverter output cannot become household load; latest malformed/NULL rows cannot fall back to older values; nested collection cannot renew the common total deadline; old v1 receipts and original source manifests must not change; v2 is not silently treated as planner-authorized or fully source-complete.
