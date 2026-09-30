# WeatherNext 3 Local Adaptation Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` for inline execution or `superpowers:subagent-driven-development` where independent workers are available. Execute the reviewed tasks sequentially with test-first changes. Checkboxes below are work to be performed, not completed work.

**Goal:** Add a cost-controlled WeatherNext challenger and a reproducible local adaptation/evaluation pipeline without changing current production weather, energy, or control behavior.

**Architecture:** A separate provider worker writes immutable private weather snapshots. A local research pipeline reads original provider issues and qualified household evidence, trains candidate corrections, and publishes bounded shadow comparisons through new OpenHAB Items. Existing Open-Meteo production remains the fallback and benchmark.

**Tech stack:** Existing Python/OpenHAB/PostgreSQL and Svelte stack; isolated Python environment for Xarray/Zarr/obstore and required array dependencies; local SQLite snapshot index and compressed JSON extracts. Reuse existing numerical libraries where practical. Pin actual tested versions during Task 2; this plan does not invent compatibility pins.

**Spec:** `docs/superpowers/specs/2026-09-30-weathernext-local-adaptation-design.md`.

**Baseline:** Earthship revision `96faff58f7ebae38dc94882c20b38e6ac5e15cdc`, inspected September 30, 2026. Re-read current source and installed manifests before implementation. No cloud account, live household database, or installed service was accessed while preparing this plan.

## Global constraints

- Initial mode is `shadow`; `paid_access_allowed=false`; actuator and notification authority remain absent.
- Preserve original provider issues, source/epoch identity, available-at times, and qualified outcomes.
- Never overwrite existing Open-Meteo bias state, production forecast Items, or the retired morning DM policy.
- Keep current PV calibration, thermal graduation, and physical safety gates intact.
- Browser accesses only OpenHAB; Google secrets and direct dataset requests stay server-side.
- Use the spec's exact resource ceilings until a separately approved measured adjustment.
- Public fixtures are synthetic or appropriately licensed historical samples, never private live forecast captures.
- Cloud access approval and operator deployment approval are separate requirements.

## Review focus

1. Data published after a household issue must not leak into that issue's training or replay.
2. An authentication default must not add a billing project or switch to the full-ensemble bucket.
3. Solar accumulation units and DST day lengths must not distort resource estimates.
4. A failure during archive/publication must not replace a good issue with partial data or fresh-looking timestamps.
5. Repeated forecasts of the same weather event and unqualified historical sensor rows must not inflate evidence or skill.

## Delivery boundaries

Four reviewable increments are recommended: A, access/readiness; B, collection/archive; C, local weather learning and comparison; D, qualified energy/thermal evaluation and attended closure. Each should be independently revertible. Tasks 8 and 9 can remain evidence-gated after the initial temperature pilot ships.

## File responsibilities

All paths below are **proposed** unless identified as existing.

| Path | Responsibility |
|---|---|
| `openhab/scripts/weather_learning/contracts.py` | Typed immutable site/run/point/snapshot/issue/outcome records |
| `openhab/scripts/weather_learning/config.py` | Private configuration validation, cost/resource policy |
| `openhab/scripts/weather_learning/weathernext_gcs.py` | Allowlisted, bounded statistics-store acquisition |
| `openhab/scripts/weather_learning/normalize.py` | Native grid, units, interval, and quality normalization |
| `openhab/scripts/weather_learning/archive.py` | Content-addressed extracts and SQLite index |
| `openhab/scripts/weather_learning/evidence.py` | Adapters to existing qualified observation/origin readers |
| `openhab/scripts/weather_learning/features.py` | Decision-time-safe training and inference features |
| `openhab/scripts/weather_learning/training.py` | Small weather-model candidate fitting/artifact manifests |
| `openhab/scripts/weather_learning/evaluation.py` | Chronological evaluation and release decisions |
| `openhab/scripts/weather_learning/energy_shadow.py` | Qualified irradiance/PV/battery comparative experiments |
| `openhab/scripts/weather_learning/thermal_shadow.py` | Paired weather-forcing experiments with fixed thermal artifacts |
| `openhab/scripts/weather_learning/publish.py` | Bounded shadow payload construction and Item allowlist |
| `openhab/scripts/weather_learning/tests/test_*.py` | Unit, contract, temporal, and failure-mode tests |
| `openhab/scripts/{weathernext_ingest,local_forecast_train,local_forecast_shadow}.py` | Small command-line entrypoints |
| `deploy/{weathernext-ingest,local-forecast-train,local-forecast-shadow}.{service,timer}` | Disabled-by-default user workers |
| `src/lib/weather/providerForecast.js` | Strict new shadow schema parser |
| `src/lib/ui/ForecastComparison.svelte` | Read-only provider/local comparison detail |
| `tests/provider-forecast.test.js`, `tests/ui/ForecastComparison.test.js` | Frontend schema and presentation tests |
| `openhab/file-config/items/forecast-provider-shadow.items` | Three new display/status Items |

