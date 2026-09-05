# Outstanding Earthship and OpenHAB work

Evidence inventory started 2026-09-05. This is a completion tracker, not an
implementation approval or a claim that historical tasks are finished.
Owner: Hex (the current assistant). Task 82 remains explicitly on hold and is
outside this Earthship workstream.

| Work | Current evidence | Remaining completion evidence |
| --- | --- | --- |
| Task 95: battery daily minimum SoC, DoD, EFC | Live PostgreSQL daily_battery has 48 days, July 19 through September 4. Latest minimum 84%, maximum 100%, daily range 16 percentage points, daily EFC 0.1656947462, cumulative EFC 7.297289539817. OpenHAB Energy_Analytics_JSON publishes minimum and cumulative EFC. | Verify coverage and epoch semantics; approve and expose missing daily DoD/EFC values with clear definitions and tests. Preserve BMS counters. |
| Energy forecast snapshot ingestion | Live Forecast_10Day_JSON version 2 is fresh. Solar_PV analytics parser accepts only version 1. Read-only parsing reproduces ValueError; energy-forecast-snapshot.service failed. Latest stored forecast issue is August 27. | Version-aware producer/consumer contract repair, regression tests, authorized deployment, fresh captured history and live analytics readback. Never rewrite issue timestamps to make old forecasts appear current. |
| Task 18: Bandit thresholds | Task explicitly requires outcome verification. Thermal shadow is observational. No outcome/advisory/reward-named tables found in inspected OpenHAB PostgreSQL database; this alone does not prove no loop exists elsewhere. | Inventory actual decision/outcome producers, establish verified delayed outcome attribution and scoring, then approve bounded tuning design and verify it before live threshold changes. |
| Task 16: forecast ML v3 | Hexmem remains in progress with conformal trough/PV intervals and low-temperature correction watch outstanding. Current forecast_intel retains seven absolute PV/trough errors; searched P10 Items absent. | Trace all current producers and scoring history, specify calibrated intervals and evidence requirements, test and verify publication; explicitly resolve the under-correction watch. |
| Task 19: analog ensembles and hourly GBM | Pending reminder expects approximately 90 days of forecast/actual pairs and October 19 checkpoint. Snapshot ingestion is currently broken. | Verify usable paired history, repair capture, approve and validate models against held-out baselines. Do not substitute calendar age for valid coverage. |
| Task 21: live winter timezone verification | Pending November MST verification; summer checks cannot satisfy its explicit requirement. | Inspect actual winter data after transition, including sunny/cloudy boundary cases and calibration attribution. |
| Task 22: rain/wind learned corrections | Task description explicitly defers rain and requires a wind consumer, scoring, and renewed approval. | Resolve deferred scope with operator; satisfy outcome/scoring prerequisites before implementing learned gains. |

## Existing battery ownership and definitions

Solar_PV analytics owns quantitative PostgreSQL history and scheduled
aggregation/publication. OpenHAB exposes Energy_Analytics_JSON; earthship-ui
validates and displays it. Do not add competing accumulators without a reason.

Current backend definitions:

- Daily DoD field is maximum minus minimum SoC within the day, not total
  discharge throughput and not necessarily 100 minus minimum SoC.
- Estimated daily EFC is (charge kWh + discharge kWh) / (2 * configured
  nominal usable kWh). Multiple partial cycles contribute to throughput.
- Cumulative EFC is recomputed from daily records within the bank epoch, rather
  than blindly incremented each time the daily job runs.
- The counter is independently calculated from telemetry, not independent of
  the telemetry's measurement errors. Data coverage and capacity assumptions
  must remain visible; it is not automatically lifetime use since installation.

Source pointers: Solar_PV/analytics/src/earthship_energy/{aggregation,series,
materialize,forecasts,ui_payload,ui_reader}.py; src/lib/energy/analyticsResult.js;
src/lib/ui/EnergyAnalyticsDetail.svelte; docs/operations/energy-analytics.md.

## Safety and completion boundaries

No hardware actions, advisory-policy changes, migrations, or production writes
were performed for this inventory. Design approval and cross-repository
contracts apply before implementation. Existing OpenHAB controls and Discover
BMS counters must remain unchanged. A future-data dependency is unfinished
work, not a passed check. The broad goal remains active.
