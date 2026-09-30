# September 30 actual Java/JDBC overnight-average verification

The source-only estimator candidate's completed local night was tested against
the actual production OpenHAB 5.2.1 Java persistence implementation. Its native
local construction selects September 29 20:30 through September 30 06:00 MDT:
`2026-09-30T02:30:00Z` through `2026-09-30T12:00:00Z`, 34,200 seconds.
The existing estimator, output Items, source evidence and equipment were not
changed. This closes this completed window's Java/JDBC calculation check,
not source-freshness qualification, minute accuracy or estimator deployment.

| Calculation over the same window | Mean W |
| --- | ---: |
| Actual default-service `averageBetween` | 172.656298128655 |
| Explicit JDBC `averageBetween`, default integration | 172.656298128655 |
| Direct Java, explicit JDBC and LEFT integration | 172.656298128655 |
| Independent reconstruction with each interval truncated to milliseconds | 172.65629812865498 |
| Same original history integrated at full timestamp precision | 172.6725910702629 |
| Previously bounded REST history, left-held integration | 172.6725981871345 |
| Independently source-qualified AC evidence, covered-time mean | 172.67245631476672 |

Java returned all 6,454 numeric observations, from
`02:30:04.209587Z` through `11:59:55.030318Z`; its default page size was
2,147,483,647, not a 1,000-row truncation. A persisted boundary carry was
available. Full-precision versus Java integration differs by 0.016293 W,
about 0.00944%. The actual implementation uses `Duration.toMillis()` on
each LEFT interval; reconstructing that arithmetic reproduces the result
within 0.000000000001 W. See the
[version-pinned core implementation](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.persistence/src/main/java/org/openhab/core/persistence/extensions/PersistenceExtensions.java).
The REST calculation additionally rounds timestamps to milliseconds; it is
not represented as exactly equal to the original PostgreSQL microseconds.
The source-qualified mean excludes 1.203 missing seconds rather than
inventing zero or holding across missing source coverage.

## Diagnostic scope and corrected preliminary result

`python3 scripts/verify-live-bms-night-average.py` creates one randomly named,
triggerless logging-only rule, verifies its exact script and empty inputs,
executes that rule once, reads only its unique structured log receipt, then
deletes its exact owned rule and checks it is absent. The command briefly
mutates the diagnostic rule registry; it is **not** a completely nonmutating
host command. It neither writes Items/persistence nor commands equipment.
It bounds history iteration to 20,000 rows and the log scan to 1 MiB, verifies
the parsed UTC boundaries against the independently calculated local window,
and withholds arbitrary errors or unrelated logs.

The preliminary 167.588862-W result is invalid for this night: converting
the supplied `+00:00` ISO strings with this runtime's `time.toZDT` silently
shifted them six hours. The next explicit-clock probe exposed a window of
`08:30Z` through `18:00Z`, including an unfinished end. This was a diagnostic
construction defect, not a demonstrated estimator defect: the candidate
already builds the native local window with `withHour`/`minusDays`, without
parsing those strings. The corrected probe matches that exact construction
and guards both epoch boundaries before querying. An initial reconstruction
attempt also failed Java/JS temporal interoperation; explicit Java Instant
boundaries and Java state-string conversion resolved it. Every temporary
rule from these attempts was removed, including failure paths.

Six offline tests cover completed nights and both DST transitions, exact
owned definitions, closed bounded receipts, success/failure cleanup and UID
collision refusal. Independent live registry readback found zero diagnostic
rules remaining. The production estimator's script still hashes to
`8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a794`
and retains its sole `BMS_TimeToDischarge_Min` Item-update trigger. No diagnostic
rule is retained or scheduled, and no diagnostic becomes a freshness assertion.

## Isolated natural no-event expiry and restart follow-through