Existing integration points: `src/screens/Weather.svelte`, relevant OpenHAB Item subscriptions, repository CI, and its ownership/deployment documentation. No initial change to `forecast_intel.py` is necessary. Mirror cross-repository contracts in Solar_PV only when the owning repository requires it.

## Task 1 — Baseline, access, and evidence inventory

**Owner:** Operator completes Google identity/access; coding agent performs read-only audit.

**Files:** Create `docs/operations/weathernext-readiness.md`, `openhab/scripts/weather_learning/evidence.py`, and `tests/test_evidence.py` within the new package.

**Interfaces:** Define `audit_evidence(reader, start, end) -> EvidenceInventory` with explicit counts of source-qualified, diagnostic-only, missing, duplicate, and epoch-excluded samples per target. Existing readers remain authoritative.

- [ ] Read the design and operator onboarding document. Record approvals, repository revisions, installed runtime identities, and private configuration locations.
- [ ] Write `test_audit_separates_qualified_and_legacy_rows`: diagnostic numeric history never increments qualified counts; a partial activation day remains excluded.
- [ ] Write `test_audit_keeps_battery_epochs_separate` and `test_audit_reports_missing_original_issue`: no current-state substitute for missing historical issue records.
- [ ] Run these tests and record their expected initial failures.
- [ ] Implement the read-only adapter using existing OpenHAB/Solar_PV evidence readers. Use restricted database access; no schema write or raw secret logging.
- [ ] Inventory original Open-Meteo issues, outdoor temperature, irradiance, rainfall, MPPT evidence, BMS/load evidence, indoor temperatures, and confirmed actions. Establish actual overlapping dates and counts rather than assuming years of usable labels.
- [ ] Record historical forecast availability separately from qualified local-label coverage. Identify which Google history exists for the selected variables and statistics backend.
- [ ] Re-run tests, review the inventory, and commit only code/synthetic fixtures/redacted documentation.

**Gate:** A written readiness result can mark temperature ready while PV/rain/thermal remain unready. Missing credentials do not block synthetic offline development, but do block claims of a working Google connection.

## Task 2 — Contracts and bounded connection probe

**Files:** Create `contracts.py`, `config.py`, `weathernext_gcs.py`, `tests/test_contracts.py`, `tests/test_gcs.py`, isolated dependency lock, and ingestion entrypoint.

**Interfaces:** `load_config(path) -> Config`; `probe_access(config, site, now) -> ProbeReport`; `discover_runs(config, earliest, latest) -> tuple[RunRef, ...]`; `fetch_points(config, run, site, valid_start, valid_end) -> FetchResult`.

