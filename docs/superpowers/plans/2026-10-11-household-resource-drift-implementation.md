# Household resource drift implementation plan

> Use superpowers:executing-plans inline, then one fresh-context whole-branch review.

**Goal:** Implement Phase 8 normalized resource vectors, cumulative drift and bounded offline scheduling-order experiments from original sealed shadow plans.

**Architecture:** Add a pure observational analysis receipt around an unchanged original plan receipt. Rederive that plan before analyzing its typed candidates. Normalize each physical dimension with explicit retained scales, preserve unknown effects, and report prefix excursions separately from final drift. This does not change planner selection, intent contracts or actuator authority.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, Phases 7 and 8.

## Global constraints

CPU 20%, memory 256 MiB, swap 0, tasks 24, nice 15, idle I/O, numerical threads 1; local numerical work serial. At most 8 candidates, 16 explicit alternative orders and 1 MiB per sealed analysis. No new intent family, live read, fit, owner migration, actuator or recovery work. Existing sealed plan inputs and outputs remain unchanged. Resource scales are declared preferences, not empirical effects or safety thresholds.

## Review focus

- A favorable final net effect must not hide adverse intermediate prefixes or opposing effects.
- Unknown dimensions remain unknown despite known contributions; empty optional schedules represent zero additional declared effect, not a known household baseline.
- Declared candidate orders containing rejected/unknown candidates remain diagnostic and cannot claim feasibility or release qualification.
- Original plan, runtime, scale, order and derived result tampering must fail replay even after an outer envelope is resealed.
- CLI uses owned bounded private files, complete original runtime closure and actual analysis closure, with source/file rechecks and sanitized errors.

## Task 1: Pure vectors and sealed cumulative drift

Produces household/resources.py and test_household_resources.py. Consume original shadow-plan receipts through replay_plan; scales cover batteryKwh, socPct, thermalF, water, wearCost, comfortDegreeHours and curtailmentKwh with explicit units and positive finite bounds. Last two effects are unavailable under the existing intent contract. Preserve per-candidate raw and normalized values, known contribution totals, unknown candidate IDs, net drift, min/max prefixes and gross movement. Compare default selected order and up to 16 explicit candidate orders; unknown/rejected intent decisions are retained. Effects remain declared, causal qualification false. Seal and rederive all results with a separate analysis manifest.

- [x] Write meaningful tests for normalization, opposing-prefix excursions, unknown propagation, empty schedules, order-dependent excursions, bounded input refusal, deterministic replay and resealed tampering.
- [x] Run RED under strict caps, implement the pure boundary, then GREEN.
- [x] Verify no live/file reads inside replay and no changes to original plan bytes.

## Task 2: Private replay CLI and actual original receipt proof

Produces household_resources.py, CLI contract tests, operations docs and canonical progress. Consume existing complete original planner-runtime verifier; add exact new CLI and module hashes to analysis manifest. Recheck both file and manifest before stdout. Reject future assessments and nonprivate/special files. Pure analysis accepts declared effects without claiming source qualification.

- [x] Write CLI tests for missing runtime closure and bad private input; RED then GREEN. Resealed-output refusal is covered by pure replay; direct CLI coverage remains a deferred Minor review gap.
- [x] Replay one actual retained original plan in private staging through pure and CLI paths; exact equality and original byte recheck required. Unavailable effects remain unavailable.
- [x] Run affected household/forecast suites under serial caps; broad verification hosted.
- [x] Commit, one independent review, one Important/Critical TDD fix pass; defer Minor findings with explicit ledger.

Full PR #3 stays active. These contracts do not qualify physical effects, original bank provenance, current-policy baselines or per-intent release.

Final independent static review at 66d16b7 found no Critical/Important issue. One Minor coverage gap deferred: direct tests for rejected/unknown candidate experiments and CLI-level resealed-output refusal. Actual runtime evidence remains author-verified; review did not run tests or inspect private receipts.