The same unchanged source candidate subsequently passed the real networkless
OpenHAB JVM qualifier's no-event test. After it entered BMS mode, the fixture
held all six evidence/elevation Item states unchanged. Its REST adapter forbade
every non-GET request during the wait: no input writes and no `runnow` calls.
The registered original 30-second cron alone cleared basis to OFF and both
numeric outputs to zero when the current source expired. Its original expiry
was `2026-09-30T15:09:03.077Z`; zero/OFF was observed at
`15:09:31.987Z`, 28,910 ms afterward, within the 45-second observation bound
(cron plus readback overhead). Source TTLs were neither shortened nor extended.
All held input strings still matched the pre-wait snapshot.

The qualifier then passed actual server-JVM exit/new-PID restart, missing-input
OFF, fresh recovery and exact managed-baseline rollback. Its production pre/
post-readbacks retained the original script hash and sole trigger. The 2-GiB
memory/no-extra-swap, two-CPU, read-only networkless fixture had no host mounts,
devices or published ports and was removed with its tmpfs. Independent Docker
label lookup found none remaining. No production rule, Item or equipment was
written.

The first attempt also passed no-event expiry (26,521-ms lag), but its later
restart-phase execution request was refused, so it was not an overall pass.
The adapter had checked provider presence without checking runnable status;
it now waits explicitly for IDLE before requesting execution, including after
restart. The complete retry passed. Offline tests compile the actual nested
REST/executor bodies with synthetic dependencies to prove write refusal during
the natural wait and IDLE-before-execution ordering, including HTTP refusal.
Eight qualifier tests plus six diagnostic tests passed, and 20 adjacent JS
estimator/replay tests passed. Disposable synthetic test logs were removed.

A separate 07:00–09:05 MDT natural-history replay had 251 half-minute ticks:
one initial distinct-current warmup (`evening`), then 250 `bms`, with no OFF
or noncharging TTF violations. It had no charging crossover, so it cannot
qualify that transition. Its REST-weighted overnight input is still explicitly
diagnostic, and numerical projected minutes are excluded from promotion.

At that checkpoint the disabled candidate still needed natural charging-transition
observation, numeric-minute comparison and the exact guarded production cutover. This
isolated no-event result does not prove a deployed production timer. Historical
AC averaging does not qualify other held source inputs, and these calculation
and fixture results authorize no equipment controls.

## Later natural charging crossover

The expanded 07:00–10:55 MDT persisted-history replay has 471 half-minute
ticks: 381 `bms`, 67 `evening` and 23 `now`, with no OFF tick. Read-only audit
instrumentation observes the candidate's own validated `bankReady` and current
sample rather than treating raw timing metadata as source qualification.
The underlying rule remains unchanged at SHA-256
`b7d414ede0db177435816e91609c1385061fc4252c4cc7da8c9047f9199a1944`.
Two new regressions exercise a distinct-source charging crossover through the
eight-minute dwell and reject a malformed-source receipt; all 22 adjacent
estimator/replay tests and eight isolated-qualification adapter tests pass.

There are 64 qualified ticks with current at least 1.0 A, zero charging/BMS-
basis violations and zero noncharging TTF violations. At `16:31:30Z`, the
candidate immediately leaves its prior `bms` basis for `evening` on a fresh
1.60-A observation acquired at `16:31:07.745Z`. This closes the previously
missing natural charging-exit test; it does not deploy that candidate or
establish numerical minute accuracy. The estimator still needs those remaining
calculation/release gates and an exact guarded production cutover.

The CLI's nightly input remains the explicitly diagnostic REST left-held mean,
172.672598 W. The separately qualified real-Java default average is 172.656298 W;
their 0.0163-W millisecond-rounding difference is already explained above.
These numeric projections are not used as a promotion proof. No live Item,
rule, persistence history, equipment control or notification was written.

## Numerical comparison exposes a sampling-loss release gate

The subsequent read-only replay adds bounded per-basis numerical comparisons
and largest-difference examples. Zero sentinel pairs are counted separately,
not scored as numerical agreement; malformed values are withheld. Original
JDBC Number strings such as `5724.0` are accepted as exact integer minutes.
The same 471 ticks have no malformed pairs. These are held live displays
versus a cold-cache, aligned replay, **not** measured runtime accuracy.

