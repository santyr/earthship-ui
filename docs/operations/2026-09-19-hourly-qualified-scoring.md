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

Verification:81focused hourly/forecast tests pass, including unavailable,
expired/future/nonfinite evidence, no fallback, cutover eligibility, exactly-once
updates, count bounds, prior buckets and atomic save/reload. Remaining work:
natural source/persistence qualification, worker/config wiring, integration with
the separate completed-trough branch, full regression and attended activation.
