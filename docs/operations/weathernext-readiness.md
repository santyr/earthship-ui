# WeatherNext migration readiness

Updated 2026-10-19. Execution branch: `feat/weathernext-migration-20261018`; base `0710a08f2a9dabcd7f5dd824dc99511642c6c728`. The operator authorized execution of the existing exclusive-provider plan. This is an implementation/readiness report, not a production cutover approval or skill result.

## Operator-confirmed clean start

On October 18 the operator required fresh weather-related ML with **WeatherNext 3 forecasts plus qualified local measurements**. New weather-model fitting/state cannot reuse Open-Meteo forecasts, features, biases, backfill seeds, error history, pending targets or fitted weather-dependent weights. Local observations, physical configuration and their existing qualification rules remain. Audit downstream weather-dependent components for fresh Google/local fitting; fixed old artifacts are pre-cutover controls only.

At production cutover, remove Open-Meteo completely from OpenHAB and the active Earthship UI project, including AQI integration and obsolete tooling/state references. No post-cutover capture-only period or provider fallback remains. This supersedes the old delayed-retirement sequence, without claiming cutover has occurred. The [reset/removal contract and dependency inventory](openmeteo-retirement.md) defines the acceptance checks.

## Access and acquisition

Google approved access. The private reader authenticates; statistics GCS listing and a real 0.1-degree temperature read succeeded. On October 18 the operator added the exact reader as a principal on project IAM with Owner. At **14:54:00Z**, all five required permissions were visible and the EE project configuration returned HTTP 200 with `REGISTERED_NOT_COMMERCIALLY`. Account setup is no longer the observed blocker. No IAM, API, registration or billing changes were made by the agent.

At **18:20:30Z**, the corrected native collector successfully archived a complete **360-hour / 10-band / 3,600-point** WeatherNext issue in **10.11 seconds**, receiving **1,255,580 bytes** with **72,128 KiB peak RSS**. The access blocker was a missing read-only Cloud Storage OAuth scope in the custom credential loader, followed by a parser assumption that source image time always meant forecast valid time. Both are corrected with regression tests; the native cell, source/run identity, original timestamps and acquisition/resource/cost bounds are preserved. No new IAM grant or credential was needed. The [live API compatibility report](2026-10-18-weathernext-api-compatibility.md) records the controlled comparison, documentation review, exact snapshot identity and limitations. The [earlier raster diagnosis](2026-10-18-weathernext-ee-raster-diagnosis.md) is historical and superseded. The [backend activation](2026-10-18-weathernext-shadow-activation.md) subsequently verified a pinned installed collector run and enabled hourly collection/private issue recording plus separate weekly shadow fitting. The first natural collector trigger also succeeded at 18:35Z; the later 18:40Z shadow trigger recorded locally. The [comparison activation](2026-10-18-weathernext-comparison-activation.md) subsequently enabled three unlinked shadow Items and the live read-only comparison UI. A fresh Google/local candidate fitted from one pair remains SHADOW_ONLY with no validation. The first natural published shadow trigger is verified at 19:40:31Z against the retained issue and all three Item states. Natural weekly training, prospective qualification intervals and production cutover remain unverified.

The [precipitation capture increment](2026-10-18-weathernext-rain-candidates.md) adds the two previously omitted supported rain heads for separate qualification. A real 360-hour capture retained all three products alongside existing fields (4,320 points / 1,272,037 bytes / 9.729 seconds); unit/interval/source rederivation and all 128 pinned tests pass. The tested f5775f8 increment is installed in the private backend; an installed 4,320-point collection and shadow issue from that exact snapshot/source both pass. No production precipitation product is selected by this increment.

## Current installed shadow state — October 19

