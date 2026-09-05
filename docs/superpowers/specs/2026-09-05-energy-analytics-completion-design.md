# Energy analytics completion: forecast capture and daily battery use

## Scope and approval

Sat approved the first implementation slice on 2026-09-05: repair the existing
forecast snapshot consumer and expose existing daily battery-use metrics.
This document records the concrete contract for review before implementation.
It does not authorize advisory tuning, physical actions, new database schemas,
or changes to Discover BMS counters. Task 82 remains on hold.

## Verified starting point

- Solar_PV owns the analytics producer and PostgreSQL quantitative history.
  OpenHAB exposes Energy_Analytics_JSON; earthship-ui is read-only presentation.
- Forecast_10Day_JSON now has version 2 and learned temperature-adjustment
  metadata. The analytics parser requires version 1 and its scheduled service
  fails. Its latest stored issue time is August 27 despite fresh live forecasts.
- daily_battery already stores minimum/maximum SoC, daily range, daily EFC,
  and cumulative EFC. There are 48 observed dates from July 19 to September 4.
- Existing battery UI exposes daily minimum and cumulative EFC but not daily
  range or daily EFC. The current energy UI payload is a closed v1 schema.

## Chosen approach and alternatives

Reuse the existing analytics history and publisher. Repair the forecast
consumer independently, then extend the versioned energy UI contract.
This preserves one calculation owner and avoids a second accumulator.

A new OpenHAB rule summing daily SoC range was considered but rejected: daily
extrema do not measure repeated partial discharge/charge throughput, and a
second mutable counter introduces reconciliation and restart ambiguity.
Replacing the existing energy-based EFC convention with a SoC-drop convention
is also excluded: it would change the meaning of historical values.

## Forecast snapshot repair (task 96)

Support exactly integer forecast versions 1 and 2; reject booleans, unknown
versions and malformed structures. Preserve version 1 interpretation.

For version 2, validate and retain the temperatureAdjustment metadata:
finite highCorrectionF and lowCorrectionF; hourlyMethod daily-fallback or
hourly-blend; exactly 24 hourBuckets with nonnegative integer count and finite
weight in [0,1]. Persist the actual forecast version and adjustment metadata
as snapshot provenance. Values are the published corrected forecast, not raw
Open-Meteo values; never relabel them as raw training targets or correct twice.

Retain original generatedAt as issued_at, actual target timestamps as valid_for,
and existing local-day/timezone semantics. Preserve the existing rule excluding
targets earlier than issue time. Do not manufacture today-at-midnight forecasts
from predictions issued later in the day. Numeric metric values must be finite
numbers or explicit null; booleans and nonnumeric values must not become numbers.
Malformed input must fail before any snapshot rows are persisted.

Preserve append/idempotency semantics and historical v1 records. Do not
retrospectively fabricate the missing August 27–September 5 forecast origins.
The capture gap remains an explicit limitation for downstream learning.

Tests cover v1/v2, provenance, invalid versions/metadata/numbers, null values,
local dates/DST, exclusion of earlier targets, and repeated capture. Verify the
actual scheduled service and PostgreSQL latest issue time after approved deploy.

## Daily battery presentation (task 95)

Introduce earthship-energy-ui/v2 on the same observational Item. All existing
v1 fields retain their meanings; battery gains two nullable numeric fields:

- latestDepthOfDischargePct: the persisted daily maximum minus minimum SoC,
  bounded 0–100 percentage points. Label "Daily SoC range (DoD)".
- latestEfc: the persisted nonnegative daily_efc. Label "Daily estimated EFC".

The backend continues computing EFC as
(charge kWh + discharge kWh) / (2 * configured nominal usable kWh).
No new counter, no database migration, and no change to cumulative rollups.
The current bank configuration remains authoritative for capacity.

The UI accepts exact v1 and v2 shapes. For v1 only, normalize the two new values
to unavailable, never zero. Reject malformed or out-of-range v2 values. Keep
the existing <16 KiB limit, 15-minute freshness gate, epoch identity and local
through-date display. Missing or insufficient-quality evidence stays explicit;
do not promote an incomplete day to a trustworthy total.

Show the two values in the existing Energy analytics detail dialog, not as new
main-page cards. Label cumulative EFC as estimated. Explain concisely that EFC
is calculated from measured energy throughput over available bank-epoch history,
not the manufacturer's lifetime cycle count or a battery-health measurement.
Daily range is not total discharged percentage when multiple partial cycles occur.

Tests cover the producer mapping, v1 compatibility, v2 exact-field validation,
null/invalid values, freshness, existing UI behavior and the new labels. Confirm
the live values against the same persisted daily row, including epoch and date.
No changes to battery accounting equations or data are needed for this slice.

## Deployment, rollback and safety

Use isolated worktrees and preserve unrelated changes in both repositories.
Read current Solar_PV cross-repository guidance; its August 20 inventory is a
historical snapshot, not proof of current runtime state.

Deploy the UI reader supporting both v1 and v2 before switching the analytics
publisher to v2. Preserve installed source/configuration backups and verify
exact deployment targets. Reuse the existing scheduler; no duplicate timers.
The forecast repair can be deployed and verified independently of UI v2.

Normal activation performs only the existing authorized analytics service
operations: snapshot history inserts and publication to Energy_Analytics_JSON.
Do not write forecast origins, BMS counters, advisory Items, rules, actuators,
or unrelated schemas. Production verification must respect separately required
deployment authorization and file-system permissions.

For rollback, restore the publisher to v1 before removing UI v2 support; the
dual-version UI remains safe with the old publisher. Keep captured valid history
and deployment evidence rather than deleting it. A failed capture retains old
history and honest stale status; it must not be disguised by a new timestamp.

## Completion criteria

1. Both repository test suites relevant to changed contracts pass, including
   regression tests that fail on the old forecast consumer.
2. Scheduled forecast capture succeeds with the real v2 payload and writes
   genuinely current issue times; Energy analytics no longer selects August 27
   solely because the consumer rejected later versions.
3. The live v2 battery payload matches the persisted day; the existing detail
   dialog renders daily minimum, range, daily EFC and cumulative estimated EFC.
4. Legacy v1 payloads remain readable and invalid evidence remains unavailable.
5. BMS counters, household actions and advisory policy are unchanged.
6. Canonical cross-repository contracts, operating guidance, task records and
   deployment verification describe the implemented result accurately.

## Outstanding work not satisfied by this slice

Task 18 still needs linked decision/action/outcome evidence before tuning.
Current forecast state retains an advisory category in a 30-day prediction map
and a once-per-day DM marker; neither is a validated delayed-reward ledger.
Ten thermal action events exist, but their existence does not establish a
verified decision-to-outcome scoring loop. Tasks 16, 19, 21 and 22 remain in the
separate outstanding-work tracker with their evidence and approval gates.
