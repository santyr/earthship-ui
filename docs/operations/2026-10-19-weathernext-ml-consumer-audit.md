# WeatherNext ML and forecast consumer audit — October 19

The audit found three production migration gaps: thermal irradiance loses Google's hourly interval semantics; the original household energy planner still depends on retired daily receipts; and all four energy outcome scorers are refusing pre-cutover sample indexes. WeatherNext acquisition, raw forecast publication and the separate physical PV/storage forecasts are operating. Passing source tests do not close the production gaps below.

This is a source/runtime audit, not an accuracy qualification. The [canonical inventory and finding ledger](2026-10-19-weathernext-ml-consumer-audit.json) inventories 282 Python modules, including shared readers and synthetic test helpers. The audit also traces installed systemd entry points, OpenHAB rules, browser/backend forecast boundaries and the adjacent Solar_PV analytics consumers. Private original readbacks, probes and logs remain outside Git.

## Confirmed findings

### WNML-01 · High · Thermal solar forcing interpolates interval means

`thermal_model/installed_shade_origin.py::_forecast_forcing`, also called by `native_thermal_forecast.py`, linearly interpolates `radiationWm2` between hourly endpoints. The native Google adapter obtains that field from `surface_solar_radiation_downwards_1hr`, dividing the original hourly energy by 3,600. It therefore describes a trailing hourly mean, rather than an instantaneous endpoint reading.

A read-only probe used the actual indexed Google snapshot `abbab673349548bd7f8b0630510ef4dd88f70e16ec2ae0bfa46cf17e4c0bad2d`, an origin of October 19 19:15 UTC, 26 original hourly brackets and all 288 thermal steps. At 19:20 UTC the thermal forcing used 625.14 W/m² while the original interval mean was 601.62 W/m². Full-horizon irradiation was 4,281.83 Wh/m² after interpolation versus 4,286.23 Wh/m² from the source intervals. The modest full-day difference does not establish equivalent hourly heat timing, especially around sunrise/sunset or with changing cloud cover.

The PV integrator already selects the containing ending-hour radiation interval. Temperature and wind can retain their separate interpolation policies.

**Correction:** preserve each original hourly radiation interval in thermal forcing, with regressions for increasing/decreasing radiation, hour boundaries, fractional origins and sunrise/sunset. Revalidate the source-bound native deployment and prospective outcomes; do not rewrite old forecasts or scores. This audit does not establish a numerical forecast error against measured indoor temperatures.

### WNML-02 · High · Original household energy planner still reads retired daily state

`household_cycle_sources.py:38` retains `/home/sat/.local/state/forecast-intel/state.json` and `Forecast_Prediction_Receipt_JSON`. Its live collector still reads both to construct `daily_energy_source`. `household_cycle.py:144` can bind the old daily energy projection only when that source exists; `household/pipeline.py::_candidates` requires its predicted trough before generating the original energy proposals.

The live receipt is `UNDEF`. Current retained Google-era plans have `energy_inputs=None` and their forecast evidence identifies `weathernext3`; the original candidate generator consequently reports `source_unavailable`. This is distinct from the separately working, conditional PV/storage and trajectory shadow scenarios. It does not mean the raw Google weather or the thermal model is unavailable.

**Correction:** remove the active dependency on extinct daily state and make the existing Google-derived trajectory the current planning basis, with explicit target/horizon labels. Keep historical daily readers isolated for original replay. Do not synthesize a legacy receipt, treat PV potential as captured PV, restore old learned weights, or grant action permission. Daily trough/curtailment estimates require their own valid target coverage; a rolling 24-hour scenario is not automatically a complete next-night forecast.

### WNML-03 · High · Retained indexes prevent every energy scoring family from restarting

The selected Google-only native score dispatch is `earthship-native-score-dispatch/v2`, with zero historical deployments. Four global sample indexes still contain references to excluded deployments:

| Index | Retained samples | References outside the selected deployment |
|---|---:|---:|
| Battery persistence | 96 | 96 |
| Solar/storage | 82 | 82 |
| Learned AC demand/storage | 6 | 6 |
| Captured PV | 82 | 82 |

The independent scorers reject those references before adding new samples: `household_battery_score.py:149`, `household_solar_score.py:107`, `household_profiled_score.py:109`, and `household_pv_score.py:121`. Actual managed-job journal records confirm `validation_refused` at those exact sites. The enclosing service can exit successfully with `status=waiting`, so exit code zero is insufficient evidence of scoring progress.

At the audit, battery, solar/storage and captured-PV reports still came from 17:28 UTC and expired around 17:58 UTC. The learned-load report was from October 16. These are retained pre-cutover reports, not newly qualified Google-era outcomes.

**Correction:** use explicitly separated Google-era sample indexes and report state, preserve original evidence without importing its scores, and test the actual existing-index cutover. Do not broaden the allowed source stages to make retired forecasts pass. Verify new original samples and subsequent mature outcomes in each family; report pending outcomes honestly rather than waiting for old references to age out.

