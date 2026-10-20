# Historical learning and daily PV implementation plan

**Goal:** Restore daily PV potential, use historical Google forecasts with existing site measurements, retrain and evaluate the Earthship thermal models, identify and implement every other model case that benefits from supported historical retraining, calibrate PV potential using historical irradiance and qualified uncensored production intervals, and improve useful learning cadence without unnecessary refitting.

**Design basis:** Operator instruction to implement all improvements discussed on October 19. Google forecasts remain the only external weather source; local measurements are outcomes. Actuation remains disabled. Shared resource admission, no-swap execution and production deadlines remain intact. Existing immutable releases and prospective scores are preserved.

**Execution:** Inline in the existing isolated worktree; focused failing/passing tests for numerical or transport changes; one whole-branch review before final integration. Existing authorization covers deployment and remote main publication.

## Deliverables and evidence

- [ ] Inventory every fitted/calibrated forecasting model and baseline, available historical features/targets, existing fitting path, useful retraining change and qualification limitation. Explicitly cover Earthship indoor thermal models, outdoor temperature, irradiance/horizon correction, array PV potential versus curtailed capture, household AC demand and storage/SoC. Implement each supported beneficial retraining case; distinguish unavailable labels from implementation gaps.

- [x] Daily PV potential for each covered Home/Weather forecast date. Reuse array physics and native Astro geometry with terrain masking; integrate hourly irradiance on a five-minute grid, respect Denver dates/DST, retain explicit partial-today scope. Publish a separately versioned read-only view with expiry and source identities. Missing coverage stays unavailable. Verify arithmetic, bounds, native cache reuse, HTTP transport, rendered UI and live values.
- [x] Daily outdoor correction candidate training, with no-op when no new eligible completed observations. Retain existing shadow-only authority. Verify installed timer and actual run.
- [x] Resumable bounded historical WeatherNext acquisition in a separate archive, using the existing Google identity and approved request limits. Select dates overlapping local measurement history; cache originals, mark historical provenance, do not modify first-seen clocks or operational archives. Verify actual source retrieval and checkpoint progress.
- [ ] Retrospective outdoor/indoor training and chronological evaluation using that history. Fit only from earlier outcomes, evaluate later disjoint periods and compare baselines; retain source/lead/sensor/shade/vent evidence. Integrate qualified artifacts into production forecasting; retain explicit uncertainty when history is unknown. Verify real paired sample coverage, training receipts, holdout metrics and serving selection.
- [ ] Hourly household-load adjustment based on newly completed qualified AC measurements, alongside the daily 14-day profile. Retain separate identities and current-load/profile baselines; no zero-fill or invented balance. Verify chronological behavior and production use.
- [ ] Evaluate six-hourly versus daily thermal fitting on later held-out predictions. Support intraday cutoffs where necessary. Choose the measured better cadence; keep daily if higher frequency has no evidenced benefit. Forecast recalculation remains five-minute and existing scoring schedules remain unchanged.
- [ ] End-to-end production monitoring, focused regression checks, source/runtime lineage and remote main publication. No recovery work or household-planner architecture expansion.

- [ ] PV potential calibration: historical Google/site irradiance correction, terrain/time-of-day/season error analysis, array output/loss fitting from qualified uncensored production, chronological held-out comparison to the current physics baseline, calibration status and source lineage in serving. Preserve separation of potential and captured PV; identify controller/SoC/meter-coverage limitations explicitly.

## Implementation order

1. Daily PV numerical view, native cache worker, fixed GET route and UI binding; deploy after focused verification.
2. Daily outdoor training with idempotence; deploy schedule.
3. Historical acquisition and coverage inventory; run bounded batches while implementing retrospective pairing and chronological evaluation.
4. Hourly load residual and baseline comparisons; deploy with retained evidence.
5. Thermal cadence experiment and eligible historical-model integration; deploy selected behavior.
6. Whole-branch review, completion audit, documentation and merge/push.

## Ledger

- 2026-10-19: Started at `eb92aff` on `feat/historical-learning-pv-20261019`. Root live checkout contains intentional overlays; deploy only verified files or new frozen releases. No reset/cleanup.
- Ruling: Daily PV uses a separate curated view, preserving the eleven-Item weather writer and sealed model receipts. This avoids treating an array calculation as a Google forecast field.
- Ruling: Additional training schedule executions alone are insufficient: current thermal/load cutoffs are midnight. Higher-frequency fitting requires new completed data and comparative evidence.

