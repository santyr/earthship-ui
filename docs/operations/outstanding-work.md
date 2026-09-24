# Outstanding Earthship and OpenHAB work

Evidence inventory started 2026-09-05. This is a completion tracker, not an
implementation approval or a claim that historical tasks are finished.
Owner: Hex (the current assistant). Task 82 remains explicitly on hold and is
outside this Earthship workstream.

## Current checkpoint — September 24, 2026

September 24 full restore rehearsal: fresh recovery point
`full-restore-h2d2mt0w` passed exact 514-table isolated data fingerprints.
The first integrated rehearsal then restored roles/ACLs and all 514 tables,
and matched 75 config, 1,337 userdata, and two add-on files byte-for-byte.
It did **not** pass the integrated OpenHAB gate: a temporary REST-managed
Number-Item `UNDEF` probe lost its state endpoint during isolated boot, and
its DELETE cleanup failed. The parent removed all owned test containers and
volumes; production OpenHAB was not restarted. The probe now uses the
existing diagnostic Number Item in the disconnected clone, retries transient
REST reads and restores its original state. A new integrated run is required
to qualify component recovery and the forecast `UNDEF` path; that rerun is
recorded below.

The second full integrated run subsequently exited zero with report
`/home/sat/backups/earthship-energy/runtime-recovery-1ml519on/recovery-report.json`:
514/514 tables, owners/ACLs, 75 config files, 1,337 userdata files and two
add-ons verified; disconnected OpenHAB restored JDBC, observational state,
431 Items, 84 Things, 36 Rules and 263 Links, and the existing diagnostic
Number Item completed an `UNDEF`/numeric round-trip with state restored.
All owned test containers/volumes were removed and the production PID was
unchanged. Four Thing channel differences are host-dependent System Info
labels/descriptions or TP-Link default tags; three uninitialized clone Rules
are the intentionally retired legacy schedules. The test is a qualified
component restore, **not** an atomic whole-host/off-host recovery or hardware
validation; those gates remain open.

The [EFC display clarification](2026-09-23-energy-efc-display.md) now keeps
qualified observed-window EFC on the Energy card with its date range and shows
the preserved 9.809 pre-cutover estimate separately and explicitly dated in
Details for the same bank epoch. The figures are not added. The modal now
displays qualified daily discharge and concise pending states instead of rows
of unsupported numbers; Lenovo layout tests pass. Qualified, atomic-BMS
high-SoC exposure is now shown as observed hours over the selected window,
with complete-day and per-day coverage gates; the September 23 17:10 publisher
readback verified both values. Source-side winter, SoH, curtailment and AC-load
qualification remain unfinished.

The forecast-intelligence SoC path still used change-only `BMS_SOC` rows for
overnight minima and included the current incomplete 20:00–11:00 night in its
morning trailing-drop sample. An opt-in `FORECAST_QUALIFIED_SOC_ENABLED=1`
path now reads current atomic evidence and only completed, coverage-qualified
nights; unavailable current evidence clears the three energy predictions to
`UNDEF` and suppresses the trough DM, while thermal output continues. Source
tests pass. On September 24 the exact tested source and helper were installed
with matching SHA-256 digests and a private prior-source rollback copy at
`/home/sat/backups/earthship-energy/forecast-soc-x9cjbG`. The installed path's
read-only check returned a currently valid atomic SoC and four qualified
completed nights. At that checkpoint, the service was idle and the enable
flag was absent, so a natural run would still have used the old algorithm.
Do not infer freshness from unchanged numeric persistence or code tests alone.

After the successful second rehearsal, a fresh read-only preflight found
current atomic SoC valid and four qualified completed nights (September 20–23).
The exact drop-in is now installed at
`/home/sat/.config/systemd/user/forecast-intel.service.d/qualified-soc.conf`;
user-manager readback confirms `FORECAST_QUALIFIED_SOC_ENABLED=1` and the
unchanged natural September 24 06:40 MDT timer. The service was idle and was
not manually run. Check that next natural publication, output Items and DM
behavior before claiming live algorithm qualification. Removing this one
drop-in and reloading the user manager is the config rollback; the private
pre-cutover script backup remains available separately.

The offline historical forecast backfill also treated the minimum of sparse
change-only `BMS_SOC` rows as a measured trough. Its source now uses the same
completed-night, bank-epoch and coverage-qualified atomic assessment in bounded
four-night batches; pre-epoch, incomplete and unavailable nights export blank,
not a fabricated minimum. The existing July 22 backfill CSV is retained as a
historical artifact and its trough column is **not** a qualified training
target; the live forecast only reads that CSV's temperature columns for seed
biases. A fresh export must be generated before using historical troughs for
training. The backfill deployment itself did not enable the separate live
forecast opt-in flag. Commit `9381e84` passed 73 focused tests and is pushed to
`origin/main`; the exact source was installed at
`/home/sat/openhab/scripts/forecast_backfill.py` with matching SHA-256
`7b93eb485d5581f6cdaba841838f6f490636af2c1d2de32067d53513d93d5b37`.
The previous installed script is recoverable under
`/home/sat/backups/earthship-energy/forecast-backfill-Ak5IYJ`. No backfill
export or live forecast run was triggered by this deployment.

An evening Energy forecast audit found the daily PV selector could show
yesterday's value after local midnight (`valid_for >=` admitted a row ending
exactly at midnight). The exact-next-Denver-midnight fix passed 850 analytics
tests, eliminated 21 wrong-day selections in a 169-origin read-only replay,
and was pushed to Solar_PV `5516c6d`. Earthship UI `b44312c` labels the field
“Today's PV forecast”; six Energy browser checks passed. The natural 18:35
publisher run and restarted UI both passed live readback. This fixes day
selection, not winter/SoH/curtailment or AC qualification.
The historical feature export had the same end-exclusive day error in a
different join: a live as-of example selected the previous day's 5.9 kWh
instead of today's 3.3 kWh. Solar_PV `fde6ab0` now uses the exact next local
midnight while preserving issue/capture as-of guards; 850 analytics tests
pass. A seven-day hourly replay found 169/169 old target-day mismatches and
112 numeric differences. No scheduled feature consumer was found, and older
explicit exports must be regenerated before using their daily-PV-forecast
field.

The unlinked observational `Thermal_Model_JSON` Item is now file-owned after
isolated OpenHAB/JDBC restore and live managed rollback/return qualification.
Its state, stable JDBC mapping/history and shadow timer were preserved. The
first natural post-transfer publication at 17:51 MDT wrote a new file-owned
Item state and JDBC row 231 under unchanged Item ID 610; the row equals the
live state and its private forcing capture verifies exactly. See the
[thermal Item cutover receipt](2026-09-23-thermal-item-file-cutover.md).

The next [strict forcing-capture score](2026-09-23-thermal-forcing-capture-live.md)
has five matured non-overlapping one-hour pairs for the current revision:
model MAE 1.8656°F versus persistence 0.6480°F. Two overlapping six-hour
targets missed low by about 6.53°F and fell outside their published intervals;
the paired persistence errors were 3.42°F and 2.88°F. No capture-qualified
24-hour target is mature. These are
diagnostics for historical/physical-model tuning, not grounds to leave shadow.
The subsequent 21:37 MDT strict rescore has six non-overlapping one-hour
pairs (model 1.731°F versus persistence 0.660°F), three overlapping six-hour
pairs (model 5.9513°F versus persistence 2.3400°F), and no due captured
24-hour target. The model remains worse than persistence on these diagnostics.
An [exact-forcing bias sensitivity check](2026-09-23-thermal-bias-sensitivity.md)
later reproduced four v4 captured publications in memory. Reducing the
negative air-bias coefficient improved a few short-horizon misses, but the
errors remained low and some variants changed the selected schedule. No live
artifact, threshold or advice was changed; this is not a fitted candidate.
At 22:17 MDT a further strict read-only rescore added one overlapping
six-hour target: four six-hour pairs now show model MAE 5.4265°F versus
persistence 2.2500°F, with only one non-overlapping pair and no due 24-hour
target. The model remains in shadow; see the
[forcing-capture score](2026-09-23-thermal-forcing-capture-live.md).
At 23:05 MDT, one further independent captured one-hour target brought the
strict model/persistence MAEs to 1.6211°F/0.6429°F across seven pairs; the
four overlapping six-hour scores and absence of due captured 24-hour targets
were unchanged. No threshold, artifact or advice changed.
At September 24 02:57 MDT, a read-only capture-strict rescore found eight
non-overlapping one-hour pairs from revision `c87551f92f02`: model MAE
1.5445°F versus same-origin persistence 0.6075°F, with negative model bias
and broad 10.4139°F intervals. Six overlapping six-hour pairs had model MAE
4.7023°F versus persistence 2.43°F; only two were non-overlapping (4.9995°F
versus 3.15°F). Both horizons still argue against shadow exit. No model,
threshold, advice or action authority was changed. The strict 24-hour audit
found all ten queried publication targets not yet due and scored none.
The new bounded, read-only
[operational-origin census](2026-09-23-thermal-historical-blend-audit.md)
paired 11/12 six-hourly origins with 24-hour qualified indoor outcomes and
origin-captured forecasts; same-origin persistence MAE was 2.0782°F. All
eleven paired origins had as-of mode knowledge, but none had a complete action
snapshot (`indoor_shade` and `vent` were missing). This is a historical
baseline and a concrete qualification gap, not a scored physical model or
evidence to graduate it from shadow.

The [AC writer/publisher preactivation receipt](2026-09-23-ac-writer-publisher-preactivation.md)
records a default-off daily command and opt-in v4 publisher path pushed to
Solar_PV, with 838 analytics tests passing. The live service still emits v3.
An 828-row AC stream audit has one startup barrier and no sequence gaps, but
not full-day or fault/restart evidence. The operator subsequently approved
the four exact-scope restricted-role grants for the new table, identity
sequence and `item0653`; they are now applied and independently read back.
The AC table remains empty and no writer or v4 publisher was activated. A
restricted-reader diagnostic later found one additional missing privilege:
`energy_power_reader` cannot SELECT the exact raw evidence table `public.item0653`.
That separate grant is requested, not applied; source reading remains withheld.

The first natural thermal shadow run after the installed-v4 confirmation-CLI
hardening succeeded at 15:51 MDT. Its verified private forcing archive exactly
matched the live shadow Item and the timer rescheduled. The result remained
low-confidence shadow with no candidate. This closes a runtime regression
check, not the accuracy or action-outcome gates for leaving shadow mode; see
the [backport receipt](2026-09-23-thermal-journal-cli-backport.md).

The [read-first AC UI v4 contract](ac-load-ui-v4.md) is now implemented and
tested without activating an AC publisher. It accepts a distinct observed
inverter-output day with coverage, revision, cutover and topology provenance,
while keeping the existing v3 load and DC/AC balance fields withheld. The
first complete AC day is not due until September25 06:00Z. Long-run,
fault/restart and retention evidence and explicit v4 publication activation
are still required; the approved table/writer grants are complete but the
reader's raw-source SELECT gate remains open.

The [AC-day revision schema](2026-09-23-ac-day-revision-schema.md) is now live
and empty after a backed-up, isolated-test-qualified additive migration. The
matching Solar_PV v4 payload validator, selected-revision reader and source-only
projector are also pushed, with 829 analytics tests passing. Append-only AC
storage is ready but has no scheduled writer or publisher; the remaining
runtime and first-complete-day gates above still apply.

