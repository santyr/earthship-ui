# Earthship WeatherNext 3 Capability Expansion — Implementation Goal and Plan

> **For the coding agent:** Execute this plan task by task using the repository's existing implementation and review workflow. Where the Superpowers skills are available, use `executing-plans` or the established subagent-driven workflow, test-driven development, and verification before completion. Preserve completed audit repairs and unrelated work. This is a new capability-expansion goal, not a restart of the correctness audit.

**Goal:** Make effective, measurable use of WeatherNext 3's available statistics, solar components, atmospheric context, and hourly forecast updates to improve the Earthship's weather display and read-only thermal/energy guidance, and deploy the new models/improvements as the active production methods in Step 11, with evaluation against real observations after deployment, while preserving source truth, operational reliability, no-billing access, and existing control authority.

**Architecture:** Extend the existing statistics-only acquisition, immutable archive, typed forecast adapters, local learning, and bounded scoring services. Add a versioned supplemental forecast product for richer weather information without changing the meaning of legacy payloads. Develop separately identified new methods, retrain on historical data where needed, and replace the existing production models during Step 11. Evaluate the actual production predictions against real data afterward; a parallel shadow period is not required. Scientific qualification remains separate from deployment.

**Tech stack:** Existing Python/OpenHAB/PostgreSQL/SQLite forecasting and evidence services; Google Earth Engine statistics access; Svelte/Vite/ECharts frontend; existing pytest/Vitest/Playwright and native qualification profiles. Use the exact supported versions and companion source pins from the executing revision.

**Spec:** Sections 1–5 of this document are the self-contained requirements and design contract. The numbered tasks implement that contract. `docs/operations/weathernext3-capabilities/completion-audit.json` is the cross-reference, not a second source of requirements.

**Prepared:** October 21, 2026. **Source baseline inspected:** `cdfaa6b51b568423a5aada34a930094c7cf0730b`, merge of PR #43, which follows `87a70336fa52a19a282941af1bcd80b2f63ded52`. Reconcile any later changes before execution. [S01]

**Evidence boundary:** Planning used public source and current provider/research documentation. Private household observations, effective service settings, account eligibility/usage, installed packages, and current fitted weights were not inspected here. The local coding agent must establish those facts. Source merge, passing fixtures, installation, actual operation, forecast skill, and physical qualification are distinct claims.

## October 22, 2026 deployment amendment

The user explicitly requests replacing the existing models during Step 11, using
the new models and improvements in production and comparing their actual issued
predictions against real observations. Retrain on historical data where needed.
A separate parallel shadow period is not required. This instruction supersedes
the original incumbent-retention and pre-deployment superiority requirements for
this rollout. Preserve the original experiments and their conclusions: choosing
experimental production use does not retroactively turn a losing/insufficient
comparison into demonstrated improvement.

The deployment decision and scientific qualification are separate. Software,
source, target, training-data and numerical-validity checks still apply. Missing
class/event support cannot produce a fabricated fitted rain model; absent joint
inputs cannot produce a fabricated coherent scenario. Use explicit target-level
fallback/withholding when such inputs are absent, without holding up other valid
new production methods. Probability, physical calibration, causal benefit and
all-season skill remain unclaimed until separately evidenced. No new actuator,
provider, full-ensemble, billing or host-resource authority is granted. Additional cloud-collection authorization is unchanged; use existing authorized collection and historical data for this replacement.

## October 23, 2026 delivery and UI wording amendment

The authorized production replacement is installed. The current source-role,
model, original fit/admission, CI, actual UI, natural-cycle, retention and rollback
readback is [production-release.json](../../operations/weathernext3-capabilities/production-release.json).
The [completion audit](../../operations/weathernext3-capabilities/completion-audit.json)
accounts for all 70 numbered task steps, 13 WN recommendations, 30 regression
scenarios and 10 global constraints. Historical task experiment records retain
their original conclusions. Checkmarks include precise externally blocked
scientific/acquisition dispositions; they do not assert unobserved qualification.

The user's October 23 wording instructions supersede the earlier modal legend and
source-age wording: omit the production-temperature heading and explanation,
the raw-range prefix, unverified-coverage/shaded-band explanation and Source
initialized row/tooltip. Preserve numerical ranges and original clocks privately.
The frozen deployment-policy document is hash-bound historical authorization;
its deployment_completed field is not the current installation indicator.

## 1. Mandate, scope, and priority

Carry this work through implementation, normal-harness tests, local evidence assessment, documentation, and the established authorized integration process. Do not finish with a list of recommendations alone. Build the bounded experiments and evaluation paths even when real observations are not yet sufficient to select a winner. Report insufficient evidence honestly without delaying unrelated engineering work.

Prioritize: existing temperature uncertainty → bounded additional data → native solar components → atmospheric context → actual hourly-update evaluation → calibrated marginal forecasts → household scenarios → precipitation selection/probability experiments → integrated release.

This goal explicitly includes the model comparisons below that were previously deferred from the correctness audit. It does **not** authorize unlimited model research, full-ensemble acquisition, new automation, or automatic promotion. Use the small predeclared challenger set; one method losing is a valid experimental result, not a reason to keep trying methods until one wins.

### Recommendations-to-work mapping

| ID | Recommendation to address | Owning tasks |
|---|---|---|
| WN-01 | Preserve latest audit repairs and reconcile source versus installed runtimes | 0, 11 |
| WN-02 | Version contracts and make optional capabilities independently available | 1, 2, 11 |
| WN-03 | Expose already acquired temperature p10/p90; preserve mean versus median | 2 |
| WN-04 | Selectively acquire additional quantiles within explicit cost/resource budgets | 1, 3 |
| WN-05 | Compare native direct/total solar against the current decomposition | 4 |
| WN-06 | Use dew point, pressure, wind components, and cloud structure appropriately | 3, 5 |
| WN-07 | Measure actual hourly refresh value and separately identify near-term correction | 6 |
| WN-08 | Test adaptive temperature correction and locally calibrated marginal uncertainty | 7 |
| WN-09 | Provide stress scenarios; evaluate dependence-aware household scenarios before probabilities | 8 |
| WN-10 | Compare all three rain products and a bounded occurrence/amount challenger | 9 |
| WN-11 | Preserve provider, cost, archive, privacy, authority, and historical replay boundaries | All |
| WN-12 | Integrate accessible UI, observability, complete tests, and scoped rollout | 2, 5, 8–11 |
| WN-13 | Disposition longer-range display, station-grid limits, and deliberately unused capabilities | 0, 10 |

## 2. Global constraints