- [ ] Write `test_rejects_paid_bucket_and_billing_headers`: both a full-ensemble URI and an injected `x-goog-user-project`/`userProject` fail before network access.
- [ ] Write `test_wrong_principal_fails_without_escalation`: 401/403 produces an access error; no broader IAM grant or backend switch is attempted.
- [ ] Write `test_budget_includes_retries_and_metadata`: request counters and transferred-byte budgets include retries and metadata; a streaming oversized response is cancelled.
- [ ] Write `test_site_comes_from_openhab_config`: no browser location or hardcoded Denver-city lookup is substituted.
- [ ] Confirm failures, implement typed contracts and a lazily selected statistics-store reader, then run the tests to passing.
- [ ] Discover a real recent run and read one variable at one site before adding additional fields. Capture library versions, actual bytes transferred, elapsed time, memory peak, source metadata, and credential principal without exposing credentials.
- [ ] Test both native grids. Gradually increase from a short interval to the 72-hour target under the same resource ceilings. Do not load a global array and slice afterward.
- [ ] Inspect the outgoing request path for billing identifiers. Verify actual data access, not merely successful credential initialization.
- [ ] Freeze a working dependency environment and record whether GCS is practical. If not, halt this backend and prepare a separately reviewed Earth Engine adapter with the same output contract.

**Gate:** A real probe must pass before unattended collection. The operator's project should not require a paid data request for this route. Any billing requirement is a stop condition, not authorization to enable billing.

## Task 3 — Normalize and archive immutable forecasts

**Files:** `normalize.py`, `archive.py`, `tests/test_normalize.py`, `tests/test_archive.py`.

**Interfaces:** `normalize_points(raw: FetchResult, site: Site) -> tuple[ForecastPoint, ...]`; `save_snapshot(snapshot: Snapshot) -> str`; `load_snapshot(snapshot_id: str) -> Snapshot`.

- [ ] Write unit fixtures: 273.15 K becomes 0°C; 3,600,000 J/m² over one hour becomes 1,000 W/m² and 1 kWh/m²; 0.001 m precipitation becomes 1 mm.
- [ ] Write `test_unknown_units_fail_closed`, `test_missing_is_not_zero`, and `test_native_longitude_wrap_preserves_site`.
- [ ] Write `test_dst_uses_actual_interval_duration` for both 23- and 25-hour local days; accumulated values require complete expected interval coverage.
- [ ] Write `test_snapshot_is_idempotent_and_revision_bound`: repeated exact retrieval has one snapshot identity; a revised upstream object creates a new version, not replacement history.
- [ ] Write `test_crash_before_index_commit_leaves_previous_good_snapshot` and digest-corruption refusal tests.
- [ ] Implement normalization and compressed canonical JSON storage with SHA-256 identities. Create SQLite tables `snapshots`, `points`, `issues`, `resource_usage`, and `schema_migrations` in a private research-only database.
- [ ] Preserve provider/model/run, native grid/cell, raw units, source object revision, original first-seen time, and data-license metadata.
- [ ] Run tests, restore the archive into a temporary directory, compare digests/record counts, and commit.

**Gate:** Two independent reads of a saved snapshot agree exactly. Re-fetching cannot make an older forecast appear newly issued.

## Task 4 — Operational issue selection and historical backfill

**Files:** `archive.py`, `features.py`, ingestion entrypoint, `tests/test_issue_selection.py`, `tests/test_backfill.py`.

**Interfaces:** `select_snapshot(archive, decision_at, target_end, provider) -> Snapshot | None`; `build_issue(artifact, snapshots, decision_at, targets) -> Issue`; `backfill(config, start, end, budget) -> BackfillReport`.

- [ ] Write `test_published_after_decision_is_ineligible`, `test_incomplete_run_not_selected`, and `test_future_target_outside_horizon_is_unavailable`.
- [ ] Write `test_historical_fetch_does_not_forge_first_seen`: today's retrieval of an old run remains a retrospective study unless separate genuine availability evidence exists.
- [ ] Write `test_license_eligibility_uses_target_time_not_download_age` and `test_training_requires_completed_target`.
- [ ] Write `test_morning_and_predusk_origins_remain_distinct`. A later provider revision cannot replace a morning prediction used in scoring.
- [ ] Implement issue selection using locally available complete snapshots and issue-time target coverage. Keep initialization age, local fetch status, and forecast validity as separate concepts. Record upstream model training cutoffs when documented; when unknown, flag retrospective hindcasts as having unverified upstream training overlap rather than claiming an entirely out-of-sample global-model test.
- [ ] Backfill a seven-day pilot, then the smallest useful overlap. Produce a manifest of gaps, variables, runs, costs/bytes, and hindsight limitations before larger extraction.
- [ ] Reject substituting reanalysis, provider current conditions, or today's rerun for an original forecast. Mark retrospective model-generated archives honestly when used in research.
- [ ] Re-run tests and commit.

