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

Operator approval update, September 10 (Hexmem 8689): Sat approved the written
UI current-day history specification and expanding the BMS design to emit each
value with its timestamp in one source record. This supersedes the pending
approval status of those approaches; it is not implementation or live
verification. The originally approved separate BMS event/timestamp streams lack
an exact sample association and must not silently populate the old observedAt
contract. The isolated BMS draft is explicitly marked superseded in 70b9667.
The written atomic BMS observation specification at `43ccb08` was subsequently
approved (Hexmem 8691). Its source transformations, observer and activation
preflight remain unfinished; the superseded BMS draft must not be deployed.

UI current-day temperature history is merged at `487365c`. Native start-state
carry is opt-in for the two daily temperature requests, with half-open end
clipping and day-owned results. Midnight and tablet visibility reconciliation
clear yesterday's extrema; failed or late responses cannot restore them.
Independent task and whole-branch review passed after deterministic late-response,
HTTP-failure and explicit Denver DST regression additions. Removing the commit-day
guard made the late-response regression fail, then exact restoration passed.
Fresh merged-main verification: 1,175 unit tests, all 10 Home browser tests and
build passed. Existing chunk-size and browser color-environment warnings remain.
Live read-only 1340x800 verification on September 10 used local midnight
`06:00Z`, boundary carry and actual persistence rows: outdoor 90.86/48.38 F
rendered 91/48, indoor 82.58/67.1 F rendered 83/67. No page errors, horizontal
overflow or write requests occurred. Active local Vite serves this main checkout;
no restart was needed. This is not a live overnight or winter observation.
The isolated UI worktree is retained to preserve ignored review evidence.
Broader source-health, outcome/scoring and remaining algorithm work is still open.

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
migration, runtime grants, shared-module installation and capture activation had
not occurred at that source-integration checkpoint. Migration 0002 has since been
installed in the separately reviewed corrective release below; runtime grants,
shared-module installation and capture activation remain unfinished.
Completed-window live evidence remains required.

Default-off producer source has since been integrated at `2fa6a70` under
`docs/superpowers/plans/2026-09-05-advisory-capture.md`. It freezes natural-run
decision inputs and observes the existing advisory/trough PUTs and notifier
results, with no side-effect retries. Exact enabled flag, lazy storage import,
constant capture-gap diagnostics and unchanged advice/DM behavior are covered
by 27 new regressions. Genuine RED27fail preceded implementation; affected
GREEN159pass, independent full Python754pass plus42subtests in139.83seconds,
and clean task/whole-branch reviews. Affected159tests passed again on main.
This is source integration only: both forecast services still execute the
unchanged installed `/home/sat/openhab/scripts/forecast_intel.py` (SHA-256
`6a3d176a9e8e852c8da9890e4c5d8a4731a912124065b8cf8ae7af7f72b23412`).
Capture helpers, protected runtime DSN/least-privilege role and assessors must
be installed and verified before activation. No decision or outcome is claimed
captured live, and premature scoring remains a required separate correction.

Detailed source-health evidence is in
`docs/operations/2026-09-05-outcome-source-health-preflight.md`: the September 4
BMS heartbeat provides full-day coverage under the existing 12-minute allowance,
despite zero comms/device state changes. Further tracing found persisted WH65B
and WH32B packet-age companions covering the sampled day, but receiver field
fallback and source-epoch validation still prevent treating packet freshness as
proven per-temperature freshness. A synthetic probe also reproduced future-heartbeat acceptance
in Solar_PV daily quality. The source correction is now complete on isolated
branch `fix/heartbeat-provenance` at `3b82b94`: original carry timestamps are
preserved, future-at-observation reports grant no coverage, and timezone
validation precedes stable observation sorting. All 275 analytics tests passed
in 7.26 seconds; final whole-branch re-review found no outstanding issues.
The separately reviewed corrective release is now complete: Solar_PV main and
origin/main are both `3b82b94d1e94a3007543f862b048321ee9d784c6`, with275tests
passing on integrated main in7.32seconds. Live daily aggregation imports this
checkout, so the next normal run uses the correction. No aggregate/backfill/reset
was invoked. Independent comms-fault intersection,
restart/epoch checks and per-weather-field provenance remain open before reuse
for verified outcomes.

