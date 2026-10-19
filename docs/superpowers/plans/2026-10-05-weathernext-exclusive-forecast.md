**Attended deployment complete — October 19:** see the [live cutover record](../../operations/2026-10-19-weathernext-live-cutover.json) for applied retirement, fresh Google/local model identity and manual/natural/degraded/UI verification. The approved release passed all four hosted workflows. A necessary installer bootstrap fix passed 23 targeted tests and live activation; its remaining full OpenHAB CI was pending under the explicit operator deployment waiver. Statistical qualification and tuning continue in production under the approved monitored-release policy. Earlier design step checkboxes below are historical planning material, not a current deployment blocker list.

**Owner-directed release update (2026-10-19):** remove the fixed 30-day provider wait and deploy as soon as source/contract/operational checks pass, then assess and tune from production data. Scientific model-qualification windows do not block explicitly unqualified monitored production. Preserve source/physics/resource/actuation safeguards and the existing reviewed release/handoff workflow; see spec section 10.

**Execution update (2026-10-18):** Operator clarified a clean restart of weather-related ML using WeatherNext 3 forecasts plus qualified local measurements. Open-Meteo must be completely removed from OpenHAB and Earthship UI at cutover; later capture-only acquisition is no longer part of the plan. Tasks 8–9 are one attended release with removal prepared in advance. Current access/evidence: `docs/operations/weathernext-readiness.md`; binding reset/removal contract: `docs/operations/openmeteo-retirement.md`.

# WeatherNext 3 Exclusive Forecast Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify WeatherNext 3, migrate the Earthship's external forecasting and local-adaptation pipeline to it, and retire Open-Meteo from normal production use without reducing forecast skill or weakening existing safety/evidence gates.

**Architecture:** WeatherNext is introduced as an isolated shadow provider with immutable issue-time provenance. During qualification, locally corrected Open-Meteo remains the production baseline only. After variable/horizon gates pass, a normalized provider boundary switches production forecasting to WeatherNext; the same attended cutover removes Open-Meteo acquisition, integration code/configuration and provider-specific state. After retirement, WeatherNext outages fail visibly degraded rather than silently falling back to another provider.

**Tech Stack:** Existing Python/OpenHAB/PostgreSQL/Svelte stack; WeatherNext 3 precomputed statistics Zarr access; isolated Python acquisition dependencies; private local archive/index; existing Earthship and Solar_PV evidence readers; existing repository CI.

**Spec:** `docs/superpowers/specs/2026-10-05-weathernext-exclusive-forecast-design.md`

**Baseline:** `santyr/earthship-ui` main at `8a5a4ddb95917c64b19454d9277a656d4b599757`, inspected 2026-10-05. WeatherNext dataset access request has been submitted by the operator and approval is pending. Re-read current main and installed runtime before execution.

## Global Constraints

- End state is one external meteorological provider: **WeatherNext 3**.
- Open-Meteo is a pre-cutover evaluation control only; remove its integration from OpenHAB and Earthship UI in the cutover release. No post-cutover capture-only service.
- Restart weather-related ML with WeatherNext forecasts and qualified local measurements only. Do not import Open-Meteo features, fitted weather-dependent weights, bias/Kalman seeds, pending targets or error history.
- Preserve qualified local histories and physical configuration. Audit weather-dependent PV/thermal components for fresh fitting; old fixed artifacts are pre-cutover comparison controls, not inherited new-model state.
- `paid_access_allowed=false`; full-ensemble Requester Pays acquisition is out of scope.
- Never attach a requester billing project or automatically enable paid Cloud compute/storage.
- Initial WeatherNext mode is shadow-only; no actuator or notification authority.
- Preserve original provider/model/run identity on every historical issue and correction.
- Preserve current PV calibration, thermal graduation, source-qualified measurement, and safety gates.
- Never convert missing forecast values into zero sun, zero precipitation, or benign conditions.
- After Open-Meteo retirement, provider failure is explicit degraded mode; there is no silent external fallback.
- Credentials and private forecast extracts stay outside Git and browser-served assets.