The [v2 runtime qualification](weathernext-shadow-runtime.md) supersedes the
historical v1 candidate status above. Shadow inference and the existing weekly
training service now use immutable revision `59c0b81`; the collector remains
pinned separately at `8be69ea`. The live producer/UI use a fresh Google-only
cohort with **zero training pairs**. All three Items matched the installed
manual READY generation and source snapshot, and real tablet/laptop browser
checks passed without equipment requests. The old v1 one-pair candidate remains
separate and unused. The first natural v2 trigger at 09:40:25 UTC is now verified against its retained
issue, all three Item states and preceding collector snapshot. No new fitting,
qualified skill, completed prospective day or production cutover is claimed. Main production still uses the incumbent pending
the release gates below.

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
| Prospective WeatherNext issues | Private content-addressed collector archive; fresh v2 issue namespace | Hourly acquisition is installed and naturally verified; v2 producer/UI manually qualified October 19, fresh/untrained with no v1 model imported | Future Google/local learning and qualification; required intervals remain incomplete |

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

Implemented the explicit site/cost policy, restricted Earth Engine HTTP transport, bounded native-cell reader/parser, probe/default-shadow CLI, single collector lock, immutable source-bound archive/index, freshness/horizon checks, and frozen unit/interval normalization. The isolated dependency environment is pinned in `requirements-weathernext.txt`. Fifty-two focused tests pass in that environment; the service/timer templates pass systemd verification. The reviewed backend units are installed/enabled; the later comparison activation also enabled the three shadow Items and their read-only UI. See the dated activation records. The corrected CLI has now completed a real native 360-hour snapshot; see the current access section and live API compatibility report. Production publication remains unselected, and no prospective reliability or forecast-skill interval is implied.

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

This increment is offline implementation, not a fitted site model or a completed Task 5. Reports remain `SHADOW_ONLY` and explicitly list prospective acquisition, complete training/holdout days, shadow inference, qualified regimes and required-variable gates as missing release evidence. This initial offline increment was subsequently extended by real collection, installed training/inference and the comparison UI; its first one-pair model remains unqualified. Live skill/holdout reports and production cutover remain unfinished. No synthetic fixture is counted as household evidence.

Verification: all 91 focused WeatherNext/SDK/learning tests pass; 138 relevant unchanged local source-reader/runtime regressions pass. A synthetic-only batch of 1,920 training and 383 holdout pairs took 0.247s to fit and 0.092s to evaluate, with 36,868 KiB peak RSS under the unchanged shared launcher. This is computational evidence, not site forecast skill. Independent review's three Important findings were reproduced and fixed in one test-backed pass; no production activation occurred.


## Prospective worker and comparison implementation (2026-10-18)

The [shadow runtime](weathernext-shadow-runtime.md) now retains original inference issues, fits separate weekly Google/local candidates from qualified native receipts, advances model pointers atomically and publishes only three bounded shadow Items. The conditional Weather comparison dialog enforces coherent generations and explicit stale/unavailable/model-untrained states. The services/timers, three unlinked file-owned Items and live comparison UI are now installed; explicit publication and the first natural published trigger at 19:40:31Z both pass.

Pre-review verification: 107 pinned Python tests and all 2,584 frontend tests across 170 files pass; the UI build and six unit templates verify. The full frontend run used a single worker thread in the existing shared 1 GiB/64-task budget after the fork pool failed at startup; no host limit was raised. Build output retains the existing large icon-chunk warning. This is implementation evidence, not a real fitted site model, release qualification or deployed UI.

At 15:54Z a source-metadata check discovered a new 08Z WeatherNext run. Exactly one bounded point retry against that changed run still returned Google HTTP 500 (5.058s, 991,384 bytes, 61,068 KiB peak RSS). The failed 07Z computation was not repeated. No snapshot was accepted and no scheduler was enabled.


## Energy and action inventory update (2026-10-18, 16:24Z)

The [bounded read-only energy/action audit](2026-10-18-weathernext-energy-action-evidence.md) found seven measured 15-hour battery nights for prediction dates October 10–16; twenty older requested packets were refused and October 17 remained pending until its window ends at 11:00 AM MDT. Of 336 AC-output hours across October 4–17, 327 meet the existing 99% coverage threshold with a single receiver epoch per hour; five receiver cohorts remain explicit. Existing v1 action-history selection succeeded for fourteen morning origins using the runtime EnvironmentFile credential missed by the earlier audit. No model was fitted, no grants or policies changed, and none of these counts establish WeatherNext skill or complete per-zone action coverage.


