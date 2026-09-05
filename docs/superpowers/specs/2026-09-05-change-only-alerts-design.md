# Change-only telemetry and transition-aware alerts

## Scope and approval

Sat directed Hex to make all algorithms compatible with change-only persistence.
This spec covers the first corrective slice: the dashboard's essential telemetry
freshness and the external sanity checker's runtime-basis warnings. It does not
close the broader historical-algorithm audit or the approved advisory-outcome work.
Written review of the alert defaults below is pending. Implementation and testing
will be isolated from the live UI checkout; deployment needs separate approval.

Keep JDBC everyChange and restoreOnStartup unchanged. Do not alter estimator
gates, advisory thresholds, household controls, the forecast schedule, or counters.
Task 82 remains on hold. Never send test DMs or save decrypted DM archives.

## Verified cause and available evidence

- UI snapshots and value-change events currently set a local Date.now() clock.
  Snapshot receipt can rejuvenate old data, while unchanged healthy values age
  into false alerts. BMS_SOC's 60-minute threshold merely delays this error.
- Live REST item DTOs expose lastStateUpdate as epoch milliseconds, including
  bulk item queries when that field is requested. Temperature update timestamps
  differ from lastStateChange, confirming unchanged updates are available.
- Live ItemStateUpdatedEvent events exist on the stateupdated topic. Their
  payload carries lastStateUpdate as a zoned ISO timestamp, sometimes with
  nanosecond precision and an appended [America/Denver] zone identifier.
  Existing proxy policy permits the required reads; no access expansion is needed.
- BMS_SOC_LastUpdate is a timestamp VALUE, rate-gated to five minutes. The scaler
  independently derives BMS_Comms_Status from a 120-second raw-input timeout.
  Neither persisted SoC row age nor SoC's own update timestamp proves BMS health.
- The external checker flags bms plus charging immediately. The live estimator
  intentionally holds its internal discharge/deep states for eight minutes.
  A controlled replay of the installed checker reproduced the warning with a
  valid 420-minute estimate and +16.85 A, with all I/O replaced and sends blocked.

## Dashboard correction

Keep the existing value-change stream for ordinary item rendering. Add targeted
stateupdated subscriptions for the two essential temperature items, with a
separate update-evidence callback. This avoids subscribing the tablet to every
unchanged update from every item, or rendering twice for each temperature change.

Request lastStateUpdate in initial and reconnect snapshots. Store upstream update
evidence separately from value-change delivery; receipt time never counts as
sensor freshness. Targeted update events refresh this evidence even when the
temperature value is unchanged. An older snapshot/event cannot move a known
source timestamp backward. Missing or malformed evidence must not manufacture
freshness or erase a previously known timestamp; retain it for diagnosis but mark
the current evidence unavailable until a valid update arrives. Ignore an older
valid event rather than treating it as a new failure.

Use one tested timestamp parser for finite epoch milliseconds and explicitly
offset-qualified ISO values. Strip an optional bracketed zone suffix and truncate
sub-millisecond fractions without changing the instant. Reject unzoned, invalid,
non-positive, and future timestamps rather than guessing a timezone or clamping
them to now. Report unusable evidence as unavailable, not as a healthy sensor.

Retain the temperature threshold of 15 minutes, now measured from actual sensor
updates. For BMS use the heartbeat timestamp value and a 12-minute threshold,
matching the external checker's existing allowance for the five-minute gate.
Fresh heartbeat plus comms OK means a long unchanged SoC is not stale.

An explicit non-OK comms status or absent-device indication retains the existing
critical battery alert; suppress only a redundant battery freshness warning.
Missing/NULL/UNDEF comms or heartbeat after initial snapshot means freshness is
unavailable and merits a warning. A stale heartbeat with comms OK still warns.
Before the first snapshot, retain the existing connection/boot handling instead
of manufacturing per-item missing-data alarms. No changes to hardware gating.

## External sanity checker correction

Bring the currently untracked installed checker into openhab/scripts with tests
before deploying any replacement. Retain its rule/range/heartbeat checks and
notification rate limit. Tests intercept REST, notification and state I/O.

Do not call a single charging snapshot a stuck gate. Store a pending mismatch's
first observation and the basis transition identity in the existing checker state
file. Warn only when a subsequent valid observation of the same bms episode is
at least eight minutes later. The existing ten-minute timer therefore normally
warns on its second observation. Do not claim continuous current from two samples.
Use wording such as "runtime basis remains bms during repeated charging checks"
instead of asserting that the gate is stuck.

Request lastStateChange for BMS_Runtime_Basis as the episode identity. A changed
identity, noncharging current, non-bms basis, backwards clock, or unreadable
observation breaks pending evidence. After a REST outage or unavailable basis
identity, collect a new pair of valid observations; never join across that gap.
Invalid/non-finite current is unavailable, not a healthy charging/discharging test.
Unavailable current or episode identity must produce an explicit diagnostic;
missing evidence must not silently disable the mismatch check indefinitely.
An already-active fault does not emit a recovery solely because a prerequisite
read failed. Recovery requires a valid observation that clears that fault.

Invalid/non-finite/nonpositive smoothed runtime for an active estimate remains an
immediate, independent consistency fault; the dwell allowance never suppresses it.
Freshness alarms retain their existing heartbeat basis and thresholds.

## Regression and deployment gates

Tests must cover healthy multi-hour SoC plateaus, fresh/expired/malformed/future
heartbeats, explicit comms faults, missing data after boot, equal-value temperature
updates, stale reconnect snapshots, out-of-order evidence, and both timestamp
formats. Exercise the real SSE callback/store/alert path, not only a pure helper.

Checker tests must cover first mismatch, before/at/after dwell, repeated mismatch,
basis episode changes between checks, recovery, REST failure, invalid current,
invalid runtime, clock reversal and persisted pending state across invocations.
No test may contact a live notifier or overwrite the installed state file.

Run focused tests, complete UI/Python regression suites appropriate to touched
paths, production build, and tablet browser integration tests. Independent review
must verify source freshness is not inferred from local receipt or row density.
Then present the exact commits and deployment/rollback targets for approval.

## Remaining all-algorithm audit

The following remain required, not silently deferred or claimed fixed here:

- forecast_intel series readers, day extrema, trough scoring, hourly actual
  matching: preserve carry-in and source-health evidence, avoid event-density bias,
  enforce half-open target windows and completed-night scoring.
- Midnight-reset PV and rainfall accumulators: never carry yesterday's totals
  into today's extrema or learned targets.
- Thermal historical interpolation/gap rejection: distinguish sparse changes from
  failed telemetry. Current code has a 20-minute interpolation bound and a separate
  60-minute hold bound; do not conflate them. Preserve live thermal_intel's existing
  authoritative lastStateUpdate handling.
- UI historical graphs/extrema: trace carry-in and day-boundary policies and show
  unavailable data honestly, including the primary tablet rendering path.
- Solar_PV readers, integration and daily quality: preserve original timestamp
  provenance behind synthetic boundary points; verify companion health intervals,
  restart gaps and time weighting. Do not silently rewrite EFC accounting/history.
- Live OpenHAB historical averages and other rule consumers: inventory their
  persistence semantics before claiming all algorithms are compatible.

Each historical family requires its own evidence-backed implementation slice under
the overall direction. The advisory outcome spec's source-health coverage contract
continues to apply; no automatic reward learning or weakened coverage gates.
