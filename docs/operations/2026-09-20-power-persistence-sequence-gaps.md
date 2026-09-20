# Power persistence sequence gaps: verified accounting release gate

**Update:** loss is now localized after publication, with the JDBC queued-state
read explaining the observed replacement. The earlier uncertainty below is
retained as diagnostic history; see the confirmed correlation at the end.

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

## Narrow repair path (not applied)

Use an explicit immutable timestamp/state persistence call for this output Item,
and exclude only `Power_Evidence_JSON` from automatic change persistence to avoid
mixed duplicate writers. Preserve every other strategy, Item and control path.
The5.2.1 mapper supports item exclusions with `!ItemName`; explicit persistence
has timestamp/state overloads. Qualify the installed API and wrapper, same-clock
ordering, queue/post failure semantics, backup/readback and rollback before
cutover. Capture fresh event/database parity afterwards. No source patch, live
rule or persistence configuration change has been made during this diagnosis.