1. **WeatherNext remains the sole external weather provider.** Local measurements provide observation evidence, not an undeclared external fallback. Do not reactivate Open-Meteo.
2. **Retain statistics-only, no-billing access.** Preserve `paid_access_allowed=False`, `full_ensemble_allowed=False`, and no requester billing project. Do not attach a billing account, change tiers, enable paid services, fetch full ensemble members, migrate to BigQuery, or deploy custom inference under this goal. [S05]
3. Preserve the actual approved host admission, CPU/RAM/IO, thread, task, timeout, and no-swap limits. More fields do not justify silently raising caps. Batch or reduce optional work instead.
4. Do not claim a particular Earth Engine quota or eligibility for this account without checking locally. Google's documented Community allowance is context, not proof of the installed project's tier or remaining budget. Missing usage visibility must be explicit; do not equate local execution seconds with EECU-seconds. [D04]
5. **Planner actuation stays disabled.** No new shade, vent, pump, charging, or feeder authority. Feeders remain manual/Lightning-payment driven. Read-only weather risk displays do not authorize a control.
6. Original API bytes, first availability, selected profiles, model bytes, fit clocks, emitted predictions, observation receipts, and historical scores remain immutable. New fields acquired later do not become available retroactively. New numerical methods get new identities.
7. Preserve current sensor epochs, observation validity, and measurement limits. Lux-derived exposure is not calibrated physical GHI; PV potential is not captured PV; nominal battery capacity is not measured usable capacity; unknown cistern inventory remains unknown.
8. Keep private data, exact site configuration, credentials, source paths, account identifiers, and raw household extracts out of public reports and Git. Read site/timezone from the authoritative configuration, not the chat's approximate location.
9. Preserve audit repairs, including coherent temperature evidence, optional-domain error isolation, selector readback, pending long-horizon scoring, matched comparisons, target weighting, and per-write archive accounting. Revalidate the executing source; do not repeat repairs already complete. [S01]
10. Implement and stage reversible software within the established workflow. Follow existing approval boundaries for production installation, model selection, service starts, cloud probes, and physical tests. Earlier approval of another rollout is not blanket permission for these changes. Complete unblocked work rather than repeatedly asking to continue.

## Review focus

The final review must specifically challenge five boundaries: optional data failing without disabling core forecasts (Tasks 1–3); changing profile coverage without invalid cache reuse or resource overruns (Tasks 1, 3); interval/component/quantile semantics surviving downstream calculations (Tasks 2, 4, 8, 9); actual source availability surviving hourly selection and retrospective evaluation (Tasks 6–7); and compatibility/readback surviving source or model changes (Task 11). The regression matrix names tests for each boundary.

## 3. What is already implemented, and what this goal adds

At the planning revision, `worker.py` collects station temperature mean/p10/p90 and mean dew point; gridded means include total/direct solar, three precipitation heads, scalar 10 m wind, total cloud, and sea-level pressure. `normalize.py` recognizes six statistics and wind components, but not the three extra cloud-layer mappings. `provider.py` builds its standard products primarily from means; `native_forecast.py` narrows forcing to temperature, total solar, and scalar wind. [S02], [S03], [S04], [S05], [S06]

Do not reimplement existing full/interim collection, native-cell validation, original-source replay, terrain daylight, weather icons, or the latest evaluation repairs. Extend the existing components where they fit. Inspect and respect compatibility packages: corrected code on main is not necessarily the code serving incumbent weights.

Google documents station and surface statistics, distinct full/interim horizons, and delayed delivery relative to initialization. Use actual discovered availability as operational truth. Provider schedules are planning estimates, not guarantees or proof that a run was available to an earlier decision. [D01], [D02], [D03]

## 4. Design contract

### 4.1 Four forecast objects, never one ambiguous range

Keep these products distinct in code, reports, and UI:

- **Raw native statistics:** unchanged provider mean/quantiles for a named variable, cell, interval, run, and valid time. A p10–p90 interval is a nominal pointwise ensemble range, not established local 80% coverage.
- **Locally calibrated marginal prediction:** a versioned local distribution or quantile forecast for one declared target, with fitting and validation evidence. A point correction or clipping bound is not a distribution.
- **Deterministic stress scenario:** a declared hypothetical input trajectory, without probability or quantile claims.
- **Locally modeled joint scenario ensemble:** trajectories with explicitly modeled temporal/cross-variable dependence, separately tested. These are not Google's recovered ensemble members and do not automatically make battery/thermal risks calibrated.

Use separate status fields for source availability, method identity, local skill evidence, probability-calibration evidence, serving admission, and actuator permission. Existing immutable authority flags must not be repurposed to make a richer UI appear enabled.

### 4.2 Supplemental product and stable interfaces

Prefer one new bounded supplemental product, proposed schema `earthship-weathernext-capabilities/v1`, delivered through a fixed read-only report route such as `/api/weather-capabilities`. The route name is proposed, not an assertion that it already exists. Inspect the established report-server pattern and reuse an equivalent existing endpoint only when its contract genuinely fits.

Do not overload a legacy schema version already used for an older temperature-adjustment format. Keep the existing `Forecast_10Day_JSON` and native-v1 semantics readable. If a native forcing v2 is necessary for direct solar, add explicit v1/v2 dispatch and frozen-producer replay; never mutate the v1 row meaning.

Define the following typed interfaces in a small shared module, or map them one-to-one to existing equivalent types during Task 1:

- `CapabilityProfile`: immutable profile ID/hash; allowed `(collection, variable, statistic)` triples; native units/periods; grid policy; core versus optional groups; and request/storage/compute bounds.
- `NativeStatisticSeries`: source snapshot/run/cell/collection; statistic; native and normalized units; period and exact interval endpoints; initialization, actual availability, decision and valid clocks; nullable values and quality reasons.
- `ForecastEvidence`: source profile, method/model/procedure IDs, target definition, sensor/observation policy, issued values, actual availability, and permission/qualification status.
- `ScenarioSet`: issue/profile/source identities, method/version/seed, target intervals, trajectory values, dependence provenance, scope assumptions, and `probability_claim` that is false unless separately qualified.

Required pure boundaries are normalization/validation, source selection, public projection, model prediction, and scoring. Neither a parser nor a UI read may trigger cloud access or fitting. Keep public output curated: source hashes and clocks are useful, private paths and raw source capsules are not.

### 4.3 Mathematical invariants

**Quantiles:** Keep labels attached to their exact variable, time interval, run, and grid. Allow tied quantiles, especially zero rain. Reject nonfinite or genuinely crossing raw quantiles with an explicit optional-group status; do not silently sort original provider values. Do not require the mean to equal p50 or lie inside p10–p90. Preserve documented small numerical tolerance separately from substantial inconsistency.

**Aggregation:** Means of additive quantities can be summed over complete matching intervals. Hourly marginal quantiles cannot be summed to obtain daily quantiles. A min/max of hourly means is not a predictive distribution of daily extrema. Differences of equal-level total/direct solar quantiles are not diffuse-radiation quantiles. Combining temperature and dew-point means gives a diagnostic derived value, not necessarily the ensemble-mean humidity.

**Solar:** The direct field must be verified against provider metadata and its documented horizontal-plane interpretation before use. For matching mean accumulated energies, `diffuse_energy = total_energy - direct_horizontal_energy`. Preserve native J/m² and interval endpoints; dividing by 3,600 yields an hourly mean W/m², not an instantaneous measurement. Direct horizontal radiation is not DNI. [D02], [D05]