### WNML-04 · Medium · Direct weather outcome evaluation remains offline

The running collector acquires Google forecasts; the shadow worker retains new issues; the trainer consumes Google/local temperature pairs. However, `weather_learning.evaluation.evaluate`, `solar_shadow.compare_solar_windows`, and the rainfall comparison routines are not called by the recurring weather entry points. Temperature comparison payloads contain `model.validation=None`. The hourly shadow cadence and weekly candidate-training cadence do not themselves score outdoor forecast errors.

Thermal and storage scores address different targets. Their existence does not prove direct Google outdoor-temperature, irradiance or rainfall performance monitoring.

**Correction:** connect bounded prospective weather-outcome evaluation to a scheduled observational job, using original available-at clocks and qualified local measurements. Retain independent day support, source/grid/sensor cohorts and explicit proxy limitations. No fixed 30-day deployment wait or automatic model promotion is needed.

### WNML-05 · Medium · Forecast parser introduces a missing dependency in ML contract checks

The current-head hosted `forecast-ml` check fails four Python/browser publication-contract tests because Node cannot find `suncalc`. The import chain is `forecastDetail.js → presentation.js → wmo.js → celestial.js → suncalc`. Those Python-only workflows previously executed the contract verifier without installing frontend packages. The ordinary frontend test check passes because its dependency installation differs.

This is a validation regression, not evidence that the live installed browser cannot render the forecasts. OpenHAB partition 2/3 also reports failure; its failed-log download returned no content in this audit, so no independent cause is asserted for that job.

**Correction:** keep pure forecast range/validation helpers free of visual/celestial imports, or explicitly install the required dependencies for every workflow that executes this verifier. Verify the package-free contract test as well as the normal browser tests.

## Consumer coverage

| Family / entry point | WeatherNext boundary and evidence | Assessment |
|---|---|---|
| Earth Engine collector · `weathernext_ingest.py`, `weather_learning/{weathernext_ee,worker,archive,normalize}` | Actual indexed Google source; original native metadata/cells and source payloads; normalized temperature, cloud, rain, radiation and wind; timer succeeds. | Ingesting. Installed collector differences are read-only-open/missing-source handling in archive/CLI, not different acquisition units or write semantics. |
| Production weather · `weather_publish.py`, `weather_learning/{provider,production_worker,production_runtime,production_publish}` | Google-only source selection, prospectively available clocks, complete required-variable coverage, no fallback; current detailed view and hourly/daily payloads available. | Ingesting. The 11-Item production writer is separate from the shadow provider-status Item. |
| Local temperature correction · `local_forecast_{shadow,train}.py`, `weather_learning/{cli,features,training,shadow}` | Installed shadow source matches the audited files; separate `google-local-v2` namespace; Google/local pairs; bounded bias/residual candidate remains shadow-only. | Ingesting. Direct scheduled evaluation gap is WNML-04. Weekly shadow training differs from daily physical thermal training. |
| Native weather capsule · `weather_learning/{native_backend,native_forecast}`, `native_thermal_live.py` | Actual source rederives 26 original temperature/GHI/wind brackets; Celsius→Fahrenheit and m/s→mph conversions; original Google capsule/hash retained; no forecast SQL credential or invented codes. | Ingesting. |
| Native thermal forecast · `native_thermal_forecast.py`, `native_irradiance_shade.py`, `thermal_model/installed_shade_origin.py` | Google temperatures/GHI reach 288 native five-minute forcings; current source-bound model publishes. | WNML-01. |
| Morning physical thermal training · `household_native_{daily,training}.py`, `native_thermal_{inputs,fit,artifact}.py` | Qualified local indoor/outdoor/radiation measurements, retained operator history and native geometry train physical response; serving selects Google-only forecasts. Current cutoff is October 19 06:00 UTC; daily timer is 06:50 Denver. | Correct distinction between forecast inputs and measurement ground truth; no retired learned state required. |
| AC-demand profile · `household_ac_load_{model,store,artifact}.py` | Qualified completed inverter AC hours; local-day cutoff; independent days; existing morning refresh, separate from battery charging. | Weather-independent training by design; joins the same-issue Google PV scenario at inference. |
| PV potential / terrain · `household_pv_model.py`, `household_solar_horizon.py`, `household_energy_forecast.py` | Original Google GHI/temperature/wind, native geometry, declared array, terrain profile; trailing-hour radiation retained. | Ingesting. Erbs decomposition, array losses and terrain remain provisional; direct-solar diagnostics are not silently substituted. |
| Constant-load storage and power flows · `household_energy_forecast.py`, `household/power_flows.py` | Same Google-derived PV steps plus qualified local SoC, AC demand, bank/topology declarations. Potential and modeled capture are distinct. | Ingesting conditionally; some issues withhold storage when AC input expires during preparation. No zero-load fallback. |
| Learned-load storage · `household_profiled_forecast.py` | Same original PV forecast; independent admitted load profile; exact original issue and source pins. | Ingesting when current storage inputs are available; source expiry can withhold a particular issue. |
| Battery persistence · `household/energy_persistence.py` | Current measured net battery power, original SoC and nominal bank capacity; no external weather input expected. | Appropriate independent baseline. Outcome progress blocked by WNML-03. |
| Original daily-energy model and planner · `household/{daily_energy_source,energy_model,pipeline}`, `household_cycle_sources.py` | Still requires retired state/receipt; Google trajectory scenarios are separate. | WNML-02. |
| New trajectory shadow plan · `household_trajectory_plan.py` | Same-issue Google PV/storage and learned-load scenarios; accepts retained forecast provenance separately from measurements. | Wired. Recent issues can report `source_stale`; no action authority follows. |
| Thermal scoring · `native_thermal_score.py`, `household_forecast_score.py`, installed-shade outcome readers | Retained exact original forecasts, measurement-qualified outcomes, Google-only dispatch and source-bound selected model. Current/historical slots retained. | New model remains provisional; future outcomes do not count as completed evidence. |
| Battery / storage / profiled / captured-PV outcome scorers | Original forecasts and qualified local measurements, with strict source/cohort pins; separate metrics. | All four blocked by WNML-03. |
| Weather variable diagnostics · `weather_learning/{evaluation,solar_shadow,energy_shadow}` | Google originals and source-qualified local temperature/radiation/rain comparisons; no pooled rainfall products or unsupported categorical codes. | Correct library boundaries; operational coverage gap WNML-04. |
| OpenHAB and native Astro | Live rule registry exposes no residual weather-forecast control consumer; Astro supplies geometry, local station supplies current-condition radiation ratio. | Native/local measurements remain appropriate. No weather-dependent actuator was enabled. |
| Browser/API presentation and qualification | Normalized Google views and sealed physical observations; unavailable source codes remain unavailable. Forecast context is retained provenance, not a measured observation. | Earlier UI repairs remain deployed. WNML-05 affects validation; public quality labels collapse retained context to “unavailable” and must not be read as failed ingestion. |
| Solar_PV analytics · `forecasts.py`, `feature_reader.py`, `scheduled.py`, trough readers | Actual Google detail parses into 1,422 analytic snapshots in a read-only probe. Snapshot timer is absent; historical daily trough readers still use original legacy advisory deliveries. | No active alternate weather acquisition found. Re-enabling snapshot ingestion requires explicit Google provider/run/source provenance and unsupported daily-PV handling; parsing alone is insufficient qualification. |
| Operator journal / Primal / historical tools | Active journal transport records confirmed actions. Legacy follow-up reads immutable advisory decisions; it is not a weather model. Pre-dusk tuning, sunset-SoC diagnostics, residual ablations and recovery helpers have no active forecast timer. | Historical/observational scope only. Do not revive legacy forecast sources or shelved recovery work. |

