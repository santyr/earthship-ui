# Expanded household power snapshot implementation plan

> Use superpowers:executing-plans inline and one final independent whole-branch review.

**Goal:** Advance Phase 2's canonical snapshot with original atomic battery/PV power and separately labeled inverter-output evidence, preserving original v1 receipts.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, Phases 1, 2 and 7.

**Architecture:** Add an immutable v2 snapshot and sealed source-bundle compiler without changing existing v1 source, snapshot or planner contracts. Recompile original v1 inputs at the final shared collection clock, reuse mature companion power/AC parsers for four new numeric roles, and carry the represented remaining domain roles as explicitly unavailable; accepted thermal artifact identity/confidence remain a recorded schema omission. Physical bank identity, whole-household load, forecast trajectories and owner availability are never inferred from power values. Model/planner adoption of v2 remains a subsequent required integration step; full PR #3 stays active.

## Constraints

Local work serial CPU20%, memory256MiB, swap0, tasks24, nice15, idle I/O and threads1. Fixed source Items only; 4096 original bytes per power receipt;15-second common collection deadline; read-only stable SQL and2-second statement/1-second lock deadlines. No actuation, new grants, owner migrations, training, vent calculations, credential changes or recovery work. Existing v1 bytes/identities remain reproducible.

## Task 1: Mature power adapters and immutable expanded snapshot

Create household/power_snapshot.py and test_household_power_snapshot.py. Compile original base inputs through the existing compiler. Source entries have fixed kind/Item identity, exact raw digest, original persistence clock and independently supplied software epoch. Preserve per-field observed/recorded/available/expiry clocks and units; field-specific unavailable/stale values remain unavailable. Expanded roles include energy, thermal, water, weather and authority/status requirements; unknown metadata/state/trajectories remain unknown. Completeness is capability-specific under explicit combined age/skew policies. Source bundle and complete snapshot seal/rederive deterministically with no I/O inside compiler/replay.

- [x] RED then GREEN tests: qualified four-role power, partial fields, wrong epoch/digest/identity, NULL barrier, stale/expired/future clocks, capability skew, unavailable bank/load/authority, immutable originals, bounded inputs and resealed replay tampering.

## Task 2: Bounded source collector and actual qualification

Create household/power_capture.py. Read only fixed Power_Evidence_JSON and Inverter_AC_Evidence_JSON in dedicated read-only REPEATABLE READ transactions, unique Item mapping and latest-two bounded originals; newest NULL is retained, ambiguous ties refused. Compose the original collector with an outer15-second common deadline and finalize all roles at one shared clock.

- [x] RED then GREEN fixed-query/deadline/invalid-row/closure tests and whole affected suite.
- [x] Private actual capture using existing restricted credentials, independent current owner epoch receipts and existing native policies; exact original digest/readback and pure sealed replay. If actual roles withhold, retain that result without inferring qualification or granting new permissions.
- [x] Update canonical progress, document v2 integration still required, commit and one final review. One Important/Critical TDD fix pass; Minor findings recorded.

## Review focus

Per-field age/expiry cannot be renewed by receipt persistence; software epochs cannot become physical bank epochs; inverter output cannot become household load; latest malformed/NULL rows cannot fall back to older values; nested collection cannot renew the common total deadline; old v1 receipts and original source manifests must not change; v2 is not silently treated as planner-authorized or fully source-complete.

Task 1 evidence:18 tests RED (missing module) then GREEN18/18 in1.29s under strict caps. Existing v1 files remain unchanged. Task2 capture/integration and final review are still outstanding. Hosted companion pin d24771b lacks the AC parser; published24d2e898 contains it and preserves pinned ancestry. Verify the changed dependency closure before updating both CI pins.

Task2 evidence:22 capture tests RED then combined40/40 GREEN; full635/635 PASS146.91s under strict caps. Final actual committed0512be3 capture9qualifiedroles at19:49:42UTC, rawreceiptSHA7938816df4e1e8787c88977b3bcaeb608cc6e3630586e8a5f23bfc168ab57bc8; exactconfig/runtime/source readback and pure identicalreplay. Fullenergy false, v2integration incomplete.

Final independent static review at7b859d5 found no Critical/Important issue. One Minor missing thermal artifact identity/confidence representation is deferred and added to full-scope follow-up, not treated as completed schema inventory. Hosted verification remains required before merge.
