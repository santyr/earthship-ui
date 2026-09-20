# Power persistence sequence gaps: verified accounting release gate

**Update:** the immutable writer is deployed and a bounded post-cutover
event/database comparison passes. Historical gaps remain unqualified. The
earlier uncertainty below is retained as diagnostic history; see the release
receipt at the end.

A live read-only qualified daily CLI calculation succeeded on September20,
using the actual15:18:58.261099Z collection cutover. It revealed unequal PV
coverage despite valid input envelopes. The common-support efficiency code
correctly avoided comparing the unequal daily totals. These are provisional
current-day diagnostics, not completed-day results or published values.

## Fixed-window evidence

`item0648`, from `2026-09-20T15:18:58.261099Z` through
`2026-09-20T15:53:24.118899Z`, contains1207rows and sequence endpoints1–1207.
There are155sequence jumps of one missing publication each, and155consecutive
byte-identical duplicate rows repeating the following sequence. The first jump
is persisted at15:30:19.373328Z. Therefore row count equaling the maximum sequence
does **not** establish complete publication history.

In this window, PV input is valid in1204rows and unavailable only in the three
initial startup rows. A slightly longer1232-row read contained zero malformed
envelopes yet reproduced substantial interval gaps. The reader correctly ends
coverage at the last known publication and requires a fresh post-barrier receipt;
it cannot assume a missing publication did not contain an invalidation.

The observed pattern is consistent with persistence coalescing Item state, but
that cause is not yet proven. Next check: correlate a bounded live output-event
capture with original database rows and inspect the installed JDBC write path.
Distinguish producer publication loss from persistence loss before changing code.
Do not remove sequence barriers, fill from held numeric Items, delete duplicate
history, or relabel incomplete coverage as complete.

## Operational status

Observational collection remains enabled; the captured data and gaps are retained.
No accounting migration, grant, timer change, control action or published daily
total change occurred. This defect is a release gate, not a reason to discard
the verified qualified intervals that do exist.

The strict opt-in policy loader and CLI/scheduler forwarding are implemented on
the Solar_PV feature branch; all660analytics tests pass. The policy resolves
`Power_Evidence_JSON` from inventory, never assumes table0648, and rejects
ambiguous/missing mappings, duplicate JSON keys, oversized policies and malformed
cutovers. No production scheduler flag has been enabled.

## Confirmed publication-versus-persistence correlation

The rotated `/var/log/openhab/events.log.7` contains these ItemStateUpdated
events, all in the continuous-collection epoch:

| Sequence | Event log time (MDT) | JDBC persistence time (UTC) |
| --- | --- | --- |
| 395 | 09:30:16.293 | 15:30:16.296628 |
| 396 | 09:30:19.367 | missing |
| 397 | 09:30:19.368 | 15:30:19.373328 and15:30:19.374119 |

This proves that396was published and was lost downstream. The two397database
rows are identical, not two distinct acquisitions. The matching5.2.1
[JDBC implementation](https://raw.githubusercontent.com/openhab/openhab-addons/5.2.1/bundles/org.openhab.persistence.jdbc/src/main/java/org/openhab/persistence/jdbc/internal/JdbcPersistenceService.java)
reads the mutable Item state inside its queued task for ordinary `store(item,alias)`.
Rapid updates can therefore replace the earlier value before the queued write
reads it. Its explicit timestamp/state overload captures the supplied state.
The matching
[core persistence manager](https://raw.githubusercontent.com/openhab/openhab-core/5.2.1/bundles/org.openhab.core.persistence/src/main/java/org/openhab/core/persistence/internal/PersistenceManagerImpl.java)
uses the ordinary Item-based path for change events, rather than the supplied
event state. Installed bundle names/manifests identify5.2.1.

A later45-second live SSE/database comparison was contiguous for all27events,
sequences1372–1398, demonstrating intermittency rather than disproving the loss.
Private captures and the preserved395–397log records are under
`/tmp/hex-power-sse-jdbc-bxuajyqe`. Both bounded captures are complete; no monitor
remains running.

## Narrow repair path (historical plan)

Use an explicit immutable timestamp/state persistence call for this output Item,
and exclude only `Power_Evidence_JSON` from automatic change persistence to avoid
mixed duplicate writers. Preserve every other strategy, Item and control path.
The5.2.1 mapper supports item exclusions with `!ItemName`; explicit persistence
has timestamp/state overloads. Qualify the installed API and wrapper, same-clock
ordering, queue/post failure semantics, backup/readback and rollback before
cutover. Capture fresh event/database parity afterwards. No source patch, live
rule or persistence configuration change has been made during this diagnosis.

## Applied repair and bounded verification

Source commits `3f0fe7c` and `ec9d723` are pushed to main. The observer now queues
the serialized immutable state through the explicit timestamp/state JDBC API;
the live Item post is separate. Sequence identities are consumed before enqueue,
including ambiguous failures. UI-post retries do not repeat persistence writes.
Queue acceptance is not a durability acknowledgement; the reader still rejects
ambiguous ordering and preserves missing-sequence barriers.

The installed API was qualified with an owned triggerless diagnostic, then the
diagnostic was removed and absence verified. Initial cutover was
`2026-09-20T16:13:47.718872Z`. JDBC automatic `everyChange` now excludes only
`Power_Evidence_JSON`; its `restoreOnStartup` remains explicitly configured.
All other strategies and protected rule definitions were preserved. Restore and
forecast side effects were checked before the configuration reload; no actuator
command or openHAB restart was used.

The initial writer reserved microseconds. Inspection of the matching JDBC5.2.1
PostgreSQL implementation showed explicit timestamps pass through
`toEpochMilli()`, so microsecond uniqueness would be lost. The corrected source
reserves distinct milliseconds and was deployed rule-only at
`2026-09-20T16:22:52.592732Z`, without another persistence reload. Source SHA256:
`9ffedbfd13c6b0971e2a612ca90e853a8e69cbc81f67f03ff0d4d890885d26ba`.
All1513unit tests in100files pass, including same-clock driver-precision
uniqueness and persistence/UI failure semantics.

Final epoch: `4bb09d80-9b62-41ed-87a5-3fcc5164ac1e`. Through
`2026-09-20T16:24:11.844164Z`, all46rows have distinct persistence timestamps,
contiguous sequences1–46 and exact original ItemStateUpdated event payload
matches. Every row parses using the production strict reader; all three fields
produce qualified intervals. Startup acquisition gaps are retained. Fresh
post-cutover values, exact rule readback, unchanged persistence configuration
and protected rule definitions were verified; recent runtime logs showed no
new error. Private backups/readbacks are under
`/tmp/hex-power-immutable-release-mqlqrg2v` and
`/tmp/hex-power-ms-release-uynxc_rv`.

This closes the demonstrated mutable-state writer defect, not full-day durability
or physical-fault qualification. The original collection cutover remains
`2026-09-20T15:18:58.261099Z`; old missing/duplicate records are not rewritten.
Qualified accounting is still source-only, with consumer integration and the
database release/rehearsal gates outstanding.
