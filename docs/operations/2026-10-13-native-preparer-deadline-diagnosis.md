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
