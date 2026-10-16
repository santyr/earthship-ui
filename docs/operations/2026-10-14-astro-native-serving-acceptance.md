# Native Astro model serving acceptance — 2026-10-14

Astro audit A07 and A08 are complete for the authorized provisional model
migration. The deployed model uses native solar geometry in both fitting and
serving, and its retained 24-hour prediction replays exactly without OpenHAB.
This acceptance does not graduate the model or establish improved accuracy.
The full PR3 program remains incomplete.

## Current serving evidence

The effective forecast service command selected deployment
`2b8aab1b7ce638f961a31155721fcacfe54590104e2c1995da11565873abf2fe`,
source `b6a5e87c3e66c445f5bf4b529c0efccdc1890e7b`, and model
`52dd5d122485f0bdafa0aed4fa7412c0823ce9829ed3d9bdc920e44d88526506`.
The offline audit freshly checked the owned deployment, model receipt,
original evidence and sealed runtime hashes. It then numerically replayed the
naturally delivered 19:20:15 UTC forecast and its training geometry.
Training runs through 2026-10-14T06:00:00Z.

The audit blocked Python socket connections. Replay completed in 1.128 seconds
with zero network attempts, no fitting, no Java process and no live writes,
inside a one-core, 256 MiB, zero-swap development scope. The current serving
code, rather than an older development-only implementation, performed replay.

Private evidence and the reproducible audit script are retained under
`.superpowers/sdd/2026-10-13-native-model-serving-receipt/` as
`a07-a08-offline-serving-audit.json` and
`a07-a08-offline-serving-audit.py`. Their exact hashes and model identities are
recorded in `household-program-progress.json` under
`proofs.astro_a07_a08_native_serving_acceptance`.

## A07 acceptance mapping

| Requirement | Evidence |
| --- | --- |
| Historical/future timestamps, leap day, DST folds, exact instants | Retained actual binding qualification contains 88 points, including leap day, spring transition, both autumn fold instants and millisecond timestamps. Its externally pinned cache replayed identically in this audit. |
| Site, timezone, version and source identity | Cache and series validators bind original requests and native runtime. Current training and forecast geometry share binding 5.2.3 and the same library hashes as the retained actual qualification. |
| Bounded batch collection | Original training qualification contains 778 points in seven batches. Serving consumes a retained exact-instant series; it does not make one binding RPC per historical row. |
| Missing geometry and artifact compatibility | Existing geometry/series tests reject missing, reordered, extra or changed instants and runtime identities. The model tests reject missing geometry even at zero radiation; the legacy fitter refuses native endpoint types. |
| Horizon disagreements | Actual qualification records two horizon disagreements; the original training cohort records one changed point. These are retained, not normalized away. |
| Versioned dataset, refit and model | Native dataset, actual fit and provisional model artifact use the v2 geometry/model contracts. Current receipt verification binds the original fit, dataset, geometry and snapshot bytes. |
| Replay parity | Earlier model tests cover identical-geometry legacy rollout and sensitivity parity. Current training geometry and the naturally delivered 24-hour native forecast replay exactly offline. |
| Prediction comparison before provisional migration | Retained paired development comparison `4fd2321fd8d2deb1df0d97080c4efbb5da00af81faa28f27a982f9d9303a11c5` compares legacy geometry, native geometry and the native refit over ten common endpoints. Its bytes were rechecked. This uses training endpoints and actual future weather; it is not held-out or as-issued accuracy evidence. |
| Actual deployed publishers | Effective command selects the verified stage; natural forecast publication and household readback are recorded in the monitoring continuity deployment evidence. |

The prior development comparison does not establish superiority: air MAE was
approximately 0.516 F for legacy fit/geometry, 0.546 F for legacy fit/native
geometry and 0.545 F for native fit/native geometry. It qualifies the migration
comparison only. CPU savings have not been demonstrated.

## A08 acceptance mapping

The existing 106 sky-rule cases and 37 native input/model cases cover low sun,
missing and stale station measurements, zero denominator, bounded thermal
fractions and cloud transients. This audit rechecked both retained test-log
hashes and the corresponding source hashes. Native input/model and forecast
sources match the deployed sealed stage. The installed sky calculator matches
the previously tested repository source. Those unchanged tests were not rerun.

The current model retains `earthship-native-clear-sky-fraction/v2`: reference
1050 W/m2, exponent 1.15, maximum fraction 1.3 and thermal night at native
elevation <= 0 degrees. Missing radiation is inferred as zero only at native
night with explicit provenance. The sky classifier remains a separate model;
native Astro radiation has not replaced station measurements. Station radiation,
calculated geometry, forecast shortwave and PV evidence keep their distinct
source contracts. Actual native refitting and serving are now verified.

## Natural monitoring and remaining work

At 19:21 UTC the normal scoring service exited successfully and wrote the
current model's artifact-specific report, assessed at 19:21:15.800053 UTC.
Every horizon correctly has zero completed outcomes. Historical delivery
selection was unavailable for some older forecasts, which explains the bounded
pending reason; it did not prevent the current report from being written.
The first 19:15:15 forecast matures for one-hour scoring at 20:20:15 UTC.

Mature native scoring, held-out/as-issued accuracy, the first scheduled morning
fit and full household program acceptance remain open. A09 circadian policy,
A10 pre-dusk scheduling and A11 protected pump daylight qualification also
remain open. This audit changes no owner rule or actuator authority.
