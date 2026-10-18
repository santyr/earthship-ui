# Open-Meteo retirement and fresh weather learning

Operator decision: 2026-10-18. This is the binding cutover requirement, not a claim that removal has already been deployed. The operator confirmed **Google forecasts + local measurements**.

## New-model data boundary

WeatherNext 3 is the sole external forecast source. Qualified local outdoor temperature, radiation, rain, indoor temperature and relevant energy outcomes remain training/scoring truth, with their original source/epoch/coverage rules. Local action and shade records remain context. Do not discard the local observation archive.

Start weather-related ML from scratch in a new provider/model namespace. Raw WeatherNext is the initial baseline; display correction/model status as untrained until eligible Google/local pairs support fitting. Missing training evidence cannot trigger legacy seeds or be displayed as a trained model.

| Existing material | Cutover treatment |
|---|---|
| Open-Meteo raw/corrected issues and derived training features | Excluded from all new-model fitting, preprocessing, calibration and online updates |
| Daily temperature Kalman state, legacy/backfill seed constants | Fresh Google/local state; never invoke the old seeder |
| Hourly temperature buckets, targets and learning receipts | Fresh buckets/targets; retain old receipts only in a detached historical archive |
| Old forecast errors, skill averages, scored markers and pending horizon records | New WeatherNext cohort; do not blend scores or consume old pending targets |
| Weather-dependent PV/thermal fitted components | Audit source lineage; fit new components on Google/local pairs before promotion. Unknown lineage does not qualify for carry-forward |
| Old fixed PV/thermal artifacts | Pre-cutover attribution/control experiment only; no implicit promotion as a new Google-trained artifact |
| Panel geometry, electrical specifications, sensor identity and physical constraints | Preserve as configuration, with existing authority and epochs |
| Qualified local measurements/actions and independently learned non-weather behavior | Preserve original identity; reuse only through the existing qualified readers |
| Immutable Open-Meteo research history | Preserve truthful provider labels outside production/new-learning readers; Git history need not be rewritten |

An Open-Meteo evaluation control is allowed before cutover, separately from fitting or tuning the new candidate. All new artifact manifests must identify WeatherNext issues, local outcome receipts, training interval, preprocessing, code revision and parent artifacts. A legacy weather-trained parent cannot be hidden by relabeling the model.

## Removal inventory

Inspected on branch `feat/weathernext-migration-20261018`, foundation revision `51d83c1bee2e081142b1e318e5d384b1ce4b11ef`. These are source dependencies; re-read live OpenHAB and installed unit ownership before applying the cutover patch.