**Timing:** Track lead from initialization and lead from the local decision separately. A 48-hour interim product covers 48 hours from initialization, not 48 hours beyond its arrival. Select only actual remaining coverage. Composite UI products keep per-segment provenance and cannot masquerade as a single issued forecast.

**Physics and authority:** Terrain blocks the appropriate direct component, not all diffuse sky light. A wind-vector mean does not equal the mean scalar speed. Station moisture context is not a surface-condensation diagnosis. Forecast improvement does not identify causal action benefits.

### 4.4 Small, predeclared comparison set

Implement the following bounded alternatives; do not run an open-ended hyperparameter/model search:

| Target | Incumbent/reference | Required challenger or experiment |
|---|---|---|
| Temperature point forecast | Raw WeatherNext and incumbent corrected policy | One adaptive past-error correction with a predeclared decay-selection procedure |
| Temperature uncertainty | Raw available quantiles and a simple empirical residual-interval baseline | One regularized EMOS-style location/scale or equivalent small quantile-calibration model using only available statistics |
| Solar/PV mean prediction | Current total-only decomposition and incumbent electrical correction | Native total/direct mean components, first without refitting electrical gains, then with separately versioned like-for-like calibration |
| Local irradiance uncertainty | Raw GHI range, clearly not calibrated to the proxy | One nonnegative/geometry-aware marginal candidate only for the declared observed proxy target |
| Wind | Raw scalar forecast and incumbent gain | One bounded affine/log-scale exposure correction; directional features only where retained inputs and local evidence support them |
| Moisture/cloud/pressure features | Existing feature set | Individually added feature-group ablations; promote no group merely because it is available |
| Household trajectories | Central deterministic scenario and labeled stress cases | One bounded dependence-aware residual/analog trajectory method, without full upstream ensemble access |
| Rain | Three raw products, incumbent selection, and existing gain baseline | One two-part occurrence/positive-amount model; a censored-shifted-gamma alternative only if the predeclared first method is unsuitable, not an unbounded search |

The research supports these families as candidates, not guaranteed site improvements. Use available native spread as a predictor, not as an exact ensemble variance. Full member-level EMOS/ECC inputs must not be fabricated from a handful of marginal quantiles. [R01], [R02], [R03], [R04], [R05], [R06]

## 5. Validation and promotion policy

Before opening final evaluation outcomes, freeze each target, baseline, method set, training/validation/test windows, temporal dependence treatment, primary metrics, meaningful improvement margin, tolerated subgroup regressions, cost limits, and promotion rule. Use existing approved thresholds where appropriate; otherwise justify and commit them before evaluating the final holdout. Do not choose thresholds after seeing who wins.

Evaluate raw, incumbent, challenger, and fallback-inclusive policies on matching issue/target/observation sets. Report availability, missingness, cost, and fallback frequency separately. Use chronological rolling-origin evaluation with inner windows for tuning and later outer/as-issued outcomes for assessment. Preprocessing, adaptation, dependence templates, and observations used at a decision must have been available by that decision.

Keep all forecasts for the same observation together when estimating uncertainty. Count original measured targets, local dates, distinct events, and justified temporal blocks separately. A high number of forecast rows is not a large independent sample. Preserve sensor/grid/product/policy/model/producer cohorts and historical versus operational evidence classes.

Point outputs: MAE, RMSE, signed bias, tails, and relevant energy/temperature utility. Quantile outputs: pinball scores, interval coverage/width, and an explicitly defined weighted interval score where quantiles support it. Compute CRPS only for a declared full predictive distribution or a clearly labeled numerical approximation with specified interpolation/tails. Rain occurrence: Brier score and reliability relative to training-only climatology. Joint scenarios: temporal/cross-variable dependence diagnostics plus multivariate and application-level scores where supported. Coverage alone can be improved by uselessly widening intervals; assess sharpness/proper scores too.

Each scientific experiment retains its source-bound disposition: `adopt_candidate`, `retain_incumbent`, `reject_candidate`, or `insufficient_evidence`. The October 22 user instruction separately authorizes direct experimental production replacement in Step 11 without a parallel shadow period or proof of superior skill first. Preserve the predeclared 3% improvement, subgroup-regression and uncertainty criteria for reporting scientific evidence; they are not deployment-entry gates for this rollout. Fit only valid target definitions with the required available training inputs; retain original predictions and evaluate their real outcomes after deployment. No universal 30-day wait and no automatic qualification reset after every ordinary refit. Qualify the declared training/serving procedure while retaining artifact-level diagnostics.

## 6. Ordered implementation tasks

For every task: first add a normal-harness test or failing contract/fixture; show the relevant failure; implement the minimal change; run the focused and affected suites; record the result and reviewable commit. Preserve invariants, not just expected snapshots. Explicitly label proposed filenames below and reuse an equivalent existing module rather than building duplicate infrastructure.


**Dependencies and parallel work:** Follow the numbered order for integrated delivery. Task 2 and the original-data part of Task 4 need no expanded cloud acquisition and may proceed once Task 1 contracts are fixed. Task 5 consumes Task 3 context; Task 6 can be developed alongside those physical/context experiments. Task 7 uses the matched evaluation and source-profile contracts established earlier. Task 8's deterministic stress cases do not wait for probability qualification, but its probabilistic experiments depend on Task 7. Rain fixtures/comparisons may run in parallel with Tasks 7–8 when their sources are ready. Task 10 UI work accompanies each capability, with a final integration pass before Task 11. Shared schema and source/runtime changes need one coordinated owner.

### Task 0 — Reconcile the merged audit and actual operating state

**Files to inspect:** current `AGENTS.md`; `docs/audits/2026-10-20/`; the PR #43 audit records; current workflows and package scripts; `weather_learning/{worker,config,provider,native_forecast,shadow,monitoring,performance,pending_scores}.py`; active learning/publishing/handoff entry points. [S01], [S02], [S03], [S04], [S05], [S06], [S07], [S08], [S09]

**Consumes:** current branch, installed manifests, selectors, policy files, account/access settings. **Produces:** one current capability/runtime inventory and dependency gate.

- [x] Identify latest main, working revision, local modifications, open work, source compatibility roots, and actual scheduled commands. Preserve immutable packages and unrelated dirty overlays.
- [x] Map every required feature from source acquisition to public consumer; identify current capabilities already implemented since this plan's baseline.
- [x] Verify the relevant audit repairs and existing evaluator gates in the normal harness. If a remaining correctness defect compromises the new comparisons, fix it before using the results; parallelize independent schema/UI fixture work.
- [x] Read current cloud access eligibility, remaining quota where available, permission boundaries, and effective host limits without changing them. Mark unavailable facts explicitly.
- [x] Record a baseline with exact source/runtime IDs and known evidence limitations. Inspect elapsed natural cycles before calling an old deployment note a future dependency.

