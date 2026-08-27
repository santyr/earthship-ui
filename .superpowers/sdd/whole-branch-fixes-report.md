# Whole-Branch Review Fixes Report

**Branch:** `feat/dashboard-weather-bitcoin`
**Reviewed base:** `4f80e2ec54ed1d05f2dac424185b5f9a5d4d2faf`
**Date:** 2026-08-27

## Outcome

All four final whole-branch review findings are fixed with regression coverage.

1. Bitcoin candlestick history now opts into tolerant per-row validation. Valid rows survive malformed timestamps, states, and unsupported units; the default line-chart path remains strict.
2. Home current-condition icons route finite WMO codes through `wmoIcon`, retain supported explicit `iconify:mdi:`, `iconify:bi:`, `mdi:`, and `bi:` identifiers, normalize partly/partially-cloudy aliases, and fall back only for unsupported text/unavailable values.
3. Full Bitcoin candle axes and tooltips show browser-local time for subday intervals and browser-local month/day for daily intervals. Compact axes remain hidden.
4. Home temperature and Bitcoin refreshes use AbortController-backed latest-generation coordinators. A new refresh aborts its predecessor, stale completions cannot commit, and destroy aborts pending work.

## TDD evidence

- Malformed Bitcoin rows RED: `loadHistorySeries` returned `error`; the modal never called `setOption`. GREEN: focused history/modal suite passed 40 tests.
- Condition icons RED: WMO 0/2/3 and bare `mdi:`/`bi:` identifiers fell back to partly-cloudy. GREEN: focused icon suites passed 204 tests.
- Candle timestamps RED: `xAxis.axisLabel.formatter` was absent for both subday and daily views. GREEN: focused candle/component/modal suites passed 41 tests.
- Home refreshes RED: latest-refresh module and Home wiring were absent. GREEN: deterministic out-of-order and destroy tests plus Home contract passed 15 tests.

## Final verification

- Combined focused Vitest: **14 files, 309 tests passed**.
- Full Vitest: **86 files, 1061 tests passed**.
- Production build: **passed** (Vite 8.1.5, 792 modules transformed).
- Required Playwright set: **12 tests passed** across 1340x800 and 1280x720.
- `git diff --check`: **passed**.

## Warnings

- Vite retained its existing advisory that several generated chunks exceed 500 kB after minification.
- Playwright printed the existing `NO_COLOR`/`FORCE_COLOR` environment warning.
- The sandboxed `apply_patch` helper failed with `bwrap: loopback: Failed RTM_NEWADDR`; edits were made with narrow deterministic rewrites after the required patch attempt, then fully diff-reviewed and verified.

No push or merge was performed.
