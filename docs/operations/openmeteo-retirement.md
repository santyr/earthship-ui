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


### Prepared source retirement — air-quality definitions and Python tools

The prepared OpenHAB configuration now removes both AQI Item files, their two channel links and the air-quality Thing. Exactly five ownership entries are removed; the remaining definitions and ownership records are unchanged. The existing forecast bridge/Thing remain only until the final weather-provider removal; native grammar validation accepts the two remaining declarations and rejects malformed syntax. The Astro handoff no longer treats retired AQI binding refreshes as an allowed metadata exception.

The four dedicated Python AQI migration/qualification drivers and their candidate-only tests are removed. Shared metadata, file-stream and local HTTP/JDBC adapters now live in `openhab_qualification_fixture.py` and `openhab_qualification_jdbc.py`; ten callers use those neutral modules. All eight extracted function bodies match the `9b1423e` preimages byte-for-byte, preserving the existing APIs without copying AQI candidate defaults or running recovery work. The remaining legacy forecast qualifier keeps its own temporary binding path until that tool is retired; the new generic module has no external-provider binding selection.

Fresh verification includes eight new adapter behavior tests, the combined affected caller/Astro contract suite (**310 tests in 1.06 seconds**), full frontend/file-ownership coverage (**2,554 tests in 168 files, 43.59 seconds**), the actual installed Thing grammar, and import-only checks for three callers without dedicated unit modules. No container, recovery rehearsal, provider transfer, live Item/Thing/JSONDB change, forecast publication, service restart or model change was performed. Original operational evidence remains private/Git-backed. Live AQI configuration and the root-only AQI evidence producer/receipt consumers must still be removed during the coordinated cutover.


### Prepared source retirement — forecast definitions and remaining weather tools

The prepared release replaces the three linked temperature/meteorology/daily
Item files with `items/forecast-weather.items`: six unlinked state targets using
explicit °F, %, W/m² and mm units. Their original names, physical Item types,
labels, tags and `gForecast` membership are preserved. The six manifest entries
are `migration: prepared`; they identify the tested publication function, not
an installed or qualified Google writer. Two Things, ten channel links and four
unsupported probability/weather-code/forecast-UV Items leave source ownership.
All 162 unrelated ownership records remain identical. No physical station
sensor, Group definition, JDBC selector or historical row is changed.

Actual read-only registry inspection confirms `gForecast` is already file-owned
(`editable:false`), consistent with its completed September 24 cutover. The
obsolete cold/hot group handoff tools and their two dedicated test modules are
removed. They depended on the retired linked native-series contract and custom
binding; retaining them would preserve an executable old-provider integration.
The nine remaining weather Item migration/provider/JDBC drivers, nine dedicated
test modules and three orphaned Java native-series probes are likewise removed.
Source preimages remain at `3674aff`; no recovery rehearsal was performed.

The unrelated Bitcoin price qualifier uses the neutral
`openhab_linked_item_qualification.py` engine. Its existing definition/channel,
provider, label and presentation checks remain; an unconfigured engine refuses
before reading the host. This extraction supplies no weather defaults or custom
binding. The Sun handoff's old forecast-Thing refresh exception is removed;
definition comparison now refuses any unexpected drift, retaining its existing
API and unrelated invariants.

The production publisher now accepts physically equivalent explicit cloud-cover
readback (`25 %` equals `0.25 one` or `0.25 1`), while rejecting bare ambiguous
fractions and non-equivalent quantities. A regression failed before that fix.
Native OpenHAB **5.2.3** grammar accepts all six new Item identities and rejects
malformed syntax. The complete WeatherNext package passes **182 tests in
6.395 seconds**; the focused Bitcoin/linked-Item/Sun suite passes **32 tests in
0.43 seconds**. This prepares source only: actual provider installation,
exclusive writer admission, fresh models and qualified natural serving remain
unfinished, and the live binding/Things/links/old Items remain in place until
coordinated cutover.


The broader affected Bitcoin/Sun/neutral-helper suite also passed **146 tests
in 0.75 seconds**. Full frontend/file-config consumer coverage passed **2,554
tests in 168 files, 43.64 seconds**. A search across scripts, backend scripts,
tests, CI and deployment found no remaining executable caller of the removed
drivers/probes or their definition-file names. The sole retired Thing UID in
tools/tests is an intentional negative drift fixture. Four extracted helper
function bodies match their preimages after the neutral alias substitution;
the main body is unchanged after its new explicit-configuration admission.
No browser rerun was needed for this increment: rendered UI code was unchanged.


### Prepared source retirement — native weather SQL acquisition

The shared native live-input collector now requires an explicit Google reader.
It rejects obsolete forecast-database settings before private file reads and no
longer loads or stores a forecast DSN. Missing Google data is unavailable; it
cannot select the old database path. Before collecting local observations or
action knowledge, it independently reconstructs the original Google capsule
and verifies the exact requested issue, knowledge cutoff and 24-hour horizon.
A valid capsule for a different request is refused as well as an invalid or
legacy-provider capsule.