September23 live follow-up: the existing qualified daily power job naturally
materialized September20,21,22; the UI publication reports three present days,
zero missing days, and latest PV/battery coverage above99.98%. Daily high/low
temperature learning naturally scored complete qualified coverage on September22
and23; hourly qualified targets scored24/24 on both days. The first day-3 target
is September24 and its assessment is not due until September25. Completed trough
assessment logged one and then two samples; this is still insufficient to claim
bandit reward attribution or tune advisory thresholds. The September23
[hourly-learning audit](2026-09-23-hourly-temperature-learning-audit.md)
verified 55 natural qualified target updates against the pre-cutover model:
all 24 per-hour count deltas match their receipts, and a read-only replay
reproduces every live bucket. The pre-update correction rule slightly improved
all-target MAE but worsened MAE for the 32 measured temperatures at or above
60°F; five sub-50°F targets are insufficient to tune the cool regime. No
learned state or forecast publication was changed by that audit. The September23
[isolated persistence rehearsal](2026-09-20-persistence-provider-qualification.md)
passed with four explicitly unpersisted provider-gap updates. Its final combined
run also passed future forecast-series replacement, nonmember exclusion, and
independently written power-history restoration after a full JVM restart. The
production gap accounting/rollback procedure and live transfer subsequently
completed as described below. The Bitcoin feed was restored
after a Java-upgrade spawn failure and disabled Thing; see the
[incident receipt](2026-09-10-bitcoin-feed-validation.md). The v5 thermal candidate
was refused on 24-hour accuracy and was not promoted; see the
[qualification result](2026-09-20-thermal-v5-qualification.md).
Origin-time forecast inventory also exposed a real future-capture leak in
Solar-PV historical features:49 of97 sampled September22 origins selected a
snapshot captured after the origin. Solar-PV `64460be` now requires capture time
as well as issue time in the feature and replayed UI reads;758 analytics tests
pass. Thermal operational replay still needs scored outcomes and qualified
future action evidence. The Earthship source now includes bounded capture-safe
weather and action-journal readers with a same-origin qualified temperature
assembler; a live read-only 24-hour assembly passed for September23 14:45Z.
Its action snapshot knows Kiva and outdoor shade, but lacks vent and indoor-shade
history and is not an outcome confirmation. This remains an input prerequisite,
not a scored operational replay or shadow exit.
The [capture-safe 24-hour origin census](2026-09-23-thermal-origin-census.md)
subsequently found63/63 hourly origins with full as-of inputs and qualified
indoor outcomes; naive persistence MAE was2.0314°F on overlapping warm-season
samples. No physical model score or action-benefit claim follows from this.
The repeatable [operational baseline audit](2026-09-23-thermal-operational-baseline.md)
subsequently paired all 63 origins with qualified later outcomes and reproduced
that overlapping MAE; greedy disjoint 24-hour windows left only three pairs
(MAE 1.32°F). No model or action benefit was scored, so shadow exit remains open.
The first two natural forcing-captured one-hour thermal targets matured later
September 23. Their strict [paired score](2026-09-23-thermal-forcing-capture-live.md)
is model MAE2.171°F versus same-origin persistence1.080°F; both outputs are
low confidence. The 24-hour targets remain unscored. This strengthens the
current no-graduation decision without identifying a causal weather or
physical-model correction.
An [audit of actual persisted shadow publications](2026-09-23-thermal-shadow-publication-score.md)
subsequently scored31 matured near24-hour targets against qualified indoor
receipts: model MAE2.4565°F, same-origin persistence MAE2.0265°F, interval
coverage87.1%. All outputs were low-confidence, spanning three revisions.
The current published model has not earned shadow exit.
The September23 [non-overlap audit](2026-09-23-thermal-nonoverlap-score.md)
now distinguishes33 overlapping 24-hour pairs from only three selected
disjoint forecast windows; those windows still favor same-origin persistence
(MAE1.5600°F versus model2.5417°F) and span three revisions. The two strict
captured one-hour pairs remain worse than persistence. No graduation follows.
The September 23 configured Nostr keyer self-check passed for signing and local
encryption/decryption with zero publication and journal writes. This clears a
thermal confirmation transport prerequisite, not operator reply collection;
the private collector policy, reviewed routes and genuine action reports remain
absent from the checked host locations. See
[the delivery runbook](thermal-messaging-delivery.md).
The real-nak loopback delivery qualification subsequently passed all eight
checks with disposable identities and no household delivery or journal write.
The existing Hex DM recipient was approved as the sole thermal-confirmation
operator and its public key matched the OpenHAB notifier configuration. Neither
that operator nor the configured Hex identity had a signed kind-10050 inbox
announcement returned by read-only queries to the notifier's three relays.
The collector therefore remains disabled pending reviewed signed routes,
private policy, real journal/backup qualification, and an attended trial.
Hex's collector kind-10050 route was later signed and remains readable;
the approved operator's signed route was still absent on all three queried
relays at 22:37 MDT. Existing Hex-to-operator encrypted DM events are
retrievable, but they neither supply the operator's signing key nor prove
receipt or action compliance. See the [delivery runbook](thermal-messaging-delivery.md).
The September 23 [forcing-capture activation](2026-09-23-thermal-forcing-capture-live.md)
now records exact raw Open-Meteo inputs alongside successful shadow
publications. Its first natural run exposed a sub-second provenance gap;
the decision timestamp was corrected and an attended publication produced a
verified private archive matching the live item. This is prospective input
evidence, not a 24-hour model score or shadow graduation. The new explicit
1-hour strict scorer paired that first captured publication with a qualified
target: model error1.541°F versus same-origin persistence0.540°F, with the
wide interval covering one point. The legacy publication remained excluded;
the same exact forcing overforecast outdoor temperature by5.12°F on its
qualified target. Both 24-hour targets were not yet due. This is one diagnostic,
not causal weather attribution or a release gate for graduating the model.

Later September23 checkpoint: the production JDBC persistence strategy was
transferred from managed to Git-owned file configuration. The exact file-owned
DTO and live independent power-evidence writes were verified; the inventory
now records the provider and reports no ownership issues. A 1.311231-second
provider-free window is explicitly unqualified. Event/history comparison found
three MPPT-derived changes inside that window without corresponding JDBC rows;
the independent power-evidence sequence remained contiguous. See the
[handoff receipt](2026-09-20-persistence-provider-qualification.md). Propagating
this known collection boundary into any future readers of automatic MPPT numeric
history remains a standing constraint. Current-consumer audit found the missing
MPPT output row, but the deployed qualified-power path uses independent
Power_Evidence_JSON intervals; AC load and its freshness companion persisted.
No thermal temperature or BMS SoC Item change appears in the OpenHAB event gap.
The natural Open-Meteo refresh at09:12MDT subsequently published48 hourly and
seven daily forecast-series values; JDBC served47 future hourly rows under the
file provider. The separate forecast-JSON timer then completed naturally at
09:16:06MDT: all three JSON forecast Items changed
and each new value had a JDBC history row. Both forecast publication paths are
verified under the file-owned provider.

The September 23 [full-day qualified-power audit](2026-09-23-power-full-day-persistence.md)
verified September 21–22 natural persistence: 101,058 strict-parser-valid rows,
one contiguous epoch, no sequence gaps/reversals or duplicate timestamps, and
a 52,640-row natural 25-hour window below the 60,000-row reader bound. This
closes full-day durability/volume for those two days, not physical source-fault,
restart/DST, AC-load or retention qualification.

The September 23 [SoC sanity release](2026-09-23-soc-sanity-atomic-freshness.md)
replaced heartbeat-only `fresh:bms` authority with validated atomic SoC
receipts. Sixteen focused tests, read-only live evaluation and guarded
one-file deployment passed; the first natural post-release sanity run at
12:56 MDT exited 0 with all checks passed. This fixes the checker's
source-validity gap without changing
OpenHAB control, persistence or notification cadence.
The UI's separate stale-SoC alert now uses that same atomic receipt instead
of the scaler heartbeat (`6ab6941`). Live receipt encoding was verified,
1,713 UI tests, the build and all 23 Home browser tests passed, and the UI
service was restarted and read back locally. An unchanged SoC remains healthy
only while fresh source evidence continues; advancing the scaler heartbeat
alone cannot clear the alert.

September23 AC-load scope clarification: the operator confirms all current
household load is inverter-served, without bypass or generator supplementation.
The Conext Gateway AC Power channel can be considered a candidate for current
household load only under that topology; it still lacks qualified acquisition
receipts, invalid/offline and restart evidence, so energy/balance publication
remains withheld. A bounded 65-second WebSocket probe then confirmed13
binding-sourced state events at roughly5.12-second intervals, but all values
changed; source-less updated events and absent native read-success channel
require a source-bound receipt design and unchanged-value/fault qualification.
See [AC-load qualification](2026-09-20-ac-load-qualification.md).
An additive file-owned AC-output observation Item and JS profile are now active
for non-authoritative collection. The timestamp is host transform time, not
device acquisition time. The isolated, networkless 5.2.1 file-provider check
passed and removed its disposable container. The bounded live trial verified
natural binding-sourced transformed events, canonical JDBC rows and exact
two-file withdrawal/restoration without altering the original inverter link;
the ownership inventory has zero issues. No consecutive unchanged-Watt receipt
was observed in the initial bounded window; later natural events supplied two
binding-sourced consecutive unchanged-Watt receipts with newer timestamps.
The observation currently adds about 15,840 JDBC rows/day at its measured
cadence, so retention/stream transition needs explicit follow-up. Fault and
full-restart behavior, durable qualified-source persistence, topology-epoch
controls and reader integration remain open;
AC-load energy publication is still withheld. See
[AC-load qualification](2026-09-20-ac-load-qualification.md).
The [independent AC evidence preflight](2026-09-23-inverter-ac-evidence-preflight.md)
adds a disabled, source-only producer and file-owned Item draft with 26
fail-closed tests. It preserves the existing three-field stream and labels
the new basis as inverter output. The subsequent persistence exclusion and
Solar-PV strict reader work is recorded below; fault/restart, production writer
and topology-period gates remained open at that preflight; the subsequent
activation is recorded below.
An isolated networkless OpenHAB 5.2.1 run subsequently loaded the file Item,
registered the exact triggers and executed the candidate rule body to an
unavailable evidence envelope. The disposable container was removed. Runtime
compilation/basic execution is now cleared; physical-source, fault, JDBC and
consumer gates remain open.
The [AC evidence JDBC exclusion](2026-09-23-ac-evidence-jdbc-exclusion.md)
subsequently passed disconnected provider/JDBC/explicit-writer/restart tests
and was hot-reloaded into the file-owned production strategy. Bounded live
readback found exact selectors, zero ownership issues, ten of ten AC observer
events persisted in the reload minute and no sequence gaps among 42 existing
power-evidence rows. At that checkpoint the AC evidence Item/rule remained
absent; the later activation is recorded below. Physical-source, fault, reader,
topology-period and actual production writer gates were still open then.
Solar-PV `24d2e89` subsequently added and published a separate strict AC
history reader. Its full analytics suite passed 763 tests. The reader is
source-only and requires an explicitly finite inverter-only topology period;
the operator's current no-bypass/no-generator statement is not backdated.
At that source-only checkpoint, production activation, natural durable
receipts, fault/restart behavior, topology period recording and daily/UI load
accounting remained open; the activation follows below.
The [September23 AC activation](2026-09-23-inverter-ac-evidence-activation.md)
subsequently installed the file-owned output Item and enabled the separate
observational rule. Natural Modbus-provenance receipts produced strict-parser-valid
immutable JDBC rows; the new reader also passed a bounded live diagnostic
read without publishing load. Fault/recovery, long-run durability, retention,
topology-period policy and daily/UI accounting remain open.
Solar-PV `e36e54f` subsequently added a strict, source-only AC activation
policy: complete finished Denver-local days only, resolved Item table, evidence
cutover and explicit topology period. Its full analytics suite passed 778
tests. No production load accounting is enabled. The operator subsequently
chose "valid until I report a topology change"; Solar-PV `2576222` records
the corresponding open-ended, non-backdated policy from the first durable AC
barrier at20:55:12.284Z. The earliest candidate full day is September24,
assessable only after September25 06:00Z.
Solar-PV `9b94a2a` subsequently added a source-only, read-only completed-day
AC load integration using both strict evidence readers and the explicit
topology gate. Simultaneous PV-DC and AC quantities remain separately labeled;
energy balance is withheld across those electrical domains. All 786 analytics
tests passed. Versioned storage, reader-first UI support and prospective
publication remain unfinished.