| Matching basis | TTD positive pairs | Mean absolute delta, min | Maximum absolute delta, min |
| --- | ---: | ---: | ---: |
| BMS | 381 | 63.955381 | 3,873 |
| Evening | 44 | 1.818182 | 10 |
| Now | 5 | 18 | 30 |

The BMS maximum is at `2026-09-30T15:32:30Z`: live 6,828 minutes versus
candidate 10,701. Its captured candidate buffer is
`[12479, 13120, 10701, 11679, 11617, 5827, 6439, 6828, 6818]`;
independent sorting gives median 10,701. Original numeric BMS history's last
nine observations through `15:32:21.103Z` are
`[13120, 10701, 11679, 11617, 5827, 6439, 6828, 6330, 6818]`, median 6,828,
matching the persisted live output at `15:32:21.106Z`.

The original 6,330 sample persisted at `15:31:50.995Z`. Bounded receipt
readback shows it absent: the `15:31:50.411Z` receipt still contains the older
6,828 sample, and the next `15:32:21.103Z` receipt contains 6,818. The producer
updates its source slot on each trusted event but publishes healthy envelopes
at most every 30 seconds; independently phased source events can be overwritten
before an envelope is published. The estimator's separate aligned 30-second
sampling can lose additional distinct envelopes. Source freshness alone does
not preserve the observation sequence required for median parity.

**Do not promote this candidate from passing mode/freshness tests.** Next
preserve original TTD observation delivery without restoring held-numeric
freshness assumptions, qualify evidence-driven estimator evaluations alongside
the no-event expiry timer, and repeat the numerical/JVM/recovery gates on the
resulting exact source hashes. TTF differences also remain diagnostic, with
41 zero/nonzero mismatches across the window and large positive-value deltas;
agreement with the old estimator is not a physical full-charge accuracy label.
No producer or production estimator changed. The 37 adjacent JS tests pass;
the only code change is the read-only replay audit.

## Observation-preserving source candidate and renewed JVM qualification

The source-only collector now enqueues an envelope for each **accepted original
native TTD or TTF event**, including new observations of unchanged values.
Its provenance, range, monotonic-time, startup and communication gates are
unchanged. High-rate current/voltage updates retain their 30-second coalescing;
fault/recovery/expiry barriers remain immediate. An enqueue failure is still
reported and consumes its sequence, never represented as a successful receipt.
Collector candidate SHA-256:
`621f4ac7416de35e1b68f87f7d0ed4096c729319cad08e5b71bc95b1b0062c80`.

The disabled estimator descriptor adds a runtime-evidence Item-update trigger
alongside the original 30-second expiry cron. AC, PV and charge-current EMAs
advance only on a distinct source epoch/observation identity, not repeated
timer reads or another field's publication. Invalidated values still reseed
on valid recovery. Estimator candidate SHA-256:
`374d2fc5ae3f1879f60d6e7cccb2a34ef627158a312769dddd88dca22f826e31`;
descriptor SHA-256:
`3031e528bb002dd4c0741b3da65a243624bf33f321c05e865b117eda17c9e458`.

New regressions first failed for the observed loss and duplicate EMA weighting,
then passed. The synthetic end-to-end test executes the actual collector and
estimator source: all ten supplied native readings are delivered, including
6,330, and the last-nine median is 6,828. It is explicitly synthetic, not a
household receipt or repaired history.

`qualify-bms-runtime-estimator.py` passed the revised estimator/descriptor in
the disconnected real OpenHAB JVM: missing inputs, expiry, charge reversal,
reload, full exit/new-PID restart, fresh recovery and exact baseline rollback.
With every input held and all manual writes/executions forbidden, the original
current expiry was `1790789803301`; OFF/zero was observed at `1790789821680`,
18,379 ms later. Production writes were zero. The owned networkless fixture
and tmpfs were removed; independent Docker label lookup found none remaining.
This qualifies the estimator fixture, not the new collector's live delivery.