## Review Focus

1. **Publication-time leakage:** a WeatherNext run that became available after an Earthship decision must not be used to train or replay that decision; Task 3 owns the tests.
2. **Hidden billing:** authentication/client defaults must not add `userProject`, billing headers, paid buckets, or Cloud jobs; Task 2 owns the tests.
3. **Solar semantics:** interval energy, average irradiance, DST, and percentile aggregation must remain physically correct; Tasks 4 and 7 own the tests.
4. **Provider state contamination:** Open-Meteo bias/state must not be applied to WeatherNext or rewritten as WeatherNext history; Tasks 5 and 9 own the tests.
5. **Outage behavior:** a stale/unavailable WeatherNext issue must degrade explicitly and must not trigger hidden Open-Meteo fallback or equipment authority; Tasks 8 and 10 own the tests.

---

## File Structure

Proposed new/changed responsibilities:

| Path | Responsibility |
|---|---|
| `openhab/scripts/weather_learning/contracts.py` | Immutable site/run/snapshot/issue/outcome/model contracts |
| `openhab/scripts/weather_learning/config.py` | Access/resource/cost policy validation |
| `openhab/scripts/weather_learning/weathernext_gcs.py` | Bounded WeatherNext statistics acquisition |
| `openhab/scripts/weather_learning/normalize.py` | Grid, interval and unit normalization |
| `openhab/scripts/weather_learning/archive.py` | Private immutable snapshot archive and index |
| `openhab/scripts/weather_learning/evidence.py` | Existing qualified household-evidence adapters |
| `openhab/scripts/weather_learning/features.py` | Decision-time-safe local-model features |
| `openhab/scripts/weather_learning/training.py` | WeatherNext-specific local adaptation artifacts |
| `openhab/scripts/weather_learning/evaluation.py` | Chronological skill/non-inferiority/release reports |
| `openhab/scripts/weather_learning/energy_shadow.py` | Solar/PV/battery attribution experiments |
| `openhab/scripts/weather_learning/thermal_shadow.py` | Fixed-artifact thermal forcing experiments |
| `openhab/scripts/weather_learning/provider.py` | Normalized production-provider snapshot boundary |
| `openhab/scripts/weather_learning/publish.py` | Bounded shadow/health payloads |
| `openhab/scripts/{weathernext_ingest,local_forecast_train,local_forecast_shadow}.py` | Small CLI entrypoints |
| `deploy/{weathernext-ingest,local-forecast-train,local-forecast-shadow}.{service,timer}` | Disabled-by-default user units |
| `openhab/scripts/forecast_intel.py` | Existing production consumer; change only after qualification |
| `src/lib/weather/providerForecast.js` | Strict comparison/health parser |
| `src/lib/ui/ForecastComparison.svelte` | Temporary qualification UI |
| `openhab/file-config/items/forecast-provider-shadow.items` | Shadow comparison/status Items |
| `docs/operations/weathernext-*.md` | Readiness, deployment, rollback, retirement runbooks |

Do not refactor unrelated forecast/UI code merely to accommodate this migration.

---

### Task 1: Refresh Baseline and Evidence Inventory

**Files:**
- Create: `docs/operations/weathernext-readiness.md`
- Create: `openhab/scripts/weather_learning/evidence.py`
- Test: `openhab/scripts/weather_learning/tests/test_evidence.py`

**Interfaces:**
- Consumes: existing OpenHAB/Solar_PV source-qualified readers and original forecast issue history.
- Produces: `audit_evidence(reader, start, end) -> EvidenceInventory` and a dated readiness report.