**Gate:** An evaluator can reconstruct exactly which inputs each issue could use. Backfill success does not assert prospective performance.

## Task 5 — Temperature adaptation and frozen evaluation

**Files:** `evidence.py`, `features.py`, `training.py`, `evaluation.py`, training entrypoint, four matching test modules.

**Interfaces:** `build_examples(issues, outcomes, cutoff) -> Dataset`; `fit_temperature(train, config) -> ModelArtifact`; `predict_temperature(artifact, features) -> Prediction`; `evaluate(artifact, test, baselines) -> EvaluationReport`.

- [ ] Write `test_future_observations_never_enter_features`, `test_scaler_fits_training_only`, and `test_duplicate_event_issues_do_not_inflate_day_count`.
- [ ] Write `test_providers_have_separate_bias_state` and `test_corrected_openmeteo_is_the_release_baseline`.
- [ ] Write `test_holdout_is_after_training_and_embargo` and `test_missing_required_features_selects_explicit_fallback`.
- [ ] Implement baselines in order: persistence; original production-corrected Open-Meteo; raw WeatherNext; provider-specific bounded bias correction; regularized local residual/blending candidate.
- [ ] Start with temperature, issue lead, cyclic hour/season, provider differences/spread, and qualified recent innovation. Add other features only with an ablation showing value on training-validation folds.
- [ ] Retain fold definitions, target windows, preprocessing, coefficients, training cutoff, source digests, model/library versions, random seeds, and runtime/memory in the artifact manifest.
- [ ] Use grouped chronological rolling-origin evaluation. Report MAE, bias, large-error frequency, and performance at declared 6/24/72-hour decision leads where available.
- [ ] Evaluate quantiles with pinball loss and empirical interval coverage. Do not label arbitrary spread or provider agreement as a calibrated probability.
- [ ] Apply the spec's minimum evidence and proposed improvement gates; return `insufficient_evidence`, `retain_shadow`, or `eligible_for_review`, never automatic promotion.
- [ ] Run synthetic leak/failure tests, replay real eligible evidence read-only, and commit a redacted report plus hashes, not private training records.

**Gate:** A frozen candidate can be reproduced and compared on identical qualified outcomes to the current adapted baseline. An apparent gain against raw Open-Meteo alone is insufficient.

## Task 6 — Prospective shadow collection and operational workers

**Files:** Three proposed user services/timers, the CLI entrypoints, `tests/test_worker_policy.py`, `docs/operations/weathernext-shadow.md`.

**Interfaces:** CLI commands `--check-config`, `--probe`, `--once`, `--replay`, and `--report` have non-overlapping read/write behavior. Training may write candidate artifacts but cannot activate them.

- [ ] Write `test_all_workers_default_to_shadow`, `test_lock_prevents_overlapping_runs`, and `test_training_failure_preserves_accepted_artifact`.
- [ ] Write `test_retry_exhaustion_does_not_change_production`, `test_disk_limit_refuses_new_capture`, and `test_terms_or_schema_change_requires_review`.
- [ ] Implement process locking, atomic output, bounded retries, durable byte counters, structured failure status, and private-directory permissions.
- [ ] Stage the ingest timer at the spec's four UTC events. Shadow inference uses new eligible inputs and explicit comparisons to existing morning/predusk origins. Use bounded periodic checks rather than adding cloud work to critical production jobs.
- [ ] Stage weekly candidate training with resource measurement. Avoid scheduling it concurrently with known heavy thermal-training windows; determine the final local slot from the installed timer inventory.
- [ ] Rehearse reboot, access revocation, network loss, unknown metadata, expired target coverage, duplicate input, interrupted write, and recovery.
- [ ] Verify that disabling all new timers leaves original production jobs unaffected. Commit; do not enable live services merely because tests pass.