## Inactive production-boundary preparation (2026-10-18)

The [prepared provider boundary](weathernext-cutover.md) now maps a validated original Google source into existing nullable raw forecast contracts without loading incumbent state or invoking its seeds. It shares the Google/local learning issue identity, begins in a separate untrained namespace, rejects incumbent corrections/PV inputs, preserves partial-day and DST interval semantics, and returns explicit unavailability on source or archive failure. It is not selected by any production schedule. New-model serving, native Astro daylight, production publication/withdrawal and complete removal remain unfinished.

Verification: 120 pinned WeatherNext tests and 117 existing forecast characterization tests pass. Three Python-produced synthetic payloads, including the maximum horizon and both DST transitions, pass the actual frontend parser. Independent review's SQLite error-contract finding was reproduced and fixed; no real source or forecast-skill qualification follows from these checks.


## Rain comparison increment — October 18

The [source-bound rain comparison](2026-10-18-weathernext-rain-comparison.md) now retains/replays original native counter receipts and compares all three Google products on identical complete days. The latest pre-day original decision is selected before outcome/missingness checks; sensor epochs and grids remain separate. A read-only real integration audit revalidated six original Google decisions and two earlier qualified local rain days. They have no prospective overlap: October 19 remains withheld pending its actual outcome, zero paired days, no product selection. Full WeatherNext tests: 139 passed; existing forecast/native rain regressions: 148 passed. Solar/PV/storage/thermal attribution and actual variable qualification remain unfinished.


## Solar comparison increment — October 18

The [source-bound solar comparison](2026-10-18-weathernext-solar-comparison.md) now separates Google GHI/direct hourly exposure from the qualified local lux proxy, magnitude errors from timing/shape, and receiver/grid cohorts. A real 19–20Z prospective hour was paired from the latest original decision completed before its start and 126 native receipts; timing remains unavailable for a single bin. Two prior full local days replay as source checks, while the restarted/gapped October 17 day remains partial. An actual floating coverage false refusal was corrected with integer microseconds; a one-microsecond real gap still refuses. Full WeatherNext tests: 152 passed; native/thermal-radiation regressions: 164 passed. No calibrated-radiometer or direct-component ground truth is claimed, and no new hardware gate is added. The installed backend is unchanged; full variable/downstream qualification and cutover remain unfinished.


## Fixed energy attribution increment — October 18

The [fixed-model comparison](2026-10-18-weathernext-fixed-energy-attribution.md) replays original physical array/storage controls under their actual immutable runtime and swaps only origin-eligible Google GHI/temperature/wind. A real 20:15:15Z control produced constant-load and unchanged learned-load alternatives by 20:27:51Z in 1.674 seconds / 114,268 KiB RSS. Battery/load/geometry/assumption pins remain identical. Ending-hour 1 is excluded because it had started before completion; hours 2–24 were still future windows. There are no outcome scores yet. Tests: 39 fixed/original model/storage cases and 152 WeatherNext cases pass. This remains temporary research, with thermal attribution, actual energy outcomes, fresh weather-dependent fitting, daily-consumer migration and all cutover gates/removal unfinished.

### Fixed thermal forcing attribution — October 18

The [thermal comparison](2026-10-18-weathernext-fixed-thermal-attribution.md) now replays the retained 24-hour thermal control and swaps only origin-eligible Google temperature/GHI. Actual source replay exposed and corrected the adapter's older model-family assumption; selection now belongs to the executing original runtime. The installed irradiance/shade model's coefficients, initial state, actions and native geometry remain identical. The real comparison completed at 20:45:45Z in 0.947 seconds / 103,384 KiB RSS, preserving the same 24 target instants. Its first hour is not prospective; hours 2–24 were whole future intervals. Tests: 46 relevant thermal/native-weather cases and 152 pinned WeatherNext cases pass. This is fixed-model attribution, not scored thermal accuracy, fresh fitting or promotion. Actual qualified outcomes, supported-regime evidence, fresh weather-dependent Google/local fitting, daily consumers, qualification intervals, production integration and full retirement remain unfinished.

