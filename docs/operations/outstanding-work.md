# Outstanding Earthship and OpenHAB work

Evidence inventory started 2026-09-05. This is a completion tracker, not an
implementation approval or a claim that historical tasks are finished.
Owner: Hex (the current assistant). Task 82 remains explicitly on hold and is
outside this Earthship workstream.

Operator approval update, September 5: Sat approved all pending work and directed
completion. This clears the pending storage-plan corrections, corrective alert
design, and integration/release decisions, subject to verification and unchanged
safety constraints. Task 82 remains held; future-data and seasonal gates remain
unfinished until their actual evidence exists.

The Cistern Pump display rename is merged and published in origin/main at
377763a. Fresh verification: 1,103 UI tests, build, two fixture browser checks,
and live read-only 1340x800 check (new label present, old label absent, no page
errors or control-write requests). Underlying ShurefloPump_Power item and control
IDs are unchanged. Local Vite serves the main checkout; no service restart was
needed. Build emitted large-chunk warnings; browser runner emitted a color-env
warning. Neither run failed. The merged rename worktree was removed; commits
remain in Git.

| Work | Current evidence | Remaining completion evidence |
| --- | --- | --- |
| Task 95: battery daily minimum SoC, DoD, EFC | September 5 reader-first v2 deployment verified against the September 4 persisted row: minimum 84%, range 16 percentage points, daily EFC 0.1656947462, cumulative EFC 7.297289539817, epoch discover_4_module_2026, battery quality ok. Live 1340x800 tablet dialog fits, displays correct values and closes. No accounting or BMS-counter changes. | Completed. Continue normal daily collection; EFC is estimated available-epoch use, not manufacturer lifetime cycles. |
| Task 96: energy forecast snapshot ingestion | September 5 repaired capture service succeeded, storing 1,446 v2 rows with genuine issue time 2026-09-05T13:45:29Z. Live analytics forecast now current. Both existing timers restored active. | Completed. Preserve the August 27–September 5 capture gap; no fabricated historical origins. |
| Task 18: Bandit thresholds | Task explicitly requires outcome verification. Thermal shadow is observational. No outcome/advisory/reward-named tables found in inspected OpenHAB PostgreSQL database; this alone does not prove no loop exists elsewhere. | Inventory actual decision/outcome producers, establish verified delayed outcome attribution and scoring, then approve bounded tuning design and verify it before live threshold changes. |
| Task 16: forecast ML v3 | Hexmem remains in progress with conformal trough/PV intervals and low-temperature correction watch outstanding. Current forecast_intel retains seven absolute PV/trough errors; searched P10 Items absent. | Trace all current producers and scoring history, specify calibrated intervals and evidence requirements, test and verify publication; explicitly resolve the under-correction watch. |
| Task 19: analog ensembles and hourly GBM | Pending reminder expects approximately 90 days of forecast/actual pairs and October 19 checkpoint. Snapshot ingestion was repaired September 5; current history has nine distinct local issue dates. | Accumulate and verify usable paired history; approve and validate models against held-out baselines. Do not substitute calendar age for valid coverage. |
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

## September 5 learning-prerequisite follow-up

- Before the repair, stored forecast snapshots covered eight distinct local issue dates,
  August 20–27. After verified September 5 capture, there are nine overall. Restoring capture does
  not retroactively create the missing origins or meet the approximately
  90-day analog-ensemble prerequisite.
- Current forecast state retains 30 daily prediction entries (August 7 through
  September 5) and seven absolute PV/trough errors. Those short arrays are not
  a validated long-term calibration set for confidence intervals.
- The thermal journal contains ten action events. Forecast state records an
  advisory category in each daily prediction and a DM deduplication marker,
  but the inspected path does not link decisions/actions to delayed rewards.
  Do not infer outcome verification from an action journal or forecast error
  average alone.
- Current read-only journal verification places those ten action events between
  October 16, 2025 and May 22, 2026. They do not verify current warm-season
  advice. Tracked and installed `forecast_intel.py` hashes match; the current
  decision path replaces its per-date prediction record on each run and keeps
  only 30 dates. It does not preserve an immutable decision ID, the exact
  thresholds/corrected inputs for that decision, or linked measured outcomes.
- Task 18 next design gate: preserve each decision and notification result,
  associate later measured outcomes and confirmed actions without assuming
  compliance or causal benefit, and retain unscorable evidence explicitly.
  Prefer the existing quantitative PostgreSQL/OpenHAB history plus compact
  verified Hexmem observations. No threshold tuning, new DM, migration, or
  runtime capture is authorized by this prerequisite assessment alone.

## Task 16 calibration audit — September 5

- Live state has seven PV percentage errors and seven SoC-trough absolute
  errors, without per-error issue timestamps or coverage metadata. No interval,
  P10, P90, or conformal-named OpenHAB Items were found in the current inventory.
- `Forecast_TempLow_Error_7d=7.2` is raw forecast MAE, not corrected forecast
  MAE. The current low filter bias is +8.214 F and the producer subtracts that
  bias. The raw error cannot prove that the applied correction is inadequate;
  evaluate generation-time corrected forecasts against later actuals instead
  of subtracting today's filter retrospectively from historical forecasts.
- Confirmed incomplete-night scoring defect: `measured_trough()` defines the
  observation window as 20:00 through 11:00 local, but the live daily timer
  invokes `forecast-intel` at 06:40. Its September 5 journal reports the
  September 4 prediction scored against an actual of 86% at 06:40:29; live
  state already marks that trough scored. The remaining observation window
  had not elapsed. The per-quantity guard prevents later same-day correction.