**Gate:** Attended staging approval precedes real installation. Prospective comparison requires at least 14 days of normal, unforced collection before promotion review.

## Task 7 — Private UI comparison, not production replacement

**Files:** New Item file; `publish.py`; `providerForecast.js`; `ForecastComparison.svelte`; relevant existing Weather screen and subscription catalog; proposed frontend tests.

**Interfaces:** The only allowed new Item writes are `Forecast_Provider_Status_JSON`, `Forecast_Comparison_JSON`, and `Forecast_Local_Shadow_JSON`. Each new payload is version 1, no more than 32 KiB UTF-8, and contains `generatedAt`, `decisionAt`, `sourceRunAt`, `sourceAvailableAt`, status, target ranges, and model/source identities.

- [ ] Write `test_publisher_rejects_nonallowlisted_items`, including all actuator and production forecast Items.
- [ ] Write parser tests rejecting oversized payloads, unsupported versions, nonfinite values, reversed intervals, missing provenance, and timestamps without offsets.
- [ ] Write UI tests proving missing data is not zero and retrieval time does not replace source-run age.
- [ ] Show original corrected Open-Meteo, WeatherNext, and local candidate distinctly. Label output `Shadow — not controlling equipment` and show validation sample count/horizon.
- [ ] Use an expandable detail panel so the 1340×800 console remains usable without adding a wall of diagnostics. Keep measured station current conditions unchanged.
- [ ] Show model interval labels as uncalibrated until validated. Do not display a single numerical confidence score without a defined measured interpretation.
- [ ] Add source/terms attribution appropriate to the private display and a separate review gate for public screenshots or exports containing live values.
- [ ] Run the new UI tests and the repository's existing test/build commands discovered at execution time. Perform a read-only browser check with no controls or notifications.

**Gate:** Existing forecast schema/behavior is regression-free, credentials are absent from built assets, and every source is distinguishable.

## Task 8 — Solar-resource, PV, and battery experiments

**Files:** `energy_shadow.py`, `tests/test_energy_shadow.py`; cross-repository contract notes in Solar_PV where necessary.

**Interfaces:** `evaluate_solar_inputs(issues, irradiance_outcomes) -> EvaluationReport`; `predict_energy_shadow(weather_issue, energy_state, artifact) -> EnergyPrediction`.

- [ ] Write `test_unqualified_pv_day_is_not_a_label`, `test_curtailed_harvest_is_not_solar_potential`, and `test_bank_epoch_change_is_not_silently_pooled`.
- [ ] Write `test_sum_of_hourly_quantiles_is_not_daily_quantile`, `test_missing_hour_withholds_daily_energy`, and `test_no_full_day_is_censored_not_fake_charge_time`.
- [ ] First compare WeatherNext versus Open-Meteo irradiance using source-qualified station observations. Diagnose timing error separately from daily energy error.
- [ ] Only after MPPT/load outcomes qualify, evaluate weather-driven available PV versus actual harvested energy using verified array geometry, solar angle, headroom, and load assumptions.
- [ ] Preserve the existing energy model while changing one weather input at a time; fit new energy coefficients in separate experiments so benefits are attributable.
- [ ] Evaluate full-charge probability/time, post-full afternoon decline, and overnight trough at their proper issue origins. Do not feed a model's own PV-derived SoC back as an independent training observation.
- [ ] Keep battery-tail forecasts uncalibrated until target-level coverage is demonstrated. Do not purchase ensemble trajectories without an explicit cost/value review.
- [ ] Record results separately for cloudy/no-full and typical days, run tests, and commit the research report.

