# Original weather forcing and origin context

The weather boundary freezes a complete verified original provisional capture together with its separately prepared thermal context. It reconstructs the original metric receipts, weather issue/availability, operator snapshot, exact five-minute outdoor/radiation forcing and original thermal output. Pure restoration rebuilds the complete measured-temperature snapshot from the retained native receipts, including source identities, physical sensor epochs, clocks, values and temporal policy. It recomputes the candidate artifact digest and requires its coefficients to equal the prepared model coefficients. Forecast wind and weather codes retain their original hourly brackets. No interpolation, forecast equation or ventilation calculation changes.

A digested canonical zlib/base64 envelope retains the complete original capture under the existing 256 KiB weather-context budget. Decoding permits at most the original producer's 2 MiB, checks exact declared size and raw digest, requires complete EOF and refuses trailing streams/data. No original data or candidates are discarded to fit. Snapshot, plan and pipeline limits stay 256 KiB, 512 KiB and 1 MiB respectively.

Snapshot/v4 enriches the unchanged model-bound v3 derivation at its original clock. It retains forecast issue and outdoor/radiation/wind/weather-code trajectories plus original shade, legacy coarse ventilation and known operator mode. Unknown mode stays unknown. Forecast and operator rows use nonphysical context quality, so they cannot authorize action references. Measured solar radiation, humidity, precipitation, wind and daylight geometry remain unavailable without their own sources. Outdoor shade presence is not actuator position; coarse ventilation does not identify separate window/skylight states.

Pipeline and plan receipts/v3 retain versioned original source contexts. Candidate validation snapshots reuse the root or retain a distinct complete document by identity, preserving every candidate's actual validation lineage without repetitive copies. Original v1/v2 receipt branches keep their structure and numerical behavior. Operational pipeline, plan and enclosing outcome replay validate the original producer closure and original weather/thermal executing dependencies.

The translator remains disabled and causal/action effects remain unqualified. Full bank/usable energy, household load, observed weather/daylight, authority/owner sources, outcomes, resource trajectories, operator UI and release qualification remain part of the full PR #3 objective. Local affected tests, actual natural-source replay, independent review and hosted exact-head checks are the stage gates; no live deployment is claimed here.

Validation: 17 pure weather boundary tests and 13 snapshot/pipeline/operational cases are included in the complete post-review affected run: 687 passed in315.41s under serial CPU20%, memory256MiB, swap0, tasks24, nice15, idle-I/O and single-thread limits. The independent review found two Important original-binding gaps: measurements could detach from retained sensor receipts, and candidate contents could contradict their stored artifact digest. Five fully resealed regressions reproduced both gaps; all 17 weather-boundary cases pass after the single fix pass. The post-fix affected suite and actual-source proof pass; all four hosted exact-head checks pass. No Critical or Minor findings were reported.

Actual-source qualification used committed source `b58de1b` and a read-only collector at **2026-10-11 22:19:37.754232 UTC**, followed by the normal **22:20:15 UTC** model issue. Original capture `d79ece790bcb9eff05084bb49a846fe25519a37d816294917d03f177174fc972` has verified delivery `062ad81a8020f4a52874c6595b8824ab355f2b659b952604df06a88abe79db5f`. Its exact 24-hour thermal output and weather forcing match the common snapshot, pure replay and private operational CLI replay. The source receipt digest is `16b2a258ae8065171c90266a7444f12822170b4f0749757023b4a513386573cd`; the household receipt digest is `acffa88afbcea0682ea8acffd0388e8b600ece03071af0562d09bb718e1d1b18`.

Nine roles qualified at collection, but inverter AC expired before the common model clock; that row remains unavailable. Eight roles remain qualified, current/full energy completeness is false, and no action was selected. The energy projection uses earlier retained numerical parameters plus original current SoC; its input qualification remains `not_assessed`, with no qualified physical bank or household load. Provisional confidence stays low and action effects stay unqualified.

The first collector attempt refused the normal publisher's existing shared lock before any source data was retained. A one-shot capped timer then collected before the following scheduled issue; no publisher start/restart or lock bypass occurred. The successful natural issue does not resolve the publisher's separately observed intermittent delivery failures. Private source/config/data files remain outside Git; only this sanitized evidence account is published.

PR [#24](https://github.com/santyr/earthship-ui/pull/24) merged at `ec4f9c2c68b4d39338fb6958937564a5ea651fae` after exact head `eb4b492b841393189336574184a0453fc7a815a5` passed CI, encrypted-delivery, authentication and GitGuardian. CI run `38180181944` includes the full OpenHAB Python suite, disposable PostgreSQL and operational-tooling regressions. Final documentation-head private CLI replay equals the original sealed household receipt. This closes the weather-context integration gates while the full PR #3 program remains active.


## Native solar geometry in the shared snapshot — 2026-10-14

New native weather preparation emits prepared-weather/v3 and weather-projection/v3.
It exposes the original native solar-position series already verified with the
thermal capture: exact timestamps, elevation and azimuth, site/timezone, binding
runtime, availability and cache/series identities. The common weather domain retains
that same value under `solar_geometry`, so energy, thermal and planner replay use
one snapshot identity. No additional astronomy calculation or live read is added.

The row is `retained_native_calculation`, with no observed-at timestamp. It cannot
serve as qualified physical evidence or authorize an action. Measured radiation,
humidity and wind remain unknown without their own sources; solar event times and
daylight duration are explicitly unavailable in this position-only series. Its
validity ends at the final retained position; no interpolation or extrapolation is
introduced. Existing v1/v2 weather contexts retain their exact prior projection
and snapshot shapes; only v3 opts into the new field.

Two regressions reproduced the missing projection/snapshot field. The 61 native
and legacy weather/common-cycle cases and 179 downstream planner, measured-weather,
energy, outcome, resource and serving-context cases pass. These include exact
original thermal parity, old native receipt replay, no-I/O restoration, immutable
returned positions and refusal of resealed derived-position changes. Original
captures and candidates keep their existing verification; configured 256 KiB
snapshot and 2 MiB pipeline limits are unchanged. Actual retained-source replay,
independent review and production adoption are pending.
