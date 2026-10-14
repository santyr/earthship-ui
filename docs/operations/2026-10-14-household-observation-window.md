# Household observation window

The thermal forecast was publishing while household collection reported
`source_collection_failed` or `insufficient_preissue_budget`.

Read-only reproduction under the real 20% CPU / 256 MiB / zero-swap profile
found that household collection itself succeeded in about 1.8 seconds after
0.9 seconds of initialization. A coupled reproduction using the original
compressed-temperature collector and source-read inventory left only 3.406
seconds before the household deadline. It completed successfully in that run,
but the live window has too little margin for normal acquisition variation.
Neither reproduction changed timers or wrote telemetry.

Native publication previously waited until 20 seconds before issue to start
original input collection. It now starts up to 30 seconds before issue. The
native driver also checks available RAM and sustained pressure immediately,
instead of spending five seconds in the older quiet-wait preflight. Continuous
RAM/pressure/OOM checks, kernel worker limits, original source freshness, the
three-second household issue margin and the ten-second collection ceiling stay
in effect. Legacy publication retains its existing preflight.

Two regression tests first failed for the old twenty-second start and fixed
preflight wait. The corrected publication, receipt-serving, household-driver,
collection and resource-admission tests passed: 56 cases in 111.80 seconds,
serially capped during development. Geometry fixtures were made available at
issue minus 35 seconds, consistent with preparation preceding collection.

This is an optional serving-source change. Packaging preserves the exact fitted
model and four original evidence files, verifies unchanged protected and required
native fitting sources, and creates a new candidate/receipt for the serving
runtime. No fresh fit or cold preparer qualification probe is required. Actual
household publication remains to be verified after activation.
