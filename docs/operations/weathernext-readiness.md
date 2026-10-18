# WeatherNext migration readiness

Updated 2026-10-18. Execution branch: `feat/weathernext-migration-20261018`; base `0710a08f2a9dabcd7f5dd824dc99511642c6c728`. The operator authorized execution of the existing exclusive-provider plan. This is an implementation/readiness report, not a production cutover approval or skill result.

## Operator-confirmed clean start

On October 18 the operator required fresh weather-related ML with **WeatherNext 3 forecasts plus qualified local measurements**. New weather-model fitting/state cannot reuse Open-Meteo forecasts, features, biases, backfill seeds, error history, pending targets or fitted weather-dependent weights. Local observations, physical configuration and their existing qualification rules remain. Audit downstream weather-dependent components for fresh Google/local fitting; fixed old artifacts are pre-cutover controls only.

At production cutover, remove Open-Meteo completely from OpenHAB and the active Earthship UI project, including AQI integration and obsolete tooling/state references. No post-cutover capture-only period or provider fallback remains. This supersedes the old delayed-retirement sequence, without claiming cutover has occurred. The [reset/removal contract and dependency inventory](openmeteo-retirement.md) defines the acceptance checks.

## Access and acquisition

Google approved access. The private reader authenticates; statistics GCS listing and a real 0.1-degree temperature read succeeded. On October 18 the operator added the exact reader as a principal on project IAM with Owner. At **14:54:00Z**, all five required permissions were visible and the EE project configuration returned HTTP 200 with `REGISTERED_NOT_COMMERCIALLY`. Account setup is no longer the observed blocker. No IAM, API, registration or billing changes were made by the agent.

At **18:20:30Z**, the corrected native collector successfully archived a complete **360-hour / 10-band / 3,600-point** WeatherNext issue in **10.11 seconds**, receiving **1,255,580 bytes** with **72,128 KiB peak RSS**. The access blocker was a missing read-only Cloud Storage OAuth scope in the custom credential loader, followed by a parser assumption that source image time always meant forecast valid time. Both are corrected with regression tests; the native cell, source/run identity, original timestamps and acquisition/resource/cost bounds are preserved. No new IAM grant or credential was needed. The [live API compatibility report](2026-10-18-weathernext-api-compatibility.md) records the controlled comparison, documentation review, exact snapshot identity and limitations. The [earlier raster diagnosis](2026-10-18-weathernext-ee-raster-diagnosis.md) is historical and superseded. The [backend activation](2026-10-18-weathernext-shadow-activation.md) subsequently verified a pinned installed collector run and enabled hourly collection/private issue recording plus separate weekly shadow fitting. Natural timer execution and production cutover remain unverified; shadow Item publication stays disabled.

## Qualified household evidence

A bounded read-only audit at 2026-10-18T13:52:57Z found 81,913 original temperature snapshots retained from 2026-09-20T00:17:03Z to 2026-10-18T13:52:28Z. Raw snapshot count is not a count of qualified training labels. The existing native daily validator proved complete outdoor-temperature coverage for October 15, 16 and 17 (each 86,400 seconds) in the same hardware epoch. Three sampled days are not the full retained training range.

The existing qualified PV reader accepted all three sampled days (coverage 99.9617%, 99.9757%, 99.9747%). The rain reader accepted October 15 and 16 and withheld October 17. Missing rain evidence remains unavailable. No evidence gates or model coefficients changed.