Replay now evaluates every persisted runtime envelope plus aligned expiry
ticks. Numerical comparisons remain on the fixed 30-second observation grid
(and cold-cache seed), avoiding an artificial comparison at an event's exact
timestamp before asynchronous live outputs reach JDBC. Replaying the same old
history makes 936 evaluations and 471 numeric comparisons, with zero charging
BMS-basis or noncharging TTF violations. The old missing-sample median error
still exists (3,873 minutes): omitted observations cannot be recovered by a
new evaluation schedule. Counts include repeated expiry checks and are not
independent physical samples.

**Production collector and estimator are unchanged.** The original installation
adapter is pinned to its historical initial-install hash and must not be used
to bypass an update qualification. Next build/verify the exact guarded
collector update, prove new natural original-event/JDBC sequence preservation
and bounded write rate, then redo numerical promotion checks and the guarded
estimator cutover. Existing history must remain unmodified.

Final verification: all 1,934 Vitest tests (133 files) pass, including 58
adjacent collector/estimator/replay tests; all 14 selected Python qualifier
and Java-average adapter tests pass. Their owned temporary test directory
was removed. Authenticated final production readback retains estimator
`8698b16a...` with one trigger and collector `a2193c0f...` with six triggers.

## Guarded collector-update adapter: preflight passed, apply gate off

`scripts/update-bms-runtime-input-evidence.py` is separate from the historical
create-only installer. Its default is read-only. Production preflight matched
old collector `a2193c0f...`, proposed `621f4ac7...`, the six original triggers,
the exact file-owned String Item and ONLINE native Things. The static
rules/Things/links/JDBC guard digest was
`7aae3f2a9e67c7a9552d9f63cfa98811e8a49a223532111593a7b5892a1c2a1b`.
Natural states/statuses are not mistaken for configuration drift or qualified
acquisition evidence.

`RELEASE_ENABLED=false` refuses application before even creating a private
backup. A later qualified apply privately saves and verifies the exact rule
preimage, rechecks the baseline/guard, PUTs only this collector definition,
requires exact definition/IDLE readback and verifies the protected static
guard. Ambiguous failure includes our exact update in rollback; a concurrent
collector edit is never overwritten. Success means definition updated with
natural evidence pending, not delivery/accuracy qualification. It cannot
command Items, alter the estimator, change hardware configuration or relax
source TTLs. Fifteen synthetic adapter tests cover the exact source-only delta,
preimage/candidate drift, closed release gate, ambiguous failure, concurrent
edit refusal, unrelated-configuration rollback, target restriction and private
backup readback. No production writes or production backup were made in this
preflight. Original-event/JDBC fixture qualification remains the next release
step; subsequent natural preservation and bounded write-rate checks are still
required before estimator promotion.

## Real-event/JDBC fixture passed; collector-only update deployed

`qualify-bms-runtime-delivery.py` executes the pinned collector in disconnected
OpenHAB 5.2.1/PostgreSQL containers. Genuine Java `ItemEventFactory` objects
carry synthetic sensor values/source tags; Thing ONLINE/OFFLINE states and
private cache are mocked. Clock, UUID, explicit JDBC persistence and the
output Item are real. This does not qualify physical Modbus acquisition.
OpenHAB is read-only, two CPUs/2 GiB; PostgreSQL is one CPU/384 MiB. Neither
has additional swap allowance, production credentials, host mounts/devices
or published ports. The probe requires its isolated environment flag.

Both runs persisted 18 exact receipts: five startup/recovery barriers, ten
successive TTD samples including 6,330, two new zero-TTF observations and a
fault barrier. Twenty high-rate current updates added no writes. The first
run passed the probe's own assertions; negative offline tests then exposed
that the verifier could accept later carry in place of immediate delivery.
The verifier was tightened to require observation/recording identity on every
runtime frame, and a new complete run passed payload, sequence and unique
timestamp checks. Both runs removed their owned containers/tmpfs; independent
label checks found none remaining.