| Surface | Known dependency | Required cutover result |
|---|---|---|
| OpenHAB binding/Things | `openhab/file-config/things/openmeteo.things`: Bridge `openmeteo:openmeteo:local`, forecast `openmeteo:forecast:local:site`, air quality `openmeteo:air-quality:local:aq` | Remove Things, channels/links and installed binding/add-on configuration after stopping writers |
| Temperature Items | `openmeteo-forecast-temperature.items`: `Forecast_Temp`, `Forecast_Daily_High`, `Forecast_Daily_Low` | Rebind/publish from the qualified Google contract; remove provider-specific file |
| Meteorology Items | `openmeteo-forecast-meteorology.items`: `Forecast_Cloudiness`, `Forecast_Radiation`, `Forecast_PrecipProb` | Qualified Google values or explicit unavailable; no fabricated probability |
| Daily Items | `openmeteo-forecast-daily.items`: `Forecast_Daily_PrecipSum`, `Forecast_Daily_PrecipProbMax`, `Forecast_Daily_WeatherCode`, `Forecast_Daily_UVIndex` | Qualified replacement or remove/unavailable; no zero/clear placeholders |
| Air-quality Items | `openmeteo-current-aqi.items`, `openmeteo-forecast-aqi.items`: `Current_US_AQI`, `Forecast_AQI` | Remove Open-Meteo writers/links. No qualified Google AQI replacement exists in the current adapter; remove affected feature or show unavailable |
| UI/alerts | AQI references in `src/screens/{Weather,Home}.svelte` and `src/lib/alerts/consoleAlerts.js`; forecast parser/display consumers | Remove obsolete dependencies and stale forecast/status display; keep concise Google health/model-skill views |
| Production worker | `openhab/scripts/forecast_intel.py`: `open_meteo_url`, `OM_URL`, network fetch and provider-dependent fitting/scoring | Replace source boundary, remove endpoint/caller, initialize fresh weather state |
| Ownership/deployment | `openhab/file-config/ownership.json`, file-config README, installed copies and live managed registry, services/timers and environment references | Remove integration from both file and managed ownership, restart/reload only what is required |
| Temporary shadow controls | `weather_learning/incumbent.py`, shadow CLI/service `--include-incumbent`, comparison UI incumbent column | Remove the capture path and UI dependency at cutover; retained controls stay detached from new learning |
| Project tools/tests | `scripts/*openmeteo*`, `scripts/HexOpenMeteoThingsParse.java`, dependent migration/qualification probes and `tests/openhab/openmeteo-*` | Remove obsolete integration/tooling and replace relevant consumer-contract coverage; check imports and CI references |
| State/artifacts | Existing forecast-intel predictions, daily/hourly correction state, error history and weather-trained downstream components | Detached historical preimage plus fresh WeatherNext namespace; no executable old-state import path |

The existing adapter has no qualified precipitation-probability, WMO-code, UV or AQI mapping. Their absence cannot keep Open-Meteo installed after cutover. A separately qualified Google source is possible only with its own documented access/contract; no new subscription or service is implied by this decision. Local current-weather sensors remain available.

## Live inventory update (2026-10-18)

The [read-only removal audit](2026-10-18-openmeteo-retirement-audit.md) and [machine-readable inventory](2026-10-18-openmeteo-retirement-inventory.json) supplement the earlier source table with the actual custom binding JAR, three live Things/twelve links, the root-only AQI evidence producer/receipt, loaded forecast consumers and current source overlays. Catalog removal alone would miss the custom JAR. This update prepares removal; no integration or learned state has been removed.

## Release order and acceptance

1. Finish real WeatherNext retrieval and required consumer qualification. Prepare and review the removal/reset patch while the incumbent still serves production.
2. Record the pre-cutover revision and private state preimages, without adding a recovery-test project.
3. In the same attended cutover, stop Open-Meteo fetch/learning writers; deploy the Google provider and fresh learning namespace; remove Open-Meteo binding, Things, channels/links, obsolete Items, code, jobs and state references.
4. Verify natural publication, model lineage, UI and required consumers. Search the deployed project, service configuration and live registry for remaining integration references; confirm no outbound Open-Meteo requests.
5. Observe Google-only operation. WeatherNext failure becomes explicit stale/degraded/unavailable status. Local observations continue; no capture-only Open-Meteo job or fallback is retained.

Historical documentation and Git records may name the retired provider. They are not an active integration. A deliberate manual rollback uses a pinned earlier revision; the running deployment must not retain a selectable Open-Meteo provider.

Current status: removal/reset is planned, not deployed. See [readiness](weathernext-readiness.md) and the [execution plan](../superpowers/plans/2026-10-05-weathernext-exclusive-forecast.md).


### Additional pre-cutover attribution dependency — October 18

`weather_learning.energy_shadow.compare_fixed_energy` and `test_weathernext_fixed_energy.py` are temporary incumbent-control analysis. They replay original household plan/energy/profiled receipts under their original source closure to isolate Google weather forcing. Before complete retirement, archive/detach this adapter and its incumbent replay tests outside the active project; do not leave a dormant comparison collector or provider fallback. The rain/Google-only functions in the same module have separate ownership and need not be removed with this adapter. Retain original private report/provider/source identities as historical evidence. This prepares removal only; it does not authorize cutover or claim the dependency inventory is complete.