- [ ] **Step 1: Write `test_audit_separates_qualified_and_diagnostic_rows`.** Assert that legacy/diagnostic numeric rows never increment qualified outcome counts and partial activation days remain excluded.
- [ ] **Step 2: Run the test and confirm it fails before implementation.**
- [ ] **Step 3: Write `test_audit_keeps_hardware_epochs_separate`.** Assert that battery/MPPT/sensor epochs cannot be silently pooled.
- [ ] **Step 4: Write `test_missing_original_forecast_issue_is_not_reconstructed_from_current_state`.**
- [ ] **Step 5: Implement `audit_evidence(...)` as a read-only adapter over existing qualified readers.** Do not create another authoritative household history.
- [ ] **Step 6: Inventory qualified outdoor temperature, local irradiance, rainfall, MPPT/PV, BMS/load, indoor temperature, action evidence, and original Open-Meteo issues.** Record actual date ranges/counts and current operational consumers.
- [ ] **Step 7: Map every current Open-Meteo field/consumer to the intended WeatherNext replacement or mark it explicitly out of scope.** Full retirement is blocked by unmapped required consumers.
- [ ] **Step 8: Run tests and commit the audit code/report.**

**Gate:** The report must state which variables are ready for qualification now. It is acceptable for temperature to be ready while rain/PV/thermal remain evidence-limited.

---

### Task 2: WeatherNext Access Probe and Zero-Paid-Access Guard

**Files:**
- Create: `openhab/scripts/weather_learning/contracts.py`
- Create: `openhab/scripts/weather_learning/config.py`
- Create: `openhab/scripts/weather_learning/weathernext_gcs.py`
- Create: `openhab/scripts/weather_learning/tests/test_gcs.py`
- Create: `openhab/scripts/weathernext_ingest.py`

**Interfaces:**
- Consumes: approved Google identity, OpenHAB authoritative site coordinates/timezone.
- Produces: `probe_access(config, site, now) -> ProbeReport`, `discover_runs(...) -> tuple[RunRef, ...]`, `fetch_points(...) -> FetchResult`.

- [ ] **Step 1: Write `test_rejects_full_ensemble_and_requester_billing`.** Reject full-member bucket URIs and `userProject`/requester-billing settings before network access.
- [ ] **Step 2: Write `test_access_denied_does_not_escalate_or_switch_backend`.** 401/403 is a truthful failure, not a reason to broaden IAM or enable paid services.
- [ ] **Step 3: Write `test_site_is_loaded_from_openhab_regional_config`.** Do not use browser geolocation or a city approximation.
- [ ] **Step 4: Write resource-limit tests for retries, transferred bytes, memory/wall-time cancellation, and unknown metadata/schema.**
- [ ] **Step 5: Implement the minimal precomputed-statistics reader and config validation.** Load only bounded chunks/variables needed for one site and selected targets.
- [ ] **Step 6: After approval arrives, perform one real single-variable/single-run probe.** Record worker principal, run metadata, target, bytes, elapsed time, peak memory, and source identity without exposing credentials.
- [ ] **Step 7: Inspect outgoing requests/client configuration and verify no billing project is attached.**
- [ ] **Step 8: Expand the probe to required temperature plus one solar field under the same resource ceilings.**
- [ ] **Step 9: Pin the exact tested dependency environment and run unit tests.**

**Gate:** No later live WeatherNext task proceeds until real data access succeeds under the zero-paid-access policy. If direct GCS extraction is operationally impractical, stop for a separately reviewed Earth Engine retrieval design.

---

### Task 3: Immutable Issue Archive and Eligible-Run Selection

**Files:**
- Create: `openhab/scripts/weather_learning/archive.py`
- Create: `openhab/scripts/weather_learning/tests/test_archive.py`
- Create: `openhab/scripts/weather_learning/tests/test_run_selection.py`

**Interfaces:**
- Consumes: `RunRef`, `FetchResult` from Task 2.
- Produces: `store_snapshot(snapshot) -> SnapshotId`, `eligible_snapshot(decision_at, target_end) -> Snapshot | None`.