The [thermal confirmation CLI backport](2026-09-23-thermal-journal-cli-backport.md)
then installed only the tested future-plan and exact-readback guards into the
compatible live v4 CLI. The refused v5 model/runtime was not installed.
Authenticated operator transport and genuine action/outcome evidence remain
open; the next natural shadow run must still be checked.

The file-owned Current_US_AQI Item passed its first natural post-transfer
binding write at 12:51 MDT: value 37.708336→37.75463, exact OpenMeteo
channel source, and JDBC identity587 advanced by one matching changed-value
row. See the [cutover receipt](2026-09-23-openmeteo-aqi-item-cutover.md).
The separate `Forecast_AQI` Item/link is now file-owned after networkless
OpenHAB provider/rollback and isolated exact `REFRESH`-state/JDBC recovery
qualification. The attended cutover preserved the special state and two
older `REFRESH` JDBC rows under Item ID 582; the exact source and link are
noneditable and declared in the ownership inventory. The first natural
post-transfer hourly binding fetch at 18:51:28 MDT emitted both expected
48-value time-series events; the same fetch updated current AQI from its
binding channel. The Item/link remained file-owned, `REFRESH` and ONLINE,
JDBC ID 582/two older rows stayed unchanged, and the ownership inventory
had zero issues. This Item is not in `gForecast`, and its JDBC REST history
remains an incomplete view of the
two older SQL rows; no numeric AQI or forecast series was invented. See the
[cutover receipt](2026-09-23-openmeteo-forecast-aqi-item-cutover.md).

The next file-first weather candidate is the coupled managed
`Forecast_Temp`/`Forecast_Daily_High`/`Forecast_Daily_Low` group, not an
unlinked scalar. Read-only preflight found exact empty-config managed links
to the file-owned OpenMeteo forecast Thing, all three members of
`gForecast`, live temperature states, and JDBC Item IDs 563/564/568 with
710/40/40 rows respectively, including future hourly/daily series. The
18:51 MDT binding fetch naturally emitted 48/7/7-value time-series pairs.
Provider migration must preserve those future rows, scalar state recovery,
group membership and the unaffected forecast JSON consumers; it requires
an isolated JDBC/file reload and full-restart rehearsal before an attended
transfer. No live provider change was made in this preflight.
The exact three-line source is now prepared in
`openhab/file-config/items/openmeteo-forecast-temperature.items`. A
networkless restored-registry OpenHAB 5.2.1 run verified all three file-owned
Item/link DTOs on first boot and full restart, then withdrew the file and
restored the exact managed definitions. The owned disposable container was
removed and production was untouched. That provider-only rehearsal cleared
syntax and managed rollback. A separate disconnected OpenHAB/PostgreSQL run
has now passed with the host-equivalent US
measurement system: three synthetic temperature states persisted, then a
test-only Java bundle published 48 hourly and two seven-day future series.
All three scalar values and the exact JDBC history prefixes survived file
withdrawal/reload and a full JVM restart. Both owned disposable containers
were removed. The first two attempts exposed harness-only assumptions about
Fahrenheit-to-Celsius normalization and cleanup/timeout helper signatures;
the completed run retested the entire path. This establishes isolated
recovery, not production permission to transfer without fresh live
preflight, private rollback material and a natural 48/7/7 writer check.

An attended live transfer on 2026-09-23 at 19:20 MDT stopped at the scalar
state guard and rolled the exact three managed Items and links back; all
710/40/40 preexisting JDBC rows under IDs 563/564/568 were retained, and
the production file Item definition was withdrawn. The high/low scalar
states did not return to their pre-transfer values: OpenHAB restored the
latest past JDBC forecast-series values (68.3473982/53.3173982 °F) instead
of the earlier binding scalar states (68.2574/54.3974 °F). A bounded scan of
all 36 live rule bodies found no consumer of these three Item names. The
private recovery backup is under
`/home/sat/.local/state/openhab-config-migration/forecast-temperature-20260924T012005Z`.
The transfer guard now accepts only the exact pre-transfer value or the
latest past JDBC value as provisional. The isolated qualifier passed that
second restore path and removed both disposable containers. A second live
attempt briefly saw absent older JDBC rows while the replacement time series
was being written; the guarded rollback restored the managed definitions and
an independent SQL comparison found all 790 original rows again. The guard
now requires four stable history-preservation reads after asynchronous JDBC
settling. At 19:32 MDT a third attended transfer reached file ownership with
exact pre-transfer state readback and all prior rows under IDs 563/564/568.
The first scheduled binding fetch after transfer at 19:51:29 MDT emitted a
new 48/7/7 series under the exact file-owned Items and links. The forecast
Thing stayed ONLINE, the ownership inventory reported zero issues, JDBC
IDs remained 563/564/568, and all 790 pre-transfer rows were still present;
`Forecast_Temp` gained one row. The two high/low scalar states did not change
on this natural series fetch, so the persisted-value restoration is a known
scalar-state semantic difference from the pre-transfer snapshot, not evidence
of a fresh scalar update. No live rule or UI direct consumer uses those two
scalars; the UI uses the separately verified daily forecast JSON. File-provider
and time-series writer cutover is verified, without claiming scalar freshness.

The next observational OpenMeteo candidate is the coupled hourly
`Forecast_Cloudiness`/`Forecast_Radiation`/`Forecast_PrecipProb` group. Read-only
preflight found three managed `gForecast` Items, one empty-config managed link
each to the file-owned forecast Thing, JDBC IDs 565/566/567 with 711 rows each,
and natural 48-value series events at 19:51 MDT. Their states are 1,
0 W/m² and 0.16 respectively; no registered live rule body directly names
these Items. The exact source is prepared in
`openhab/file-config/items/openmeteo-forecast-meteorology.items`. A disposable
networkless restored-registry OpenHAB 5.2.1 run verified the three exact
file-owned Item/link definitions on first boot and full restart, then removed
the file and restored the original managed definitions. Its owned container
was removed; production remained managed with a clean ownership inventory at
that checkpoint. A second disconnected OpenHAB/PostgreSQL rehearsal then
persisted all three synthetic scalar states and 48/48/48 future-series values,
preserved them through hot reload and full restart, and exercised latest-past
JDBC state restoration. Both owned containers were removed. At 20:07 MDT an
attended live transfer placed all three Items/links under the exact file
source. Private backup
`/home/sat/.local/state/openhab-config-migration/forecast-temperature-20260924T020713Z`
contains the original managed definitions and 2,133 JDBC rows; the backup
prefix is historical from the shared adapter and does not imply temperature
content. Readback found file ownership, unchanged source hash, original scalar
states at the transfer (1, 0 W/m², 0.17), IDs 565/566/567 and all 711 rows
each preserved after JDBC settling. The ownership inventory has zero issues.
At the transfer checkpoint this remained provisional pending a scheduled
natural 48/48/48 binding update and historical-row preservation; the
reload-generated series did not satisfy that gate.

The 20:51:31 MDT scheduled binding fetch subsequently emitted all three
48-value series through the file-owned Items and links. JDBC IDs 565/566/567
retained every pre-transfer timestamp and all values at or before cutover;
each table grew from 711 to 712 rows. Cloudiness revised 13 future values and
radiation revised 22 future values at existing timestamps, with no timestamp
lost; precipitation probability had no revised values. The forecast Thing
remained ONLINE and the live ownership inventory had zero issues. The six
Item/link declarations are now verified, not a claim that every old future
forecast value remains immutable after a natural forecast revision.

The remaining four bound OpenMeteo daily series are
`Forecast_Daily_PrecipSum`, `Forecast_Daily_PrecipProbMax`,
`Forecast_Daily_WeatherCode` and `Forecast_Daily_UVIndex`. Read-only preflight
found one empty-config managed link each, JDBC IDs 569–572 with 40 rows each,
and the exact Item types/units/labels. The prepared
`openmeteo-forecast-daily.items` source passed a networkless restored-registry
OpenHAB 5.2.1 first-boot, full-restart and managed-rollback rehearsal. The
owned container was removed and production remains managed for these four.
Their mixed-unit JDBC recovery and future daily-series preservation still need
isolated qualification before any live transfer; no daily-group cutover was
attempted.

A separate disconnected OpenHAB/PostgreSQL rehearsal subsequently persisted
four synthetic scalar states and seven future values per daily Item. It passed
exact JDBC series checks, hot file reload, full JVM restart and latest-past
JDBC state restoration; a separate pure guard checks inch/millimeter conversion
for precipitation.
Both disposable containers were removed and production remains managed. The
next gate is an attended transfer with exact private backup and rollback;
neither a synthetic production update nor a live cutover has occurred.
The guarded four-Item transfer adapter now passes its pure unit tests and a
fresh live `--check`: managed definitions/links, ONLINE Thing, fixed source
digest, JDBC IDs 569–572 and 40 rows each match. At that checkpoint its
`--apply` had not run because the earlier hourly meteorology group still
needed a natural binding update.

After that hourly gate passed, a fresh daily `--check` passed and the attended
daily `--apply` at 20:53 MDT privately backed up the managed definitions,
links and 160 JDBC rows under
`/home/sat/.local/state/openhab-config-migration/forecast-daily-20260924T025355Z`.
All four exact Item/link pairs are now file-owned from the prepared source
(SHA-256 `9f1236706f3e33748e9a6069ce01fe44dfebc111d699bbaa6c34f4f77f957fea`),
and the original 40 rows per JDBC ID 569–572 survived the transfer. As in the
isolated rehearsal, precipitation sum, probability maximum and weather-code
scalar states restored to their latest past JDBC values instead of the
pre-transfer binding states; UV index stayed 2.9. This was provisional until
the next scheduled natural seven-value series update under file ownership
and post-update historical-row/ownership checks. The reload-generated events
did not satisfy that gate.

The 21:51:32 MDT natural binding fetch emitted seven-value series for all four
file-owned daily Items. Their exact links remained file-owned, the forecast
Thing ONLINE, all ten `gForecast` member references intact, JDBC IDs 569–572
unchanged, and the ownership inventory clean. Each table still had 40 target
timestamps and none disappeared. All 33 rows per Item with target dates before
the current seven-day forecast's first timestamp (2026-09-24 00:00Z) retained
their exact earlier values. The binding legitimately revised the active
forecast at that first timestamp for precipitation sum, probability maximum
and weather code, plus six later probability values; UV values were unchanged.
The first timestamp was already earlier than the transfer clock but remained
part of the current, mutable seven-day forecast. The gate is therefore met for
natural writer and prior-day history preservation, not immutable preservation
of active forecast values. All eight daily Item/link declarations are verified.

The `gForecast` Group itself remains REST-managed and has no JDBC Item
identity; its ten members are the forecast persistence selector. The prepared
`forecast-group.items` source passed a restored-registry, networkless OpenHAB
5.2.1 rehearsal: all ten member references and exact file Group fields matched
on first boot and full restart, then the file was withdrawn and the managed
Group plus references restored. The owned container was removed. Production
Group ownership was untouched; at that stage a live transfer and
persistence-selector continuity check had to wait for the daily member group.
An added live-like isolated test revealed that REST-deleting the managed Group
removes all ten member references. Reloading the file Group produced a valid
file-owned Group with **zero** members after the bounded wait; the owned
container was removed and production was untouched. A simple hot provider
handoff would therefore silently break the `gForecast*` JDBC selector and is
refused. The exact current Group definition is now inventoried as a managed
exception in `managed-exceptions/gForecast.json`; the prepared `.items` source
is inactive. Any future file transfer needs a separately qualified
restart/registry migration that preserves all ten references atomically, plus
history and natural-writer checks. Do not REST-delete this live Group merely
because the member Items have become file-owned.

