# UI and private operational diagnostics

Task 10 implementation record. This document describes the feature branch; it is
not an installation receipt or a model-selection approval. Task 11 owns the
consumer-first rollout, installed-source readback and final review.

## Display and horizon decision

Retain the ten-day default. `forecastDetail.js` accepts at most ten ordered local
calendar days; `forecast-detail.test.js` exercises ten accepted and eleven refused.
The native provider horizon is measured from initialization. A 360-hour product
cannot promise fifteen full days remaining after acquisition and publication.
No new long-range console view is added. Revisit only with a bounded expandable
view that demonstrates useful remaining, source-qualified coverage and labels
uncertainty without shrinking the current console.

Raw temperature p10/p90 retain their native source and remain separate from the
displayed point correction. They are not locally verified coverage intervals.
The existing forecast modal contains an optional experimental-comparison
disclosure. Opening it starts the fixed read-only marginal and rain report
subscriptions; closing it removes those subscriptions. The default forecast
remains usable when the optional reports are absent, stale, malformed or offline.
Original report clocks and confirmed emission identities govern availability.

Rain details show the three original interval means and any supported local
experimental amount separately. An exact target interval and original source age
are visible. The display withholds local rain probability: its public contract
lacks a complete wet-event threshold definition, and no local probability is
qualified. Marginal mean, median and p10/p90 are labeled by their actual statistic
and remain experimental. This work does not sum quantiles into interval quantiles
or infer rain probability from a mean.

The 1340×800 and 1280×720 browser fixtures cover disclosure navigation, loading,
zero, stale/malformed/offline/withdrawal and reconnect behavior without changing
the primary forecast. Both expanded screenshots were visually inspected. The
existing modal suite covers focus restoration and chart resize. A full branch
verification and release review remain required before installation.

Existing distinctions remain necessary: terrain direct-sun hours differ from
astronomical daylight; native direct/diffuse radiation differs from a radiation
proxy; simulated nominal storage differs from measured battery history. A grid
station-head forecast is a native grid product, not arbitrary household-coordinate
inference. Local sensor representativeness and physical calibration are separate
questions; device identification does not establish calibration.

## Private diagnostics

Collection writes `ingest-status.json` in the private archive after a real collect
attempt. Probe mode does not write it. A pre-reader failure can replace a previous
success diagnostic in an existing archive without creating a new archive. Failure
records do not borrow an older successful forecast as their current source.

The bounded report retains original initialization and acquisition clocks,
ingestion lag, current source age, native run/collection identities, enabled
profiles, optional refusals/retry clocks, actual request/transfer/runtime/RSS
counts and conservative archive runway. Provider revision and EECU used/remaining
remain explicitly unknown where the retained contract does not expose them.
Request counts and bytes are not converted into billing or EECU estimates.

An applied evaluation writes `operations.json` beside the original private score
reports. It retains the score report identity, queue states/backlog, daily pending
windows, rain interval state, correction coverage and bounded original artifact
and procedure cohorts. Auxiliary reports retain their original clocks, stale
status, identities and separate scopes. Counts are not pooled across scopes.
Configured model/procedure identities are validated and explicitly labeled as
configuration, not proof of effective serving admission. A missing selection and
an invalid selection have different statuses.

Both reports are capped at 128 KiB and private to the service account. Domain or
write failures leave the core collection/scoring outcome intact. The shared owner
deadline, admission deferral and memory-stop exceptions still propagate. These
projections issue no additional cloud queries, observation reads, fits, promotion
requests or control calls. Existing observation and acquisition budgets remain
unchanged. No new public diagnostics route exposes these private reports.

## Deliberately unused capabilities

| Capability | Disposition and reason | Evidence needed to revisit |
| --- | --- | --- |
| 100 m turbine winds | Unused; the household has no turbine forecast consumer. Existing near-surface wind semantics remain separate. | An actual turbine, hub-height/site specification, decision owner and measured validation target. |
| Upper-air and ocean fields | Unused; no bounded household decision or validated incremental skill. | A named household use case and a past-only comparison showing benefit within the shared budget. |
| Arbitrary-coordinate custom inference | Unused; native grid forecasts suffice for current consumers. No claim that grid station-head output is custom household inference. | Evidence that representativeness limits an actual decision, plus an available source, exact site contract and explicit cost budget. |
| Bulk spatial downloads | Unused; current site needs bounded native-cell originals. | A defined multi-site or spatial decision, retention plan and measured cost/resource envelope. |
| Full ensembles | Unused; no accessible retained full-member product or qualified joint-probability consumer. Marginal quantiles are not members. | Authorized member access, bounded ingestion, coherent trajectory validation and a consumer benefiting from qualified joint outcomes. |
| Paid backend migration | Unused; account EECU balance is not observable and no billing migration is authorized. | A measured limitation, concrete benefit/cost comparison and explicit authorization for paid access. |

These are explicit dispositions, not unfinished feature implementations. The [capability matrix](capability-matrix.json) inventories every declared field
and feature, including acquired, normalized, consumed, tested, installation,
observation and qualification states. Task 11 must update actual production
replacement and readback evidence separately. The October 22
[deployment policy](deployment-policy.json) requires direct production replacement
and evaluation after activation, without a parallel shadow period. Existing
shadow-format readers/receipts remain historical compatibility interfaces; their
immutable flags must not be rewritten into production admissions.