- [ ] **Step 1: Write `test_late_published_run_cannot_serve_earlier_decision`.** A run initialized earlier but first observed/published after the decision is ineligible.
- [ ] **Step 2: Write `test_backfill_without_as_issued_availability_is_retrospective_only`.**
- [ ] **Step 3: Write `test_interrupted_archive_write_never_replaces_last_good_snapshot`.**
- [ ] **Step 4: Write `test_duplicate_snapshot_is_idempotent_and_source_digest_bound`.**
- [ ] **Step 5: Implement a private content-addressed archive plus small SQLite index.** Store run initialization, first-seen availability, ingestion completion, target intervals, grid/statistic/unit identity and source digest.
- [ ] **Step 6: Implement eligible-run selection by decision time and required horizon.** Prefer the freshest published WeatherNext run that actually covers the target; do not assume initialization equals availability.
- [ ] **Step 7: Add bounded retention/storage accounting without deleting evidence needed by accepted model artifacts.**
- [ ] **Step 8: Run tests and commit.**

**Gate:** Replaying a household decision can reconstruct exactly which WeatherNext issue was eligible at that time.

---

### Task 4: Normalize WeatherNext Variables and Freeze the Forecast Contract

**Files:**
- Create: `openhab/scripts/weather_learning/normalize.py`
- Test: `openhab/scripts/weather_learning/tests/test_normalize.py`

**Interfaces:**
- Consumes: raw WeatherNext points.
- Produces: normalized hourly/daily points in provider-independent units while preserving original values/units.

- [ ] **Step 1: Write temperature conversion/interval tests including offset-aware timestamps and both DST transitions.**
- [ ] **Step 2: Write solar tests proving J/m² interval energy is converted correctly to mean W/m² and daily kWh/m².**
- [ ] **Step 3: Write `test_hourly_percentiles_are_not_summed_as_daily_percentiles`.** Unsupported probabilistic aggregation must raise/refuse rather than produce misleading p10/p90 daily energy.
- [ ] **Step 4: Write missing-data tests: missing sun/rain remains missing; incomplete accumulation withholds the daily aggregate.**
- [ ] **Step 5: Write native-grid selection tests that freeze one deterministic cell-selection rule before validation.**
- [ ] **Step 6: Implement WeatherNext mappings for station-head temperature/dew point, surface downward solar radiation, direct-beam radiation, candidate precipitation products, and useful wind/cloud/pressure fields supported by the actual dataset.**
- [ ] **Step 7: Capture source metadata/version in every normalized record and reject unknown unit/schema changes.**
- [ ] **Step 8: Run tests and commit the frozen contract.**

**Gate:** The same source point always normalizes identically, with no unit guessing and no unsupported uncertainty arithmetic.

---

### Task 5: Temperature Local Adaptation and Incumbent Comparison

**Files:**
- Create: `openhab/scripts/weather_learning/features.py`
- Create: `openhab/scripts/weather_learning/training.py`
- Create: `openhab/scripts/weather_learning/evaluation.py`
- Test: `openhab/scripts/weather_learning/tests/test_training.py`
- Test: `openhab/scripts/weather_learning/tests/test_evaluation.py`

**Interfaces:**
- Consumes: archived WeatherNext issues and qualified local temperature outcomes for fitting; original corrected Open-Meteo issues only in a separate pre-cutover evaluation path.
- Produces: versioned `ModelArtifact`, raw/locally-adapted WeatherNext predictions, frozen `EvaluationReport`.