An additional networkless, restored-registry rehearsal now covers the exact
stopped-service alternative. `scripts/qualify-forecast-group-offline.py`
started the managed Group with all ten members, stopped isolated OpenHAB,
removed only the Group's JSONDB record, installed the prepared file source,
and verified file ownership plus all ten member references after start and
full restart. A second stopped-service edit restored the managed record and
withdrawn source; rollback also preserved all ten references. The owned
container and private temporary directory were removed, and the live Group
remains managed with ten members. This qualifies the provider/membership
handoff in isolation, not live maintenance, JDBC continuity or a natural
writer after cutover. The daily Items' natural series gate has since passed;
the live restart decision remains separate.

The same networkless Group rehearsal now also passes with an intentional
SIGKILL before both offline JSONDB edits: file ownership, all ten memberships,
full restart and managed rollback remained exact. Its owned container and
private temporary directory were removed. This narrows file-provider recovery
risk from the last production stop's forced-kill behavior, but does not qualify
protected hardware controls across another live OpenHAB restart.
Read-only maintenance risk check at 21:42 MDT: systemd shows production
OpenHAB was stopped at 07:09 MDT on September23, reached its two-minute
`TimeoutStopSec`, was SIGKILLed, and restarted at 07:11 MDT. It is now active;
the SouthOutlet controller and four inspected BMS/Schneider safety rules report
IDLE/NONE. Both greywater pump outputs are OFF, the controller reports
`after_dark`, and `SouthOutlet_LastCycle` records a later 18:43 MDT cycle.
These current-state and later-operation observations show recovery of the
inspected rule path, not safe behavior throughout the restart or all protected
controls. An attended live Group restart remains a separate decision.
The 22:23 MDT read-only shutdown review found the September23 07:09:24
stop's Equinox framework thread waiting in Jetty `ManagedSelector.doStop` /
`CountDownLatch.await` at 07:09:55; systemd killed the JVM at 07:11:25 under
the configured 120-second stop timeout. The old JVM also logged repeated
`jspawnhelper` version mismatches shortly before the stop (running Java
21.0.12 versus installed helper 21.0.12.1). The service restarted afterward;
the installed Java is now 21.0.12.1 and it has emitted no further mismatch
messages, but that does **not** prove the Jetty stop wait is fixed or another
restart is safe. Both pump outputs were OFF at this read-only check. No service
restart, timeout change or Group transfer was attempted.
A later networkless rehearsal tested the *current* topology: managed
`gForecast` with all ten members loaded from their three file-owned Item
sources. Unlike the earlier managed-member live-like test, REST deletion of
the Group left all ten file-owned member references intact. File Group load,
member-file reload, an isolated full restart, file withdrawal and managed
rollback all retained exactly ten references. The first exploratory run had
an incorrect zero-member expectation; the second exposed a tmpfs test-auth
header lost on restart. After correcting both harness issues, the final
forward/restart/rollback run passed and its container was removed. This
topology-specific result may permit a hot Group handoff without a production
restart, but does **not** yet prove JDBC selector continuity or safe event-gap
behavior. Production `gForecast` remains managed; an isolated JDBC/event-gap
rehearsal and a guarded live rollback are still required before transfer.
The subsequent [disconnected PostgreSQL rehearsal](2026-09-23-forecast-group-hot-jdbc-gap.md)
closed that question negatively: synthetic 48/7/7 forecast series persisted
before the handoff, after file Group load and after managed rollback, but all
three series posted while the Group provider was absent were missing from JDBC
and did not backfill. Membership readback alone was not a persistence contract.
The restart-free Group handoff is therefore **refused**; do not run it live.
The stopped-service path remains staged but requires its separate attended
restart decision and protected-control safety gate.
A fresh read-only Group `--check` in the same pass still found exactly ten
members, JDBC IDs 563–572 and the verified daily natural-writer gate.

The guarded `scripts/migrate-forecast-group-offline.py` adapter is now staged
for that later attended maintenance. Its read-only `--check` verifies the
exact managed Group, ten file-owned members/links, ONLINE forecast Thing,
fixed file-source digest and JDBC identities 563–572. Before the daily natural
fetch, `--check` reported that gate pending and `--apply` refused it. With the
daily gate verified, a fresh `--check` is required before any attended apply.
If approved and otherwise eligible, the adapter stops OpenHAB, takes a private
backup of the exact JSONDB, removes only the stopped Group record, installs the
file definition, restarts, and verifies Group membership and historical JDBC
rows. A failed handoff attempts a stopped-service return to the original managed
record, and removes only the pinned file source. The apply path also refuses to
stop
OpenHAB unless both greywater pump output Items are explicitly OFF, with a
second check immediately before the stop. Nine focused tests pass, including
the no-service-stop, pump-state and unrelated-JSONDB-preserving rollback
guards. The adapter has not yet been executed against production; the natural
Group writer and rollback gates remain live obligations.

### Explicit active goal: graduate the thermal model from shadow

Operator reaffirmed that Hex must perform the requisite work, without rushing
or forgetting it. Hexmem task99 and the [graduation workstream](thermal-model-graduation.md)
track historical tuning, confirmed action/outcome evidence, numerical acceptance
criteria, advisory integration and verified deployment. Model fitting and shadow
publication alone do not close this goal; automatic actuation is separate.

The [baseline audit](2026-09-20-thermal-graduation-baseline.md) now quantifies
forecast errors and interval undercoverage. Historical evaluation blends toward
persistence but the publication path does not; output-contract parity is the
next prerequisite before tuning. Source-only v5/v3 parity repair now scores raw
predictions and rejects legacy blended evidence. Production retains its prior
runtime/model pair pending separate candidate qualification; do not deploy the
new runtime alone. No advisory graduation occurred.

Latest UI follow-up: `051ed57` restores outdoor chart forecasts from corrected
hourly JSON rather than absent future `Forecast_Temp` persistence; indoor charts
use validated thermal trajectories explicitly labeled shadow model. Current-day
temperature high/low summaries and shared selected-period extrema are rendered.
Shared nighttime weather icons use timestamped day/night flags and moon phases.
Live Home/Weather and both temperature modals passed browser checks; 1,625 UI
tests,64 producer tests and build passed. The temporary missing-import UI failure
was corrected. This does not promote the shadow thermal model to control authority.

Full OpenHAB recovery follow-up is now recorded in the
[integrated recovery receipt](2026-09-20-openhab-recovery-rehearsal.md): database,
durable configuration/userdata and isolated runtime boot were verified. Earlier
unqualified-full-restore statements below are historical, not the current result.
Whole-host/off-host and protected-control restart qualification remain open.

The four display-only rolling temperature extrema Items are now file-owned;
same-unit state restoration, historical-prefix preservation and actual provider
rollback passed. See [migration receipt](2026-09-20-temperature-extrema-migration.md).
Natural17:30scheduled writer confirmation passed for both indoor and outdoor
calculations; this batch's post-transfer checks are complete.

September 23 21:12 MDT read-only next-candidate inventory: the live
`BTC_USD_Price` Number Item and its empty-config Exec output link remain
managed, with JDBC Item ID34 and 1,089,881 rows (about70 MB) since May2025.
The binding naturally changes the price about every30seconds; the already
file-owned percentage-change Item is a separate member of the managed
`BTC_Price` Group. That Group also has semantic `Equipment` metadata. A price
Item migration therefore needs a bounded/streaming history-preservation
check, exact link/provider and writer verification, and separate Group metadata
and membership handling. No Bitcoin provider or feed setting changed in this
inventory; do not reuse a small-forecast Item adapter that loads all history
into memory.
The prepared `openhab/file-config/items/bitcoin-price.items` source now uses
the explicit label “Bitcoin Price” with a whole-dollar state format; the
managed label-only `[%.0f ]` string parsed as an empty label in an isolated
`.items` provider and could not be transferred as-is. A networkless restored-
registry rehearsal verified the exact Number Item, `BTC_Price` membership and
empty-config Exec link after first boot and full restart, then withdrew the
file and restored the original managed Item/link. Its owned container was
removed. This qualifies provider syntax and reversibility only; production
price Item/link/Group ownership, JDBC history and feed are unchanged. A
bounded history/restart qualification is still required before any live cutover.
The separate disconnected OpenHAB/PostgreSQL rehearsal then persisted one
synthetic numeric Bitcoin price, restored the same state and exact JDBC history
prefix after managed rollback, forward file transfer, hot reload and full JVM
restart. Both owned disposable containers and their test database were
removed. The first attempt exposed a harness-only string-versus-number JDBC
comparison; the completed rerun used numeric equivalence and exercised the
entire path. This is isolated recovery evidence, not a backup or verification
of the production Item34 history or the natural Exec writer under file
ownership. The live Bitcoin feed remains managed and unchanged.
A bounded-memory, read-only history verifier is now prepared at
`scripts/bitcoin-price-history-digest.py`. At the fixed exclusive cutoff
2026-09-24 03:12:00Z, it streamed 1,089,880 Item34 rows/39,452,387 CSV bytes
under one repeatable-read transaction and returned the same SHA-256 digest
`5b500b573644a48cac707461be15cce17b78882307e5bbd156a172c0e872208e`
on two runs while new prices continued arriving. The digest also matched an
independent `psql COPY | sha256sum` calculation. This provides a scalable
before/after preservation check, not a recoverable backup, a live migration or
natural writer qualification.
The read-only `scripts/preflight-bitcoin-price-item.py` now pins the prepared
source, managed price Item and empty-config output link, companion file-owned
receipt link's JS transform, ONLINE Exec Thing, two-member managed Group with
semantic metadata, and IDLE percentage-change rule triggered by price updates.
It also streams a fixed-time Item34 JDBC digest. A live check at 21:57 MDT
passed with 1,089,962 rows before its two-minute cutoff. The preflight
explicitly reports `file_transfer:not_qualified`; no price provider or feed
changed. A private recoverable backup, guarded live handoff, natural writer
and Group metadata handling remain required.
The staged `scripts/migrate-bitcoin-price-item.py` adds a read-only `--check`
and a release-gated `--apply` path. It prepares a private Item34 custom dump
and JSONDB/REST snapshots, removes an incomplete backup if preparation fails,
checks an unchanged fixed history prefix, and defines exact managed rollback
plus a fresh natural Exec receipt gate. `RELEASE_READY` remains false: this
adapter has **not** transferred the production Item/link. Twelve focused
tests pass, including refusal before mutation, backup-failure cleanup and
rollback. The 22:09 MDT live `--check` passed with Item34 and 1,089,985
historical rows. Before any live `--apply`, review the backup and rollback
path, verify recovery from the private archive, and keep the Group's managed
semantic metadata and two-member references intact.
The private production Item34 snapshot at
`/home/sat/.local/state/openhab-config-migration/bitcoin-price-20260924T041023Z`
was then restored into a networkless disposable PostgreSQL 16 container.
The restored fixed cutoff contained 1,089,986 rows and exactly matched its
saved SHA-256 prefix digest
`ef0f628b85404fd0ddb313a931a1fd346bae7558cee66d789ef4a437c9f5909d`.
The archive hash matched its private proof, and the disposable container was
removed. The private recovery archive was retained. This closes the actual
production-archive restore prerequisite, but not the live Item cutover.
The adapter now checks that the managed `BTC_Price` Group retains its semantic
`Equipment` metadata during provider readback; thirteen focused tests pass.
The live `RELEASE_READY` gate is still false. The environment's safety review
rejected enabling that gate without a specifically approved attended
production Item/link cutover plan; no alternate activation path was used.
The [exact attended plan](2026-09-24-bitcoin-price-item-cutover-plan.md) now
spells out scope, current backup, fixed-prefix/JDBC identity proof, natural
writer gate and guarded managed rollback. A fresh September 24 read-only
`--check` passed with 1,090,544 Item34 rows before its two-minute cutoff.
The plan is proposed, not yet specifically approved or executed; the release
gate and live price provider remain unchanged.

