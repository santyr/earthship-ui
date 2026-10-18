# WeatherNext migration readiness

Updated 2026-10-18. Execution branch: `feat/weathernext-migration-20261018`; base `0710a08f2a9dabcd7f5dd824dc99511642c6c728`. The operator authorized execution of the existing exclusive-provider plan. This is an implementation/readiness report, not a production cutover approval or skill result.

## Operator-confirmed clean start

On October 18 the operator required fresh weather-related ML with **WeatherNext 3 forecasts plus qualified local measurements**. New weather-model fitting/state cannot reuse Open-Meteo forecasts, features, biases, backfill seeds, error history, pending targets or fitted weather-dependent weights. Local observations, physical configuration and their existing qualification rules remain. Audit downstream weather-dependent components for fresh Google/local fitting; fixed old artifacts are pre-cutover controls only.

At production cutover, remove Open-Meteo completely from OpenHAB and the active Earthship UI project, including AQI integration and obsolete tooling/state references. No post-cutover capture-only period or provider fallback remains. This supersedes the old delayed-retirement sequence, without claiming cutover has occurred. The [reset/removal contract and dependency inventory](openmeteo-retirement.md) defines the acceptance checks.

## Access and acquisition

Google approved access. The private reader authenticates; statistics GCS listing and a real 0.1-degree temperature read succeeded. On October 18 the operator added the exact reader as a principal on project IAM with Owner. At **14:54:00Z**, all five required permissions were visible and the EE project configuration returned HTTP 200 with `REGISTERED_NOT_COMMERCIALLY`. Account setup is no longer the observed blocker. No IAM, API, registration or billing changes were made by the agent.

Live WeatherNext raster extraction remains blocked by Google HTTP 500 internal errors. Collection/image metadata reads succeed, as does a bounded constant-raster control. Single-cell WeatherNext queries fail for both station and gridded collections, for 00Z and 07Z runs, across native `getRegion`, native first-value reduction and a one-cell rectangle. The agent stopped repeated cloud trials; no EE forecast snapshot was accepted, no collector was enabled, and no production values changed. Exact support reproduction and request IDs are in [the EE raster-access diagnosis](2026-10-18-weathernext-ee-raster-diagnosis.md). Owner is broader than the intended Viewer plus Service Usage Consumer roles; reducing that grant remains an operator IAM action and is not a prerequisite for further local implementation.

## Qualified household evidence

A bounded read-only audit at 2026-10-18T13:52:57Z found 81,913 original temperature snapshots retained from 2026-09-20T00:17:03Z to 2026-10-18T13:52:28Z. Raw snapshot count is not a count of qualified training labels. The existing native daily validator proved complete outdoor-temperature coverage for October 15, 16 and 17 (each 86,400 seconds) in the same hardware epoch. Three sampled days are not the full retained training range.

The existing qualified PV reader accepted all three sampled days (coverage 99.9617%, 99.9757%, 99.9747%). The rain reader accepted October 15 and 16 and withheld October 17. Missing rain evidence remains unavailable. No evidence gates or model coefficients changed.

| Source | Existing authoritative reader | Current migration inventory | Consumers |
|---|---|---|---|
| Outdoor temperature | `daily_temperature_runtime.collect_v2`, `weather_temperature_history` | 7 complete current-epoch days, October 11–17, in the 28-day audit | Weather correction, thermal forcing/outcomes |
| Irradiance | `weather_radiation_history`, `household.measured_weather` | 9 complete qualified days in October 3–17; lux-derived proxy, not a physical radiometer | Solar-forcing comparison, fixed-model PV/thermal attribution |
| Rainfall | `weather_rain_history` | 10 accepted days in the 28-day audit; other days withheld | Forecast precipitation outcomes |
| MPPT harvested PV | `pv_day_history` | 18 accepted days in the 28-day audit | Existing PV calibration and outcomes |
| Battery/AC load | `household_battery_source`, `household_ac_load_window` | Original epoch-bound readers identified; range/count pending | Evening SoC, overnight trough, charge/no-full outcomes |
| Indoor temperature | `weather_temperature_history` native role streams | Bedroom/indoor/north_wall current epochs audited; no full 24-hour days in October 3–17; shorter qualified thermal windows retain existing rules | Fixed-artifact thermal attribution |
| Operator actions/shades | `thermal_model.action_history`, `thermal_model.shade_observations` | Existing event readers identified; range/count pending | Known action context; no action effects inferred |
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

Implemented the explicit site/cost policy, restricted Earth Engine HTTP transport, bounded native-cell reader/parser, probe/default-shadow CLI, single collector lock, immutable source-bound archive/index, freshness/horizon checks, and frozen unit/interval normalization. The isolated dependency environment is pinned in `requirements-weathernext.txt`. Fifty-two focused tests pass in that environment; the service/timer templates pass systemd verification. They are not installed or enabled. The CLI currently reports unavailable because WeatherNext raster reads return HTTP 500, with no successful EE snapshot or production publication. Live EE schema/SDK graph behavior and full 360-hour transfer/memory/latency remain unverified until registration succeeds.

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


The radiation/indoor audit at 14:39:05Z accepted 9 complete radiation days from October 3–17 using the existing reviewed radiation-v2 cutover (October 2 at 20:00:09.206165Z). The measured signal is a lux-derived proxy. Three indoor streams had no complete current-epoch 24-hour days in that sample; the existing thermal trainer can use shorter qualified windows, so this audit adds no daily-coverage requirement and makes no claim that thermal training is unavailable. Source receipts/refusals are private in `radiation-indoor-audit.json`. Operator-action range inventory remains pending; no new database access or permissions were introduced.


## Fresh local-learning implementation (2026-10-18)

`weather_learning/features.py`, `training.py` and `evaluation.py` now implement a separate WeatherNext-only temperature pipeline. The feature builder checks original snapshot/issue availability and rederives normalized points from retained Google capsules before using them. Point outcomes reuse the existing native outdoor metadata validator; grids and sensor epochs cannot be pooled. No incumbent learning state is read or imported.

Candidates are raw WeatherNext/untrained, bounded bias, and a seven-feature standardized ridge residual model (native mean/spread, lead, local hour and season). The default correction bound is 6 degrees C, recorded in each artifact. Artifacts freeze source manifests, training clocks, preprocessing, coefficients, code revision and cohort identity. Prepared inference validates/copies the artifact once per batch. A unique target-date count is not a complete qualified-day count.

The evaluator enforces chronological train/embargo/holdout boundaries, retains the predeclared criterion (default 10% lower paired day-weighted MAE), and reports MAE/RMSE/signed bias/pair-tail error by decision horizon and diagnostic regime. Persistence uses only prior qualified local outcomes. Original incumbent forecasts are optional as-issued controls; they cannot enter fitting. Identical pairs are idempotent and conflicting snapshots for one decision/target are refused. Regime annotations alone do not qualify evidence.

This increment is offline implementation, not a fitted site model or a completed Task 5. Reports remain `SHADOW_ONLY` and explicitly list prospective acquisition, complete training/holdout days, shadow inference, qualified regimes and required-variable gates as missing release evidence. Live-source reports, real model fitting, scheduled training/inference, comparison UI and cutover remain unfinished. No synthetic fixture is counted as household evidence.
