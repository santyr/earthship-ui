# Completed-night forecast integration

Feature-only integration with Solar_PV `feat/advisory-trough-assessment`
through `a1aa6a6`. This is not a production activation receipt.

The forecast job no longer appends to legacy `trough_errors` or marks yesterday's
trough consumed at 06:40. Existing arrays and score markers remain intact.
`measured_trough` and its morning inputs to current prediction equations are
unchanged. PV/weather scoring, learned parameters, thresholds, forecast outputs,
advisory selection, notification eligibility/content/deduplication and the
existing schedule are outside this diagnostic change.

The adapter runs after normal forecast, advisory, notification and state-save
work. Enabled assessment imports the Solar package lazily and calls its bounded
worker, then its exact single-Item publisher. It does not replay existing actions.
When disabled, missing assessment dependencies or an incomplete/failed assessment result
leave no verified projection, the adapter requests `UNDEF` through the existing
safe state writer. This is an explicit unknown diagnostic, not publication of a
partial assessment. An ambiguous numeric publication is logged with no follow-up
write or retry in that invocation. No fallback resumes premature scoring.

`ADVISORY_ASSESS_ENABLED=1` requires the Solar runtime's explicit DSN, bank epoch,
cutover and timezone variables. The service import path must contain both the
installed Earthship script directory and the reviewed Solar analytics `src`.
Production tables, narrowly scoped capture/assessor grants, source/state/schema
backups and actual numeric/UNDEF acceptance must be verified before activation.
The capture adapter must use the same bank and reviewed cutover boundary.
Do not merge Solar's pending migrations into scheduled main prematurely.

Regression coverage includes the actual forecast main function at January,
July and both DST-transition 06:40 dates, preserving legacy scores and refusing
to consume the incomplete target. Golden comparisons exercise advisory choices,
normal/low-resource predictions, eligible/suppressed DMs and disabled/accepted/
failed assessment. Exact normal state, prediction writes and notifier commands
are compared with the diagnostic adapter omitted. Tests use stubs only for
external side effects; no real notification or OpenHAB state write is sent.

Full OpenHAB script suite: 795 passed and 42 subtests passed in 139.62 seconds.
Cross-repository analytics verification using this worktree's scripts on
PYTHONPATH: 522 passed in 16.41 seconds. Natural completed post-cutover outcomes
and live deployment remain open; no historical record or learned state was reset.