**Gate:** no dependent model selection uses a known-broken evaluator; the plan does not restart repaired audit work. Actual runtime and access facts are recorded, not assumed from repository defaults.

### Task 1 — Freeze capability contracts, acquisition profiles, and budgets

**Modify:** `weather_learning/config.py`, `contracts.py`, `normalize.py`, `weathernext_ee.py` as needed. **Proposed new module:** `weather_learning/capabilities.py`. **Proposed tests:** `weather_learning/tests/test_capability_profiles.py`.

**Consumes:** Task 0 inventory and provider contracts. **Produces:** typed interfaces in Section 4, versioned profile allowlists, resource accounting, source/consumer migration map, and predeclared evaluation specification.

Use staged profiles rather than requesting all advertised fields:

| Group | Required contents | Acquisition policy |
|---|---|---|
| Existing core | Preserve current 12 requested bands | Unchanged meaning and fallback behavior |
| Temperature display | Existing mean/p10/p90 | Reuse retained sources first; no new remote request needed |
| Additional uncertainty | Temperature p25/p50/p75; GHI p10/p50/p90; scalar wind p10/p50/p90 | Add only after budget and schema tests; p25/p75 for GHI/wind may be added when a declared scoring model needs them |
| Atmospheric context | Already retained dew-point/pressure means; new u10/v10 means and high/medium/low cloud means | Three cloud layers need explicit unit/range mappings; wind components need acquisition enablement |
| Rain uncertainty | Additional p10/p25/p50/p75/p90 for the three named rain heads | Separate lower-priority profile; stage or limit its acquisition if quota/size would threaten core service |

Each group has an explicit consumer, dataset signature, coverage policy, byte/row/pixel/time bounds, request frequency, priority, archive-growth estimate, and retry budget. Account for shared-project quota and concurrent jobs. Do not multiply request frequency just because more statistics are requested; batch compatible fields and reuse immutable completed runs. Do not claim savings without measuring them.

- [x] Add rejection tests for paid/full-ensemble/requester-billing paths; unsupported bands; cloud fractions outside 0–1; renamed fields; wrong units; mixed-run/cell products; and response/archive caps.
- [x] Specify partial availability: optional field or group failure must not suppress valid core forecasts. Avoid making every exploratory field part of the global required-variable set.
- [x] Include profile signatures in cache eligibility. An old mean-only source cannot satisfy an expanded profile. Retain supplementary originals with actual acquisition clocks; never rewrite the older source or its earlier availability.
- [x] Measure bounded real access only under existing authorization; otherwise complete fixtures and supply the exact probe/acceptance procedure. Record EECU usage when actually observable; use labeled request/byte/time budgets otherwise.

**Gate:** an explicit contract and safe migration exist before producers change. Request expansion respects existing guards; denial degrades optional capability, not correctness or core availability.

### Task 2 — Deliver the existing temperature uncertainty end to end

**Modify:** `weather_learning/provider.py`, current publication/report adapter, `src/lib/weather/{forecastDetail,detailChart,providerForecast}.js`, and the current forecast-detail UI. **Proposed modules:** `weather_learning/capability_publish.py`, `src/lib/weather/capabilityForecast.js`. **Proposed tests:** `weather_learning/tests/test_capability_publish.py`, `tests/weather-capability-forecast.test.js`, `tests/e2e/weather-capabilities.spec.js`.

**Consumes:** archived temperature statistics and Task 1 contracts. **Produces:** source-bound supplemental product and hourly uncertainty UI.

- [x] Test raw quantile preservation, Kelvin/°C/°F conversions, ties, missing percentiles, crossing quantiles, source expiry, optional failure, old payload compatibility, and mean/p50 distinction.
- [x] Publish raw mean/p10/p90 initially; include p50 only when actually acquired. Attach profile/run, initialization, actual available-at, valid time, and nominal/local-calibration labels. Never substitute mean for missing median.
- [x] Render a legible interval band and values in the existing hourly detail, with accessible legend/tooltips and unambiguous source age. Label it “WeatherNext p10–p90; local coverage not yet verified.” Do not draw it as a bound around a separately corrected mean without explaining their different sources.
- [x] Add target-matured quantile verification using original emitted values. Report raw-range coverage and quantile scores without declaring calibration from a small sample.
- [x] Preserve legacy parsers and old receipts. Serve the supplemental product through the existing fixed-route security pattern, no query-selected files or browser cloud credentials.

**Gate:** existing acquired uncertainty reaches the UI and evaluator correctly without changing deterministic model behavior. Mean-only forecasts still work when the range is unavailable.

### Task 3 — Add bounded statistics and atmospheric collection

**Modify:** the existing collector, Earth Engine reader, archive eligibility, normalizer and tests. **Proposed tests:** `weather_learning/tests/test_capability_acquisition.py`.

**Consumes:** approved profiles and budgets. **Produces:** immutable originals and normalized series for enabled groups.

- [x] Add offline SDK/query and original-response fixtures covering both native grids, full/interim horizons, all requested statistics, and partial per-group delivery.
- [x] Implement the staged profile selection and native-cell/interval validations. Retain the two native resolutions; do not invent site-specific downscaling by interpolating percentile fields.
- [x] Confirm per-write caps also cover multiple products in one collection cycle and expanded profiles. Protect raw originals and pending outcome dependencies from eviction; compute archive runway and bounded growth. Do not delete history to make room without an approved retention policy.
- [x] Report collected, normalized, consumed, unavailable, rejected, and deferred groups with specific reasons. Add bounded backoff for late provider delivery and quota restriction. Do not endlessly poll a predicted publication time.
- [x] Exercise a representative source-to-public replay under current host limits, including cold and warm caches. Verify runtime source closures and schema readers before an authorized staged collection rollout.

**Gate:** actual or fixture acquisition demonstrates every enabled band under cost/resource bounds, and optional groups cannot strand the established core pipeline.

### Task 4 — Implement and evaluate native direct/total solar

**Modify:** `weather_learning/native_forecast.py`, `household_pv_model.py`, relevant daily PV/shared baseline adapters, historical pair builders, `household/thermal_weather_conditioning.py` only where the new contract requires it. **Proposed pure module:** `weather_learning/solar_components.py`. **Proposed tests:** `openhab/scripts/test_native_solar_components.py`.

**Consumes:** same-run/cell/interval total and direct mean energies plus retained native geometry and terrain. **Produces:** a versioned component-aware forcing path, same-input training/serving replay, and a matched experiment report.