- [ ] **Step 1: Write `test_weathernext_never_uses_openmeteo_bias_state`.** Also reject old fitted weather-dependent artifacts, features, error history and pending targets; an empty candidate must serve raw WeatherNext with an explicit untrained status.
- [ ] **Step 2: Write temporal-leakage tests proving recent-error features contain only outcomes completed before the issue.**
- [ ] **Step 3: Write chronological split/embargo tests; random time-row split is forbidden.**
- [ ] **Step 4: Implement baseline evaluation for persistence, locally corrected Open-Meteo as issued, raw WeatherNext, and WeatherNext bounded-bias correction.**
- [ ] **Step 5: Implement a small regularized residual model only after the bounded-bias baseline exists.** Candidate features: WeatherNext center/spread, lead, season/hour, qualified prior innovations, and selected meteorological context.
- [ ] **Step 6: Freeze all model preprocessing, coefficients, training window, source manifests and code revision in the artifact.**
- [ ] **Step 7: Evaluate by horizon and weather regime.** Report MAE/RMSE/bias/tail errors and paired day-level comparison against corrected Open-Meteo.
- [ ] **Step 8: Predeclare the cutover criterion before opening the final holdout.** Default target: >=10% lower MAE; a non-inferiority tolerance may be substituted only if declared beforehand and justified by architectural simplification.
- [ ] **Step 9: Run tests, freeze the first report, commit.**

**Gate:** Temperature can be marked `QUALIFIED_FOR_CUTOVER`, `SHADOW_ONLY`, or `REJECTED`. No label is implied by WeatherNext access approval.

---

### Task 6: Prospective Shadow Workers and Temporary Comparison UI

**Files:**
- Create: `openhab/scripts/local_forecast_train.py`
- Create: `openhab/scripts/local_forecast_shadow.py`
- Create: `deploy/weathernext-ingest.service`
- Create: `deploy/weathernext-ingest.timer`
- Create: `deploy/local-forecast-train.service`
- Create: `deploy/local-forecast-train.timer`
- Create: `deploy/local-forecast-shadow.service`
- Create: `deploy/local-forecast-shadow.timer`
- Create: `openhab/scripts/weather_learning/publish.py`
- Create: `openhab/file-config/items/forecast-provider-shadow.items`
- Create: `src/lib/weather/providerForecast.js`
- Create: `src/lib/ui/ForecastComparison.svelte`
- Modify: `src/screens/Weather.svelte` only to expose read-only detail/status.

**Interfaces:**
- Consumes: accepted shadow model artifacts and eligible WeatherNext snapshots.
- Produces only: `Forecast_Provider_Status_JSON`, `Forecast_Comparison_JSON`, `Forecast_Local_Shadow_JSON`.

- [ ] **Step 1: Write worker tests for default shadow mode, process locking, retry exhaustion, disk/resource refusal, and preservation of last accepted artifact.**
- [ ] **Step 2: Write `test_shadow_publisher_rejects_production_and_actuator_items`.**
- [ ] **Step 3: Write strict frontend parser tests for version, size, finite numbers, provenance timestamps and stale/unavailable status.**
- [ ] **Step 4: Implement disabled-by-default user services/timers with atomic outputs and bounded retries.** Ingestion discovers the newest eligible upstream run; it does not rely on a guessed publication clock.
- [ ] **Step 5: Stage weekly candidate training separately from acquisition and inference.** Never make the production forecast wait for model training.
- [ ] **Step 6: Add a compact temporary comparison panel showing corrected Open-Meteo, raw WeatherNext and local WeatherNext candidate distinctly, labeled `Shadow — not controlling equipment`.**
- [ ] **Step 7: Display source-run age/decision time and validation sample/horizon; do not invent a generic confidence percentage.**
- [ ] **Step 8: Verify network loss, access revocation, schema change and interrupted-write refusal.** Recovery rehearsals remain deferred per operator instruction; do not expand this migration into backup/recovery work.
- [ ] **Step 9: Verify disabling all new units leaves existing Open-Meteo production unchanged, then stage attended deployment.**

**Gate:** Current complete manual and normal scheduled acquisition, source/contract correctness and operational health are required before monitored provider cutover. No fixed 30-day acquisition wait applies. Training/holdout and normal-shadow evidence remain scientific qualification criteria; explicitly provisional/unqualified monitored production may proceed before those targets are complete.

---

### Task 7: Qualify Solar, Precipitation, PV/Battery, and Thermal Forcing

