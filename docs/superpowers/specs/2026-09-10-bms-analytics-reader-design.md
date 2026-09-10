# BMS analytics reader cutover — proposed

Status: awaiting operator review. The atomic producer contract at43ccb08 is
approved and its live source, output, expiry and recovery checks are complete.
This proposal resolves downstream numerical and rollout semantics; it does not
authorize notification-policy changes or claim reader implementation.

## Verified current state

Solar_PV main91867f8 is clean. Its `analytics/config/metric-sources.json` assigns
`battery.soc_pct` to numeric `BMS_SOC`, with `BMS_Comms_Status` as an indefinitely
carried OK companion. `daily.build_daily_snapshot` calculates battery statistics
before applying source-quality labels. `aggregate_battery` uses a single point
series and trapezoidal integration; merely dropping invalid points could connect
across gaps. `feature_reader.fetch_feature_rows` independently selects the last
numeric SoC at each grid time and one-hour lag, without an evidence expiry bound.

`system-epochs.json` owns the physical bank epoch `discover_4_module_2026` from
July19. `streamEpoch` is only observer-cache provenance. Existing EFC uses
charge/discharge energy divided by twice20.48kWh; it is not SoC-throughput EFC.
These definitions must not change with observer restarts or reader migration.

The deployed evidence stream is demonstrated to expire before the status flag
changes on the next cron. A reader must enforce validUntil itself. Exact live
receipts are in `docs/operations/2026-09-10-bms-natural-qualification.md`.

## Alternatives

1. Change quality labels only. Smallest patch, but leaves invalid extrema and
   unbounded feature carry available to algorithms. Does not finish the requested
   change-aware algorithm correction.
2. **Recommended: shared validated intervals and their own SoC values.** One
   parser/interval API supplies daily SoC statistics, SoC feature columns and
   future outcome assessment. This keeps value and qualification atomic.
3. Authorize carried legacy BMS_SOC with separate JSON evidence. Preserves the
   numeric reader but can join a legacy value to evidence for a different value.
   It does not preserve the producer's atomic value/provenance contract.

## Recommended behavior

Implement one pure parser and interval builder under Solar_PV analytics. Input
is the original JDBC `(persisted_at, JSON)` sequence, including a bounded prior
record when needed; do not replace original timestamps with window boundaries.
Validate exact version1 keys, UUID stream epoch, finite0–100 SoC, integer UTC
timestamps, source times no later than recordedAt, recordedAt no later than
original persistence, and exact min(source times)+120000 validity. Unavailable
records must have the specified reason and null measurement fields. Reject
duplicate JSON keys, booleans-as-numbers, nonfinite values and malformed records.

Valid segments carry that record's own `soc`, starting no earlier than both
recordedAt and persistence time, ending no later than validUntil or the next
record boundary. Use half-open UTC intervals clipped to the requested window
and configured physical-bank dates. No segment crosses a known fault, malformed
record or observer epoch transition. A well-formed next record bounds prior
coverage at its recordedAt; malformed data bounds it at its persistence time.
No invalid, duplicate, conflicting or out-of-order record may extend coverage.
Ambiguous ordering fails closed instead of silently selecting an arbitrary row.

Observer epoch changes create coverage boundaries, never a new battery epoch or
a reset of cumulative counters. The configured physical bank remains authoritative;
no new epoch-mapping database or parallel history store is required.

Daily SoC extrema, range/DoD, threshold durations, time-weighted mean and sunrise/
sunset or overnight values use qualified segments. Do not flatten them into a
single point list that reconnects gaps. Missing event-time coverage yields null,
not a previous unqualified SoC. Preserve the DoD formula max minus min and the
existing90percent quality gate; partial coverage stays explicit. Preserve all
power/temperature paths, energy-throughput EFC computation and BMS counters.

Feature export uses qualified SoC at each actual grid time. Its one-hour lag is
qualified independently at the lag time, including physical-bank boundaries.
Missing coverage produces null SoC fields. Forecast, power, weather and other
feature semantics remain unchanged; they retain their separately tracked audits.
Future SoC outcome assessment reuses this API rather than implementing another
parser or treating historical numeric SoC as validated atomic evidence.

## Rollout and evidence

First implement/test the shared reader, then daily and feature callers. Exercise
the real observed expiry/recovery sequence, irregular cadence, unchanged values,
publication delays, faults, malformed/duplicate records, epoch transitions,
carry-in without relabeling, half-open boundaries, Denver23/25-hour days, and
missing/empty history. Prove gaps are not interpolated and pre-stream history
never gains qualifying coverage. Test accounting formulas and unrelated metrics
for parity. Independently review before integration.

Run read-only comparisons against actual PostgreSQL rows before deployment.
No historical materialized report is rewritten or backfilled. New scheduled days
use the corrected reader; insufficient coverage remains insufficient, including
the partial first source day. Existing schedules and everyChange persistence stay
unchanged. Source Items/rules and physical controls are not modified by this work.
Rollback restores reader/config code only, preserving all accumulated history.

UI/checker freshness migration remains a separate slice: the current checker
uses12minutes while evidence expires after2minutes. This proposal does not change
DM eligibility, rate limits, wording, recovery messages, runtime-basis behavior,
or notification timing. No test DMs are authorized. Task82 remains held; weather
validation, outcome assessment and learned threshold tuning remain outstanding.