Further live-source tracing and an isolated replay found that `hex_bms_soc_scale`
refreshes its heartbeat before validating raw SoC and on scale-factor changes
alone. Invalid raw 65535 and unavailable scaling can therefore retain old SoC
while posting a fresh heartbeat and comms OK. The preflight document records
the exact script hash, positive control and counterexamples. Producer-validity
and binding/restoration provenance remain open; no live scaler or control gate
was changed. Historical heartbeat coverage is not yet validated SoC coverage.

Sat subsequently approved a separate validated SoC signal. Draft source/tests
are isolated in `.worktrees/bms-soc-evidence`, but live WebSocket verification
found that OpenHAB5.2.1 event reconstruction strips source from updated events.
The original binding state event retains it. Implementation is paused before
source commit/deployment pending the corrected event/timestamp contract; the
42 passing draft tests do not establish runtime usability. Native Modbus read-
success channels and a generic event trigger are available for that correction.
The preflight also reproduced nonfinite numeric carry becoming apparently valid
zero-power analytics. That independent correction is now integrated and pushed
to Solar_PV main/origin at `91867f8c79bf894d608ec0f052d343fe19eb2bc6`:
selected carries receive the same finite check as in-window rows, before
synthetic boundaries or clipping. Genuine RED17fail/10pass preceded the change;
focused27pass, full296pass, clean task and whole-branch reviews, and integrated
main296pass in7.29seconds. September4 complete read-only daily JSON is identical
before, after and on integrated main (SHA256
`16c37713e2855d93a892c4b573c5828656f3f90dfc24f5e744f809a034c0d080`).
The existing service imports this checkout; it remains inactive with prior
success status, timer active for September6 00:20MDT. No manual apply/backfill,
database/configuration mutation, schedule change or learned-state reset occurred.
September 10 read-only follow-up closes the natural-run verification item:
the September 6–10 scheduled invocations all finished successfully, reporting
materialization of September 5–9 respectively (five tables and 21 source-quality
rows each). PostgreSQL readback confirms all five daily battery records in
`discover_4_module_2026`, with cumulative EFC respectively 7.460282252545,
7.629311980220, 7.804210099642, 7.968349561756 and 8.134920384835, matching the
service journal. Solar_PV remains clean at `91867f8`; the service still imports
that checkout. Latest invocation September 10 00:20:29 MDT exited 0; timer active
for September 11. No manual apply, restart, backfill or production write was
used for this verification. Successful materialization is not independent proof
of historical sensor health and does not close the separate BMS event/timestamp
contract or broader source-health work.

Release preflight also found that the already integrated advisory migration0002
would block the next daily --apply invocation while pending. Following a verified
14-table/four-sequence isolated restore of the affected-schema backup, only0002
was applied transactionally. Readback verifies versions[1,2], no pending migration,
two empty advisory tables with enabled append-only triggers and no PUBLIC table
privileges. Seven existing history/configuration row fingerprints are unchanged.
The September4 full dry-run snapshot is identical between pre-fix and integrated
source. Timer remains active for September6 00:20MDT plus its unchanged delay;
that future run is not yet verified. No capture, runtime role grants, notification,
threshold or hardware changes were made. Release/rollback evidence is in
`docs/superpowers/plans/2026-09-05-analytics-corrective-release.md`.

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

### Alert release checkpoint, September 5

Reviewed UI freshness and external checker changes merged and pushed at
`d85f07cccf1390ccdaf3cd01633b78179d7c245f`. Branch verification included1,148UI
tests,727Python tests plus42subtests,5Home browser tests and build. Merged main
reverified1,148UI and14checker tests plus42subtests; runtime/test files matched
the fully reviewed branch exactly. UI tests-first deviation was explicitly
accepted by Sat (Hexmem8671); no retroactive TDD claim.

