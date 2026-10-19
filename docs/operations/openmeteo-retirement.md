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

`weather_learning/thermal_shadow.py` and `test_weathernext_fixed_thermal.py` likewise retain a temporary incumbent thermal control and must be archived/detached from the active project at retirement. Their fixed original-model coefficients are attribution controls only; they are not a source for fresh Google/local production model weights. See the [thermal comparison evidence](2026-10-18-weathernext-fixed-thermal-attribution.md).

The native Google backend now avoids the incumbent forecast credential entirely. Retirement must still remove the default legacy SQL branch from shared collection/receipt/forcing helpers, update native live/serving configuration, and rebind the final immutable source closure before real release fitting. Temporary legacy compatibility tests and incumbent-control adapters remain pre-cutover only; the new Google capsule/backend and private v4 context are retained. See [native source integration](2026-10-18-weathernext-native-inputs.md).


The [preserved irradiance-family integration](2026-10-18-weathernext-irradiance-family.md) keeps the actual running thermal equations and makes them mandatory for Google production profiles. This does not exempt historical compatibility paths from retirement: detach incumbent pending forecasts, historical scoring selections, the old weather SQL/receipt branch and temporary comparison adapters from the active Google-only release. Preserve local measurements/physical context and fit new artifacts after that final source closure is frozen.


### Prepared source retirement — attribution adapters

The migration branch now removes `weather_learning/thermal_shadow.py`, the incumbent `compare_fixed_energy` function and their two dedicated replay test modules. Their attribution experiments are complete and retained reports keep their original provider, model and source identities. Source/test preimages are available at revision `05c5d61`; no historical evidence is relabeled or deleted. The remaining `energy_shadow` module contains Google/local rain qualification only. A source/import search found no remaining executable callers of the detached attribution APIs.

Google collection, inference and learning now obtain regional configuration and state-only publication through `weather_learning/openhab.py`, using the existing private hex identity. They no longer import the legacy forecast worker for these utilities. End-to-end local HTTP tests exercise collector startup and three-Item shadow publication with the old worker made unimportable; an empty Google archive publishes unavailable rather than substituting a site or forecast.

These are prepared source changes in the isolated migration branch. The installed immutable shadow release and incumbent services have not changed. The legacy forecast worker and SQL receipt readers, provider-specific OpenHAB definitions/tooling and attended deployment still require removal. Do not interpret this increment as complete retirement or production cutover.


The prepared shadow worker and UI now accept only `earthship-weather-provider-shadow/v2`. Incumbent capture, its CLI switch/service argument, source metadata and temperature column are removed. The dialog shows WeatherNext raw values, the separate local candidate, source health and explicit unqualified status. It retains its accessible dialog and tile positioning. Mixed/old publications are unavailable rather than silently adapted.

Retained new issues use `earthship-weather-shadow-issue/v2`, without any incumbent payload. Both CLI inference and fitting select the fresh `google-local-v2` directory under the configured shadow state root; neither loads the old comparison cohort's candidate pointer or issues. Original Google acquisition objects remain reusable through the unchanged archive provenance checks. The old cohort stays private and unchanged for detached evidence. The synthetic frontend fixture was replaced with a v2 fixture; real retained records are not rewritten. Deploy producer, service arguments and frontend together at cutover; the installed immutable release continues publishing v1 until that attended change.


### Prepared source retirement — evaluation and Thing tooling

The new evaluator emits `earthship-weathernext-temperature-evaluation/v2` and accepts only original Google/local pairs plus qualified local persistence observations. The incumbent forecast class, records argument, source manifest, age setting and comparison scorer are removed. Raw Google and the local candidate use identical pairs and equal weight per local target date. Relative MAE improvement is explicitly a local-adaptation diagnostic, unavailable for an empty holdout or zero raw error; worse adaptation reports negative gain. Reports remain `SHADOW_ONLY` and retain their missing-release-evidence list.

The old incumbent promotion threshold is deliberately not relabeled as a raw-Google threshold. Existing promotion requirements and untouched historical v1 reports retain their original meaning; the new diagnostic does not satisfy incumbent non-inferiority or grant a release. Chronological split, embargo, model/holdout clocks, deduplication, horizon/regime reporting and original persistence receipt/availability binding remain enforced.

The Bitcoin Thing tool no longer imports the Open-Meteo migrator for its private-file utility. The unchanged exclusive/no-follow, mode-600, write/fsync behavior and local JSONDB path constants now live in `scripts/openhab_private_files.py`; the generic grammar parser is `scripts/HexThingsParse.java`. With the unrelated caller detached, the prepared branch removes the Open-Meteo Thing migrator, provider rehearsal, typed-configuration comparator/dedicated test and syntax launcher. Preimages remain at `efdf001`. No recovery rehearsal, provider transfer, service restart or live registry mutation was run. Other provider-specific Item/JDBC tools still require dependency cleanup before final removal.


### Prepared source retirement — modeled AQI display and alerts

The prepared frontend removes the modeled AQI Weather tile, Home chip, classification helpers and global alert source/priority. Old `Current_US_AQI`/`Forecast_AQI` states cannot recreate them. The remaining current-weather tile spans the Weather grid's first row; hourly/daily/other observation rows and the model dialog retain their placement. Physical station observations, including measured current UV, are preserved. Optional forecast condition/probability fields still render unknown when Google supplies no qualified value; no zero, clear-weather or benign-AQI replacement is synthesized.

The standalone JavaScript AQI migration tool and its dedicated migration/source-consumption tests are removed; their preimages remain at `48a42b3`. Retained header dialog and polite/assertive announcement tests now use a fresh, valid thermal-warning receipt. Provider-only classification tests leave with the removed feature, while new behavior tests supply old high/hazardous AQI states and verify no display or unsupported warning.

This changes the prepared release only. The live root's AQI evidence rule, receipt consumer and installed binding/Things/Items remain in the attended removal inventory. The Python Item/JDBC qualification tools still borrow provider-specific helpers and need detachment before their definitions/tooling can be removed together. Those dependencies are unfinished; the absence of AQI strings in the prepared frontend does not prove complete Open-Meteo retirement.


Frontend verification: **2,556 tests in 170 files passed in 43.34 seconds**; the production build passed in 1.44 seconds. Eight selected tablet/laptop checks passed across focused runs: four Weather/model-dialog checks, two Home long/unavailable-state checks and two Home settled-layout/chart checks. The existing Home fixture expected a computed season without supplying native season Items/evidence; the unchanged `48a42b3` baseline reproduced that failure. Its expectation now correctly requires `Season unavailable`; application season behavior was not changed.

The broader Home browser workload also exposed an insufficient development scope. With 2 GiB RAM and 96 tasks, the measured scope peaked at 1,108,140,032 bytes, recorded four task-limit refusals and no OOM events. Within the existing launcher maximum, the final single-worker run requested 1 GiB minimum / 2 GiB preferred and 128 tasks: both settled checks passed in 5.9 seconds, peaking at 1,084,125,184 bytes with zero OOM or task-limit events. Use that development allocation for the full Home chart checks. Existing aggregate RAM admission, the 3 GiB host reserve, no-swap setting, deadlines and production safeguards remain unchanged; no global launcher limit was raised.
