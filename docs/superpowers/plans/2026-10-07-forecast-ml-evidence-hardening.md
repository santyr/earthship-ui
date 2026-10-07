# Earthship forecast-ML evidence hardening

**Date:** 2026-10-07  
**Branch:** `feat/ml-evidence-conditioning-20261007`  
**Scope:** existing Earthship thermal, SoC, PV/energy, and temperature-learning paths.  
**Explicitly deferred:** WeatherNext ingestion, adaptation, provider selection, and WeatherNext model work.

## Goal

Make the existing forecasting stack harder to overfit or overstate by treating independent days/windows—not dense sensor rows—as the primary evidence unit, rejecting numerically ill-conditioned thermal fits, and checking whether learned thermal coefficients are stable under deterministic day-block refits.

This work must not change live forecast equations, calibrated coefficients, alert thresholds, notification policy, or actuator authority.

## Principles

1. Five-minute or hourly rows are observations, not independent experiments.
2. A full-rank regression can still be numerically non-identifiable.
3. Qualified source-bound outcomes remain authoritative; summaries are derived caches only.
4. Model complexity must be judged against independent evidence units.
5. Existing production forecasts remain unchanged by this patch; new evidence is diagnostic or a fit-refusal guard.
6. WeatherNext remains out of scope until separately resumed.

## Task 1 — shared independent-evidence utilities

Create `openhab/scripts/forecast_ml_evidence.py`.

- Normalize qualified evidence origins to local calendar days.
- Summarize reported evidence units, unique independent days, duplicates, first/last day, active parameter count, and days per parameter.
- Count non-overlapping forecast origins for a declared horizon.
- Refuse naive timestamps, malformed dates, booleans masquerading as integers, and contradictory inputs.
- Add focused tests in `openhab/scripts/test_forecast_ml_evidence.py`.

## Task 2 — thermal numerical conditioning

Update `thermal_model/dynamics.py`.

- Column-normalize design/sensitivity matrices before assessing conditioning.
- Retain the existing exact rank tests.
- Reject a full-rank matrix whose normalized condition number exceeds the floating-point safety limit `1/sqrt(machine epsilon)`.
- Apply the guard to both bounded five-minute fits and the multihorizon sensitivity matrix.
- Do not change coefficient bounds, objectives, optimizer settings, or physics checks.

The condition threshold is a numerical safety guard, not a claim that every smaller condition number is scientifically well identified.

## Task 3 — thermal coefficient block-refit stability

Add a deterministic stability check to the strict artifact fit only.

- Use independent local days as the resampling unit.
- Once at least twice the active dynamics coefficient count in independent days exists, split days deterministically into four interleaved blocks.
- Refit the five-minute identification stage four times, each time withholding one block.
- Compare each coefficient with the all-day initializer after normalizing by its allowed physical span.
- Refuse only large instability: a coefficient moving by more than 25% of its entire allowed physical range under a one-block omission.
- Evaluation-fold fitting with inactive action columns does not run the extra refits, preventing a large walk-forward compute multiplier.
- Short synthetic/early datasets report insufficient support and retain the pre-existing behavior rather than fabricating a stability pass.

This check is about parameter identifiability; predictive skill is still judged by chronological backtesting.

## Task 4 — existing forecast evidence summaries

Update `forecast_intel.py` without changing predictions.

At each normal morning issue, derive a private `learning_evidence` state summary for:

- SoC trough: the actual recent qualified night dates used by the current heuristic.
- PV calibration: source-qualified PV days currently retained in scoring evidence, plus the existing calibration-release-gate state.
- Hourly temperature: qualified receipt days plus total/min/max per-hour Kalman bucket update counts.

The summary must never substitute for raw state, forecast receipts, BMS evidence, or qualified PV evidence.

## Task 5 — regression tests and safety checks

Add tests proving:

- column scaling does not change normalized condition number materially;
- nearly collinear but technically full-rank designs are refused;
- stable synthetic thermal data pass the block-refit check;
- a deliberately unstable refit is refused;
- evidence summaries deduplicate same-day observations;
- non-overlapping origin counts do not treat overlapping forecasts as independent;
- SoC/PV/hourly support summaries do not alter forecast outputs.

Run the repository CI/test suites available to the branch. This patch is not a deployment.

## Definition of done

- The branch contains the implementation and focused tests.
- No WeatherNext code is changed.
- No production forecast formula, coefficient, Item, alert threshold, notification, or control authority changes.
- Thermal fitting refuses extreme numerical ill-conditioning.
- Strict thermal artifact fitting checks day-block coefficient stability when enough independent days exist.
- Existing forecast state records compact independent-evidence support for SoC, PV, and hourly temperature learning.
- A PR records any CI failures or remaining migration/deployment work.
