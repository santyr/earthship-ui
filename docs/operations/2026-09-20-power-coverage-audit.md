# Power coverage and estimated cycle accounting

Read-only source trace and isolated production-function reproduction on September
20. This establishes a software-contract gap, not an observed physical outage or
a quantified error in existing daily records.

## Verified behavior

In `/home/sat/Solar_PV/analytics/src/earthship_energy/`:

- `reader.fetch_numeric_series` obtains original numeric carry and changes;
  `normalize_window_series` supplies numeric start/end boundaries.
- `daily.build_daily_snapshot` uses a maximum numeric gap equal to the entire
  local day. Battery, PV and load energy are computed before freshness assessment.
- `daily.apply_source_quality` lowers coverage/quality labels, but does not clip
  numerical integration to the intervals supported by health evidence.
- `materialize.materialize_daily_snapshot` accepts successful snapshots without
  requiring battery quality `ok`. `_recompute_battery_rollups` sums all daily EFC
  records within the bank epoch, without a quality predicate.
- UI `latestEfc` is quality-gated, whereas `endingCumulativeEfc` can be exposed
  independently of that latest-day gate. Changing only the UI would not repair
  accounting.

An isolated Python probe imported the production reader, integrator and quality
assessor. Inputs: a 1000 W carry from the previous day, no numerical changes in
a 24-hour UTC window, and one timestamp health receipt at the start with a
120-second TTL. The reader/integrator produced **24 kWh**; the independent quality
assessor correctly reported **120 qualified seconds**, coverage **1/720**, and
`insufficient_data`. No SQL writes, live Item updates or forced rule runs occurred.
This probe does not execute a full scheduled materialization; the persistence
conclusion above is from the traced materializer code.

## Required correction boundary

Power accounting must consume explicitly qualified intervals, with numerical
values and coverage derived from the same intervals. Held change-only state is
not itself an outage; neither is it independent freshness evidence. Invalid
values, expired health, restart boundaries and persistence delays must not be
bridged. The existing coarse Schneider group timestamps require a separate
per-field receipt-contract audit before being promoted to independent evidence.

Historical estimated totals must not be silently rewritten or relabeled as
qualified. A correction needs an explicit version/cutover and cumulative policy
that distinguishes observed qualified throughput, missing coverage and legacy
estimates. Filtering out whole partial days alone discards real measured use and
does not meet this requirement. Preserve bank epochs and manufacturer counters.

Before implementation, read Solar_PV's cross-repository contracts, inspect its
working tree and test scheduled/materialized/report/UI consumers together. No
analytics code, database schema, control rule or historical total was changed
in this audit. Thermal training PID2326440 remained actively running, so pending
shared temperature-runtime deployment remains held until that run is terminal.