All four archived weather SQL acquisition functions are removed from
`thermal_model/forecast_history.py`; there is no remaining production caller
or query of `energy_analytics.forecast_snapshots` in backend Python source.
Their three dedicated SQL test cases and unused fake connection helper leave
with that API. Native source/temperature/journal barrier tests now use actual
synthetic Google capsules rather than replacing the old SQL function. Local
measurement queries, causal mass initialization, sensor epochs, action-journal
knowledge clocks, original-source retention and fixed telemetry authority stay
unchanged.

Seven new regressions failed before implementation and pass afterward. Broader
source-bound verification passed **123 tests in 26.63 seconds**; the full
WeatherNext package passed **182 tests in 5.943 seconds**. The native suite ran
from an immutable Git export with the pinned Solar-PV test dependency. An
initial direct worktree run had 44 passing tests and three refusals because
runtime source files were group-writable; using the isolated immutable export
resolved the verification environment without changing worktree/live permissions
or weakening source-integrity checks.

This is acquisition removal, not final receipt/configuration retirement. Old
in-memory per-metric receipt selection/verification, its compatibility forcing
branches and old configuration loaders/callers remain explicit unfinished
work. They cannot use the removed SQL API, and old source-less live-backend
construction now refuses. Remove those remaining paths and the legacy forecast
worker before freezing the final source closure and fitting release models.
Existing installed sources/services, model artifacts, source history, database
permissions and production data remain unchanged.


### Prepared source retirement — shared weather receipt replay

The prepared source removes the three in-memory per-metric forecast selectors
and the old receipt reconstruction path. `thermal_model/forecast_history.py`
now retains only its unchanged aware-clock/hourly-window helpers and original
Google capsule verification. Installed-shade, operational-origin and split-airflow
replay require those Google originals; condition codes remain unknown rather
than being invented. The existing Google availability/freshness policy applies,
including the native left bracket, instead of the retired six-hour source rule.

Standalone installed-shade and airflow runtime bindings now include all nine
local files needed by Google receipt verification. The full native runtime
already includes those files; this does not change its physical equations or
promote an old model. Existing release artifacts must be fitted/bound after the
final source closure is complete.

The well-formed retired receipt in `tests/fixtures/retired-weather-receipts-v2.json`
is synthetic and consumed only by refusal tests. Its old schema/source/digests
are preserved. Model-test weather factories generate fresh original-shaped
Google responses while preserving their intended temperature, radiation and
wind forcing. Household weather fixtures use the existing native v4 Google
context rather than weakening its version guard. Downgraded v1/v2/v3 Google
contexts refuse. The two retired selector/receipt test modules leave with their
API; CI names the new Google refusal/acquisition suites instead.

Eight new regressions failed before the source change. The focused shared
receipt/operational suite now passes 19 tests, and the WeatherNext package last
passed 182 tests. Broader native/household verification used an immutable export; the exact
completed coverage and local skip are recorded below. Both operational CLIs
correctly refuse the synthetic test model's runtime in a cold process, while
in-process tests use the explicit mathematical fixture hook. Successful cold
replay of an actual release candidate remains separate required evidence.

This remains source preparation. Legacy configuration loaders/factories, old
household context entrypoints and the legacy forecast worker still require
retirement, followed by qualified production publication, fresh models and
coordinated cutover. Installed model/state/service configuration is unchanged.


Native household outcome integration exposed an additional consumer gap: the
existing delivered-outcome factory accepted only the older provisional capture.
`prepare_native_outcome_origin` now prepares a separately typed v2 delivered
origin using explicit runtime/model/capture pins, the existing native projection
preparer, both actual persisted publication receipts and the complete frozen
Google weather/model/geometry verifier. Its five envelope fields and 3 MiB bound
are unchanged; existing outcome arithmetic is unchanged. This adds no writer,
schedule, fit, release decision or actuator authority.

Native and older mathematical outcome envelopes must both reconstruct original
Google weather. A regression rehashed the changed wind row, forecast, capture,
sensor snapshot, prepared model, both publication states and outcome envelope;
the older frozen outcome previously accepted it. That case failed before the
verification fix and now refuses. Native frozen restoration also passes with
file, network and database reads disabled. Downgrading a native delivered origin
to the older model contract refuses.

The focused delivered-outcome/old-score/enclosing-context/sidecar suite passes
**35 tests in 24.46 seconds**. Verification covered all 125 affected modules
in an immutable Git export with the pinned Solar_PV dependency and single-thread
BLAS, using shared aggregate resource admission. The first shard passed **964
tests in 515.69 seconds**. The second reached **894 passes and one skip** before
a positive airflow fixture failed because it edited selected values without
updating the original Google response. The complete corrected airflow module
then passed **61 tests in 4.23 seconds**. These counts overlap at that module;
they are not a single-run aggregate. Only test fixtures changed after the shard
runs: they now generate coherent original Google values and use native ISO
clocks. Source checks and independent numerical equations remain intact.

The existing skipped multiweek synthetic calibration replay is enabled by its
`CI=true` marker in hosted CI. The full WeatherNext package separately passed
**182 tests in 6.302 seconds**. This proves affected source behavior, not full
repository CI, an actual release candidate, predictive qualification or cutover.
