# Power persistence sequence gaps: verified accounting release gate

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