- 2026-10-19 operator expansion: Earthship thermal models must also be retrained using historical OpenHAB/WeatherNext pairing; identify and implement all other cases benefiting from historical retraining. This is required scope, not optional follow-up.

- 2026-10-19 operator expansion: PV potential calibration is required scope. Historical Google irradiance, site radiation, terrain, qualified PV meter coverage and charge-limited censoring must be assessed; implement the supported calibration and report held-out performance.

- Task 1: deployed daily PV sidecar and Home/Weather rendering from frozen `35a64b4`. Live source yielded ten covered days; 53 Python and 22 frontend checks passed, build passed, and installed hourly job succeeded. Native geometry cold cache took 17.7 seconds; subsequent refresh reused original geometry clocks. Potential remains explicitly provisional pending required calibration.
- Finding for thermal refresh task: `/home/sat/.local/state/thermal-intel/native-daily/last-result.json` reports `daily_native_refresh_failed: closed staged source set differs`; investigate actual checkpoint and selected release before claiming daily fitting healthy.

- Task 2 tests: 34 weather shadow/training tests and 17 subtests passed. Daily training now skips identical paired evidence and refits when outcomes change. Chosen daily slot is 06:35 Denver, ahead of the 06:50 thermal job.

- Task 2 deployed from frozen `43549fd`: installed timer is daily 06:35 Denver; actual run fitted 14 completed pairs in the active `google-local-v2` cohort.
- Checkpoint correction: the failed native checkpoint was in an inactive historical state directory. The actual configured morning state reports `already_current`, exit 0, with training cutoff October 19 06:00 UTC; no active daily-training failure was established.
- Historical capture progress: all 28 UTC measurement days September 20 through October 17 are retained. Qualified five-minute targets: indoor 8082/8092, wall 8052/8092, outdoor 8083/8092, bedroom 4901/8092. Missing targets remain absent; original v1 receipts keep sensorEpoch absent.

- Historical infrastructure checkpoint: 116 recent Google runs and 291 days of older numeric OpenHAB measurements retained. First historical fits and an uncontaminated earlier native physics refit completed; none activated. Seasonal Google sampling and hourly original energy capture are running. Source snapshots and actual environment versions retained for future fits. Baseline comparison, calibration, serving integration and remaining model cases are not complete.
- Ruling: use weekly four-cycle Google sampling across older seasons initially, preserving full hourly forecast horizons and actual source clocks. This covers seasonal and diurnal regimes without fetching every redundant daily run. Expand based on coverage or learning-curve evidence.
- Ruling: low SoC and sub-clipping charge periods supply provisional potential labels; without charge-mode/fault receipts they do not grant physical calibration qualification. Keep that limitation visible in artifacts and serving.

- Energy experiments complete on all 696 retained hours: hourly load adjustment and apparent storage capacity lost to their current baselines; retain current daily profile and nominal bank capacity. Controller conversion improved conditional-on-measured-input error, not battery-acceptance forecasting.
- Ruling: do not deploy a worse hourly load adjustment or add fitting executions solely to meet a cadence proposal. The measured outcomes favor the existing profile. Keep the implemented experiment available for future evidence.
- PV progress: first global adjustment improved MAE but worsened the afternoon subset. A fixed, regularized 45-degree variant improved aggregate retrospective error from 560.91 to 438.91 W across 124 intervals on five days. It is a development variant and requires prospective monitoring. Prepare first-24-hour-only provisional deployment, preserve raw physics/longer horizons and exact prediction steps. Seasonal/site irradiance separation and same-issue downstream integration remain required.
- Verification: 54 focused Python cases, 18 frontend cases; final tightened source-loader regression passed separately. Build passed with a larger dynamically admitted 2.5 GiB preference after the initial 1.5 GiB build was stopped by the shared pressure watchdog. No host/pool pressure safeguard changed.

- Deployment evidence: frozen `42b680e` daily PV service succeeded; live GET serves v2 with selected directional model `f7ed8273c8ee8c2e5c07961165659fe803fa318a1ec55bdebb1ae2078428ad83`. At publication, October 20 potential was 14.00 kWh adjusted versus 20.10 kWh raw. October 21 and later remained unchanged. Read-only Chromium checks over `192.168.1.217` rendered ten PV values on both Home and Weather, one empirically adjusted day, and no page errors. Earthship UI remained active.

- Prospective PV monitor implementation: hourly at :55, evaluate the preceding mature full UTC hour from an original forecast that existed before that hour. Retain original input-power/BMS/AC receipts, exact prediction steps and unchanged score receipts. Full-battery/censored or missing measurements produce unavailable metrics, never zero error. Initial live check correctly reported `awaiting_as_issued_forecast`: the scored hour preceded the new model's actual deployment. Three regressions passed, covering post-origin/modified forecasts, censored evidence and scoring after UI-display expiry. The numerical scoring scope remains a low-SoC controller-input proxy, not certified full-day potential.