- [x] Verify provider field semantics and source metadata; block the new component method if interpretation remains ambiguous. Do not assume FDIR is DNI. [D05]
- [x] Add analytic fixtures: 1,800,000 J/m² total and 1,080,000 J/m² direct over one hour imply means of 500 and 300 W/m² and diffuse 200 W/m². A constant 30° solar elevation gives DNI 600 W/m² for that idealized fixture. These are not instructions to use one midpoint elevation for a changing real hour.
- [x] Specify a bounded intrahour reconstruction. Prefer retained geometry with a declared nonnegative direct-normal shape normalized so its horizontal integral equals original direct energy. Low-sun/zero-denominator handling must be explicit. Preserve raw interval energy before terrain masking; then remove the blocked direct beam while retaining the declared diffuse treatment.
- [x] Test sunrise/sunset, fractional origins and hour crossings, diffuse-only days, below-skyline sunlight, missing direct data, direct greater than total, negative inputs, and geometry gaps. Small floating-point discrepancies may use a versioned tolerance; substantial inconsistency must reject/fallback with a reason, not silently clip into plausibility.
- [x] Keep total-only decomposition as the declared fallback and benchmark. Share the new numerical kernel across training, serving, historical pair construction, daily potential and storage. Preserve original implementations for old forecasts.
- [x] Evaluate in two steps: native components without refitting electrical correction; then like-for-like separately refitted corrections using each baseline. Match outcomes and censoring policy. Do not compare a newly refitted challenger against an intentionally mismatched old calibration.
- [x] Evaluate thermal benefit only on comparable recorded action/state trajectories. Do not replace a lux-proxy empirical thermal target with physical GHI or facade heat gain without a distinct target/model experiment. Do not stack proxy and electrical corrections by default.

**Gate:** conserved interval semantics and train/serve parity; later held-out PV/thermal comparison; recorded disposition. Availability alone is not evidence of improvement; Step 11 uses the October 22 authorization for a reviewed, source-valid production replacement with fresh compatible calibration where needed.

### Task 5 — Add atmospheric context and controlled feature ablations

**Modify:** supplemental projection/UI; `weather_learning/{historical_pairs,historical_serving,weather_response}.py` through new versioned candidate paths; current ventilation advisory consumer only where source-qualified. **Proposed module/tests:** `weather_learning/atmospheric_context.py` and `weather_learning/tests/test_atmospheric_context.py`.

**Consumes:** native dew point/pressure, optional wind components/cloud layers, qualified local observations. **Produces:** correctly labeled atmospheric displays and bounded feature-comparison artifacts.

- [x] Expose dew point and sea-level pressure without pretending the existing temperature model already uses them. Pair temperature/dew point from compatible station/run/time sources. If derived relative humidity is shown, label it as a diagnostic derived from forecast statistics, not an exact ensemble-mean RH or a calibrated probability.
- [x] Define meteorological wind-from direction with cardinal-vector tests: u=1,v=0 means wind from west (270°); u=0,v=-1 means wind from north (0°); zero/indeterminate vector means direction unavailable. Keep the provided scalar speed separate from magnitude of the mean vector. Never relabel either as a gust.
- [x] Add high/medium/low cloud validation and labels. Do not sum layer percentages into total cloud or assume layers are disjoint. Compare pressure only against a compatible station/sea-level convention; keep any conversion assumptions explicit.
- [x] Provide moisture-aware read-only ventilation context only when indoor temperature/humidity sources meet current quality/freshness contracts. Without them, display outdoor moisture information and the missing dependency. Do not infer safe condensation conditions without surface-temperature evidence or a separately declared model.
- [x] Run individual feature-group ablations for temperature residuals/local wind/thermal forecasts. Use forecast-time or origin-time data only, never future observed weather as a predictor. Test gain-only versus one bounded wind challenger; direction features require genuine retained support.

**Gate:** added fields have useful, truthful consumers; feature groups get evidence-backed dispositions; no atmospheric field silently grants action authority or changes PV cooling wind.

### Task 6 — Evaluate actual hourly updates and a near-term correction profile

**Modify:** `weather_learning/{archive,provider,shadow,monitoring,performance,pending_scores,historical_serving}.py` or their current equivalents. **Proposed module/tests:** `weather_learning/refresh_evaluation.py` and `weather_learning/tests/test_refresh_evaluation.py`.

**Consumes:** actual run availability, original publication selections, measured targets, bounded source profiles. **Produces:** latest-available serving-policy evidence and separately identified near-term correction outputs.

- [x] Preserve the existing first-original-per-local-day benchmark. Add a separate evaluation population for actual scheduled publication decisions; do not change the old population retroactively.
- [x] At each eligible decision compare latest available interim, latest available full-range, actual serving policy, raw baseline and any corrected candidates on identical targets. Record initialization age, actual availability lag, local issue age, remaining coverage, and revision magnitude.
- [x] Test a nominal 48-hour interim run arriving more than seven hours after initialization. It must not advertise 48 future hours from arrival. A full-range correction requirement must not accidentally exclude useful near-term sources.
- [x] Implement a separately identified 24-hour near-term local-correction path; use the same source run for origin-bias estimation and future predictors, or declare and validate a source-mixing method explicitly. Keep extended correction and display-composite provenance distinct.
- [x] Handle delayed/incomplete runs with deterministic selection based only on facts known at the decision. A newer initialization is not automatically better; evaluate the actual policy. Never backfill an “issued” prediction with a run fetched afterward.
- [x] Retain or index enough original profile decisions for bounded replay and long-horizon outcome maturity. If sampling is needed for resource limits, predeclare it and do not call the sample exhaustive all-cycle verification.

**Gate:** the project can measure whether hourly refresh helps the forecasts it actually serves. New near-term corrections have independent identity, fallback, source binding, and evidence; an interim source cannot corrupt extended products.

### Task 7 — Implement bounded local marginal calibration

**Modify:** current weather-learning training, feature, serving, score and qualification modules; retain legacy numerical dispatch. **Proposed module/tests:** `weather_learning/probabilistic.py` and `weather_learning/tests/test_probabilistic.py`.

**Consumes:** repaired/matched evaluator, declared profiles, original statistics, compatible local targets. **Produces:** adaptive temperature candidate, marginal-distribution candidates, original predictive records, and qualification reports.

- [x] Implement the predeclared temperature adaptive-error challenger using only already available residuals; freeze the decay selection and any training window before outer evaluation. A cold or expired adaptation state falls back explicitly.
- [x] Implement one low-dimensional location/positive-scale temperature model, or an equivalent regularized quantile-calibration model, plus the simple empirical residual-interval benchmark. Native p90–p10 is a predictor; two quantiles are not the full ensemble variance. Handle near-zero spread and missing statistics without division errors or invented certainty. [R01], [R03]
- [x] Add one nonnegative irradiance marginal candidate for the explicitly named local proxy target, and uncertainty evaluation for the wind candidate where observations support it. Nighttime zero solar and zero wind/rain need their declared distributions; do not apply a Gaussian everywhere by convenience.
- [x] Freeze preprocessing, coefficients, training/availability cutoffs, target definitions, observation cohorts, runtime identities and prediction object. Retain fitted values at issuance so later scoring never refits them.
- [x] Compare point error, interval sharpness/coverage and proper scores across lead, local hour, season and supported regimes. Report absent regimes and group sizes. Avoid claiming rare-event or all-season calibration from dense but narrow data.
- [x] Wire bounded prospective scoring and status into the existing monitor; expose separate raw and local-calibrated products only under their actual qualification state.