| Source | Existing authoritative reader | Current migration inventory | Consumers |
|---|---|---|---|
| Outdoor temperature | `daily_temperature_runtime.collect_v2`, `weather_temperature_history` | 7 complete current-epoch days, October 11–17, in the 28-day audit | Weather correction, thermal forcing/outcomes |
| Irradiance | `weather_radiation_history`, `household.measured_weather` | 9 complete qualified days in October 3–17; lux-derived proxy, not a physical radiometer | Solar-forcing comparison, fixed-model PV/thermal attribution |
| Rainfall | `weather_rain_history` | 10 accepted days in the 28-day audit; other days withheld | Forecast precipitation outcomes |
| MPPT harvested PV | `pv_day_history` | 18 accepted days in the 28-day audit | Existing PV calibration and outcomes |
| Battery/AC load | `household_battery_source`, `household_ac_load_window` | 7 measured current-epoch nights (October 10–16 prediction dates); 327/336 eligible AC hours, October 4–17, partitioned across 5 receiver epochs | Evening SoC, overnight trough, charge/no-full outcomes |
| Indoor temperature | `weather_temperature_history` native role streams | Bedroom/indoor/north_wall current epochs audited; no full 24-hour days in October 3–17; shorter qualified thermal windows retain existing rules | Fixed-artifact thermal attribution |
| Operator actions/shades | `thermal_model.action_history`, `thermal_model.shade_observations` | 19 action events, 4 mode events, 13 receipts; 14 origin-aware snapshots selected; continuous/per-zone observation not established | Known action context; no action effects inferred |
| Original incumbent issues | Existing forecast/thermal original captures | 129 validated original capture files, October 1–18, 18 capture dates; pre-cutover controls only, excluded from new fitting | Paired chronological comparison |
| Prospective WeatherNext issues | New private content-addressed archive | 0 scheduled issues so far | Future comparison evidence |

The inventory helper counts only typed windows supplied by source validators, requires original digests and complete post-cutover windows, partitions by hardware epoch, rejects conflicting proofs and cannot turn raw numeric rows into qualified labels. The initial audit did not query original forecast archives: its zero counted issues means no verified inputs supplied, not proof that no archives exist. Temperature is ready to begin shadow acquisition and paired qualification; no variable is qualified for production cutover yet.

## Required provider field mapping

| Incumbent field(s) | WeatherNext replacement | Remaining qualification |
|---|---|---|
| Hourly `temperature_2m`; daily max/min | `station_head_temperature_2m_mean` (0.05°), convert K to °C/F; aggregate complete local days | Native-cell live extraction, paired chronological skill |
| `shortwave_radiation`, `shortwave_radiation_sum` | `surface_solar_radiation_downwards_1hr_mean`, J/m² interval to W/m² and daily kWh/m² | Qualified irradiance comparison, DST, fixed PV/thermal forcing attribution |
| Direct solar thermal/PV attribution | `total_sky_direct_solar_radiation_at_surface_1hr_mean` | Separate direct-beam qualification |
| `precipitation`, daily `precipitation_sum` | `total_precipitation_1hr_mean`, m to mm/in | Qualified rain-event scoring, product choice |
| `precipitation_probability`, daily max | No exact equivalent established from marginal percentiles | Explicit mapping/UI decision required; do not invent percentages or fill zero |
| `wind_speed_10m` | Native `wind_speed_10m_mean`, m/s to mph for existing consumers | Units and paired coverage |
| `cloud_cover_mean` | Hourly `total_cloud_cover_mean`, fraction to percent | Complete-day aggregation and required-consumer checks |
| `weather_code` | No native WMO weather-code band established | Explicit derived-condition contract or visible unavailable value; never fake clear skies |
| `is_day` | Existing native Astro context at the site | Verify timestamps/coverage, no weather-provider approximation |
| Current AQI, if separately supplied by Open-Meteo | WeatherNext has no qualified AQI replacement in this mapping | Remove Open-Meteo AQI integration at cutover; unsupported display/alerts must become unavailable or be removed |

## Release gates and current limitations

The approved plan calls for 30 consecutive prospective acquisition days, 60 qualified temperature training days plus an untouched 30-day holdout when available, and 14 days of normal local-model shadow inference. None of that is established by an authentication test or historical download. Preserve the incumbent until required variable/horizon gates pass; remove it in the cutover release with no capture-only service or fallback.

Production forecasts, correction state, thermal/PV coefficients, notification policy and actuator authority are unchanged. Recovery work remains deferred per operator instruction.

## Implementation increment (2026-10-18)

Implemented the explicit site/cost policy, restricted Earth Engine HTTP transport, bounded native-cell reader/parser, probe/default-shadow CLI, single collector lock, immutable source-bound archive/index, freshness/horizon checks, and frozen unit/interval normalization. The isolated dependency environment is pinned in `requirements-weathernext.txt`. Fifty-two focused tests pass in that environment; the service/timer templates pass systemd verification. The reviewed backend units are now installed/enabled with shadow Item publication explicitly omitted; see the activation record. The corrected CLI has now completed a real native 360-hour snapshot; see the current access section and live API compatibility report. Production publication remains unselected, and no prospective reliability or forecast-skill interval is implied.

