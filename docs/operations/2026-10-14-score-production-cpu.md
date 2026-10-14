# Production scoring CPU admission

The current model's normal 20:21 UTC score failed at 20:22:44 with `deadline`
at `thermal_model/capture_readers.py:36`: its 50-second acquisition budget had
expired. The worker used 20.245 CPU seconds and peaked at 83.8 MiB, with no swap.
A previous historical run was throttled in 897/904 periods for 71.69 seconds,
with zero memory PSI and memory-limit/OOM events. Its exact 32 retained packets
rebuilt a valid original source score offline in 3.834 seconds at one core,
without networking, fitting, or live writes.

Under the user's approval to increase production resources while protecting the
host, scoring now opts into the existing one-core publication profile. The
worker retains 256 MiB RAM, zero swap, 24 tasks, one numerical thread, low I/O
priority, host RAM/pressure admission, the shared consumer lock, and its existing
120-second work/130-second service deadlines. This is a bounded production fix;
a dynamic host-wide resource coordinator is not implemented by this change.

Current scoring invokes the pinned publication resource helper. Retained legacy
and native scoring invokes its original numerical code and evidence validation
under an explicit scoped admission-policy adapter. That adapter temporarily
replaces only the installed/native resource-preflight entry points and the
publication admission helper, restoring them on exit. The current policy helper
is checked against its pinned source digest before use. Archived source files,
model identities, receipts, data validation and physical-control authority are
unchanged. Existing archived service-family definitions retain their original
quota when verified; new opted-in families require exactly one core in effective
unit readback. Preparation remains at its existing quota.

Validation: 129 affected scoring, dispatch, admission, effective-unit and handoff
tests passed in 15.93 seconds. An offline check accepted the new policy against
the actual legacy archive and all ten retained native archives, denying network
access and executing no scores or fitting. Deployment and production scoring
outcomes remain pending.


The current model's failed 20:21 attempt also rebuilt offline from its 32 retained
packets, using the original serving receipt for the 19:15 forecast. The canonical
source score is `7e538e710674dc1ef84fc5af016e83a1e140ea56370495844e4d70308c7c6fa3`.
For 20:15 UTC the prediction was 69.002446 F, the original observed value 69.26 F,
and absolute error 0.257554 F. Persistence error was 0.18 F. This is one validated
measurement, without a model-superiority or graduation claim. The replay took
3.919 seconds with no network attempts, fitting, or production writes.


Source `870293e` is deployed as
`0db0237d3661453c77e15b2b0d5aaacf323823f3609000e9e246627b150e5875`.
The original model artifact remains `52dd5d12...526506`. Effective readback
verified all owned files, service pins and active timers; scorer CPU is `1s`,
RAM is 268435456 bytes, swap is zero, and TasksMax is 24. The daily production
checkout contains the same source. UI and both thermal publications returned
HTTP 200 with the unchanged provisional model.

The first normal legacy run at 20:36 UTC succeeded, refreshing 256 existing
horizon samples with no new mature legacy outcome, using 2.958 CPU seconds.
The first normal current-model slot after activation is 20:41 UTC; its live
completion and performance report remain pending.

A second scheduling defect made current-model monitoring stale by design:
`_validate_report` accepts a report for 15 minutes, while the previous current
model cadence was 20 minutes. The staged scheduler now reserves minute 1 and 11
of each 20-minute period for the current model, minute 6 for legacy scoring, and
minute 16 for rotating native history. This retains one job every five minutes
and unchanged preparation/forecast slots, limits and deadlines. Current reports
can refresh every ten minutes without relaxing report freshness. Archived family
metadata retains its old slot definitions. A full-day scheduling regression
proves the counts, ten-minute current gap and complete history rotation; all 91
affected routing, deadline, admission and handoff tests pass in 16.15 seconds.
This cadence is active in deployment `715078d7`; the successful 21:01 UTC
current-model invocation confirms the new slot. See the admission-continuity
record for the intervening chronology and reader fixes.


The 20:56 historical invocation failed before scoring at
`household_cycle_pressure.py:31`. The retained pressure monitor supplies the
actual cgroup leaf, but the new production-policy adapter accepted no keyword
arguments. The adapter now forwards that explicit leaf to the same pinned policy;
limits and pressure checks are unchanged. A missing explicit leaf still refuses
admission instead of silently checking a different cgroup.

Both regressions failed with the original TypeError before the two-line fix.
All 94 affected scoring, dispatch and admission cases pass. A network-denied
serial check also exercised actual pressure monitors in all 13 retained native
archives plus the legacy admission context. No scoring, fitting or live writes
were performed by that check. The callback correction is deployed as `a6b37ac4` from source `2fbad86`.
Effective unit/file/timer readback passed; UI and both thermal publications
returned HTTP 200. The clean daily-training checkout is at the same source.
The natural 21:06 UTC legacy invocation exited 0 in five seconds. The natural
21:16 UTC retained-native slot also succeeded: one outcome scored in 48 seconds,
44.710 CPU seconds, 84.8 MiB peak memory and zero swap.
