# Validated BMS SoC evidence

## Approval and purpose

Sat approved a separate validated SoC freshness signal for alerts and analytics
on September 5, then approved documenting its source checks, restart behavior
and consumer rollout. This implements that decision without changing the scaler
or any physical-control gate. Task 82 remains held.

The existing heartbeat refreshes before raw validation and on scale changes.
The reproduced cases and version-matched event-source investigation are in
`docs/operations/2026-09-05-outcome-source-health-preflight.md`.

## Architecture

Add one observational rule `hex_bms_soc_evidence`, writing only one String Item
`BMS_SOC_Evidence_JSON`. A single versioned JSON record keeps status, numeric
value and provenance atomic. Separate timestamp/status Items were rejected
because consumers could join different updates. Reinterpreting the existing
heartbeat was rejected because its communication/control semantics must remain
unchanged. This is OpenHAB-owned evidence, not a new external telemetry service.

The first implementation increment supplies the source and disabled deployment
descriptor plus exact-script tests. No runtime activation is implied by merging.
The subsequent attended release must install/read back this exact rule and Item,
verify naturally occurring records, then migrate alert/UI and analytics readers.
No legacy evidence is relabeled, and no alert uses a nonexistent Item at cutover.

## Inputs and qualification

Subscribe to state UPDATE events for `BMS_SOC_Raw` and
`BMS_SOC_ScaleFactor_Raw`, CHANGE events for `BMS_Comms_Status` and
`BMS_DevicePresent`, and a one-minute cron for expiry/startup reconciliation.
Use private in-memory cache only; never restore the qualifying input cache from
Items or JDBC. A new cache lifetime gets a UUID stream epoch.

Only exact `ItemStateUpdatedEvent` inputs with sources equal to
`org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:socRaw:number`
and `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:socSf:number`
qualify their respective values. Reject missing, persistence, REST, other-channel,
suffix and arbitrary delegated source chains. Source text is provenance, not an
authentication boundary against privileged OpenHAB code.

Support the installed converted event's `raw` Java Map original event and direct
Java event form. Read the event's own item state, source and lastStateUpdate,
not a later Item snapshot or invocation time. Require integer millisecond
timestamps, positive and no later than now, and at most 120 seconds old.
Ignore trusted out-of-order or duplicate observations for the same field.
Bad source, malformed timestamp, or invalid new value clears that field.

Raw SoC must be a strict unsigned decimal integer, 0 through 65534 (65535 is
invalid). Scale must be a strict signed decimal integer, -32767 through 32767
(-32768 is invalid). Reject NULL, UNDEF, empty, partial numbers, units, fractional
values and nonfinite values. Scaled `raw * 10 ** scale` must be finite and in
0 through 100; nonzero raw underflowing to zero is invalid. Do not use the
scaler's default scale or its above-100 clamp as measurement validation.

Both independent input observations must be fresh within the existing 120-second
raw communication allowance. Scale-only activity never advances raw observation
time. Comms must be exactly OK and DevicePresent numerically 1; missing or fault
companions clear both cached observations. Recovery requires new binding evidence
for both fields. No cached value is carried across a known fault or cache restart.

## Record and persistence contract

Closed record fields: `version` (integer 1), `streamEpoch` (UUID), `recordedAt`
(UTC milliseconds), `status` (`valid` or `unavailable`), `reason` (`ok`,
`source_unavailable`, `input_unavailable`, `input_stale`, or `invalid_scaled_soc`),
`observedAt`, `scaleObservedAt`, `validUntil`, `soc`.

Valid records use the raw and scale event timestamps and
`validUntil = min(observedAt, scaleObservedAt) + 120000`. Unavailable records
set the four measurement fields to null. Epoch is local stream provenance,
not a bank epoch; analytics must still intersect the configured bank/source epoch.

Publish immediately on status/reason/value changes, otherwise at most once per
60 seconds for valid evidence. A valid record with unchanged SoC still advances
from genuine raw observations. Repeated unavailable records are suppressed.
No cron or scale event invents a raw timestamp. Cache the publication receipt
only after postUpdate returns; a failed publication is retried on a later normal
trigger with a constant diagnostic, without retry loops or commands.

Persist only `everyChange` plus `restoreOnStartup`, preserving all existing
persistence strategy definitions. Historical coverage starts no earlier than
both the record's original persistence time and recordedAt, ends by validUntil,
and is interrupted by unavailable records and epoch transitions. A restored JSON
record does not bootstrap the producer. Live consumers must validate expiry and
current comms/device companions; producer startup publication replaces restored
evidence with unavailable until new raw and scale observations arrive.

## Verification and rollout

Exact-script VM tests deny all output Items except BMS_SOC_Evidence_JSON and
provide no commands, notifier, persistence calls or network. Test healthy
unchanged raw/scale events, restored JSON/cache restart, all input/source/time
rejections, delayed/out-of-order events, scale-only expiry, fault/recovery,
publication cadence/failure and source immutability.

The descriptor is disabled by default and is not added to an existing broad
apply bundle. Release tooling must be receipt-bound, exact-target and drift
guarded. Before activation verify installed event source matches the pinned
contract from natural traffic; a mismatch stays unavailable and needs diagnosis,
never a broad source-prefix fallback. Snapshot affected resources, check original
scaler/control script hashes before and after, and prove change-only persistence.

Reader rollout remains incomplete until UI/checker, daily analytics and outcome
assessment use this evidence contract as appropriate, with no retrospective
learning resets or manufactured history. Deployment rollback disables only the
new observer and restores affected reader configuration; retain captured history.
