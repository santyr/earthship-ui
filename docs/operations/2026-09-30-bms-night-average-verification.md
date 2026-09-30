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

The disabled candidate still needs natural charging-transition observation,
numeric-minute comparison and the exact guarded production cutover. This
isolated no-event result does not prove a deployed production timer. Historical
AC averaging does not qualify other held source inputs, and these calculation
and fixture results authorize no equipment controls.