The scheduler template uses the existing shared job-admission launcher, with no resource-policy changes. It performs shadow collection only and has no OpenHAB publisher, actuator or notification function. The archive refuses after 16 GiB / 10,000 objects or inadequate disk headroom rather than silently deleting retained evidence.

Latest raw-storage audit (14:12Z; raw snapshots are not qualified windows):

| Item | First retained UTC | Last retained UTC | Raw snapshots |
|---|---|---|---:|
| Radiation evidence | 2026-10-02 15:30:39 | 2026-10-18 14:11:58 | 44,880 |
| Rain evidence | 2026-09-29 04:12:48 | 2026-10-18 14:11:58 | 55,023 |
| MPPT day evidence | 2026-09-28 14:06:49 | 2026-10-18 14:11:47 | 40,080 |
| Battery SoC evidence | 2026-09-10 21:51:32 | 2026-10-18 14:11:35 | 59,475 |
| Inverter AC evidence | 2026-09-23 20:55:12 | 2026-10-18 14:12:03 | 411,943 |

The incumbent `forecast-intel/weather-inputs` directory contains 129 files totaling 91,004 bytes. At 14:37:43Z all 129 passed the existing source/digest/schema reader (zero refusals), spanning capture times October 1 at 00:11:58Z to October 18 at 12:40:44Z across 18 capture dates. This does not establish provider publication times or prospective WeatherNext pairs. These records are separate pre-cutover controls, excluded from new weather-model fitting.

The completed 28-day audit (September 20–October 17, assessed October 18 at 14:21Z) accepted **7 complete current-epoch outdoor-temperature days** (October 11–17), **18 PV days**, and **10 rain days** using the existing production-qualified readers. Other sampled days were withheld; the audit does not merge earlier receipt formats into the current hardware epoch. Per-variable accepted date lists and refusal reasons are retained privately in `source-audit-28days.json`.

Independent review found and fixed a native-projection argument mismatch, a scheduler/collection-admission profile mismatch, and the absence of an interrupting total response deadline. Each was reproduced before its fix. The scheduler now uses the existing collection profile (256 MiB preferred/minimum, 24 tasks, 90 seconds); acquisition has a 75-second total interrupting budget plus the unchanged outer host safeguards. A separate CI job runs the pinned SDK tests without cloud credentials.

Deferred minor limitations: archive validation binds point digests to retained originals but does not independently rederive every normalized point from those originals; the current reader/parser owns that validation. `AccessPolicy.max_attempts` and `max_pixels` are reserved configuration bounds, not independent active transport controls; actual retry count is zero and acquisition uses a fixed single-point query with strict response/target bounds. Neither limitation authorizes production cutover.


The radiation/indoor audit at 14:39:05Z accepted 9 complete radiation days from October 3–17 using the existing reviewed radiation-v2 cutover (October 2 at 20:00:09.206165Z). The measured signal is a lux-derived proxy. Three indoor streams had no complete current-epoch 24-hour days in that sample; the existing thermal trainer can use shorter qualified windows, so this audit adds no daily-coverage requirement and makes no claim that thermal training is unavailable. Source receipts/refusals are private in `radiation-indoor-audit.json`. The later [energy/action audit](2026-10-18-weathernext-energy-action-evidence.md) completes the sampled battery/load and action-range inventory using existing credentials and unchanged policies; no new database grants were introduced.


## Fresh local-learning implementation (2026-10-18)

`weather_learning/features.py`, `training.py` and `evaluation.py` now implement a separate WeatherNext-only temperature pipeline. The feature builder checks original snapshot/issue availability and rederives normalized points from retained Google capsules before using them. Point outcomes reuse the existing native outdoor metadata validator; grids and sensor epochs cannot be pooled. No incumbent learning state is read or imported.

Candidates are raw WeatherNext/untrained, bounded bias, and a seven-feature standardized ridge residual model (native mean/spread, lead, local hour and season). The default correction bound is 6 degrees C, recorded in each artifact. Artifacts freeze source manifests, training clocks, preprocessing, coefficients, code revision and cohort identity. Prepared inference validates/copies the artifact once per batch. A unique target-date count is not a complete qualified-day count.

