# Household energy outcome implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, TDD, and one whole-stage independent review.

**Goal:** Score original household energy projections against a source-qualified completed-night minimum while retaining every original BMS row and physical bank binding.
**Architecture:** A bounded read-only collector freezes the original bank configuration and exact atomic SoC query rows. Pure replay checks independent stream/bank bindings and invokes the existing completed-night assessor. The score replays the original model/plan and requires the matching originally persisted forecast receipt; missing sources, missing model inputs and incomplete nights remain unavailable.
**Tech Stack:** Existing Python, PostgreSQL read-only reader, earthship_energy atomic SoC assessor; no dependencies.
**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, phases1/2/3/7.

## Global constraints

- Serial CPU20%, memory256MiB, swap0, tasks24, numerical threads1; broad hosted CI.
- Fixed BMS_SOC_Evidence_JSON only. Raw malformed/unavailable/null rows remain barriers, never removed or replaced by numeric BMS_SOC.
- Physical bank interval and source stream epoch are independent; never infer either from measured percentages.
- Target night is recorded prediction-day20:00 through following-day11:00 America/Denver; at least90% validated coverage, existing assessor semantics unchanged.
- No causal benefit, statistical graduation, automatic actuation, owner migration, recovery work or new service installation.

## Review focus

- A coherent wrong stream must not qualify merely because its internal rows agree.
- Bank cutovers, target-date changes and late origin delivery must refuse rather than score another night.
- NULL/malformed/unavailable rows must terminate carry and affect coverage.
- Read transactions must be dedicated, bounded and read-only; row/byte overflow must refuse without truncating truth.
- A derived assessment or error must be rederived from originals, not trusted after resealing.

## Task1: Original completed-night packets

Files: household/energy_outcome_sources.py, test_household_energy_outcomes.py.
Interfaces: build_night_source(rows, prediction_day, assessed_at, bank_config_raw, expected_bank_epoch, expected_stream_epoch); replay_night_source(packet); fetch_night_source(connection_factory,...,remaining).
- [x] Write failing tests for full-night measured minimum, sparse/incomplete coverage, wrong independent phase, physical cutover, missing bank, future rows, NULL barriers and resealed derived assessment.
- [x] Bound packet4MiB, rows10000, each raw4096bytes; closed original bank configuration64KiB and complete physical epoch validation. Preserve exact row strings and persistence clocks. Replay existing assessor; no IO in pure path.
- [x] Write/read failing DB transaction tests. Fixed unique Item mapping, repeatable-read/read-only transaction, total15s callback, statement2s/lock1s, bounded original window with120s lookback, ordered rows10001overflow detection, NULL barrier preservation, close on all paths.
- [x] Run focused caps, commit with ledger.

## Task2: Original plan/forecast energy scoring

Files: household/energy_outcomes.py, test_household_energy_outcomes.py.
Interface: seal_energy_outcomes(plan_receipt, forecast_source, night_source, plan_runtime_manifest, outcome_runtime_manifest, thermal_runtime); replay_energy_outcomes(...).
- [x] Failing tests for rederived plan/trough binding, exact persisted original forecast and issuance chronology, wrong date/phase/bank/value, missing original model and immature/insufficient measurement, score tamper.
- [x] Preserve original forecast raw bytes/persisted clock, require earlier same-day issue before target night, cross-check original BMS origin/digest against plan snapshot. Compare original energy projection and delivered trough; later source qualification uses an independently bound outcome stream; a producer restart requires a fresh later fixed-owner receipt. Physical bank identity remains separate. Explicit model/outcome unavailable statuses, reserve diagnostics only, no causal or release claims.
- [x] Whole focused task suite under caps, commit.

## Task3: Actual evidence and offline CLI

Files: household_energy_outcomes.py, tests and operations docs/canonical tracker.
- [x] Owned0600 bounded receipt, actual complete source manifests and separate thermal closure, pure replay/recheck before stdout, sanitized refusal.
- [x] Acquire one actual completed-night packet through existing private restricted reader and bank configuration. Verify actual retained forecast/model context; if exact as-issued inputs are absent, record the missing evidence and withhold scoring rather than reconstruct guessed inputs.
- [ ] Full appropriate capped regressions (534 passed), one independent whole-stage review/fix pass; publish hosted CI and keep the full objective active for every remaining requirement.
