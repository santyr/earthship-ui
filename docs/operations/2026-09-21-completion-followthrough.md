# September 21 source-only completion follow-through

## Result and evidence limits

This work was based on `santyr/earthship-ui` main commit
`0fa49f2ee26a48ae5c932a7476c98b702dad7673` and the current
[outstanding-work tracker](outstanding-work.md) and
[thermal graduation workstream](thermal-model-graduation.md).
The latest inspected commit already qualified a full isolated JVM restart;
this patch does not repeat that as newly accomplished work.

The connected GitHub integration returned **403 Resource not accessible by
integration** for branch creation. No branch, commit, pull request, release,
production deployment, host restart, or real journal write was performed.
The deliverable is an apply-checked patch, changed source, offline tests and
runbooks. Do not label the overall project or thermal graduation complete.

## Implemented source work

### Authenticated confirmation ingress

`openhab/scripts/thermal_confirmation.py` adds a bounded, prompt-scoped encrypted
Nostr ingress. It binds prompt IDs to exact question content/action states,
allowlists the authenticated operator, delegates cryptography to pinned nak,
uses a private durable first-receipt spool, deduplicates rewrapped rumors, rejects
future plans, supports append-only corrections, and acknowledges only after
full journal record equality. Negative/nonterminal replies never become actions.
It requires an explicit apply mode and has offline preparation/rendering modes.

See [the ingress runbook](thermal-confirmation-ingress.md). The complete live
relay/sender/acknowledgement route, exact nak/keyer behavior, genuine PostgreSQL
integration and natural operator collection remain unqualified here.

### Persistence provider collection boundaries

The existing disconnected rehearsal in
`scripts/qualify-persistence-file-provider.py` now uses
`scripts/persistence_boundary.py` during both file/managed/file roundtrips.
After observing provider absence at each of the four handoffs, it injects one
controlled update to **JDBC_Qualification_Probe inside the disposable container**.
It observes the changed Item and unchanged history, then requires the next
positive persistence write and an exact preserved historical prefix.

The structured `persistence_collection_boundary_report=` line records the
handoff timestamps, last pre-boundary and first post-boundary persisted times,
conservative unqualified probe windows, and the count of deliberately injected
updates not persisted. It never backfills a gap or calls a provider roundtrip
uninterrupted sensor collection. Clock discontinuity, late/extra writes, changed
history, absent positive controls, or missing handoffs fail qualification.

The overall report becomes `verified_with_collection_gaps` only after the
existing restart/restoration and exact DTO checks also complete. An exception
retains an incomplete report and the original owned-container cleanup. The
original prepared strategy, resource identities, power exclusion, change-only
policy, and production ownership are unchanged.

**This is executable test logic, not a new successful Docker/OpenHAB/JDBC run.**
Run the existing `python3 scripts/qualify-persistence-jdbc.py` on the qualified
host to execute it with the actual cached OpenHAB 5.2.1/PostgreSQL bundles.
It retains the existing read-only live strategy comparison and disconnected
owned containers. Review and retain the new report alongside the prior receipts.
A failed extended rehearsal is a release blocker, not a reason to relax the
history checks or silently insert missing records.

This patch does not implement or claim the still-open future forecast time-series
and independently written power-history restoration qualifications. The new
report explicitly labels both `not_tested`, along with natural source continuity
and whole-host recovery.

### Tests and CI

`tests/completion/` covers strict envelope/policy handling, canonical hashing,
question binding, allowlisting, bounded subprocess behavior, durable SQLite
replay/restart/failure paths, exact journal readback, corrections, DST, and
conservative provider-gap accounting. The actual provider `main` function is
also executed against a stateful Docker/database double to check orchestration
and cleanup. Existing CI gains a separate command for these tests.

The package's verification directory records the actual offline test result and
environment. SQLite, hashing, clocks, process limits, and patch application were
executed locally. Nostr cryptography/keyers, PostgreSQL, Docker and OpenHAB were
not available here and are expressly represented by doubles at those boundaries.
The full existing UI/Python suites, production build, browser checks and GitHub
Actions were not run. Historical passing test counts in repository receipts are
not results of this patch.

## Remaining work and next evidence checkpoints

| Workstream | What remains | Completion evidence |
|---|---|---|
| Confirmation collection | Exact-binary crypto/keyer tests, real append-only journal integration, narrow relay/sender/ack wiring, attended deployment | Genuine authorized replies; repeatable replay/failure/restart receipts; later qualified outcomes |
| Thermal v5/v3 | Isolated candidate fitting/validation using corrected output contract, provenance-aware evaluation, reviewed numerical/seasonal graduation gates | Reproducible candidate report; eligible advice; compatible runtime/model rollout and rollback |
| Persistence migration | Forecast-series behavior, independent power restoration, real extended boundary rehearsal, staged cutover | Actual isolated runtime/database receipts before any live ownership change |
| Power accounting | Read back September 21 scheduled results and first qualified completed windows; full-day storage/query checks | Actual natural job logs and qualified revisions, not inferred success from elapsed time |
| Scheduled temperature/monthly paths | Verify eligible daily and day-3 results on/after September 22 and 25; monthly run on/after October 1 | Natural executions and valid evidence, without fabricated reports or premature manual DM jobs |
| Power/lifecycle/winter work | Independent AC-load evidence, remaining temperature/lifecycle/BMS comparisons and winter replay in the appropriate project | Qualified source coverage and reproducible comparisons; no legacy substitution |
| Recovery/protected resources | Off-host/whole-host recovery and protected-control restart/rollback before their migrations | Attended rehearsals with independent recovery evidence |

Task 82 remains held. The removed pump-cycling concern is not reintroduced.
Do not repeat completed migrations, grants, natural-writer verification, or full
backup rehearsals merely because older tracker sections predate their receipts.
The current source work adds no actuator authority and no thermal promotion.