The evaluator enforces chronological train/embargo/holdout boundaries, retains the predeclared criterion (default 10% lower paired day-weighted MAE), and reports MAE/RMSE/signed bias/pair-tail error by decision horizon and diagnostic regime. Persistence uses only prior qualified local outcomes. Original incumbent forecasts are optional as-issued controls; they cannot enter fitting. Each scored persistence prediction retains its selected receipt and original target/availability clocks in the frozen report. Identical pairs are idempotent and conflicting snapshots for one decision/target are refused. Regime annotations alone do not qualify evidence.

This increment is offline implementation, not a fitted site model or a completed Task 5. Reports remain `SHADOW_ONLY` and explicitly list prospective acquisition, complete training/holdout days, shadow inference, qualified regimes and required-variable gates as missing release evidence. Live-source reports, real model fitting, scheduled training/inference, comparison UI and cutover remain unfinished. No synthetic fixture is counted as household evidence.

Verification: all 91 focused WeatherNext/SDK/learning tests pass; 138 relevant unchanged local source-reader/runtime regressions pass. A synthetic-only batch of 1,920 training and 383 holdout pairs took 0.247s to fit and 0.092s to evaluate, with 36,868 KiB peak RSS under the unchanged shared launcher. This is computational evidence, not site forecast skill. Independent review's three Important findings were reproduced and fixed in one test-backed pass; no production activation occurred.


## Prospective worker and comparison implementation (2026-10-18)

The [shadow runtime](weathernext-shadow-runtime.md) now retains original inference issues, fits separate weekly Google/local candidates from qualified native receipts, advances model pointers atomically and publishes only three bounded shadow Items. The conditional Weather comparison dialog enforces coherent generations and explicit stale/unavailable/model-untrained states. New services/timers and unlinked Item definitions remain uninstalled.

Pre-review verification: 107 pinned Python tests and all 2,584 frontend tests across 170 files pass; the UI build and six unit templates verify. The full frontend run used a single worker thread in the existing shared 1 GiB/64-task budget after the fork pool failed at startup; no host limit was raised. Build output retains the existing large icon-chunk warning. This is implementation evidence, not a real fitted site model, release qualification or deployed UI.

At 15:54Z a source-metadata check discovered a new 08Z WeatherNext run. Exactly one bounded point retry against that changed run still returned Google HTTP 500 (5.058s, 991,384 bytes, 61,068 KiB peak RSS). The failed 07Z computation was not repeated. No snapshot was accepted and no scheduler was enabled.


## Energy and action inventory update (2026-10-18, 16:24Z)

The [bounded read-only energy/action audit](2026-10-18-weathernext-energy-action-evidence.md) found seven measured 15-hour battery nights for prediction dates October 10–16; twenty older requested packets were refused and October 17 remained pending until its window ends at 11:00 AM MDT. Of 336 AC-output hours across October 4–17, 327 meet the existing 99% coverage threshold with a single receiver epoch per hour; five receiver cohorts remain explicit. Existing v1 action-history selection succeeded for fourteen morning origins using the runtime EnvironmentFile credential missed by the earlier audit. No model was fitted, no grants or policies changed, and none of these counts establish WeatherNext skill or complete per-zone action coverage.


## Inactive production-boundary preparation (2026-10-18)

The [prepared provider boundary](weathernext-cutover.md) now maps a validated original Google source into existing nullable raw forecast contracts without loading incumbent state or invoking its seeds. It shares the Google/local learning issue identity, begins in a separate untrained namespace, rejects incumbent corrections/PV inputs, preserves partial-day and DST interval semantics, and returns explicit unavailability on source or archive failure. It is not selected by any production schedule. New-model serving, native Astro daylight, production publication/withdrawal and complete removal remain unfinished.

Verification: 120 pinned WeatherNext tests and 117 existing forecast characterization tests pass. Three Python-produced synthetic payloads, including the maximum horizon and both DST transitions, pass the actual frontend parser. Independent review's SQLite error-contract finding was reproduced and fixed; no real source or forecast-skill qualification follows from these checks.