After qualification the adapter release flag was opened. Its collector-only
update applied around 12:09 MDT, preserving six triggers, the file-owned Item,
TTLs and every other rule/Thing/link/JDBC definition. Production collector
now equals `621f4ac7...`; estimator remains `8698b16a...` with its original
single trigger. There was no OpenHAB restart or equipment command.
Private rollback preimage:
`/home/sat/.local/state/openhab-config-migration/bms-runtime-observation-update-wfksp9h7/preimage.json`,
SHA-256 `ead58baa44d780fe45b3b55b0c3d9288a893994f41c8807b14604a11676a871f`.
Its original script matches `a2193c0f...`; final static guard matches backup.

### First new natural delivery window

Read-only observation of `2026-09-30T18:09:40Z` through
`2026-09-30T18:11:42.157Z` found seven JDBC receipts, continuous sequences
5–11 in epoch `c69cf9eb-ffd9-4b5b-98c8-96da028aa880`. Six have all four fields
valid; the initial incomplete startup prefix is not invented freshness.
Qualified receipts include four new TTD observations and two new zero-TTF
observations. Bounded history digest:
`59237f1bc97a76ff6863512ff4bea5a2e45eef9facb7d6e26655b87b4dbd2f6a`.

| Independent native UTC timestamp | TTD minutes | Collector callback delta |
| --- | ---: | ---: |
| 18:10:01.595 | 956 | 0 ms |
| 18:10:31.701 | 906 | 0 ms |
| 18:11:01.716 | 885 | 0 ms |
| 18:11:31.912 | 894 | 0 ms |

All four changed numeric-history rows pair uniquely with valid collector
observations. The sampled rate is about 3.44 envelopes/minute, including
warmup—not a universal future-rate bound. Change-only numeric TTF history
cannot independently prove repeated zeros; those are evidenced by the
qualified original-event collector/fixture, not held Item timestamps.
All 38 selected Python tests pass. Temporary test files were removed; the
operational rollback backup is retained. New numerical qualification and
guarded estimator cutover remain open. Existing history is unchanged.

## Post-update minute comparison and output dependency census

Read-only production rule census found only `hex_bms_ttd_smooth` referencing
`BMS_Runtime_Basis`, `BMS_TimeToDischarge_Smoothed` or
`BMS_TimeToFull_Smoothed`. No other live OpenHAB rule consumes these outputs;
this is not a census of arbitrary external clients.

The candidate replay of 12:10–12:20 MDT used the new collector receipts:
52 evaluations were all `now` and source-qualified charging, with zero
charging-BMS or noncharging-TTF violations. At the 21 aligned numeric ticks,
TTD mean/max absolute differences from the live display were 435.24/830
minutes; TTF differences were 46.19/70 minutes. The largest differences were
at the cold-cache start. Nightly load was not consulted on this `now` path.

The replay now supports a bounded `--compare-from UTC` target window after
historical warmup, without changing the four-hour total replay bound. Its
regression proves prefix inputs seed the actual candidate state while prefix
minutes are excluded from target statistics; invalid comparison bounds fail
before history requests. Repeat command:

```sh
node openhab/scripts/bms_runtime_shadow_replay.mjs \
  2026-09-30T14:20:00Z 2026-09-30T18:20:00Z \
  2026-09-30T02:30:00Z 2026-09-30T12:00:00Z \
  --compare-from 2026-09-30T18:10:00Z
```

The 3-hour-50-minute prefix changes the target's TTD mean/max difference to
173.33/380 minutes, not zero; TTF remains 44.76/70 minutes. Thus initialization
matters, but does not explain all differences. The 970 total evaluations
include two legitimate fail-closed startup barriers when the collector was
updated, followed by fresh recovery. The warmed prefix is reconstructed
history, **not** a copy of the live rule's private cache or proof of minute
accuracy. No natural deep-discharge BMS median is tested in this all-charging
target window. Keep the estimator candidate undeployed while its remaining
numeric/state-history differences are investigated; do not treat mode agreement
or warmup as numerical promotion. No production write, job or control was
performed by these checks.