## Verification and operational observations

- A bounded serialized check passed **160 integration tests** in 72.93 seconds and **221 WeatherNext tests** in 10.943 seconds. Coverage includes Google irradiance-family preservation, native daily orchestration, source collection, PV/storage integration, learned-load scenarios, captured-PV outcomes and score diagnostics. Existing tests did not detect WNML-01 or the actual retained-index transition in WNML-03.
- The first local test invocation refused group-writable checkout sources. Standard non-group-writable permissions were restored on tracked files in the isolated worktree, with no source-byte change or live checkout alteration; the repeated exact selection passed. No provenance guard was disabled.
- Compared 291 staged source files with the audited checkout. The single difference was `weather_learning/provider.py`, the separately deployed cloud-cover presentation fix outside the native model binding. Thirteen installed shadow files matched; installed collector differences were inspected as noted above.
- Current-head hosted frontend, two OpenHAB partitions, WeatherNext foundation, receipt integrity, encrypted delivery, authentication and GitGuardian checks passed. Forecast-ML and OpenHAB partition 2/3 failed; this audit does not claim full CI success.
- Scheduled battery scoring is present at minute 8 of each ten-minute period. Its observed failures are original-reference validation failures, not an absent timer or proof of inadequate host memory.
- Your report “no venting today” was appended to the existing journal as closed from October 19 local midnight, received at 19:09:02 UTC. Historical availability was not backdated. Actual 19:10 and 19:15 UTC forecast publications subsequently show `vent_open=0` with manual-report provenance. No equipment command or external message was sent.
- No production model fit, forecast algorithm deployment, timer/resource-policy change, database migration, host restart or OpenHAB restart was performed by this audit. The operator observation above is the only production-data mutation.

## Completion boundary

Source and live evidence establish the findings above. They do **not** establish that all consumers are correctly migrated or that production accuracy is qualified. The high-priority remediation order is: restore independent Google-era score state; correct thermal interval semantics and validate the source-bound release; remove the retired daily-planner dependency. Scheduled direct-weather evaluation and package-free ML contract verification follow. Preserve all original evidence and keep automatic actuation disabled.
