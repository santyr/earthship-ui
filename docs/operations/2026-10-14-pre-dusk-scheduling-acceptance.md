# Pre-dusk scheduling acceptance — October 14, 2026

Retain the existing persistent ten-minute timer. An isolated offset Astro event
would add a second trigger and require the same retry/catch-up path. The current
calendar already supplies three opportunities inside the 60–90-minute lead
window in both summer and winter. A successful outside-window run consumed
0.137 CPU seconds. Avoiding these small checks does not justify adding another
scheduler for this display-only estimate.

This implements A10's evaluation without changing the shared Astro sunset or
introducing an event provider. The selected schedule remains
`*-*-* 14..20:02/10:45 America/Denver`, with `Persistent=true`. The shared
`Sun_Set_Start` channel has offset 0 and one existing link. Its October 14 sunset
was 18:25:35.452 MDT. Today's expected in-window opportunities are 17:02:45,
17:12:45 and 17:22:45 MDT; later checks must withhold.

## Deployed source discrepancy fixed

The deployed `forecast_pre_dusk.py` lacked the independent-night validation
already committed as `fd9f522`. It accepted duplicate, unordered, current-day,
stale or malformed sample dates, and mismatches between sample and date counts.
Six existing regressions failed against that exact production script.

The committed fix was installed atomically under the existing shared consumer
lock at 19:41:48 UTC. The selected file now hashes to
`1198c93a8893f9892f2d01070b165fe29210285d156768cf7eedf94118325b17`, matching the
worktree. All 49 affected pre-dusk and canonical trough-window cases pass against
the deployed script and its actual import context. Today's real morning record
has three distinct descending sample days: October 13, 12 and 11. Its numeric
samples and frozen drop value were not changed.

The normal service ran after installation, exited 0 and reported `outside_window`.
It used 0.137 CPU seconds and sent no Item updates. Its existing timer remains
active. OpenHAB was not restarted; no actuator, calibration, notification or
morning forecast behavior changed.

## Acceptance mapping

| Requirement | Verification |
| --- | --- |
| Contention | Real private-file `flock` test returns 75 without starting the worker while locked; the next attempt succeeds after release. Effective service uses the same flock command and shared lock with a bounded 20-second wait. |
| Restart/catch-up | A newly loaded worker reuses the external same-day receipt and refuses a duplicate. The live persistent timer supplies subsequent opportunities without process-local scheduler state. |
| Sunset changes | An outside-window attempt followed by a changed native sunset reads the source again; the next valid attempt records the original unshifted timestamp. |
| Missed trigger | Actual systemd calendar expansion for native summer/winter sunset samples yields three valid ten-minute opportunities. Missing the first leaves two; the fourth is outside the window. |
| Expiration | Existing exact 60/90-minute boundary and delayed-I/O tests refuse expired windows and stale atomic SoC. |
| Duplicate opportunities | Original and restarted workers publish once per date, using the external receipt. |
| Stable unshifted sunset | Live channel offset 0, one source link, unchanged timer and original sunset timestamps retained in receipts. |
| Calibrated load interval | `advisory_windows.py` remains byte-identical in deployment; 20:00 Denver to next-day 11:00 tests include both DST transitions. |

The 49-case set includes five added schedule/restart/lock tests. The prior 44 cases
cover original receipt semantics, stale inputs, provenance and trough windows.
The real systemd/lock checks operate only on private fixtures; they do not
simulate failure on live equipment.

## Monitoring limits

The latest natural receipt at this readback is still October 13, issued at
23:02:45.994795UTC for the original 00:27:02.277 UTC sunset, with predicted trough 82%.
Today's issue window has not started. No new in-window publication after this
fix is claimed. Its upcoming natural receipt remains a production-monitoring
check; A10's existing scheduling policy and source correction are qualified.
This acceptance does not establish forecast accuracy or complete the broader
PR3 program. A11 protected daylight qualification remains open.

Private before/after logs, deployed source copy and live readback are retained
under `.superpowers/sdd/2026-10-13-native-model-serving-receipt/` with `a10-`
prefixes. Their hashes and current source identity are recorded in
`household-program-progress.json`, proof `astro_a10_scheduling_acceptance`.