### Serving preparation and explicit withdrawal — October 18

The [Google-only serving preparation](2026-10-18-weathernext-serving-preparation.md) serializes all three existing forecast views, including explicit empty/unavailable states. The UI no longer treats an empty fresh forecast as ready. Optional source-qualified native Astro supplies hourly daylight and daily duration without substitutes. A real 12Z Google source acquired at 20:36:52Z produced ten UI days, 224 native daylight labels and a 49,118-byte detail; the actual UI parser accepts the ready and simulated unavailable cases. Tests: 156 WeatherNext, 150 existing forecast/Astro and 2,589 frontend cases pass; build passes. No scheduled production caller or deployed source was changed. Qualified serving/partial-write handling, numeric consumers, fresh fitting, release evidence and full retirement remain outstanding.

### Publication mechanics and numeric outputs — October 18

[Publication mechanics](2026-10-18-weathernext-publication-mechanics.md) now withdraw the detail first, verify three JSON/eight numeric outputs and commit the final detail last. Every failure attempts all eleven withdrawals and reports any unconfirmed clears. Real-source in-memory simulation and read-only Item-type checks passed; no live PUT occurred. Home/Weather no longer expose old arrays behind a parsed Google withdrawal. Complete-day summaries use all qualified original mean points while hourly rows remain future-only. Tests: 167 WeatherNext, 150 existing forecast/Astro and 2,591 frontend cases pass; build passes. This does not qualify or activate a production writer. Release/ownership/lock integration, retained attempts, required native consumer translation, fresh fitting/outcomes, intervals and complete retirement remain unfinished.

### Native thermal/energy source handoff — October 18

The [native Google adapter](2026-10-18-weathernext-native-inputs.md) retains complete original capsules, supplies causal hourly brackets and uses the existing native five-minute physics without inventing a weather code. Google collection requires no incumbent forecast credential or query. Household code evidence is explicitly unavailable; private Google context v4 supports the necessary larger payload while old/public limits remain. A retained-origin replay generated 26 rows / 288 steps in 1.007 seconds / 88,976 KiB, without publication, fitting or new action claims. Tests: 175 WeatherNext and 140 native/household/runtime/energy cases pass, including genuine large-source energy consumption and real source-runtime binding. This prepares the interface; native live/serving configuration, final installed-family deployment/fit binding, qualified release, real model/variable evidence and complete retirement remain required.


## Native source selection prepared (October 18)

Explicit Google-only native and receipt-serving configuration profiles now reach household collection, preparation, publication, scoring and immutable deployment staging without the forecast database credential. Inference opens the collector archive read-only; Google input mismatch refuses before publication, and receipt/deployment/model/source/resource checks remain. A real private source-selection preparation selected 26 original rows in 0.713 seconds without model admission or live changes. Verification: 115 native execution/staging, 175 pinned WeatherNext and 140 native/household/energy regressions passed. See [the native selection record](2026-10-18-weathernext-native-selection.md). Installed production remains incumbent; final Google-only removal/source closure, fresh Google/local fitting and all release gates still precede attended cutover.


## Installed model family preserved (October 18)

The migration source now preserves the installed fourteen-parameter irradiance/shade equations and source-bound validation. Google production profiles refuse older model families; scheduled fitting selects the preserved family, the full 83-source/context package verifies, and the UI accepts its removed-shade domain without granting authority. A retained real-data replay exactly matches all 288 forcing steps and 24 hourly rows; this uses old coefficients only for parity, not promotion. Final checks: 125 relevant Python, 175 WeatherNext and 2,598 frontend tests passed, plus UI build. See [model-family preservation evidence](2026-10-18-weathernext-irradiance-family.md). Final provider retirement/source closure and real fresh fitting remain ahead of cutover.