**Gate:** full implementation and tests exist, with results on all eligible data and specific evidence blockers otherwise. Retain the actual scientific comparison result. Step 11 may install the new technically valid method under the October 22 experimental production authorization; raw ranges and explicit validity fallbacks remain usable without a shadow prerequisite.

### Task 8 — Build household stress cases and test coherent scenarios

**Modify:** current pure thermal/PV/storage projection and report consumers, not owner actuation. **Proposed module/tests:** `weather_learning/scenarios.py`, `openhab/scripts/test_household_weather_scenarios.py`.

**Consumes:** source-bound weather profiles, existing household state/model assumptions, and optionally calibrated marginal forecasts. **Produces:** labeled deterministic stress reports and a separate joint-scenario experiment.

- [x] First implement a small fixed set of deterministic stress cases, such as central, reduced-solar, and warm/high-gain conditions. Record their construction and target horizon. A sequence using every hourly p10 may be a deliberate stress input, but must have `probability_claim=False` and must not be described as a p10 battery trajectory.
- [x] Test one bounded joint method using historical, issue-available residual blocks or analog rank templates to preserve temporal and cross-variable behavior. Freeze template selection, seed, scenario count and runtime budget. Do not claim ECC from native members when no members are available. [R02]
- [x] Use native geometry and constraints to keep night solar zero and variables/intervals consistent; document any reconciliation. Reject unsupported joint combinations rather than silently treating marginal percentile combinations as coherent weather.
- [x] Propagate each valid trajectory through the same versioned physical model. Keep weather, household-load, initial-state and model-parameter uncertainty scopes explicit. Weather-only uncertainty is not total battery/thermal uncertainty.
- [x] Evaluate daily energy, minimum nominal SoC, and indoor/wall outcomes on actual matching evidence. Use multivariate/dependence diagnostics and application scores; verify temporal correlation, ramp behavior, joint extremes and trajectory coverage. Parameter/acceptance uncertainty and sensor limitations remain visible.
- [x] Publish stress results as advisory. Withhold numerical probabilities of reserve breach/overheating until the joint method and downstream target are qualified; never equate an ensemble count from an unvalidated local model with an established risk probability.

**Gate:** useful stress cases work independently of probability qualification. Scenario software, experiments and explicit uncertainty limits are complete even if real evidence requires the probabilistic product to remain unavailable.

### Task 9 — Compare precipitation products and local occurrence/amount

**Modify:** `weather_learning/{energy_shadow,weather_response,monitoring,provider}.py` and current rain readers under new explicit contracts. **Proposed module/tests:** `weather_learning/rain_calibration.py` and `weather_learning/tests/test_rain_calibration.py`.

**Consumes:** separate precipitation-head originals/statistics and qualified accumulation observations. **Produces:** matched product comparison, bounded local occurrence/amount experiment, original forecast retention, and a selection disposition.

- [x] Compare all three raw products on the same complete targets. Separate local-calendar daily totals, rolling 24-hour totals, and partial remaining-day totals; retain interval and DST semantics. Mean totals may be summed; marginal rain quantiles may not.
- [x] Predeclare wet-event thresholds consistent with gauge resolution/boundary uncertainty and relevant household use. Do not classify ambiguous small accumulation as certainly wet/dry. Assess wet-event amount, false alarms, missed events and timing as well as aggregate error.
- [x] Implement a small two-part model: occurrence probability and conditional positive amount. Use training-only climatology as the probability benchmark. If a censored shifted-gamma method is chosen instead, document why and keep the model set bounded. [R04]
- [x] Probability labels identify a locally learned forecast, target interval and method; they are not native Google probabilities. A cumulative probability must come from an appropriately trained interval target or coherent joint method, not summed hourly probabilities/quantiles.
- [x] Fit only when the prescribed class/event support exists. All-dry, sparse-wet and unseen-regime cases produce explicit `insufficient_evidence`, not a fabricated calibrated probability. Complete the fixtures, collection, scoring and pending evidence report anyway.
- [x] Record the raw production rain baseline and scientific selection disposition at the Task 9 assessment. Step 11 governs the later authorized replacement: use the new rain method when its target and required training class/event inputs are valid, or name the exact dependency and declared raw fallback. Do not manufacture wet-event support or calibrated probability. Support roof-collection decisions with rainfall information only; do not calculate cistern availability without independently approved roof/runoff/reserve/inventory inputs.

**Gate:** no gain is promoted for looking good only on dry days. Each head and candidate has matched coverage, scores, uncertainty and a clear retained/selected/deferred disposition.

### Task 10 — Complete UI, observability, and capability dispositions

**Modify:** current Home/Weather/Energy/Earthship/ventilation-advisory components, shared fixed-report stores/parsers and operational reports. **Proposed tests:** extend `tests/e2e/weather-capabilities.spec.js` and existing Energy/Earthship fixtures.

**Consumes:** versioned products from prior tasks. **Produces:** coherent user-facing distinctions and an operational capability matrix.

- [x] Keep the default console readable at 1340×800 and 1280×720. Put detailed ranges, source age, profiles, method, support, limitations and candidate diagnostics in existing expandable detail views; avoid cluttering every tile.
- [x] Test loading, zero values, nulls, stale/withdrawn reports, malformed schemas, offline/reconnect, keyboard focus, touch targets, chart resize, accessible legends, and no unauthorized mutation/network requests.
- [x] Preserve terrain direct-sun versus astronomical daylight, native direct/diffuse versus proxy radiation, raw versus local forecasts, nominal storage versus measured history, and mean/median/range/probability distinctions.
- [x] Add operational measures for ingestion lag, provider revision, enabled groups, optional refusals, query/byte/runtime/usage accounting, archive runway, pending/expired scores, correction coverage, and selected model/procedure identity. Keep sensitive diagnostics private.
- [x] Record an explicit horizon decision: retain the ten-day default unless a bounded expandable long-range view provides useful actual remaining coverage and honest uncertainty. Do not promise a full 15 days after publication from a 360-hour-from-initialization product. Parser/test hard limits must agree with the chosen display.
- [x] Record intentionally unused capabilities: no 100 m turbine winds, upper-air/ocean fields, arbitrary-coordinate custom inference, bulk spatial downloads, full ensembles, or paid backend migration. Document reasons and the specific new use case/evidence that would justify revisiting them, rather than implementing unnecessary features.

**Gate:** every recommendation has a disposition; no fabricated probability, freshness, physical calibration, or completeness claim reaches the UI.

### Task 11 — Verify, retrain, replace production models, and evaluate real outcomes

**Files:** affected normal tests/workflows, retraining and active-serving adapters, release/source/model/selector manifests, deployment/rollback tooling, actual-issued evaluators and one current delivery record.

**Consumes:** complete implementations, available historical observations, retained experiment/source records and the October 22 direct-production authorization. **Produces:** reviewed and verified replacement models active in production, actual-outcome evaluation, exact rollback and honest remaining scientific dependencies.