**Gate:** Passing this task does not open the existing PV calibration flag or grant equipment authority. Unsupported targets remain unqualified.

## Task 9 — Thermal forcing attribution

**Files:** `thermal_shadow.py`, `tests/test_thermal_shadow.py`; existing thermal replay interfaces are read, not rewritten indiscriminately.

**Interfaces:** `compare_thermal_forcing(thermal_artifact, weather_issues, qualified_grid) -> EvaluationReport`.

- [ ] Write `test_same_building_artifact_used_for_forcing_comparison`, `test_future_actions_not_inferred`, and `test_missing_action_evidence_preserves_shadow_status`.
- [ ] Freeze the accepted thermal artifact and compare original versus candidate outdoor-temperature/radiation inputs on the same issue/outcome windows.
- [ ] Separate building-parameter error, weather-input error, missing intervention evidence, and sensor quality; report which changed.
- [ ] Refit thermal parameters only as a distinct experiment after the forcing comparison, under the existing chronological and action-confirmation rules.
- [ ] Compare against persistence and the original thermal forecast, retain all failures, run replay tests, and commit.

**Gate:** Better weather alone cannot graduate a thermal model whose overall skill or action evidence remains inadequate.

## Task 10 — Attended release decision, rollback, and closure

**Files:** Operational runbook and a dated release/evaluation report; small explicit provider-selection integration only after a separate approved promotion patch.

**Interfaces:** `assess_release(report, policy) -> ReleaseDecision` cannot mutate production. Selection changes are operator-approved configuration/patches, versioned by target and horizon.

- [ ] Write `test_release_requires_all_gates`, `test_model_change_invalidates_prior_approval`, and `test_missing_provider_reverts_without_new_control_authority`.
- [ ] Record account/access and terms review, exact source/installed versions, cost/resource evidence, dataset manifest, model artifact, test outcomes, and prospective comparison.
- [ ] Take private rollback preimages and archive/index backups. Rehearse restoring them and stopping all new workers before applying any production-display selection.
- [ ] Review each variable/horizon as promote, retain shadow, or reject. Include unsupported seasons explicitly; do not extrapolate summer evidence to winter.
- [ ] For an approved display promotion, use a small adapter; retain original Open-Meteo acquisition and correction. Do not impersonate a v2 correction payload with values produced by a different untracked model.
- [ ] Verify natural scheduled publication, exact Item/archive identity, no unintended writes, resource limits, credential exclusion, and reboot recovery.
- [ ] Close with a signed-off engineering report. Equipment control, notification changes, paid cloud access, public live-data redistribution, and full-ensemble acquisition require separate authorization.

## Test execution convention

The proposed Python package tests can use the standard library runner from the repository root:

```bash
PYTHONPATH=openhab/scripts python3 -m unittest discover \
  -s openhab/scripts/weather_learning/tests -p 'test_*.py' -v
```

This command becomes runnable after the proposed package exists. Reuse the repository's actual existing CI setup and required Solar_PV import paths for integration suites; do not interpret an environment import failure as a model regression. Capture the commands and results used in the release report. No tests were run by this planning task.

## Effort, sequencing, and definition of done

Planning estimate: access preparation/audit 1–3 focused engineering days; ingestion/archive 3–5; temperature learning/replay 3–5; UI/worker/recovery work 2–4. Qualified energy/thermal experiments add roughly 4–8 focused days, with shared infrastructure already built. These are estimates for a developer with working host/repository access, not delivery commitments.

External access approval and eligible local outcomes control elapsed time. Collection can start while learning code is being reviewed. A useful temperature shadow pilot may be achievable within 2–4 weeks after access, but evidence-qualified promotion may require several further months and representative winter outcomes.

The project is complete when the integration and evaluations are reproducible, costs and permissions are understood, the UI distinguishes sources, failures are safe, and an evidence-based release decision is recorded. Retaining Open-Meteo after a fair trial is a valid outcome.