This section supersedes older deployment snapshots below; historical receipts
are retained as evidence, not current-state claims.

### Started: file-first configuration migration

The existing `/etc/openhab/transform/astro.map` now has an exact canonical
source at `openhab/transform/astro.map`. Source/live/archive SHA-256 matched
byte-for-byte, and a focused test covers all moon and night-phase keys. No
live transform was overwritten or reloaded. `SunPhaseIcon` and
`MoonPhaseicon` were still managed Items with their existing Astro MAP links
at that source-only stage; adopting the transform source did not silently
transfer those providers. Their exact file definitions were prepared in Git.
A disposable networkless
OpenHAB rehearsal verified both Item/link definitions on first boot and after
full restart, plus withdrawal and managed rollback; its container was removed.
The later [attended live transfer](2026-09-23-astro-icon-item-cutover.md)
verified file ownership and preserved JDBC identities/history. A natural Astro
update after transfer remains a separate gate.

September 23 OpenMeteo follow-up: the bridge, forecast Thing and air-quality
Thing were [transferred to the Git-owned file](2026-09-23-openmeteo-file-preflight.md)
after restore-based dynamic-channel, full-restart and live-like forward/reverse
provider rehearsals passed. All three are now online/file-owned with exact
1/38/12 channel sets, supported setting parity and 12 retained links. The
managed definitions were backed up privately and removed; the link JSONDB is
unchanged. The ownership inventory has 81 managed plus three file Things and
zero issues. Live events at 10:51:18 MDT also show file-provider startup
publication of 48 hourly and seven daily forecast values, 48 AQI forecast
values and an AQI Item update. A later scheduled refresh remains to be
observed; immediate JDBC readback had no new AQI receipt because the state
was unchanged and forecast rows use target timestamps.
Later at 11:51 MDT, a natural scheduled binding refresh updated both 48-hour
forecast series and changed Current_US_AQI; its new JDBC value row was read
back. After separate isolated Item/link and JDBC restore/restart qualification,
the [AQI observation Item and link were transferred](2026-09-23-openmeteo-aqi-item-cutover.md)
to a Git-owned file at 12:18 MDT. Exact state and 581-row history prefix were
preserved, both resources are non-managed, and the registry inventory reports
zero issues. The subsequent 12:51 natural binding update and matching JDBC row
closed this resource's publication gate.

September23 13:18 MDT: three direct-published forecast JSON Items were
[transferred to file ownership](2026-09-23-forecast-json-item-cutover.md) after
isolated provider, JDBC restore, managed rollback, hot reload and full restart
rehearsals. The actual live cutover also verified managed rollback and return
to file ownership, exact states and unchanged item580/581/588 histories. The
forecast timer is active; next natural file-provider publication remains to be
observed at about15:16 MDT. No synthetic production values were posted.
The 15:17 MDT natural publisher exited0, and each of the three file-owned Items
matched a new JDBC row under its unchanged identity. This resource's first
post-transfer publication check is complete; see the updated cutover receipt.

September20 operator instruction: change the OpenHAB configuration policy and
start migration after current tasks are finished. Execution order communicated:
finish the in-flight temperature-learning and power-evidence work, then replace
the REST-managed-only policy with Git-owned, file-first configuration and begin
staged migration. The host policy is now file-first and the first observational
Item, `Energy_Analytics_JSON`, was transferred to its Git-owned file definition
at 11:24 MDT. Persisted state restored before publication; JDBC identity/history,
protected rule definitions and the publisher schedule were preserved. A natural
11:25 publication and the 11:20 data-quality run succeeded. See the
[initial migration receipt](2026-09-20-file-first-initial-migration.md).
Read-only registry inventory at 13:59 MDT verifies 427 managed Items plus two file
Items, 84 managed Things, 35 managed rules and 261 managed plus one file link, with no detected
structural dependency/ownership discrepancies. The reproducible tool excludes
configuration values and states; this is not yet a full installation inventory
or restore export. See [remaining scope](2026-09-20-file-first-inventory.md).
The exact JDBC strategy file is now prepared and live-compared, but not deployed;
managed persistence stays authoritative pending provider/load/rollback validation.
Follow-up: isolated5.2.1 file-provider readback now matches the complete strategy
DTO with only editability changed. See [qualification](2026-09-20-persistence-provider-qualification.md).
Two isolated file/managed/file configuration rollback cycles now pass with
exact DTOs and absent-provider checks before each handoff. Actual isolated
PostgreSQL/JDBC writes preserve five history rows through both roundtrips;
Item recreation restores the latest value. Change-only suppression and power
exclusion now pass at every ownership checkpoint. Full isolated JVM stop/start
restores state and exact history with the same file-owned strategy. Forecast-group
and independent-power restore behavior and collection-boundary handling remain open; no live persistence
ownership change occurred.
Offline syntax qualification now passes using the actual installed OpenHAB 5.2.1
parser in a separate bounded JVM, including selector types and strategy tokens;
malformed syntax is rejected. This does not establish live strategy resolution,
provider transfer or rollback, which remain required.
Backup review found the August 20 full restore point stale and same-host.
The analytics-only rehearsal could not replace it; the full refresh below does.
A full-database snapshot/rehearsal completed at 18:59:53Z with all 510 tables
matching the source snapshot; the isolated target was removed. Independent
monitor assessment verifies freshness, readability and archive hash. The
[procedure and scope](2026-09-20-full-database-restore.md) distinguish data restore
from role/configuration recovery. The scheduled monitor now selects the new
verified archive (Solar_PV `6f5d914`); exact deployed unit readback and active
weekly timer verified, with no manual job or DM. Off-host recovery remains
deferred and Actionable.
September23 follow-up removed a vanished, session-local `apply_patch`
executable from the full OpenHAB recovery script and the analogous PATH-only
dependency from the full-database verifier. Both now create exclusive,
mode-0600 JSON receipts inside their owned mode-0700 private backup directory;
15 focused recovery/receipt tests and five subtests pass. This repairs the
rehearsal tooling but is **not** a new full backup, restore run or off-host
recovery proof.

Preserve stable resource IDs and exactly one configuration provider per resource.
Start with observational resources; qualify restore/restart/rollback before
migrating pumps, battery safety or other protected controls. Supported declarative
definitions and scripts belong in Git; managed exceptions require reproducible
exports. Credentials, userdata, PostgreSQL history and learned model artifacts
need appropriate encrypted backups rather than raw secret/data commits. A clean
restore rehearsal is a completion requirement. All other runtime ownership stays
unchanged until each resource's verified cutover. Full restart, actual rollback
rehearsal and protected-control migration remain outstanding. Task82 remains held.
Update: actual file-to-managed-to-file rollback is now verified for the single
observational analytics Item, including pre-publication state restoration on both
legs, unchanged history/mapping and unchanged control definitions. See the
[rollback receipt](2026-09-20-item-provider-rollback.md). Broader restore/restart
and protected-resource rollback remain outstanding.

### Operator-requested follow-up after current tasks

- Pump-cycling investigation removed at the operator's request: both pumps are
  running (operator confirmation September 20). Do not retain the earlier
  East-only concern as an outstanding fault. Hexmem task 98 now retains only
  the display work below.
- Completed: the main UI displays the controller-authored next pump and earliest
  eligible time, explicitly conditional on safety and sunlight. Live natural
  publication, tablet text containment, all 1,561 UI tests and build verified.
  See [next-pump display receipt](2026-09-20-greywater-next-display.md).

### Operational checkpoint

- Bitcoin receipt collection is deployed from `a6946ef`: file-owned observation
  Item/link, existing price link and polling unchanged, JDBC651/item0651 verified.
  A naturally unchanged price produced a distinct persisted receipt timestamp.
  These are local output receipts, not provider quote timestamps or execution IDs;
  a read-only Home warning now handles unknown/invalid/stale/mismatched receipts
  and unchanged-price recovery without extra polling. Failure/restart source
  qualification and historical coverage remain outstanding; UI status is not
  provider quote freshness or a control gate.
  See [deployment evidence](2026-09-10-bitcoin-feed-validation.md).
  The operator subsequently approved normalization; the percent-change Item is
  now file-owned with clean label and two-decimal percent format. JDBC139/history,
  original-definition rollback and natural writer recovery are verified. See
  [migration receipt](2026-09-20-bitcoin-item-migration-preflight.md).

- Qualified lifecycle throughput reporting is deployed in Solar_PV `819880a`:
  `report lifecycle --power-evidence-policy` selects only qualified revisions,
  preserves missing days and daily coverage, and reports period EFC rather than
  lifetime totals. All 733 analytics tests pass; restricted live reader verified
  empty evidence yields null totals without legacy substitution. Complete
  lifecycle temperature exposure, independent BMS comparison and winter load
  replay remain unqualified; no scheduled consumer was changed. High-SoC exposure
  was subsequently deployed in `af93fb1`, with atomic SoC evidence, independent
  coverage, unknown-versus-zero handling and no extrapolation. All 743 analytics
  tests passed. Follow-up `a4d402b` verifies 23/25-hour Denver DST exposure windows
  (27 targeted tests). September23 read-only restricted reporting now verifies
  naturally written September20–22 snapshots: observed period EFC0.434789,
  power coverage60.39% on the cutover day and above99.98% on both later
  completed days, with separate valid atomic-SoC exposure on all three days.
  This closes the first nonempty completed-day readback, not temperature
  exposure, independent BMS comparison or winter qualification. A September 23
  [counter preflight](2026-09-23-bms-counter-comparison-preflight.md) found both
  Discover counter Things ONLINE with unchanged Item updates each minute, while
  change-only JDBC has no new rows since July 18. Thus missing persistence is
  not sensor staleness; register/reset semantics and atomic receipt history
  are prerequisites to a same-bank EFC comparison.
  The official Schneider 990-6278A gateway map now confirms registers 110 and
  112 as unscaled charge-cycle and discharge-count fields, respectively. The
  LYNK II's emulation/reset semantics remain unverified, so neither count is
  treated as EFC; the Energy card labels register 110 more precisely.

- Qualified power feature export is now available in the deployed Solar_PV
  `1a013f3` via explicit `export-features --power-evidence-policy`. CSV v3 labels
  PV evidence/cutover and other-field limitations; PV and one-hour lag never
  bridge gaps, AC-load values remain empty. Legacy v2 is separate. Requests
  are bounded to 24 hours plus lag. All 728 analytics tests pass and a live
  read-only three-row export verified actual qualified PV and withheld load.
  No scheduler or training consumer was activated. Winter reporting and independent
  AC-load qualification remain outstanding; lifecycle progress is recorded above.

- Qualified monthly reporting is now deployed from Solar_PV `5fc878a` on the
  existing monthly timer with the restricted power reader. It writes a distinct
  `qualified-power-monthly.json`, preserves legacy reports and missing dates,
  and never substitutes legacy totals. All 706 analytics tests pass; a real
  restricted-reader report succeeds. No manual monthly job or DM was triggered.
  Private activation receipt: `/tmp/qualified-monthly-release-ik0qyach`.
  Next natural run is October 1 in the existing randomized morning window;
  its execution remains unverified. Later lifecycle/feature-export work is recorded
  above; this change only completes the monthly consumer path.
- Recurring 09:00/21:00 legacy-rule errors are diagnosed and their cause removed:
  two schedules still called three deliberately disabled child rules. Only those
  references were removed; live readback preserves schedules, OverrideSwitch and
  GoatCamOff actions, other definitions and disabled retirement. Four tests pass;
  natural next executions remain to be observed. See the
  [repair receipt](2026-09-20-retired-schedule-calls.md).