- [x] Build a per-model replacement manifest naming the existing and replacement method, training procedure, artifact, numerical source closure, input/observation cohort, effective default and exact rollback. New methods are the production target, not optional shadow challengers left alongside the incumbent. Record any target that cannot produce a valid fitted prediction with its concrete missing input/support; do not substitute a blanket incumbent-retention rule.
- [x] Retrain against the available historical data where needed, using the corrected production numerical path and already available observations. Preserve chronological cutoffs, target definitions, sensor/grid epochs and the small declared method set. Store fresh artifact/procedure identities and original fit clocks. Refit electrical calibration when changing the PV/solar baseline; never apply old coefficients to a changed baseline under the old identity. Keep immutable historical source packages and experiment results replayable.
- [x] Run normal dependency-pinned unit/build/browser checks, all required OpenHAB partitions, WeatherNext SDK/contracts, sensor/receipt/native/delivery gates affected by shared changes, and numerical golden/old-producer replay. Inventory every new test into current CI ownership. Review the exact integrated source and concrete replacement manifest before release.
- [x] Migrate compatible readers and schemas before new production outputs publish. Test optional-field failure, source-closure changes, original admission expiry, fit no-op, genuine new fit, interrupted promotion, post-publish nonzero exit, concurrent selector edits and rollback. Preserve post-PR #43 readback truthfulness. Create new production admission/emission identities rather than changing immutable shadow receipts or qualification flags.
- [x] Deploy the richer read-only consumers and required bounded acquisition, then switch the registered replacement models/improvements to the active production defaults in Step 11. Use reversible selectors/flags. No separate parallel shadow deployment or elapsed shadow-scoring period is required, and the scientific improvement thresholds are not deployment-entry gates under this user-authorized experimental production rollout.
- [x] Retain the actual predictions emitted by the replacement models before their targets occur and compare them with real observations after target maturity through the bounded evaluator. Report point, interval, rain and household metrics only for their valid targets/cohorts. Use preserved historical comparisons where comparable; do not run the old models in parallel or invent old live predictions. Keep scoring, qualification and production admission distinct.
- [x] Read back installed source, environment, schemas, effective selectors/artifacts, resource caps and current report consumers. Observe archive growth and actual request/byte/runtime costs at each stage. Verify available natural cycles and view the UI against actual OpenHAB data. Historical retraining and model replacement are authorized by the October 22 instruction; do not fabricate observations, stimulate hardware or grant new control/billing authority.
- [x] Verify exact rollback for each changed source, reader, model and selector. Retain old artifacts for rollback and historical replay, without scheduling a parallel shadow pipeline. A runtime validity failure may use its explicitly declared safe fallback; retain newly emitted originals and scoring state across rollback.
- [x] Freeze the final verification revision, source/evidence manifest and delivery record. Separate implemented, passing, installed, active, naturally exercised and scientifically supported claims. Include the post-deployment evaluation schedule and a finite checklist for remaining wet events, horizon maturity and measurement quality. These pending scientific outcomes do not postpone otherwise valid production replacement or unblocked engineering.

**Gate:** The reviewed integrated source and newly trained/registered methods are installed as the active production defaults, with original as-issued scoring against real observations and verified rollback. No parallel shadow period or advance proof of superior skill is required. Invalid inputs, unsupported target definitions and unqualified probability/physical claims remain refused; deployment is not a claim of improvement.

## 7. Required regression scenarios

These tests supplement the existing suites; they are not the entire verification requirement.

| ID | Scenario | Required result |
|---|---|---|
| T01 | Current/legacy schemas, missing supplemental report | Existing deterministic UI/replay remain valid |
| T02 | Optional quantile/dewpoint/cloud group fails | Core forecast remains valid; group explains missingness |
| T03 | p10=p50=p90=0 rain; mean differs from median | Accepted and truthfully labeled |
| T04 | Crossing/nonfinite quantiles; mean outside nominal range | Reject malformed quantiles; do not reject a valid mean merely for lying outside the range |
| T05 | 273.15 K and a 10 K spread | 32°F value and 18°F spread, without applying the temperature offset to a spread |
| T06 | Expanded profile against old cached subset | Old cache cannot falsely satisfy new fields; originals unchanged |
| T07 | Two writes approach byte/object cap in one cycle | Second write checked against updated usage; no overrun |
| T08 | Restricted quota/late provider run | Bounded retries/deferred optional work, no billing or fallback provider |
| T09 | Solar 1.8 MJ total / 1.08 MJ direct over 1 h | 500/300/200 W/m² total/direct-horizontal/diffuse |
| T10 | Ideal constant 30° elevation | 300 W/m² direct-horizontal corresponds to 600 W/m² DNI |
| T11 | Real varying elevation/hour crossing/terrain masking | Declared reconstruction conserves original energy before terrain loss; diffuse is not incorrectly erased |
| T12 | Missing direct or substantial direct>total | Explicit versioned total-only fallback/rejection, no silent fabricated component |
| T13 | Same inputs to training and serving | Exact or predeclared numerical-tolerance parity and identical units/intervals |
| T14 | u/v cardinal directions and calm | Correct wind-from direction; calm unavailable; scalar speed retained separately |
| T15 | Mixed pressure conventions or absent indoor humidity | No false matched comparison or moisture/condensation assurance |
| T16 | 23/25-hour Denver day, 1 mm/h mean | Complete total 23/25 mm; no synthetic 24-hour assumption |
| T17 | Add hourly marginal rain/solar p10 | Not labeled a daily p10; reject quantile aggregation API misuse |
| T18 | 48 h interim arrives >7 h after init | Only actual remaining targets available; 24 h near profile selected when supported |
| T19 | Late run or observation discovered after decision | Cannot enter historical as-issued features or selection |
| T20 | Many forecasts verify against one observation | Correct target weights/cohorts; no inflated independent sample count |
| T21 | Sparse statistics, zero spread, cold adaptive state | Bounded calibrated-model refusal/fallback, no infinite confidence |
| T22 | Candidate available only on easy targets | Matched comparison plus full fallback-policy result and availability |
| T23 | Old and new model scores mixed | Policy and artifact results distinct, no old skill attributed to new weights |
| T24 | Stress trajectory using marginal endpoints | Explicit hypothetical label and no probability claim |
| T25 | Joint scenario resampling/template selection | Uses only past available blocks; deterministic replay and bounded runtime |
| T26 | All-dry or uncertain-boundary rain observations | No unsupported occurrence model or promotion |
| T27 | New consumer/source closure with old admission | Staged compatible handoff or truthful fallback; never bypass source checks |
| T28 | Selector changes then child exits unsuccessfully | Readback describes changed/uncertain state, not unsupported preservation |
| T29 | Long-horizon score plus restart/late observation | Original prediction matures once under bounded durable work |
| T30 | Both console sizes, stale/offline optional products | Legible layout, accurate source/qualification status, no page errors or unexpected commands |

## 8. Verification commands and evidence discipline

