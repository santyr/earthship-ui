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

## Production CPU correction

The observer-window family activated successfully without refitting. Its natural
18:23 UTC geometry preparation completed, but the 18:24:45 UTC forecast hit the
90-second service timeout at the old 20%-of-one-core quota. Household observation
was still stale. Activation alone therefore did not establish the repair.

The native forecast now receives one CPU (`CPUQuota=100%`). It uses the existing
publication RAM/pressure admission instead of the original 20% profile. Memory
remains 256 MiB, worker swap remains zero, and scheduling priority, thread count,
deadlines and source validation remain unchanged. The staged driver identifies
this profile so historical sealed families retain their exact original bytes.
The installer verifies the precise quota for each service; scoring and Java
geometry retain their current quotas pending separate measured changes.

The user permits increased development and production resources, with combined
host load as the constraint. The one-core regression run passed 80 cases in
11.11 seconds. It covers production admission, family compatibility, handoff,
role-specific effective limits and receipt serving. A misplaced timer CPU check
was caught and corrected before packaging. This change does not yet implement
the proposed shared cgroup budget or dynamic admission coordinator.

Live completion evidence must follow the next scheduled serving cycle.