**Files:**
- Create: `openhab/scripts/weather_learning/energy_shadow.py`
- Create: `openhab/scripts/weather_learning/thermal_shadow.py`
- Test: `openhab/scripts/weather_learning/tests/test_energy_shadow.py`
- Test: `openhab/scripts/weather_learning/tests/test_thermal_shadow.py`
- Create/update: dated research reports under `docs/operations/`.

**Interfaces:**
- Consumes: normalized WeatherNext issues plus qualified irradiance/rain/energy/thermal outcomes.
- Produces: variable-specific qualification decisions and downstream attribution reports.

- [ ] **Step 1: Write tests that unqualified PV/rain days cannot become labels and battery/sensor epochs cannot be silently pooled.**
- [ ] **Step 2: Write solar tests distinguishing resource potential from demand-limited/curtailed harvested PV.**
- [ ] **Step 3: Compare WeatherNext GHI and direct-beam forcing against qualified local irradiance before touching PV coefficients.** Diagnose timing error separately from daily energy error.
- [ ] **Step 4: Evaluate the supported WeatherNext precipitation candidates against source-qualified rain events using a predeclared selection metric.** Freeze one WeatherNext precipitation product if/when evidence is adequate.
- [ ] **Step 5: Hold the existing energy model fixed and swap only WeatherNext weather forcing.** Evaluate available PV, harvested PV, full-charge/no-full outcomes, evening SoC and overnight trough at correct issue origins.
- [ ] **Step 6: Hold the accepted thermal artifact fixed and compare WeatherNext versus incumbent weather forcing on identical windows.** Do not refit building parameters in this attribution step. Audit every weather-dependent learned component and train the new production component afresh on Google/local pairs; a fixed-artifact comparison does not authorize carrying old weather-trained weights into the new model.
- [ ] **Step 7: Record cloudy, clear, cold/front, precipitation and no-full cases separately.** Unsupported regimes remain explicit gaps.
- [ ] **Step 8: Preserve PV/thermal physics, source and disabled-actuation gates; apply the October 19 monitored-production policy to accuracy qualification; run tests and commit reports.**

**Gate:** Every currently required Open-Meteo consumer must have a source/contract-verified WeatherNext path or explicit unavailability/removal before complete retirement. Predictive accuracy can remain unqualified and be assessed in production; missing values cannot become benign conditions or authorize action.

---

### Task 8: Production Provider Boundary and WeatherNext Cutover

**Execution update (October 19):** the focused `weather_learning.production_worker`
now consumes the Google-only provider directly; `forecast_intel.py` is retired by
the separately owner-approved 84-path source patch (`2f02e38`). Native Astro is
wired through the existing adapter. These source preparations do not complete
the release/fitting/qualification/installed-cutover steps below.

**Files:**
- Create: `openhab/scripts/weather_learning/provider.py`
- Test: `openhab/scripts/weather_learning/tests/test_provider.py`
- Modify: `openhab/scripts/forecast_intel.py` narrowly to consume the normalized provider snapshot.
- Modify/add tests around existing forecast JSON generation and scoring.
- Create: `docs/operations/weathernext-cutover.md`

**Interfaces:**
- Produces: `load_production_forecast(decision_at, required_horizon) -> ProviderSnapshot` with explicit provider/model/run/provenance.
- During pre-cutover deployment `production_provider=openmeteo`; approved cutover changes it to `weathernext`.