- Continuous observational power collection is now enabled with actual cutover
  `2026-09-20T15:18:58.261099Z`; all three new data Things ONLINE, observer ready,
  and every field verified from fresh post-cutover receipts. A180-second probe yielded105valid
  output rows, projected52,466rows/25h and26.95MiB/day combined JSON payload.
  Full-day storage/query checks remain; no control or published total changed.
  Binding-origin receipt validation, natural unchanged battery receipts,
  observer cache restart and exact120-second expiry clipping are verified.
  Initial disabled installation and bounded probes are historical stages, not
  the current enabled state. See the [installation and activation receipt](2026-09-20-power-disabled-installation.md).
  Physical-source faults and full-openHAB restart were not induced.

- Qualified power accounting is **enabled in production** since17:10:31.538073Z;
  Solar_PV main `d3361d1`,702analytics tests; UI1537tests/build pass. Restricted
  writer/publisher/monitor paths and a natural v3 publication are verified.
  The UI shows a truthful waiting state until the first daily write around
  September21 00:21MDT. See [activation receipt](2026-09-20-power-production-activation.md).
  The implementation chronology below is historical; this activation supersedes
  its earlier source-only, v2-only, pending-grants and pending-migration statements.
  Implemented: bounded evidence transport; battery/PV energy and EFC using exact
  qualified intervals; daily and solar-noon composition with matching source
  quality; common-support PV efficiency; explicit legacy/cutover provenance.
  Empty/error evidence never falls back to held numeric history. PV/load balance
  remains withheld until independent AC-load evidence is qualified.
  Migration0005 adds append-only daily revisions without rewriting legacy daily
  tables. Cumulative qualified EFC selects latest revisions within one bank,
  policy and cutover. The new read-only reader is bounded to366days/5-second SQL,
  validates identity/digest/completed windows, preserves missing dates and never
  resurrects an older better-quality result. Real PostgreSQL tests cover these
  semantics, immutable writes, retries, permissions and transaction locking.
  Strict opt-in policy and CLI/scheduler forwarding are now implemented;
  all660analytics tests pass. An end-to-end live read-only daily calculation
  succeeded, but revealed a new persistence release gate:155missing sequence
  publications paired with155duplicate following snapshots in a fixed1207-row
  window. Valid source values do not authorize bridging those missing records.
  Attribution is now localized after publication: event log sequences395/396/397
  correspond to JDBC395/397/397. Matching5.2.1JDBC code reads mutable Item state
  inside its queued task. A later27-event SSE/database sample was complete,
  confirming intermittency. The explicit immutable timestamp/state writer is now
  deployed, with only this Item excluded from automatic change persistence and
  restore preserved. Final millisecond-precision cutover16:22:52.592732Z passes
  exact event/database parity for46contiguous rows and the production reader;
  all1513UI/observer unit tests pass. Historical gaps remain unqualified;
  collection stays active; accounting was subsequently activated as noted above. See the
  [sequence-gap evidence](2026-09-20-power-persistence-sequence-gaps.md).
  An explicit `report power` consumer now reads the bounded qualified revision
  series and exports JSON/Markdown with policy/cutover/as-of and per-day revision
  provenance/coverage. Missing dates remain listed and empty totals remain null;
  observed-window EFC is not mixed with lifetime/legacy estimates. Real isolated
  PostgreSQL verifies latest lower-coverage correction selection. This additive
  report itself does not migrate the legacy consumers; subsequent monthly,
  lifecycle and UI releases are recorded separately.
  Reader-first UI v3 support now validates exact qualified provenance, completed
  revision windows, missing-day counts and coverage, and labels observed-window
  EFC separately from lifetime estimates. Served source and unchanged live v2
  payload compatibility were verified;1536unit tests and build passed at that
  stage. The producer is now v3. See [v3 reader contract](2026-09-20-qualified-energy-ui-contract.md).
  Matching source-only Python v3 validation/projection and explicit scheduled
  publisher policy routing are now implemented. Qualified mode bypasses legacy
  daily/quality tables; missing yesterday cannot borrow older healthy evidence.
  Actual Python partial/empty outputs pass the JavaScript parser. Publisher
  activation and writer qualification were subsequently completed below.
  Completed-day writer and database safeguards now pass actual SQL/DST tests.
  Production schema backup restored all18tables exactly and migration5 rehearsed
  without changing existing data. See [release preflight](2026-09-20-power-release-preflight.md).
  Reference verification, monitor routing, restricted roles, policy flags,
  source/schema cutover and production accounting activation are complete; see
  the activation receipt above. **Remaining:** scheduled monthly execution,
  independent AC-load qualification, restart/DST and physical-fault durability
  checks, retention planning, and the specific unfinished lifecycle/winter
  consumers. Two natural full-day writes and their persistence integrity are
  verified above.
  Do not repeat completed migrations, grants or backup rehearsals.

- Qualified daily/day-3 temperature learning is now deployed and enabled with
  actual cutover2026-09-20T14:52:58.582165Z. Five runtime files verified, protected
  model/state hashes unchanged, all three timers restored with definitions
  unchanged. Installed read-only worker correctly reported September19 partial.
  See [activation receipt](2026-09-20-daily-temperature-activation.md).
  First natural daily assessment remainsSeptember22 and day-3September25,
  contingent on complete coverage and correctly captured origins.

- First natural qualified-temperature training completed and promoted at
  September20 08:44:23MDT. Installed pure validators accepted the new eligible
  model and backtest report; prior accepted generation was preserved. Post-cutover
  evidence:air149/149,mass148/149(with1missing),outdoor149/149. Older training
  history remains explicitly legacy. See [training receipt](2026-09-20-natural-qualified-training.md).
  Training is terminal; the pending daily-temperature release is no longer
  blocked by that process. The natural09:25shadow job now verifiably uses today's
  accepted artifact: saved/live equality and production schema passed, model
  hash unchanged,25observed rows. Confidence remains low, statusshadow and no
  candidate emitted; no accuracy or additional control authority is claimed.
  See [shadow follow-up](2026-09-20-natural-shadow-verification.md).

- Temperature receipt collection and qualified hourly learning are enabled and
  deployed. Indoor235 is operator-confirmed. All three streams have naturally
  persisted receipts; the installed restricted worker passed post-cutover reads.
  Hourly cutover is2026-09-20T00:30:09Z. First natural qualified model update is
  still unobserved. See [activation receipt](2026-09-19-qualified-temperature-activation.md).
- Full-day atomic BMS materialization is now verified for September11–18.
  Raw-envelope rederivation matches daily coverage/minimum/DoD and the live
  published latest-day values; all eight days exceed99.93%qualified coverage.
  September10 correctly remains partial/insufficient. See [full-day receipt](2026-09-19-bms-full-day-verification.md).
  Independent power health and physical source-fault qualification are not implied
  by these daily SoC results. The September20observer-only cache restart is now
  separately verified: new epoch first unavailable, fresh post-reset raw/scale
  recovery, and10.197147seconds retained as an unqualified gap by the production
  reader. Protected rule definitions and BMS acquisition were unchanged.
  See [restart evidence](2026-09-20-bms-cache-restart-verification.md).
- Completed-night capture/assessment is now enabled on the existing06:40
  schedule, with assessment cutover2026-09-20T00:48:40Z. Exact deployed source
  retains qualified hourly learning and removes premature trough scoring.
  Migrations1–4/checksums, separate restricted roles, imports, private configuration,
  source hashes and all eight restored timers are verified. The natural18:50:14
  analytics publication succeeded. See [activation](2026-09-19-trough-live-activation.md).
- The [verified private backup/rehearsal](2026-09-19-trough-release-preflight.md)
  was the live migration gate. All15pre-existing data-table fingerprints and
  the learned model state remained identical after cutover. There were still
  zero origins/results/outcomes at release. First natural capture/publication is
  now verified September20; fully completed-night assessment remains unverified. No synthetic origin,
  forecast replay, test DM, or causal/bandit reward was manufactured.
- September20 natural06:40 forecast run succeeded: one canonical immutable origin,
  two accepted publications matching live Items, and notification not_eligible.
  No completed-night outcomes/selections exist yet. All24new hourly targets are
  for September21, correctly yielding zero eligible scores today. First normal
  hourly scoring is September21; first completed-night assessment is September22.
  See [natural capture evidence](2026-09-20-natural-forecast-capture.md).
- Pump hour-selection and expired-busy fixes are deployed; natural East start
  was observed. The concurrent15-minute rule change is preserved. Natural South
  start18:53:03.334 was curtailed safely at19:04:51.935 by the after-dark gate.
  At19:08:03.336 its stale timer nevertheless advanced LastCycle and posted
  cycle_completed. This is a verified reporting/ownership defect, not proof of
  a full run. The callback ownership guard is now deployed and read back exactly;
  stale callbacks cannot command either pump or publish completion. Live15-minute
  timing and all gates are unchanged. Five regressions reproduced the defect;
  all1370unit tests and build pass. See [release](2026-09-19-pump-timer-ownership.md).
  September20 natural East cycle now verifies uninterrupted observed operation:
  ON13:25:00.274, 32ONupdates with no intervening OFF, then timer OFF13:40:00.277,
  completion19:40:00.276Z and subsequent OFF confirmations. No safety interruption
  or logged error occurred. The bounded monitor exited. This is controller/Item
  evidence, not independent flow measurement; post-fix sunset interruption still
  needs natural verification. See the updated timer-ownership release receipt.
  September20morning's old status was explained by the former08:00–20:00condition.
  The operator then approved daylight operation and timer-only automatic checks:
  live now has one-minute cron plus manual request, no fixed-hour condition and
  unchanged safety/SoC/cycle timing. Natural07:38evaluation correctly kept pumps
  OFF at84%SoC under partly cloudy skies. See [activation](2026-09-20-greywater-daylight-activation.md).
  September23 [timer fail-safe follow-up](2026-09-23-greywater-timer-watchdog.md)
  found one September21 South cycle that switched OFF after 6m42s without a
  completion marker; the old callback later failed because its JS context was
  closed. The live rule now invalidates an early-OFF timer and enforces a
  next-minute duration cutoff if a callback is lost while a pump stays ON.
  A same-day follow-up also prevents the callback itself from claiming
  completion if its pump turned OFF just before the deadline.
  Exact guarded release, private rollback and natural idle evaluation passed;
  no post-release interrupted cycle was manufactured or claimed. A September23
  13:23–13:38 natural East cycle under the final rule hash completed at its
  15-minute deadline with no intervening OFF transition; both pumps ended OFF.
  The interruption fallback and sunset case remain unobserved.
- Thermal invalid-history barrier correction5fc437a is merged and deployed:
  timestamped UNDEF/NULL/bad states remain invalid rather than being dropped and
  bridged by interpolation/hold.10regressions failed before the fix;118focused
  and1031full tests plus42subtests pass. This does not migrate thermal learning
  to receipt-qualified temperature history. See [receipt](2026-09-19-thermal-invalid-history.md).
- A bounded single-pass qualified temperature grid reader is implemented for
  thermal's next history integration. Independent old-reader parity passed6300
  comparisons; a live restricted read qualified all36targets across the three
  streams. The reader is now installed as part of thermal training activation.
  See [foundation and integration requirements](2026-09-19-thermal-qualified-grid.md).
- Thermal training/backtest source integration now has an explicit legacy/
  receipt cutover, bounded read-only worker, no-fallback invalid grid targets and
  validated per-role artifact provenance. Real child-worker reads qualified36/36
  targets and existing accepted/previous artifacts remain readable. Training is
  now activated with cutover2026-09-20T00:30:00Z; all model files are unchanged,
  installed reads pass and the three original timers are restored. Natural
  training proof was subsequently verified at 08:44 as recorded above. Current-shadow temperature migration is
  now deployed as recorded in the September20 update below.
  See [integration and rollback contract](2026-09-19-thermal-qualified-integration.md).
  The [activation receipt](2026-09-19-thermal-qualified-activation.md) records
  exact runtime/model hashes and the next06:50MDT natural training gate.
