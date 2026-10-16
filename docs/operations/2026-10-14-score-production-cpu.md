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

## Repeated pressure polling

An offline profile of the actual five current-model completions reproduced97,350 guard callbacks in59.732seconds. Pressure sampling consumed22.256seconds; the full original inventory was verified78times, totaling1,122,490,211bytes. These timings overlap: inventory verification itself calls the guard.

The outside-fitted scoring coordinator now samples native inference pressure at the first callback and then at most once per second, with forced fresh checks before scoring and before returning success. It preserves native preflight, every-callback deadline/lock/config/source checks, original-source validation, kernel caps, pressure thresholds and fitting behavior. Refusals latch for the invocation. Clock regression/nonfinite values refuse. During a long blocking operation, cooperative samples resume when callbacks resume; kernel limits remain continuous. This changes detection cadence to the next callback after one second; it does not provide asynchronous host monitoring. The dynamic shared resource allocator remains proposed, not implemented.

The same five original outcomes replay in35.449seconds (40.7% less wall time), with identical statistics and identical inventory count/bytes. Pressure overhead is0.083seconds. Network was denied, no fit ran, and no live writes occurred. The profile excludes the live consumer lock and does not claim end-to-end production timing.89 affected tests pass, including real memory-event refusal, forced final sampling, nonrenewing deadlines, retained-native dispatch and admission. Source `8245591` was deployed as `c3d2dbe5ce7dff2df4b72124119fd1fec71928b59ea99cb650940789820db164` after the normal21:35 forecast. The original model artifact, fit and receipt stayed unchanged. Owned activation exited0, peaked at59,293,696bytes with all memory-event counters0, and ran no qualification probes. Readback at21:36:20UTC verifies all five owned files, effective service pins/caps and enabled timers, with UI/publication HTTP200. The clean idle daily checkout also selects8245591. The first updated current-model run at21:41UTC succeeded at21:42:08, scoring one new outcome and reconciling seven total. It used64.810CPU seconds,97,607,680bytes peak RAM and zero swap. The preceding six-outcome run took100seconds and96.867CPU seconds. These natural runs have different report sizes; the controlled five-outcome comparison above isolates the sampling change. Independent review found no Critical, Important or Minor issues.

## Retained native pressure policy

The21:36 historical slot selected the `actual-review-fixes-20261014` archive and refused in its old `native_inference_pressure.py:68` after16seconds. The bounded public diagnostic does not retain the inner cause, so the precise triggering counter is unknown. Inspection showed the archive still enforced retired host-wide swap and per-callback PSI restrictions: `production_score_policy` replaced admission functions but not that monitor.

Correction `8a112eb` explicitly substitutes the current release's hash-pinned publication monitor and one-second sampler for retained native scoring. The existing archived numerical/runtime/receipt functions stay original. The factory matches the original no-argument constructor and preflight/check interface. The wrapper forces fresh memory/pressure checks after successful archived returns, then restores every substituted hook even on failure. Legacy fitting policy remains unchanged. Three RED regressions reproduce the incomplete override, missing final check and changed-helper refusal; all92affected tests pass. Admission-only checks pass in19actual retained/current source contexts, with network forbidden and no scoring or fits. Independent review found no Critical, Important or Minor issues. Deployment `2beeb8843b5d8f3b83b0540b8ceb4bb905ef6d395d13325c509d317ae481654e` activated in35.473seconds, peaked at58,925,056bytes with zero memory events, and preserved model52dd5d12. Readback at21:43:10UTC verifies all five owned files, effective caps/pins, active timers and HTTP200 UI/publications. The new preparer started normally at21:43:05UTC. The clean idle daily checkout selects8a112eb. The normal historical21:56UTC invocation031534b3ed194e8091544f076ff65f49 succeeded at21:57:22UTC: one outcome scored, nine reconciled for the selected revision,79.145CPU seconds,96,862,208bytes peak RAM and zero swap.