- [ ] **Step 1: Write characterization tests around current Open-Meteo-to-`Forecast_10Day_JSON` behavior before changing the boundary.**
- [ ] **Step 2: Write `test_weathernext_snapshot_can_drive_existing_normalized_forecast_contract` without altering Item semantics unexpectedly.**
- [ ] **Step 3: Write `test_stale_weathernext_is_degraded_not_openmeteo_fallback`.** After WeatherNext selection, no automatic provider switch is allowed.
- [ ] **Step 4: Write `test_provider_identity_is_bound_to_prediction_and_learning_state`.** Old Open-Meteo issues remain Open-Meteo history.
- [ ] **Step 5: Extract/introduce only the provider boundary needed for `forecast_intel.py`; leave scoring, PV gates, notifications and downstream contracts unchanged unless the new source requires an explicit reviewed mapping.**
- [ ] **Step 6: Define correction-state migration.** Use a new WeatherNext namespace with an empty, explicit untrained state, or a separately fitted Google/local artifact. Never call the legacy Kalman/backfill seeder, merge old state defaults, or retain Open-Meteo-trained weather weights. Separate local-only/physical configuration from learned weather state.
- [ ] **Step 7: Take private rollback preimages, verify source/contract/operational checks under the October 19 monitored-production policy, then perform the reviewed attended WeatherNext production selection.**
- [ ] **Step 8: Verify natural scheduled publication, forecast JSON identity, UI, energy/thermal consumers, reboot behavior and degraded-mode behavior.**
- [ ] **Step 9: Apply the prepared Task 9 removal in this same attended cutover.** Stop Open-Meteo writers, detach its state and remove all integrations before qualifying the new runtime. No capture-only acquisition remains after cutover.

**Gate:** WeatherNext is authoritative only after the dated operational release report records passing access, provenance, variable-contract, regression, rollback-prerequisite and operational-health checks. It must disclose unqualified predictive skill; the former calendar/statistical qualification windows do not block this owner-directed monitored deployment.

---

### Task 9: Retire Open-Meteo Cleanly

**Files:**
- Modify/remove: Open-Meteo runtime acquisition/provider-specific files only after dependency inventory proves them unused.
- Modify/remove: `openhab/file-config/things/openmeteo.things` and Open-Meteo-linked Items as appropriate.
- Modify: forecast-learning state schema/migration tooling.
- Modify: temporary comparison UI once no longer needed.
- Create: `docs/operations/openmeteo-retirement.md`
- Test: retirement/dependency regression tests.

**Interfaces:**
- Consumes: passing pre-cutover qualification and a reviewed dependency/reset manifest. Prepare removal before Task 8; execute it as part of the same attended release, then observe WeatherNext-only stability.
- Produces: WeatherNext-only runtime and project, with historical Open-Meteo evidence detached from deployed readers and new learning.

- [ ] **Step 1: Generate a machine/readable dependency inventory for every Open-Meteo Thing/channel/Item/function/state key and classify each as replaced, removed/unavailable, detached historical-only, or still blocking cutover. Include AQI/UV, managed and file-owned objects, installed binding/add-on configuration, scheduled jobs, frontend/alert consumers, migration tools/tests, CI and ownership manifests.**
- [ ] **Step 2: Write `test_no_production_path_calls_openmeteo_after_retirement`.** Network acquisition and production provider selection must contain no Open-Meteo path.
- [ ] **Step 3: Verify detached historical records retain their original provider labels.** Any archive reader retained outside the active project cannot feed new fitting or production; add tests for fresh Google/local-only state and artifact lineage.
- [ ] **Step 4: Prepare a reversible removal patch before cutover; stop Open-Meteo acquisition/writers first during the attended release.** Verify fresh WeatherNext state and observe the resulting Google-only runtime; no Open-Meteo diagnostic collector remains.
- [ ] **Step 5: Apply the prepared removal patch in the cutover release.** Remove the installed binding, Things/channels/links, obsolete Item definitions, provider code, migration/deployment tooling and state references from OpenHAB and Earthship UI. Archive old state privately outside all runtime readers; retain historical documentation/Git identity without keeping executable integration. Remove stale UI/alert dependencies, including AQI/UV when no qualified Google replacement exists.
- [ ] **Step 6: Remove temporary provider-comparison UI or simplify it to WeatherNext health/local-skill status.**
- [ ] **Step 7: Run the entire repository CI/test/build suite and explicit network-call search.**
- [ ] **Step 8: Commit retirement only after rollback materials remain available for the defined post-cutover window.**