- September20: qualified current-shadow temperatures are deployed and enabled
  from63529ea. Installed current-input and expiry validation passed; all model
  files and original unit definitions are unchanged. Three supported temperature
  streams use receipts with no numeric fallback; glazing/radiation are not newly
  qualified. Full1078Python tests passed at activation. Natural07:25shadow output
  is now verified: successful scheduled job, canonical saved/live Item equality,
  fresh receipt ages and25observed rows. That 07:25 result used yesterday's model;
  the 09:25 result subsequently verified today's accepted model as recorded above.
  See [natural verification](2026-09-20-natural-shadow-verification.md).
- Conformal intervals, weather/thermal outcome attribution, broad change-only
  historical-algorithm coverage, bandit reward design, independent feed-health
  checks, and actual seasonal/paired-data gates are still unfinished. Task82
  remains held; rain/wind scope and offhost backup retain their explicit deferrals.
- September20 daily-temperature evidence foundation is implemented, not deployed:
  exact receipt-interval coverage/extrema includes every persisted change point
  and DST-length days. All1101Python tests pass;7200pre-refactor oracle selections
  agree. Live read-only evidence correctly marks September19partial and today's
  elapsed window fully covered. Daily/day-3 temperature scoring integration,
  cutover policy and provenance remain open; numeric learning is not yet replaced.
  See [reader evidence and integration boundary](2026-09-20-temperature-window-reader.md).
- September20 daily/day-3 temperature scoring is now integrated in source with
  a bounded restricted worker, explicit complete-day receipt coverage policy,
  post-cutover forecast origins and bounded scoring provenance. No activation
  has occurred: the natural thermal training job is still using shared runtime
  files and must finish before deployment. The real read-only child correctly
  reports September19aspartial. Final1146Python tests and42subtests pass, one skip.
  Rain/PV are not newly qualified by this work.
  See [integration and activation gates](2026-09-20-daily-temperature-integration.md).

The broad goal remains active. Successful source deployment or synthetic tests
do not substitute for natural outcome or future-season verification.

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
approved (Hexmem 8691). Reviewed atomic transforms, corrected observer and
create-only disabled descriptor are now merged at `487eada`; fresh merged-main
verification passed 1,267 unit tests and build. This replaces the unusable draft,
not existing control or freshness readers. Two new unlinked transformation files
are installed and registered with exact source hashes. The installed JS service
passed eight filename-based cases through a triggerless diagnostic; a fresh log
receipt proved execution, and the diagnostic rule was removed. Existing rules,
poller, raw/scale configurations and persistence hashes stayed unchanged.
Disabled installation is now verified: two read-only source Things, three String
Items, two links and the exact observer with six triggers. Sources and observer
remain disabled, all three Items remain NULL, and preexisting rules, Items, links,
persistence and raw/scale/poller configurations matched the private baseline.
Ten installer VM tests passed; both one-shot installer receipts were verified
and temporary rules removed. The [installation receipt](2026-09-10-bms-disabled-install.md)
records the corrected rule-disable API/status assertions and safe ordering
deviation. Do not sweep these intentionally staged resources as dead config.
Subsequent [natural source qualification](2026-09-10-bms-natural-qualification.md)
passed five events per field with exact provenance, advancing source timestamps
despite unchanged numeric values, and all ten corresponding JDBC records. The
two observational sources are now ONLINE. Live probing exposed a trigger-prefixed
original-event map absent from the observer's test fixtures; the reviewed fix is
published at9840831, with1280 merged-main tests and build passing. The installed
observer was updated while disabled, then enabled under bounded natural-output
qualification. Five valid persisted records matched exact source envelopes; an
adjacent unchanged100percent pair63.385seconds apart proved the heartbeat.
Current validity, healthy companions and unchanged other definitions were checked.
Observer and sources remain enabled; no readers were migrated. A subsequent
source-only pause passed natural expiry/recovery: exact accepted timestamps,
input_stale with null measurement fields, independent source restoration, fresh
same-epoch recovery and all exact output records persisted. Existing BMS
acquisition remained healthy and definitions unchanged. Consumers must enforce
validUntil even while the status remains valid before the next cron publication.
Live health-fault/cache-restart qualification, consumer integration and sufficient
completed-window coverage remain open. This is not a completed historical-
algorithm audit.

Analytics reader cutover design e91b576 was approved by Sat (recorded34b2ded;
Hexmem8697). Superpowers was disabled at the operator's request; no further
skill approval loops apply. Solar_PV branch `feat/bms-analytics-reader` initially
introduced foundation6f97edf: closed-record validation, immutable qualified SoC
intervals, explicit ordering errors, bank/window clipping, expiry/fault barriers,
and a JDBC adapter retaining120seconds of pre-window history plus its original
carry. A single latest carry can hide a fault followed by restored evidence;
the regression rejects that ambiguous sequence instead of renewing coverage.
Original source data from a previous physical bank cannot authorize the new bank.

Verification:51new cases,347full analytics tests passed with the existing
cross-repository advisory test import path supplied. Read-only PostgreSQL checks
against the exact live expiry/recovery window produced9segments, no value at
the expired-valid snapshot and99percent after fresh recovery. No production
configuration, schedules, Items, algorithms, accounting or historical rows changed.
Subsequent daily integration1c5d2c9 and hourly/configuration integrationb08ae14
are now reviewed, merged, pushed to Solar_PV origin/main and deployed locally.
All381analytics tests pass. Daily statistics and quality use the same qualified
intervals; hourly current/lag values are qualified independently at actual UTC
times, including bank and DST boundaries. The real expiry/recovery feature
comparison yielded null at22:00:09.963Z and100percent at22:05:09.963Z;
unrelated features, daily power/temperature metrics and EFC matched exactly.
The partial first source day remains insufficient rather than being backfilled.

Spark completed a bounded independent read-only checklist, including a corrected
second pass over accounting and CLI files; Hex retained deployment authority.
Deployed imports/default policy and a real CLI dry run passed. All53historical
rows in each daily battery/PV/load/weather table retained identical fingerprints.
No controls, schedules, persistence or notification policy changed. Full receipt:
Solar_PV `docs/operations/2026-09-10-bms-analytics-reader-verification.md`.
Natural materialization was verified September11: the scheduled service ran at
00:21:29MDT, exited0 and materialized September10 into five tables with21source
quality rows. JDBC readback confirms bank discover_4_module_2026 and atomic
BMS quality provenance,679rows with29233.746037qualified seconds of86400
(33.835354percent), correctly insufficient_data. Qualified observed SoC ranged
92..100percent (8points observed DoD); these are partial-day observations, not
proof of the full day's minimum or maximum. Daily/cumulative EFC readback was
0.161628077692/8.296548462527 under the unchanged power accounting path.
The first scheduled post-cutover materialization is now verified; a full
qualified source day and source-health coverage remain pending.

Release correction: a later caller audit found that the shared atomic source
policy was also consumed by the live analytics quality/UI health evaluators,
which did not recognize it and falsely marked BMS fault. Solar_PV hotfix6a992f0
is merged, pushed and deployed, explicitly preserving their prior comms-status
contract while historical readers remain atomic.383tests and real read-only
comparison passed. The normal17:20:29MDT publication reports BMS OK and removes
the false BMS fault reason; `daily_source_quality_not_ok` remains explicit.
Receipt: Solar_PV docs/operations/2026-09-10-live-health-contract-correction.md.

Outcome work is implemented on isolated Solar_PV feat/advisory-trough-assessment
through `814a10a`: completed-window SoC qualification, immutable origins,
append-only revisions, frozen accepted-trough selection, bounded orchestration,
hard worker timeout, current-revision projection and exact diagnostic publisher.
The real worker passes isolated PostgreSQL success/replay/denied-read tests;
523 analytics tests pass. Earthship integration branch
`feat/completed-trough-integration` at `81f6a03` removes premature scoring while
preserving morning prediction inputs and legacy state. Its full script suite
passes 795 tests and 42 subtests, including forecast/DM behavior comparisons.

These branches are not deployed. Read-only preflight confirms production
migrations [1,2], atomic source item0613, no proposed advisory_writer or
advisory_assessor roles, and no installed capture/record/window/score helpers.
The existing service still executes the older forecast script from
`/home/sat/openhab/scripts` at 06:40. Reviewed migration/grant/dependency and
service-environment installation, activation and genuinely completed captured
targets remain unfinished. No bandit reward, learned reset or live scoring
change occurred. Feature-branch receipts document the exact tests and gaps.

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
| Task 18: Bandit thresholds | Deferred per its explicit prerequisite instruction. Immutable decision/result capture and completed-night assessment are live. Read-only September 23 verification found two naturally measured, frozen nights (September 20–21), with 99.98%+ qualified SoC coverage and a live seven-night diagnostic of 4.0 percentage points from two samples; see [receipt](2026-09-23-natural-trough-outcomes.md). Both outcomes explicitly forbid bandit eligibility and do not assess action attribution. | First natural assessment is verified. Next qualify action confirmation, delivery/compliance attribution, and a bounded reward/tuning design before any threshold change. Forecast residuals alone are not advisory benefit or DM utility. Keep current 95/92/90 F advisory and 30% DM thresholds unchanged. |
| Task 16: forecast ML v3 | Hexmem remains in progress with conformal trough/PV intervals and low-temperature correction watch outstanding. Current forecast_intel retains seven absolute PV/trough errors; searched P10 Items absent. | Trace all current producers and scoring history, specify calibrated intervals and evidence requirements, test and verify publication; explicitly resolve the under-correction watch. |
| Task 19: analog ensembles and hourly GBM | Pending reminder expects approximately 90 days of forecast/actual pairs and October 19 checkpoint. Snapshot ingestion was repaired September 5; current history has nine distinct local issue dates. | Accumulate and verify usable paired history; approve and validate models against held-out baselines. Do not substitute calendar age for valid coverage. |
| Task 21: live winter timezone verification | Pending November MST verification; summer checks cannot satisfy its explicit requirement. | Inspect actual winter data after transition, including sunny/cloudy boundary cases and calibration attribution. |
| Task 22: rain/wind learned corrections | Task description explicitly defers rain and requires a wind consumer, scoring, and renewed approval. | Resolve deferred scope with operator; satisfy outcome/scoring prerequisites before implementing learned gains. |

## Weather temperature evidence implementation

Additive temperature receipt evidence is implemented through fe4ec7f, with an
explicit model/ID/range/expiry policy, atomic value/receipt/expiry records,
process epochs, clock-rollback and expiry handling, loopback-only capture/read,
and an optional default-off WSGI entrypoint. Missing/invalid fields never renew
saved fallback temperatures. Exact configuration and deployment boundaries:
[temperature evidence contract](2026-09-10-temperature-evidence-contract.md).

Full script verification passed849tests and42subtests in144.44seconds, including
95focused source/receiver/configuration cases. The actual receiver was exercised
only with disposable state and blocked network; disabled/enabled/failed capture
produced identical legacy responses and saved weather/rain state.