The checker is installed at `/home/sat/openhab/scripts/openhab_sanity_check.py`,
hash`0e796c07b9d828aab579c77bea9f4bbb9ca33ed617f2c029e1533d9180e866f4`,
permissions775 sat:sat. Paired original script/state and unchanged unit backups
are at `/home/sat/.local/state/openhab-sanity/release-20260905-br7IJC`.
Installation was atomic during an idle interval; state and units were unchanged.
The normal12:39:48MDT timer invocation exited0 and logged all checks passed.
No manual checker invocation or test notification was used. Rollback must retain
newer state/log evidence, then restore the paired original script/state while idle.

Live1340x800 UI validation confirmed requested REST lastStateUpdate fields,
two targeted stateupdated topics, fresh temperature timestamps, no overflow,
no page errors and no attempted writes. It also caught an actual BMS heartbeat
format gap: OpenHAB state uses compact offset`-0600`, rejected by the first parser.
Follow-up4fde6e0 supports that qualified format with genuine4-test RED and59focused/
1,156full GREEN plus build. Independent review found no issues. It was merged,
pushed and locally deployed at`b0064d91db4a281c99f2496c9f6a9d3a434c680c`, with
1,156tests passing again on merged main. Live1340x800 recheck accepted actual
heartbeat`2026-09-05T12:40:59.070-0600` with commsOK: the false battery freshness
warning was absent, normal thermal advisory was shown, and there were no page
errors, horizontal overflow or attempted writes. This completes the first
corrective UI/checker alert slice, not the broader historical-algorithm audit.

### Live rule history inventory, September 5

Read-only registry inspection scanned 25 live rules and found eight actions with
history-related text. The targeted analytical calls are:

- `hex_bms_ttd_smooth`: overnight AC-power `averageBetween`, from yesterday
  20:30 to today 06:00, cached per day with a numeric fallback. Script SHA-256
  `b5b80aa90ca0dbea4b03cd4c7b62eb73d2ee938d7df2b7940a21a29ba5d543a2`.
- `temp-highlow-24h`: `minimumSince`/`maximumSince` from now minus 24 hours,
  publishing the four `IndoorTemp_24h_*`/`OutdoorTemp_24h_*` Items. Script hash
  `a499269f5aabf7a82de55f9fbc168d7c281c3155d07d91321a2259199b7072db`.
- `hex_btc_24h_change`: `persistedState(now.minusHours(24))`. Script hash
  `9e15eb8e7f4e3d3118f12295d7b09f82525ab52f41b951f8809097c98fc369bb`.

These identify review targets, not proven defects or verified change-aware
behavior. Other matches include comments/guard terminology in the sky,
scaler and household-owner rules; keyword matching alone is not a full audit.
Main-page temperatures use `localDayHistoryRange` already. Weather still displays
the outdoor 24-hour Items, and Earthship's buffering metric explicitly compares
24-hour indoor/outdoor swings. Do not silently redefine those Item contracts as
local-day values. Carry-in, source health and persistence API aggregation
semantics remain to be verified for the three analytical consumers. No live
rule was invoked or changed during this inventory.

### UI boundary follow-up

Read-only REST requests plus the actual extrema helper reproduce missing
start-state carry in UI history: a September4 two-minute outdoor window yields
only65.3, while the prior state65.48 changes its historical maximum. The full-day
sample's extrema are not asserted wrong. Native boundary=true is not a safe
global fix: OpenHAB also moves the first post-window value back to the end and
relabels the carry timestamp. UI repair must explicitly discard look-ahead,
separate historical carry from freshness evidence, and handle local-day rollover.
The preflight records exact ranges/results and version-matched source. Category-
axis sparkline spacing and midnight-array retention remain additional review
targets; no UI fix is claimed by this audit.

No hardware actions, advisory-policy changes, migrations, or production writes
were performed for this inventory. Design approval and cross-repository
contracts apply before implementation. Existing OpenHAB controls and Discover
BMS counters must remain unchanged. A future-data dependency is unfinished
work, not a passed check. The broad goal remains active.
