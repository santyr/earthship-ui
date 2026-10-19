# Historical learning and daily PV implementation plan

**Goal:** Restore daily PV potential, use historical Google forecasts with existing site measurements, retrain and evaluate the Earthship thermal models, identify and implement every other model case that benefits from supported historical retraining, calibrate PV potential using historical irradiance and qualified uncensored production intervals, and improve useful learning cadence without unnecessary refitting.

**Design basis:** Operator instruction to implement all improvements discussed on October 19. Google forecasts remain the only external weather source; local measurements are outcomes. Actuation remains disabled. Shared resource admission, no-swap execution and production deadlines remain intact. Existing immutable releases and prospective scores are preserved.

**Execution:** Inline in the existing isolated worktree; focused failing/passing tests for numerical or transport changes; one whole-branch review before final integration. Existing authorization covers deployment and remote main publication.

## Deliverables and evidence

- [ ] Inventory every fitted/calibrated forecasting model and baseline, available historical features/targets, existing fitting path, useful retraining change and qualification limitation. Explicitly cover Earthship indoor thermal models, outdoor temperature, irradiance/horizon correction, array PV potential versus curtailed capture, household AC demand and storage/SoC. Implement each supported beneficial retraining case; distinguish unavailable labels from implementation gaps.

- [x] Daily PV potential for each covered Home/Weather forecast date. Reuse array physics and native Astro geometry with terrain masking; integrate hourly irradiance on a five-minute grid, respect Denver dates/DST, retain explicit partial-today scope. Publish a separately versioned read-only view with expiry and source identities. Missing coverage stays unavailable. Verify arithmetic, bounds, native cache reuse, HTTP transport, rendered UI and live values.
- [x] Daily outdoor correction candidate training, with no-op when no new eligible completed observations. Retain existing shadow-only authority. Verify installed timer and actual run.
- [ ] Resumable bounded historical WeatherNext acquisition in a separate archive, using the existing Google identity and approved request limits. Select dates overlapping local measurement history; cache originals, mark historical provenance, do not modify first-seen clocks or operational archives. Verify actual source retrieval and checkpoint progress.
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