The only installed production change is outdoor relay ID forwarding, preserving
the existing206filter and all weather conversions, with exact backup/source
hashes and restart/readback recorded in the contract. Both services are active;
the receiver still runs gunicorn weather:app. No evidence wrapper, policy file,
OpenHAB evidence persistence or scoring reader is active. Indoor235 was observed
but physical ownership confirmation remains pending. Natural per-field history,
expiry/restart/ingress qualification and learned scoring cutover remain open.
Packet health and display fallbacks cannot substitute for that evidence.

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
September 23 follow-up verified the current `hex_bms_ttd_smooth` rule body
matches tracked `bms-runtime-estimator.js` byte-for-byte (SHA-256
`8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a7940`).
The current code caches only a completed 20:30–06:00 window and uses
`averageBetween`; [openHAB's persistence contract](https://www.openhab.org/docs/configuration/persistence)
defines this as a time-weighted LEFT Riemann average suited to change-only
step states, not an unweighted average of changed rows. This resolves the
suspected sample-frequency bias for that specific API call, but it does not
prove physical source freshness or full-window coverage; its fallback remains
an estimate, not acquisition evidence.
At the 18:15 MDT September 23 read-only rolling-extrema check, indoor JDBC
Item 123 had a pre-window carry of 76.46°F at 00:14:37Z and 187 changed rows
in the ensuing 24-hour window. The changed rows alone peaked at 76.28°F, while
the published `IndoorTemp_24h_High` was 76.46°F. Thus the live
`maximumSince` path did include the held boundary value in this observed case;
the outdoor source likewise matched its carry-aware 55.22–73.4°F extrema.
This disproves a missing-carry claim for this natural window, not a general
source-health or gap-coverage guarantee for the rule.
At 18:43 MDT a fresh authenticated scan of all 36 registered OpenHAB rules
found nine rule bodies with persistence-history calls. The only analytical
consumers were the three above: BMS `averageBetween`, temperature
`minimumSince`/`maximumSince`, and Bitcoin `persistedState` (whose held-state
carry was independently verified September 10). The other six bodies use
`previousState(false, 'jdbc')` to cross-check explicitly persisted request,
counter or journal state against live state during recovery/write-readback;
three are Lightning Goats fixtures and the remaining three are the
SouthOutlet, feeder and night-load owners. They do not calculate a sensor
freshness age or numeric average from a change-only sample count. This closes
the live rule-body call inventory for these API names, not the separate
Python/JS service algorithms or physical-source freshness qualification.
Main-page temperatures use `localDayHistoryRange` already. Weather still displays
the outdoor 24-hour Items, and Earthship's buffering metric explicitly compares
24-hour indoor/outdoor swings. Do not silently redefine those Item contracts as
local-day values. Carry-in, source health and persistence API aggregation
semantics remain to be verified for the three analytical consumers. No live
rule was invoked or changed during this inventory.

September 10 follow-up confirms an incomplete-night cache defect in the exact
live runtime estimator: the first call before06:00 queries a future-ending
window and caches its result for the whole date, including after completion.
An isolated exact-function reproduction returned the early value at06:05 with
no second query. See [runtime cache audit](2026-09-10-runtime-overnight-cache-audit.md).
The correction now selects/caches the latest completed local06:00 window,
preserving weighted averaging and all estimator gates. Source and guarded
deployment adapter merged/pushed at b07af72; live script installed September10
18:45MDT with original enable state restored and exact source/readback verified.
Full verification:1,332tests/94files and production build passed. Private original
rule backup is retained; see the audit's deployment receipt. Natural overnight
boundary verification and independent power-source coverage qualification remain
unfinished; installation alone does not establish either.

September11 read-only follow-through reconfirmed installed runtime action SHA
8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a794,
rule IDLE/NONE and naturally updated runtime Items (basis evening,4640minutes
at the snapshot). There are no dedicated cache-window diagnostics in the
installed action, and the bounded midnight/06:00 log check yielded no such
evidence. Current output and correct source do not independently prove which
private cache window was used at those boundaries. That verification remains
open; no forced run, cache read/write or diagnostic control mutation was used.

### Power coverage audit, September 20

The [power coverage audit](2026-09-20-power-coverage-audit.md) reproduces a
numeric/health mismatch with production functions: a held1000W state integrates
to24kWh while a single120-second health receipt qualifies only1/720 of the day.
Daily quality is downgraded, but numeric energy is not clipped; cumulative EFC
currently sums daily records without a quality predicate. This is a verified
software-contract gap, not proof of a physical outage or the size of any live
accounting error. Qualified-interval accounting and an explicit legacy/cutover
policy remain required; no historical totals or controls were changed.

The [power acquisition audit](2026-09-20-power-acquisition-sources.md) now
identifies exact raw battery/PV registers and source-only timestamp transforms
on existing pollers. No additional TCP slaves or polling schedules are proposed.
The Solar_PV interval-math foundation a8925f9 is published on
feat/qualified-power-accounting;543analytics tests pass. Validated observer,
household-load receipt contract, persistence, qualified reader and versioned
accounting integration remain open. Raw observation transforms are not qualified
evidence and have not been deployed.

The source-only power observer now validates original binding events, keeps
per-field120-second expiry and invalid barriers, and resets its stream epoch
across cache loss/clock rollback.76isolated observer tests pass. The disabled
descriptor is not in managed deployment; no producer is active and no new
persistence is configured. Historical reader, volume qualification, household
load and versioned accounting integration remain required.

Historical power parsing/interval construction is now implemented in the isolated
Solar_PV branch: strict schema, per-epoch publication sequence, invalid/missing
barriers, exact TTL, persistence delay and unchanged-field independence.
579analytics tests and an actual-JS-output-to-Python-reader probe pass. Producer
sequence support passes1498UI/OpenHAB tests. Neither side is active; bounded SQL
transport/persistence, real source qualification and accounting cutover remain.

Bounded SQL transport is now implemented and published on Solar_PV feature branch
at c1d04e6. One read-only snapshot supplies all fields, with120-second lookback,
original timestamps,25-hour/60000-row bounds, oversized-record barriers and
explicit overflow failure.595analytics tests pass; a read-only real-JDBC query
structure probe passed on existing weather history, not power evidence. It is
not scheduled or deployed. Live collection, storage-volume measurement,
read-only role/table configuration and accounting cutover remain open.

Power collection preflight found no target collisions and confirmed existing
wildcard JDBC persistence needs no edit. All three exact source bodies passed
12installed-JS-engine checks through a temporary triggerless diagnostic, removed
with ownership verification. The source descriptor now uses REST-managed inline
transforms; no additional `/etc/openhab` files are needed. Exact source-parity
tests pass. Disabled resource installation and natural pipeline qualification
are the next gates; no power Items/Things/observer are live yet.

### Bitcoin carry audit, September 10

The live `hex_btc_24h_change` source still matches the September 5 SHA above.
REST configuration confirms its default persistence service is JDBC. The
[OpenHAB 5.2.1 implementation](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.persistence/src/main/java/org/openhab/core/persistence/extensions/PersistenceExtensions.java#L314-L339)
sets the historical query end to the target, orders descending and requests one
row. This is a held-state lookup, not an exact-time or nearest-change lookup.

At September 10 20:00:45.313 MDT, the naturally triggered rule logged current
76960 and historical 78043. A bounded read-only JDBC check at the corresponding
September 9 cutoff found 78043 at 20:00:44.781223 MDT, followed by 78036 at
20:01:14.773108 MDT. The logged historical value matches the preceding row;
no manual rule run or Item update was used. This verifies carry semantics for
this consumer, not feed freshness or completeness of all historical data.

Home and modal candles retain their approved observation-only contract:
first/high/low/last recorded values, empty intervals omitted, no fabricated
carry candles. The three focused candle/component/modal suites passed all
41 tests. No Bitcoin rule, chart behavior or persistence policy change was
needed for this carry audit. Independent feed-health qualification remains
separate from arithmetic and held-state semantics.

September20 follow-up: the legacy `/home/sat/bin/bitcoin.py` credential is now
externalized into a private 0600 file; the tracked credential-free replacement
is installed and four offline tests pass. Checked consumer surfaces found no
legacy reference, but root cron was unreadable and manual use cannot be excluded.
The existing credential was preserved, not rotated. Provider-side rotation and
historical-copy cleanup remain open. See the feed-validation cleanup receipt;
never copy the private key or original backup into reports or Git.
September20 clarification: the live feed executes the distinct Bash script at
`/etc/openhab/scripts/bitcoin.py`, still matching the validated tracked version
and using externalized Strike credentials. Exec result/time channels are
currently unlinked and publish separately; a timestamp alone is not a successful
price receipt. See the updated feed-validation audit. Legacy credential cleanup
and independently correlated feed-health evidence remain separate open work.

### UI boundary follow-up

Read-only REST requests plus the actual extrema helper reproduce missing
start-state carry in UI history: a September4 two-minute outdoor window yields
only65.3, while the prior state65.48 changes its historical maximum. The full-day
sample's extrema are not asserted wrong. Native boundary=true is not a safe
global fix: OpenHAB also moves the first post-window value back to the end and
relabels the carry timestamp. UI repair must explicitly discard look-ahead,
separate historical carry from freshness evidence, and handle local-day rollover.
The preflight records exact ranges/results and version-matched source. Category-
axis sparkline spacing and midnight-array retention were additional review
targets in that audit.

September 23 source follow-up: Home and temperature-modal local-day extrema now
request `includeStartState`, and the shared client filters OpenHAB's end
look-ahead to the half-open requested window. This resolves the earlier
start-carry/extrema reproduction for those paths; the preflight above is
historical. The six-hour Home outdoor/indoor/SoC/barometer sparklines were then
updated to request the bounded start carry. Their post-observation tail is a
separate dashed held-value segment through the wall clock, not a fabricated
sensor update; an empty or invalid history still renders no line. The source
freshness alert path remains independent. Verification passed 1,691 UI tests,
the production build, and all 23 Home browser checks, including a single-value
plateau with an excluded end look-ahead on the Lenovo M9 1340x800 fixture.
This does not qualify source health or complete the wider algorithm audit.

September 10 sparkline follow-up replaces the category axis with a hidden time
axis and timestamp/value pairs. Irregular change-only events now retain elapsed
time spacing; smoothing, colors and card dimensions are unchanged. Verification:
1,282 unit tests across 91 files, production build, and all 12 Home browser tests
passed. Actual ECharts pixel-coordinate checks on Lenovo M9 1340x800 and laptop
1280x720 prove a one-minute gap occupies 1/60 of a one-hour gap for both indoor
and outdoor sparklines. A unit regression preserves distinct instants through
the repeated DST hour. These fixture checks do not establish source freshness,
gap coverage, time-weighted smoothing or completion of the wider algorithm audit.

September10 Home daily-load follow-up replaces endpoint-only trapezoidal
integration with held-state integration of change-only power history. The
explicit local-midnight boundary request includes native carry-in, excludes
end look-ahead and accounts for the final interval through the request time.
A constant1000W state now contributes2kWh over two hours rather than zero.
Missing midnight coverage, invalid/negative/non-W states, conflicting duplicate
timestamps and request failure show unavailable rather than a partial daily
total. Latest-request ownership, minute-tick/visibility day reconciliation and
destroy cancellation prevent yesterday's response/total leaking into today.
Displayed load and derived net carry an estimate marker; historical held state
is not independent source-health evidence. No persistence policy or controls
change. This does not close the power-source outage/coverage audit.

Verification:19focusedintegrationtests; full1,351tests/95files; productionbuild;
all17Homebrowserchecks including constant carry/tail, missing coverage, request
failure, pending midnight reset and late old-day response. Existing LenovoM9
1340x800/laptop1280x720 geometry checks pass. A read-only live September10
00:00–18:53:44MDT history contained12,904rows with midnight carry and finite
nonnegative states, yielding a held-state estimate4.5274kWh. This is a bounded
snapshot calculation, not metered truth or verified source-health coverage.

September10 Home daily-gust follow-up now requests native midnight carry-in
with end look-ahead excluded, uses latest-request ownership, rejects prior-day
responses and clears/refetches the daily maximum on minute-tick or visible-tab
day rollover. Destroy aborts the gust request. Failed new-day reads show
unavailable rather than yesterday's maximum. Existing gust units, colors,
refresh cadence and current-gust display are unchanged. Full1,351tests/95files,
productionbuild and all21Homebrowserchecks passed, including four dedicated
gust cases and the existing M9/laptop layout checks. No source-health guarantee,
weather algorithm qualification or global24-hour Item contract is inferred
from this UI history correction.

No hardware actions, advisory-policy changes, migrations, or production writes
were performed for this inventory. Design approval and cross-repository
contracts apply before implementation. Existing OpenHAB controls and Discover
BMS counters must remain unchanged. A future-data dependency is unfinished
work, not a passed check. The broad goal remains active.