Discover the actual commands from the executing revision, then use its pinned environments. The established frontend starting points are:

```bash
npm ci
npm run test:unit
npm run build
npm run test:geometry
npm run test:e2e
```

For new Python tests placed in the proposed location, a focused invocation is:

```bash
PYTHONPATH="$PWD/openhab/scripts:$PWD/.ci/solar-pv/analytics/src" \
  python -m pytest -q openhab/scripts/weather_learning/tests/test_capability_profiles.py \
  openhab/scripts/weather_learning/tests/test_capability_publish.py \
  openhab/scripts/weather_learning/tests/test_capability_acquisition.py
```

Those test paths are planned deliverables, not pre-existing files. Run later proposed modules and all affected existing suites as they are implemented. The executing workflow may use additional companion profiles and Python interpreters; do not substitute this illustrative command for that setup. Verify discovery and CI ownership for every new test.

Keep RED/GREEN evidence for each change, independent analytic fixtures for numerical conversions, source-bound replay for original forecasts, and real-data comparisons distinct from synthetic tests. A passed workflow is not Google-account approval, observed runtime use, physical calibration, or statistical superiority. Do not sum overlapping focused and full-suite test counts as unique tests.

## 9. Deliverables and definition of done

Create or extend a single current work area, preferably `docs/operations/weathernext3-capabilities/`, with a scope/runtime inventory, contract/profile specification, evaluation protocol, concise findings/decisions, verification record and release/rollback record. Retain large private evidence locally; publish only curated identifiers and summaries.

For each enabled field or feature, the final capability matrix records: available upstream; acquired; normalized; source-bound; consumed; tested; deployed; operationally observed; statistical/physical qualification; cost; and explicit limitations.

Completion requires:

1. Every WN requirement has an implemented and verified result or a precise, genuine external dependency. Deliberately unused capabilities have documented dispositions, not hidden TODOs.
2. Existing temperature ranges, atmospheric context, optional-domain isolation, original selection/profile clocks, and cost/resource safeguards work end to end.
3. Native solar, refresh, adaptive/marginal, joint-scenario and rainfall comparison software and normal-harness tests are complete. All locally supported experiments have run and retain reproducible results; unsupported experiments identify exact missing evidence. No blanket “research later” substitutes for implementable work.
4. Every production replacement has an explicit method/artifact/procedure/source manifest, historical retraining where needed, valid inputs, integration tests, installed-selector readback and rollback. Preserve predeclared historical comparison results and evaluate actual replacement predictions against real outcomes. A separate shadow period or superior-score gate is not required for the October 22 authorized rollout. Name exact unsupported targets individually; do not use blanket incumbent retention as completion.
5. Old source/forecast/model/score evidence remains replayable. New schema readers, current consumers and source closures are migrated together; rollback preserves newly emitted originals and scoring state.
6. The exact integrated source passes its required tests. Installed and natural-cycle evidence is separately recorded where authorized and available.
7. No new billing, provider, full-ensemble access, private-data exposure, planner/feeder authority, or weakened safety/resource gate was introduced.
8. The final handoff explains what users gain now, which predictors or methods proved useful, which did not, what remains provisional, and what exact observations would permit each pending claim.

**Do not wait indefinitely for rain, a season, or a 14-day target to finish unblocked engineering. Do not claim those outcomes exist. Deliver the implemented system and precise pending-evidence state, while closing every implementable requirement.**

## 10. Source and research references

Repository links are pinned to the planning baseline. Consult the corresponding current sources while executing; preserve these links as evidence of the starting design.

[S01]: https://github.com/santyr/earthship-ui/commit/cdfaa6b51b568423a5aada34a930094c7cf0730b
[S02]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/worker.py
[S03]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/provider.py
[S04]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/normalize.py
[S05]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/config.py
[S06]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/native_forecast.py
[S07]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/src/lib/weather/forecastDetail.js
[S08]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/performance.py
[S09]: https://github.com/santyr/earthship-ui/blob/cdfaa6b51b568423a5aada34a930094c7cf0730b/openhab/scripts/weather_learning/pending_scores.py

Current provider documentation, checked October 21, 2026:

[D01]: https://developers.google.com/weathernext/guides/earth-engine
[D02]: https://developers.google.com/weathernext/guides/models
[D03]: https://developers.google.com/weathernext/guides/dissemination
[D04]: https://developers.google.com/earth-engine/guides/noncommercial_tiers
[D05]: https://codes.ecmwf.int/grib/param-db/228021
[D06]: https://developers.google.com/weathernext/guides/gcs

- **D01:** Earth Engine collection/statistic contract. Verify the requested field availability and current schema; statistics are not joint members.
- **D02:** WeatherNext variable names, units, native grids and run horizons. Treat native station-grid output as a grid product, not custom inference at the household sensor.
- **D03:** Delivery targets and variability. Discovery/actual first availability remain authoritative.
- **D04:** Noncommercial eligibility/usage limits. Check the actual account and do not change its tier or billing configuration.
- **D05:** Direct-horizontal radiation parameter definition and accumulation units. Cross-check the actual WeatherNext metadata before implementing the component method.
- **D06:** Distinction between precomputed statistics and requester-pays full ensemble access. This goal retains statistics-only access.

Research guidance; applicability must be tested, not assumed:

[R01]: https://journals.ametsoc.org/view/journals/mwre/133/5/mwr2904.1.xml
[R02]: https://arxiv.org/abs/1302.7149
[R03]: https://arxiv.org/abs/1903.06739
[R04]: https://repository.library.noaa.gov/view/noaa/14608
[R05]: https://www.jmlr.org/papers/v11/cawley10a.html
[R06]: https://pvpmc.sandia.gov/model-validation/model-validation-procedure/

- **R01:** Gneiting, Raftery, Westveld and Goldman (2005), *Calibrated Probabilistic Forecasting Using Ensemble Model Output Statistics and Minimum CRPS Estimation*. Basis for separating correction of forecast location from dispersion.
- **R02:** Schefzik, Thorarinsdottir and Gneiting (2013), *Uncertainty Quantification in Complex Simulation Models Using Ensemble Copula Coupling*. Explains the role of dependence; native member-rank ECC is not available from marginal quantiles alone.
- **R03:** Möller and Groß (2019 preprint), *Probabilistic Temperature Forecasting with a Heteroscedastic Autoregressive Ensemble Postprocessing Model*. Motivation for a small past-error/adaptive challenger, not a promise of local gains.
- **R04:** Scheuerer and Hamill (2015), *Statistical Postprocessing of Ensemble Precipitation Forecasts by Fitting Censored, Shifted Gamma Distributions*. Motivation for explicit zero/positive-rain structure and adequate training support.
- **R05:** Cawley and Talbot (2010), *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*. Keep tuning and final assessment separate; do not repeatedly mine the same holdout.
- **R06:** Sandia PV Performance Modeling Collaborative, *Model Validation Procedure*. Compare component behavior, residuals and baselines; total-chain error cannot identify every physical parameter.