**Gate:** OpenHAB and the active Earthship UI project contain no Open-Meteo integration, acquisition or learning path; weather ML has only Google/local-measurement lineage. No silent, dormant or capture-only Open-Meteo runtime remains.

---

### Task 10: Post-Cutover Validation and Closure

**Files:**
- Create: `docs/operations/YYYY-MM-DD-weathernext-exclusive-forecast-closure.md`
- Update: architecture/readme/runbooks that still describe Open-Meteo as current.

**Interfaces:**
- Consumes: production WeatherNext issues, local outcomes, resource/cost logs, rollback evidence.
- Produces: final `ReleaseDecision`/closure report and current documentation.

- [ ] **Step 1: Write/verify `test_weather_provider_outage_has_no_new_control_authority`.** Current local measurements continue; forecast-dependent features report unavailable/degraded as designed.
- [ ] **Step 2: Score post-cutover WeatherNext/local forecasts against actual outcomes and compare them with the frozen pre-cutover incumbent baseline.** Keep failures and adverse regimes in the report.
- [ ] **Step 3: Verify Google access path still obeys zero-paid-access policy and record observed bytes/runtime/storage.**
- [ ] **Step 4: Verify there are no credentials/private extracts in Git, built frontend assets, logs or screenshots intended for publication.**
- [ ] **Step 5: Record the pinned pre-cutover revision and manual rollback prerequisites.** Backup/recovery rehearsal and finishing work remain deferred per operator instruction.
- [ ] **Step 6: Update architecture docs to the actual final state and close superseded migration instructions.**
- [ ] **Step 7: Record unresolved limitations explicitly: insufficient seasonal evidence, precipitation-event count, WeatherNext experimental-service risk, or any target left shadow-only.**

**Definition of done:** WeatherNext is the sole normal external forecast source; local adaptation is reproducible and prospectively scored; all current forecast consumers have qualified replacements; Open-Meteo no longer participates in acquisition, prediction or learning; outages are visible degraded states; existing safety/evidence gates remain intact; and rollback/closure evidence is documented.

---

## Verification Commands

Use the repository's actual current commands at implementation time. At the inspected revision, CI includes Vitest, frontend build, Python completion/OpenHAB tests, and operational tooling tests. The new package should also support focused execution such as:

```bash
PYTHONPATH=openhab/scripts python3 -m pytest \
  openhab/scripts/weather_learning/tests -q

npx vitest run
npm run build
python -m pytest tests/completion/ -q
python -m pytest openhab/scripts/ -q
```

Do not claim completion from partial suites. Production cutover and retirement require fresh full-suite output plus attended runtime verification.

## Execution Sequence and Stop Conditions

Recommended increments:

1. **Access/readiness:** Tasks 1–2.
2. **Archive/contract:** Tasks 3–4.
3. **Temperature shadow:** Tasks 5–6.
4. **Required-variable/downstream qualification:** Task 7.
5. **WeatherNext production cutover:** Task 8.
6. **Open-Meteo retirement:** prepare Task 9 before Task 8, apply it in the same cutover release, then observe WeatherNext-only stability.
7. **Closure:** Task 10.

Stop rather than proceed when any of the following is true:

- WeatherNext approval/access is unavailable;
- real retrieval violates the zero-paid-access/resource policy;
- source availability times cannot be represented honestly;
- a required WeatherNext variable cannot be mapped correctly;
- an evaluated local correction shows a material regression: withhold that correction and serve raw WeatherNext where its operational checks pass;
- a required precipitation/solar source or unit/interval contract is unavailable and the consumer has not been explicitly withdrawn; insufficient accuracy-event samples alone do not impose a calendar wait;
- rollout reveals stale-data ambiguity, hidden fallback, or unintended control authority.

The operator has accepted monitored production before full statistical qualification. Complete the concrete source/contract/operational checks promptly, then retire Open-Meteo in the reviewed handoff. Record and tune actual production outcomes without claiming unmeasured skill or retaining an incumbent fallback.
