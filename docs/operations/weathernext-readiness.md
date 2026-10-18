# WeatherNext migration readiness

Updated 2026-10-18. Execution branch: `feat/weathernext-migration-20261018`; base `0710a08f2a9dabcd7f5dd824dc99511642c6c728`. The operator authorized execution of the existing exclusive-provider plan. This is an implementation/readiness report, not a production cutover approval or skill result.

## Access and acquisition

Google approved access. The reader is installed privately, OAuth authentication works, statistics GCS listing and a real 0.1-degree temperature read succeeded. See [connection evidence and approved Earth Engine design](2026-10-18-weathernext-access.md). Earth Engine initially returned HTTP 403 `SERVICE_DISABLED`. The operator enabled the API; the next configuration GET at 14:15:13Z confirms the API is reachable but reports the project is not registered. The operator reports a generic console registration error. Noncommercial registration must succeed before a live point query. The agent made no API, IAM, billing or production changes; API activation was performed by the operator.

## Qualified household evidence

A bounded read-only audit at 2026-10-18T13:52:57Z found 81,913 original temperature snapshots retained from 2026-09-20T00:17:03Z to 2026-10-18T13:52:28Z. Raw snapshot count is not a count of qualified training labels. The existing native daily validator proved complete outdoor-temperature coverage for October 15, 16 and 17 (each 86,400 seconds) in the same hardware epoch. Three sampled days are not the full retained training range.

The existing qualified PV reader accepted all three sampled days (coverage 99.9617%, 99.9757%, 99.9747%). The rain reader accepted October 15 and 16 and withheld October 17. Missing rain evidence remains unavailable. No evidence gates or model coefficients changed.

| Source | Existing authoritative reader | Current migration inventory | Consumers |
|---|---|---|---|
| Outdoor temperature | `daily_temperature_runtime.collect_v2`, `weather_temperature_history` | 3 sampled fully covered days, October 15–17; broader qualified-day count pending | Weather correction, thermal forcing/outcomes |
| Irradiance | `weather_radiation_history`, `household.measured_weather` | Reader identified; complete-day range/count not yet audited | Solar-forcing comparison, fixed-model PV/thermal attribution |
| Rainfall | `weather_rain_history` | 2 accepted sampled days, October 15–16; October 17 unavailable | Forecast precipitation outcomes |
| MPPT harvested PV | `pv_day_history` | 3 accepted sampled days, October 15–17; broader range/count pending | Existing PV calibration and outcomes |
| Battery/AC load | `household_battery_source`, `household_ac_load_window` | Original epoch-bound readers identified; range/count pending | Evening SoC, overnight trough, charge/no-full outcomes |
| Indoor temperature | `weather_temperature_history` native role streams | Existing qualified reader identified; role/epoch inventory pending | Fixed-artifact thermal attribution |
| Operator actions/shades | `thermal_model.action_history`, `thermal_model.shade_observations` | Existing event readers identified; range/count pending | Known action context; no action effects inferred |
| Original incumbent issues | Existing forecast/thermal original captures | `forecast-intel/state.json` exists; original-issue archive inventory pending; current state is not reconstructed history | Paired chronological comparison |
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
| Current AQI, if separately supplied by Open-Meteo | WeatherNext has no qualified AQI replacement in this mapping | Current-observation/AQI scope must be inventoried separately before deleting any shared Thing |

## Release gates and current limitations

The approved plan calls for 30 consecutive prospective acquisition days, 60 qualified temperature training days plus an untouched 30-day holdout when available, and 14 days of normal local-model shadow inference. None of that is established by an authentication test or historical download. Preserve the incumbent until required variable/horizon gates pass; later retirement has no silent fallback.

Production forecasts, correction state, thermal/PV coefficients, notification policy and actuator authority are unchanged. Recovery work remains deferred per operator instruction.

## Implementation increment (2026-10-18)

Implemented the explicit site/cost policy, restricted Earth Engine HTTP transport, bounded native-cell reader/parser, probe/default-shadow CLI, single collector lock, immutable source-bound archive/index, freshness/horizon checks, and frozen unit/interval normalization. The isolated dependency environment is pinned in `requirements-weathernext.txt`. Fifty-two focused tests pass in that environment; the service/timer templates pass systemd verification. They are not installed or enabled. The CLI currently refuses service on the unregistered project, with no source/archive or production publication. Live EE schema/SDK graph behavior and full 360-hour transfer/memory/latency remain unverified until registration succeeds.

The scheduler template uses the existing shared job-admission launcher, with no resource-policy changes. It performs shadow collection only and has no OpenHAB publisher, actuator or notification function. The archive refuses after 16 GiB / 10,000 objects or inadequate disk headroom rather than silently deleting retained evidence.

Latest raw-storage audit (14:12Z; raw snapshots are not qualified windows):

| Item | First retained UTC | Last retained UTC | Raw snapshots |
|---|---|---|---:|
| Radiation evidence | 2026-10-02 15:30:39 | 2026-10-18 14:11:58 | 44,880 |
| Rain evidence | 2026-09-29 04:12:48 | 2026-10-18 14:11:58 | 55,023 |
| MPPT day evidence | 2026-09-28 14:06:49 | 2026-10-18 14:11:47 | 40,080 |
| Battery SoC evidence | 2026-09-10 21:51:32 | 2026-10-18 14:11:35 | 59,475 |
| Inverter AC evidence | 2026-09-23 20:55:12 | 2026-10-18 14:12:03 | 411,943 |

The incumbent `forecast-intel/weather-inputs` directory contains 129 files totaling 91,004 bytes. Their issue/availability eligibility still needs validation; file count is not a scored sample count.

The completed 28-day audit (September 20–October 17, assessed October 18 at 14:21Z) accepted **7 complete current-epoch outdoor-temperature days** (October 11–17), **18 PV days**, and **10 rain days** using the existing production-qualified readers. Other sampled days were withheld; the audit does not merge earlier receipt formats into the current hardware epoch. Per-variable accepted date lists and refusal reasons are retained privately in `source-audit-28days.json`.

Independent review found and fixed a native-projection argument mismatch, a scheduler/collection-admission profile mismatch, and the absence of an interrupting total response deadline. Each was reproduced before its fix. The scheduler now uses the existing collection profile (256 MiB preferred/minimum, 24 tasks, 90 seconds); acquisition has a 75-second total interrupting budget plus the unchanged outer host safeguards. A separate CI job runs the pinned SDK tests without cloud credentials.

Deferred minor limitations: archive validation binds point digests to retained originals but does not independently rederive every normalized point from those originals; the current reader/parser owns that validation. `AccessPolicy.max_attempts` and `max_pixels` are reserved configuration bounds, not independent active transport controls; actual retry count is zero and acquisition uses a fixed single-point query with strict response/target bounds. Neither limitation authorizes production cutover.