- Repair must precede trustworthy interval calibration: score only completed
  trough windows, retain forecast-origin and target identities, and permit
  delayed scoring without duplicate updates. Keep the 06:40 forecast/advisory
  schedule; a whole-job move to 11:00 would delay existing morning advice.
  Do not reset learned state or relabel the old seven errors as validated
  full-window calibration evidence. Implementation design remains pending.

## Outcome implementation preflight

Implementation branch `feat/advisory-outcome-foundation` now contains the pure
UTC day/trough window dependency and immutable decision/result JSON builders
(implementation commits 33fb0f9 and d283033). Combined verification has 132 passing
tests and clean task/whole-branch reviews. These are dependencies only: storage
activation, producer capture, measured outcomes and live scoring replacement are unfinished.
The reviewed foundation was merged into main at 4818d75 and reverified with
132 Python and 1,103 UI tests. No live forecast capture/scorer was wired or
activated by this merge. Solar_PV storage corrections at 1de8aa0 resolved fixture
routing isolation and deterministic timeout/retry acceptance. Independent task
and whole-branch reviews are clean. The storage implementation was merged and
pushed to Solar_PV main at 7f0b583, with 240 tests passing on merged main in
7.29 seconds and exact remote SHA verified. This integrates source only: production
migration, runtime grants, shared-module installation and capture activation have
not occurred. Completed-window live evidence remains required.
Detailed source-health evidence is in
`docs/operations/2026-09-05-outcome-source-health-preflight.md`: the September 4
BMS heartbeat provides full-day coverage under the existing 12-minute allowance,
despite zero comms/device state changes. Further tracing found persisted WH65B
and WH32B packet-age companions covering the sampled day, but receiver field
fallback and source-epoch validation still prevent treating packet freshness as
proven per-temperature freshness. A synthetic probe also reproduced future-heartbeat acceptance
in Solar_PV daily quality; that path must be corrected before reuse for outcomes.

The written outcome/scoring specification was approved. Live cadence validation
then found a necessary design correction before implementation: managed JDBC
persistence uses everyChange plus restoreOnStartup for all Items, with no cron
strategy. Under the approved 20-minute hold, September 2–4 BMS_SOC history covers
only 34.4%, 45.2% and 38.2% of each day; hallway temperature covers 96.3–98.6%.
Some SoC gaps exceed five hours. Change-only history cannot itself establish
fresh observations during an unchanged interval; this is not proof of BMS failure.

Do not silently lower the 90% coverage gate or treat these gaps as fresh samples.
Proposed operator decision: add five-minute periodic persistence for BMS_SOC
through OpenHAB's existing JDBC owner, retaining everyChange and restoreOnStartup
and leaving other Items and controls unchanged. This adds observations, not a
new collector or forecast/notification run. A periodic stored value alone is not
freshness proof: the implementation must also validate contemporaneous BMS
freshness evidence and reject a cached value during stale/faulted telemetry.
This periodic-persistence proposal was superseded by Sat's subsequent direction:
adjust all algorithms for change-only persistence rather than changing storage
strategy. No persistence configuration was changed. The outcome specification
now separates held value state from independently verified telemetry freshness.

## Change-only semantics and notification audit

Corrective alert design: `docs/superpowers/specs/2026-09-05-change-only-alerts-design.md`.
Written review is pending; no corrective alert code has been deployed. September 5
read-only verification confirmed live bulk REST lastStateUpdate and targeted
ItemStateUpdatedEvent support, so unchanged sensor updates can be used without
adding a collector or changing JDBC strategy. The spec separates this alert slice
from the still-required historical-algorithm audit.

- Confirmed UI false alert: src/lib/alerts/staleness.js flags BMS_SOC after
  60 minutes without a value change even with a current BMS_SOC_LastUpdate
  heartbeat. Snapshot receipt time also must not masquerade as sensor freshness.
- Forecast window readers, hourly matching, thermal historical gap rejection,
  dashboard extrema and Solar_PV integrations require a source-by-source audit
  for carry-in, reset boundaries, health gating and event-sampling bias. Do not
  claim these are all fixed from the UI reproduction alone.
- The supplied DMs are `openHAB sanity` runtime-basis alerts, not stale-SoC
  alerts. openhab_sanity_check.py immediately flags basis=bms with current>0.5A.
  The live estimator intentionally dwells for eight minutes. September 5 basis
  transitions: evening08:48:46, bms08:49:16, now08:56:49; the08:52:50 warning
  occurred during that permitted dwell. The next sanity check reported recovery.
  Correct the checker against the actual state-machine contract, retaining
  detection of persistent mismatch. Do not remove genuine freshness alarms.
- Existing BMS_SOC_LastUpdate is a five-minute rate-gated timestamp driven by
  raw SoC update / scale-factor events; the scaler also calculates comms health
  from a120-second raw-update timeout. The sanity checker already evaluates the
  heartbeat timestamp value, not a persisted SoC change timestamp.
- Authorized read-only Nostr verification fetched 37 unique outgoing NIP-04
  events for the operator over the preceding 14 days from two responding relays;
  all 37 decrypted locally. Of these, 34 were runtime-basis warnings/recoveries,
  including the supplied September 5 examples. This is bounded relay evidence,
  not a claim of complete lifetime DM history or recipient delivery. No message
  was sent, credentials printed, or decrypted archive committed.

## Safety and completion boundaries

No hardware actions, advisory-policy changes, migrations, or production writes
were performed for this inventory. Design approval and cross-repository
contracts apply before implementation. Existing OpenHAB controls and Discover
BMS counters must remain unchanged. A future-data dependency is unfinished
work, not a passed check. The broad goal remains active.