- Prospective monitor deployed from frozen `56a8c3c`; installed hourly timer is active at :55 plus up to 15 seconds. Actual service result is success, with the explicit initial `awaiting_as_issued_forecast` status. Existing UI and daily PV timers remain active. Current daily PV worker uses the same tested numerical implementation in that frozen release.
- Continuing work: seasonal Google history is at 66/152 sampled cycles and still acquiring. Recent 116-cycle and 291-day numeric datasets are complete. The full goal remains active: finish seasonal/irradiance analysis, historical thermal comparison and serving decisions, thermal cadence assessment, downstream PV/storage integration, remaining source-supported model cases, final whole-branch review and main integration. None of those are implied complete by the PV deployment.

- Completed actual thermal cadence experiment: twelve earlier refits at six-hour cutoffs across October 14–16, evaluated on twelve later Google forecast origins and 48 matched 1/6/12/24-hour outcomes. On the same 25 pairs with stable retained collective action declarations, daily air/mass MAE was 0.818/0.515 C and six-hourly was 0.697/0.369 C (about 15%/28% lower). All-outcome errors also improved. No stable-declaration 24-hour subset was available; this is a three-day retrospective comparison, not actuation qualification. Original/current selected fitted weights were not reused for the earlier models.
- Cadence implementation: completed local six-hour cutoffs, with daily load training retained. Per-day capture indexes reuse at most two long immutable original prefixes; the original eight-part, two-day capture, byte, pressure and fitting limits remain unchanged. Six new DST/load/prefix regressions and the existing daily/resource cases passed (24 tests total). Actual checks show numerical runtime and capture revision unchanged. Production cadence activation remains pending.
- Seasonal acquisition now explicitly retains missing core targets in a distinct training coverage index. Its strict completeness default is unchanged; available targets train and missing values are never filled. The April 30 run's missing GHI hour no longer blocks the rest of the year.
- Radiation evidence: all 29 receipt-source days retained (46,152 original rows; first nonempty date October 2). Three overlap days support legacy W/m2-proxy units: MAE 2.58/4.65/14.44 W/m2 versus 388/398/318 for a lux interpretation. Recent clean-v2 hourly coverage is 23/24, 21/24 and 23/24 hours. Legacy units and hardware health remain explicitly assumed/unknown before receipt coverage; incomplete recent receipt windows do not become training labels.


## Remaining PV potential calibration work

The existing directional adjustment is provisional and already served. Its 560.91 to 438.91 W error change is a retrospective development comparison on 124 qualifying intervals across five later dates, not an independent prospective result or a certified physical calibration.

- [ ] Build historical Google/local irradiance pairs across the retained seasonal sample. Quantify error by lead, month, solar elevation and azimuth. Preserve null forecast targets and reject incomplete recent receipt windows; identify the earlier numeric radiation unit/health assumptions.
- [ ] Compare the declared 57.4-degree panel tilt, approximate 165-degree true azimuth and unvalidated terrain horizon against measured morning/evening production. Fit only effects supported by observations; do not claim that weather bias, lux-proxy bias, terrain and array losses have all been independently identified.
- [ ] Extend electrical calibration with qualified low-SoC, positive-charge, sub-clipping intervals, retaining actual controller-input meter scope. Exclude charge-limited/missing intervals rather than teaching the array to predict curtailment as low potential.
- [ ] Compare candidates on later chronological targets and supported lead/season groups against raw physics and the current directional correction. Retain the better candidate; report independent days and unsupported groups.
- [ ] Apply supported calibration consistently to same-issue PV/storage scenarios while preserving raw potential, captured-energy scope, source identities and uncertainty.
- [ ] Accumulate actual as-issued production scores from the installed hourly monitor. Report unavailable/censored periods explicitly and assess whether the retrospective improvement persists. No arbitrary additional waiting period is required to serve useful provisional forecasts.

- Acquisition complete: 116 recent four-cycle runs and all 152 requested weekly seasonal cycle samples are retained in the separate historical archive. These are samples across the year, not a complete daily year. Additional acquisitions should be driven by a demonstrated coverage gap.
- Foundation verification: 41 focused regression cases passed. The active score-history inventory retained both currently referenced historical stages, changed no archives, and remains deployment-pending with the six-hour cadence implementation.
