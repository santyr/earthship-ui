# Native preparer deadline diagnosis

The current native stage passes model/runtime qualification, but its current-input
attempt still exceeds the unchanged 75-second geometry deadline. The new preparer
timer remains uninstalled; production keeps the existing model and schedules.

Source `36a6d32` seals 221 source files, retaining all 72 fitted-runtime and 12
native-runtime source hashes and four original evidence references. The capped
production-interpreter probe passed in 31.598 seconds, with 120,971,264 bytes peak
memory and no memory-limit or OOM events. The actual installed-service/library
handoff independently verified in 7.900 seconds. Those checks do not prove timely
current geometry or forecast publication.

The read-only current-input attempt (`run-u7792.scope`, handle 47634, terminal exit
1) refused at the geometry phase deadline. Total elapsed time was 230.898 seconds,
including scheduler admission. Its exception stack is inside `capture_batch` →
`run_training_worker` → the unchanged-source/resource guard. The retained request
contains the final 32 timestamps, from October 14 16:50:15 through 19:25:15 UTC.
Deterministic splitting produces 128, 128 and 32 points, so the preceding two
batches completed before the third began. The complete 288-point series was not
persisted, and neither current capture nor household projection was qualified.

Preparation independently validates the candidate and then runs three bounded
Java source-mode batches. The stack establishes where the deadline expired; it
does not identify how much earlier time belonged to candidate validation, Java
startup/calculation or repeated resource checks. The next diagnosis should measure
those contributions under the existing caps and deadlines. Preserve the original
safeguards and model evidence; another identical retry would add little evidence.

Full household replay additionally requires actual publication and independently
verified delivery receipts (`household_cycle.complete_cycle` and
`load_cycle_delivery`). Natural delivery and mature outcome scoring must therefore
be verified after shadow deployment. They remain full-program requirements;
private calculations cannot stand in for production receipts. Source-backed
admission and timely current geometry remain unfinished before activation.

The subsequent bounded profile (handle17532) expired during candidate validation, before Java batching. It recorded4,684 preparation guard calls,61.337 seconds cumulative guard time in74.950 profiled seconds, including28.462 seconds in native inference checks and32.543 seconds in the additional resource preflight. Profiler overhead is included. The resource helper now reuses only parsed path objects, freshly checks every cgroup component, and reads each kernel value through an equivalent bounded ASCII reader.97 affected regressions passed. A controlled two-second preparer-guard comparison completed173 checks in2.079 seconds before and255 in2.001 after, approximately12.02→7.85 milliseconds per check. This comparison does not qualify whole-model or geometry latency.

The helper revision updates native_live's explicit source pin. All72 fitted sources and nine REQUIRED native fitting sources remain unchanged; _fit_environment permits this OPTIONAL serving-source change against the retained original fit. A new independently validated serving artifact and source stage are required before selection. Existing artifacts and production selection remain unchanged.

The optimized source37c1f3e independently passed its221-source sealed production-interpreter runtime probe in30.308 seconds, peaking at120,786,944 bytes with all memory-limit/OOM counters zero. It binds serving artifacta8b84ac/runtime8ebad5e to the identical original fit and four original references; all72 fitted and nine REQUIRED native sources remain unchanged. Earlier standalone validation attempts stopped on interval pressure and the approved host swap-read limit; both refusals remain retained. The staged probe performs its own full independent readback and passed without changing policy. The actual owned handoff also passed in7.609 seconds.

Current geometry now succeeds: all288 points were computed and replayed in67.899 seconds for issue2026-10-13T20:00:15UTC, within the same75-second limit. However, the subsequent strict read-only capture probe refused because input collection finished after that issue. It began at the actual19:59:45UTC warm clock. No current capture, household projection, publication or installation was qualified. NativeInferenceHeadroom in this probe differs from the production forecast driver's PublicationHeadroom. The next timing qualification must exercise the production driver, count cold startup, and intercept every write, including withdrawal, without fabricating delivery receipts.
