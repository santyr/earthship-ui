# Opt-in hourly qualified scoring seam

The existing hourly scorer can now accept a strict qualified_reader and an
explicit offset-aware evidence_cutover string. Both are required together;
invalid or future cutovers reject before mutation. No production caller passes
these arguments yet. This branch does not enable collection or learning.

Qualified mode makes no legacy numeric-history request. It only considers
elapsed targets whose original captured_at is at/after cutover and before
target. It uses the exact target's receipt-qualified reader result, rejects
future persistence/receipts, expiry and nonfinite measurements, and never
falls back after unavailable or failed reads. The strict JDBC reader remains
responsible for identity, epoch, policy, barriers and complete query validation.

Existing Kalman parameters, hour buckets and 72-hour/96-target retention are
preserved. Qualified attempts are limited to24eligible targets per invocation;
unmatched targets remain queued under existing retention, and this count bound
is NOT a worker wall-time limit. At activation the caller still needs a bounded
worker, dedicated read-only connection factory and explicit fail-closed mode
selection. Invalid enabled configuration must not silently select legacy mode.

Each successful update consumes its target and retains a bounded96entry receipt
list with target/capture/assessment/cutover, raw/measured values, original
receipt/persistence/expiry times and exact snapshot digest. The existing atomic
state save persists learned updates, consumption and provenance together.
Earlier learned values are not reset or relabeled as qualified observations.

Verification:89focused hourly/forecast tests pass, including unavailable,
expired/future/nonfinite evidence, no fallback, cutover eligibility, exactly-once
updates, count bounds, prior buckets and atomic save/reload. Remaining work:
natural source/persistence qualification, worker/config wiring, integration with
the separate completed-trough branch and attended activation.

Eight producer-to-reader-to-scorer cases additionally verify unchanged receipts,
a closer post-target observation, future-only history, exact expiry, invalid
barriers, a restarted unknown epoch, fresh recovery and foreign identity. The
restart fixture's explicit epoch change was separately rechecked with all26
qualified-scoring tests. All43strict reader/adapter tests also passed against
the explicitly supplied disposable PostgreSQL fixture (5.63seconds); no live
database was used for those tests.

The first full regression exposed two relay fixture failures: the live relay
has independently gained an optional Lightning Goats observer, while its AST
fixture did not supply that global. The fixture now explicitly supplies None
(no project DB I/O), plus a failing-observer case proving household forwarding
continues. No production relay or observer change was made. Combined relay,
hourly and forecast checks passed95tests after the fixture correction.

Fresh full script regression after correcting the observer fixture passed
943tests and42subtests in142.17seconds, with one opt-in PostgreSQL test skipped.
That skipped path was independently exercised by the43-test disposable suite
above. The later explicit epoch-change fixture refinement passed its26-test
qualified group separately. These are offline software checks, not evidence
of activated production collection, a full real pump cycle, or learned outcomes.
